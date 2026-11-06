import { expect, test } from 'claude-code/testing'

import { approvalLabel, approvalOf, originLabel, outwardOf, rowText, sqlVerb } from '../hooks/audit'

const PANE = {
  component: 'Pane',
  requestId: 'agent-watch',
  props: {
    title: 'Agent watch',
    isFocused: false,
    bodyColumns: 120,
    placement: 'dock',
    scroll: { offset: 0, bodyRows: 40 },
    view: {},
  },
} as const

test('outward: what reaches past the session, and what is risky', () => {
  const bash = (command: string) => outwardOf('Bash', { command })
  expect(bash('git push -u origin mods/23')).toMatchObject({ kind: 'push', isRisky: false })
  expect(bash('git push --force origin main')).toMatchObject({ kind: 'push', isRisky: true })
  expect(bash('cd x && git push origin +main')).toMatchObject({ kind: 'push', isRisky: true })
  expect(bash('git status && git diff')).toBeUndefined()
  expect(bash('git commit -m "x"')).toBeUndefined()
  expect(bash('rm -rf build')).toMatchObject({ kind: 'destroy', isRisky: true })
  expect(bash('rm notes.txt')).toBeUndefined()
  expect(bash('git reset --hard HEAD~1')).toMatchObject({ kind: 'destroy', isRisky: true })
  expect(outwardOf('PowerShell', { command: 'Remove-Item -Recurse -Force .\\dist' })).toMatchObject({ kind: 'destroy' })
  expect(bash('glab mr create -t "x" -d "y"')).toMatchObject({ kind: 'gitlab' })
  expect(bash('glab issue note 23 -m "done"')).toMatchObject({ kind: 'gitlab' })
  expect(bash('glab api graphql -f query=\'mutation{workItemUpdate(input:{})}\'')).toMatchObject({ kind: 'gitlab' })
  expect(bash('glab api projects/1/merge_requests')).toBeUndefined()
  expect(bash('curl -s -X POST https://example.com/hook -d @body.json')).toMatchObject({ kind: 'http' })
  expect(bash('curl -s https://example.com')).toBeUndefined()
  expect(bash('python skills/knowledge/kb.py write fact --id x')).toMatchObject({ kind: 'kb' })
  expect(bash('python skills/knowledge/kb.py read search --q x')).toBeUndefined()
  // The line that matched, not the whole script.
  expect(bash('cd repo\ngit add .\ngit push origin x\necho done')?.what).toBe('git push origin x')

  expect(outwardOf('mcp__production_uk_cbtote__execute_sql', { sql: 'SELECT * FROM pool LIMIT 1' })).toMatchObject({
    kind: 'sql',
    target: 'production_uk_cbtote',
    isRisky: false,
  })
  expect(outwardOf('mcp__staging_mysql_cbtote__execute_sql', { sql: '-- fix\nUPDATE pool SET status = 2' })).toMatchObject({ isRisky: true })
  expect(outwardOf('mcp__slack__slack_send_message', { channel_id: 'C1', text: 'Deployed' })).toMatchObject({ kind: 'message', what: 'slack_send_message · Deployed' })
  expect(outwardOf('mcp__gitlab__delete_comment', { id: '1' })).toMatchObject({ kind: 'mcp', isRisky: true })
  expect(outwardOf('mcp__slack__slack_read_channel', { channel_id: 'C1' })).toBeUndefined()
  expect(outwardOf('mcp__neo4j-kb__read_neo4j_cypher', { query: 'MATCH (n) RETURN n' })).toBeUndefined()
  expect(outwardOf('mcp__ccd_session_mgmt__delete_session', {})).toBeUndefined()
  expect(outwardOf('mcp__notion__notion-create-pages', { title: 'Plan' })).toMatchObject({ kind: 'mcp', what: 'notion-create-pages · Plan' })
  expect(outwardOf('mcp__notion__notion-fetch', { id: 'x' })).toBeUndefined()
  expect(outwardOf('mcp__aws-mcp__aws___run_script', { code: 'x' })).toMatchObject({ kind: 'mcp', target: 'aws-mcp' })
  expect(outwardOf('Artifact', { file_path: 'report.html' })).toMatchObject({ kind: 'publish', what: 'artifact publish' })
  expect(outwardOf('Artifact', { action: 'read', url: 'x' })).toBeUndefined()
  expect(outwardOf('Read', { file_path: 'a.ts' })).toBeUndefined()
})

test('sql verbs: past comments and a WITH', () => {
  expect(sqlVerb('/* why */ delete from x')).toBe('DELETE')
  expect(sqlVerb('WITH t AS (SELECT 1) SELECT * FROM t')).toBe('SELECT')
  expect(sqlVerb('with t as (select 1) update x set a = 1')).toBe('UPDATE')
})

test('approvals: a rule, the mode, a question and its answer, a refusal', () => {
  expect(approvalLabel(approvalOf({ decision: 'allow', rule: 'Bash(git push:*)' }))).toBe('rule Bash(git push:*)')
  expect(approvalLabel(approvalOf({ decision: 'allow', reason: 'read-only tool' }))).toBe('allowed')
  expect(approvalLabel(approvalOf({ decision: 'allow', hook: 'PreToolUse' }))).toBe('hook PreToolUse')
  expect(approvalLabel({ ...approvalOf({ decision: 'ask' }), outcome: 'approved' })).toBe('asked → approved')
  expect(approvalLabel(approvalOf({ decision: 'deny', rule: 'Bash(rm:*)' }))).toBe('denied')
  expect(approvalLabel(undefined)).toBe('')
})

test('injected rows: text without reminder tags, and who caused them', () => {
  expect(rowText([{ type: 'text', text: '<system-reminder>\nKB working agreement\n</system-reminder>' }])).toBe('KB working agreement')
  expect(originLabel({ kind: 'hook', event: 'SessionStart' })).toBe('hook SessionStart')
  expect(originLabel({ kind: 'plugin', event: 'prompt.submit' })).toBe('plugin (prompt.submit)')
  expect(originLabel({ kind: 'peer' })).toBe('peer')
  expect(originLabel(undefined)).toBe('engine')
})

test('the Audit tab: a push and how it was approved, a refusal, injected context, a compaction', async ($, on) => {
  const onAny = on as unknown as (event: string, matcher: object, hook: (...a: never[]) => object) => void
  const callAny = $.tool.call as unknown as (input: object) => Promise<unknown>
  const checkAny = $.tool.check as unknown as (input: object) => Promise<unknown>
  const appendAny = $.session.append as unknown as (input: object) => Promise<unknown>
  const compactAny = $.session.compact as unknown as (input: object) => Promise<unknown>

  onAny('tool.check', { tool: 'Bash' }, (_$: never, e: { input: { command: string } }) =>
    e.input.command.startsWith('rm ') ? { decision: 'deny', rule: 'Bash(rm:*)' } : { decision: 'allow', rule: 'Bash(git push:*)' },
  )
  onAny('tool.check', { tool: 'mcp__production_uk_cbtote__execute_sql' }, () => ({ decision: 'ask', reason: 'needs approval' }))
  onAny('tool.call', { tool: 'Bash' }, (_$: never, e: { command: string }) =>
    e.command.startsWith('rm ') ? { deny: 'Permission to use Bash with command rm -rf build has been denied.' } : { result: {}, text: 'pushed' },
  )
  onAny('tool.call', { tool: 'mcp__production_uk_cbtote__execute_sql' }, () => ({ result: {}, text: '[]' }))
  onAny('session.compact', {}, () => ({ messages: [{ role: 'user', text: 'Summary of the work so far', toolUses: [] }], tokensBefore: 180_000, tokensAfter: 12_000 }))

  const run = async (tool: string, id: string, input: Record<string, unknown>) => {
    await checkAny({ tool, input, tool_use_id: id })
    await callAny({ tool, tool_use_id: id, ...input })
  }
  await run('Bash', 't1', { command: 'git push -u origin mods/23' })
  await run('Bash', 't2', { command: 'rm -rf build' })
  await run('mcp__production_uk_cbtote__execute_sql', 't3', { sql: 'SELECT 1' })

  const reminder = {
    door: 'hook-context',
    message: { type: 'attachment', name: 'hook_additional_context', role: 'user', isMeta: true, content: [{ type: 'text', text: '<system-reminder>Colossus KB: technical/workflow</system-reminder>' }] },
    origin: { kind: 'hook', event: 'SessionStart' },
  }
  await appendAny({ ...reminder, uuid: 'u1' })
  await appendAny({ ...reminder, uuid: 'u2' })
  // The person's own prompt is the chat's: not recorded.
  await appendAny({ door: 'prompt', message: { type: 'user', role: 'user', content: [{ type: 'text', text: 'my own prompt' }] }, origin: { kind: 'composer' }, uuid: 'u3' })
  await compactAny({ trigger: 'auto', messages: [{ role: 'user', text: 'the work so far', toolUses: [] }] })

  const ui = await $.ui.mount({ plugin: 'agent-watch', surface: 'desktop', ...PANE })
  await ui.press({ key: 'tab-audit' })

  // Outward actions: the push with the rule that let it run, the refused rm in red, the production query asked about.
  expect(await ui.find({ type: 'Text', text: 'Outward actions' })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /git push -u origin mods\/23/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: 'rule Bash(git push:*)' })).toBeDefined()
  expect((await ui.find({ type: 'Text', text: 'destroy' }))?.props).toMatchObject({ color: 'error' })
  expect(await ui.find({ type: 'Text', text: /production_uk_cbtote/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: 'asked → approved' })).toBeDefined()

  // Approvals: the tally, and the calls that were asked about or refused.
  expect(await ui.find({ type: 'Text', text: /by rule ×1/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /asked ×1/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /denied ×1/ })).toBeDefined()

  // Injected: the SessionStart hook's output once, counted twice; the compaction; not the person's prompt.
  expect(await ui.find({ type: 'Text', text: 'hook SessionStart' })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /Colossus KB: technical\/workflow/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: / ×2/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /180\.0k → 12\.0k tokens/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /my own prompt/ })).toBeUndefined()
  await ui.unmount()
})

test('a busy Audit tab stays under the 100,000-character tree limit', { timeoutMs: 120000 }, async ($, on) => {
  const onAny = on as unknown as (event: string, matcher: object, hook: () => object) => void
  const callAny = $.tool.call as unknown as (input: object) => Promise<unknown>
  const appendAny = $.session.append as unknown as (input: object) => Promise<unknown>
  onAny('tool.call', { tool: 'Bash' }, () => ({ result: {}, text: 'ok' }))
  const long = 'with a long branch name and a remote spelled out in full '.repeat(4)
  for (let i = 0; i < 220; i += 1) await callAny({ tool: 'Bash', tool_use_id: `p${i}`, command: `git push origin ${i} ${long}` })
  for (let i = 0; i < 170; i += 1) {
    await appendAny({
      door: 'attachment',
      message: { type: 'attachment', name: `reminder_${i}`, role: 'user', isMeta: true, content: [{ type: 'text', text: `${i} ${'x'.repeat(600)}` }] },
      origin: { kind: 'engine' },
      uuid: `r${i}`,
    })
  }

  for (const surface of ['desktop', 'terminal'] as const) {
    const ui = await $.ui.mount({ plugin: 'agent-watch', surface, ...PANE })
    await ui.press({ key: 'tab-audit' })
    expect(JSON.stringify(await ui.drawn()).length).toBeLessThan(100_000)
    expect(await ui.find({ type: 'Text', text: /git push origin 219 / })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /older not shown/ })).toBeDefined()
    await ui.unmount()
  }
})
