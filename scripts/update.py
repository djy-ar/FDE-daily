#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FDE 每日行业动态 —— 自动抓取与数据追加脚本（仅用 Python 标准库，无需 pip 安装）

由 .github/workflows/daily.yml 每天北京时间 08:30（UTC 00:30）自动运行一次。
职责：
  1. 从 Hacker News Algolia API / Google News RSS / 科技媒体 RSS 抓取过去 window 天的 FDE 相关条目
  2. 用严格的术语闸门过滤（必须命中 forward deployed engineer / FDE / 前沿部署工程师 等）
  3. 按「链接指纹 + 标题指纹」双重去重
  4. 追加写入 data/items.json，并重新生成 data/feed.xml（RSS）

设计原则：
  - 只搬运来源原文，绝不自行编造或改写事实（缺字段就留空）
  - 单个信息源失败不影响其他源，全部失败时以非零码退出，让 CI 报警
  - 幂等：重复运行不会产生重复条目

本地调试：
  python scripts/update.py --dry-run          # 抓取并打印，不写文件
  python scripts/update.py --rebuild-feed     # 只用现有 items.json 重新生成 feed.xml
  python scripts/update.py --window 1         # 抓取窗口（天），默认 1
"""

import argparse
import hashlib
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")
ITEMS_FILE = os.path.join(DATA_DIR, "items.json")
FEED_FILE = os.path.join(DATA_DIR, "feed.xml")

TZ_CN = timezone(timedelta(hours=8))          # 北京时间
UA = "Mozilla/5.0 (compatible; fde-daily-bot/1.0; GitHub Actions scheduled fetch)"
TIMEOUT = 15
RETRIES = 2
MAX_KEEP = 2000                               # items.json 最多保留条目数
MAX_AGE_DAYS = 365                            # 超过一年自动淘汰

SITE_NAME = "FDE 每日行业动态"
SITE_DESC = "Forward Deployed Engineer（前线/前沿部署工程师）行业动态每日聚合"

# ---------------------------------------------------------------- 信息源配置
# 想加源，直接往这里添。type 支持 hn / gnews / rss 三种。
SOURCES = [
    # --- Hacker News Algolia API：实时检索，最稳定，无需解析 RSS
    {
        "name": "Hacker News",
        "type": "hn",
        "queries": ['"forward deployed engineer"', '"forward-deployed engineer"', "FDE deployment"],
        "tags": "story",
        "tier": "社区讨论",
    },
    # --- Google News RSS：跨媒体关键词检索（中文源）
    {
        "name": "Google News 中文",
        "type": "gnews",
        "queries": [
            '"前沿部署工程师" OR "前线部署工程师" OR "前置部署工程师"',
            '"Forward Deployed Engineer" 中国',
        ],
        "hl": "zh-CN", "gl": "CN", "ceid": "CN:zh-Hans",
        "lang": "zh", "tier": "行业观察",
    },
    # --- Google News RSS：英文源
    {
        "name": "Google News EN",
        "type": "gnews",
        "queries": [
            '"forward deployed engineer"',
            'forward deployed engineer hiring OR salary OR "AI"',
        ],
        "hl": "en-US", "gl": "US", "ceid": "US:en",
        "lang": "en", "tier": "行业观察",
    },
    # --- 科技媒体 RSS：整源抓取后按关键词过滤（这些站不一定天天写 FDE）
    {
        "name": "TechCrunch",
        "type": "rss",
        "urls": ["https://techcrunch.com/category/artificial-intelligence/feed/"],
        "sourceUrl": "https://techcrunch.com/category/artificial-intelligence/",
        "lang": "en", "tier": "行业观察",
    },
    {
        "name": "The Verge AI",
        "type": "rss",
        "urls": ["https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"],
        "sourceUrl": "https://www.theverge.com/ai-artificial-intelligence",
        "lang": "en", "tier": "行业观察",
    },
    {
        "name": "VentureBeat AI",
        "type": "rss",
        "urls": ["https://venturebeat.com/category/ai/feed/"],
        "sourceUrl": "https://venturebeat.com/category/ai/",
        "lang": "en", "tier": "行业观察",
    },
]

# ---------------------------------------------------------------- 术语闸门
TERMS = [
    "forward deployed engineer", "forward-deployed engineer", "forward deployment engineer",
    "forward-deployment engineer", "forward deployed engineering", "forward deployed",
    "前沿部署工程师", "前线部署工程师", "前置部署工程师", "前沿驻场工程师", "驻场部署工程师",
    "fdde",
]
FDE_RE = re.compile(r"(^|[^a-z])fde([^a-z]|$)")


def is_fde(text):
    hay = (text or "").lower()
    for t in TERMS:
        if t in hay:
            return True
    return bool(FDE_RE.search(hay))


# ---------------------------------------------------------------- 分类规则
TIER_RULES = [
    ("政策信号", ["工信部", "监管", "政策", "国家标准", "试点", "发文", "意见稿"]),
    ("大厂动向", ["openai", "anthropic", "palantir", "google", "microsoft", "aws", "amazon",
                  "meta", "salesforce", "字节", "阿里", "腾讯", "蚂蚁", "百度", "美团", "智谱",
                  "deepseek", "siemens", "IBM", "Oracle", "Nvidia"]),
    ("行业报告", ["研报", "报告", "研究显示", "数据显示", "洞察报告", "gartner", "lightcast",
                  "indeed", "领英", "linkedin", "脉脉", "猎聘", "智联", "mckinsey", "bain",
                  "survey", "report", "study"]),
    ("薪酬人才", ["salary", "薪", "年包", "总包", "compensation", "招聘", "hiring", "job",
                  "岗位", "人才缺口", "缺口", "岗位数量", "职位发布"]),
    ("方法论", ["how to", "guide", "roadmap", "best practice", "教程", "区别", "怎么做",
                "framework", "playbook", "tips"]),
    ("社区讨论", ["hacker news", "reddit", "Ask HN", "Show HN", "知乎", "微博"]),
]


def classify(item):
    hay = (item.get("title", "") + " " + (item.get("summary") or "")).lower()
    for name, kws in TIER_RULES:
        for kw in kws:
            if kw.lower() in hay:
                return name
    return "行业观察"


# ---------------------------------------------------------------- 工具函数
def http_get(url, timeout=TIMEOUT):
    last = None
    for i in range(RETRIES):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read()
            enc = r.headers.get_content_charset()
            try:
                return raw.decode(enc or "utf-8", "replace")
            except Exception:
                return raw.decode("utf-8", "replace")
        except Exception as e:                       # noqa: BLE001
            last = e
            time.sleep(2 * (i + 1))
    raise RuntimeError("%s -> %s" % (url, last))


def clean(s):
    if not s:
        return ""
    s = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", s, flags=re.S)
    s = html.unescape(s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s[:500]


def pub_str(dt):
    """统一成 YYYY-MM-DD（北京时间），前端按日期做区间筛选。"""
    if dt is None:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(TZ_CN).strftime("%Y-%m-%d")


def parse_dt(text):
    if not text:
        return None
    text = text.strip()
    fmts = ["%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z",
            "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"]
    for f in fmts:
        try:
            return datetime.strptime(text[:32] if "T" in f else text, f)
        except ValueError:
            continue
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", text)
    if m:
        return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=timezone.utc)
    return None


def fingerprint(url, title):
    u = re.sub(r"[?#].*$", "", (url or "").lower().rstrip("/"))
    t = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", (title or "").lower())
    return hashlib.sha1(("U:" + u).encode()).hexdigest(), hashlib.sha1(("T:" + t).encode()).hexdigest()


def make_item(url, title, summary, source, source_url, published, lang, tier_hint, extra=None):
    title = clean(title)
    if not title or not url:
        return None
    it = {
        "id": hashlib.sha1(url.encode()).hexdigest()[:16],
        "url": url.strip(),
        "title": title,
        "summary": clean(summary),
        "source": source,
        "sourceUrl": source_url or "",
        "published": published,
        "lang": lang,
        "tier": tier_hint or "行业观察",
        "tags": [],
    }
    if extra:
        it.update(extra)
    if not is_fde(it["title"] + " " + it["summary"] + " " + " ".join(it.get("tags") or [])):
        return None                                   # 闸门：正文没提到 FDE 相关术语的一律丢弃
    it["tier"] = classify(it) if not tier_hint or tier_hint == "自动" else it["tier"]
    return it


# ---------------------------------------------------------------- 各源抓取器
def fetch_hn(src, since):
    out = []
    for q in src["queries"]:
        api = "https://hn.algolia.com/api/v1/search_by_date?query=%s&tags=%s&hitsPerPage=50" % (
            urllib.parse.quote(q), src.get("tags", "story"))
        try:
            data = json.loads(http_get(api))
        except Exception as e:                        # noqa: BLE001
            log("HN 源失败: %s" % e)
            continue
        for h in data.get("hits", []):
            created = h.get("created_at") or ""
            dt = parse_dt(created)
            if not dt or dt < since:
                continue
            title = clean(h.get("title") or "")
            body = h.get("story_text") or ""
            url = h.get("url") or ("https://news.ycombinator.com/item?id=%s" % h.get("objectID"))
            it = make_item(
                url=url, title=title,
                summary=body if url == title else (body or ""),
                source="Hacker News",
                source_url="https://news.ycombinator.com/",
                published=pub_str(dt), lang="en", tier_hint=src["tier"],
                extra={"hn": {"id": h.get("objectID"), "points": h.get("points"),
                              "comments": h.get("num_comments")}},
            )
            if it:
                it["tags"] = ["HN"] + (h.get("_tags") or [])[:3]
                out.append(it)
    return out


def fetch_gnews(src, since):
    out = []
    for q in src["queries"]:
        api = ("https://news.google.com/rss/search?q=%s&hl=%s&gl=%s&ceid=%s"
               % (urllib.parse.quote(q), src["hl"], src["gl"], src["ceid"]))
        try:
            xml_text = http_get(api)
        except Exception as e:                        # noqa: BLE001
            log("Google News 源失败: %s" % e)
            continue
        for raw in parse_rss(xml_text):
            dt = parse_dt(raw.get("pubDate"))
            if not dt or dt < since:
                continue
            title = raw["title"]
            # Google News 标题常带 " - 来源名"，拆出来当来源
            if " - " in title:
                head, tail = title.rsplit(" - ", 1)
                srcname = tail.strip()[:40]
            else:
                head, srcname = title, src["name"]
            it = make_item(
                url=raw["link"], title=head, summary=raw.get("description") or "",
                source=srcname or src["name"], source_url="",
                published=pub_str(dt), lang=src["lang"], tier_hint=src["tier"],
            )
            if it:
                out.append(it)
    return out


def fetch_rss(src, since):
    out = []
    for u in src["urls"]:
        try:
            xml_text = http_get(u)
        except Exception as e:                        # noqa: BLE001
            log("RSS 源失败 %s: %s" % (u, e))
            continue
        for raw in parse_rss(xml_text):
            dt = parse_dt(raw.get("pubDate"))
            if not dt or dt < since:
                continue
            it = make_item(
                url=raw["link"], title=raw["title"], summary=raw.get("description") or "",
                source=src["name"], source_url=src.get("sourceUrl", ""),
                published=pub_str(dt), lang=src.get("lang", "en"), tier_hint=src.get("tier"),
            )
            if it:
                cats = raw.get("categories") or []
                if cats:
                    it["tags"] = [c for c in cats if is_fde(c) or len(c) < 22][:4]
                out.append(it)
    return out


def parse_rss(xml_text):
    """极简 RSS/Atom 解析，返回 [{title,link,pubDate,description,categories}]。"""
    items = []
    try:
        root = ET.fromstring(xml_text.encode("utf-8", "ignore"))
    except Exception as e:                            # noqa: BLE001
        log("XML 解析失败: %s" % e)
        return items
    ns_a = "{http://www.w3.org/2005/Atom}"

    def text_of(node, tag):
        if node is None:
            return ""
        el = node.find(tag)
        if el is None:
            el = node.find(ns_a + tag)
        return (el.text or "") if el is not None else ""

    for it in root.iter("item"):
        link = text_of(it, "link")
        items.append({
            "title": text_of(it, "title"),
            "link": link,
            "pubDate": text_of(it, "pubDate") or text_of(it, "date"),
            "description": text_of(it, "description") or text_of(it, "encoded"),
            "categories": [text_of(c, "title") or (c.text or "") for c in it.findall("category")],
        })
    if not items:                                    # Atom feed
        for it in root.iter(ns_a + "entry"):
            link = ""
            for l in it.findall(ns_a + "link"):
                if l.get("rel") in (None, "alternate"):
                    link = l.get("href") or ""
                    break
            items.append({
                "title": text_of(it, "title"),
                "link": link,
                "pubDate": text_of(it, "updated") or text_of(it, "published"),
                "description": text_of(it, "summary") or text_of(it, "content"),
                "categories": [],
            })
    return [i for i in items if i.get("link")]


FETCHERS = {"hn": fetch_hn, "gnews": fetch_gnews, "rss": fetch_rss}


# ---------------------------------------------------------------- 日志
LOGS = []


def log(msg):
    line = "[%s] %s" % (datetime.now(TZ_CN).strftime("%H:%M:%S"), msg)
    LOGS.append(line)
    print(line)


# ---------------------------------------------------------------- 合并与输出
def load_items():
    if os.path.exists(ITEMS_FILE):
        try:
            with open(ITEMS_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:                        # noqa: BLE001
            log("现有 items.json 读取失败，将重建: %s" % e)
    return {"meta": {}, "items": []}


def merge(store, fresh):
    u_fp = set()
    t_fp = set()
    for it in store.get("items", []):
        a, b = fingerprint(it.get("url"), it.get("title"))
        u_fp.add(a)
        t_fp.add(b)
    added = []
    for it in fresh:
        a, b = fingerprint(it.get("url"), it.get("title"))
        if a in u_fp or b in t_fp:
            continue
        u_fp.add(a)
        t_fp.add(b)
        added.append(it)
    pool = store.get("items", []) + added
    pool.sort(key=lambda x: (x.get("published") or "", x.get("source") or ""), reverse=True)
    cutoff = (datetime.now(TZ_CN) - timedelta(days=MAX_AGE_DAYS)).strftime("%Y-%m-%d")
    pool = [p for p in pool if (p.get("published") or "9999") >= cutoff][:MAX_KEEP]
    return pool, added


def write_feed(pool, meta):
    top = pool[:60]
    esc = lambda s: html.escape(s or "", quote=True)  # noqa: E731
    buf = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">',
           "<channel>",
           "<title>%s</title>" % esc(SITE_NAME),
           "<link>%s</link>" % esc(meta.get("siteUrl", "")),
           "<description>%s</description>" % esc(SITE_DESC),
           "<language>zh-CN</language>",
           "<lastBuildDate>%s</lastBuildDate>" % datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000"),
           '<atom:link href="%s" rel="self" type="application/rss+xml"/>' % esc(meta.get("feedUrl", ""))]
    for it in top:
        buf.append("<item>")
        buf.append("<title>%s</title>" % esc(it.get("title")))
        buf.append("<link>%s</link>" % esc(it.get("url")))
        buf.append("<guid isPermaLink=\"false\">%s</guid>" % esc(it.get("id")))
        buf.append("<source url=\"%s\">%s</source>" % (esc(it.get("sourceUrl")), esc(it.get("source"))))
        buf.append("<category>%s</category>" % esc(it.get("tier")))
        dt = parse_dt(it.get("published"))
        if dt:
            buf.append("<pubDate>%s</pubDate>" % dt.astimezone(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000"))
        desc = "%s ｜ 来源：%s" % (it.get("summary") or "", it.get("source") or "")
        buf.append("<description>%s</description>" % esc(desc))
        buf.append("</item>")
    buf += ["</channel>", "</rss>", ""]
    with open(FEED_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(buf))


def save(store, pool, meta, added, failed_sources):
    meta = dict(store.get("meta") or {})
    meta.update({
        "siteName": SITE_NAME,
        "topic": "Forward Deployed Engineer (FDE)",
        "updated": datetime.now(TZ_CN).strftime("%Y-%m-%d %H:%M 北京时间"),
        "nextRun": "每天 08:30 北京时间（GitHub Actions cron '30 0 * * *' UTC）",
        "generatedBy": "scripts/update.py（自动抓取，仅搬运来源原文，不做主观改写）",
        "count": len(pool),
        "lastRunAdded": len(added),
        "lastRunFailedSources": failed_sources,
        "window": meta.get("window", "过去 24 小时"),
    })
    with open(ITEMS_FILE, "w", encoding="utf-8") as f:
        json.dump({"meta": meta, "items": pool}, f, ensure_ascii=False, indent=1)
    write_feed(pool, meta)
    log("已写入 data/items.json（%d 条，新增 %d）与 data/feed.xml" % (len(pool), len(added)))


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description="FDE 每日动态抓取")
    ap.add_argument("--window", type=float, default=1.0, help="抓取窗口（天），默认 1")
    ap.add_argument("--dry-run", action="store_true", help="只抓取打印，不写文件")
    ap.add_argument("--rebuild-feed", action="store_true", help="只用现有数据重建 feed.xml")
    ap.add_argument("--site-url", default="", help="站点地址，写进 feed 与 meta")
    args = ap.parse_args()

    os.makedirs(DATA_DIR, exist_ok=True)
    store = load_items()
    meta = dict(store.get("meta") or {})
    if args.site_url:
        meta["siteUrl"] = args.site_url.rstrip("/")
    base = meta.get("siteUrl", "")
    meta["feedUrl"] = (base + "/data/feed.xml") if base else "data/feed.xml"

    if args.rebuild_feed:
        write_feed(store.get("items", []), meta)
        log("feed.xml 重建完成")
        return 0

    since = datetime.now(timezone.utc) - timedelta(days=args.window)
    log("抓取窗口：过去 %.1f 天" % args.window)

    fresh, failed = [], []
    for src in SOURCES:
        fn = FETCHERS.get(src["type"])
        if not fn:
            continue
        try:
            got = fn(src, since)
        except Exception as e:                        # noqa: BLE001
            log("源 %s 异常: %s" % (src["name"], e))
            got = []
            failed.append(src["name"])
            continue
        if not got:
            failed.append(src["name"])
        log("源 %-16s 命中 %d 条" % (src["name"], len(got)))
        fresh.extend(got)

    pool, added = merge(store, fresh)
    log("去重后新增 %d 条，累计 %d 条；失败/空源 %d 个" % (len(added), len(pool), len(failed)))

    if args.dry_run:
        for it in added[:20]:
            print("  · [%s] %s | %s %s" % (it["tier"], it["title"], it["source"], it["published"]))
        log("dry-run：未写入文件")
        return 0

    save(store, pool, meta, added, failed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
