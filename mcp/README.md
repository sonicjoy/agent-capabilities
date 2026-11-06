# MCP setup (Colossus)

Copy `mcp.example.json` into your user MCP config (merge with existing servers). **Do not commit real passwords or host-specific credentials**—use your team secrets process or local env overrides.

## Colossus-relevant servers

| Server | Use for |
|--------|---------|
| `staging_mysql_cbtote` | Staging `cbtote` schema (tote replica) |
| `production_uk_cbtote` | UK production tote replica |
| `production_us_fantasy_cbtote` | US fantasy production `cbtote` |
| `staging_mysql_stats_feed` | Staging `stats_feed` |
| `local_mysql_cbtote_test` | Local `cbtote_test` dev DB |
| `aws-mcp` | AWS CLI/docs automation via MCP proxy |
| `awslabs.redshift-mcp-server` | Redshift (data warehouse / reporting profile) |
| `MS Learn Docs` | Optional Microsoft/.NET reference |
| `neo4j-colossus-kb` | The Colossus KB, **read-only** (ad-hoc Cypher only; agents look things up with `kb.py`) |
| `neo4j-aura` | Other Neo4j graphs, only if your squad uses them |

## Colossus KB (`neo4j-colossus-kb`)

The KB MCP is read-only twice over:

- `--read-only`: the server offers no write tool and refuses write queries;
- your reader login (`kb_<name>_reader`) has the database's built-in `reader` role, so the database refuses writes too.

It takes every value from the same user environment variables as `kb.py` (see [`skills/knowledge/scripts/README.md`](../skills/knowledge/scripts/README.md)): `COLOSSUS_KB_URI`, `COLOSSUS_KB_DATABASE`, `COLOSSUS_KB_READER_USER` and `COLOSSUS_KB_READER_PASSWORD`. The config holds only `${env:…}` references, never the password (restart the app after setting the variables: the server sees only what existed when it started), and the server follows `kb.py` to whichever instance `COLOSSUS_KB_URI` names: production (`fc801360`) since 2026-10-08.

**For the KB, use `neo4j-colossus-kb`: read-only, your reader login.** A server with the instance admin login (`neo4j`) can write the KB and bypass `kb.py`. If you need the admin login for other work, keep that server for that work; agents must not use it on the KB (rule `kb-writes-via-skill-only`: changes only through `kb.py write`). `scripts/setup_kb.py` adds `neo4j-colossus-kb` to both tools.

`neo4j-aura` is for other graphs on Aura. Use your own login, not the shared `neo4j` admin: after the migration the KB lives on the same production instance.

## Prerequisites

- [uv](https://docs.astral.sh/uv/) on `PATH` for `uvx` / `uv tool run`
- AWS SSO/profile configured for `aws-mcp` and Redshift MCP
- `glab auth login` for GitLab at `gitlab.colossusbets.com` (see `skills/gitlab-issues/`)
- Loki: Windows SecretStore + `logcli` (see `skills/grafana-loki-logs/`)

## Install

1. Back up `~/.cursor/mcp.json`.
2. Merge entries from `mcp.example.json` into `mcpServers`.
3. Replace every `<placeholder>` with values from your internal runbook or secrets store. `${env:NAME}` entries (Cursor's syntax) are read from your user environment variables; set those instead of pasting values.
4. Restart MCP servers in Cursor (or reload the window).
5. For Claude Code, run `scripts/setup-claude-code.ps1`: it copies the servers over and turns `${env:NAME}` into Claude Code's `${NAME}`.

## Pair with skills

- Database investigations: pool settlement, cbtote debugging → MySQL MCP + `skills/pool-settlement-error/`
- Logs: `skills/grafana-loki-logs/`
- EKS: `skills/access-kube-pod/`
- GitLab: `skills/gitlab-issues/`, `skills/plan-gitlab-work-item/`
- Colossus knowledge: `skills/knowledge/` (`kb.py`); `neo4j-colossus-kb` only for ad-hoc read-only Cypher
