"""Deterministic SEO audit for a static HTML website.

Usage:
    python3 check_site.py --root /workspace/site --site https://www.example.co.uk [options]

Options:
    --noindex /thank-you,/404   paths that are meant to be noindex (not flagged)
    --no-dashes                 flag em dashes, en dashes and hyphenated words in visible copy
    --allow-dash a-b,c-d        words allowed to keep a hyphen when --no-dashes is on
    --url-style clean|html      how page URLs look (default: clean if vercel.json sets cleanUrls)
    --json                      machine readable output

Exit code 1 if any ERROR is found. Standard library only.
"""
import argparse
import json
import pathlib
import re
import sys
import xml.etree.ElementTree as ET
from html.parser import HTMLParser

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
SKIP_TEXT = {"script", "style", "noscript", "svg", "code", "pre", "template"}
SKIP_DIRS = {".git", "node_modules", ".vercel", ".next", ".github", "agents"}


class Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.lang = None
        self.title = ""
        self.metas = {}
        self.links = []
        self.canonical = None
        self.headings = []
        self.hrefs = []
        self.imgs = []
        self.jsonld = []
        self.text = []
        self._stack = []
        self._in_title = False
        self._script_type = None
        self._buf = []
        self._heading = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "html":
            self.lang = a.get("lang")
        elif tag == "title":
            self._in_title = True
        elif tag == "meta":
            key = a.get("name") or a.get("property")
            if key:
                self.metas[key.lower()] = a.get("content", "")
        elif tag == "link":
            if (a.get("rel") or "").lower() == "canonical":
                self.canonical = a.get("href")
            self.links.append(a)
        elif tag == "a" and a.get("href"):
            self.hrefs.append(a["href"])
        elif tag == "img":
            self.imgs.append(a)
        elif tag == "script":
            self._script_type = (a.get("type") or "").lower()
            self._buf = []
        if re.fullmatch(r"h[1-6]", tag):
            self._heading = [tag, []]
        if tag not in VOID:
            self._stack.append(tag)

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        if tag == "script" and self._script_type == "application/ld+json":
            self.jsonld.append("".join(self._buf))
        if tag == "script":
            self._script_type = None
        if self._heading and tag == self._heading[0]:
            self.headings.append((tag, " ".join("".join(self._heading[1]).split())))
            self._heading = None
        if tag in self._stack:
            while self._stack and self._stack.pop() != tag:
                pass

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        if self._script_type is not None:
            self._buf.append(data)
            return
        if self._heading:
            self._heading[1].append(data)
        if not any(t in SKIP_TEXT for t in self._stack) and "head" not in self._stack:
            self.text.append(data)


class Site:
    def __init__(self, root, site, url_style, noindex):
        self.root = root
        self.site = site.rstrip("/")
        self.clean = url_style == "clean"
        self.noindex = {p.rstrip("/") or "/" for p in noindex}

    def pages(self):
        return sorted(p for p in self.root.rglob("*.html")
                      if not SKIP_DIRS.intersection(p.relative_to(self.root).parts))

    def path_of(self, file):
        rel = file.relative_to(self.root).as_posix()
        if rel == "index.html":
            return "/"
        if rel.endswith("/index.html"):
            return "/" + rel[: -len("index.html")]
        return "/" + (rel[:-5] if self.clean else rel)

    def target(self, href):
        """Map an internal href to a file in the repo, or None if it is external."""
        href = href.split("#")[0].split("?")[0]
        if href.startswith(self.site):
            href = href[len(self.site):] or "/"
        if not href.startswith("/") or href.startswith("//"):
            return None
        p = self.root / href.lstrip("/")
        if href.endswith("/"):
            return p / "index.html"
        if p.suffix:
            return p
        return p.with_suffix(".html") if p.with_suffix(".html").exists() else p / "index.html"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--site", required=True)
    ap.add_argument("--noindex", default="")
    ap.add_argument("--no-dashes", action="store_true")
    ap.add_argument("--allow-dash", default="")
    ap.add_argument("--url-style", choices=["clean", "html"])
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    root = pathlib.Path(a.root).resolve()
    style = a.url_style
    if not style:
        try:
            style = "clean" if json.loads((root / "vercel.json").read_text()).get("cleanUrls") else "html"
        except (OSError, ValueError):
            style = "html"
    site = Site(root, a.site, style, [p for p in a.noindex.split(",") if p])
    allowed_dash = {w for w in a.allow_dash.split(",") if w}
    issues = []

    def add(level, page, msg):
        issues.append({"level": level, "page": page, "issue": msg})

    sitemap_urls = set()
    if (root / "sitemap.xml").exists():
        try:
            ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
            for loc in ET.parse(root / "sitemap.xml").getroot().findall("s:url/s:loc", ns):
                sitemap_urls.add(loc.text.strip())
        except ET.ParseError as e:
            add("ERROR", "sitemap.xml", f"does not parse: {e}")
    else:
        add("ERROR", "sitemap.xml", "missing")

    robots = (root / "robots.txt").read_text() if (root / "robots.txt").exists() else ""
    if not robots:
        add("WARN", "robots.txt", "missing")
    elif "sitemap:" not in robots.lower():
        add("WARN", "robots.txt", "no Sitemap line")

    pages = site.pages()
    titles, descs = {}, {}
    inbound = {p: 0 for p in pages}
    summary = []
    for file in pages:
        name = file.relative_to(root).as_posix()
        path = site.path_of(file)
        url = site.site + path
        pg = Page()
        pg.feed(file.read_text(encoding="utf-8", errors="replace"))
        indexable = "noindex" not in pg.metas.get("robots", "")
        expected_noindex = (path.rstrip("/") or "/") in site.noindex or file.name == "404.html"
        title = " ".join(pg.title.split())
        desc = pg.metas.get("description", "")
        summary.append({"page": name, "url": url, "title": title, "title_len": len(title),
                        "desc_len": len(desc), "h1": [h for t, h in pg.headings if t == "h1"],
                        "indexable": indexable})

        if not pg.lang:
            add("WARN", name, "html has no lang attribute")
        if not title:
            add("ERROR", name, "missing <title>")
        elif not 25 <= len(title) <= 65:
            add("WARN", name, f"title is {len(title)} characters (aim for 30 to 60)")
        if "viewport" not in pg.metas:
            add("ERROR", name, "missing viewport meta")
        if indexable and expected_noindex:
            add("WARN", name, "expected noindex but page is indexable")
        if not indexable and not expected_noindex:
            add("WARN", name, "page is noindex")
        if indexable:
            titles.setdefault(title, []).append(name)
            descs.setdefault(desc, []).append(name)
            if not desc:
                add("ERROR", name, "missing meta description")
            elif not 70 <= len(desc) <= 165:
                add("WARN", name, f"meta description is {len(desc)} characters (aim for 120 to 160)")
            if not pg.canonical:
                add("WARN", name, "no canonical tag")
            elif pg.canonical != url:
                add("WARN", name, f"canonical is {pg.canonical!r}, page URL looks like {url!r}")
            if sitemap_urls and url not in sitemap_urls and (pg.canonical or url) not in sitemap_urls:
                add("WARN", name, "indexable page missing from sitemap.xml")
            for key in ("og:title", "og:description", "og:image", "twitter:card"):
                if key not in pg.metas:
                    add("WARN", name, f"missing {key}")
            if not pg.jsonld:
                add("WARN", name, "no structured data")

        h1s = [h for t, h in pg.headings if t == "h1"]
        if len(h1s) != 1:
            add("WARN", name, f"has {len(h1s)} h1 headings (expected 1)")
        last = 0
        for tag, _ in pg.headings:
            level = int(tag[1])
            if last and level > last + 1:
                add("INFO", name, f"heading level jumps from h{last} to h{level}")
                break
            last = level

        for img in pg.imgs:
            if "alt" not in img:
                add("ERROR", name, f"img without alt: {img.get('src')}")
            elif "width" not in img or "height" not in img:
                add("INFO", name, f"img missing width or height (layout shift risk): {img.get('src')}")

        for raw in pg.jsonld:
            try:
                data = json.loads(raw)
            except json.JSONDecodeError as e:
                add("ERROR", name, f"JSON-LD does not parse: {e}")
                continue
            items = data.get("@graph", [data]) if isinstance(data, dict) else data
            for item in items:
                if isinstance(item, dict) and "@type" not in item:
                    add("WARN", name, "JSON-LD item without @type")

        for href in pg.hrefs:
            t = site.target(href)
            if t is None:
                continue
            if not t.exists():
                add("ERROR", name, f"broken internal link: {href}")
            elif t in inbound and t != file:
                inbound[t] += 1

        if a.no_dashes:
            text = " ".join(" ".join(pg.text).split())
            for m in re.finditer(r"\S*[\u2014\u2013]\S*|\b\w+-\w+\b", text):
                word = m.group(0)
                if re.fullmatch(r"[\d\-/:.]+", word) or word in allowed_dash:
                    continue
                add("ERROR", name, f'dash in visible copy: "{word}"')

    for title, names in titles.items():
        if len(names) > 1:
            add("ERROR", ", ".join(names), f'duplicate title "{title}"')
    for desc, names in descs.items():
        if desc and len(names) > 1:
            add("ERROR", ", ".join(names), "duplicate meta description")
    for file, count in inbound.items():
        path = site.path_of(file)
        if count == 0 and path != "/" and (path.rstrip("/") or "/") not in site.noindex and file.name != "404.html":
            add("WARN", file.relative_to(root).as_posix(), "orphan page: no internal links point to it")

    if a.json:
        print(json.dumps({"pages": summary, "issues": issues}, indent=2))
    else:
        for s in summary:
            flag = "" if s["indexable"] else "noindex"
            print(f"{s['page']:40} title {s['title_len']:>3}  desc {s['desc_len']:>3}  h1 {len(s['h1'])}  {flag}")
        print()
        order = {"ERROR": 0, "WARN": 1, "INFO": 2}
        for i in sorted(issues, key=lambda i: (order[i["level"]], i["page"])):
            print(f"{i['level']:5} {i['page']}: {i['issue']}")
        counts = {k: sum(1 for i in issues if i["level"] == k) for k in order}
        print(f"\n{len(pages)} pages, {counts['ERROR']} errors, {counts['WARN']} warnings, {counts['INFO']} info")
    sys.exit(1 if any(i["level"] == "ERROR" for i in issues) else 0)


if __name__ == "__main__":
    main()
