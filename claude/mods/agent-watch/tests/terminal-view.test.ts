import { expect, test } from 'claude-code/testing'

import { fitCommands, rowsOf } from '../hooks/terminal-view'
import type { TermLine } from '../hooks/terminal-view'

test('a long command wraps to the left edge, as a terminal wraps', () => {
  const rows = rowsOf([{ p: '~/repo $ ', t: 'y'.repeat(40) }], 38)
  expect(rows.map(row => row.prefix + row.text)).toEqual([`~/repo $ ${'y'.repeat(29)}`, 'y'.repeat(11)])
  expect(rows.map(row => row.last)).toEqual([false, true])
})

test('a hanging line wraps under its text', () => {
  const rows = rowsOf([{ p: '● ', t: 'x'.repeat(50), h: true }], 38)
  expect(rows.map(row => row.prefix + row.text)).toEqual([`● ${'x'.repeat(36)}`, `  ${'x'.repeat(14)}`])
})

const command = (n: number, out: number): TermLine[] => [
  { p: '$ ', t: `cmd ${n}` },
  ...Array.from({ length: out }, (_, i) => ({ t: `out ${n}.${i}` })),
]
const cursor: TermLine = { p: '$ ', t: '█' }
const text = (rows: ReturnType<typeof fitCommands>) => rows.map(row => row.prefix + row.text)

test('a box opens on a prompt: whole commands only, newest last, then the cursor', () => {
  // Three commands of 4 rows each; 10 rows hold the last two and the cursor.
  const rows = text(fitCommands([command(1, 3), command(2, 3), command(3, 3)], cursor, 40, 10))
  expect(rows).toEqual(['$ cmd 2', 'out 2.0', 'out 2.1', 'out 2.2', '$ cmd 3', 'out 3.0', 'out 3.1', 'out 3.2', '$ █'])
})

test('a command too tall for the box keeps its command, folds the middle, shows the end', () => {
  const rows = text(fitCommands([command(1, 2), command(2, 30)], cursor, 40, 8))
  expect(rows).toEqual(['$ cmd 2', '… 25 more lines', 'out 2.25', 'out 2.26', 'out 2.27', 'out 2.28', 'out 2.29', '$ █'])
})
