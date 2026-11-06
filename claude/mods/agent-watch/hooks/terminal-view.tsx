/** One logical line: a prefix (a prompt) and its text, each with its own style. */
export type TermLine = {
  p?: string
  pc?: string
  t: string
  c?: string
  b?: boolean
  d?: boolean
  i?: boolean
  /** Drawn dim after the text, on its last row: a time. */
  s?: string
  /** A wrapped row starts under the text, past the prefix; else at the left edge, as a terminal wraps. */
  h?: boolean
}

export type TermRow = { line: TermLine; prefix: string; text: string; last: boolean }

/** Each line cut to the box's width; a wrapped part starts at the left edge, as a terminal wraps. */
export function rowsOf(lines: TermLine[], columns: number): TermRow[] {
  const rows: TermRow[] = []
  for (const line of lines) {
    const prefix = line.p ?? ''
    const first = Math.max(8, columns - prefix.length)
    const rest = line.h ? first : Math.max(8, columns)
    const text = [line.t.slice(0, first)]
    for (let at = first; at < line.t.length; at += rest) text.push(line.t.slice(at, at + rest))
    text.forEach((part, i) =>
      rows.push({ line, prefix: i === 0 ? prefix : line.h ? ' '.repeat(prefix.length) : '', text: part, last: i === text.length - 1 }),
    )
  }

  return rows
}

/**
 * What a terminal box of `height` rows shows: whole commands, newest last, so it always opens on a
 * prompt, then the cursor. When the newest command alone is too tall, its prompt and command stay
 * at the top, a "… N lines" fold stands for the middle, and the end of its output fills the rest.
 */
export function fitCommands(commands: TermLine[][], cursor: TermLine, columns: number, height: number): TermRow[] {
  const groups = commands.map(lines => rowsOf(lines, columns))
  const tail = rowsOf([cursor], columns)
  const room = Math.max(3, height - tail.length)
  const shown: TermRow[][] = []
  let used = 0
  for (let i = groups.length - 1; i >= 0; i -= 1) {
    const group = groups[i] ?? []
    if (used + group.length > room) break
    shown.unshift(group)
    used += group.length
  }
  if (shown.length > 0 || groups.length === 0) return [...shown.flat(), ...tail]

  // The newest command alone does not fit: keep its head (the prompt and command), fold the middle.
  const newest = groups[groups.length - 1] ?? []
  const typed = newest.findIndex(row => row.line.p === undefined)
  const head = newest.slice(0, Math.min(typed < 0 ? newest.length : typed, room - 2))
  const end = newest.slice(newest.length - (room - head.length - 1))
  const hidden = newest.length - head.length - end.length
  const fold: TermRow = { line: { t: `… ${hidden} more line${hidden === 1 ? '' : 's'}`, d: true }, prefix: '', text: `… ${hidden} more line${hidden === 1 ? '' : 's'}`, last: true }

  return [...head, fold, ...end, ...tail]
}
