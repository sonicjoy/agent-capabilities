# kb.py

`kb.py` is the only way to read and write the Colossus knowledge graph. Every query it runs comes from a named file under [`graph/`](../../../graph/), and it never runs free-form Cypher. The design is in [`docs/plans/colossus-knowledge-base.md`](../../../docs/plans/colossus-knowledge-base.md).

## Setup

To install for Claude Code and Cursor, run `python scripts/setup_kb.py` from the repo root ([README, *Install the Colossus KB*](../../../README.md#install-the-colossus-kb-claude-code-and-cursor)): it does all of the below, the skill links, the read-only MCP and the rules, then checks them. By hand:

```
uv run skills/knowledge/scripts/kb.py status                    # runtime: kb.py declares neo4j inline (# /// script); uv provides it
pip install -r skills/knowledge/scripts/requirements-dev.txt   # tests only: pytest, and neo4j via requirements.txt
```

Agents, the SessionStart hook and `setup_kb.py --check` all run `uv run kb.py`, so the check tests what agents run. The inline pin and `requirements.txt` are kept equal by a test. **Changing the pin:** update both, and tell the team to run `python scripts/setup_kb.py --check` after pulling it; that prepares the new environment, so the first session's SessionStart hook doesn't time out building it.

| Setting | Value |
|---------|-------|
| `COLOSSUS_KB_URI` | `neo4j+s://<instance>.databases.neo4j.io` |
| `COLOSSUS_KB_USER` | your writer login, `kb_<name>` (`publisher`) |
| `COLOSSUS_KB_PASSWORD` | from the secret store |
| `COLOSSUS_KB_DATABASE` | `neo4j` |
| `COLOSSUS_KB_READER_USER` / `COLOSSUS_KB_READER_PASSWORD` | your reader login, `kb_<name>_reader` (`reader`), and its password (optional, recommended) |

Reads, `status` and `integrity` use the reader login when it's set, and fall back to the writer otherwise. A read-only setup (an agent that only looks things up) needs only `COLOSSUS_KB_URI`, `COLOSSUS_KB_DATABASE` and the reader pair; leave the writer password out of it. Write commands (#6) need the writer.

Set them as user environment variables. On Windows, `kb.py` also reads them from the user environment in the registry, so apps started before you set them still work. A variable set to an empty string in the process counts as unset, so the registry value is used. `status` shows where the settings came from.

`kb.py` only uses the KB logins. Schema migrations need the instance admin, so they live in a separate script for humans, [`graph/admin/migrate.py`](../../../graph/admin/migrate.py). Agents never run `graph/admin/*`.

## Commands

| Command | Does | Exit code |
|---------|------|-----------|
| `kb.py status` | Shows the login, roles, applied and pending migrations, and counts. Prints no secrets. | 0 |
| `kb.py read categories` | The category tree. Leaves (where facts go) show their number of current facts. | 0 |
| `kb.py read context --path-prefix P [--limit N]` | Every current fact under P (whole path segments) in full, as markdown for an agent session. The Claude Code SessionStart hook (`claude/hooks/kb_session_context.py`) runs it for `technical/workflow`. At most 200. | 0, 1 if none |
| `kb.py read current-by-category [--path-prefix P] [--limit N]` | Current facts in a category and everything below it (`business`, `technical/architecture`, …; whole path segments only). Default 50, at most 200; says so when the limit is reached. | 0 |
| `kb.py read search --q TEXT [--limit N]` | Searches current facts. Words are lower-cased; words under 3 characters (except `ru`, `bb`, `ou`) and stopwords are dropped; a simple stem is added per word. The index is sought for every variant, and each word scores once by its best variant (title 4, keywords 3, summary 2, statement 1). At most 8 results. | 0 |
| `kb.py read fact --id ID [--as-of T \| --kb-as-of T]` | One fact in full. `--as-of` gives the rule in force on that date by today's knowledge (corrected versions skipped); `--kb-as-of` gives what the KB said on that date. T is an ISO date or datetime; a date means midnight UTC, and a datetime without a time zone is taken as UTC. A retracted fact has no current version, and `read fact` says so and points to `read history`. | 0, or 1 if not found |
| `kb.py read related --id ID` | One hop: related facts (both directions, with `rel`), described components and their repos, and repos. | 0, or 1 if not found |
| `kb.py read history --id ID` | Every version, oldest first, with status, change type, both timelines, `why` and what it supersedes. | 0, or 1 if not found |
| `kb.py integrity [--json]` | Runs every check in `graph/schema/integrity.cypher` in one read transaction: one snapshot, and the database refuses any write. | 0 clean, 1 problems, 2 error |
| `kb.py export [--out DIR] [--check] [--allow-removals]` | Regenerates `knowledge/colossus-bets/` from the current versions ([`export/`](../../../export/README.md)); refuses if any integrity check fails, or if more than 3 files would be removed without `--allow-removals`. `--check` compares only. | 0, 1 if `--check` finds differences, 2 error |

Reads print compact text by default; add `--json` for structured output. Every read runs in one read transaction. Output is always UTF-8, whatever the console code page. A Windows PowerShell 5.1 that captures or pipes it decodes with `[Console]::OutputEncoding`; if non-ASCII text looks garbled there, set `[Console]::OutputEncoding = [Text.UTF8Encoding]::new()`.

### Writes

Agents write only after the user says yes (see the knowledge skill). Every write:

- runs in **one transaction**: it locks the fact, checks `--expected-current`, applies the change, and runs all integrity checks **before commit**, rolling back on any problem;
- supports `--dry-run`, which does everything, prints the result, then rolls back (show this to the user before they confirm);
- is refused while `COLOSSUS_KB_FREEZE=1` is set;
- is refused if **any** integrity check already fails, even somewhere else in the KB. If a write is blocked that way, run `kb.py integrity` and fix or report what it lists;
- is refused if a field looks like it contains a credential (private key, token, password assignment, credentials in a URL). Everyone with the reader login can read the KB.

**Who:** the author (and a promote's approver) is the person running `kb.py`: `COLOSSUS_KB_AUTHOR`, else `git config --global user.email`. `--author` / `--approver` may only repeat that. A draft is approved by someone other than its author: either they run the promote on their own machine, or the author runs it with `--confirmed-by EMAIL --evidence URL`, naming the person who confirmed it and linking their confirmation (an http(s) link, e.g. a work-item comment or a Slack message). `--confirmed-by` must already be in the KB; for someone new, check the address and add `--confirmed-by-name NAME`. These options are only for the author. Then `KB_APPROVED_BY` points to that person, and the version keeps `approval_recorded_by` (the author) and `approval_evidence`, shown by `read fact` and `read history`.

| Command | Does |
|---------|------|
| `write fact --id … --why … --source-type … --source-ref … --via human\|agent` | New fact (needs `--category` (a leaf), `--kind`, `--title`, `--summary`, `--statement` or `--statement-file`), or a new version of an existing one (needs `--expected-current`; omitted fields keep the latest version's value, including a retracted one being brought back; a different `--category` moves the fact). |
| … `--change-type change` (default) | The rule changed. `--valid-from` = when it took effect (default now; must be after the current start). The old version's `valid_to` closes at that date. |
| … `--change-type correction` | The KB was wrong. Inherits the old dates, or `--valid-from` moves the start; then the previous rule's `valid_to` moves with it (it must stay after that rule's own start). The corrected version disappears from `--as-of` but stays in `--kb-as-of`. |
| … `--draft` | Saved as a draft, not live, remembering the version it was written against. Always the case under `business/pools`. |
| `write promote --version-id V --expected-current V\|none [--confirmed-by EMAIL --evidence URL [--confirmed-by-name NAME]]` | Draft → active, approved by you, or, if you wrote it, by the person in `--confirmed-by` (required then, and only then; not you). Refused if the fact has a newer version than the one the draft was written against: re-draft instead. |
| `write retract --id … --why … --source-ref … --expected-current V [--never-valid]` | The rule stopped applying (`valid_to` = now). `--never-valid` = it was never true (`valid_to` = `valid_from`), so `--as-of` never returns it; refused if the version replaced an earlier rule (that would leave a gap; write a correction instead). Why, sources and who are kept and shown by `read history`. |
| `write link --type relates_to --from FACT --to FACT --rel depends_on\|see_also\|contradicts\|example_of` | Typed fact link (idempotent). |
| `write link --type describes --from FACT --to COMPONENT` / `--type implemented_in --from FACT_OR_COMPONENT --to REPO` | Architecture links. |
| `write unlink --type … --from … --to … [--rel]` | Remove a mistaken link (links aren't versioned). |
| `write component --name … [--kind] [--description]`, `write repo --path group/project [--web-url]` | Create or update. A link source that is both a fact id and a component name is refused. |
| `write category --path a/b/c --title …` | A new category; its parent must hold no facts (facts live in leaves). |

Exit codes: 0 written (or dry run), 2 refused or error, with the reason on stderr.

## Tests

```
python -m pytest skills/knowledge/scripts/tests
```

Unit tests (for `kb.py` and `graph/admin/migrate.py`) need no database. To also run the integration tests, set `KB_IT=1` and point the session at a test KB. Staging is retired, so use a throwaway local Neo4j Enterprise container (the schema's type and existence constraints need Enterprise; starting it means accepting Neo4j's evaluation licence):

```bash
docker run -d --name kb-it --rm -p 17687:7687 -e NEO4J_ACCEPT_LICENSE_AGREEMENT=eval -e NEO4J_AUTH=neo4j/<password> neo4j:5.26-enterprise
export COLOSSUS_KB_URI=neo4j://127.0.0.1:17687 COLOSSUS_KB_DATABASE=neo4j
COLOSSUS_KB_ADMIN_USER=neo4j COLOSSUS_KB_ADMIN_PASSWORD=<password> uv run graph/admin/migrate.py
KB_IT=1 COLOSSUS_KB_USER=neo4j COLOSSUS_KB_PASSWORD=<password> COLOSSUS_KB_READER_USER=neo4j COLOSSUS_KB_READER_PASSWORD=<password> python -m pytest skills/knowledge/scripts/tests
docker stop kb-it
```

Every write in them runs in a transaction that is rolled back, and they refuse to run against any host but `localhost`, `127.0.0.1` or the old staging instance. `test_rehearsal_dump_wipe_load_gives_an_identical_kb` needs staging's imported facts and fails on an empty local KB. They include one fixture per integrity check. Each must trigger exactly its own check; the only allowed overlaps are listed in `ALSO_FIRES`.
