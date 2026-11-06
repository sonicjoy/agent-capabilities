import { expect, test } from 'claude-code/testing'

const PANE = {
  component: 'Pane',
  requestId: 'agent-watch',
  props: {
    title: 'Agent watch',
    isFocused: false,
    bodyColumns: 100,
    placement: 'dock',
    scroll: { offset: 0, bodyRows: 40 },
    view: {},
  },
} as const

test('Timeline sums up each call; Agents shows what the chat does not: terminals, MCP, skills, lookups', async ($, on) => {
  // Loosely typed: the session's whole MCP tool union is too deep for tsc to narrow here.
  const onAny = on as unknown as (event: string, matcher: object, hook: () => object) => void
  const callAny = $.tool.call as unknown as (input: object) => Promise<unknown>
  onAny('tool.call', { tool: 'Bash' }, () => ({ result: { stdout: 'hello' }, text: 'hello from echo' }))
  onAny('tool.call', { tool: 'mcp__neo4j-kb__read_neo4j_cypher' }, () => ({ result: {}, text: '[]' }))
  onAny('tool.call', { tool: 'Skill' }, () => ({ result: {}, text: 'loaded' }))

  await callAny({ tool: 'Bash', command: 'echo hello', description: 'Say hello' })
  await callAny({ tool: 'Bash', command: "python - <<'EOF'\nprint(1)\nEOF" })
  await callAny({ tool: 'mcp__neo4j-kb__read_neo4j_cypher', query: 'MATCH (n) RETURN n LIMIT 1' })
  await callAny({ tool: 'Skill', skill: 'knowledge' })
  await callAny({ tool: 'Bash', command: 'python skills/knowledge/kb.py read search --q "pool restart"', description: 'Look up pool restart' })

  for (const surface of ['terminal', 'desktop'] as const) {
    const ui = await $.ui.mount({ plugin: 'agent-watch', surface, ...PANE })
    // Four tabs, nothing else to press.
    expect(await ui.findAll({ type: 'Button' })).toHaveLength(4)
    expect(await ui.find({ key: 'clear' })).toBeUndefined()

    // Timeline: one row of four columns (time, action, about what, how long), and nothing more.
    expect(await ui.find({ type: 'Text', text: /^\d\d:\d\d:\d\d$/ })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: 'Bash' })).toBeDefined()
    // A command with a description reads as the description; one without, as the command.
    expect(await ui.find({ type: 'Text', text: 'Say hello' })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: 'echo hello' })).toBeUndefined()
    expect(await ui.find({ type: 'Text', text: /^\d+\.\ds$/ })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /hello from echo/ })).toBeUndefined()
    expect(await ui.find({ type: 'Text', text: /tool calls/ })).toBeUndefined()
    // The action is coloured by its kind: a shell command in the theme's bash colour.
    expect((await ui.find({ type: 'Text', text: 'Bash' }))?.props).toMatchObject({ color: 'bashBorder' })
    // A multi-line command keeps to one row: its first line, then an ellipsis.
    expect(await ui.find({ type: 'Text', text: "python - <<'EOF' …" })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /print\(1\)/ })).toBeUndefined()

    // Agents: one agent per page (main first), and none of the chat's own text.
    await ui.press({ key: 'tab-agents' })
    expect(await ui.find({ key: 'agent-all' })).toBeUndefined()
    expect((await ui.find({ key: 'agent-main' }))?.props).toMatchObject({ variant: 'primary' })
    expect(await ui.find({ type: 'Text', text: /no model requests seen yet/ })).toBeDefined()

    // The terminal it typed into: a fixed box of rows, each command after the shell's prompt, then its output.
    expect(await ui.find({ type: 'Text', text: 'Terminals' })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /^.* \$ $/ })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: 'echo hello' })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: 'hello from echo' })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: '# Say hello' })).toBeUndefined()

    // The MCP server it called, by tool; the skill it used; what it looked up in the KB.
    expect(await ui.find({ type: 'Text', text: 'neo4j-kb' })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /read_neo4j_cypher ×1/ })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: '/knowledge' })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: 'read search --q "pool restart"' })).toBeDefined()

    await ui.press({ key: 'tab-files' })
    expect(await ui.find({ type: 'Text', text: /changed/ })).toBeDefined()
    await ui.press({ key: 'tab-timeline' })
    await ui.unmount()
  }
})

test('an agent page shows its thinking, every terminal command in full, and the files it changed', async ($, on) => {
  const onAny = on as unknown as (event: string, matcher: object, hook: () => object) => void
  const callAny = $.tool.call as unknown as (input: object) => Promise<unknown>
  onAny('tool.call', { tool: 'Bash' }, () => ({ result: {}, text: Array.from({ length: 30 }, (_, i) => `line ${i}`).join('\n') }))
  onAny('tool.call', { tool: 'Write' }, () => ({ result: {}, text: 'written' }))
  for (let i = 0; i < 12; i += 1) await callAny({ tool: 'Bash', command: `echo ${i}`, description: `Step ${i}` })
  await callAny({ tool: 'Write', file_path: 'notes/plan.md', content: '# Plan\n' })

  const ui = await $.ui.mount({ plugin: 'agent-watch', surface: 'desktop', ...PANE })
  await ui.press({ key: 'tab-agents' })
  // A fixed box of 14 rows: the newest output, the prompt waiting at the end.
  expect(await ui.find({ type: 'Text', text: 'line 29' })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: '█' })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: 'echo 0' })).toBeUndefined()
  // No scrolling inside: no buttons, the box keeps to the newest rows.
  expect(await ui.find({ key: 'term-up:shell:bash' })).toBeUndefined()
  // The file it wrote, marked as a change.
  expect(await ui.find({ type: 'Text', text: 'File changes' })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /plan\.md$/ })).toBeDefined()
  await ui.unmount()
})

test('a long session stays under the 100,000-character tree limit, newest rows first', { timeoutMs: 60000 }, async ($, on) => {
  const onAny = on as unknown as (event: string, matcher: object, hook: () => object) => void
  const callAny = $.tool.call as unknown as (input: object) => Promise<unknown>
  onAny('tool.call', { tool: 'Bash' }, () => ({ result: {}, text: 'x'.repeat(2000) }))
  const long = 'a fairly long description of what this command is for, '.repeat(3)
  for (let i = 0; i < 250; i += 1) await callAny({ tool: 'Bash', command: `echo ${i}`, description: `${i}: ${long}` })

  for (const surface of ['desktop', 'terminal'] as const) {
    const ui = await $.ui.mount({ plugin: 'agent-watch', surface, ...PANE })
    for (const tabKey of ['tab-timeline', 'tab-agents', 'tab-files', 'tab-audit']) {
      await ui.press({ key: tabKey })
      expect(JSON.stringify(await ui.drawn()).length).toBeLessThan(100_000)
    }
    await ui.press({ key: 'tab-timeline' })
    expect(await ui.find({ type: 'Text', text: /^249: / })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /older rows not shown/ })).toBeDefined()
    await ui.unmount()
  }
})

test('the pane scrolls as panes do: no fixed height, no clipped area, all of the body there', async ($, on) => {
  const onAny = on as unknown as (event: string, matcher: object, hook: () => object) => void
  const callAny = $.tool.call as unknown as (input: object) => Promise<unknown>
  onAny('tool.call', { tool: 'Bash' }, () => ({ result: {}, text: 'ok' }))
  for (let i = 0; i < 60; i += 1) await callAny({ tool: 'Bash', command: `echo ${i}` })

  const short = { ...PANE, props: { ...PANE.props, scroll: { offset: 0, bodyRows: 20 } } }
  const ui = await $.ui.mount({ plugin: 'agent-watch', surface: 'terminal', ...short })
  const boxes = (await ui.findAll({ type: 'Box' })).map(box => box.props as Record<string, unknown>)
  expect(((await ui.drawn()) as { props?: { height?: number } }).props?.height).toBeUndefined()
  expect(boxes.some(box => box.overflow === 'hidden' || box.position === 'absolute')).toBe(false)
  expect(await ui.find({ type: 'Text', text: 'echo 59' })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: 'echo 0' })).toBeDefined()
  await ui.unmount()
})

test('what the mod keeps stays bounded, however big each call is', { timeoutMs: 60000 }, async ($, on) => {
  const onAny = on as unknown as (event: string, matcher: object, hook: () => object) => void
  const callAny = $.tool.call as unknown as (input: object) => Promise<unknown>
  onAny('tool.call', { tool: 'Bash' }, () => ({ result: {}, text: 'o'.repeat(50_000) }))
  // Every value the mod writes, as it writes it, passed on to the kit's own state.
  const written = new Map<string, unknown>()
  const onState = on as unknown as (event: string, hook: ($: unknown, e: { key: string; value: unknown }, next: (e: unknown) => unknown) => unknown) => void
  onState('state.set', (_$, e, next) => {
    written.set(e.key, e.value)

    return next(e)
  })
  // 300 calls, each with a huge command, description and output: more than the timeline keeps.
  for (let i = 0; i < 300; i += 1) {
    await callAny({ tool: 'Bash', command: `echo ${i} ${'c'.repeat(20_000)}`, description: 'd'.repeat(5_000) })
  }
  const kept = (written.get('events') ?? []) as { command?: string; note?: string; output?: string }[]
  expect(kept).toHaveLength(250)
  expect(kept[kept.length - 1]?.command?.startsWith('echo 299 ')).toBe(true)
  for (const ev of kept) {
    expect((ev.command ?? '').length).toBeLessThanOrEqual(4100)
    expect((ev.note ?? '').length).toBeLessThanOrEqual(400)
    expect((ev.output ?? '').length).toBeLessThanOrEqual(2001)
  }
  // About 1.6 MB at worst: 250 entries of a few kilobytes each.
  expect(JSON.stringify(kept).length).toBeLessThan(1_750_000)
})

test('terminals: a background agent is not one, and only the newest six draw, a row apart', async ($, on) => {
  const onAny = on as unknown as (event: string, matcher: object, hook: () => object) => void
  const callAny = $.tool.call as unknown as (input: object) => Promise<unknown>
  let shell = 0
  onAny('tool.call', { tool: 'Bash' }, () => ({ result: {}, text: `Command running in background with ID: sh${(shell += 1)}` }))
  onAny('tool.call', { tool: 'Agent' }, () => ({ result: {}, text: 'agentId: abc123 (internal ID - do not mention to user.)' }))
  await callAny({ tool: 'Agent', description: 'Review', prompt: 'x', run_in_background: true })
  for (let i = 0; i < 8; i += 1) await callAny({ tool: 'Bash', command: `sleep ${i}`, run_in_background: true })

  const ui = await $.ui.mount({ plugin: 'agent-watch', surface: 'desktop', ...PANE })
  await ui.press({ key: 'tab-agents' })
  expect(await ui.find({ type: 'Text', text: /^Background shell -/ })).toBeUndefined()
  expect(await ui.find({ key: 'term-bg:sh8' })).toBeDefined()
  expect(await ui.find({ key: 'term-bg:sh2' })).toBeUndefined()
  expect(await ui.find({ type: 'Text', text: /2 older terminals not shown/ })).toBeDefined()
  const boxes = await ui.find({ key: 'term-bg:sh8' })
  expect(boxes).toBeDefined()
  const column = (await ui.findAll({ type: 'Box' })).find(box => (box.props as { gap?: number }).gap === 1 && JSON.stringify(box).includes('term-bg:sh8'))
  expect(column).toBeDefined()
  await ui.unmount()
})

test('a subagent has its tab as it is spawned, named Alice, Bob, ... in the order they started', async ($, on) => {
  const onAny = on as unknown as (event: string, hook: (_: unknown, e: { description: string }) => object) => void
  // Beneath the mod's hook: the engine starting the subagent, answering its id.
  onAny('agent.spawn', (_, e) => ({ model: 'claude-opus-5-5', agentId: e.description === 'Second' ? 'sub-2' : 'sub-1' }))
  const spawnAny = $.agent.spawn as unknown as (input: object) => Promise<unknown>
  await spawnAny({ subagentType: 'general-purpose', description: 'Audit season-stat merge for the new feed', prompt: 'x' })
  await spawnAny({ subagentType: 'Explore', description: 'Second', prompt: 'y' })

  const ui = await $.ui.mount({ plugin: 'agent-watch', surface: 'desktop', ...PANE })
  await ui.press({ key: 'tab-agents' })
  // Before any step or tool call of their own.
  const label = async (key: string) => String(((await ui.find({ key }))?.props as { label?: string } | undefined)?.label)
  expect(await label('agent-sub-1')).toBe('● Alice')
  expect(await label('agent-sub-2')).toBe('● Bob')
  // The picked one's card says which it is, and what it does.
  await ui.press({ key: 'agent-sub-2' })
  expect(await ui.find({ type: 'Text', text: 'Bob · Explore' })).toBeDefined()
  await ui.unmount()
})

test('past MAX_AGENTS, a tab keeps its name, and a dropped subagent the list still has stays dropped', async ($, on) => {
  const onAny = on as unknown as (event: string, hook: (_: unknown, e: { description: string }) => object) => void
  type Listed = { id: string; type: string; description: string; status: string }
  const listed: Listed[] = []
  onAny('agent.spawn', (_, e) => ({ model: 'claude-opus-5-5', agentId: `sub-${e.description}` }))
  // The engine's list keeps every agent, the dropped ones too.
  onAny('agent.list', () => ({ value: listed }))
  const spawnAny = $.agent.spawn as unknown as (input: object) => Promise<unknown>
  const turnAny = $.turn.complete as unknown as (input: object) => Promise<unknown>
  for (let i = 1; i <= 52; i += 1) {
    listed.push({ id: `sub-${i}`, type: 'general-purpose', description: String(i), status: 'completed' })
    await spawnAny({ subagentType: 'general-purpose', description: String(i), prompt: 'x' })
    await turnAny({ agentId: `sub-${i}`, answer: 'done', durationMs: 1 }).catch(() => undefined)
  }

  const ui = await $.ui.mount({ plugin: 'agent-watch', surface: 'desktop', ...PANE })
  await ui.press({ key: 'tab-agents' })
  const label = async (key: string) => ((await ui.find({ key }))?.props as { label?: string } | undefined)?.label
  // The two oldest went; the rest keep the names they started with.
  expect(await label('agent-sub-1')).toBeUndefined()
  expect(await label('agent-sub-2')).toBeUndefined()
  expect(await label('agent-sub-4')).toMatch(/Dexter$/)
  expect(await label('agent-sub-27')).toMatch(/Alice 2$/)
  expect(await label('agent-sub-52')).toMatch(/Ziggy 2$/)
  await ui.unmount()
})
