# Catalog (Colossus Bets)

Shared Cursor capabilities for Colossus Bets engineering (tote, fantasy pools, cbtote, ops).

## Skills (`skills/`)

| Skill | When to use |
|-------|-------------|
| `access-kube-pod` | EKS pods, kubectl, AWS SSO |
| `commit-regularly` | Commit coherent slices during agent work |
| `gitlab-issues` | GitLab issues via `glab` (`gitlab.colossusbets.com`) |
| `gitlab-cli-skills` | Full `glab` reference and automation scripts |
| `grafana-loki-logs` | Loki / `logcli` for enginelinux, statsfeed, etc. |
| `knowledge` | Look up and record Colossus knowledge in the KB graph through `kb.py` (other companies: markdown in `~/.cursor/knowledge/`) |
| `plan-gitlab-work-item` | GitLab work item for every Colossus task |
| `pool-settlement-error` | Wrong fantasy pool settlements |

## Rules (`rules/`)

| Rule | Scope |
|------|--------|
| `bandit-quality-gate` | Python (`**/*.py`): no new Bandit findings when the repo has a baseline |
| `gitlab-work-item-sync` | Always: one GitLab work item per Colossus task, status and **Plan —** comments in sync with the work |
| `kb-lookup-triggers` | Always: when to look up the Colossus KB (planning, design, debugging, implementing) |
| `kb-writes-via-skill-only` | Always: the KB changes only through `kb.py write`, after the user confirms; never MCP writes or hand edits of the export |
| `run-probe-scripts` | Always: write probe SQL/scripts to `.scratch/` and run them in the same turn |

Claude Code loads the always-on rules through `claude/CLAUDE.md`. Cursor: copy into a project's `.cursor/rules/`, and paste [`cursor/user-rules.md`](cursor/user-rules.md) into User Rules for the always-on Colossus rules.

## Claude Code mods (`claude/mods/`)

| Mod | What it adds |
|-----|--------------|
| [`agent-watch`](claude/mods/agent-watch/README.md) | A live **Agent watch** pane: a timeline of every step; per agent its cost, context, thinking, terminals and file changes; the files being written, streamed as diffs; an audit of outward actions, approvals, instructions and injected context |

`scripts/setup-claude-code.ps1` loads them in every session.

## Knowledge (`knowledge/`)

- `colossus-bets/` — an old snapshot of the graph, not kept up to date (#19). Agents don't read it; never edit it by hand. The graph is the source of truth: read it with `kb.py`.

## Knowledge graph

Colossus knowledge lives in a Neo4j Aura graph (Epic #846; plan in [`docs/plans/colossus-knowledge-base.md`](docs/plans/colossus-knowledge-base.md)). Setup: [README, *Install the Colossus KB*](README.md#install-the-colossus-kb-claude-code-and-cursor); write path: [CONTRIBUTING](CONTRIBUTING.md).

- `graph/`: schema, migrations, read and write query templates, admin scripts
- `ingest/`: one-off load of `knowledge/` markdown into the graph
- `export/`: regenerates `knowledge/` from the graph, only on request
- `skills/knowledge/scripts/`: `kb.py`, the only way to read or write the KB
- `scripts/setup_kb.py`: one-command KB setup for Claude Code and Cursor (skill, logins, read-only MCP, check)

Since #9 the graph is the source of truth; agents read and write it through the `knowledge` skill.

## MCP (`mcp/`)

Sanitized `mcp.example.json` + setup notes for Colossus MySQL, AWS, Redshift, the read-only Colossus KB (`neo4j-colossus-kb`, `kb_reader`, `--read-only`, values from `${env:…}`), and optional Neo4j. No credentials in git.

## Not included (use Cursor marketplace / built-ins)

- `~/.cursor/skills-cursor/*` (Cursor built-in skills)
- Plugins: cursor-team-kit, superpowers, compound-engineering, etc.
- Personal-only: `caveman`, `find-skills`, `code-refactoring`, `read-engine-logs` (incomplete)
