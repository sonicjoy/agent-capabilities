import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { AgentNames, AgentRow, Approval, AuditAction, FileRow, InjectedRow, LoopUsage, WatchEvent, WatchStatus, WatchTab } from '../types'

import { approvalLabel, approvalOf, originLabel, outwardOf, rowText } from './audit'

import { listedPaths, numstatEntries, statusEntries } from './git-parse'
import { fitCommands } from './terminal-view'
import type { TermLine } from './terminal-view'
import { doneHunk, fieldsOf, isMarkdown, lineDelta, normalise, scanFields, splitFrontmatter, writingHunk } from './live-files'

const PANE = 'agent-watch'
const TITLE = 'Agent watch'
const MAX_EVENTS = 250
const MAX_TEXT = 400
// Thinking is shown on the Agents page, and a terminal's output: keep more of those.
const MAX_THINKING = 1500
const MAX_OUTPUT = 2000
const FLUSH_MS = 350
const GIT_EVERY_MS = 5000

const EVENTS = { plugin: 'agent-watch', key: 'events' } as const
const events = atom(EVENTS, [])
const files = atom({ plugin: 'agent-watch', key: 'files' } as const, [])
const tab = atom({ plugin: 'agent-watch', key: 'tab' } as const, 'timeline')
const gitNote = atom({ plugin: 'agent-watch', key: 'gitNote' } as const, '')
const agents = atom({ plugin: 'agent-watch', key: 'agents' } as const, [])
const agentNames = atom({ plugin: 'agent-watch', key: 'agentNames' } as const, { last: 0, dropped: [] })
const focus = atom({ plugin: 'agent-watch', key: 'focus' } as const, '')

const TABS: { id: WatchTab; label: string }[] = [
  { id: 'timeline', label: 'Timeline' },
  { id: 'agents', label: 'Agents' },
  { id: 'files', label: 'Files' },
  { id: 'audit', label: 'Audit' },
]

const loops = atom({ plugin: 'agent-watch', key: 'loops' } as const, {})
const session = atom({ plugin: 'agent-watch', key: 'session' } as const, {})
const contextInfo = atom({ plugin: 'agent-watch', key: 'contextInfo' } as const, { mcp: [], at: 0 })
const CONTEXT_EVERY_MS = 15000
const workspace = atom({ plugin: 'agent-watch', key: 'workspace' } as const, [])
const fileFocus = atom({ plugin: 'agent-watch', key: 'fileFocus' } as const, '')
const live = atom({ plugin: 'agent-watch', key: 'live' } as const, null)
const preview = atom({ plugin: 'agent-watch', key: 'preview' } as const, { path: '', kind: 'none', text: '', note: '', at: 0 })
// Whether the person closed the pane: then the agent's work doesn't open it again by itself.
const dismissed = atom({ plugin: 'agent-watch', key: 'dismissed' } as const, false)
const paneShown = atom({ plugin: 'agent-watch', key: 'paneShown' } as const, false)
const actions = atom({ plugin: 'agent-watch', key: 'actions' } as const, [])
const injected = atom({ plugin: 'agent-watch', key: 'injected' } as const, [])
const approvals = atom({ plugin: 'agent-watch', key: 'approvals' } as const, { rules: {}, hook: 0, mode: 0, asked: 0, refused: 0, denied: 0 })

// The Audit tab's caps: calls that reached past the session, and rows the model read unseen.
const MAX_ACTIONS = 200
const MAX_INJECTED = 150
const MAX_INJECTED_TEXT = 400
// Rows the chat does not show the model reading: a settings hook's output, an attachment (a reminder,
// a nested CLAUDE.md, a listing), a delivery from another session or a task, a compaction, a notice.
const UNSEEN_DOORS = new Set(['hook-context', 'attachment', 'delivery', 'compaction', 'notice', 'note'])

// Tool names as Claude's transcript shows them.
const TOOL_NAMES: Record<string, string> = { Edit: 'Update', Grep: 'Search', Glob: 'Search', WebFetch: 'Fetch' }

const MAX_CHANGED = 500
// Caps on what state keeps, so a long session cannot grow it without bound.
const MAX_AGENTS = 50
// Dropped subagents remembered, so the list does not bring them back.
const MAX_DROPPED = 500
const MAX_PATHS = 3000
const MAX_NOTE = 300

// The engine draws no tree past 100,000 characters serialized: the desktop then shows nothing at
// all ("has not drawn"). Each tab keeps its rows within a share of that, newest first.
const TREE_LIMIT = 100_000
const sizeOf = (tree: unknown) => JSON.stringify(tree)?.length ?? 0
function withinBudget<T>(rows: T[], budget: number): { kept: T[]; left: number } {
  const kept: T[] = []
  let used = 0
  for (const row of rows) {
    used += sizeOf(row)
    if (used > budget) break
    kept.push(row)
  }

  return { kept, left: rows.length - kept.length }
}
const MAX_PREVIEW = 30000
// A terminal box on the Agents tab: this many rows, its newest.
const TERMINAL_ROWS = 14
const MAX_TERMINALS = 6

const ACTIVE = new Set(['pending', 'running', 'waiting'])
const AGENTS_EVERY_MS = 2000

// First-party list prices, $ per million tokens (claude-api skill, 2026-10-06): input, output, cache read.
// Cache writes are priced at 1.25x input. First match wins, so the specific ids come first.
const PRICES: [RegExp, number, number, number][] = [
  [/(fable|mythos)-5-1/, 10, 50, 0.25],
  [/(fable|mythos)-5/, 10, 50, 1],
  [/opus-5-5/, 4, 20, 0.2],
  [/opus/, 5, 25, 0.5],
  [/sonnet-5/, 2, 10, 0.2],
  [/sonnet/, 3, 15, 0.3],
  [/haiku-5-5/, 0.1, 0.5, 0.01],
  [/haiku/, 1, 5, 0.1],
]

const windowOf = (model: string) => (/haiku-4/.test(model) ? 200_000 : 1_000_000)

type StepUsage = {
  model: string
  input_tokens: number
  output_tokens: number
  cache_read_input_tokens: number
  cache_creation_input_tokens: number
}

function priceOf(u: StepUsage): number | undefined {
  const row = PRICES.find(([match]) => match.test(u.model))
  if (row === undefined) return undefined
  const [, input, output, read] = row

  return (
    (u.input_tokens * input +
      u.cache_creation_input_tokens * input * 1.25 +
      u.cache_read_input_tokens * read +
      u.output_tokens * output) /
    1_000_000
  )
}

async function addStep($: EngineInterface, key: string, u: StepUsage, effort?: string | number) {
  const usd = priceOf(u)
  await update($, loops, all => {
    const old: LoopUsage | undefined = all[key]
    const row: LoopUsage = {
      model: u.model,
      effort: effort === undefined ? old?.effort : String(effort),
      requests: (old?.requests ?? 0) + 1,
      input: (old?.input ?? 0) + u.input_tokens,
      cacheRead: (old?.cacheRead ?? 0) + u.cache_read_input_tokens,
      cacheWrite: (old?.cacheWrite ?? 0) + u.cache_creation_input_tokens,
      output: (old?.output ?? 0) + u.output_tokens,
      usd: usd === undefined ? old?.usd : (old?.usd ?? 0) + usd,
      context: u.input_tokens + u.cache_read_input_tokens + u.cache_creation_input_tokens,
      window: windowOf(u.model),
    }

    return { ...all, [key]: row }
  })
}

// What the session's context holds: memory and rules files, MCP tools by server, skills.
// The summary breakdown is estimated locally and sends no request.
async function refreshContext($: EngineInterface) {
  const now = await $.session.usage({ breakdown: 'summary' }).catch(() => undefined)
  const b = now?.context.breakdown
  if (b === undefined) return
  const next = {
    mcp: b.mcpTools.map(t => ({ tool: t.name, server: t.serverName })),
    memory: b.memoryFiles.slice(0, 100).map(f => ({ path: f.path, type: f.type, tokens: f.tokens })),
  }
  const old = await read($, contextInfo)
  const isSame = JSON.stringify({ ...old, at: 0 }) === JSON.stringify({ ...next, at: 0 })
  if (!isSame) await update($, contextInfo, () => ({ ...next, at: Date.now() }))
}

// Entries stored by an earlier version carried raw arguments, diffs and whole replies: keep only
// what is drawn. Where the stored list cannot even be read, start the timeline over.
async function slimStoredEvents($: EngineInterface) {
  const slim = (ev: WatchEvent): WatchEvent => {
    const { args: _args, argLines: _argLines, diff: _diff, ...rest } = ev as WatchEvent & Record<'args' | 'argLines' | 'diff', unknown>

    return {
      ...rest,
      text: rest.text === undefined ? undefined : rest.text.slice(0, rest.kind === 'thinking' ? MAX_THINKING : MAX_TEXT),
      output: rest.output === undefined ? undefined : tail(rest.output, MAX_OUTPUT),
      ...(rest.status === 'running' ? { status: 'error' as const, output: '(no result seen)' } : {}),
    }
  }
  await update($, events, list => list.slice(-MAX_EVENTS).map(slim)).catch(() => $.state.set(EVENTS, []))
  await update($, contextInfo, info => ({ mcp: info.mcp.map(t => ({ tool: t.tool, server: t.server })), memory: info.memory, at: info.at }))
  await update($, preview, shown => ({ ...shown, text: cut(shown.text, MAX_PREVIEW) }))
}

async function refreshSession($: EngineInterface) {
  const now = await $.session.usage().catch(() => undefined)
  if (now === undefined) return
  const figures = {
    usd: now.cost?.usd,
    contextTokens: now.context.tokens,
    window: now.context.window,
    percent: now.context.percent,
  }
  // Written only when it changed: every write redraws the sites that read it.
  if (JSON.stringify(await read($, session)) !== JSON.stringify(figures)) await update($, session, () => figures)
}

const tokens = (n: number) => (n >= 1_000_000 ? `${(n / 1_000_000).toFixed(2)}M` : n >= 1000 ? `${(n / 1000).toFixed(1)}k` : `${n}`)

const dollars = (usd?: number) => (usd === undefined ? '$?' : usd < 0.01 ? `$${usd.toFixed(4)}` : `$${usd.toFixed(2)}`)

const TERMINAL_TOOLS = /^(Bash|PowerShell|BashOutput|KillShell|mcp__terminal__.*)$/

// Which terminal a shell call runs in; a background shell gets its id from the call's result.
function terminalOf(tool: string, args: Record<string, unknown>): string | undefined {
  const id = args.bash_id ?? args.shell_id ?? args.task_id
  if (tool === 'BashOutput' || tool === 'KillShell') return `bg:${typeof id === 'string' ? id : '?'}`
  if (tool === 'Bash' || tool === 'PowerShell') {
    return args.run_in_background === true ? 'bg:starting' : `shell:${tool.toLowerCase()}`
  }
  if (tool === 'mcp__terminal__open_terminal_tab') return 'tab:new'
  if (tool.startsWith('mcp__terminal__') && tool !== 'mcp__terminal__list_terminal_tabs') {
    return `tab:${typeof args.tab_id === 'string' && args.tab_id !== '' ? args.tab_id : '0'}`
  }

  return undefined
}

// Files that carry rules or memory: reading one is the agent consulting it.
const RULE_FILES = /(\/rules\/|\.mdc$|(^|\/)(CLAUDE|AGENTS|SKILL|MEMORY)\.md$|\/memory\/|\/\.cursor\/|\/knowledge\/)/i

// What a call looked up, for the Agents tab's references.
function referenceOf(tool: string, args: Record<string, unknown>): { kind: WatchEvent['refKind']; name: string } | undefined {
  const text = (key: string) => (typeof args[key] === 'string' ? (args[key] as string) : undefined)
  if (tool === 'Skill' && text('skill')) return { kind: 'skill', name: text('skill')! }
  if (tool === 'ToolSearch' && text('query')) return { kind: 'tools', name: text('query')! }
  if (tool === 'WebFetch' && text('url')) return { kind: 'web', name: text('url')! }
  if (tool === 'WebSearch' && text('query')) return { kind: 'web', name: text('query')! }
  const command = text('command')
  const kb = command === undefined ? null : /kb\.py["']?\s+([^\n|&;>]*)/.exec(command)
  if (kb) return { kind: 'kb', name: (kb[1] ?? '').trim().slice(0, 160) }
  const file = text('file_path') ?? text('path')
  if (tool === 'Read' && file !== undefined && RULE_FILES.test(slashes(file))) return { kind: 'rule', name: slashes(file) }

  return undefined
}
const FILE_TOOLS: Record<string, string> = {
  Edit: 'file_path',
  Write: 'file_path',
  NotebookEdit: 'notebook_path',
}

const cut = (text: string, max: number) =>
  text.length > max ? `${text.slice(0, max)}… (+${text.length - max} chars)` : text

// A label too long for a tab or a narrow column: the count of what was cut would only crowd it.
const clip = (text: string, max: number) => (text.length > max ? `${text.slice(0, max)}…` : text)

const tail = (text: string, max: number) =>
  text.length > max ? `…${text.slice(text.length - max)}` : text

const clock = (at: number) => new Date(at).toTimeString().slice(0, 8)

const seconds = (ms?: number) => (ms === undefined ? '' : `${(ms / 1000).toFixed(1)}s`)

const slashes = (path: string) => path.replace(/\\/g, '/')

const shortTool = (tool = '') => (tool.startsWith('mcp__') ? tool.split('__').slice(1).join(' ') : tool)

const effortLabel = (effort?: string) => (effort ? effort.charAt(0).toUpperCase() + effort.slice(1) : undefined)

const firstLine = (text: string) => text.split(/\r?\n/).find(line => line.trim() !== '')?.trim() ?? ''

// One line saying what a tool call is about, for the Timeline.
function summaryOf(tool: string, args: Record<string, unknown>): string {
  const str = (key: string) => (typeof args[key] === 'string' ? (args[key] as string) : undefined)
  const file = str('file_path') ?? str('notebook_path') ?? str('path')
  const short = () => tool.split('__').slice(2).join('__') || tool
  if (file !== undefined && /^(Read|Edit|Write|NotebookEdit)$/.test(tool)) {
    const name = slashes(file).split('/').pop() ?? file

    return tool === 'Edit' && args.replace_all === true ? `${name} (all matches)` : name
  }
  const command = str('command')
  if (command !== undefined) return cut(firstLine(command), 140)
  if (tool === 'Grep' || tool === 'Glob') return `${str('pattern') ?? ''}${file ? ` in ${slashes(file)}` : ''}`
  if (tool === 'Agent') return `${str('subagent_type') ?? 'agent'}: ${str('description') ?? ''}`
  if (tool === 'Skill') return str('skill') ?? ''
  if (tool === 'ToolSearch') return str('query') ?? ''
  const first = Object.values(args).find((v): v is string => typeof v === 'string' && v.trim() !== '')
  const what = str('description') ?? str('url') ?? str('query') ?? str('prompt') ?? first ?? ''

  return cut(firstLine(`${tool.startsWith('mcp__') ? `${short()} ` : ''}${what}`), 140)
}

// The model and effort of each loop's latest model request: stamped on its Timeline rows.
const efforts = new Map<string, string>()
const models = new Map<string, string>()

const toolName = (ev: WatchEvent) => TOOL_NAMES[ev.tool ?? ''] ?? shortTool(ev.tool)
const toolArgs = (ev: WatchEvent) => (ev.isTerminal ? ev.command || ev.summary : ev.summary) ?? ''

// One line, always: a multi-line command (a heredoc, a script) shows its first line and an ellipsis.
function oneLine(text: string): string {
  const lines = text.split(/\r?\n/).filter(line => line.trim() !== '')

  return `${lines[0]?.trim() ?? ''}${lines.length > 1 ? ' …' : ''}`
}

// A Timeline row's words: what happened and about what. The band above the prompt uses them too.
function timelineWords(ev: WatchEvent): { action: string; about: string } {
  const action = ev.kind === 'tool' ? toolName(ev) : ev.kind === 'thinking' ? 'Thinking' : 'Reply'
  // A shell command reads as what it is for (the agent's own description of it), the command
  // itself only when it came without one.
  const about =
    ev.kind === 'tool'
      ? oneLine(ev.isTerminal && ev.note ? ev.note : toolArgs(ev))
      : ev.text
        ? firstLine(ev.text)
        : ev.kind === 'thinking'
          ? '(not shared)'
          : ''

  return { action, about }
}

// A model as the Timeline's narrow column shows it: claude-opus-5-5[1m] → opus-5-5.
const shortModel = (model = '') => model.replace(/^claude-/, '').replace(/\[.*\]$/, '').replace(/-\d{8}$/, '')

// Labels for subagent loops; a reload starts this over, which only costs a lookup.
const labels = new Map<string, string>()

async function agentLabel($: EngineInterface, agentId?: string): Promise<string> {
  if (agentId === undefined) return 'main'
  const known = labels.get(agentId)
  if (known !== undefined) return known
  const listed = await $.agent.list().catch(() => [])
  const found = listed.find(one => one.id === agentId)
  if (found === undefined) return `↳ agent ${agentId.slice(0, 6)}`
  const label = `↳ ${found.type}: ${clip(found.description, 30)}`
  labels.set(agentId, label)
  return label
}

// Merges $.agent.list() into the Agents tab: new subagents, and status changes.
async function refreshAgents($: EngineInterface) {
  const listed = await $.agent.list().catch(() => [])
  if (listed.length === 0) return
  const rows = await read($, agents)
  const book = await read($, agentNames)
  const gone = new Set(book.dropped)
  let settled = { rows, book }
  const merged = (() => {
    const byId = new Map(rows.map(row => [row.id, row]))
    for (const one of listed) {
      // Dropped to keep MAX_AGENTS: back in, it would push out another and take a new name.
      if (gone.has(one.id)) continue
      const old = byId.get(one.id)
      byId.set(one.id, {
        id: one.id,
        n: old?.n,
        type: one.type,
        description: cut(one.description, MAX_NOTE),
        // Its own turn.complete says how a run ended; the list wins when it says the agent runs
        // again, or when it has ended and that turn.complete was missed (a reload mid-run).
        status: ACTIVE.has(one.status) || old === undefined || ACTIVE.has(old.status) ? one.status : old.status,
        parentId: one.parentId,
        startedAt: old?.startedAt ?? Date.now(),
        toolCalls: old?.toolCalls ?? 0,
        lastAction: old?.lastAction,
        answer: old?.answer,
        durationMs: old?.durationMs,
      })
    }

    settled = settle([...byId.values()], book)

    return settled.rows
  })()
  if (JSON.stringify(merged) !== JSON.stringify(rows)) await update($, agents, () => merged)
  await keepBook($, settled.book)
}

// Changes one subagent's row, adding a bare row first when the list has not caught up yet.
async function patchAgent($: EngineInterface, agentId: string, change: (row: AgentRow) => AgentRow) {
  if (!(await read($, agents)).some(row => row.id === agentId)) await refreshAgents($)
  const book = await read($, agentNames)
  if (book.dropped.includes(agentId)) return
  let settled = { rows: [] as AgentRow[], book }
  await update($, agents, rows => {
    const base: AgentRow[] = rows.some(row => row.id === agentId)
      ? rows
      : [
          ...rows,
          { id: agentId, type: 'agent', description: agentId.slice(0, 8), status: 'running', startedAt: Date.now(), toolCalls: 0 },
        ]

    settled = settle(base.map(row => (row.id === agentId ? change(row) : row)), book)

    return settled.rows
  })
  await keepBook($, settled.book)
}

// Keeps MAX_AGENTS rows, notes the ones dropped, and numbers the new ones.
function settle(rows: AgentRow[], book: AgentNames): { rows: AgentRow[]; book: AgentNames } {
  const kept = keepNewest(rows)
  const dropped = rows.filter(row => !kept.includes(row)).map(row => row.id)
  const numberedRows = numbered(kept, book.last)
  const last = Math.max(book.last, ...numberedRows.map(row => row.n ?? 0))

  return { rows: numberedRows, book: { last, dropped: [...book.dropped, ...dropped].slice(-MAX_DROPPED) } }
}

// Writes the book back, merged with any write that landed since it was read.
async function keepBook($: EngineInterface, next: AgentNames) {
  await update($, agentNames, book => {
    const dropped = [...new Set([...book.dropped, ...next.dropped])].slice(-MAX_DROPPED)
    const last = Math.max(book.last, next.last)

    const same = last === book.last && dropped.length === book.dropped.length && dropped.every((id, i) => id === book.dropped[i])

    return same ? book : { last, dropped }
  })
}

// Gives each subagent its tab's number, in the order they started, once and never again: a tab
// keeps its name when older rows go, and no later one takes it.
function numbered(rows: AgentRow[], given: number): AgentRow[] {
  if (rows.every(row => row.n !== undefined)) return rows
  let last = Math.max(given, ...rows.map(row => row.n ?? 0))
  const next = new Map(
    rows
      .filter(row => row.n === undefined)
      .sort((a, b) => a.startedAt - b.startedAt)
      .map(row => [row.id, (last += 1)]),
  )

  return rows.map(row => (row.n === undefined ? { ...row, n: next.get(row.id) } : row))
}

// A subagent's tab name, A to Z in the order they started; the 27th is Alice 2.
const NAMES = [
  'Alice', 'Bob', 'Cindy', 'Dexter', 'Edie', 'Felix', 'Greta', 'Hugo', 'Iris', 'Jasper', 'Kiki', 'Leo', 'Mabel',
  'Ned', 'Olive', 'Pip', 'Quinn', 'Rufus', 'Suki', 'Theo', 'Uma', 'Vince', 'Wren', 'Xavi', 'Yara', 'Ziggy',
]
const tabName = (row: AgentRow) => {
  if (row.n === undefined) return 'agent'
  const lap = Math.floor((row.n - 1) / NAMES.length)

  return `${NAMES[(row.n - 1) % NAMES.length]}${lap > 0 ? ` ${lap + 1}` : ''}`
}

// The running subagents, then the newest finished, MAX_AGENTS in all, in the order they came.
function keepNewest(rows: AgentRow[]): AgentRow[] {
  if (rows.length <= MAX_AGENTS) return rows
  const kept = new Set(
    [...rows]
      .sort((a, b) => Number(ACTIVE.has(b.status)) - Number(ACTIVE.has(a.status)) || b.startedAt - a.startedAt)
      .slice(0, MAX_AGENTS)
      .map(row => row.id),
  )

  return rows.filter(row => kept.has(row.id))
}

const push = ($: EngineInterface, event: WatchEvent) =>
  update($, events, list => [...list, event].slice(-MAX_EVENTS))

// Each call's permission verdict, from its tool.check, until its tool.call has finished and takes it.
const checks = new Map<string, Approval>()

function rememberCheck(id: string, approval: Approval) {
  checks.set(id, approval)
  while (checks.size > 200) checks.delete(checks.keys().next().value as string)
}

async function countApproval($: EngineInterface, approval: Approval) {
  await update($, approvals, tally => {
    if (approval.kind === 'rule') {
      const rule = cut(approval.detail ?? '?', 120)
      const rules = { ...tally.rules, [rule]: (tally.rules[rule] ?? 0) + 1 }
      // The 50 rules used most: a session's rules are few, but a rule names its own pattern.
      const kept = Object.entries(rules).sort((a, b) => b[1] - a[1]).slice(0, 50)

      return { ...tally, rules: Object.fromEntries(kept) }
    }
    if (approval.kind === 'asked') return { ...tally, asked: tally.asked + 1, refused: tally.refused + (approval.outcome === 'refused' ? 1 : 0) }

    return { ...tally, [approval.kind]: tally[approval.kind] + 1 }
  })
}

// A row the model read unseen; the same row again (a reminder each turn) adds to the last one's count.
async function noteInjected($: EngineInterface, row: Omit<InjectedRow, 'count'>) {
  await update($, injected, list => {
    const recent = list.length - 20
    const same = list.findIndex(
      (one, i) => i >= recent && one.door === row.door && one.name === row.name && one.agent === row.agent && one.text === row.text,
    )
    if (same >= 0) {
      const one = list[same]!

      return [...list.slice(0, same), ...list.slice(same + 1), { ...one, at: row.at, count: one.count + 1 }]
    }

    return [...list, { ...row, count: 1 }].slice(-MAX_INJECTED)
  })
}

const patch = ($: EngineInterface, id: string, change: Partial<WatchEvent>) =>
  update($, events, list => list.map(one => (one.id === id ? { ...one, ...change } : one)))

function changeOf(xy: string): string {
  if (xy === '??') return 'untracked'
  if (xy.includes('D')) return 'deleted'
  if (xy.includes('R')) return 'renamed'
  if (xy.includes('A')) return 'created'
  return 'modified'
}

let gitBusy = false

// Nobody is looking while the pane is hidden: no git processes then. Opening it refreshes at once.
async function refreshGit($: EngineInterface) {
  if (gitBusy || !(await read($, paneShown))) return
  gitBusy = true
  try {
    await refreshGitOnce($)
  } finally {
    gitBusy = false
  }
}

async function refreshGitOnce($: EngineInterface) {
  const cwd = await $.session.cwd().catch(() => undefined)
  if (cwd === undefined) return
  // Every git call passes --no-optional-locks: a plain status refreshes the index and writes it back
  // through index.lock, and a poll holding that lock would fail the agent's own git add or commit.
  // git status names paths from the repository's root; the tree, the session's folder within it.
  const prefix = (
    await $.process.run(['git', '--no-optional-locks', 'rev-parse', '--show-prefix'], { cwd, timeoutMs: 5000 }).catch(() => undefined)
  )?.stdout.trim() ?? ''
  const ran = await $.process
    .run(['git', '--no-optional-locks', '-c', 'core.quotepath=off', 'status', '--porcelain=v1', '-z', '-uall'], { cwd, timeoutMs: 10000 })
    .catch(() => undefined)
  if (ran === undefined || ran.exitCode !== 0) {
    const notGit = 'Not a git repository: showing only files the agent wrote.'
    if ((await read($, gitNote)) !== notGit) await update($, gitNote, () => notGit)
    return
  }
  const seen = new Map<string, string>()
  for (const { path, code } of statusEntries(ran.stdout)) {
    // Changes outside the session's folder are not in its tree.
    if (path.startsWith(prefix)) seen.set(path.slice(prefix.length), changeOf(code))
  }
  if ((await read($, gitNote)) !== '') await update($, gitNote, () => '')
  const listed = await $.process
    .run(['git', '--no-optional-locks', '-c', 'core.quotepath=off', 'ls-files', '-z', '-co', '--exclude-standard'], { cwd, timeoutMs: 15000 })
    .catch(() => undefined)
  if (listed !== undefined && listed.exitCode === 0) {
    const all = drawnPaths(listedPaths(listed.stdout), [...seen.keys(), await read($, fileFocus)]).slice(0, MAX_PATHS)
    const old = await read($, workspace)
    if (all.length !== old.length || all.some((path, i) => path !== old[i])) await update($, workspace, () => all)
  }
  // Lines added and removed per file, staged and unstaged together; '-' for a binary file.
  const counted = await $.process
    .run(['git', '--no-optional-locks', '-c', 'core.quotepath=off', 'diff', '--numstat', '-z', '--relative', 'HEAD'], { cwd, timeoutMs: 10000 })
    .catch(() => undefined)
  const stats = numstatEntries(counted?.stdout ?? '')
  const rows = await read($, files)
  // A file the agent wrote that git does not list stays while it is there. A path recorded while the
  // session's folder was another (the agent's shell moved) points nowhere now, and goes.
  const present = new Set<string>()
  for (const row of rows) {
    if (!row.byAgent || seen.has(row.path)) continue
    const full = isOutside(row.path) ? row.path : `${cwd}/${row.path}`
    if (await $.fs.stat(full).then(() => true, () => false)) present.add(row.path)
  }
  const merged = (() => {
    const byPath = new Map(rows.map(row => [row.path, row]))
    const next: FileRow[] = []
    for (const [path, change] of seen) {
      const old = byPath.get(path)
      next.push({
        path,
        change,
        byAgent: old?.byAgent ?? false,
        edits: old?.edits ?? 0,
        ...(old?.ownAdded === undefined ? {} : { ownAdded: old.ownAdded, ownRemoved: old.ownRemoved ?? 0 }),
        ...stats.get(path),
      })
    }
    // Files the agent wrote that git does not list (ignored, or already committed).
    for (const row of rows) if (row.byAgent && !seen.has(row.path) && present.has(row.path)) next.push(row)

    // The agent's own first, then git's, as many as a tree can show.
    return [...next.filter(row => row.byAgent), ...next.filter(row => !row.byAgent)].slice(0, MAX_CHANGED)
  })()
  if (JSON.stringify(merged) !== JSON.stringify(rows)) await update($, files, () => merged)

  // Nothing written yet this session: show the most recent change git reports. Then keep the
  // focused file's preview current, unless a write is streaming into it.
  let focused = await read($, fileFocus)
  if (focused === '') {
    const first = (await read($, files))[0]?.path ?? ''
    if (first !== '') {
      await update($, fileFocus, () => first)
      focused = first
    }
  }
  if (focused !== '' && (await read($, live)) === null) await loadPreview($, focused)
}

// The workspace paths the Files tree draws: the folders on the way to a changed or focused file
// are open, every other folder closed. One path per closed folder is enough to draw it; an open
// folder needs all of its own. A repository of thousands of files keeps a few dozen.
function drawnPaths(all: string[], opened: string[]): string[] {
  const open = new Set<string>()
  for (const path of opened.filter(Boolean)) {
    const parts = path.split('/')
    for (let i = 1; i < parts.length; i += 1) open.add(parts.slice(0, i).join('/'))
  }
  const shown = new Set<string>()

  return all.filter(path => {
    const parts = path.split('/')
    let depth = 0
    while (depth < parts.length - 1 && open.has(parts.slice(0, depth + 1).join('/'))) depth += 1
    const drawn = parts.slice(0, depth + 1).join('/')
    if (shown.has(drawn)) return false
    shown.add(drawn)

    return true
  })
}

async function relativePath($: EngineInterface, path: string) {
  const root = slashes(await $.session.cwd().catch(() => '')).replace(/\/$/, '')
  const full = slashes(path)

  return full.toLowerCase().startsWith(`${root.toLowerCase()}/`) ? full.slice(root.length + 1) : full
}

// A file's lines added and removed: git's count where git has one, else the agent's own edits'.
function linesOf(row: FileRow | undefined): { added: number; removed: number } | undefined {
  if (row?.added !== undefined) return { added: row.added, removed: row.removed ?? 0 }
  if (row?.ownAdded !== undefined) return { added: row.ownAdded, removed: row.ownRemoved ?? 0 }

  return undefined
}

// The agent's own edits, counted where git cannot count them (a new file, one outside the repo).
async function noteAgentWrite(
  $: EngineInterface,
  path: string,
  existed: boolean,
  delta: { added: number; removed: number },
) {
  const rel = await relativePath($, path)
  await update($, files, rows => {
    const old = rows.find(row => row.path === rel)
    if (old) {
      return rows.map(row =>
        row === old
          ? {
              ...row,
              byAgent: true,
              edits: row.edits + 1,
              ownAdded: (row.ownAdded ?? 0) + delta.added,
              ownRemoved: (row.ownRemoved ?? 0) + delta.removed,
            }
          : row,
      )
    }

    return [
      ...rows,
      {
        path: rel,
        change: existed ? 'modified' : 'created',
        byAgent: true,
        edits: 1,
        ownAdded: delta.added,
        ownRemoved: delta.removed,
      },
    ]
  })
}

type TreeNode = { path: string; name: string; dirs: Map<string, TreeNode>; files: string[] }

/** One row of the Files tab's tree. */
type TreeRow = {
  name: string
  depth: number
  isDir: boolean
  isOpen: boolean
  color: string
  badge: string
  isAgent: boolean
  isFocus: boolean
  added: number
  removed: number
}

const isOutside = (path: string) => /^[A-Za-z]:|^\//.test(path)
const OUTSIDE = '(outside the workspace)'
const SEVERITY = ['deleted', 'created', 'untracked', 'renamed', 'modified']

const partsOf = (path: string) =>
  isOutside(path) ? [OUTSIDE, ...slashes(path).split('/').filter(Boolean)] : path.split('/').filter(Boolean)

// The workspace as a tree that opens itself: the folders holding changes, and the file the agent
// is on, are open; every other folder stays closed. Files outside the workspace sit in a group.
function liveTreeRows(all: string[], changed: FileRow[], focused: string): TreeRow[] {
  const changes = new Map(changed.map(row => [row.path, row]))
  const root: TreeNode = { path: '', name: '', dirs: new Map(), files: [] }
  const paths = new Set([...all.filter(path => !isOutside(path)), ...changes.keys()])
  if (focused !== '') paths.add(focused)
  for (const path of paths) {
    let node = root
    for (const part of partsOf(path).slice(0, -1)) {
      let next = node.dirs.get(part)
      if (next === undefined) {
        next = { path: node.path ? `${node.path}/${part}` : part, name: part, dirs: new Map(), files: [] }
        node.dirs.set(part, next)
      }
      node = next
    }
    node.files.push(path)
  }
  const open = new Set<string>()
  for (const path of [...changes.keys(), focused].filter(Boolean)) {
    const parts = partsOf(path)
    for (let i = 1; i < parts.length; i += 1) open.add(parts.slice(0, i).join('/'))
  }
  const worst = (node: TreeNode): string | undefined => {
    const found = [...node.files.map(path => changes.get(path)?.change), ...[...node.dirs.values()].map(worst)].filter(
      (c): c is string => c !== undefined,
    )

    return SEVERITY.find(change => found.includes(change))
  }
  const lines = (node: TreeNode): { added: number; removed: number } =>
    [
      ...node.files.map(path => linesOf(changes.get(path)) ?? { added: 0, removed: 0 }),
      ...[...node.dirs.values()].map(lines),
    ].reduce((sum, one) => ({ added: sum.added + one.added, removed: sum.removed + one.removed }), { added: 0, removed: 0 })
  // Outside the workspace, a chain of folders holding one folder each is one short row.
  const fold = (dir: TreeNode): { node: TreeNode; name: string } => {
    const names = [dir.name]
    let node = dir
    while (node.files.length === 0 && node.dirs.size === 1) {
      node = [...node.dirs.values()][0]!
      names.push(node.name)
    }

    return { node, name: names.length > 3 ? `${names[0]}/…/${names.slice(-2).join('/')}` : names.join('/') }
  }
  const byName = (a: string, b: string) => a.localeCompare(b, undefined, { sensitivity: 'base' })
  const rows: TreeRow[] = []
  const walk = (node: TreeNode, depth: number, isFolded: boolean) => {
    for (const found of [...node.dirs.values()].sort((a, b) => byName(a.name, b.name))) {
      const isGroup = found.name === OUTSIDE
      const { node: dir, name } = isFolded ? fold(found) : { node: found, name: found.name }
      const isOpen = open.has(dir.path)
      const change = worst(dir)
      const counted = change ? lines(dir) : { added: 0, removed: 0 }
      rows.push({
        name,
        depth,
        isDir: true,
        isOpen,
        color: change ? CHANGE_STYLE[change]?.color ?? '' : '',
        badge: change ? '●' : '',
        isAgent: false,
        isFocus: false,
        added: counted.added,
        removed: counted.removed,
      })
      if (isOpen) walk(dir, depth + 1, isFolded || isGroup)
    }
    for (const path of [...node.files].sort((a, b) => byName(a, b))) {
      const row = changes.get(path)
      const style = row ? CHANGE_STYLE[row.change] : undefined
      rows.push({
        name: slashes(path).split('/').pop() ?? path,
        depth,
        isDir: false,
        isOpen: false,
        color: style?.color ?? '',
        badge: style?.mark ?? '',
        isAgent: row?.byAgent ?? false,
        isFocus: path === focused,
        added: linesOf(row)?.added ?? 0,
        removed: linesOf(row)?.removed ?? 0,
      })
    }
  }
  walk(root, 0, false)

  return rows.slice(0, 3000)
}

// The last edit made to each file, for the files git cannot diff (outside the workspace, ignored).
// A reload forgets them; git's diff covers the rest.
const lastEdits = new Map<string, { tool: string; oldText: string; newText: string }>()

// The last few files' edits only: each may hold a Write's whole content.
function rememberEdit(path: string, edit: { tool: string; oldText: string; newText: string }) {
  lastEdits.delete(path)
  lastEdits.set(path, edit)
  while (lastEdits.size > 20) lastEdits.delete(lastEdits.keys().next().value as string)
}

const readText = ($: EngineInterface, path: string) => $.fs.read(path).then(normalise, () => null)

// The focused file's changes once a write has landed: git's diff, a new file whole, the last
// edit found again in the file, or the file's text when none of those applies.
async function loadPreview($: EngineInterface, path: string) {
  if (path === '') return
  const row = (await read($, files)).find(one => one.path === path)
  const text = await readText($, path)
  const isNew = row?.change === 'untracked' || row?.change === 'created'
  let diff = ''
  if (row !== undefined && !isNew && !isOutside(path)) {
    const cwd = await $.session.cwd().catch(() => undefined)
    const ran = await $.process
      .run(['git', '--no-optional-locks', '-c', 'core.quotepath=off', 'diff', '-U4', 'HEAD', '--', path], { cwd, timeoutMs: 10000 })
      .catch(() => undefined)
    const out = ran?.stdout ?? ''
    diff = out.includes('@@') ? out.slice(out.indexOf('@@')).trimEnd() : ''
  }
  const edit = lastEdits.get(path)
  if (diff === '' && edit !== undefined) diff = doneHunk(edit.tool, edit.oldText, edit.newText, text)
  if (diff === '' && isNew && text !== null) diff = doneHunk('Write', '', '', text)
  // A new Markdown file reads best rendered, as the Files browser shows it; an edit to one stays a diff.
  if (isNew && isMarkdown(path) && text !== null && edit?.tool !== 'Edit') diff = ''
  const both = linesOf(row)
  const counts = both && both.added + both.removed > 0 ? ` +${both.added} −${both.removed}` : ''
  const note = `${row?.change ?? 'unchanged'}${counts}`
  const shown =
    diff !== '' && diff.length <= MAX_PREVIEW
      ? { kind: 'diff' as const, text: diff }
      : { kind: 'file' as const, text: text === null ? '(cannot read the file)' : cut(text, MAX_PREVIEW) }
  await update($, preview, () => ({ path, ...shown, note, at: Date.now() }))
}

// A file tool call the model is still writing: what it has written so far, as a hunk.
type Writing = { tool: string; json: string; flushed: number; path?: string; rel?: string; before?: string | null }

async function showWriting($: EngineInterface, w: Writing, agent: string) {
  w.flushed = Date.now()
  const fields = scanFields(w.json)
  const target = fields[FILE_TOOLS[w.tool] ?? 'file_path']
  if (!target?.isDone) return
  if (w.rel === undefined) {
    w.path = target.text
    w.rel = await relativePath($, target.text)
    w.before = await readText($, target.text)
    await update($, fileFocus, () => w.rel ?? '')
  }
  const rel = w.rel
  const diff = writingHunk(w.tool, fields, w.before ?? null)
  await update($, live, () => ({ path: rel, tool: w.tool, agent, diff: cut(diff, MAX_PREVIEW), at: Date.now() }))
}

const CHANGE_STYLE: Record<string, { mark: string; color: string }> = {
  created: { mark: 'A', color: 'success' },
  untracked: { mark: '?', color: 'success' },
  modified: { mark: 'M', color: 'warning' },
  renamed: { mark: 'R', color: 'suggestion' },
  deleted: { mark: 'D', color: 'error' },
}

// Reads from the engine whether the pane is on screen (it may wait, unseated, in a narrow window).
async function syncPane($: EngineInterface) {
  const pane = (await $.ui.panes().catch(() => [])).find(one => one.id === PANE)
  const isShown = pane?.isShown ?? false
  if ((await read($, paneShown)) !== isShown) await update($, paneShown, () => isShown)
}

// The open the agent's work makes, at most one at a time: main and a subagent can step together.
let opening: Promise<void> | undefined

// Opens the pane for the agent's work only when it isn't open at all. `paneShown` says whether it is
// in front, so an open pane behind another one, or one waiting undrawn in a narrow terminal, counts
// as open here: it is never reopened, and never pulled in front of what the person is reading.
function openForWork($: EngineInterface): Promise<void> {
  if (opening !== undefined) return opening
  opening = (async () => {
    if ((await read($, paneShown)) || (await read($, dismissed))) return
    const isOpen = (await $.ui.panes().catch(() => [])).some(pane => pane.id === PANE)
    if (!isOpen) await openPane($)
  })().finally(() => {
    opening = undefined
  })

  return opening
}

// The person asked for the pane (the button, /agent-watch): it opens, and opens by itself again.
async function openByPerson($: EngineInterface) {
  await update($, dismissed, () => false)
  await openPane($)
}

async function openPane($: EngineInterface) {
  await $.ui.open({ id: PANE, title: TITLE })
  await syncPane($)
  void refreshGit($).catch(() => undefined)
}

// A session can hold more than one copy of this mod (a draft beside the installed folder, a copy
// loaded before a reload); were each to draw, the pane would flip between them. The copy loaded
// last claims the session as soon as one of its hooks runs; an older copy then passes everything on.
const INSTANCE = Date.now() + Math.random()
const owner = atom({ plugin: 'agent-watch', key: 'owner' } as const, 0)
const claim = async ($: EngineInterface) => {
  if ((await read($, owner).catch(() => 0)) < INSTANCE) await update($, owner, current => Math.max(current, INSTANCE))
}
const isStale = async ($: EngineInterface) => (await read($, owner).catch(() => 0)) > INSTANCE

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    await $.command.register({
      name: 'agent-watch',
      description: 'Open the live pane: thinking, tool calls, terminal commands and file changes',
    })
    // An older copy's timers stand down once a newer copy holds the session.
    const unlessStale = (work: () => Promise<unknown>) => () =>
      void isStale($)
        .then(stale => (stale ? undefined : work()))
        .catch(() => undefined)
    $.clock.every(GIT_EVERY_MS, unlessStale(() => refreshGit($)))
    $.clock.every(
      AGENTS_EVERY_MS,
      unlessStale(() => Promise.all([claim($), refreshAgents($), refreshSession($), syncPane($)])),
    )
    $.clock.every(CONTEXT_EVERY_MS, unlessStale(() => refreshContext($)))
    void refreshContext($)
    await claim($)
    await slimStoredEvents($)
    void refreshSession($)
    void refreshGit($)
    void refreshAgents($)
    // No pane yet: the button above the prompt stands in until the agent starts working.
    void syncPane($)

    return next(e)
  })

  on('command.run', { command: 'agent-watch' }, async $ => {
    await openByPerson($)

    return { text: 'Agent watch pane opened.' }
  })

  // The person closing the pane brings the button above the prompt back. (Its own opens go
  // through openPane: a plugin's hooks do not see the plugin's own $.ui.open.)
  on('ui.close', async ($, e, next) => {
    const closed = await next(e)
    if (e.id === PANE) {
      await update($, paneShown, () => false)
      // Closed by the person (not the session ending): the agent's next turns leave it closed.
      if (e.origin.kind === 'person') await update($, dismissed, () => true)
    }

    return closed
  })

  // A click that only brings the focus ring to a tab, an agent or the open button (the desktop's
  // first click into the pane) acts as the press would: selecting is safe to do twice, so a
  // press that does land as well changes nothing. Clear is left to its press.
  on('ui.focus', async ($, e, next) => {
    if (await isStale($)) return next(e)
    await claim($)
    const moved = await next(e)
    // The person's move names the element; a `$.ui.focus` call names it `key`.
    const named = e as { element?: string; key?: string }
    const key = named.element ?? named.key ?? ''
    const tabId = key.startsWith('tab-') ? TABS.find(t => `tab-${t.id}` === key)?.id : undefined
    if (tabId !== undefined) await update($, tab, () => tabId)
    else if (key.startsWith('agent-')) await update($, focus, () => key.slice('agent-'.length))
    // Opening on focus, not only on press: on the desktop the first click on the band only focuses
    // the button. Tabbing onto it opens the pane too, which is meant.
    else if (key === 'open-agent-watch') await openByPerson($)

    return moved
  })

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    if (await isStale($)) return next(e)
    if (e.props.hasSurvey || (await read($, paneShown))) return next(e)
    const { Box, Button, Text } = $.ui.resolve(e)
    const list = await read($, events).catch((): WatchEvent[] => [])
    const running = list.filter(ev => ev.status === 'running')
    const live = (await read($, agents)).filter(a => ACTIVE.has(a.status)).length
    // The newest thing any agent did (a subagent's too, though the Timeline shows one agent at a
    // time), so the closed pane still says what is happening. A tool still running is named by the
    // counts already: the newest row is then the latest thing that isn't one.
    const last = list.findLast(ev => !(ev.kind === 'tool' && ev.status === 'running'))
    const words = last === undefined ? undefined : timelineWords(last)

    // The counts give up width only once the newest row has none left; both cut off at the end.
    return (
      <Box flexDirection="row" gap={1} alignItems="center">
        <Button
          key="open-agent-watch"
          label="Agent watch"
          variant="primary"
          onPress={() => openByPerson($)}
        />
        <Box flexShrink={1}>
          <Text dimColor wrap="truncate-end">
            {running.length > 0 ? `● ${running.map(ev => shortTool(ev.tool)).join(', ')}` : 'Idle'}
            {live > 0 ? ` · ${live} subagent${live > 1 ? 's' : ''}` : ''}
            {` · ${list.filter(ev => ev.kind === 'tool').length} tool calls`}
            {words === undefined ? '' : ' ·'}
          </Text>
        </Box>
        {last === undefined || words === undefined ? null : (
          <Box key="band-last" flexGrow={1} flexShrink={1000}>
            <Text wrap="truncate-end" dimColor>
              <Text bold>{last.agentId ? `↳ ${words.action}` : words.action}</Text>
              {words.about ? ` ${words.about}` : ''}
            </Text>
          </Box>
        )}
      </Box>
    )
  })

  // A subagent gets its tab as it starts, not at the next poll or its own first step.
  on('agent.spawn', async ($, e, next) => {
    const started = await next(e)
    if (started.agentId === undefined || (await isStale($))) return started
    const { agentId } = started
    labels.set(agentId, `↳ ${e.subagentType}: ${clip(e.description, 30)}`)
    await patchAgent($, agentId, row => ({
      ...row,
      type: e.subagentType,
      description: cut(e.description, MAX_NOTE),
      parentId: e.parentAgentId,
    }))

    return started
  })

  // Thinking and reply text, streamed as the model writes them.
  on('turn.step', async function* ($, e, next) {
    await claim($)
    if (await isStale($)) {
      for await (const chunk of next(e)) yield chunk

      return
    }
    // The agent is working: the pane opens by itself, unless the person closed it.
    void openForWork($).catch(() => undefined)
    const agent = await agentLabel($, e.agentId)
    if (e.effort !== undefined) efforts.set(e.agentId ?? 'main', String(e.effort))
    models.set(e.agentId ?? 'main', e.model)
    const blocks = new Map<number, { id: string; kind: string; text: string; flushed: number; started: number; last: number }>()
    const writes = new Map<number, Writing>()

    // The block's text so far, and how long it has streamed: the Timeline's timespan for it.
    const flush = async (index: number) => {
      const block = blocks.get(index)
      if (block === undefined) return
      block.flushed = Date.now()
      await patch($, block.id, { text: block.text.slice(0, block.kind === 'thinking' ? MAX_THINKING : MAX_TEXT), ms: block.last - block.started })
    }

    const stream = next(e)
    for await (const chunk of stream) {
      if (chunk.kind === 'thinking' || chunk.kind === 'text') {
        let block = blocks.get(chunk.index)
        if (block === undefined) {
          const now = Date.now()
          block = { id: `${e.turnId}:${e.index}:${chunk.index}:${e.agentId ?? 'main'}`, kind: chunk.kind, text: '', flushed: 0, started: now, last: now }
          blocks.set(chunk.index, block)
          await push($, { id: block.id, at: Date.now(), agent, agentId: e.agentId, model: models.get(e.agentId ?? 'main'), effort: efforts.get(e.agentId ?? 'main'), kind: chunk.kind, text: '' })
          if (e.agentId !== undefined) {
            const doing = chunk.kind === 'thinking' ? 'thinking…' : 'writing…'
            await patchAgent($, e.agentId, row => ({ ...row, status: 'running', lastAction: doing }))
          }
        }
        block.text += chunk.text
        block.last = Date.now()
        if (block.last - block.flushed > FLUSH_MS) await flush(chunk.index)
      } else if (chunk.kind === 'tool' && FILE_TOOLS[chunk.name] !== undefined) {
        writes.set(chunk.index, { tool: chunk.name, json: '', flushed: 0 })
      } else if (chunk.kind === 'input') {
        const w = writes.get(chunk.index)
        if (w !== undefined) {
          w.json += chunk.json
          if (Date.now() - w.flushed > FLUSH_MS) await showWriting($, w, agent)
        }
      }
      yield chunk
    }
    for (const index of blocks.keys()) await flush(index)
    for (const w of writes.values()) await showWriting($, w, agent)

    const response = await stream.result
    if (response.usage) await addStep($, e.agentId ?? 'main', response.usage, e.effort)
  })

  // Every tool call: name, arguments, how it went, and what it returned.
  on('tool.call', async ($, e, next) => {
    await claim($)
    if (await isStale($)) return next(e)
    const { tool, tool_use_id, agentId, consent, ...args } = e as unknown as Record<string, unknown> & {
      tool: string
      tool_use_id?: string
      agentId?: string
      consent?: string
    }
    const id = tool_use_id ?? `${tool}:${Date.now()}`
    const started = Date.now()
    const isTerminal = TERMINAL_TOOLS.test(tool)
    const command = args.command ?? args.text ?? args.shell_id ?? args.bash_id
    const summary = summaryOf(tool, args)
    const reference = referenceOf(tool, args)
    await push($, {
      id,
      at: started,
      agent: await agentLabel($, agentId),
      agentId,
      model: models.get(agentId ?? 'main'),
      effort: efforts.get(agentId ?? 'main'),
      kind: 'tool',
      tool,
      summary,
      isTerminal,
      terminal: terminalOf(tool, args),
      refKind: reference?.kind,
      reference: reference?.name === undefined ? undefined : cut(reference.name, MAX_NOTE),
      command: isTerminal ? cut(String(command ?? ''), 4000) : undefined,
      note: isTerminal && typeof args.description === 'string' ? cut(args.description, MAX_NOTE) : undefined,
      status: 'running',
    })
    // A call that reaches past the session goes on the Audit tab too, where it stays longer.
    const outward = outwardOf(tool, args)
    if (outward !== undefined) {
      const action: AuditAction = { id, at: started, agent: await agentLabel($, agentId), agentId, tool, ...outward, status: 'running' }
      await update($, actions, list => [...list, action].slice(-MAX_ACTIONS))
    }

    if (agentId !== undefined) {
      await patchAgent($, agentId, row => ({
        ...row,
        status: 'running',
        toolCalls: row.toolCalls + 1,
        lastAction: cut(`${tool} ${summary}`.trim(), 120),
      }))
    }

    const pathKey = FILE_TOOLS[tool]
    const path = pathKey ? args[pathKey] : undefined
    const existed =
      typeof path === 'string' ? await $.fs.stat(path).then(() => true, () => false) : false
    // What a Write replaces, to count the lines it changes.
    const replaced = typeof path === 'string' && tool === 'Write' && existed ? await readText($, path) : null
    const rel = typeof path === 'string' ? await relativePath($, path) : undefined
    if (typeof path === 'string' && rel !== undefined) {
      // Streamed, the live view is already showing it; else (a call no stream wrote) show it now.
      await update($, fileFocus, () => rel)
      if ((await read($, live))?.path !== rel) {
        const diff = writingHunk(tool, fieldsOf(args), await readText($, path))
        const agent = await agentLabel($, agentId)
        await update($, live, () => ({ path: rel, tool, agent, diff: cut(diff, MAX_PREVIEW), at: Date.now() }))
      }
    }

    const ran = await next(e)

    const status: WatchStatus = ran.deny !== undefined ? 'denied' : ran.isError ? 'error' : 'ok'
    const output = ran.deny ?? ran.text ?? ''
    // A background shell or a new terminal tab is named by what the call answered.
    const opened =
      args.run_in_background === true && (tool === 'Bash' || tool === 'PowerShell')
        ? /\b(?:ID|id)\b[:\s]+([A-Za-z0-9_-]+)/.exec(output)?.[1]
        : tool === 'mcp__terminal__open_terminal_tab'
          ? /tab[_ ]?id["'\s:=]+([A-Za-z0-9_-]+)/i.exec(output)?.[1]
          : undefined
    const terminal = opened === undefined ? {} : { terminal: tool.startsWith('mcp__') ? `tab:${opened}` : `bg:${opened}` }
    // How it was let run: its permission check's verdict, and for a question, whether it then ran.
    const checked = checks.get(id)
    checks.delete(id)
    const approval: Approval | undefined =
      checked?.kind === 'asked'
        ? { ...checked, outcome: status === 'denied' ? 'refused' : 'approved' }
        : checked ?? (ran.deny !== undefined ? { kind: 'denied', detail: cut(ran.deny, MAX_NOTE) } : undefined)
    await patch($, id, {
      status,
      ms: Date.now() - started,
      output: tail(output, MAX_OUTPUT),
      ...terminal,
      ...(rel === undefined ? {} : { file: rel }),
      ...(approval === undefined ? {} : { approval }),
    })
    if (outward !== undefined) {
      await update($, actions, list => list.map(one => (one.id === id ? { ...one, status, approval } : one)))
    }
    if (approval !== undefined) await countApproval($, approval)
    if (typeof path === 'string' && rel !== undefined) {
      if (status === 'ok') {
        const newText = args.new_string ?? args.content ?? args.new_source
        rememberEdit(rel, {
          tool,
          oldText: typeof args.old_string === 'string' ? cut(args.old_string, MAX_PREVIEW) : '',
          newText: typeof newText === 'string' ? cut(newText, MAX_PREVIEW) : '',
        })
        const delta =
          tool === 'Edit'
            ? lineDelta(String(args.old_string ?? ''), String(args.new_string ?? ''))
            : tool === 'Write'
              ? lineDelta(replaced ?? '', String(args.content ?? ''))
              : { added: 0, removed: 0 }
        await noteAgentWrite($, path, existed, delta)
      }
      await update($, live, current => (current?.path === rel ? null : current))
      void loadPreview($, rel).catch(() => undefined)
    }

    return ran
  }).catch(($, e, next) => next(e)) // only watches: a fault here never blocks a tool

  // The engine's verdict on each call (a settings rule, a hook, the mode, a question, a refusal), kept
  // for the call's tool.call to stamp. Only observes: the verdict goes on as it came.
  on('tool.check', async ($, e, next) => {
    const verdict = await next(e)
    if (e.tool_use_id !== undefined && !(await isStale($))) rememberCheck(e.tool_use_id, approvalOf(verdict))

    return verdict
  }).catch(($, e, next) => next(e))

  // What the model reads that the chat does not show: a settings hook's output, reminders and other
  // attachments, deliveries from other sessions or tasks, compactions, notices.
  on('session.append', async ($, e, next) => {
    const stored = await next(e)
    if (!UNSEEN_DOORS.has(e.door) || (await isStale($))) return stored
    const text = rowText(e.message.content as { type: string; text?: unknown; content?: unknown }[])
    if (text === '' && e.message.name === undefined) return stored
    await noteInjected($, {
      id: e.uuid,
      at: Date.now(),
      agent: await agentLabel($, e.agentId),
      door: e.door,
      name: e.message.name,
      origin: originLabel(e.origin),
      text: cut(text, MAX_INJECTED_TEXT),
      isSent: e.message.role !== undefined,
    })

    return stored
  }).catch(($, e, next) => next(e))

  // A compaction: from then on the agent works from a summary. How much it held before, and after.
  on('session.compact', async ($, e, next) => {
    const done = await next(e)
    if (e.trigger === 'precompute' || done.messages === undefined || (await isStale($))) return done
    const before = done.tokensBefore === undefined ? '?' : tokens(done.tokensBefore)
    const after = done.tokensAfter === undefined ? '?' : tokens(done.tokensAfter)
    await noteInjected($, {
      id: `compact:${Date.now()}`,
      at: Date.now(),
      agent: await agentLabel($, e.agentId),
      door: 'compaction',
      name: e.trigger,
      origin: 'engine',
      text: `Conversation compacted (${e.trigger}): ${before} → ${after} tokens. The agent works from a summary from here on.`,
      isSent: true,
    })

    return done
  }).catch(($, e, next) => next(e))

  // A subagent's run ends in its own turn.complete: record how it ended and what it said.
  on('turn.complete', async ($, e, next) => {
    await claim($)
    if (await isStale($)) return next(e)
    // A write whose tool never ran (output cut off, the turn interrupted) stops showing as live.
    if ((await read($, live)) !== null) await update($, live, () => null)
    const isOpen = (ev: WatchEvent) => ev.status === 'running' && ev.kind === 'tool' && ev.agentId === e.agentId
    if ((await read($, events)).some(isOpen)) {
      await update($, events, list =>
        list.map(ev => (isOpen(ev) ? { ...ev, status: 'error' as const, output: '(no result seen)' } : ev)),
      )
    }
    if (e.agentId !== undefined) {
      const status = e.isAborted ? 'killed' : e.reason === 'answer' ? 'completed' : 'failed'
      await patchAgent($, e.agentId, row => ({
        ...row,
        status,
        answer: cut(e.answer, 2000),
        durationMs: e.durationMs,
        lastAction: status,
      }))
    }

    return next(e)
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e, next) => {
    if (await isStale($)) return next(e)
    const { Box, Text, Button, Code, Markdown } = $.ui.resolve(e)
    const stored = await read($, tab)
    const current: WatchTab = TABS.some(t => t.id === stored) ? stored : 'agents'
    const list = await read($, events)
    const rows = await read($, files)
    const note = await read($, gitNote)
    const subagents = await read($, agents)
    const focused = await read($, focus)
    const usage = await read($, loops)
    const totals = await read($, session)
    const width = Math.max(30, e.props.bodyColumns ?? e.viewport?.columns ?? 100)
    // The Agents tab shows one agent: the picked subagent, else main.
    const isShown = (ev: WatchEvent) =>
      subagents.some(a => a.id === focused) ? ev.agentId === focused : ev.agentId === undefined

    // The Timeline: one row per thing that happened, in four columns: when, what, about what, how long.
    const timelineLine = (ev: WatchEvent) => {
      const { action, about } = timelineWords(ev)
      const span = ev.status === 'running' ? 'running' : ev.ms !== undefined ? seconds(ev.ms) : ''
      const failed = ev.status === 'error' || ev.status === 'denied'
      // The action's colour says what kind of thing it is, in the theme's own colours; red when it failed.
      const actionColor = (): string => {
        if (failed) return 'error'
        if (ev.kind === 'thinking') return 'subtle'
        if (ev.kind === 'text') return 'claude'
        const tool = ev.tool ?? ''
        if (ev.isTerminal) return 'bashBorder'
        if (/^(Edit|Write|NotebookEdit|MultiEdit)$/.test(tool)) return 'success'
        if (/^(Read|Grep|Glob|WebFetch|WebSearch|ToolSearch|LS)$/.test(tool)) return 'suggestion'
        if (/^(Agent|Task|Skill)$/.test(tool)) return 'merged'
        if (tool.startsWith('mcp__')) return 'permission'

        return 'text'
      }

      return (
        <Box flexDirection="row" gap={2}>
          <Box width={8} flexShrink={0}>
            <Text dimColor>{clock(ev.at)}</Text>
          </Box>
          <Box width={12} flexShrink={0}>
            <Text
              wrap="truncate-end"
              bold={ev.kind === 'tool'}
              italic={ev.kind === 'thinking'}
              color={actionColor()}
            >
              {ev.agentId ? `↳ ${action}` : action}
            </Text>
          </Box>
          <Box flexGrow={1} flexShrink={1}>
            <Text wrap="truncate-end" dimColor={ev.kind === 'thinking'}>
              {about}
            </Text>
          </Box>
          <Box width={26} flexShrink={0} justifyContent="flex-end">
            <Text dimColor wrap="truncate-start">
              {[shortModel(ev.model), effortLabel(ev.effort)].filter(Boolean).join(' ')}
              {span ? '  ' : ''}
              <Text color={ev.status === 'running' ? 'claude' : undefined}>{span}</Text>
            </Text>
          </Box>
        </Box>
      )
    }

    const usageText = (key: string) => {
      const u = usage[key]
      if (u === undefined) return 'no model requests seen yet'
      const percent = Math.round((u.context / u.window) * 100)

      return `${u.model}${u.effort ? ` · ${effortLabel(u.effort)}` : ''} · ${dollars(u.usd)} est. · context ${tokens(u.context)}/${tokens(u.window)} (${percent}%) · ${u.requests} requests · in ${tokens(u.input)} · cache ${tokens(u.cacheRead)} read ${tokens(u.cacheWrite)} written · out ${tokens(u.output)}`
    }

    const everything = [...list].reverse()
    const newest = everything.filter(isShown)
    let body
    if (current === 'agents') {
      // In the order they started: a tab stays where it is.
      const sorted = [...subagents].sort((a, b) => (a.n ?? 0) - (b.n ?? 0) || a.startedAt - b.startedAt)
      // One agent at a time: main unless a subagent was picked (and is still listed).
      const picked: 'main' | AgentRow = sorted.find(a => a.id === focused) ?? 'main'
      const statusColor = (status: string) =>
        ACTIVE.has(status) ? 'claude' : status === 'completed' || status === 'idle' ? 'success' : 'error'
      const mainCard = (
        <Box key="card-main" flexDirection="column" marginBottom={1}>
          <Text wrap="truncate-end">
            <Text color="claude">● </Text>
            <Text bold>main</Text>
            <Text dimColor>
              {' '}
              · session {dollars(totals.usd)}
              {totals.percent !== undefined
                ? ` · context ${tokens(totals.contextTokens ?? 0)}/${tokens(totals.window ?? 0)} (${totals.percent}%)`
                : ''}
            </Text>
          </Text>
          <Box flexDirection="row">
            <Text dimColor>{'  ⎿  '}</Text>
            <Text dimColor wrap="wrap">
              {usageText('main')}
            </Text>
          </Box>
        </Box>
      )
      const agentCard = (a: AgentRow, isFull: boolean) => (
        <Box key={`card-${a.id}`} flexDirection="column" marginBottom={1}>
          <Text wrap="truncate-end">
            <Text color={statusColor(a.status)}>● </Text>
            <Text bold>{tabName(a)} · {a.type}</Text>
            <Text>({a.description})</Text>
            <Text dimColor>
              {' '}
              · {a.status} · {a.toolCalls} tool calls
              {a.durationMs !== undefined ? ` · ${seconds(a.durationMs)}` : ''}
            </Text>
          </Text>
          <Box flexDirection="row">
            <Text dimColor>{'  ⎿  '}</Text>
            <Box flexDirection="column" flexShrink={1}>
              <Text dimColor wrap="wrap">
                {usageText(a.id)}
              </Text>
              {a.lastAction && ACTIVE.has(a.status) ? (
                <Text color="claude" wrap="truncate-end">
                  {a.lastAction}
                </Text>
              ) : null}
              {a.answer ? (
                <Text dimColor wrap="wrap">
                  {cut(a.answer, isFull ? 3000 : 240)}
                </Text>
              ) : null}
            </Box>
          </Box>
        </Box>
      )
      const pick = (id: string) => () => update($, focus, () => id)
      // What the chat does not show, for the agent picked: the terminals it used, the MCP servers it
      // called, the rules and memory in its context, the skills and tools it reached for, what it looked up.
      const calls = newest.filter(ev => ev.kind === 'tool')
      const ctx = await read($, contextInfo)
      const cwd = slashes(await $.session.cwd().catch(() => '')).replace(/\/$/, '')
      const shortPath = (path: string) => {
        const p = slashes(path)
        if (cwd !== '' && p.toLowerCase().startsWith(`${cwd.toLowerCase()}/`)) return p.slice(cwd.length + 1)

        return p.replace(/^[A-Za-z]:\/Users\/[^/]+/, '~')
      }
      const counted = <T,>(items: T[], keyOf: (item: T) => string) => {
        const map = new Map<string, T[]>()
        for (const item of items) map.set(keyOf(item), [...(map.get(keyOf(item)) ?? []), item])

        return [...map.entries()].sort((a, b) => b[1].length - a[1].length)
      }
      const heading = (title: string, detail: string) => {

        return (
          <Box marginTop={1}>
            <Text wrap="truncate-end">
              <Text bold>{title}</Text>
              <Text dimColor> · {detail}</Text>
            </Text>
          </Box>
        )
      }
      const markOf = (ev: WatchEvent) =>
        ev.status === 'running' ? <Text color="claude"> running</Text> : (
          <Text color={ev.status === 'ok' ? 'success' : 'error'}>
            {' '}
            {ev.status === 'ok' ? '✓' : '✗'} <Text dimColor>{seconds(ev.ms)}</Text>
          </Text>
        )

      // Terminals: each shell the agent typed into, its commands in order, the tail of what they printed.
      // Where a call sits in `calls` (newest first): 0 is the newest.
      const position = new Map(calls.map((ev, i) => [ev.id, i]))
      const order = (ev?: WatchEvent) => (ev === undefined ? Infinity : position.get(ev.id) ?? Infinity)
      const byTerminal = counted([...calls].reverse().filter(ev => ev.isTerminal && ev.terminal !== undefined), ev => ev.terminal ?? '')
        // Newest-used first, by the order the commands ran: several can share one millisecond.
        .sort((a, b) => order(a[1][a[1].length - 1]) - order(b[1][b[1].length - 1]))
      const terminalTitle = (key: string) =>
        key === 'shell:bash'
          ? 'Bash'
          : key === 'shell:powershell'
            ? 'PowerShell'
            : key.startsWith('bg:')
              ? `Background shell ${key.slice(3)}`
              : key === 'tab:0'
                ? 'Terminal panel'
                : `Terminal tab ${key.slice(4)}`
      // As the shell itself shows it: its prompt and the command typed, then what it printed.
      const promptOf = (key: string) => {
        if (key === 'shell:powershell') return `PS ${cwd.replace(/\//g, '\\')}> `
        const unix = cwd.replace(/^([A-Za-z]):/, (_, drive: string) => `/${drive.toLowerCase()}`).replace(/^\/c\/Users\/[^/]+/i, '~')

        return `${unix || '~'} $ `
      }
      const termLines = (key: string) => (ev: WatchEvent): TermLine[] => {
        const failed = ev.status === 'error' || ev.status === 'denied'
        const prompt = promptOf(key)
        const lines: TermLine[] = []
        // Reading a background shell's output types nothing: only what it printed shows.
        if (ev.tool === 'KillShell') lines.push({ t: '^C', d: true })
        else if (ev.tool !== 'BashOutput') {
          const all = (ev.command ?? '').split(/\r?\n/)
          const typed = all.length > 40 ? [...all.slice(0, 40), `… +${all.length - 40} lines`] : all
          typed.forEach((line, i) =>
            lines.push({ p: i === 0 ? prompt : ev.tool === 'PowerShell' ? '>> ' : '> ', pc: 'success', t: line }),
          )
        }
        // Output kept from its end starts mid-line: that partial first line goes.
        const printed = (ev.output ?? '').split(/\r?\n/)
        if (printed[0]?.startsWith('…')) printed.shift()
        for (const line of printed) {
          if (line.trim() !== '') lines.push({ t: line, c: failed ? 'error' : undefined })
        }

        return lines
      }
      const terminalBox = (key: string, list: WatchEvent[]) => {
        // Newest commands first into the budget, then drawn oldest to newest as a terminal reads.
        const fitted = withinBudget([...list].reverse().map(termLines(key)), 8_000)
        // The newest command always shows, however much it printed.
        const commands = fitted.kept.length > 0 ? fitted.kept.reverse() : [...list].slice(-1).map(termLines(key))
        const isRunning = list[list.length - 1]?.status === 'running'
        const cursor: TermLine = isRunning ? { t: '█', c: 'claude' } : { p: promptOf(key), pc: 'success', t: '█', d: true }
        // A live tail of whole commands, in a box of fixed height. Older commands are on the Timeline.
        const shown = fitCommands(commands, cursor, Math.max(20, width - 8), TERMINAL_ROWS)

        return (
          <Box key={`term-${key}`} flexDirection="column" borderStyle="round" borderColor="bashBorder" paddingX={1}>
            <Text wrap="truncate-end">
              <Text color="bashBorder" bold>
                {terminalTitle(key)}
              </Text>
              <Text dimColor>
                {' '}
                · {list.length} command{list.length === 1 ? '' : 's'}
              </Text>
            </Text>
            <Box flexDirection="column" height={TERMINAL_ROWS}>
              {shown.map(row => (
                <Text wrap="truncate-end">
                  {row.prefix ? <Text color={row.line.pc}>{row.prefix}</Text> : null}
                  <Text color={row.line.c} bold={row.line.b} dimColor={row.line.d} italic={row.line.i}>
                    {row.text}
                  </Text>
                  {row.last && row.line.s ? <Text dimColor>{row.line.s}</Text> : null}
                </Text>
              ))}
            </Box>
          </Box>
        )
      }
      const terminalsBlock = (
        <Box flexDirection="column">
          {heading('Terminals', `${byTerminal.length} used`)}
          <Box flexDirection="column" gap={1}>
            {byTerminal.slice(0, MAX_TERMINALS).map(([key, list]) => terminalBox(key, list))}
          </Box>
          {byTerminal.length > MAX_TERMINALS ? (
            <Text dimColor>… {byTerminal.length - MAX_TERMINALS} older terminals not shown</Text>
          ) : null}
        </Box>
      )

      // Thinking: only what the agent is reasoning now, its latest block. Its replies are the chat's.
      const thoughts = newest.filter(ev => ev.kind === 'thinking')
      // The newest block, shared or not: an older block with text would sit there stale.
      const latest = thoughts[0]
      const isNow = latest !== undefined && newest[0]?.id === latest.id
      const hasText = (latest?.text ?? '').trim() !== ''
      const thinkingBlock = (
        <Box flexDirection="column">
          {heading(
            'Thinking',
            latest === undefined
              ? 'none yet'
              : [isNow ? 'now' : '', clock(latest.at), latest.ms !== undefined ? seconds(latest.ms) : '', effortLabel(latest.effort) ?? '']
                  .filter(Boolean)
                  .join(' · '),
          )}
          {hasText ? (
            <Text italic wrap="wrap">
              {latest?.text}
              {(latest?.text ?? '').length >= MAX_THINKING ? ' …' : ''}
            </Text>
          ) : (
            <Text dimColor wrap="wrap">
              The model did not share this block's text. Sessions started with showThinkingSummaries on show a summary here.
            </Text>
          )}
        </Box>
      )

      // File changes: each file this agent wrote, how, and by how much against HEAD.
      const byFile = counted(calls.filter(ev => ev.file !== undefined), ev => ev.file ?? '')
      const fileRows = withinBudget(
        byFile.map(([path, list]) => {
          const row = rows.find(r => r.path === path)
          const style = CHANGE_STYLE[row?.change ?? 'modified'] ?? { mark: 'M', color: 'warning' }
          const failed = list.filter(ev => ev.status === 'error' || ev.status === 'denied').length

          return (
            <Text wrap="truncate-start">
              <Text color={style.color}>{shortPath(path)}</Text>
              {linesOf(row) !== undefined ? <Text color="success"> +{linesOf(row)?.added}</Text> : null}
              {linesOf(row) !== undefined ? <Text color="error"> −{linesOf(row)?.removed}</Text> : null}
              <Text dimColor>
                {' '}
                · {list.length} write{list.length === 1 ? '' : 's'} · last {clock(list[0]?.at ?? 0)}
              </Text>
              {failed > 0 ? <Text color="error"> · {failed} failed</Text> : null}
            </Text>
          )
        }),
        10_000,
      )
      const filesBlock = (
        <Box flexDirection="column">
          {heading('File changes', `${byFile.length} file${byFile.length === 1 ? '' : 's'}`)}
          {fileRows.kept}
          {fileRows.left > 0 ? <Text dimColor>… {fileRows.left} more</Text> : null}
        </Box>
      )

      // MCP servers: the ones called, with each tool's calls.
      const serverOfTool = new Map(ctx.mcp.map(t => [t.tool, t.server]))
      const serverOf = (tool: string) => serverOfTool.get(tool) ?? tool.split('__')[1] ?? tool
      const mcpCalls = calls.filter(ev => (ev.tool ?? '').startsWith('mcp__') && !(ev.tool ?? '').startsWith('mcp__terminal__'))
      const used = counted(mcpCalls, ev => serverOf(ev.tool ?? ''))
      const mcpBlock = (
        <Box flexDirection="column">
          {heading('MCP servers', `${used.length} called`)}
          {used.map(([server, list]) => {
            const failed = list.filter(ev => ev.status === 'error' || ev.status === 'denied').length
            const last = list[0]

            return (
              <Box key={`mcp-${server}`} flexDirection="column">
                <Text wrap="truncate-end">
                  <Text color="permission">● </Text>
                  <Text bold>{server}</Text>
                  <Text dimColor>
                    {' '}
                    · {list.length} call{list.length === 1 ? '' : 's'}
                    {last ? ` · last ${clock(last.at)}` : ''}
                  </Text>
                  {failed > 0 ? <Text color="error"> · {failed} failed</Text> : null}
                </Text>
                <Text dimColor wrap="truncate-end">
                  {'  ⎿  '}
                  {counted(list, ev => (ev.tool ?? '').split('__').slice(2).join('__'))
                    .map(([name, each]) => `${name} ×${each.length}`)
                    .join(' · ')}
                  {last?.summary ? ` · ${last.summary}` : ''}
                </Text>
              </Box>
            )
          })}
        </Box>
      )

      // Rules: the rules and memory files the agent opened to consult.
      const consulted = counted(calls.filter(ev => ev.refKind === 'rule'), ev => ev.reference ?? '')
      const rulesBlock = (
        <Box flexDirection="column">
          {heading('Rules referenced', `${consulted.length} file${consulted.length === 1 ? '' : 's'}`)}
          {consulted.map(([path, list]) => (
            <Text wrap="truncate-start">
              <Text color="suggestion">{shortPath(path)}</Text>
              <Text dimColor>
                {' '}
                · read {list.length}× · last {clock(list[0]?.at ?? 0)}
              </Text>
            </Text>
          ))}
        </Box>
      )

      // Skills and tools: which it invoked and how often, which deferred tools it loaded.
      const skillsUsed = counted(calls.filter(ev => ev.refKind === 'skill'), ev => ev.reference ?? '')
      const toolsUsed = counted(calls.filter(ev => !(ev.tool ?? '').startsWith('mcp__')), ev => toolName(ev))
      const loaded = calls.filter(ev => ev.refKind === 'tools')
      const skillsBlock = (
        <Box flexDirection="column">
          {heading(
            'Skills & tools',
            `${calls.length} tool call${calls.length === 1 ? '' : 's'}${skillsUsed.length > 0 ? ` · ${skillsUsed.length} skill${skillsUsed.length === 1 ? '' : 's'} used` : ''}`,
          )}
          {skillsUsed.map(([skill, list]) => (
            <Text wrap="truncate-end">
              <Text color="merged">/{skill}</Text>
              <Text dimColor>
                {' '}
                · {list.length}× · last {clock(list[0]?.at ?? 0)}
              </Text>
            </Text>
          ))}
          {toolsUsed.length > 0 ? (
            <Text wrap="wrap">
              {toolsUsed.map(([name, list], i) => (
                <Text>
                  {i > 0 ? <Text dimColor> · </Text> : null}
                  <Text bold>{name}</Text>
                  <Text dimColor> ×{list.length}</Text>
                </Text>
              ))}
            </Text>
          ) : null}
          {loaded.map(ev => (
            <Text dimColor wrap="truncate-end">
              loaded tools: {ev.reference}
            </Text>
          ))}
        </Box>
      )

      // References: knowledge-base lookups and web pages, newest first.
      const looked = calls.filter(ev => ev.refKind === 'kb' || ev.refKind === 'web').slice(0, 15)
      const referencesBlock = (
        <Box flexDirection="column">
          {heading('Looked up', `${looked.length} recent`)}
          {looked.map(ev => (
            <Text wrap="truncate-end">
              <Text color={ev.refKind === 'kb' ? 'success' : 'suggestion'}>{ev.refKind === 'kb' ? 'KB  ' : 'Web '}</Text>
              <Text>{ev.reference}</Text>
              <Text dimColor> · {clock(ev.at)}</Text>
            </Text>
          ))}
        </Box>
      )
      const sections = (
        <Box flexDirection="column">
          {/* The agent's tool and skill tally leads, under its card. */}
          {calls.length > 0 ? skillsBlock : null}
          {thoughts.length > 0 ? thinkingBlock : null}
          {byTerminal.length > 0 ? terminalsBlock : null}
          {byFile.length > 0 ? filesBlock : null}
          {used.length > 0 ? mcpBlock : null}
          {consulted.length > 0 ? rulesBlock : null}
          {looked.length > 0 ? referencesBlock : null}
          {calls.length === 0 && thoughts.length === 0 ? <Text dimColor>Nothing yet: thinking, terminals, file changes, MCP calls, rules and lookups show here as they happen.</Text> : null}
        </Box>
      )
      body = (
        <Box flexDirection="column">
          {/* One agent per page: the main loop, or one subagent. */}
          <Box flexDirection="row" flexWrap="wrap" gap={1}>
            <Button key="agent-main" label="main" variant={picked === 'main' ? 'primary' : 'secondary'} onPress={pick('main')} />
            {sorted.map(a => (
              <Button
                key={`agent-${a.id}`}
                label={`${ACTIVE.has(a.status) ? '● ' : ''}${tabName(a)}`}
                variant={picked !== 'main' && picked.id === a.id ? 'primary' : 'secondary'}
                onPress={pick(a.id)}
              />
            ))}
          </Box>
          <Box marginTop={1} flexDirection="column">
            {picked === 'main' ? mainCard : agentCard(picked, true)}
          </Box>
          {sections}
        </Box>
      )
    } else if (current === 'files') {
      const fileFocused = await read($, fileFocus)
      const writing = await read($, live)
      const shownPreview = await read($, preview)
      const treeRows = liveTreeRows(await read($, workspace), rows, fileFocused)
      const isWide = width >= 70
      const treeWidth = Math.min(44, Math.max(26, Math.floor(width * 0.36)))
      const tally = (...changes: string[]) => rows.filter(row => changes.includes(row.change)).length
      // A Markdown file as the Files browser shows it: its frontmatter as a table, then the document rendered.
      const markdownView = (text: string) => {
        const { fields, body } = splitFrontmatter(text)

        return (
          <Box flexDirection="column">
            {fields.length > 0 ? (
              <Box flexDirection="column" marginTop={1} marginBottom={1}>
                {fields.map(([key, value]) => (
                  <Box flexDirection="row" gap={2}>
                    <Box width={12} flexShrink={0}>
                      <Text dimColor>{key.charAt(0).toUpperCase() + key.slice(1)}</Text>
                    </Box>
                    <Box flexGrow={1} flexShrink={1}>
                      <Text wrap="wrap">{value}</Text>
                    </Box>
                  </Box>
                ))}
              </Box>
            ) : null}
            <Markdown text={body} />
          </Box>
        )
      }
      body = (
        <Box flexDirection={isWide ? 'row' : 'column'} gap={2}>
          <Box flexDirection="column" width={isWide ? treeWidth : undefined} flexShrink={0}>
            <Text wrap="truncate-end">
              <Text dimColor>{rows.length} changed · </Text>
              <Text color="success">+{tally('created', 'untracked')} </Text>
              <Text color="warning">~{tally('modified', 'renamed')} </Text>
              <Text color="error">−{tally('deleted')}</Text>
            </Text>
            {note ? <Text dimColor>{note}</Text> : null}
            {withinBudget(treeRows.map(row => (
              <Text wrap="truncate-end">
                <Text dimColor>{'  '.repeat(row.depth)}</Text>
                {/* A file has no icon: its name lines up with its folder's, past the triangle. */}
                <Text dimColor>{row.isDir ? (row.isOpen ? '▾ ' : '▸ ') : '  '}</Text>
                <Text> </Text>
                {/* The file being edited stands out as a bar in its change colour; ✎ while it is written. */}
                <Text
                  color={row.isFocus ? row.color || 'claude' : row.color || undefined}
                  inverse={row.isFocus}
                  bold={row.isFocus}
                  strikethrough={row.badge === 'D'}
                >
                  {row.isFocus ? ` ${row.name} ` : row.name}
                </Text>
                {row.isFocus && writing !== null ? <Text color="claude"> ✎ writing</Text> : null}
                {/* A changed folder keeps its dot; a file's colour says its change, with no letter. */}
                {row.isDir && row.badge ? <Text color={row.color || undefined}> {row.badge}</Text> : null}
                {row.added > 0 ? <Text color="success"> +{row.added}</Text> : null}
                {row.removed > 0 ? <Text color="error"> −{row.removed}</Text> : null}
              </Text>
            )), 25_000).kept}
          </Box>
          <Box flexDirection="column" flexGrow={1} flexShrink={1}>
            {writing !== null ? (
              <Box flexDirection="column">
                <Text wrap="truncate-start">
                  <Text color="claude">● </Text>
                  <Text bold>{TOOL_NAMES[writing.tool] ?? writing.tool}</Text>
                  <Text>({writing.path})</Text>
                  <Text dimColor>
                    {'  '}
                    writing… · {writing.agent}
                  </Text>
                </Text>
                {writing.diff !== '' ? <Code format="diff" source={cut(writing.diff, MAX_PREVIEW)} wrap="wrap" /> : <Text dimColor>…</Text>}
              </Box>
            ) : shownPreview.kind !== 'none' ? (
              <Box flexDirection="column">
                <Text wrap="truncate-start">
                  <Text bold>{shownPreview.path.split('/').pop()}</Text>
                  <Text dimColor>
                    {'  '}
                    {shownPreview.path.includes('/') ? `${shownPreview.path.slice(0, shownPreview.path.lastIndexOf('/'))} · ` : ''}
                    {shownPreview.note} · {clock(shownPreview.at)}
                  </Text>
                </Text>
                {shownPreview.kind === 'diff' ? (
                  <Code format="diff" source={shownPreview.text} wrap="wrap" />
                ) : isMarkdown(shownPreview.path) ? (
                  markdownView(shownPreview.text)
                ) : (
                  <Code source={shownPreview.text} path={shownPreview.path} startLine={1} wrap="wrap" />
                )}
              </Box>
            ) : (
              <Text dimColor>Waiting for the agent to write a file. Changed files are marked in the tree.</Text>
            )}
          </Box>
        </Box>
      )
    } else if (current === 'audit') {
      // What an audit needs and the chat does not show: what left the machine and how each call was let
      // run, the instructions the agent had, and what was put into its context unseen.
      const acted = [...(await read($, actions))].reverse()
      const unseen = [...(await read($, injected))].reverse()
      const tally = await read($, approvals)
      const memory = (await read($, contextInfo)).memory ?? []
      const cwd = slashes(await $.session.cwd().catch(() => '')).replace(/\/$/, '')
      const shortPath = (path: string) => {
        const p = slashes(path)
        if (cwd !== '' && p.toLowerCase().startsWith(`${cwd.toLowerCase()}/`)) return p.slice(cwd.length + 1)

        return p.replace(/^[A-Za-z]:\/Users\/[^/]+/, '~')
      }
      const heading = (title: string, detail: string) => (
        <Box marginTop={1}>
          <Text wrap="truncate-end">
            <Text bold>{title}</Text>
            <Text dimColor> · {detail}</Text>
          </Text>
        </Box>
      )
      const KIND_COLOR: Record<string, string> = {
        push: 'warning',
        gitlab: 'merged',
        github: 'merged',
        http: 'permission',
        publish: 'suggestion',
        kb: 'success',
        sql: 'permission',
        message: 'claude',
        mcp: 'permission',
      }
      const statusMark = (status?: WatchStatus) =>
        status === 'running' ? <Text color="claude"> running</Text> : status === 'ok' ? <Text color="success"> ✓</Text> : <Text color="error"> ✗</Text>
      const approvalColor = (approval?: Approval) =>
        approval?.kind === 'denied' || approval?.outcome === 'refused' ? 'error' : approval?.kind === 'asked' ? 'warning' : undefined

      // Outward actions: newest first, the risky ones red.
      const risky = acted.filter(a => a.isRisky).length
      const actionRows = withinBudget(
        acted.map(a => (
          <Box key={`act-${a.id}`} flexDirection="row" gap={2}>
            <Box width={8} flexShrink={0}>
              <Text dimColor>{clock(a.at)}</Text>
            </Box>
            <Box width={8} flexShrink={0}>
              <Text bold wrap="truncate-end" color={a.isRisky ? 'error' : KIND_COLOR[a.kind] ?? 'text'}>
                {a.kind}
              </Text>
            </Box>
            <Box flexGrow={1} flexShrink={1}>
              <Text wrap="truncate-end">
                {a.agentId ? <Text dimColor>{a.agent} · </Text> : null}
                {a.what}
                {a.target ? <Text dimColor> · {a.target}</Text> : null}
              </Text>
            </Box>
            <Box width={32} flexShrink={0} justifyContent="flex-end">
              <Text wrap="truncate-start">
                <Text dimColor color={approvalColor(a.approval)}>
                  {approvalLabel(a.approval) || 'not checked'}
                </Text>
                {statusMark(a.status)}
              </Text>
            </Box>
          </Box>
        )),
        30_000,
      )
      const actionsBlock = (
        <Box flexDirection="column">
          {heading('Outward actions', `${acted.length} call${acted.length === 1 ? '' : 's'}${risky > 0 ? ` · ${risky} risky` : ''}`)}
          {acted.length === 0 ? (
            <Text dimColor>None yet: pushes, MRs and issues, messages, SQL, publishes and destructive commands show here.</Text>
          ) : null}
          {actionRows.kept}
          {actionRows.left > 0 ? <Text dimColor>… {actionRows.left} older not shown</Text> : null}
        </Box>
      )

      // Approvals: how the session's calls were let run, and the calls that were asked about or refused.
      const ruleRows = Object.entries(tally.rules).sort((a, b) => b[1] - a[1])
      const ruled = ruleRows.reduce((sum, [, n]) => sum + n, 0)
      const questioned = [...list]
        .reverse()
        .filter(ev => ev.approval?.kind === 'asked' || ev.approval?.kind === 'denied')
        .slice(0, 15)
      const approvalsBlock = (
        <Box flexDirection="column">
          {heading('Approvals', `${ruled + tally.hook + tally.mode + tally.asked + tally.denied} calls checked`)}
          <Text wrap="wrap">
            <Text>by rule ×{ruled}</Text>
            <Text dimColor> · </Text>
            <Text>by mode or the tool ×{tally.mode}</Text>
            <Text dimColor> · </Text>
            <Text>by hook ×{tally.hook}</Text>
            <Text dimColor> · </Text>
            <Text color={tally.asked > 0 ? 'warning' : undefined}>
              asked ×{tally.asked}
              {tally.refused > 0 ? ` (${tally.refused} refused)` : ''}
            </Text>
            <Text dimColor> · </Text>
            <Text color={tally.denied > 0 ? 'error' : undefined}>denied ×{tally.denied}</Text>
          </Text>
          {ruleRows.slice(0, 12).map(([rule, n]) => (
            <Text key={`rule-${rule}`} dimColor wrap="truncate-end">
              {'  '}
              {rule} ×{n}
            </Text>
          ))}
          {questioned.map(ev => (
            <Text key={`asked-${ev.id}`} wrap="truncate-end">
              <Text dimColor>{clock(ev.at)} </Text>
              <Text color={approvalColor(ev.approval)}>{approvalLabel(ev.approval)}</Text>
              <Text>
                {' '}
                {TOOL_NAMES[ev.tool ?? ''] ?? shortTool(ev.tool)} {ev.summary ?? ''}
              </Text>
              {ev.approval?.detail && ev.approval.kind === 'denied' ? <Text dimColor> · {ev.approval.detail}</Text> : null}
            </Text>
          ))}
        </Box>
      )

      // Instructions: the files the context holds (CLAUDE.md, rules, memory), largest first.
      const memoryRows = withinBudget(
        [...memory]
          .sort((a, b) => b.tokens - a.tokens)
          .map(f => (
            <Text key={`mem-${f.path}`} wrap="truncate-start">
              <Text color="suggestion">{shortPath(f.path)}</Text>
              <Text dimColor>
                {' '}
                · {f.type} · {tokens(f.tokens)} tokens
              </Text>
            </Text>
          )),
        10_000,
      )
      const memoryBlock = (
        <Box flexDirection="column">
          {heading(
            'Instructions in context',
            memory.length === 0 ? 'not read yet' : `${memory.length} file${memory.length === 1 ? '' : 's'} · ${tokens(memory.reduce((sum, f) => sum + f.tokens, 0))} tokens`,
          )}
          {memoryRows.kept}
          {memoryRows.left > 0 ? <Text dimColor>… {memoryRows.left} more</Text> : null}
        </Box>
      )

      // Injected: what the model read that the chat does not show, newest first.
      const unseenRows = withinBudget(
        unseen.map(row => (
          <Box key={`inj-${row.id}`} flexDirection="row" gap={2}>
            <Box width={8} flexShrink={0}>
              <Text dimColor>{clock(row.at)}</Text>
            </Box>
            <Box width={24} flexShrink={0}>
              <Text wrap="truncate-end" color={row.door === 'hook-context' ? 'permission' : row.door === 'delivery' ? 'claude' : row.door === 'compaction' ? 'warning' : 'subtle'}>
                {row.agent !== 'main' ? '↳ ' : ''}
                {row.door === 'hook-context' || row.door === 'delivery' ? row.origin : row.name ?? row.door}
              </Text>
            </Box>
            <Box flexGrow={1} flexShrink={1}>
              <Text wrap="truncate-end" dimColor={!row.isSent}>
                {firstLine(row.text) || '(no text)'}
                {row.count > 1 ? <Text dimColor> ×{row.count}</Text> : null}
                {row.isSent ? null : <Text dimColor> · not sent to the model</Text>}
              </Text>
            </Box>
          </Box>
        )),
        30_000,
      )
      const unseenBlock = (
        <Box flexDirection="column">
          {heading('Injected into context', `${unseen.length} row${unseen.length === 1 ? '' : 's'}: hook output, reminders, deliveries, compactions`)}
          {unseen.length === 0 ? <Text dimColor>Nothing yet.</Text> : null}
          {unseenRows.kept}
          {unseenRows.left > 0 ? <Text dimColor>… {unseenRows.left} older not shown</Text> : null}
        </Box>
      )

      body = (
        <Box flexDirection="column">
          {actionsBlock}
          {approvalsBlock}
          {memoryBlock}
          {unseenBlock}
        </Box>
      )
    } else {
      const shown = withinBudget(everything.map(timelineLine), 70_000)
      body = (
        <Box flexDirection="column">
          {everything.length === 0 && <Text dimColor>Nothing yet. Newest shows first.</Text>}
          {shown.kept}
          {shown.left > 0 ? <Text dimColor>… {shown.left} older rows not shown</Text> : null}
        </Box>
      )
    }

    const running = list.filter(ev => ev.status === 'running')
    const liveAgents = subagents.filter(a => ACTIVE.has(a.status)).length

    const header = (
        <Box flexDirection="row" gap={1} alignItems="center">
          {TABS.map(t => (
            <Button
              key={`tab-${t.id}`}
              label={t.label}
              variant={t.id === current ? 'primary' : 'secondary'}
              onPress={() => update($, tab, () => t.id)}
            />
          ))}
          <Box flexGrow={1} flexShrink={1} justifyContent="flex-end">
            <Text wrap="truncate-end">
              {running.length > 0 ? (
                <Text>
                  <Text color="claude">✻ </Text>
                  <Text>{running.map(ev => toolName(ev)).join(', ')}</Text>
                </Text>
              ) : (
                <Text dimColor>Idle</Text>
              )}
              {liveAgents > 0 ? <Text dimColor>{` · ${liveAgents} subagent${liveAgents > 1 ? 's' : ''}`}</Text> : null}
            </Text>
          </Box>
        </Box>
    )
    const tree = (
      <Box flexDirection="column">
        {header}
        <Box marginTop={1} flexDirection="column">
          {body}
        </Box>
      </Box>
    )
    const size = sizeOf(tree)
    if (size <= TREE_LIMIT) return tree

    return (
      <Box flexDirection="column">
        {header}
        <Box marginTop={1}>
          <Text dimColor wrap="wrap">
            This tab holds more than the pane can draw at once ({Math.round(size / 1000)}k of {TREE_LIMIT / 1000}k
            characters). It will show again as older entries make room.
          </Text>
        </Box>
      </Box>
    )
  }).catch(($, e, next) => {
    if (next.error.kind === 're-entry') return next(e)
    const { Box, Text } = $.ui.resolve(e)

    return (
      <Box flexDirection="column">
        <Text color="error" bold>
          Agent watch could not draw this tab
        </Text>
        <Text dimColor wrap="wrap">
          {next.error.kind}: {next.error.message ?? '(no message)'}
        </Text>
        <Text dimColor>Send this line to Claude. /agent-watch tries again.</Text>
      </Box>
    )
  })
}
