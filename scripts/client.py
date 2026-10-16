"""Manage SEO care plan clients.

Usage (from the repo root):
    python scripts/client.py new <slug>       # create clients/<slug>/client.yaml from the template
    python scripts/client.py render <slug>    # (re)build the client's Managed Agents files from client.yaml
    python scripts/client.py run <slug>       # start a run now (works while the schedule is paused)
    python scripts/client.py fetch <slug>     # download the latest run's reports into ./reports/<slug>/

Needs: pip install pyyaml "anthropic>=0.92.0", and for run/fetch Anthropic credentials
(ANTHROPIC_API_KEY or `ant auth login`).
"""
import hashlib
import json
import pathlib
import re
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
CLIENTS = ROOT / "clients"


class Literal(str):
    pass


yaml.SafeDumper.add_representer(
    Literal, lambda d, s: d.represent_scalar("tag:yaml.org,2002:str", s, style="|"))


def lock():
    p = ROOT / "claude-lock.json"
    return json.loads(p.read_text())["resources"] if p.exists() else {}


def load(slug):
    path = CLIENTS / slug / "client.yaml"
    if not path.exists():
        sys.exit(f"{path} not found. Run: python scripts/client.py new {slug}")
    data = yaml.safe_load(path.read_text())
    if data.get("slug") != slug:
        sys.exit(f"slug in {path} must be {slug!r}")
    return data


def new(slug):
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,40}", slug):
        sys.exit("slug must be lowercase letters, numbers and hyphens")
    target = CLIENTS / slug / "client.yaml"
    if target.exists():
        sys.exit(f"{target} already exists")
    h = int(hashlib.sha1(slug.encode()).hexdigest(), 16)
    # Spread clients across the month so runs and pull requests don't all land on one day.
    cron = f"{h % 50 + 5} 6 {h % 28 + 1} * *"
    text = (CLIENTS / "_template" / "client.yaml").read_text()
    text = text.replace("slug: SLUG", f"slug: {slug}").replace('"10 6 1 * *"', f'"{cron}"')
    target.parent.mkdir(parents=True)
    target.write_text(text)
    print(f"Created {target.relative_to(ROOT)}. Fill it in, then run: python scripts/client.py render {slug}")


RUBRIC = """\
- seo-report-{slug}-YYYY-MM-DD.md and client-update-{slug}-YYYY-MM.md exist in /mnt/session/outputs/ with today's date. The internal report has the sections: In one minute, Changes in this pull request, Health check, Opportunities for next time, Needs the client.
- Either exactly one new pull request was opened on {repo} from a branch named seo/YYYY-MM-DD into {branch}, with the internal report as its body, or the report states that an earlier seo/ pull request is still open and no new one was opened.
- Nothing was pushed to {branch}, nothing was merged, and no repository other than {repo} was touched.
- No more than {max_changes} changes, each with its evidence and how to check it worked.
- The site audit ran before and after the changes and shows zero errors afterwards; any new warning is explained.
- Every JSON-LD block touched parses and only states facts from the client brief or the live site; no address, phone, opening hours, reviews, ratings, prices or results were invented.
- Changed visible copy follows the brief's style ({language}{dash_rule}) and makes no invented claims.
- Design, animations, forms, consent, analytics and everything in do_not_touch are unchanged, or the report explains a specific fix.
- Every changed page has an updated sitemap lastmod, and any new page is in the sitemap, linked from an existing page and copies the existing page structure.
- PageSpeed Insights results (mobile at least) are recorded for the homepage, or the report says why they could not be fetched.
- The client update is 150 to 300 words, jargon free, promises no rankings or traffic, and contains no internal notes.
- seo-log.md in the memory store has a new dated section for this run.
"""


def render(slug):
    c = load(slug)
    for key in ("business_name", "website", "repo", "branch"):
        if not c.get(key):
            sys.exit(f"client.yaml: {key} is required")
    d = CLIENTS / slug
    (d / "memory_store.yaml").write_text(yaml.safe_dump({
        "name": f"seo-log-{slug}",
        "description": f"SEO change log for {c['business_name']} ({c['website']}): every change the SEO agent "
                       "has proposed, why, the audit and PageSpeed numbers at the time, and what to re-check. "
                       "Read before choosing changes; append a dated section after each run.",
    }, sort_keys=False, width=1000))
    (d / "vault.yaml").write_text(
        "# Holds this client's GitHub token only. Never put a secret in this file.\n"
        + yaml.safe_dump({"type": "vault", "display_name": f"seo-{slug}"}, sort_keys=False))

    vault = lock().get(f"./clients/{slug}/vault.yaml", {}).get("id")
    brief = yaml.safe_dump(c, sort_keys=False, allow_unicode=True, width=1000)
    style = c.get("style") or {}
    deployment = {
        "name": f"seo-{slug}",
        "agent": "../../agent/agent.md",
        "environment_id": "../../agent/environment.yaml",
        "resources": ["./memory_store.yaml"],
        "vault_ids": [vault] if vault else [],
        "schedule": {"type": "cron", "expression": c["schedule"]["cron"],
                     "timezone": c["schedule"].get("timezone", "Europe/London")},
        "budget": {"type": "limit", "max_list_cost": {"amount": str(int(c.get("budget_usd", 15) * 100)),
                                                       "currency": "USD"}},
        "initial_events": [
            {"type": "user.message", "content": [{"type": "text", "text": Literal(
                f"Client brief for this run. Work only on this client.\n\n```yaml\n{brief}```\n")}]},
            {"type": "user.define_outcome",
             "description": Literal(
                 f"Run this month's SEO review of {c['business_name']} ({c['website']}) as described in the "
                 f"client brief: audit the site, make up to {c.get('max_changes', 6)} evidenced, white hat "
                 f"improvements, prove they work, and open one pull request on {c['repo']} from a new "
                 f"seo/YYYY-MM-DD branch into {c['branch']} (unless an earlier seo/ pull request is still "
                 "open). Save the internal report and the client update to /mnt/session/outputs/ and append "
                 "this run to seo-log.md in the memory store.\n"),
             "max_iterations": 3,
             "rubric": {"type": "text", "content": Literal(RUBRIC.format(
                 slug=slug, repo=c["repo"], branch=c["branch"], max_changes=c.get("max_changes", 6),
                 language=style.get("language", "British English"),
                 dash_rule=", no em dashes, en dashes or hyphenated words" if style.get("no_dashes") else ""))}},
        ],
    }
    header = (f"# Generated from client.yaml by scripts/client.py render {slug}. Edit client.yaml, not this file.\n"
              + ("" if vault else "# vault_ids is empty until the vault is applied and its token added (see README).\n"))
    (d / "deployment.yaml").write_text(header + yaml.safe_dump(deployment, sort_keys=False, width=1000,
                                                               allow_unicode=True))
    print(f"Rendered clients/{slug}/memory_store.yaml, vault.yaml and deployment.yaml"
          + ("" if vault else " (no vault ID yet)"))


def deployment_id(slug):
    key = f"./clients/{slug}/deployment.yaml"
    if key not in lock():
        sys.exit(f"{key} is not in claude-lock.json yet. Apply it first (see README).")
    return lock()[key]["id"]


def run(slug):
    import anthropic
    anthropic.Anthropic().beta.deployments.run(deployment_id(slug))
    print(f"Run started for {slug}. It usually takes 20 to 45 minutes. The pull request appears on GitHub; "
          f"then run: python scripts/client.py fetch {slug}")


def fetch(slug):
    import anthropic
    client = anthropic.Anthropic()
    runs = [r for r in client.beta.deployment_runs.list(deployment_id=deployment_id(slug)) if r.session_id]
    if not runs:
        print("No successful runs yet.")
        return
    latest = max(runs, key=lambda r: r.created_at)
    session = client.beta.sessions.retrieve(latest.session_id)
    print(f"Latest run: {latest.created_at}  session {session.id}  status {session.status}")
    print(f"Watch or review it: https://platform.claude.com/workspaces/default/sessions/{session.id}")
    out = ROOT / "reports" / slug
    out.mkdir(parents=True, exist_ok=True)
    files = client.beta.files.list(scope_id=session.id, betas=["managed-agents-2026-04-01"])
    count = 0
    for f in files.data:
        client.beta.files.download(f.id).write_to_file(str(out / f.filename))
        print("Saved", (out / f.filename).relative_to(ROOT))
        count += 1
    if not count:
        print("No report files yet. If the run is still going, try again in a few minutes.")


if __name__ == "__main__":
    commands = {"new": new, "render": render, "run": run, "fetch": fetch}
    if len(sys.argv) != 3 or sys.argv[1] not in commands:
        sys.exit(__doc__)
    commands[sys.argv[1]](sys.argv[2])
