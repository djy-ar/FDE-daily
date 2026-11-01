/* FDE 每日行业动态 —— 纯前端渲染，数据来自 data/items.json（由 GitHub Actions 每日追加） */
(function () {
  "use strict";

  var DATA = "data/items.json";
  var FEED = "data/feed.xml";
  var DAY = 864e5;

  var elList = document.getElementById("list");
  var elStatus = document.getElementById("status");
  var elEmpty = document.getElementById("empty");
  var elCount = document.getElementById("countLine");
  var elTabs = document.querySelectorAll(".tab");
  var elQ = document.getElementById("q");
  var elTier = document.getElementById("tier");
  var elCn = document.getElementById("cnOnly");
  var rowTpl = document.getElementById("row");
  var footMeta = document.getElementById("footMeta");

  var state = { range: "7d", q: "", tier: "", cn: false };
  var all = [];
  var meta = {};

  /* ---------- 术语闸门：只保留真正与 FDE 相关的条目 ---------- */
  var TERMS = [
    "forward deployed engineer", "forward-deployed engineer", "forward deployment engineer",
    "forward deployed", "fde", "fdde",
    "前沿部署工程师", "前线部署工程师", "前置部署工程师", "前沿驻场工程师"
  ];
  function isFde(item) {
    var hay = (item.title + " " + (item.summary || "") + " " + (item.tags || []).join(" ")).toLowerCase();
    for (var i = 0; i < TERMS.length; i++) {
      var t = TERMS[i];
      if (t === "fde") {
        // 避免把 "fde" 当成别的词的子串（如 "features"），要求独立出现
        if (new RegExp("(^|[^a-z])fde([^a-z]|$)").test(hay)) return true;
      } else if (hay.indexOf(t) >= 0) return true;
    }
    return false;
  }

  /* ---------- 加载 ---------- */
  function load() {
    var url = DATA + "?t=" + Date.now();
    fetch(url, { cache: "no-store" })
      .then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      })
      .then(function (d) {
        meta = d.meta || {};
        all = (d.items || []).filter(isFde);
        elStatus.className = "status done";
        renderStatus();
        fillTiers();
        render();
      })
      .catch(function (err) {
        elStatus.className = "status warn";
        elStatus.innerHTML = "";
        var p = document.createElement("p");
        p.innerHTML = "<b>数据没加载出来。</b>" +
          "<br>如果你是用浏览器直接双击打开 index.html（地址栏以 file:// 开头），浏览器会出于安全限制拒绝读取本地 JSON。" +
          "两种解决办法：① 部署到 GitHub Pages 后从网址访问（推荐）；② 本地预览请在此目录运行 <code>python -m http.server 8000</code>，再访问 http://localhost:8000 。" +
          '<br><span class="fail">' + esc(String(err.message || err)) + "</span>";
        elStatus.appendChild(p);
      });
  }

  function renderStatus() {
    var n = all.length;
    var upd = meta.updated || "—";
    var oldest = all.length ? all[all.length - 1].published : "—";
    elStatus.innerHTML =
      "共 <b>" + n + "</b> 条已收录 · 最近自动更新 <b>" + esc(upd) + "</b>" +
      (meta.nextRun ? " · 下次更新 " + esc(meta.nextRun) : "") +
      (meta.generatedBy ? '<br><span>更新方式：' + esc(meta.generatedBy) + "</span>" : "") +
      '<br><span>收录范围：' + esc(String(oldest)) + " 起</span>";
    if (footMeta) {
      footMeta.textContent = "数据文件：" + DATA + "（" + n + " 条） · 最近更新 " + upd;
    }
  }

  function fillTiers() {
    var seen = {};
    all.forEach(function (it) { if (it.tier) seen[it.tier] = 1; });
    Object.keys(seen).sort().forEach(function (t) {
      var o = document.createElement("option");
      o.value = t; o.textContent = t;
      elTier.appendChild(o);
    });
  }

  /* ---------- 筛选 ---------- */
  function inRange(item) {
    var days = { today: 1.2, "7d": 7, "30d": 30, all: 1e6 }[state.range];
    if (state.range === "all") return true;
    var t = Date.parse(item.published);
    if (isNaN(t)) return false;
    return (Date.now() - t) <= days * DAY;
  }

  function match(item) {
    if (!inRange(item)) return false;
    if (state.tier && item.tier !== state.tier) return false;
    if (state.cn && item.lang !== "zh") return false;
    if (state.q) {
      var hay = (item.title + " " + (item.summary || "") + " " + (item.source || "") + " " + (item.tags || []).join(" ")).toLowerCase();
      if (hay.indexOf(state.q) < 0) return false;
    }
    return true;
  }

  /* ---------- 渲染 ---------- */
  function render() {
    var rows = all.filter(match);
    elList.innerHTML = "";
    elEmpty.hidden = rows.length > 0;
    elCount.textContent = "显示 " + rows.length + " 条" +
      ({ today: "（今日）", "7d": "（近 7 天）", "30d": "（近 30 天）", all: "（全部）" })[state.range] +
      (state.q ? ' · 关键词 "' + state.q + '"' : "");

    rows.slice(0, 200).forEach(function (it) { elList.appendChild(node(it)); });
    if (rows.length > 200) {
      var more = document.createElement("p");
      more.className = "count-line";
      more.textContent = "另有 " + (rows.length - 200) + " 条未展开，缩小时间范围或加关键词可快速定位。";
      elList.appendChild(more);
    }
  }

  function node(item) {
    var n = rowTpl.content.cloneNode(true);
    var art = n.querySelector(".item");

    var src = n.querySelector(".src");
    if (item.sourceUrl) {
      var a = document.createElement("a");
      a.href = item.sourceUrl; a.target = "_blank"; a.rel = "noopener";
      a.textContent = item.source || "来源";
      src.appendChild(a);
    } else {
      src.textContent = item.source || "来源";
    }

    var tier = n.querySelector(".tier");
    if (item.tier) { tier.textContent = item.tier; tier.className = "tier t-" + item.tier; }
    else { tier.remove(); }

    var dt = n.querySelector(".date");
    dt.textContent = item.published || "";
    dt.setAttribute("datetime", item.published || "");

    var lang = n.querySelector(".lang");
    lang.textContent = item.lang === "zh" ? "中文源" : "英文源";

    var ta = n.querySelector(".title a");
    ta.href = item.url || "#";
    ta.innerHTML = highlight(item.title || "(无标题)", state.q);

    var sum = n.querySelector(".sum");
    if (item.summary) { sum.innerHTML = highlight(item.summary, state.q); }
    else { sum.remove(); }

    var tags = n.querySelector(".tags");
    (item.tags || []).slice(0, 4).forEach(function (t) {
      var s = document.createElement("span"); s.className = "tag"; s.textContent = t;
      tags.appendChild(s);
    });

    var hn = n.querySelector(".hn");
    if (item.hn && item.hn.id) {
      var h = document.createElement("a");
      h.href = "https://news.ycombinator.com/item?id=" + item.hn.id;
      h.target = "_blank"; h.rel = "noopener";
      h.textContent = "HN 讨论 " + (item.hn.points != null ? item.hn.points + " 分 / " : "") + (item.hn.comments || 0) + " 条";
      hn.appendChild(h);
    } else { hn.remove(); }

    var copy = n.querySelector(".copy");
    copy.addEventListener("click", function () {
      var link = item.url || location.href;
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(link).then(function () {
          copy.textContent = "已复制"; copy.classList.add("ok");
          setTimeout(function () { copy.textContent = "复制链接"; copy.classList.remove("ok"); }, 1600);
        });
      } else {
        window.prompt("手动复制链接：", link);
      }
    });

    return n;
  }

  function esc(s) {
    return String(s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  function highlight(text, q) {
    var safe = esc(text);
    if (!q) return safe;
    try {
      var re = new RegExp(q.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "gi");
      return safe.replace(re, function (m) { return "<mark>" + m + "</mark>"; });
    } catch (e) { return safe; }
  }

  /* ---------- 事件 ---------- */
  Array.prototype.forEach.call(elTabs, function (b) {
    b.addEventListener("click", function () {
      Array.prototype.forEach.call(elTabs, function (x) { x.classList.remove("is-on"); });
      b.classList.add("is-on");
      state.range = b.getAttribute("data-range");
      render();
    });
  });
  elQ.addEventListener("input", function () { state.q = elQ.value.trim().toLowerCase(); render(); });
  elTier.addEventListener("change", function () { state.tier = elTier.value; render(); });
  elCn.addEventListener("change", function () { state.cn = elCn.checked; render(); });

  document.getElementById("rssBtn").addEventListener("click", function () {
    window.open(FEED, "_blank");
  });

  load();
})();
