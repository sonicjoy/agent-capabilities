---
name: grafana-loki-logs
description: >-
  Debug production/staging issues with logcli against Grafana Loki. Use when
  investigating service errors, incident triage, enginelinux, statsfeed /
  cbstats-feed router behavior, or when the user asks for Loki logs.
---

# Grafana Loki debug skill (logcli)

## Goal

Make Loki debugging fast and repeatable with `logcli` as the default workflow.

## Prerequisites

1. Install `logcli` and confirm: `logcli --version`
2. Ensure `Microsoft.PowerShell.SecretManagement` and `Microsoft.PowerShell.SecretStore` are available.
3. Use the shared script: `scripts/loki-env.ps1`

### Script-first workflow (PowerShell)

```powershell
# Path is relative to this skill folder (wherever the skill is installed)
. "<this-skill-folder>\scripts\loki-env.ps1"
Unlock-LokiSecretStore
Set-LokiEnv -Environment production
Test-LokiAuth
```

Notes:
- `Unlock-LokiSecretStore` must run in an interactive terminal if your SecretStore requires a password prompt.
- Secret names are expected as `loki-env-staging` and `loki-env-production` (JSON with `loki_addr`, `loki_username`, `loki_password`).
- `Set-LokiEnv` loads `LOKI_ADDR`, `LOKI_USERNAME`, and `LOKI_PASSWORD` for the current shell session.

### Script functions

- `Unlock-LokiSecretStore` - unlocks SecretStore only when needed.
- `Set-LokiEnv -Environment staging|production` - loads environment credentials.
- `Test-LokiAuth` - quick labels endpoint check.
- `Get-LokiLogs -Query <logql> -Since <window> -Limit <n>` - runs `logcli query`.
- `Clear-LokiEnv` - clears `LOKI_*` session variables.

## Quick commands

### 1) Script wrapper usage (PowerShell, preferred)

```powershell
Get-LokiLogs -Query '{app="enginelinux"}' -Since '1h' -Limit 80
Get-LokiLogs -Query '{app=~"cbstats-feed-daemon-.*"}' -Since '1h' -Limit 200
Get-LokiLogs -Query '{app="enginelinux"} |~ "\"level\":\"(WARN|ERROR)\""' -Since '6h' -Limit 50
```

### 2) Raw `logcli` fallback (`cmd /c`, Windows quoting-safe)

```powershell
cmd /c 'logcli --addr=%LOKI_ADDR% --username=%LOKI_USERNAME% --password=%LOKI_PASSWORD% query "{app=\"enginelinux\"}" --since=1h --limit=80 --quiet'
cmd /c 'logcli --addr=%LOKI_ADDR% --username=%LOKI_USERNAME% --password=%LOKI_PASSWORD% query "{app=\"enginelinux\"} |~ \"\\\"level\\\":\\\"(WARN|ERROR)\\\"\"" --since=6h --limit=50 --quiet'
```

## Debug workflow

1. Start narrow: `--since=15m` to `--since=1h`, service-specific `app`.
2. Add line filter with `|= "..."` for key/topic/error snippets.
3. Expand only if empty: widen `--since` or relax selector.
4. For noisy output, lower `--limit` first, then refine filter.

## Label gotchas

- `app` is usually the Kubernetes deploy label, not a product nickname.
- If `{app="statsfeed"}` is empty, use real deploy labels like `cbstats-feed-daemon-soccer`, `cbstats-feed-daemon-nba`, `cbstats-feed-daemon-nfl`, `cbstats-feed-daemon-mlb`, `cbstats-feed-daemon-nhl`, `cbstats-feed-daemon-nca`, or `cbstats-feed-api`.

## Troubleshooting

- **401**: bad/missing credentials, VPN/auth gateway issue.
- **400 parse error**: quoting issue in shell or malformed LogQL; on Windows prefer `cmd /c` forms above.
- **200 with empty result**: wrong label or too small window.

## Agent behavior

- Always ask which environment to use (`staging` or `production`) before running any Loki query.
- On PowerShell, prefer script workflow: source `scripts/loki-env.ps1`, then `Set-LokiEnv -Environment <staging|production>`.
- If `Set-LokiEnv` is unavailable, prompt the user to set `LOKI_ADDR`, `LOKI_USERNAME`, and `LOKI_PASSWORD` in the current shell session before running commands.
- Prefer `logcli` commands first.
- On Windows, prefer `cmd /c` for non-trivial LogQL; use direct PowerShell only for simple selectors.
- Never print or persist `LOKI_PASSWORD` (staging or production).
- Return: query used, window, and concise matching lines (or "no matches").

## Optional fallback

Python helper scripts in `scripts/` remain available for advanced post-processing, but default user guidance should be `logcli`.
