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

test('the Files tab follows the agent: folders open themselves, the written file shows its change', async ($, on) => {
  // Loosely typed: the session's whole MCP tool union is too deep for tsc to narrow here.
  const onAny = on as unknown as (event: string, matcher: object, hook: () => object) => void
  const callAny = $.tool.call as unknown as (input: object) => Promise<unknown>
  onAny('tool.call', { tool: 'Write' }, () => ({ result: {}, text: 'written' }))
  onAny('tool.call', { tool: 'Edit' }, () => ({ result: {}, text: 'edited' }))

  const ui = await $.ui.mount({ plugin: 'agent-watch', surface: 'terminal', ...PANE })
  await ui.press({ key: 'tab-files' })
  expect(await ui.find({ type: 'Text', text: /Waiting for the agent to write a file/ })).toBeDefined()

  await callAny({ tool: 'Write', file_path: 'src/lib/util.ts', content: 'export const u = 1' })
  await callAny({ tool: 'Write', file_path: 'README.md', content: '# hi' })
  await callAny({ tool: 'Edit', file_path: 'src/app/main.ts', old_string: 'let x = 1', new_string: 'let x = 2' })

  for (const surface of ['terminal', 'desktop'] as const) {
    const view = surface === 'terminal' ? ui : await $.ui.mount({ plugin: 'agent-watch', surface, ...PANE })

    // Nothing to press or type: the four tabs are the only controls.
    expect(await view.findAll({ type: 'Button' })).toHaveLength(4)
    expect(await view.find({ type: 'Input' })).toBeUndefined()

    // Every folder on the way to a change opened by itself; the last write is the focused file.
    expect(await view.find({ type: 'Text', text: 'app' })).toBeDefined()
    expect(await view.find({ type: 'Text', text: 'lib' })).toBeDefined()
    expect(await view.find({ type: 'Text', text: 'util.ts' })).toBeDefined()
    // The preview's header, as the Files browser titles a file: its name, then its folder dimmed.
    expect(await view.find({ type: 'Text', text: /^main\.ts {2}src\/app · / })).toBeDefined()
    expect(await view.find({ type: 'Code', text: /-let x = 1\n\+let x = 2/ })).toBeDefined()
    expect(await view.find({ type: 'Text', text: /3 changed/ })).toBeDefined()
    if (surface !== 'terminal') await view.unmount()
  }
  await ui.unmount()
})

test('files outside the workspace sit in one group, their folder chain folded short', async ($, on) => {
  const onAny = on as unknown as (event: string, matcher: object, hook: () => object) => void
  const callAny = $.tool.call as unknown as (input: object) => Promise<unknown>
  onAny('tool.call', { tool: 'Write' }, () => ({ result: {}, text: 'written' }))

  await callAny({ tool: 'Write', file_path: 'C:/Users/me/.claude/dev-mods/abc/agent-watch/hooks/register.tsx', content: 'x' })

  const ui = await $.ui.mount({ plugin: 'agent-watch', surface: 'terminal', ...PANE })
  await ui.press({ key: 'tab-files' })
  expect(await ui.find({ type: 'Text', text: '(outside the workspace)' })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: 'C:/…/agent-watch/hooks' })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: 'register.tsx' })).toBeDefined()
  expect(await ui.find({ type: 'Code', text: /\+x/ })).toBeDefined()
  await ui.unmount()
})

test('folders open and close with centred triangles that sit level with the names', async ($, on) => {
  const onAny = on as unknown as (event: string, matcher: object, hook: () => object) => void
  const callAny = $.tool.call as unknown as (input: object) => Promise<unknown>
  onAny('tool.call', { tool: 'Write' }, () => ({ result: {}, text: 'ok' }))
  await callAny({ tool: 'Write', file_path: 'src/app/main.ts', content: 'x' })
  const ui = await $.ui.mount({
    plugin: 'agent-watch',
    surface: 'desktop',
    component: 'Pane',
    requestId: 'agent-watch',
    props: { title: 'Agent watch', isFocused: false, bodyColumns: 100, placement: 'dock', scroll: { offset: 0, bodyRows: 40 }, view: {} },
  })
  await ui.press({ key: 'tab-files' })
  expect(await ui.find({ type: 'Text', text: '▾ ' })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: '⌄ ' })).toBeUndefined()
  await ui.unmount()
})

test('a file shows no type icon and no change letter; the one being edited is highlighted', async ($, on) => {
  const onAny = on as unknown as (event: string, matcher: object, hook: () => object) => void
  const callAny = $.tool.call as unknown as (input: object) => Promise<unknown>
  onAny('tool.call', { tool: 'Write' }, () => ({ result: {}, text: 'ok' }))
  await callAny({ tool: 'Write', file_path: 'src/app/main.ts', content: 'x' })
  const ui = await $.ui.mount({
    plugin: 'agent-watch',
    surface: 'desktop',
    component: 'Pane',
    requestId: 'agent-watch',
    props: { title: 'Agent watch', isFocused: false, bodyColumns: 100, placement: 'dock', scroll: { offset: 0, bodyRows: 40 }, view: {} },
  })
  await ui.press({ key: 'tab-files' })
  // The file just written is the one in focus: highlighted, a bar in its change colour.
  const bars = (await ui.findAll({ type: 'Text' })).filter(text => (text.props as { inverse?: boolean }).inverse === true)
  expect(bars).toHaveLength(1)
  expect(JSON.stringify(bars[0])).toContain(' main.ts ')
  for (const gone of [/^ ?A$/, /^ ?M$/, /^TS$/, /^▪ $/]) expect(await ui.find({ type: 'Text', text: gone })).toBeUndefined()
  await ui.unmount()
})

test('a file git cannot count shows the lines its own edits changed', async ($, on) => {
  const onAny = on as unknown as (event: string, matcher: object, hook: () => object) => void
  const callAny = $.tool.call as unknown as (input: object) => Promise<unknown>
  onAny('tool.call', { tool: 'Write' }, () => ({ result: {}, text: 'ok' }))
  onAny('tool.call', { tool: 'Edit' }, () => ({ result: {}, text: 'ok' }))
  // Outside any repo: a new file of 4 lines, then an edit turning 1 line into 2.
  await callAny({ tool: 'Write', file_path: 'C:/elsewhere/notes/plan.md', content: 'a\nb\nc\nd\n' })
  await callAny({ tool: 'Edit', file_path: 'C:/elsewhere/notes/plan.md', old_string: 'b', new_string: 'b1\nb2' })
  const ui = await $.ui.mount({
    plugin: 'agent-watch',
    surface: 'desktop',
    component: 'Pane',
    requestId: 'agent-watch',
    props: { title: 'Agent watch', isFocused: false, bodyColumns: 100, placement: 'dock', scroll: { offset: 0, bodyRows: 40 }, view: {} },
  })
  await ui.press({ key: 'tab-files' })
  expect(await ui.find({ type: 'Text', text: ' +6' })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: ' −1' })).toBeDefined()
  await ui.unmount()
})
