# agent-watch

A Claude Code mod (a function-hooks plugin) that adds a live **Agent watch** pane: what the agent is doing, step by step, including what the chat doesn't show.

It opens by itself when the agent starts working. While the agent is idle, only the **Agent watch** button above the prompt shows, next to the newest thing any agent did; press it, or type `/agent-watch`, to open the pane. If you close the pane, it stays closed through the agent's next turns until you open it again.

## Tabs

**Timeline.** One row per thought, reply or tool call, newest first: time, the action (colour-coded by kind, red when it failed), a short description, then model, effort and how long it took. A shell command reads as the agent's description of it. Subagent rows start with `↳`.

**Agents.** One page per agent: `main`, or one subagent. Subagent tabs get names A to Z in the order they started (Alice, Bob, Cindy, Dexter, …, Ziggy; then Alice 2), and appear as each is spawned; the card under the tabs names its type and task. Each page shows:

- the agent's model, effort, estimated cost, context window and tokens
- **Skills & tools:** how many calls of each tool, and the skills used
- **Thinking:** the latest thinking block, if the model shares its text. Turn on `"showThinkingSummaries": true` in your settings to get summaries; it applies to sessions started after.
- **Terminals:** each shell the agent used, drawn as a terminal (prompt, command, output). Each box shows its newest 14 rows; the Timeline has the older commands.
- **File changes:** the files this agent wrote, coloured by change (green added, yellow modified, red deleted), with lines added and removed
- **MCP servers**, **Rules referenced** (rules and memory files read) and **Looked up** (KB queries and web pages), when there are any

**Files.** The workspace tree, opening itself to the file the agent is writing. The write streams in live as a diff, and changed files are coloured by change (green added, yellow modified, red and struck through deleted). The file being edited is highlighted, with ✎ while it is written. Markdown files show rendered.

**Audit.** What an audit of the agent's work needs and the chat doesn't show, for all agents:

- **Outward actions:** each call that reached past the session, newest first: git push (force-push in red), GitLab and GitHub writes (`glab mr create`, `glab issue note`, API mutations), HTTP writes (`curl -X POST`), destructive commands (`rm -r`, `Remove-Item -Recurse`, `git reset --hard`, `DROP TABLE`), cloud changes (`kubectl apply`, AWS writes), KB writes, SQL (with its database; writes in red), MCP tools that send, create, update or delete (Slack, Gmail, Notion, GitLab, AWS), and artifact publishes. Each shows how it was approved and whether it ran.
- **Approvals:** how the session's calls were let run (by a settings rule, by the mode or the tool's own check, by a hook, asked, denied), the rules used most, and the calls that were asked about or refused.
- **Instructions in context:** the CLAUDE.md, rules and memory files the context holds, with their size.
- **Injected into context:** rows the model read that the chat doesn't show: settings hooks' output (by event), reminders and other attachments, deliveries from other sessions and tasks, compactions (tokens before and after), notices. A repeated row is counted, not listed again.

## Install

`scripts/setup-claude-code.ps1` (step 5) loads every mod in `claude/mods/` in every session. It points `CLAUDE_CODE_PLUGIN_DIRS` in `~/.claude/settings.json` at this folder and sets `CLAUDE_CODE_PLUGIN_DIR_WATCH=1`, so a `git pull` reaches running sessions too.

By hand, add this to `~/.claude/settings.json`:

```json
"env": {
  "CLAUDE_CODE_PLUGIN_DIRS": "C:\\repos\\agent-capabilities\\claude\\mods\\agent-watch",
  "CLAUDE_CODE_PLUGIN_DIR_WATCH": "1"
}
```

Use your own clone's path, and separate several folders with `;` (`:` on macOS). Don't install it through a plugin marketplace: that runs a frozen copy that never picks up changes.

**Then restart.** A session reads `CLAUDE_CODE_PLUGIN_DIRS` only when it starts, so chats that are already open keep running without the mod. Quit the Claude app fully and reopen it, or start new chats. `/reload-plugins` won't do it: it acts only on the chat you type it in, and doesn't read that setting again.

**Check it loaded.** An **Agent watch** button sits above the prompt (it hides while the pane is open), and `/agent-watch` is in the slash menu. If neither shows in a new chat, look for `agent-watch` in the session's debug log (`claude --debug`).

**Updates.** Every session watches this folder, so a `git pull` that changes the mod reaches open sessions within a moment, with no restart. Only a change to the setting itself, such as moving your clone, needs a restart.

## Change it

The code is in `hooks/`:

| File | What it does |
|---|---|
| `hooks/register.tsx` | The hooks and the pane |
| `hooks/live-files.ts` | Diff hunks for writes in progress, and Markdown frontmatter |
| `hooks/audit.ts` | The Audit tab's rules: which calls are outward or risky, approval labels, injected rows' text |
| `hooks/terminal-view.tsx` | Wrapping terminal lines |
| `types/index.d.ts` | The state the mod keeps |

Load the `plugin-authoring` skill in Claude Code for the mod API. Before an MR, run these from this folder:

```
claude plugin validate .
claude plugin test .
```

Limits to keep:

- **Drawing size.** A pane's drawing may be at most 100,000 characters serialized (20,000 nodes, 32 deep). Past that, the desktop shows "has not drawn" with no error, and the test kit doesn't check it. Each tab keeps its rows within a budget (`withinBudget`, `TREE_LIMIT`), and a test measures every tab's drawing.
- **Stored state.** The timeline keeps 250 entries: about 1.6 MB at worst, and a test holds it there. Every other stored value is capped (`MAX_*`).
- **Render hooks** may not write state.
- **State reads** must name their atom directly, not through a helper that takes the atom as a parameter: the engine scans the source to list what a mod reads and writes.
- **Copies.** When more than one copy of the mod is loaded in a session, the newest one draws and records, and the older ones pass everything on.
