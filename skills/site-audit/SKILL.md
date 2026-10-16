---
name: site-audit
description: Deterministic SEO audit of a static HTML website checkout (titles, meta descriptions, canonicals, sitemap coverage, noindex, headings, alt text, JSON-LD parsing, broken internal links, orphan pages, Open Graph, optional dash style check). Use before and after every change in an SEO run.
---

# Site audit

Run the bundled script against the cloned client site. It needs only Python 3.

```sh
python3 <this skill's directory>/check_site.py \
  --root /workspace/site \
  --site https://www.example.co.uk \
  --noindex /thank-you \
  [--no-dashes --allow-dash word-one,word-two] \
  [--url-style clean|html] \
  [--json]
```

- `--site` is the client's canonical origin (from the client brief, no trailing slash).
- `--noindex` lists paths that are meant to be noindex, comma separated (from the client brief).
- `--no-dashes` turns on the "no em dashes, en dashes or hyphenated words in visible copy" house style check. Use it only when the client brief says `no_dashes: true`.
- `--url-style` defaults to `clean` when `vercel.json` sets `cleanUrls`, otherwise `html`.

Exit code 1 means at least one ERROR. Save the full output before your changes and compare it with the output after them. Every ERROR must be gone after your changes, and any new WARN must be explained in the report.

The script covers static HTML only. It does not replace checking the live site, PageSpeed Insights or Google's structured data rules.
