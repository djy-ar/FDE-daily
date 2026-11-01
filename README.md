# FDE 每日行业动态

聚合 Forward Deployed Engineer（FDE，前线／前沿部署工程师）相关的中英文行业动态。网站以 GitHub Pages 发布，由 GitHub Actions 定时抓取公开信息源，并生成 JSON 数据和 RSS 订阅。

**在线阅读：**[FDE 每日行业动态](https://sghpedc5279.github.io/FDE-daily/) · **RSS 订阅：**[data/feed.xml](https://sghpedc5279.github.io/FDE-daily/data/feed.xml)

## 网站功能

- 按今日、近 7 天、近 30 天或全部时间筛选动态。
- 搜索标题、摘要、来源和标签，并按分类筛选；可选择只看中文条目。
- 查看来源链接、发布日期、摘要及 Hacker News 讨论信息（如有）。
- 订阅 RSS，或直接查看仓库中的 [`data/items.json`](data/items.json)。

## 收录内容与来源

目前抓取来源配置在 [`scripts/update.py`](scripts/update.py) 的 `SOURCES` 中：

- **Hacker News Algolia API**：搜索 FDE 相关讨论。
- **Google News RSS**：分别检索中文和英文关键词。
- **科技媒体 RSS**：TechCrunch、The Verge AI、VentureBeat 的 AI 栏目。

采集结果还要通过术语过滤：标题、摘要或标签中必须出现 FDE 相关表述（例如 “forward deployed engineer”、独立词 “FDE” 或中文相关术语）才会收录。程序保留来源标题和摘要，不自行改写；按链接和标题去重，最多保留 2,000 条且不超过一年，RSS 输出最新的 60 条。分类规则也在 `scripts/update.py` 中维护。

## 更新方式

工作流配置见 [`.github/workflows/daily.yml`](.github/workflows/daily.yml)：

- 每天 **北京时间 08:30**（UTC 00:30）运行。
- 可在仓库的 **Actions → FDE 每日动态更新 → Run workflow** 手动运行，并设置抓取窗口 `window`（天数，默认 1）。
- 修改 `scripts/update.py` 或工作流文件并推送到 `main` 时，也会触发一次运行。
- 工作流使用 Python 3.11 和仓库内置的 Python 标准库，无需安装第三方依赖；运行后更新 `data/items.json` 和 `data/feed.xml`。

每次运行都会刷新数据元信息和 RSS 生成时间，即使没有新增条目也可能产生数据文件提交。某个来源没有产出匹配条目时，工作流不一定报错；可在 `data/items.json` 的 `meta.lastRunFailedSources` 查看本次无结果或失败的来源，再到 Actions 日志区分是暂无匹配内容还是抓取异常。

## 本地预览与调试

需要 Python 3；项目没有额外依赖。先在仓库根目录启动静态服务器：

```bash
python -m http.server 8000
```

浏览器打开 <http://localhost:8000>。直接以 `file://` 打开 `index.html` 通常无法加载 JSON 数据。

可在本地手动运行抓取脚本（需要能够访问配置中的公开信息源）：

```bash
# 只抓取并显示结果，不写入文件
python scripts/update.py --dry-run

# 抓取最近 7 天
python scripts/update.py --window 7

# 根据现有 items.json 重新生成 RSS
python scripts/update.py --rebuild-feed
```

## 仓库结构

```text
.
├── index.html                    # 页面结构与筛选控件
├── assets/
│   ├── app.js                    # 加载、筛选和渲染条目
│   └── style.css                 # 页面样式与响应式布局
├── data/
│   ├── items.json                # 条目及更新元信息
│   └── feed.xml                  # RSS 订阅文件
├── scripts/
│   └── update.py                # 信息源抓取、过滤、去重和数据生成
└── .github/workflows/
    └── daily.yml                 # 定时及手动更新工作流
```

## 部署到自己的仓库

1. Fork 本仓库，并在仓库 **Settings → Pages** 中将 Source 设为 `Deploy from a branch`，选择 `main` 和 `/(root)`。
2. 在 **Settings → Actions → General → Workflow permissions** 中允许工作流写入仓库内容，以便自动提交更新后的数据文件。
3. 等待 Pages 发布完成；站点地址通常是 `https://<用户名>.github.io/<仓库名>/`。工作流会根据仓库名称设置站点 URL。

## 定制

- **调整运行时间：**修改 `.github/workflows/daily.yml` 中的 cron（按 UTC 设置；北京时间 = UTC + 8 小时）。
- **增删信息源或搜索词：**修改 `scripts/update.py` 中的 `SOURCES`；支持 `hn`、`gnews` 和 `rss` 类型。
- **调整过滤或分类：**修改 `TERMS` 和 `TIER_RULES`，并检查前端 `assets/app.js` 中的术语过滤规则。
- **调整样式：**修改 `assets/style.css`。
