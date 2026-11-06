// git's NUL-separated (-z) output: paths come raw, never quoted or escaped, whatever they hold.

/** `git status --porcelain=v1 -z`: each changed path (repo-root relative) and its two-letter code. */
export function statusEntries(stdout: string): { path: string; code: string }[] {
  const fields = stdout.split('\0')
  const entries: { path: string; code: string }[] = []
  for (let i = 0; i < fields.length; i += 1) {
    const field = fields[i] ?? ''
    if (field.length < 4) continue
    const code = field.slice(0, 2)
    entries.push({ path: field.slice(3), code })
    // A rename or copy is followed by the path it came from.
    if (code.includes('R') || code.includes('C')) i += 1
  }

  return entries
}

/** `git ls-files -z`: the paths. */
export function listedPaths(stdout: string): string[] {
  return stdout.split('\0').filter(Boolean)
}

/** `git diff --numstat -z`: lines added and removed per path; a binary file ('-') is left out. */
export function numstatEntries(stdout: string): Map<string, { added: number; removed: number }> {
  const fields = stdout.split('\0')
  const stats = new Map<string, { added: number; removed: number }>()
  for (let i = 0; i < fields.length; i += 1) {
    const match = /^(\d+|-)\t(\d+|-)\t([\s\S]*)$/.exec(fields[i] ?? '')
    if (match === null) continue
    let path = match[3] ?? ''
    // A rename leaves the path empty, then gives the old path and the new one as fields of their own.
    if (path === '') {
      path = fields[i + 2] ?? ''
      i += 2
    }
    if (match[1] !== '-' && match[2] !== '-' && path !== '') {
      stats.set(path, { added: Number(match[1]), removed: Number(match[2]) })
    }
  }

  return stats
}
