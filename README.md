# FDE 每日行业动态（GitHub Pages 站点）

每天北京时间 **08:30** 自动抓取 Forward Deployed Engineer（前线/前沿部署工程师）的最新行业动态，纯静态、零依赖、无需构建。

## 目录结构

```
fde-daily/
├── index.html                 # 站点入口（列表、搜索、筛选、时间范围切换）
├── assets/
│   ├── style.css              # 样式（自适应深色/浅色）
│   └── app.js                 # 前端渲染（读取 data/items.json）
├── data/
│   ├── items.json             # 全部条目数据（Actions 每天自动追加）
│   └── feed.xml               # RSS 订阅文件（随 items.json 自动重建）
├── scripts/
│   └── update.py              # 抓取脚本（仅 Python 标准库，本地也能跑）
└── .github/workflows/
    └── daily.yml              # 定时工作流：每天 UTC 00:30（北京 08:30）运行
```

## 上传部署（5 分钟）

1. 在 GitHub 新建一个仓库（建议命名 `fde-daily`），不要勾选自动生成 README。
2. 在本目录打开终端，执行（把 `你的用户名` 换成你的 GitHub 用户名）：

   ```powershell
   git init
   git add .
   git commit -m "FDE daily digest site"
   git branch -M main
   git remote add origin https://github.com/你的用户名/fde-daily.git
   git push -u origin main
   ```

   也可以直接在 GitHub 网页上把本文件夹内容拖进仓库上传。
3. 仓库 **Settings → Pages** → Source 选 **Deploy from a branch** → Branch 选 `main` / `/ (root)` → Save。
4. 等 1～2 分钟，站点地址即 `https://你的用户名.github.io/fde-daily/`。
5. 到仓库 **Actions** 页签，找到 "FDE 每日行业动态更新"，点 **Run workflow** 手动触发一次，验证自动更新链路（Actions 在海外网络环境运行，Google News / HN / 各媒体 RSS 全部可达）。

> 首次推送后 Actions 需要仓库开启 workflow 权限：Settings → Actions → General → Workflow permissions 选 **Read and write permissions**（或依赖 daily.yml 里已声明的 `contents: write`，默认即可）。

## 更新机制说明

- 定时：`cron: "30 0 * * *"`（UTC）＝ 北京时间每天 08:30，Actions 跑 `scripts/update.py` 抓取过去 24 小时新条目，追加进 `data/items.json` 并自动 commit + push。网页刷新即见。
- 信息源（在 `scripts/update.py` 顶部 `SOURCES` 里增删）：
  - Hacker News Algolia API（英文社区）
  - Google News RSS：`"前沿部署工程师" OR "前线部署工程师"…`（中文）与 `"forward deployed engineer"`（英文）
  - TechCrunch / The Verge / VentureBeat 的 AI RSS，按关键词过滤
- 防编造闸门：标题+摘要必须命中 FDE 相关术语才入库；抓取只搬运来源原文，不做改写；某天没有新动态就不产出空更新。
- 去重：链接指纹 + 标题指纹双重去重；数据保留一年、最多 2000 条。
- 若连续几天 Actions 红色报错（多半是某个源改版），打开 Actions 日志看 `源 xx 失败` 字样，把对应源注释掉即可，不影响其他源。

## 本地预览

`file://` 直接双击打开会被浏览器拦截本地 JSON，请起一个静态服务：

```powershell
cd fde-daily
python -m http.server 8000
# 浏览器访问 http://localhost:8000
```

## 定制

- 改时间：编辑 `.github/workflows/daily.yml` 的 cron（UTC = 北京时间 - 8 小时）。
- 加中文源：Google News RSS 关键词加进 `update.py` 的 `SOURCES`；若有可靠 RSS 直接用 `type: "rss"`。
- 换主题色：`assets/style.css` 顶部 CSS 变量。
