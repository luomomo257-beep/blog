# 我的小站・定时更新的个人博客

一个零依赖、免费的个人博客：**GitHub Pages 托管 + GitHub Actions 每天自动更新内容**。

- 每天北京时间 06:00 左右，自动生成一篇「每日更新」文章（一言 + 生活冷知识 + 编程小贴士）

- 手动文章随时发布：往 `posts/` 丢一个 Markdown 文件即可

- 首页按类型筛选文章，列表整卡可点击跳转详情页

- 自带 RSS 订阅（`feed.xml`）、404 页面、响应式样式

- 构建脚本只用 Python 标准库，GitHub Actions 免费额度内运行，无任何第三方依赖

## 目录结构

```
.

├── index.html              # 博客主页

├── 404.html                # 404 页面

├── feed.xml                # RSS 订阅源

├── posts.json              # 文章元数据

├── posts/                  # 文章目录：YYYY-MM-DD-标题.md + \*.html

├── assets/css/style.css    # 主题样式

├── scripts/

│   ├── generate.py         # 站点生成器 + 每日文章生成

│   └── daily\_pool.py       # 每日文章的素材池（冷知识 / 编程贴士 / 备用一言）

└── .github/workflows/

&#x20;   └── daily-update.yml    # 每日定时任务
```

## 一分钟部署

1. **建仓库**：在 GitHub 新建一个仓库（示例 `my-blog`）。如果希望博客地址是

   `https://<你的用户名>.github.io/`，仓库名必须叫 `<你的用户名>.github.io`。

2. **推送**：把本目录所有文件推送到仓库 main 分支。

3. **开启 Pages**：仓库 Settings → Pages → Source 选

   **Deploy from a branch** → 分支选 `main`、目录选 `/ (root)` → Save。

   约 1 分钟后，`https://<你的用户名>.github.io/<仓库名>/`（或 `用户名.github.io`）即可访问。

4. **开启定时任务**：仓库 Actions 页面如果提示要启用，点一下启用即可。

   定时任务每天 UTC 22:00（北京时间 06:00）自动运行；也可在

   Actions → 每日自动更新 → Run workflow 手动触发测试。

## 常用操作

| 想做什么                 | 怎么做                                                                                                                           |
| ------------------------ | -------------------------------------------------------------------------------------------------------------------------------- |
| 改博客名称 / 简介 / 作者 | 编辑 `scripts/generate.py` 顶部的 `SITE_NAME` / `SITE_DESC` / `AUTHOR`                                                           |
| 改部署地址（影响 RSS）   | 编辑 `scripts/generate.py` 里的 `SITE_URL`                                                                                       |
| 发布新文章               | 在 `posts/` 新建 `YYYY-MM-DD-标题.md`，推送到 main                                                                               |
| 给文章设置类型           | 文章开头加 front matter：`---` 块内写 `类型: 生活`（支持 类型/分类/type/category，不写默认「随笔」，每日文章自动归「每日更新」） |
| 改自动更新时间           | 编辑 `.github/workflows/daily-update.yml` 里的 cron（UTC，北京时间 = UTC+8）                                                     |
| 调整每日内容             | 编辑 `scripts/daily_pool.py` 的素材池；改自动生成逻辑看 `generate.py` 的 `generate_daily_post`                                   |
| 停用每日更新             | 删除 `.github/workflows/daily-update.yml` 即可，博客照常手动发布                                                                 |
| 本地预览                 | `python scripts/generate.py` 后在浏览器打开 `index.html`                                                                         |

## 本地构建

```
\# 只重建站点（posts/ 里的文章 → HTML）

python scripts/generate.py

\# 先生成一篇"每日更新"文章，再重建站点（和定时任务完全一致）

python scripts/generate.py --auto
```

## 文章类型（front matter）

在 Markdown 文件最开头用 `---` 包裹元信息，可指定类型：

```
---
类型: 生活
---
# 标题
```

- 支持键名：`类型` / `分类` / `type` / `category`

- 不写类型时默认归入「随笔」；每日自动文章固定归入「每日更新」

- 首页顶部会按类型生成筛选标签，点击即可过滤文章列表

## 注意事项

- 文章文件名必须形如 `2026-09-17-标题.md`，否则会被跳过并告警。

- 定时任务默认每天只生成一篇；同一天重复运行不会重复生成。

- 每日一言来自免费 API（[v1.hitokoto.cn](https://v1.hitokoto.cn)），接口不可用时会自动回退到本地素材池。
