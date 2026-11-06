import { expect, test } from 'claude-code/testing'

const BAND = { component: 'AbovePrompt', requestId: 'band', props: { hasSurvey: false } }

test('the pane opens itself when the agent starts working, not at session start', async ($, on) => {
  // The test stands in for the engine's panes: ui.open seats the pane, ui.panes reports it.
  let opens = 0
  let isShown = false
  const onAny = on as unknown as (event: string, hook: (...args: unknown[]) => unknown) => void
  onAny('ui.open', () => {
    opens += 1
    isShown = true

    return { value: { isPlaced: true } }
  })
  // Listed while open; isShown only while it is the pane in front.
  let isListed = false
  onAny('ui.panes', () => ({ value: isShown || isListed ? [{ id: 'agent-watch', title: 'Agent watch', isShown }] : [] }))
  onAny('command.register', () => ({ value: undefined }))
  onAny('session.start', (_$: unknown, e: unknown) => e)
  onAny('clock.every', () => ({ value: undefined }))
  onAny('turn.step', async function* (_$: unknown, e: unknown) {
    const { turnId, index } = e as { turnId: string; index: number }
    yield { kind: 'text', index: 0, text: 'working' }

    return { turnId, index, answer: 'working', toolUses: [] }
  })
  const raise = $ as unknown as {
    session: { start: (input: object) => Promise<unknown> }
    turn: { step: (input: object) => AsyncGenerator<unknown> }
  }
  const step = async (turnId: string) => {
    for await (const _ of raise.turn.step({ turnId, index: 0, model: 'claude-opus-5-5', messageCount: 1 })) void _
  }

  // A new session: no pane, the button instead.
  await raise.session.start({ cwd: 'C:/repo', surface: 'desktop', isInteractive: true })
  expect(opens).toBe(0)
  const mount = $.ui.mount as unknown as (target: object) => ReturnType<typeof $.ui.mount>
  const band = await mount({ plugin: 'agent-watch', surface: 'desktop', ...BAND })
  expect(await band.find({ key: 'open-agent-watch' })).toBeDefined()
  await band.unmount()

  // The agent starts working, main and a subagent at the same moment: the pane opens, once.
  await Promise.all([step('t1'), step('t1-sub')])
  expect(opens).toBe(1)
  await step('t1')
  expect(opens).toBe(1)

  // Open but behind another pane (listed, not in front): the agent's steps leave it where it is.
  isShown = false
  isListed = true
  await step('t2')
  expect(opens).toBe(1)

  // Opening it by hand (the button) is the band test's; closing it is the person's, which the
  // test kit cannot raise: a pane the person closed stays closed until they open it again.
})
