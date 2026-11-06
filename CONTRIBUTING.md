# Contributing

Changes to this repo go through a merge request on `gitlab.colossusbets.com/colossus/agent-capabilities`. Never push to `main`. Every Colossus task has one GitLab work item, kept in sync with the work (rule [`gitlab-work-item-sync`](rules/gitlab-work-item-sync.mdc), skill [`plan-gitlab-work-item`](skills/plan-gitlab-work-item/SKILL.md)).

## Skills, rules, docs

1. Add or update the skill (`skills/<name>/SKILL.md`), rule (`rules/<name>.mdc`) or doc.
2. Keep changes focused: one capability per skill or rule.
3. In the MR, say what triggers it, who it's for, and how you tested it (for a skill: a sample task run by an agent that had only the skill text).
4. No secrets, credentials or machine-specific paths: use placeholders and `${env:NAME}` references.
5. A new or changed **always-on rule** also needs `claude/CLAUDE.md` (the `@` import) and, if Cursor should follow it, [`cursor/user-rules.md`](cursor/user-rules.md).

## Colossus knowledge

The Colossus KB graph (Neo4j) is the only source of truth, and agents read it live (the working agreement through a SessionStart hook, see `claude/hooks/`). `knowledge/colossus-bets/` is an old snapshot of the graph, not kept up to date (#19). Agents don't read it; never edit it by hand. Set up access with `python scripts/setup_kb.py` ([README, *Install the Colossus KB*](README.md#install-the-colossus-kb-claude-code-and-cursor)).

| Do | Don't |
|----|-------|
| Change knowledge with `kb.py write` through the [`knowledge`](skills/knowledge/SKILL.md) skill, after the person you work for confirms the dry run | Edit `knowledge/colossus-bets/` by hand: the next export overwrites it |
| Read with `kb.py read` (or the read-only `neo4j-colossus-kb` MCP for ad-hoc Cypher) | Write with a Neo4j MCP, your own Cypher, or the admin login |
| Leave `business/pools` changes as drafts for a second person to `promote`, or to confirm in writing so you can promote with `--confirmed-by` and `--evidence` | Promote your own draft without naming who confirmed it |

**Export:** not routine. Run it only when someone asks for a markdown copy, e.g. to review a batch of changes in an MR:

```
uv run skills/knowledge/scripts/kb.py export --check   # what would change
uv run skills/knowledge/scripts/kb.py export           # write knowledge/colossus-bets/
```

The export refuses to run if any integrity check fails, and refuses to remove more than 3 files without `--allow-removals`. The facts are already live in the graph; the markdown is only a copy for reading.

**Schema changes** (`graph/migrations/`) need an MR and are applied by an admin with `graph/admin/migrate.py` (staging first). Agents never run `graph/admin/*`.

**Tests:** `python -m pytest skills/knowledge/scripts/tests`. Add `KB_IT=1` to run the integration tests; they only run against a test KB (never production) and inside transactions that are rolled back. Staging is retired, so run a local Neo4j Enterprise container and point the test terminal's session at it: see *Tests* in [`skills/knowledge/scripts/README.md`](skills/knowledge/scripts/README.md).

## Secrets

- Each person has their **own KB logins**, `kb_<name>` (writer) and `kb_<name>_reader`, created by the KB owner with `graph/admin/kb_users.py add <name>`. They live in that person's **user** environment variables; the passwords come through the team secret store. Never share your logins: ask the KB owner to add a person instead.
- The **admin login** is never stored: type it into one terminal session only, for `graph/admin/*`, as [graph/admin/README.md](graph/admin/README.md) shows, and remove it afterwards. It never goes in user variables, an MCP config or an agent's environment.
- No login goes in git, an MR, a work item or a chat.
- `kb.py write` refuses text that looks like a credential.
- `.gitignore` covers `mcp/mcp.json`, `.env*`, `*.pem` and `.scratch/`.
