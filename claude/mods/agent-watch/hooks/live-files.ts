// Pure helpers for the Files tab: reading a tool call's arguments while they still stream,
// and turning a file change into unified-diff hunks the Code element colours.

/** One argument read so far: its text, and whether its closing quote has arrived. */
export type Field = { text: string; isDone: boolean }
export type Fields = Record<string, Field>

const ESCAPES: Record<string, string> = { '"': '"', '\\': '\\', '/': '/', b: '\b', f: '\f', n: '\n', r: '\r', t: '\t' }

/**
 * Reads the top-level fields of a JSON object that may stop anywhere: a string field
 * cut mid-way comes back with what has arrived and `isDone: false`.
 */
export function scanFields(json: string): Fields {
  const out: Fields = {}
  let i = json.indexOf('{') + 1
  if (i === 0) return out

  const readString = (): Field => {
    i += 1 // the opening quote
    let text = ''
    let from = i
    while (i < json.length) {
      const c = json[i]
      if (c === '"') {
        text += json.slice(from, i)
        i += 1
        return { text, isDone: true }
      }
      if (c === '\\') {
        text += json.slice(from, i)
        const next = json[i + 1]
        if (next === undefined) return { text, isDone: false }
        if (next === 'u') {
          const hex = json.slice(i + 2, i + 6)
          if (hex.length < 4) return { text, isDone: false }
          text += String.fromCharCode(parseInt(hex, 16))
          i += 6
        } else {
          text += ESCAPES[next] ?? next
          i += 2
        }
        from = i
        continue
      }
      i += 1
    }
    text += json.slice(from, i)

    return { text, isDone: false }
  }

  while (i < json.length) {
    while (i < json.length && /[\s,]/.test(json[i] ?? '')) i += 1
    if (json[i] !== '"') break
    const key = readString()
    if (!key.isDone) break
    while (i < json.length && /[\s:]/.test(json[i] ?? '')) i += 1
    if (i >= json.length) break
    if (json[i] === '"') {
      const value = readString()
      out[key.text] = value
      if (!value.isDone) break
    } else {
      const raw = /^[^,}]*/.exec(json.slice(i))?.[0] ?? ''
      i += raw.length
      out[key.text] = { text: raw.trim(), isDone: i < json.length }
    }
  }

  return out
}

/** The complete arguments of a tool call, as fields. */
export function fieldsOf(args: Record<string, unknown>): Fields {
  const out: Fields = {}
  for (const [key, value] of Object.entries(args)) {
    if (typeof value === 'string') out[key] = { text: value, isDone: true }
  }

  return out
}

export const normalise = (text: string) => text.replace(/\r\n/g, '\n')

const linesOf = (text: string) => normalise(text).split('\n')

const range = (start: number, count: number) => `${count === 0 ? Math.max(0, start - 1) : start},${count}`

const CONTEXT = 4
const MAX_LINES = 1500
const TAIL_LINES = 80

/**
 * `oldText` at offset `at` of `before` replaced by `newText`, as one hunk of whole lines with
 * the file's real line numbers and a few lines around it. `newText` may be half-written.
 */
export function editHunk(before: string, at: number, oldLength: number, newText: string, context = CONTEXT): string {
  const text = normalise(before)
  const lineStart = text.lastIndexOf('\n', at - 1) + 1
  const endAt = text.indexOf('\n', at + oldLength)
  const lineEnd = endAt < 0 ? text.length : endAt
  const oldBlock = text.slice(lineStart, lineEnd).split('\n')
  const newBlock = (text.slice(lineStart, at) + normalise(newText) + text.slice(at + oldLength, lineEnd)).split('\n')
  const all = text.split('\n')
  const first = text.slice(0, lineStart).split('\n').length - 1
  const above = all.slice(Math.max(0, first - context), first)
  const below = all.slice(first + oldBlock.length, first + oldBlock.length + context)
  const start = first - above.length + 1

  return [
    `@@ -${range(start, above.length + oldBlock.length + below.length)} +${range(start, above.length + newBlock.length + below.length)} @@`,
    ...above.map(line => ` ${line}`),
    ...oldBlock.map(line => `-${line}`),
    ...newBlock.map(line => `+${line}`),
    ...below.map(line => ` ${line}`),
  ].join('\n')
}

/** Old lines out, new lines in, with no file around them (where the old text was not found). */
export function pairHunk(oldText: string, newText: string): string {
  const removed = oldText === '' ? [] : linesOf(oldText)
  const added = newText === '' ? [] : linesOf(newText)
  if (removed.length + added.length === 0) return ''

  return [
    `@@ -${range(1, removed.length)} +${range(1, added.length)} @@`,
    ...removed.map(line => `-${line}`),
    ...added.map(line => `+${line}`),
  ].join('\n')
}

/**
 * A whole file as added lines. While it is still being written (`isTail`), its last lines,
 * so the line being written stays in view.
 */
export function addedHunk(text: string, isTail = false): string {
  if (text === '') return ''
  const all = linesOf(text)
  const keep = isTail ? TAIL_LINES : MAX_LINES
  const lines = isTail ? all.slice(-keep) : all.slice(0, keep)
  const start = isTail ? all.length - lines.length + 1 : 1

  return [`@@ -0,0 +${start},${lines.length} @@`, ...lines.map(line => `+${line}`)].join('\n')
}

/** What a file tool is doing, as a hunk: from the arguments read so far and the file as it was. */
export function writingHunk(tool: string, fields: Fields, before: string | null): string {
  if (tool === 'Edit') {
    const oldField = fields.old_string
    const newText = fields.new_string?.text ?? ''
    if (oldField?.isDone && before !== null) {
      const at = normalise(before).indexOf(normalise(oldField.text))
      if (at >= 0) return editHunk(before, at, normalise(oldField.text).length, newText)
    }

    return pairHunk(oldField?.text ?? '', newText)
  }
  const content = fields.content ?? fields.new_source
  const text = content?.text ?? ''

  return addedHunk(text, !(content?.isDone ?? false))
}

/** A finished edit, found again in the file as it is now; else the edit alone. */
export function doneHunk(tool: string, oldText: string, newText: string, after: string | null): string {
  if (tool !== 'Edit') return addedHunk(after ?? newText)
  const now = after === null ? null : normalise(after)
  const added = normalise(newText)
  const at = now === null || added === '' ? -1 : now.indexOf(added)
  if (now === null || at < 0) return pairHunk(oldText, newText)
  const before = now.slice(0, at) + normalise(oldText) + now.slice(at + added.length)

  return editHunk(before, at, normalise(oldText).length, added)
}

// A two-cell type mark per file, in the column a folder's chevron takes, coloured as the
// app's Files browser colours its icons.
export const isMarkdown = (path: string) => /\.(md|mdx)$/i.test(path)

/**
 * A Markdown file's YAML frontmatter as `[key, value]` rows (a folded or multi-line value
 * joined into one line, quotes dropped), and the document after it.
 */
export function splitFrontmatter(text: string): { fields: [string, string][]; body: string } {
  const source = normalise(text)
  const match = /^---\n([\s\S]*?)\n---[ \t]*(?:\n|$)/.exec(source)
  if (match === null) return { fields: [], body: source }
  const fields: [string, string][] = []
  for (const line of (match[1] ?? '').split('\n')) {
    const pair = /^([A-Za-z_][\w-]*):\s*(.*)$/.exec(line)
    const last = fields[fields.length - 1]
    if (pair !== null) fields.push([pair[1] ?? '', pair[2] ?? ''])
    else if (last !== undefined && line.trim() !== '') last[1] = `${last[1]} ${line.trim()}`.trim()
  }
  const clean = (value: string) => value.replace(/^[>|][-+]?\s*/, '').replace(/^(['"])([\s\S]*)\1$/, '$2').trim()

  return { fields: fields.map(([key, value]) => [key, clean(value)]), body: source.slice(match[0].length).replace(/^\n+/, '') }
}

/**
 * Lines added and removed from `before` to `after`: the lines both share at the start and the end
 * are set aside, and what differs between counts. Exact for one changed region, as an edit is.
 */
export function lineDelta(before: string, after: string): { added: number; removed: number } {
  const old = before === '' ? [] : normalise(before).replace(/\n$/, '').split('\n')
  const now = after === '' ? [] : normalise(after).replace(/\n$/, '').split('\n')
  let start = 0
  while (start < old.length && start < now.length && old[start] === now[start]) start += 1
  let end = 0
  while (end < old.length - start && end < now.length - start && old[old.length - 1 - end] === now[now.length - 1 - end]) end += 1

  return { added: now.length - start - end, removed: old.length - start - end }
}
