#!/usr/bin/env bash
# Store a client's GitHub token in that client's vault, twice:
#  1. for the GitHub MCP server (opening the pull request), and
#  2. as GITHUB_TOKEN, swapped in only on requests to api.github.com (downloading the site).
# The token is read at a silent prompt, never echoed, and never written to disk or this repo.
#
# Usage (from the repo root, after the client's vault.yaml has been applied):
#   bash scripts/add_token.sh <slug>
set -euo pipefail
slug="${1:?usage: bash scripts/add_token.sh <slug>}"
vault_id=$(jq -r --arg k "./clients/$slug/vault.yaml" '.resources[$k].id // empty' claude-lock.json)
[ -n "$vault_id" ] || { echo "No vault for $slug in claude-lock.json. Apply clients/$slug/vault.yaml first."; exit 1; }

read -rsp "Paste the GitHub token for $slug (input hidden): " CMA_GITHUB_TOKEN; echo
export CMA_GITHUB_TOKEN
[ -n "$CMA_GITHUB_TOKEN" ] || { echo "No token entered."; exit 1; }

jq -n '{display_name: "GitHub MCP", auth: {type: "static_bearer",
        mcp_server_url: "https://api.githubcopilot.com/mcp/", token: env.CMA_GITHUB_TOKEN}}' |
  ant beta:vaults:credentials create --vault-id "$vault_id" >/dev/null

jq -n '{display_name: "GitHub API for site download", auth: {type: "environment_variable",
        secret_name: "GITHUB_TOKEN", secret_value: env.CMA_GITHUB_TOKEN,
        networking: {type: "limited", allowed_hosts: ["api.github.com"]}}}' |
  ant beta:vaults:credentials create --vault-id "$vault_id" >/dev/null

unset CMA_GITHUB_TOKEN
echo "Stored both credentials in vault $vault_id. Now run: python scripts/client.py render $slug"
