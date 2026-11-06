import { expect, test } from 'claude-code/testing'

import { listedPaths, numstatEntries, statusEntries } from '../hooks/git-parse'

// Real `-z` output (git 2.49) from a repo with spaces in its paths, a rename, a rename inside
// folders, an edit and an untracked file.
const STATUS = 'R  now named.txt\0re named.txt\0R  sub dir/d1/d2/g\0sub dir/d1/d2/f\0 M sub dir/my file.txt\0?? un tracked.txt\0'
const NUMSTAT = '0\t0\t\0re named.txt\0now named.txt\0' + '0\t0\t\0sub dir/d1/d2/f\0sub dir/d1/d2/g\0' + '2\t1\tsub dir/my file.txt\0'
const LISTED = 'un tracked.txt\0now named.txt\0sub dir/d1/d2/g\0sub dir/my file.txt\0'

test('status: paths with spaces come whole, and a rename names its new path', () => {
  expect(statusEntries(STATUS)).toEqual([
    { path: 'now named.txt', code: 'R ' },
    { path: 'sub dir/d1/d2/g', code: 'R ' },
    { path: 'sub dir/my file.txt', code: ' M' },
    { path: 'un tracked.txt', code: '??' },
  ])
})

test('numstat: counts attach to the new path, a rename inside folders included', () => {
  expect([...numstatEntries(NUMSTAT)]).toEqual([
    ['now named.txt', { added: 0, removed: 0 }],
    ['sub dir/d1/d2/g', { added: 0, removed: 0 }],
    ['sub dir/my file.txt', { added: 2, removed: 1 }],
  ])
  // A binary file counts '-': left out.
  expect(numstatEntries('-\t-\timage.png\0').size).toBe(0)
})

test('ls-files: every path, spaces and all', () => {
  expect(listedPaths(LISTED)).toEqual(['un tracked.txt', 'now named.txt', 'sub dir/d1/d2/g', 'sub dir/my file.txt'])
  expect(listedPaths('')).toEqual([])
})
