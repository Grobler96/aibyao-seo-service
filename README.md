# AI by AO SEO care plan

One Claude Managed Agent that does monthly SEO for every client website you look after. Each client has its own folder, schedule, GitHub token, memory and cost cap, so no client's data or access ever touches another's.

On each run, the agent works on one client:

1. It reads that client's brief (`clients/<slug>/client.yaml`) and its memory of earlier changes.
2. It audits the site the way Google and AI search engines see it:
   - indexing
   - Core Web Vitals
   - titles and content
   - structured data
   - AI search readiness
   - local SEO
   - social tags
   - accessibility
3. It makes up to 6 tested, white hat improvements and opens a pull request on the client's site repo for you to review. The host builds a preview, and nothing goes live until you merge.
4. It writes two reports:
   - an internal one for you, which is also the pull request description
   - a short, friendly client update that you can forward after merging

The agent never pushes to the live branch, never merges, and only has the five GitHub tools it needs to open a pull request.

## What's in here

| Path | What it is |
|---|---|
| `agent/agent.md` | The shared agent and its SEO playbook. Improve it once and every client benefits |
| `agent/environment.yaml` | The shared cloud sandbox |
| `skills/site-audit/` | The audit script the agent runs before and after every change |
| `clients/_template/client.yaml` | The brief you fill in for each new client |
| `clients/<slug>/client.yaml` | That client's brief (the only file you edit) |
| `clients/<slug>/deployment.yaml`, `memory_store.yaml`, `vault.yaml` | Generated from the brief by `scripts/client.py render` |
| `scripts/client.py` | `new`, `render`, `run` and `fetch` for a client |
| `scripts/add_token.sh` | Stores a client's GitHub token in that client's vault, securely |
| `claude-lock.json` | Written by `ant apply`. Commit it |

`clients/aibyao/` is your own site, set up as the first client and running twice a month (1st and 15th).

## What the client's site needs

- A static HTML site, or a site built from source files, in a GitHub repo **in your account**. It must deploy from a branch (usually `main`) to a host that builds previews for pull requests, such as Vercel or Netlify. WordPress, Wix and Squarespace sites won't work with this.
- A branch ruleset protecting the live branch (step 2 below). This is what guarantees that nothing reaches the live site without your merge.

## One time setup (first client only)

1. Install the Anthropic CLI (`ant` 1.34 or later) and sign in with `ant auth login`. Then run `pip install pyyaml "anthropic>=0.92.0"`. You also need `jq`.
2. Create the shared agent and environment (dry run first):

```sh
ant apply --dry-run -v agent/agent.md agent/environment.yaml
ant apply agent/agent.md agent/environment.yaml
```

## Adding a client (about 10 minutes)

Replace `acme-plumbing` with the client's short name.

1. **Write the brief:**
   ```sh
   python scripts/client.py new acme-plumbing
   ```
   Fill in `clients/acme-plumbing/client.yaml`. Only include true facts the client is happy to publish; the agent never invents any. The schedule is set to a random day early in the month, so clients don't all run at once.

2. **Protect the live branch:** in the client's site repo, go to Settings, then Rules, then Rulesets, then New branch ruleset.
   - Target the default branch.
   - Tick "Restrict deletions", "Block force pushes" and "Require a pull request before merging" (0 approvals is fine).
   - Leave the bypass list empty and set the ruleset to Active.

3. **Create a GitHub token for that one repo:** in GitHub, go to Settings, then Developer settings, then Fine grained tokens.
   - Repository access: Only select repositories, then pick that site's repo.
   - Permissions: Contents **Read and write**, Pull requests **Read and write**.
   - Expiry: up to a year. Note the renewal date.

4. **Create the client's vault, memory and schedule, store the token, then pause the schedule:**
   ```sh
   python scripts/client.py render acme-plumbing
   ant apply clients/acme-plumbing/vault.yaml clients/acme-plumbing/memory_store.yaml
   bash scripts/add_token.sh acme-plumbing          # paste the token at the hidden prompt
   python scripts/client.py render acme-plumbing    # now picks up the vault ID
   ant apply clients/acme-plumbing/deployment.yaml &&
     ant beta:deployments pause --deployment-id "$(jq -r '.resources["./clients/acme-plumbing/deployment.yaml"].id' claude-lock.json)"
   git add -A && git commit -m "Add acme-plumbing" && git push
   ```

5. **Test run:**
   ```sh
   python scripts/client.py run acme-plumbing
   python scripts/client.py fetch acme-plumbing     # 20 to 45 minutes later, saves both reports to ./reports/acme-plumbing/
   ```
   Open the pull request on GitHub, check the preview on your phone and laptop, then merge or close it. Forward the client update once you merge.

6. **Switch on the monthly schedule:**
   ```sh
   ant beta:deployments unpause --deployment-id "$(jq -r '.resources["./clients/acme-plumbing/deployment.yaml"].id' claude-lock.json)"
   ```

## Changing things

- **A client's details, schedule, focus or cost cap:** edit their `client.yaml`, run `python scripts/client.py render <slug>`, then `ant apply clients/<slug>/deployment.yaml`.
- **The playbook for everyone:** edit `agent/agent.md`, then `ant apply agent/agent.md`. Every client's next run uses the new version.
- **Removing a client:** pause their deployment, revoke their GitHub token, then delete their folder and run `ant apply --prune` only if you're sure.

## Costs and pricing

Each run is capped by the client's `budget_usd`, which defaults to $15. A monthly run usually costs about $4 to $12. That covers model use, web searches at $10 per 1,000, and $0.08 per hour of run time. Check real figures in the Claude Console after the first few runs and lower the cap if there's room.

Suggested pitch: a "website care plan" at £75 to £150 a month. That's a monthly SEO update with a plain English report, plus hosting and small edits. Sell the work, not rankings: no one can guarantee Google positions, so the terms should say "monthly technical and on page SEO improvements and a report".

## Coming next

Google Search Console data (searches, clicks, positions and indexing problems) for each client, so the agent can target pages that already get impressions and show whether last month's changes worked. This needs the client to add a Google Cloud service account to their Search Console property.
