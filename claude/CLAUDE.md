# Colossus Bets — shared agent instructions

Loaded into every Claude Code session by `~/.claude/CLAUDE.md` (installed by `scripts/setup-claude-code.ps1`).
The same skills, rules and knowledge are used from Cursor, so the two tools can share work on one repo.

## Where things live

- **Skills**: `skills/` in this repo. They are linked into `~/.claude/skills/`, so Claude Code finds them by name.
- **Knowledge (Colossus)**: the Colossus KB graph (Neo4j) is the only source of truth, read and written through the `knowledge` skill (`kb.py`). Look up the relevant facts before changing code that touches pools, settlement, engine controllers, event ordering or conventions. Record new knowledge only through the skill, after the user confirms. `knowledge/colossus-bets/` in this repo is an old snapshot of the graph that is not kept up to date: don't read it for answers and don't edit it.
- **Rules**: `rules/` in this repo (Cursor `.mdc` format). The always-on ones are imported below.
- **Repo rules**: each repo's own `.cursor/rules/` and `AGENTS.md` are loaded by that repo's `CLAUDE.md`.

## Working agreement

The working agreement is the `technical/workflow` facts in the Colossus KB. A SessionStart hook (`claude/hooks/kb_session_context.py`, installed by `scripts/setup-claude-code.ps1`) reads them live from the graph and adds them to the session under **Colossus KB: technical/workflow**. If that section is missing or says it wasn't loaded, read it before Colossus work: `kb.py read context --path-prefix technical/workflow`. Change it with the `knowledge` skill.

## Always-on rules

@../rules/kb-lookup-triggers.mdc
@../rules/kb-writes-via-skill-only.mdc
@../rules/gitlab-work-item-sync.mdc
@../rules/run-probe-scripts.mdc

## Python changes

When you change Python in a repo that has a Bandit baseline, follow `rules/bandit-quality-gate.mdc` in this repo (path relative to this file: `../rules/bandit-quality-gate.mdc`).

## Sharing work with Cursor

- Keep plans, probes and notes in files in the repo (`.scratch/` for throwaway probes, the GitLab work item for task state), not only in the chat. The other tool can then pick the work up.
- Do not edit `.cursor/` from Claude Code or `.claude/` from Cursor unless asked. Shared content goes in this repo.
- Commit coherent slices as you go (`commit-regularly` skill), so either tool starts from a clean tree.
