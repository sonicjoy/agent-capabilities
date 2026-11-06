---
name: knowledge
description: Look up and record organizational knowledge (business rules, domain constraints, technical decisions, architecture, conventions). Colossus Bets knowledge lives in the Colossus KB graph and is read and written only through kb.py. Use when the user asks about rules or decisions, before planning, designing, debugging or changing code in documented areas (pools, settlement, remaining units, event ordering, commingling, StatsFeed, cbtote, fantasy/MVP, GitLab process), or when knowledge emerges that should be recorded.
---

# Knowledge

Two knowledge stores, used differently:

| Knowledge | Source of truth | How |
|-----------|-----------------|-----|
| **Colossus Bets** | The Colossus KB graph (Neo4j) | `kb.py` only (this skill). The graph is the only source of truth. `knowledge/colossus-bets/` in agent-capabilities is an old snapshot that is not kept up to date: don't read it for answers, don't edit it |
| **Other companies** (e.g. White Swan Data) | Markdown at `~/.cursor/knowledge/` | Edit the files, see [Personal markdown knowledge](#personal-markdown-knowledge) |

`kb.py` is in this skill's `scripts/` folder (in the agent-capabilities checkout, `skills/knowledge/scripts/kb.py`). Run it with `uv run <this skill's folder>/scripts/kb.py …`, from any directory: `uv run` brings its dependency (`neo4j`, declared inline in `kb.py`), which plain `python`/`python3` may not have. If `uv` isn't installed, tell the user to run `python scripts/setup_kb.py`. It works the same from Cursor and Claude Code. Setup and every option: `scripts/README.md`.

Look things up with `kb.py`: it always reaches the KB that the `COLOSSUS_KB_*` settings name, and `kb.py status` says which one. Neo4j MCP servers may also be configured, but their names don't say which database they reach (on some machines `neo4j-kb` is an empty instance). Use one only for ad-hoc read-only Cypher the user asks for, and if a result looks empty, check with `kb.py status` before concluding anything. **Never write through any Neo4j MCP**. `neo4j-aura` is a personal graph, not the KB.

## Is the KB reachable?

Run `kb.py status` once per session, before the first lookup.

- **Exit 0:** use the KB.
- **Exit 2 with `missing COLOSSUS_KB_…`:** no login is configured on this machine. Tell the user you can't reach the KB, and ask them to run `python scripts/setup_kb.py` in their agent-capabilities checkout. Don't answer from the markdown snapshot in `knowledge/colossus-bets/`: it is not kept up to date. Don't write; tell the user what you would have recorded so they can record it on a configured machine.
- **Any other error:** report it. Don't fall back silently.
- **A `WARNING: this app was started before … changed`:** the KB settings changed since this app started (e.g. the move to production), and `kb.py` is still using the old ones. Tell the user to restart the app; until then, results come from the old instance.

`status` uses the read-only login when one is set, so exit 0 doesn't prove you can write. A write that fails with `missing COLOSSUS_KB_…` means this machine can only read: tell the user what you would have recorded, and don't retry.

## Read: minimal and on demand

Stop as soon as the question is answered:

1. **Find:** `kb.py read search --q "words"` (at most 8 hits, ranked), or `kb.py read current-by-category --path-prefix technical/architecture` to browse a topic. `kb.py read context --path-prefix P` prints every current fact under P in full (the session-start hook uses it for `technical/workflow`).
2. **Read:** `kb.py read fact --id ID` for the 1–3 hits that matter: statement, why, sources, dates, and the `version` line.
3. **Expand (only for design or debugging):** `kb.py read related --id ID`: linked facts, components and repos.

Never dump the whole library or a fact's history unless asked. `--json` gives structured output.

**When:** the user asks "what are the rules for X?" or "why do we Y?"; **before** planning, designing, proposing a fix or changing code in documented areas. Not for formatting, typos or dependency bumps.

**Present** what you found with its id (`withdrawn-unit-reallocation`) so the user can check it, and say when a fact is an import from the legacy markdown (`confidence legacy_ingest`) rather than verified since.

**Past states** (only when asked):

| Question | Command |
|----------|---------|
| What was the rule on a date? (business time) | `read fact --id ID --as-of 2026-03-01` |
| What did the KB say on a date? (record time) | `read fact --id ID --kb-as-of 2026-03-01` |
| How did it change? | `read history --id ID` |

The KB was loaded from the legacy markdown on **2026-10-08**. Every legacy fact is recorded from that day, so a `--kb-as-of` before it finds nothing (exit 1: "no version … at …"). That means "not in the KB yet", not "no such fact". Its business dates (`--as-of`) come from the markdown's **Added** dates.

## Write: only after the user says yes

Writes go through `kb.py write` and nothing else: never `write_neo4j_cypher` or any MCP against the KB, never the personal `neo4j-aura` MCP, never `graph/admin/*`, never hand edits under `knowledge/colossus-bets/`. The author is the person you work for: `kb.py` takes it from `COLOSSUS_KB_AUTHOR` or `git config --global user.email`. Use `--via agent` whenever you wrote the text, even from the user's words; `--via human` only when the user supplied the exact text.

### 1. Notice and ask

"I noticed a [rule / decision / …]: [one line]. Should I record it in the Colossus KB?" Record only on a yes. One fact = one rule or decision.

### 2. Check what's there

`read search` for it. Then decide:

| Situation | Operation | Command |
|-----------|-----------|---------|
| Nothing covers it | **create** | `write fact --id NEW --category … --kind … --title … --summary … --statement-file … --expected-current none …` |
| The text was right when written, but the world **changed** (a new release, a new process) | **change** | `write fact --id ID --expected-current V …` with only the fields that change |
| The text was **wrong** when written | **correction** | the same, plus `--change-type correction` |
| The rule **no longer applies** | **retract** | `write retract --id ID --why … --source-ref … --expected-current V` |
| It **never** applied | **retract, never valid** | the same, plus `--never-valid` |

- **V** is the `version` shown by `read fact --id ID`. If someone wrote in between, `kb.py` refuses and names the new version: read again and redo.
- **Change and correction** keep every field you leave out (category, kind, title, …). Pass only what changes, plus `--why`, `--source-type`, `--source-ref` and `--via`. A different `--category` moves the fact.
- **On a change, re-read the title and summary**: if the new statement makes them wrong, pass new ones. Set `--confidence` for what this version rests on: `verified` only if you or the owner checked it (code, data, MR); a kept `legacy_ingest` means "unchecked import".
- **`--valid-from`**: when the rule took effect in reality, if known (the release or MR merge date, as an ISO date), for a create or a change. If unknown, leave it out (it defaults to now) and tell the user. For a correction, only pass it when the original start date was wrong too.
- **`--expected-current none`** on a create makes it fail if someone created that id meanwhile.
- **Retract**: ask the user whether the rule *stopped* applying or *never* applied (`--never-valid`), and why; the why goes in `--why`. Retract takes only the flags shown above (no `--via` or `--source-type`) and reports the version it retracted.

### 3. Fill it in

| Field | Guidance |
|-------|----------|
| `--id` | Short kebab slug, **permanent**, no category in it: `pool-restart-event-ordering` |
| `--category` | An existing **leaf**: `kb.py read categories` shows the tree, with `[leaf, N facts]` (or `1 fact`) on the categories facts can go in. If no leaf clearly fits, propose the closest one or a new leaf (`write category`) and let the user choose |
| `--kind` | `rule` (must/never), `decision` (we chose X over Y; add `--alternatives`, `--trade-offs`, `--revisit-if`), `description` (how it works), `procedure` (steps), `glossary` (a term), `lesson` (from an investigation) |
| `--title`, `--summary` | The summary is one line a PM can read |
| `--statement-file` | The body as markdown. Write it to a temp file rather than quoting a long `--statement` on the command line |
| `--keywords` | Comma-separated words people would search for; no `:`, `/` or `*` |
| `--why` | Why this version exists ("rule changed in release 42", "v2 misread the code") |
| `--source-type` | The main kind of evidence, one value: `mr`, `work_item`, `code`, `db_query`, `conversation` |
| `--source-ref` | At least one; repeat it for every source, whatever its kind: URLs, `colossus/cbtote!123`, `colossus/agent-capabilities#10`, `path/File.cs:120`. For a conversation: `conversation with <user email> on YYYY-MM-DD`, plus the work item if there is one. Never a secret: the writer refuses anything that looks like one |
| `--confidence` | `verified` (checked in code, data or by the owner) or `inferred` |

### 4. Dry run, show, confirm, write

1. Run the command with `--dry-run`: it does everything, including every integrity check, then rolls back. It prints only the outcome (id, new version, status, change type, category, start, and what it supersedes).
2. Show the user what will be stored: the id, operation, category, kind, title, summary, the statement (or for a change, what differs from the current version), why and sources, plus the dry-run outcome. Wait for a yes.
3. Run it without `--dry-run`. Report the id and the version it printed.

**`business/pools`** writes are always saved as **drafts**, and someone other than the author approves them. Either that person promotes it on their own machine (`kb.py write promote --version-id V --expected-current …`), or they confirm the draft in writing (e.g. a work-item comment) and the author promotes it, naming them: `kb.py write promote --version-id V --expected-current … --confirmed-by EMAIL --evidence URL` (add `--confirmed-by-name NAME` if the KB doesn't know them yet). Run that only after the user tells you in chat who confirmed it and where; don't infer a confirmation yourself. Show the user the command and wait for a yes, as for any write.

If a write is refused, report the message as it is. Integrity problems block every write: run `kb.py integrity` and report what it lists; don't work around it.

### 5. After the write

- **No export:** the write is live in the graph, which is all agents read. Don't run `kb.py export` or offer an export MR unless the user asks for one.
- **Work item:** if the knowledge came from a task with a GitLab work item, comment there with the fact id.

### Links (when they help later lookups)

`kb.py write link --type relates_to --from FACT --to FACT --rel depends_on|see_also|contradicts|example_of`; `--type describes` (fact → component), `--type implemented_in` (fact or component → repo). Create components and repos with `write component` / `write repo`.

## Maintenance

Ask before each change, then use the write operations above:

- verbose entries, or entries the world has moved past → a **change** with a distilled or updated statement;
- entries that were wrong when written → a **correction**;
- dead rules → **retract**.

Nothing is ever deleted: the history keeps every version. To review the whole KB, browse it with `read categories` and `read context`; export to markdown only if the user asks.

## Phrases

| User says | Do |
|-----------|----|
| "record / remember this rule" | Write flow |
| "what do we know about X", "search knowledge for X" | `read search` |
| "what topics are there?", "show knowledge" | `read categories` |
| "show business rules", "show technical decisions" | `read current-by-category --path-prefix business` (or `technical`) |
| "what was the rule on <date>" | `read fact --as-of` |
| "update / correct <fact>" | Write flow: change or correction |
| "delete / forget <fact>" | Retract (explain that history is kept) |
| "clean up / distill knowledge" | Maintenance |

## Personal markdown knowledge

For other companies' knowledge (not Colossus): markdown under `~/.cursor/knowledge/<company>/`, with an `index.md` in every folder. These files are edited directly:

- **Read:** start at `~/.cursor/knowledge/index.md`, follow the folder indexes, then grep if needed.
- **Write (after the user confirms):** add an entry to the right topic file, then update that folder's `index.md` (files table and Quick Reference) and the parents' if you added a folder. Entry format:

```markdown
## [Title]
**Added**: YYYY-MM-DD
**Updated**: YYYY-MM-DD (when modified)
**Context**: [when/why this was captured]

[One rule or decision, essentials only]

---
```

- **Delete or distill:** edit or remove the entry, update the indexes, and confirm with the user first.
