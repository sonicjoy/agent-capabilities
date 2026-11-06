// Pure helpers for the Audit tab: which tool calls reach past the session (a push, an MR, a message,
// SQL, a publish, a destructive command), how a call was approved, and the text of a row the model
// reads that the chat does not show.

import type { Approval } from '../types'

/** A call that reaches past the session: what kind, a line saying what, where to, and whether it is risky. */
export type Outward = { kind: string; what: string; target?: string; isRisky: boolean }

// Shell commands that change something outside the working tree, or destroy work in it. First match wins,
// so the riskier form of a command comes before its plain one.
const SHELL: [RegExp, string, boolean][] = [
  [/\bgit\s+push\b[^\n;&|]*\s(--force\b|--force-with-lease\b|-f\b|\+\S)/, 'push', true],
  [/\bgit\s+push\b/, 'push', false],
  [/\bgit\s+(reset\s+--hard|clean\s+-[a-zA-Z]*f|branch\s+-D|checkout\s+--\s|stash\s+(drop|clear))\b/, 'destroy', true],
  [/(^|[\s;&|(])rm\s+-[a-zA-Z]*[rR]/, 'destroy', true],
  [/\bRemove-Item\b[^\n;|]*-Recurse/i, 'destroy', true],
  [/\b(DROP|TRUNCATE)\s+(TABLE|DATABASE|SCHEMA)\b/i, 'destroy', true],
  [/\bglab\s+(mr|issue|release|ci|repo|label|variable|incident)\s+(create|new|note|comment|update|close|reopen|merge|approve|delete|run|retry|cancel|set)\b/, 'gitlab', false],
  [/\bglab\s+api\b[^\n]*(-X\s*(POST|PUT|PATCH|DELETE)\b|--method\s+(POST|PUT|PATCH|DELETE)\b|\bmutation\b)/i, 'gitlab', false],
  [/\bgh\s+(pr|issue|release|repo)\s+(create|comment|merge|close|edit|delete|review)\b/, 'github', false],
  [/\bgh\s+api\b[^\n]*(-X\s*(POST|PUT|PATCH|DELETE)\b|--method\s+(POST|PUT|PATCH|DELETE)\b)/i, 'github', false],
  [/\b(curl|wget)\b[^\n]*(-X\s*(POST|PUT|PATCH|DELETE)\b|--data\b|--data-\w+|\s-d\s|--form\b|\s-F\s)/i, 'http', false],
  [/\bInvoke-(RestMethod|WebRequest)\b[^\n]*-Method\s+(Post|Put|Patch|Delete)\b/i, 'http', false],
  [/\bkubectl\s+(apply|delete|scale|rollout|edit|patch|exec|set|drain|cordon|replace|create)\b/, 'cloud', true],
  [/\baws\s+\S+\s+(create|delete|put|update|start|stop|terminate|run|invoke|send|publish|modify|attach|detach|remove|cp|mv|rm|sync)[\w-]*\b/, 'cloud', true],
  [/\b(npm|pnpm|yarn)\s+publish\b|\bdocker\s+push\b|\bdotnet\s+nuget\s+push\b/, 'publish', false],
  [/kb\.py["']?\s+write\b/, 'kb', false],
]

// An MCP tool's verb is the first word of its name that says what it does (`slack_send_message`,
// `notion-create-pages`, `get_issue`): one that only looks is not outward. No verb found, not outward either.
const READ_VERBS = new Set('get list search read fetch query find describe show view check count lookup download extract whoami retrieve preview tabs computer navigate resize javascript screenshot zoom me'.split(' '))
const WRITE_VERBS = new Set(
  'send create save update delete write post publish merge share unshare trash untrash forward reply submit schedule upload remove label unlabel mark unmark resolve apply retire restore move duplicate spawn stop set run execute add archive unarchive clear respond complete convert import enable disable cancel approve close reopen edit rename pin unpin start trigger invoke put insert drop'.split(' '),
)
// MCP tool names that delete or merge: risky.
const RISKY = /(^|[_-])(delete|trash|merge|drop|remove|purge|destroy|terminate|stop)([_-]|$)/

/** The verb of an MCP tool's name, and whether it only looks. */
export function verbOf(name: string): { verb: string; isRead: boolean } | undefined {
  for (const word of name.toLowerCase().split(/[_-]+/)) {
    if (READ_VERBS.has(word)) return { verb: word, isRead: true }
    if (WRITE_VERBS.has(word)) return { verb: word, isRead: false }
  }

  return undefined
}

const SQL_WRITES = /^(insert|update|delete|replace|alter|drop|create|truncate|grant|revoke|rename|merge|call|set)$/i

const lineWith = (text: string, match: RegExpExecArray) => {
  const start = text.lastIndexOf('\n', match.index) + 1
  const end = text.indexOf('\n', match.index)

  return text.slice(start, end < 0 ? text.length : end).trim()
}

const cut = (text: string, max: number) => (text.length > max ? `${text.slice(0, max)}…` : text)

/** The first statement keyword of a query, past comments and a WITH clause's name. */
export function sqlVerb(query: string): string {
  const bare = query
    .replace(/\/\*[\s\S]*?\*\//g, ' ')
    .replace(/(--|#)[^\n]*/g, ' ')
    .trim()
  const words = bare.match(/[A-Za-z_]+/g) ?? []
  if ((words[0] ?? '').toUpperCase() !== 'WITH') return (words[0] ?? '').toUpperCase()
  const main = /\)\s*(select|insert|update|delete|replace|merge)\b/i.exec(bare)

  return (main?.[1] ?? 'WITH').toUpperCase()
}

/** Whether a tool call reaches past the session, and how. */
export function outwardOf(tool: string, args: Record<string, unknown>): Outward | undefined {
  const str = (key: string) => (typeof args[key] === 'string' ? (args[key] as string) : undefined)

  if (tool.startsWith('mcp__')) {
    const [, server = '', ...rest] = tool.split('__')
    const name = rest.join('__')
    if (/(^|_)execute_sql$/.test(name)) {
      const query = str('sql') ?? str('query') ?? ''
      const verb = sqlVerb(query)

      return { kind: 'sql', what: cut(query.replace(/\s+/g, ' ').trim(), 160), target: server, isRisky: SQL_WRITES.test(verb) }
    }
    // The Claude app's own panes and the terminal panel are this machine's, not the outside's.
    const verb = verbOf(name)
    if (/^(ccd_|Claude_|terminal$|visualize$)/.test(server) || verb === undefined || verb.isRead) return undefined
    const kind = /slack|gmail|mail|message|reply|forward/i.test(`${server} ${name}`) ? 'message' : 'mcp'
    const about = str('title') ?? str('subject') ?? str('text') ?? str('body') ?? str('name') ?? str('description') ?? ''

    return { kind, what: cut(`${name}${about ? ` · ${about.split('\n')[0]}` : ''}`, 160), target: server, isRisky: RISKY.test(name) }
  }

  if (tool === 'Artifact') {
    const action = str('action') ?? 'publish'
    if (action !== 'publish' && action !== 'delete') return undefined

    return { kind: 'publish', what: `artifact ${action}`, target: str('url') ?? str('file_path'), isRisky: action === 'delete' }
  }
  if (tool === 'ArtifactData') {
    const action = str('action') ?? ''
    if (!/^(set|update|delete|batch)$/.test(action)) return undefined

    return { kind: 'publish', what: `artifact data ${action}`, target: str('url'), isRisky: action === 'delete' }
  }
  if (tool === 'PushNotification') return { kind: 'message', what: cut(str('message') ?? str('text') ?? 'notification', 160), isRisky: false }

  const command = /^(Bash|PowerShell)$/.test(tool) || tool === 'mcp__terminal__run_in_terminal' ? str('command') : undefined
  if (command === undefined) return undefined
  for (const [pattern, kind, isRisky] of SHELL) {
    const found = pattern.exec(command)
    if (found !== null) return { kind, what: cut(lineWith(command, found), 160), isRisky }
  }

  return undefined
}

/** The verdict of a call's permission check, in the words the Audit tab uses. */
export function approvalOf(verdict: { decision: string; rule?: string; hook?: string; reason?: string }): Approval {
  if (verdict.decision === 'deny') return { kind: 'denied', detail: verdict.rule ?? verdict.hook ?? verdict.reason }
  if (verdict.decision === 'ask') return { kind: 'asked', detail: verdict.reason }
  if (verdict.rule !== undefined) return { kind: 'rule', detail: verdict.rule }
  if (verdict.hook !== undefined) return { kind: 'hook', detail: verdict.hook }

  return { kind: 'mode', detail: verdict.reason }
}

/** An approval as one short label: `rule Bash(git status:*)`, `asked → approved`, `denied`. */
export function approvalLabel(approval?: Approval): string {
  if (approval === undefined) return ''
  if (approval.kind === 'asked') return approval.outcome === undefined ? 'asked' : `asked → ${approval.outcome}`
  if (approval.kind === 'rule' || approval.kind === 'hook') return `${approval.kind} ${approval.detail ?? ''}`.trim()
  if (approval.kind === 'mode') return 'allowed'

  return 'denied'
}

/** The text a row carries, as the model reads it: its text blocks, reminder tags dropped. */
export function rowText(content: readonly { type: string; text?: unknown; content?: unknown }[]): string {
  const parts: string[] = []
  for (const block of content) {
    if (typeof block.text === 'string') parts.push(block.text)
    else if (typeof block.content === 'string') parts.push(block.content)
  }

  return parts
    .join('\n')
    .replace(/<\/?system-reminder>/g, '')
    .trim()
}

/** Who caused a row: a settings hook by event, a plugin, a peer session, the engine. */
export function originLabel(origin: unknown): string {
  const o = (origin ?? {}) as { kind?: string; event?: string; server?: string; plugin?: string; tool?: string }
  if (o.kind === 'hook') return `hook ${o.event ?? ''}`.trim()
  if (o.kind === 'plugin') return `plugin${o.plugin ? ` ${o.plugin}` : ''}${o.event ? ` (${o.event})` : ''}`
  if (o.kind === 'channel') return `channel ${o.server ?? ''}`.trim()
  if (o.kind === 'tool') return `tool ${o.tool ?? ''}`.trim()

  return o.kind ?? 'engine'
}
