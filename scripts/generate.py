#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
个人博客静态站点生成器（零第三方依赖，仅用 Python 标准库）。

用法：
    python scripts/generate.py          # 仅根据 posts/ 下的 Markdown 重建站点
    python scripts/generate.py --auto   # 先生成一篇"每日更新"文章，再重建站点

输出（写入仓库根目录，配合 .nojekyll，GitHub Pages 直接托管）：
    index.html          博客主页（文章列表）
    posts/<slug>.html   单篇文章页
    feed.xml            RSS 订阅源
    posts.json          文章元数据
    404.html            404 页面

定时执行：.github/workflows/daily-update.yml（GitHub Actions 每天北京时间 06:00 左右触发）。
"""

import argparse
import datetime
import html
import json
import os
import random
import re
import sys
import urllib.request
from pathlib import Path

# ---------- 站点配置（改成你自己的） ----------
SITE_NAME = "伦辛小站"                                  # 博客名称
SITE_DESC = "记录生活、学习与折腾，偶尔更新一点点。"   # 博客简介
AUTHOR = "lencin"                                         # 页脚作者名
SITE_URL = "https://luomomo257-beep.github.io/blog/"      # 部署后改成真实地址（影响 RSS 链接）
TZ_OFFSET = 8          # 每日文章的日期按北京时间（UTC+8）计算
DAILY_TZ = datetime.timezone(datetime.timedelta(hours=TZ_OFFSET))
# ------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
POSTS_SRC = ROOT / "posts"          # Markdown 文章源
POSTS_OUT = ROOT / "posts"          # 生成的 HTML 文章（与源文件同目录）
ASSETS = ROOT / "assets"

SYS_PATH = os.path.dirname(os.path.abspath(__file__))
if SYS_PATH not in sys.path:
    sys.path.insert(0, SYS_PATH)
import daily_pool  # noqa: E402


# ================= Markdown（常用子集） =================

def _escape(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;").replace('"', "&quot;"))


def _inline(text: str) -> str:
    """行内格式：行内代码、图片、链接、加粗、斜体、删除线。"""
    tokens = []

    def _code_repl(m):
        tokens.append("<code>" + _escape(m.group(1)) + "</code>")
        return "\x00%d\x00" % (len(tokens) - 1)

    text = re.sub(r"`([^`\n]+)`", _code_repl, text)

    def _img_repl(m):
        return '<img src="%s" alt="%s" loading="lazy">' % (
            _escape(m.group(2)), _escape(m.group(1)))

    text = re.sub(r"!\[([^\]]*)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)", _img_repl, text)

    def _link_repl(m):
        return '<a href="%s">%s</a>' % (_escape(m.group(2)), _inline(m.group(1)))

    text = re.sub(r"\[([^\]]+)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)", _link_repl, text)
    text = re.sub(r"\*\*([^*\n]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<em>\1</em>", text)
    text = re.sub(r"~~([^~\n]+)~~", r"<del>\1</del>", text)
    return re.sub(r"\x00(\d+)\x00", lambda m: tokens[int(m.group(1))], text)


def _parse_list(lines, i):
    """支持两级嵌套的有序/无序列表，返回 (html, 下一个索引)。"""
    out = []
    stack = []  # [(tag, indent)]
    root_indent = None
    while i < len(lines):
        line = lines[i]
        stripped = line.lstrip()
        if not stripped:
            i += 1
            continue
        m = re.match(r"^([-*+]|\d+[.)])\s+(.*)$", stripped)
        if not m:
            break
        indent = len(line) - len(stripped)
        if root_indent is None:
            root_indent = indent
        elif indent < root_indent:
            break
        marker, content = m.group(1), m.group(2)
        tag = "ul" if marker in "-*+" else "ol"
        while stack and stack[-1][1] > indent:
            out.append("</%s>" % stack.pop()[0])
        if not stack or stack[-1][1] < indent:
            out.append("<%s>" % tag)
            stack.append((tag, indent))
        elif stack[-1][1] == indent and stack[-1][0] != tag:
            out.append("</%s>" % stack.pop()[0])
            out.append("<%s>" % tag)
            stack.append((tag, indent))
        out.append("<li>%s</li>" % _inline(content))
        i += 1
    while stack:
        out.append("</%s>" % stack.pop()[0])
    return "\n".join(out), i


def _parse_table(lines, i):
    header = [c.strip() for c in lines[i].strip().strip("|").split("|")]
    i += 2  # 跳过表头分隔行
    rows = []
    while i < len(lines) and lines[i].strip() and "|" in lines[i]:
        rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
        i += 1
    out = ["<table><thead><tr>"]
    for h in header:
        out.append("<th>%s</th>" % _inline(h))
    out.append("</tr></thead><tbody>")
    for row in rows:
        out.append("<tr>")
        for c in row:
            out.append("<td>%s</td>" % _inline(c))
        out.append("</tr>")
    out.append("</tbody></table>")
    return "\n".join(out), i


def markdown_to_html(text: str) -> str:
    lines = text.replace("\r\n", "\n").split("\n")
    out = []
    i, n = 0, len(lines)
    while i < n:
        line = lines[i]

        m = re.match(r"^\s*```(\w*)\s*$", line)
        if m:
            lang, buf = m.group(1), []
            i += 1
            while i < n and not re.match(r"^\s*```\s*$", lines[i]):
                buf.append(lines[i])
                i += 1
            i += 1  # 跳过结尾 ``` 行
            cls = ' class="language-%s"' % lang if lang else ""
            out.append("<pre><code%s>%s</code></pre>" % (cls, html.escape("\n".join(buf))))
            continue

        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            level = len(m.group(1))
            out.append("<h%d>%s</h%d>" % (level, _inline(m.group(2)), level))
            i += 1
            continue

        if re.match(r"^\s*(-{3,}|\*{3,}|_{3,})\s*$", line):
            out.append("<hr>")
            i += 1
            continue

        if line.lstrip().startswith(">"):
            buf = []
            while i < n and lines[i].lstrip().startswith(">"):
                buf.append(lines[i].lstrip()[1:].lstrip())
                i += 1
            out.append("<blockquote>%s</blockquote>" % _inline("\n".join(buf)))
            continue

        if re.match(r"^\s*[-*+]\s+", line) or re.match(r"^\s*\d+[.)]\s+", line):
            block, i = _parse_list(lines, i)
            out.append(block)
            continue

        if "|" in line and i + 1 < n and re.match(r"^\s*\|?[\s:|-]+\|?\s*$", lines[i + 1]):
            block, i = _parse_table(lines, i)
            out.append(block)
            continue

        # 普通段落
        if not line.strip():
            i += 1
            continue
        buf = [line.strip()]
        i += 1
        while (i < n and lines[i].strip()
               and not re.match(r"^\s*(#{1,6}\s+|```|[-*+]\s+|\d+[.)]\s+|[>|])", lines[i])
               and not re.match(r"^\s*(-{3,}|\*{3,}|_{3,})\s*$", lines[i])):
            buf.append(lines[i].strip())
            i += 1
        out.append("<p>%s</p>" % _inline(" ".join(buf)))
    return "\n".join(out)


# ================= 文章解析 =================

DEFAULT_CATEGORY = "随笔"

FRONT_MATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def parse_front_matter(text: str):
    """解析文章开头的可选 front matter（--- 包裹的键值行），目前只读取类型。

    支持中英文键：类型 / 分类 / type / category。
    """
    meta = {}
    m = FRONT_MATTER_RE.match(text)
    if m:
        for line in m.group(1).splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            kv = re.split(r"[:：]", line, maxsplit=1)
            if len(kv) == 2 and kv[0].strip().lower() in ("类型", "分类", "type", "category"):
                meta["category"] = kv[1].strip()
    body = text[m.end():] if m else text
    return meta, body


def parse_post(path: Path):
    """解析一篇 Markdown 文章，文件名格式：YYYY-MM-DD-标题.md"""
    text = path.read_text(encoding="utf-8")
    meta, body = parse_front_matter(text)
    name = path.name
    m = re.match(r"^(\d{4}-\d{2}-\d{2})-(.+)\.md$", name)
    if not m:
        print("[警告] 跳过不符合命名规范的文章（应为 YYYY-MM-DD-标题.md）：%s" % name)
        return None
    date, slug = m.group(1), m.group(2)
    # 类型：front matter 优先；每日文章自动归入"每日更新"；其余默认"随笔"
    category = meta.get("category")
    if not category:
        if slug.endswith("-daily") or body.lstrip().startswith("# 每日更新"):
            category = "每日更新"
        else:
            category = DEFAULT_CATEGORY
    # 标题：取正文第一个 # 标题，否则用文件名中的标题部分
    title_m = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
    title = title_m.group(1).strip() if title_m else slug
    # 摘要：正文里第一个非空、非标题的段落
    excerpt = ""
    for para in re.split(r"\n\s*\n", body):
        p = para.strip()
        if not p or p.startswith("#"):
            continue
        excerpt = re.sub(r"[`*_#>\[\]()!~]", "", p)
        break
    excerpt = re.sub(r"\s+", " ", excerpt).strip()
    if len(excerpt) > 140:
        excerpt = excerpt[:140].rstrip() + "…"
    return {
        "slug": slug,
        "title": title,
        "date": date,
        "excerpt": excerpt,
        "category": category,
        "source": path,
    }


# ================= 页面渲染 =================

def render_page(title, body, *, with_header=True):
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<meta name="description" content="{SITE_DESC}">
<link rel="stylesheet" href="../assets/css/style.css">
<link rel="alternate" type="application/rss+xml" title="{SITE_NAME}" href="../feed.xml">
</head>
<body>
<header class="site-header">
  <div class="wrap">
    <a class="brand" href="../index.html">{SITE_NAME}</a>
    <nav>
      <a href="../index.html">首页</a>
      <a href="../feed.xml">RSS</a>
    </nav>
  </div>
</header>
<main class="wrap">
{body}
</main>
<footer class="site-footer">
  <div class="wrap"><p>© {datetime.date.today().year} {AUTHOR} · 本站由 GitHub Actions 每日自动更新</p></div>
</footer>
</body>
</html>"""


def render_root_page(title, body):
    """渲染位于仓库根目录的页面（index.html / 404.html），资源路径用相对根目录。"""
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<meta name="description" content="{SITE_DESC}">
<link rel="stylesheet" href="assets/css/style.css">
<link rel="alternate" type="application/rss+xml" title="{SITE_NAME}" href="feed.xml">
</head>
<body>
<header class="site-header">
  <div class="wrap">
    <a class="brand" href="index.html">{SITE_NAME}</a>
    <nav>
      <a href="index.html">首页</a>
      <a href="feed.xml">RSS</a>
    </nav>
  </div>
</header>
<main class="wrap">
{body}
</main>
<footer class="site-footer">
  <div class="wrap"><p>© {datetime.date.today().year} {AUTHOR} · 本站由 GitHub Actions 每日自动更新</p></div>
</footer>
</body>
</html>"""


FILTER_JS = """<script>
(function () {
  try {
    var tabs = document.querySelectorAll('.filter-tab');
    var cards = document.querySelectorAll('.post-card');
    var empty = document.getElementById('filter-empty');
    if (!tabs.length || !cards.length) return;
    function apply(type) {
      var visible = 0;
      for (var i = 0; i < cards.length; i++) {
        var show = (type === 'all' || cards[i].getAttribute('data-type') === type);
        cards[i].style.display = show ? '' : 'none';
        if (show) visible++;
      }
      for (var j = 0; j < tabs.length; j++) {
        tabs[j].className = tabs[j].getAttribute('data-type') === type
          ? 'filter-tab active' : 'filter-tab';
      }
      if (empty) empty.style.display = visible ? 'none' : 'block';
    }
    for (var k = 0; k < tabs.length; k++) {
      tabs[k].addEventListener('click', (function (t) {
        return function () { apply(t.getAttribute('data-type')); };
      })(tabs[k]));
    }
    apply('all');
  } catch (e) { /* 筛选脚本异常时默认展示全部文章 */ }
})();
</script>"""


def build_site(posts):
    posts = sorted(posts, key=lambda p: p["date"], reverse=True)

    # ---- 类型统计与筛选标签 ----
    counts = {}
    for p in posts:
        counts[p["category"]] = counts.get(p["category"], 0) + 1
    category_order = sorted(counts.keys(), key=lambda c: (-counts[c], c))
    tabs = ['<button class="filter-tab active" data-type="all">全部 <span class="count">%d</span></button>' % len(posts)]
    for c in category_order:
        tabs.append('<button class="filter-tab" data-type="%s">%s <span class="count">%d</span></button>'
                    % (html.escape(c), html.escape(c), counts[c]))
    tabs_html = "\n  ".join(tabs)

    # ---- 文章列表 HTML（整卡可点击，data-type 供筛选） ----
    cards = []
    for p in posts:
        cards.append(f"""<a class="post-card" href="posts/{p['slug']}.html" data-type="{html.escape(p['category'])}">
  <div class="post-meta"><time datetime="{p['date']}">{p['date']}</time><span class="badge">{html.escape(p['category'])}</span></div>
  <h3>{html.escape(p['title'])}</h3>
  <p class="post-excerpt">{html.escape(p['excerpt'])}</p>
</a>""")
    list_html = "\n".join(cards) if cards else '<p class="empty">还没有文章，去 <code>posts/</code> 目录添加第一篇吧。</p>'

    index_body = f"""<section class="hero">
  <h1>{SITE_NAME}</h1>
  <p>{SITE_DESC}</p>
</section>
<section class="posts">
  <h2 class="section-title">全部文章 <span class="count">({len(posts)})</span></h2>
  <div class="filter-tabs" role="tablist">
  {tabs_html}
  </div>
  <p class="empty" id="filter-empty" style="display:none">该类型下暂无文章。</p>
  {list_html}
</section>"""
    (ROOT / "index.html").write_text(render_root_page(
        f"{SITE_NAME} · {SITE_DESC}", index_body).replace("</main>", FILTER_JS + "\n</main>"), encoding="utf-8")

    # ---- 单篇文章页 ----
    for p in posts:
        src = p["source"].read_text(encoding="utf-8")
        src = re.sub(r"^#\s+.*$", "", src, count=1, flags=re.MULTILINE)  # 去掉正文首个标题（页头已显示）
        content = markdown_to_html(src)
        body = f"""<article class="post">
  <header>
    <h1>{html.escape(p['title'])}</h1>
    <div class="post-meta"><time datetime="{p['date']}">{p['date']}</time> · {AUTHOR} · <span class="badge">{html.escape(p['category'])}</span></div>
  </header>
  <div class="post-content">
{content}
  </div>
  <nav class="post-nav"><a href="../index.html">← 返回首页</a></nav>
</article>"""
        (POSTS_OUT / f"{p['slug']}.html").write_text(render_page(p["title"], body), encoding="utf-8")

    # ---- RSS ----
    items = []
    for p in posts:
        link = SITE_URL.rstrip("/") + "/posts/" + p["slug"] + ".html"
        pub = datetime.datetime.strptime(p["date"], "%Y-%m-%d").strftime("%a, %d %b %Y 00:00:00 +0800")
        items.append(f"""<item>
  <title>{html.escape(p['title'])}</title>
  <link>{link}</link>
  <guid>{link}</guid>
  <pubDate>{pub}</pubDate>
  <description>{html.escape(p['excerpt'])}</description>
</item>""")
    rss = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
  <title>{SITE_NAME}</title>
  <link>{SITE_URL}</link>
  <description>{SITE_DESC}</description>
  <language>zh-CN</language>
  {chr(10).join(items)}
</channel>
</rss>
"""
    (ROOT / "feed.xml").write_text(rss, encoding="utf-8")

    # ---- posts.json（元数据） ----
    meta = [{"slug": p["slug"], "title": p["title"], "date": p["date"],
             "excerpt": p["excerpt"], "category": p["category"]} for p in posts]
    (ROOT / "posts.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    # ---- 404 ----
    body_404 = """<section class="hero">
  <h1>404</h1>
  <p>页面不存在或已被移动。</p>
  <p><a href="index.html">← 回到首页</a></p>
</section>"""
    (ROOT / "404.html").write_text(render_root_page("404", body_404), encoding="utf-8")

    print("站点构建完成：%d 篇文章 → index.html / posts/*.html / feed.xml / posts.json / 404.html" % len(posts))


# ================= 每日自动文章 =================

def _fetch_quote():
    """从一言 API 抓取每日一言，失败时回退到本地素材池。"""
    try:
        req = urllib.request.Request("https://v1.hitokoto.cn/", headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        text = (data.get("hitokoto") or "").strip()
        source = (data.get("from") or "").strip()
        if text:
            return text, source or "网络"
    except Exception as e:  # noqa: BLE001
        print("[提示] 一言 API 获取失败（%s），使用本地备用一言。" % e)
    text, source = random.choice(daily_pool.FALLBACK_QUOTES)
    return text, source


def generate_daily_post(now: datetime.datetime) -> bool:
    """生成一篇"每日更新"文章；当天已存在则跳过。返回是否新建。"""
    slug = "%s-daily" % now.strftime("%Y-%m-%d")
    target = POSTS_SRC / (slug + ".md")
    if target.exists():
        print("[提示] %s 已存在，跳过自动生成。" % target.name)
        return False

    quote, source = _fetch_quote()
    tip = random.choice(daily_pool.COLD_TIPS)
    coding = random.choice(daily_pool.CODING_TIPS)

    title = "每日更新 · %s" % now.strftime("%m月%d日")
    content = f"""---
类型: 每日更新
---
# {title}

> 本文由 GitHub Actions 定时任务自动生成，每天北京时间 06:00 左右更新。

## 今日一言

> “{quote}”
>
> —— {source}

## 生活冷知识

{tip}

## 编程小贴士

{coding}

---

*本页由 [scripts/generate.py](scripts/generate.py) 自动生成，停用或修改请见 [README.md](README.md)。*
"""
    target.write_text(content, encoding="utf-8")
    print("[新建] %s" % target.name)
    return True


# ================= 入口 =================

def main():
    parser = argparse.ArgumentParser(description="个人博客静态站点生成器")
    parser.add_argument("--auto", action="store_true", help="先自动生成每日文章，再重建站点")
    args = parser.parse_args()

    if args.auto:
        now = datetime.datetime.now(DAILY_TZ)
        generate_daily_post(now)

    posts = []
    for md in sorted(POSTS_SRC.glob("*.md")):
        post = parse_post(md)
        if post:
            posts.append(post)
    if not posts:
        print("[错误] posts/ 目录下没有符合命名规范（YYYY-MM-DD-标题.md）的文章。")
        sys.exit(1)
    build_site(posts)


if __name__ == "__main__":
    main()
