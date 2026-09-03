import { describe, expect, it, vi } from 'vitest'

import {
  buildTrayMenuTemplate,
  createTrayRuntime,
  DEFAULT_TRAY_LABELS,
  normalizeResidency,
  type ResidencySnapshot,
  shouldHideOnClose,
  type TrayLike,
  type TrayMenuItem,
  trayTooltip
} from './tray-runtime'

function body(overrides: Record<string, unknown> = {}) {
  return {
    llm: { label: 'Language model', loaded: [], selected: 'qwen/qwen3.5-9b', warming: false },
    stt: { label: 'Speech recognition', loaded: [], selected: 'large-v3-turbo', warming: false },
    total: 0,
    tts: { label: 'Voice', loaded: [], selected: 'kokoro', warming: false },
    ...overrides
  }
}

function snapshotWith(overrides: Record<string, unknown> = {}): ResidencySnapshot {
  const parsed = normalizeResidency(body(overrides))

  if (!parsed) {
    throw new Error('fixture is not a valid snapshot')
  }

  return parsed
}

function labelsOf(template: TrayMenuItem[]) {
  return template.map(item => (item.type === 'separator' ? '---' : item.label))
}

function findItem(template: TrayMenuItem[], label: string) {
  const found = template.find(item => item.label === label)

  if (!found) {
    throw new Error(`no menu row labelled "${label}" in: ${labelsOf(template).join(' | ')}`)
  }

  return found
}

const actions = () => ({
  onQuit: vi.fn(),
  onShow: vi.fn(),
  onUnload: vi.fn(),
  onUnloadAll: vi.fn()
})

describe('normalizeResidency', () => {
  it('parses a well-formed body and counts what is loaded', () => {
    const snapshot = normalizeResidency(
      body({
        llm: {
          label: 'Language model',
          loaded: [{ id: 'qwen/qwen3.5-9b', label: 'qwen/qwen3.5-9b' }],
          selected: 'qwen/qwen3.5-9b',
          warming: false
        },
        tts: { label: 'Voice', loaded: [{ id: 'kokoro', label: 'Kokoro' }], selected: 'kokoro', warming: false }
      })
    )

    expect(snapshot?.total).toBe(2)
    expect(snapshot?.tts.loaded[0]).toEqual({ id: 'kokoro', label: 'Kokoro' })
  })

  it('recomputes the total instead of trusting the body', () => {
    const snapshot = normalizeResidency(
      body({ total: 99, tts: { label: 'Voice', loaded: [{ id: 'kokoro' }], selected: '', warming: false } })
    )

    expect(snapshot?.total).toBe(1)
    // A row without a label still needs a name — fall back to its id.
    expect(snapshot?.tts.loaded[0].label).toBe('kokoro')
  })

  it('rejects a body that is not a residency snapshot', () => {
    // An older/remote backend answers 404-shaped JSON or a plain error object.
    // Guessing at it would paint a menu of models that are not there.
    expect(normalizeResidency(null)).toBeNull()
    expect(normalizeResidency({ detail: 'Not Found' })).toBeNull()
    expect(normalizeResidency({ ...body(), tts: undefined })).toBeNull()
  })

  it('drops entries with no id — an unload could not name them', () => {
    const snapshot = normalizeResidency(
      body({ tts: { label: 'Voice', loaded: [{ label: 'ghost' }, { id: 'kokoro' }], selected: '', warming: false } })
    )

    expect(snapshot?.tts.loaded.map(entry => entry.id)).toEqual(['kokoro'])
  })
})

describe('buildTrayMenuTemplate', () => {
  it('always offers Open and Quit, even with no answer from the backend', () => {
    const template = buildTrayMenuTemplate(null, actions())

    expect(labelsOf(template)).toEqual([
      DEFAULT_TRAY_LABELS.open,
      '---',
      DEFAULT_TRAY_LABELS.unavailable,
      '---',
      DEFAULT_TRAY_LABELS.quit
    ])
    expect(findItem(template, DEFAULT_TRAY_LABELS.unavailable).enabled).toBe(false)
  })

  it('says so plainly when nothing is resident', () => {
    const template = buildTrayMenuTemplate(snapshotWith(), actions())

    expect(labelsOf(template)).toContain(DEFAULT_TRAY_LABELS.noModels)
    // Nothing to drop — no "unload all" to click.
    expect(labelsOf(template)).not.toContain(DEFAULT_TRAY_LABELS.unloadAll)
  })

  it('lists one row per loaded model, in speech-chain order', () => {
    const template = buildTrayMenuTemplate(
      snapshotWith({
        llm: { label: 'Language model', loaded: [{ id: 'qwen/qwen3.5-9b' }], selected: '', warming: false },
        stt: {
          label: 'Speech recognition',
          loaded: [{ id: 'large-v3-turbo', label: 'Whisper Large-v3 Turbo' }],
          selected: '',
          warming: false
        },
        tts: { label: 'Voice', loaded: [{ id: 'kokoro', label: 'Kokoro' }], selected: '', warming: false }
      }),
      actions()
    )

    expect(labelsOf(template)).toEqual([
      DEFAULT_TRAY_LABELS.open,
      '---',
      `${DEFAULT_TRAY_LABELS.loadedHeader} — 3`,
      'Speech recognition: Whisper Large-v3 Turbo',
      'Voice: Kokoro',
      'Language model: qwen/qwen3.5-9b',
      DEFAULT_TRAY_LABELS.unloadAll,
      '---',
      DEFAULT_TRAY_LABELS.quit
    ])
  })

  it('unloads exactly the model whose submenu was used', () => {
    const handlers = actions()

    const template = buildTrayMenuTemplate(
      snapshotWith({
        tts: {
          label: 'Voice',
          loaded: [
            { id: 'kokoro', label: 'Kokoro' },
            { id: 'chatterbox', label: 'Chatterbox' }
          ],
          selected: 'kokoro',
          warming: false
        }
      }),
      handlers
    )

    const row = findItem(template, 'Voice: Chatterbox')

    // The action lives in a submenu, not on the row: a bare row gives no hint
    // that clicking it drops the model, and a mis-click costs a cold reload.
    expect(row.click).toBeUndefined()
    row.submenu?.[0].click?.()

    expect(handlers.onUnload).toHaveBeenCalledWith('tts', 'chatterbox')
  })

  it('shows a warming category so a load in flight does not read as failure', () => {
    const template = buildTrayMenuTemplate(
      snapshotWith({ stt: { label: 'Speech recognition', loaded: [], selected: '', warming: true } }),
      actions()
    )

    expect(labelsOf(template)).toContain(`Speech recognition: ${DEFAULT_TRAY_LABELS.warming}`)
  })

  it('wires Open, Unload all and Quit to their handlers', () => {
    const handlers = actions()

    const template = buildTrayMenuTemplate(
      snapshotWith({ tts: { label: 'Voice', loaded: [{ id: 'kokoro' }], selected: '', warming: false } }),
      handlers
    )

    findItem(template, DEFAULT_TRAY_LABELS.open).click?.()
    findItem(template, DEFAULT_TRAY_LABELS.unloadAll).click?.()
    findItem(template, DEFAULT_TRAY_LABELS.quit).click?.()

    expect(handlers.onShow).toHaveBeenCalledTimes(1)
    expect(handlers.onUnloadAll).toHaveBeenCalledTimes(1)
    expect(handlers.onQuit).toHaveBeenCalledTimes(1)
  })
})

describe('trayTooltip', () => {
  it('answers whether the hidden app is holding anything', () => {
    expect(trayTooltip('The Fool', null)).toBe('The Fool')
    expect(trayTooltip('The Fool', snapshotWith())).toBe('The Fool')
    expect(
      trayTooltip('The Fool', snapshotWith({ tts: { label: 'Voice', loaded: [{ id: 'kokoro' }], selected: '', warming: false } }))
    ).toBe('The Fool — 1 model loaded')
  })
})

describe('shouldHideOnClose', () => {
  it('hides only while a tray exists and no quit is under way', () => {
    expect(shouldHideOnClose({ quitting: false, trayReady: true })).toBe(true)
    expect(shouldHideOnClose({ quitting: true, trayReady: true })).toBe(false)
    // No tray (a Linux desktop with no StatusNotifier host): hiding would
    // strand a running app with no way to reach or quit it.
    expect(shouldHideOnClose({ quitting: false, trayReady: false })).toBe(false)
  })
})

function fakeTray() {
  const listeners = new Map<string, (...args: any[]) => void>()
  let destroyed = false

  const tray: TrayLike = {
    destroy: vi.fn(() => void (destroyed = true)),
    isDestroyed: () => destroyed,
    on: vi.fn((event: string, listener: (...args: any[]) => void) => void listeners.set(event, listener)),
    popUpContextMenu: vi.fn(),
    setContextMenu: vi.fn(),
    setToolTip: vi.fn()
  }

  return { emit: (event: string) => listeners.get(event)?.(), listeners, tray }
}

function runtimeHarness(overrides: Record<string, any> = {}) {
  const { emit, tray } = fakeTray()

  // Overrides land in the SAME object the harness hands back. Building the
  // deps separately let a test override `fetchResidency` and then assert
  // against the harness's unused default — a green-looking test of nothing.
  const deps = {
    buildMenu: vi.fn((template: TrayMenuItem[]) => template),
    createTray: () => tray,
    fetchResidency: vi.fn(async () => body()),
    onQuit: vi.fn(),
    onShow: vi.fn(),
    unload: vi.fn(async () => ({ total: 1 })),
    ...overrides
  }

  return { ...deps, emit, runtime: createTrayRuntime(deps), tray }
}

describe('createTrayRuntime', () => {
  it('reports not-ready when the platform has no tray to create', async () => {
    const failing = createTrayRuntime({
      buildMenu: vi.fn(),
      createTray: () => {
        throw new Error('no StatusNotifier host')
      },
      fetchResidency: vi.fn(async () => body()),
      onQuit: vi.fn(),
      onShow: vi.fn(),
      unload: vi.fn(async () => ({}))
    })

    expect(failing.start()).toBe(false)
    expect(failing.isReady()).toBe(false)
  })

  it('reads residency on start and answers the click that shows the window', async () => {
    const harness = runtimeHarness()

    expect(harness.runtime.start()).toBe(true)
    await harness.runtime.refresh()

    expect(harness.runtime.lastSnapshot()?.total).toBe(0)
    expect(harness.tray.setToolTip).toHaveBeenCalledWith('The Fool')

    harness.emit('click')
    expect(harness.onShow).toHaveBeenCalledTimes(1)
  })

  it('opens the menu immediately and refreshes behind it', async () => {
    const harness = runtimeHarness()
    harness.runtime.start()
    await harness.runtime.refresh()
    harness.fetchResidency.mockClear()

    harness.emit('right-click')

    // The menu is popped up from the cached snapshot in the same tick: waiting
    // on a backend round trip first reads as a click that did nothing.
    expect(harness.tray.popUpContextMenu).toHaveBeenCalledTimes(1)
    expect(harness.fetchResidency).toHaveBeenCalledTimes(1)
    await harness.runtime.refresh()
  })

  it('does not attach a context menu where the menu is built per click', async () => {
    // Windows/macOS: an attached menu is what Electron shows on right-click,
    // so leaving one there would display a stale copy instead of the fresh one.
    const harness = runtimeHarness()
    harness.runtime.start()
    await harness.runtime.refresh()

    expect(harness.tray.setContextMenu).not.toHaveBeenCalled()
  })

  it('keeps an attached menu current when the platform cannot build one per click', async () => {
    const harness = runtimeHarness({ refreshIntervalMs: 30_000 })
    harness.runtime.start()
    await harness.runtime.refresh()

    expect(harness.tray.setContextMenu).toHaveBeenCalled()
    harness.runtime.destroy()
  })

  it('coalesces overlapping reads into one backend request', async () => {
    const harness = runtimeHarness()
    harness.runtime.start()

    await Promise.all([harness.runtime.refresh(), harness.runtime.refresh(), harness.runtime.refresh()])

    // start() already issued one; the three above must not add three more.
    expect(harness.fetchResidency).toHaveBeenCalledTimes(1)
  })

  it('unloads from its own menu and re-reads so the row stops being offered', async () => {
    const loaded = body({
      tts: { label: 'Voice', loaded: [{ id: 'kokoro', label: 'Kokoro' }], selected: 'kokoro', warming: false }
    })

    const harness = runtimeHarness({ fetchResidency: vi.fn(async () => loaded) })

    harness.runtime.start()
    await harness.runtime.refresh()

    harness.emit('right-click')
    const template = harness.buildMenu.mock.calls.at(-1)?.[0] as TrayMenuItem[]
    await harness.runtime.refresh()
    harness.fetchResidency.mockClear()

    findItem(template, 'Voice: Kokoro').submenu?.[0].click?.()

    await vi.waitFor(() => expect(harness.unload).toHaveBeenCalledWith('tts', 'kokoro'))
    // The snapshot the menu was built from is now wrong -- re-read, or the next
    // right-click still offers to unload a model that is already gone.
    await vi.waitFor(() => expect(harness.fetchResidency).toHaveBeenCalled())
  })

  it('survives a backend that cannot answer', async () => {
    const harness = runtimeHarness({
      fetchResidency: vi.fn(async () => {
        throw new Error('backend is not running')
      })
    })

    harness.runtime.start()
    await harness.runtime.refresh()

    expect(harness.runtime.lastSnapshot()).toBeNull()
    // The rows that must never depend on the backend still work.
    expect(labelsOf(buildTrayMenuTemplate(harness.runtime.lastSnapshot(), actions()))).toContain(
      DEFAULT_TRAY_LABELS.quit
    )
  })

  it('destroys the icon exactly once and stops being ready', async () => {
    const harness = runtimeHarness()
    harness.runtime.start()
    await harness.runtime.refresh()

    harness.runtime.destroy()
    harness.runtime.destroy()

    expect(harness.tray.destroy).toHaveBeenCalledTimes(1)
    expect(harness.runtime.isReady()).toBe(false)
  })
})
