export type WatchTab = 'timeline' | 'agents' | 'files' | 'audit'

/** One subagent this session started. */
/** What keeps subagent tab names unique for the session: no number is given twice, no dropped row returns. */
export type AgentNames = {
  last: number
  dropped: string[]
}

export type AgentRow = {
  id: string
  /** The order it started in this session, from 1: its tab's name (1 Alice, 2 Bob, ...). Absent on a row kept before numbering. */
  n?: number
  type: string
  description: string
  /** pending | running | waiting | idle | completed | failed | killed */
  status: string
  parentId?: string
  startedAt: number
  toolCalls: number
  lastAction?: string
  /** Its final answer, cut short. */
  answer?: string
  durationMs?: number
}

/** What one loop (main, or one subagent) has spent, summed over its model requests. */
export type LoopUsage = {
  model: string
  /** The effort its latest request asked for (low … max), when the model takes one. */
  effort?: string
  requests: number
  input: number
  cacheRead: number
  cacheWrite: number
  output: number
  /** Estimated at first-party list prices; undefined for a model with no known price. */
  usd?: number
  /** Input tokens of its latest request: how full its context window is now. */
  context: number
  window: number
}

/** A file tool call as it is being written: its arguments so far, as a diff hunk. */
export type LiveWrite = {
  path: string
  tool: string
  agent: string
  diff: string
  at: number
}

/** The Files tab's right-hand side once a write has landed: the file's changes, or its text. */
export type Preview = {
  path: string
  kind: 'diff' | 'file' | 'none'
  text: string
  note: string
  at: number
}

/** Which MCP server each connected tool belongs to, from the session's /context breakdown. */
export type ContextInfo = {
  mcp: { tool: string; server: string }[]
  /** The instruction and memory files in the context: CLAUDE.md, rules, memory. */
  memory?: { path: string; type: string; tokens: number }[]
  at: number
}

/** How a tool call was let run, from its permission check: a settings rule, a hook, the mode, a question, a refusal. */
export type Approval = {
  kind: 'rule' | 'hook' | 'mode' | 'asked' | 'denied'
  /** The rule as written, the hook's event, or the reason. */
  detail?: string
  /** For a call that was asked: whether it then ran. */
  outcome?: 'approved' | 'refused'
}

/** A call that reached past the session: a push, an MR, a message, SQL, a publish, a destructive command. */
export type AuditAction = {
  id: string
  at: number
  agent: string
  agentId?: string
  tool: string
  /** push, destroy, gitlab, github, http, cloud, publish, kb, sql, message, mcp */
  kind: string
  what: string
  /** Where to: the MCP server (the database for SQL), the artifact. */
  target?: string
  isRisky: boolean
  status?: WatchStatus
  approval?: Approval
}

/** A row the model read that the chat does not show: a hook's output, a reminder, a delivery, a compaction. */
export type InjectedRow = {
  id: string
  at: number
  agent: string
  /** The door it came in by: hook-context, attachment, delivery, compaction, notice, note. */
  door: string
  /** The attachment's type or the notice's subtype (nested_memory, compact_boundary). */
  name?: string
  /** Who caused it: hook SessionStart, plugin x, peer, engine. */
  origin: string
  text: string
  /** The same row again: how many times. */
  count: number
  /** False for a notice no request carries: shown to the person, not read by the model. */
  isSent: boolean
}

/** How the session's tool calls were let run, counted since the session started. */
export type ApprovalTally = {
  rules: Record<string, number>
  hook: number
  mode: number
  asked: number
  refused: number
  denied: number
}

/** The engine's own figures for the whole session, as the status line has them. */
export type SessionFigures = {
  usd?: number
  contextTokens?: number
  window?: number
  percent?: number
}

export type WatchStatus = 'running' | 'ok' | 'error' | 'denied'

/** One thing the agent did: a thought, a reply, or a tool call. */
export type WatchEvent = {
  id: string
  at: number
  /** Which loop: 'main', or the subagent's label. */
  agent: string
  /** The subagent's id; absent on the main loop. */
  agentId?: string
  /** The model and effort of the agent's latest model request (claude-opus-5-5, medium). */
  model?: string
  effort?: string
  kind: 'thinking' | 'text' | 'tool'
  /** The start of the thinking or reply text: the Timeline shows its first line. */
  text?: string
  tool?: string
  /** One line saying what the call is about: a file name, a command, a pattern. */
  summary?: string
  isTerminal?: boolean
  /** Which terminal a shell call ran in: shell:bash, shell:powershell, bg:<shell id>, tab:<panel tab>. */
  terminal?: string
  /** What the call looked up: a skill, a rules file, a KB query, a web page, deferred tools. */
  refKind?: 'skill' | 'rule' | 'kb' | 'web' | 'tools'
  reference?: string
  /** For terminal tools: the command line, and the agent's note on it. */
  command?: string
  note?: string
  status?: WatchStatus
  ms?: number
  /** The workspace path a file tool wrote: the Agents tab's file changes. */
  file?: string
  /** The end of the tool's output: the Agents tab's terminals show its last lines. */
  output?: string
  /** How the call was let run (its permission check). */
  approval?: Approval
}

/** One file that differs in the workspace, or that the agent wrote. */
export type FileRow = {
  path: string
  /** created | modified | deleted | renamed | untracked */
  change: string
  /** Changed through the agent's Edit/Write/NotebookEdit calls. */
  byAgent: boolean
  edits: number
  /** Lines added and removed against HEAD (git diff --numstat); absent when unknown or binary. */
  added?: number
  removed?: number
  /** Lines the agent's own edits added and removed, for a file git does not count (new, or outside the repo). */
  ownAdded?: number
  ownRemoved?: number
}

declare module 'claude-code' {
  interface PluginState {
    'agent-watch': {
      events: WatchEvent[]
      files: FileRow[]
      tab: WatchTab
      gitNote: string
      agents: AgentRow[]
      /** The highest tab number given out, and the subagents dropped from the tabs: neither comes back. */
      agentNames: AgentNames
      /** Show only this loop: '' for all, 'main', or a subagent's id. */
      focus: string
      /** Keyed 'main' or the subagent's id. */
      loops: Record<string, LoopUsage>
      session: SessionFigures
      /** The workspace paths the Files tree draws: one per closed folder, every file of an open one. */
      workspace: string[]
      /** The file the agent wrote last, or is writing now: the Files tab follows it. */
      fileFocus: string
      /** The write in progress, while the agent streams it and the tool runs; null between writes. */
      live: LiveWrite | null
      preview: Preview
      /** Whether the pane is on screen: the button above the prompt shows while it is not. */
      paneShown: boolean
      /** The person closed the pane: the agent's work doesn't open it again until they do. */
      dismissed: boolean
      contextInfo: ContextInfo
      /** Which loaded copy of the mod draws and records: the newest one's load stamp. */
      owner: number
      /** The Audit tab: calls that reached past the session, newest last. */
      actions: AuditAction[]
      /** The Audit tab: rows the model read that the chat does not show, newest last. */
      injected: InjectedRow[]
      approvals: ApprovalTally
    }
  }
}
