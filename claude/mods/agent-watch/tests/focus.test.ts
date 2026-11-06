import { expect, test } from 'claude-code/testing'

const PANE = {
  component: 'Pane',
  requestId: 'agent-watch',
  props: {
    title: 'Agent watch',
    isFocused: true,
    bodyColumns: 100,
    placement: 'dock',
    scroll: { offset: 0, bodyRows: 40 },
    view: {},
  },
} as const

test('the focus ring reaching a tab selects it, so a click that only focuses still switches', async ($, on) => {
  // The engine's focus ring, stood in for: a move lands where it was asked.
  const onAny = on as unknown as (event: string, hook: () => unknown) => void
  onAny('ui.focus', () => ({}))
  const focusOn = $.ui.focus as unknown as (args: { requestId: string; key: string }) => Promise<unknown>

  const ui = await $.ui.mount({ plugin: 'agent-watch', surface: 'desktop', ...PANE })
  expect(await ui.find({ type: 'Text', text: /Nothing yet/ })).toBeDefined()

  await focusOn({ requestId: 'agent-watch', key: 'tab-files' })
  expect(await ui.find({ type: 'Text', text: /Waiting for the agent to write a file/ })).toBeDefined()

  await focusOn({ requestId: 'agent-watch', key: 'tab-agents' })
  expect(await ui.find({ key: 'agent-main' })).toBeDefined()

  // An agent button the same way; Clear only by its press.
  await focusOn({ requestId: 'agent-watch', key: 'agent-main' })
  expect((await ui.find({ key: 'agent-main' }))?.props).toMatchObject({ variant: 'primary' })
  await ui.unmount()
})
