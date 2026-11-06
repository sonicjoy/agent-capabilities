import { describe, expect, test } from 'claude-code/testing'

import { addedHunk, doneHunk, editHunk, lineDelta, pairHunk, scanFields, splitFrontmatter, writingHunk } from '../hooks/live-files'

describe('Markdown files read as the Files browser shows them', () => {
  test('frontmatter becomes rows, a folded value one line, and the body follows', async () => {
    const skill = [
      '---',
      'name: gitlab-issues',
      'description: >-',
      '  Manage GitLab issues using glab CLI,',
      '  with the browser as fallback.',
      'version: "1.2"',
      '---',
      '',
      '# GitLab Issue Management',
      'Body text.',
    ].join('\r\n')
    expect(splitFrontmatter(skill)).toEqual({
      fields: [
        ['name', 'gitlab-issues'],
        ['description', 'Manage GitLab issues using glab CLI, with the browser as fallback.'],
        ['version', '1.2'],
      ],
      body: '# GitLab Issue Management\nBody text.',
    })
  })

  test('no frontmatter: the whole text is the body', async () => {
    expect(splitFrontmatter('# Title\n---\nnot frontmatter')).toEqual({ fields: [], body: '# Title\n---\nnot frontmatter' })
  })

})

describe('scanFields reads tool arguments that are still streaming', () => {
  test('a string cut mid-way is read so far, and not done', async () => {
    const fields = scanFields('{"file_path": "src/a.ts", "old_string": "one\\ntwo", "new_string": "hel')
    expect(fields.file_path).toEqual({ text: 'src/a.ts', isDone: true })
    expect(fields.old_string).toEqual({ text: 'one\ntwo', isDone: true })
    expect(fields.new_string).toEqual({ text: 'hel', isDone: false })
  })

  test('escapes decode, a cut escape waits, and text naming another field stays text', async () => {
    expect(scanFields('{"content": "a \\"q\\" \\u00e9 \\t').content).toEqual({ text: 'a "q" é \t', isDone: false })
    expect(scanFields('{"content": "a\\').content).toEqual({ text: 'a', isDone: false })
    expect(scanFields('{"content": "a\\u00').content).toEqual({ text: 'a', isDone: false })
    const tricky = scanFields('{"old_string": "x \\"new_string\\": y", "new_string": "z"}')
    expect(tricky.old_string?.text).toBe('x "new_string": y')
    expect(tricky.new_string).toEqual({ text: 'z', isDone: true })
  })

  test('a key not yet closed, and non-string values', async () => {
    expect(scanFields('{"file_pa')).toEqual({})
    expect(scanFields('{"replace_all": false, "file_path": "a"}')).toEqual({
      replace_all: { text: 'false', isDone: true },
      file_path: { text: 'a', isDone: true },
    })
  })
})

describe('hunks', () => {
  const file = ['l1', 'l2', 'l3', 'const x = 1', 'l5', 'l6', 'l7', 'l8', 'l9'].join('\n')

  test('an edit mid-line becomes whole lines with real numbers and context', async () => {
    const at = file.indexOf('x = 1')
    expect(editHunk(file, at, 'x = 1'.length, 'y = 2', 2)).toBe(
      ['@@ -2,5 +2,5 @@', ' l2', ' l3', '-const x = 1', '+const y = 2', ' l5', ' l6'].join('\n'),
    )
  })

  test('an edit that adds lines counts them', async () => {
    const at = file.indexOf('l5')
    expect(editHunk(file, at, 2, 'l5\nnew', 1)).toBe(['@@ -4,3 +4,4 @@', ' const x = 1', '-l5', '+l5', '+new', ' l6'].join('\n'))
  })

  test('a half-written edit shows the line being typed', async () => {
    const hunk = writingHunk('Edit', scanFields('{"old_string": "const x = 1", "new_string": "const x = 4'), file)
    expect(hunk).toContain('-const x = 1\n+const x = 4')
  })

  test('an edit whose old text is not in the file falls back to the pair', async () => {
    expect(writingHunk('Edit', scanFields('{"old_string": "nope", "new_string": "yes"}'), file)).toBe('@@ -1,1 +1,1 @@\n-nope\n+yes')
    expect(pairHunk('', '')).toBe('')
    expect(pairHunk('', 'a')).toBe('@@ -0,0 +1,1 @@\n+a')
  })

  test('a file being written shows its last lines; a finished one from the top', async () => {
    const long = Array.from({ length: 100 }, (_, i) => `line ${i + 1}`).join('\n')
    const writing = addedHunk(long, true)
    expect(writing.startsWith('@@ -0,0 +21,80 @@\n+line 21')).toBe(true)
    expect(writing.endsWith('+line 100')).toBe(true)
    expect(addedHunk('a\nb').toString()).toBe('@@ -0,0 +1,2 @@\n+a\n+b')
    expect(writingHunk('Write', scanFields('{"file_path": "a", "content": "x\\ny'), null)).toBe('@@ -0,0 +1,2 @@\n+x\n+y')
  })

  test('a finished edit is found again in the file as it is now', async () => {
    const after = file.replace('x = 1', 'y = 2')
    expect(doneHunk('Edit', 'const x = 1', 'const y = 2', after)).toContain('-const x = 1\n+const y = 2\n l5')
    expect(doneHunk('Edit', 'a', 'b', null)).toBe('@@ -1,1 +1,1 @@\n-a\n+b')
    expect(doneHunk('Write', '', 'p\nq', null)).toBe('@@ -0,0 +1,2 @@\n+p\n+q')
  })
})

test('lines added and removed: shared lines at the start and end are not counted', () => {
  expect(lineDelta('', 'a\nb\nc\n')).toEqual({ added: 3, removed: 0 })
  expect(lineDelta('a\nb\nc\n', 'a\nB\nX\nc\n')).toEqual({ added: 2, removed: 1 })
  expect(lineDelta('a\nb\n', 'a\nb\n')).toEqual({ added: 0, removed: 0 })
  expect(lineDelta('one line', 'one line\r\ntwo')).toEqual({ added: 1, removed: 0 })
  expect(lineDelta('x\ny\nz', '')).toEqual({ added: 0, removed: 3 })
})
