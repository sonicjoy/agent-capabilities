# Agent capabilities

Shared **agent skills**, **rules**, and **workflows** for Colossus teams, used from both Cursor and Claude Code. Use this repo as the canonical place to version, review, and distribute how we want AI agents to behave across projects.

**Quick start:** to give Claude Code and Cursor access to the Colossus knowledge base, follow [Install the Colossus KB](#install-the-colossus-kb-claude-code-and-cursor): clone this repo, run `python scripts/setup_kb.py`, restart both apps, then `python scripts/setup_kb.py --check`.

## What lives here

| Kind | Purpose |
|------|---------|
| **Skills** | Task-focused instructions (`SKILL.md`) the agent loads when relevant—deploy steps, domain workflows, tool usage, review checklists. |
| **Rules** | Persistent guidance (`.mdc` in `.cursor/rules/`)—coding standards, file-specific patterns, always-on conventions. |
| **Workflows** | Human-readable runbooks: when to do what, gates, handoffs, and links to skills/rules that implement each step. |

## Repository layout

```
agent-capabilities/
├── skills/           # One folder per skill: skills/<name>/SKILL.md
├── rules/            # Cursor rules: rules/<name>.mdc (copy into .cursor/rules/)
├── knowledge/        # Old snapshot of the Colossus KB graph, not kept up to date (read the graph with kb.py)
├── graph/            # Colossus KB schema, migrations, query templates, admin scripts
├── ingest/ export/   # One-off markdown import; graph -> knowledge/ export
├── mcp/              # Example MCP config (no secrets): mcp.example.json
├── claude/           # Claude Code entry point (CLAUDE.md), imported from ~/.claude/CLAUDE.md; hooks; mods
├── cursor/           # Cursor User Rules block (user-rules.md)
├── scripts/          # setup_kb.py (KB install), setup-claude-code.ps1, check_kb_readonly.py
├── docs/plans/       # Plans (e.g. the Colossus KB)
├── CATALOG.md        # Full list of what is in this repo
├── CONTRIBUTING.md   # MRs, the knowledge write path, secrets
└── README.md
```

Colossus knowledge (including the workflow runbooks) lives in the Colossus KB graph; use the `knowledge` skill. `knowledge/colossus-bets/` is an old snapshot of it that agents don't read.

Keep each skill in its own directory with a single `SKILL.md` entry point.

### Skill conventions

- Each skill is a directory with **`SKILL.md`** and YAML frontmatter (`name`, `description`).
- Optional: `reference.md`, `examples.md`, `scripts/` for helpers.
- Write descriptions so the agent can **discover** the skill from natural-language triggers (“use when…”, “when the user asks…”).

### Rule conventions

- Rules use **`.mdc`** with frontmatter: `description`, optional `globs`, and `alwaysApply`.
- Prefer **narrow globs** over global rules when the guidance only applies to certain files.

### Workflow conventions

- One doc per process; link to the skills and rules it depends on.
- Include prerequisites, verification steps, and who owns escalation.

## Using this repo

### Project-scoped (recommended for team repos)

1. Clone or submodule this repository, or copy the pieces you need.
2. **Skills**: place under `.cursor/skills/<skill-name>/` in the target project (or symlink from a shared checkout).
3. **Rules**: copy from `rules/` into the project’s `.cursor/rules/`. For the always-on Colossus rules in every project, paste [`cursor/user-rules.md`](cursor/user-rules.md) into Cursor Settings → Rules → User Rules (Cursor doesn't load `~/.cursor/rules/`).
4. **Knowledge**: install the Colossus KB with `python scripts/setup_kb.py` ([below](#install-the-colossus-kb-claude-code-and-cursor)); it covers the `knowledge` skill, its logins, rules and MCP server. Don't copy or edit `knowledge/`: it is generated.
5. **Other MCP servers**: merge `mcp/mcp.example.json` into `~/.cursor/mcp.json` with real credentials from your secrets process (see `mcp/README.md`).

### Install the Colossus KB (Claude Code and Cursor)

One command, run once, sets up the KB for both Claude Code and Cursor.

**Before you start:**

| Need | Check | Get it |
|------|-------|--------|
| This repo, cloned | `C:\repos\agent-capabilities` exists | `git clone git@gitlab-shell.colossusbets.com:colossus/agent-capabilities.git C:\repos\agent-capabilities` |
| Python 3.11+ | `python --version` | python.org, or `winget install Python.Python.3.12` |
| uv, which runs `kb.py` and the MCP server | `uv --version` | Windows: `winget install astral-sh.uv`; macOS: `brew install uv` (or [docs.astral.sh/uv](https://docs.astral.sh/uv/)) |
| Claude Code CLI on `PATH` (for its MCP entry) | `claude --version` | [Claude Code setup](https://docs.claude.com/en/docs/claude-code/setup); without it, setup skips only Claude Code's MCP entry |
| Your KB logins | — | `kb_<name>` (writer) and `kb_<name>_reader`, with their passwords, from the KB owner (team secret store) |

**Install** (from the repo folder; close Cursor and Claude Code first, or restart them afterwards):

```
cd C:\repos\agent-capabilities
python scripts/setup_kb.py
```

Options: `--dry-run` previews, `--reader-only` skips the writer login (look things up only), `--reset` asks again for logins already set (Enter keeps a value).

It:
1. checks uv and prepares `kb.py`'s environment (`kb.py` runs as `uv run kb.py`, so nothing is pip-installed into your Python);
2. links the `knowledge` skill into both tools (links, so updates to this repo arrive by themselves);
3. asks for your KB logins that aren't set yet (`kb_<name>` and `kb_<name>_reader`; passwords show as `*`) and stores them as user environment variables;
4. adds the read-only `neo4j-colossus-kb` MCP server to both tools (variable references only, no password);
5. makes Claude Code import the shared instructions and KB rules;
6. copies the KB rules to the clipboard for Cursor's User Rules and asks once whether you pasted them;
7. **checks everything** (below).

**Finish in each tool** (setup can't do these for you):
- **Cursor:** at step 6, paste the clipboard into Settings → Rules → User Rules (replacing an older copy), close Settings, then answer `y`. Restart Cursor.
- **Claude Code:** restart it (desktop app and any open `claude` terminals). Nothing to paste: `~/.claude/CLAUDE.md` now imports the rules.

Run it again only for new logins or a new instance (`--reset`), or when `--check` reports that the Cursor rules changed. `git pull` in this repo updates the skill in both tools by itself (they are links).

**Verify** at any time; this changes nothing and exits 1 if anything is wrong:

```
python scripts/setup_kb.py --check
```

It checks with the saved settings, as a restarted app sees them:
- the settings (and that the URI isn't the retired staging instance), both skill links, both MCP entries and the rules;
- a KB read (`kb.py status`, showing the instance and the number of facts);
- the read-only MCP: it reads, and refuses writes;
- a dry-run write with the writer login, rolled back.

Then, in a new Claude Code or Cursor session:
- `/mcp` (Claude Code) or Settings → MCP (Cursor) shows `neo4j-colossus-kb` connected;
- asking "use the knowledge skill: what is the rule for withdrawn runners?" gets an answer from the KB citing `withdrawn-unit-reallocation`;
- if `kb.py` warns "this app was started before … changed", restart that app; if it warns that the URI points at staging, run `setup_kb.py --reset` (Enter at the URI prompt then takes production).

The settings it stores (values from the team secret store; never in git, MRs, work items or chats):

| Variable | Value |
|----------|-------|
| `COLOSSUS_KB_URI` | `neo4j+s://fc801360.databases.neo4j.io` (production; the default in `setup_kb.py`) |
| `COLOSSUS_KB_DATABASE` | `neo4j` |
| `COLOSSUS_KB_USER` / `COLOSSUS_KB_PASSWORD` | `kb_<name>` (`publisher`): lets your agent record knowledge through `kb.py write` |
| `COLOSSUS_KB_READER_USER` / `COLOSSUS_KB_READER_PASSWORD` | `kb_<name>_reader` (`reader`): reads, and the read-only `neo4j-colossus-kb` MCP; the database refuses its writes |

MCP servers only see variables that existed when the app started, hence the restart (`kb.py` also reads them from the registry). The admin login is never stored this way; see [graph/admin/README.md](graph/admin/README.md).

**macOS / Linux:** run the setup with `python3` (macOS has no `python`). Don't pip-install anything: Homebrew's Python refuses it, and `kb.py` gets `neo4j` through `uv run`. Steps 1, 2, 4, 5 and 7 work the same; step 3 prints the variables to add to your shell profile (`export COLOSSUS_KB_…=…`) instead of storing them. Add them, open a new shell, and run `setup_kb.py` again. Apps started from the Dock don't read your shell profile: start Cursor and `claude` from that shell, or also set each variable with `launchctl setenv`. Step 6 asks you to copy [`cursor/user-rules.md`](cursor/user-rules.md) by hand if no clipboard tool is found.

**If something fails:**

| Symptom | Fix |
|---------|-----|
| `--check` fails on the MCP, or `/mcp` shows `neo4j-colossus-kb` failed | Install uv, restart the app; an app started before setup can't see the variables |
| `No module named 'neo4j'` | Something ran `kb.py` with plain `python`/`python3`. Run it as `uv run skills/knowledge/scripts/kb.py …` (agents do); nothing needs pip-installing |
| `No module named 'neo4j'` from `graph/admin/*` (admins) | Run them as `uv run graph/admin/<script>.py …`, as in [graph/admin/README.md](graph/admin/README.md) |
| First session after a `git pull` says the working agreement wasn't loaded (timed out) | uv was preparing `kb.py`'s environment for a new dependency version: run `python scripts/setup_kb.py --check` once, or just start another session |
| Claude Code MCP entry `skip` | Install the Claude Code CLI, then run `setup_kb.py` again |
| `kb.py` warns the app "was started before … changed" | Restart that app |
| `kb.py` warns the URI points at staging | `python scripts/setup_kb.py --reset`; Enter at the URI prompt takes production |
| Auth error for your reader or writer login | Wrong name or password: `--reset` and enter them again |
| `skip (exists, not a link to this repo)` for a skill | You have an older copy of `knowledge` in `~/.claude/skills` or `~/.cursor/skills`: move it away, run again |

Details of `kb.py` and every setting: [`skills/knowledge/scripts/README.md`](skills/knowledge/scripts/README.md). Agents read and write the KB through the [`knowledge`](skills/knowledge/SKILL.md) skill; the write path is in [CONTRIBUTING](CONTRIBUTING.md).

For the rest of this repo's skills and MCP servers in Claude Code, also run `setup-claude-code.ps1` ([below](#claude-code-shared-with-cursor)); it works alongside `setup_kb.py` in either order.

### Personal / cross-project

Skills can also live in your **user Agent Store** (`skills/<skill-name>/SKILL.md`) so they follow you across machines when signed in. Prefer **this repo** for anything the team should share and review; use the user store for individual experiments until they are ready to promote here.

Do not commit copies into `~/.cursor/skills-cursor/`—that tree is reserved for Cursor built-ins.

## Claude Code (shared with Cursor)

The same skills, rules, knowledge and MCP servers work in Claude Code. Clone this repo, then from PowerShell:

```powershell
cd C:\repos\agent-capabilities
.\scripts\setup-claude-code.ps1 -DryRun   # preview
.\scripts\setup-claude-code.ps1
```

It is safe to re-run and deletes nothing. It:

1. Links every `skills/<name>` into `~/.claude/skills/` and `~/.cursor/skills/` (junctions), so edits here reach both tools.
2. Adds a managed block to `~/.claude/CLAUDE.md` that imports [`claude/CLAUDE.md`](claude/CLAUDE.md) (working agreement + always-on rules) and your personal `~/.cursor/rules`.
3. Copies MCP servers from `~/.cursor/mcp.json` into Claude Code (user scope), skipping ones already there. `${env:NAME}` references stay references. It warns about Neo4j servers that use the admin login, or KB servers without `--read-only`.
4. Writes a `CLAUDE.md` into each repo under `C:\repos` that has `.cursor/rules` or `AGENTS.md`, loading them (always-on rules imported, scoped rules listed), and adds it to `.git/info/exclude`.
5. Loads the mods in [`claude/mods/`](claude/mods/) in every Claude Code session, straight from this folder: [`agent-watch`](claude/mods/agent-watch/README.md), a live pane of what the agent is doing (its steps, each agent's cost, thinking and terminals, and the files it writes).

Use `-ReposRoot` for another repos folder and `-SkipSkills`, `-SkipClaudeMd`, `-SkipMcp`, `-SkipRepos`, `-SkipMods` to run single steps. Check the result in Claude Code with `/memory` and `/mcp`. For Cursor, paste [`cursor/user-rules.md`](cursor/user-rules.md) into its User Rules.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md): MRs (never push to `main`), how to test skills and rules, the Colossus knowledge write path, and the secret policy.

## Related Cursor concepts

- **Skills**: procedural knowledge the agent reads on demand.
- **Rules**: always-on or file-scoped context in `.cursor/rules/`.
- **User rules**: editor-level preferences; team standards belong here or in project rules, not only in personal settings.

Questions or proposals for new capabilities: open an issue or MR in this repository.
