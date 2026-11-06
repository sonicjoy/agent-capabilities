# Cursor User Rules (paste into Cursor Settings → Rules → User Rules)

Cursor doesn't load rule files from `~/.cursor/rules/`, so the always-on Colossus rules reach Cursor through this block. `scripts/setup_kb.py` copies it to the clipboard and asks once. Claude Code gets the full rules from `rules/` through `claude/CLAUDE.md`. The rule files in `rules/` are the source: this block keeps their key points, and `skills/knowledge/scripts/tests/test_rules_sync.py` fails if the two drift apart. Paste it again when it changes.

```text
Colossus knowledge (Colossus Bets work only):
- The Colossus KB graph (Neo4j) is the only source of truth; knowledge/colossus-bets/ is an old snapshot, never read it for answers. At the start of a Colossus task, read the working agreement: kb.py read context --path-prefix technical/workflow. If the KB isn't reachable, say so and ask me to run scripts/setup_kb.py.
- Look up the Colossus KB with the `knowledge` skill (kb.py read search / read fact) before planning, designing, debugging (before proposing a fix) or changing code that touches pools, settlement, remaining units, event ordering, commingling, StatsFeed, cbtote, fantasy/MVP or the GitLab process. Not for typos, formatting or dependency bumps. Mention the fact ids you used.
- Change the KB only with `kb.py write` via the knowledge skill, after I say yes to the --dry-run result. Never write with a Neo4j MCP or your own Cypher, never run graph/admin/*, never hand-edit knowledge/colossus-bets/. After a write, report the fact id and version; don't run kb.py export or offer an export MR unless I ask.
- Every Colossus task has one GitLab work item on gitlab.colossusbets.com (plan-gitlab-work-item skill): status In progress + "Plan — start" when work starts, "Plan — progress" when an MR opens or the approach changes, "Plan — done" with evidence then status Done. Same turn as the progress. Ask before commenting on someone else's issue.
```
