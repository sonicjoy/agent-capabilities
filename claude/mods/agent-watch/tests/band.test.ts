import { expect, test } from 'claude-code/testing'

const BAND = { component: 'AbovePrompt', requestId: 'band', props: { hasSurvey: false } }

test('the button above the prompt opens the pane, and hides while it is open', async ($, on) => {
  // The test stands in for the engine's panes: ui.open seats the pane, ui.panes reports it.
  let isShown = false
  const onAny = on as unknown as (event: string, hook: () => unknown) => void
  onAny('ui.open', () => {
    isShown = true

    return { value: { isPlaced: true } }
  })
  // Beneath the band the engine draws nothing of its own: what the band hands back when it hides.
  const onRender = on as unknown as (event: string, matcher: object, hook: () => unknown) => void
  onRender('ui.render', { component: 'AbovePrompt' }, () => ({ type: 'Box', props: { key: 'engine-band' }, children: [] }))
  onAny('ui.panes', () => ({ value: isShown ? [{ id: 'agent-watch', title: 'Agent watch', isShown: true }] : [] }))

  const mount = $.ui.mount as unknown as (target: object) => ReturnType<typeof $.ui.mount>
  // On the terminal: shown while the pane is closed; a press opens the pane and hides it.
  const ui = await mount({ plugin: 'agent-watch', surface: 'terminal', ...BAND })
  expect(await ui.find({ key: 'open-agent-watch' })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /Idle/ })).toBeDefined()
  await ui.press({ key: 'open-agent-watch' })
  expect(isShown).toBe(true)
  expect(await ui.find({ key: 'open-agent-watch' })).toBeUndefined()
  expect(await ui.find({ key: 'engine-band' })).toBeDefined()
  await ui.unmount()

  // The desktop's band agrees: the pane is open, so no button.
  const desk = await mount({ plugin: 'agent-watch', surface: 'desktop', ...BAND })
  expect(await desk.find({ key: 'open-agent-watch' })).toBeUndefined()
  await desk.unmount()
})

test('the button above the prompt shows the Timeline\'s newest row', async ($, on) => {
  const onAny = on as unknown as (event: string, matcher: object, hook: () => object) => void
  const callAny = $.tool.call as unknown as (input: object) => Promise<unknown>
  onAny('tool.call', { tool: 'Read' }, () => ({ result: {}, text: 'a' }))
  onAny('tool.call', { tool: 'Edit' }, () => ({ result: {}, text: 'edited' }))

  const mount = $.ui.mount as unknown as (target: object) => ReturnType<typeof $.ui.mount>
  // Nothing has happened yet: only the counts.
  const empty = await mount({ plugin: 'agent-watch', surface: 'terminal', ...BAND })
  expect(await empty.find({ key: 'band-last' })).toBeUndefined()
  await empty.unmount()

  await callAny({ tool: 'Read', file_path: 'a.ts' })
  await callAny({ tool: 'Edit', file_path: 'b.ts', old_string: 'a', new_string: 'b' })

  // Named as the Timeline names it: Edit reads as Update.
  const ui = await mount({ plugin: 'agent-watch', surface: 'terminal', ...BAND })
  expect(await ui.find({ key: 'band-last' })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: 'Update' })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /b\.ts/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /a\.ts/ })).toBeUndefined()
  await ui.unmount()
})

test('the band marks a subagent row as one', async ($, on) => {
  const onAny = on as unknown as (event: string, matcher: object, hook: () => object) => void
  const callAny = $.tool.call as unknown as (input: object) => Promise<unknown>
  onAny('tool.call', { tool: 'Read' }, () => ({ result: {}, text: 'a' }))
  const mount = $.ui.mount as unknown as (target: object) => ReturnType<typeof $.ui.mount>

  await callAny({ tool: 'Read', file_path: 'sub.ts', agentId: 'abc123' })
  const ui = await mount({ plugin: 'agent-watch', surface: 'terminal', ...BAND })
  expect(JSON.stringify(await ui.find({ key: 'band-last' }))).toContain('↳ Read')
  await ui.unmount()
})
