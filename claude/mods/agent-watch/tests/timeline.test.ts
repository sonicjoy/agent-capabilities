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

test('each kind of action has its own colour, and a failed one is red', async ($, on) => {
  // Loosely typed: the session's whole MCP tool union is too deep for tsc to narrow here.
  const onAny = on as unknown as (event: string, matcher: object, hook: () => object) => void
  const callAny = $.tool.call as unknown as (input: object) => Promise<unknown>
  onAny('tool.call', { tool: 'Read' }, () => ({ result: {}, text: 'a\nb' }))
  onAny('tool.call', { tool: 'Edit' }, () => ({ result: {}, text: 'edited' }))
  onAny('tool.call', { tool: 'Grep' }, () => ({ result: {}, text: 'no matches', isError: true }))
  onAny('tool.call', { tool: 'Skill' }, () => ({ result: {}, text: 'loaded' }))

  await callAny({ tool: 'Read', file_path: 'a.ts' })
  await callAny({ tool: 'Edit', file_path: 'a.ts', old_string: 'a', new_string: 'b' })
  await callAny({ tool: 'Grep', pattern: 'nothing' })
  await callAny({ tool: 'Skill', skill: 'knowledge' })

  const ui = await $.ui.mount({ plugin: 'agent-watch', surface: 'desktop', ...PANE })
  const colorOf = async (action: string) => ((await ui.find({ type: 'Text', text: action }))?.props as { color?: string })?.color
  expect(await colorOf('Read')).toBe('suggestion')
  expect(await colorOf('Update')).toBe('success')
  expect(await colorOf('Search')).toBe('error')
  expect(await colorOf('Skill')).toBe('merged')
  await ui.unmount()
})
