/**
 * System tray: what is loaded, drop it, and close-to-tray.
 *
 * Why the app hides instead of quitting
 * -------------------------------------
 * Closing the window used to end the process, and the next launch paid the
 * whole cold start again — backend boot, then a cold model load on the first
 * sentence (measured on the user's card: 6,94 s for the first transcription,
 * 24,17 s for a cold Kokoro sentence). Hiding to the tray keeps the warm
 * process and turns the next launch into a window show.
 *
 * That trade only holds if the user can see — and drop — what the running app
 * is holding. Three categories share one GPU (`fool/residency.py`), and none
 * of them was visible anywhere: the app looked closed while a 6,5 GB model sat
 * in VRAM. So the tray menu is not decoration; it is the other half of
 * close-to-tray.
 *
 * The menu is built fresh on every right-click rather than polled: a menu
 * nobody opened must cost nothing, which is the whole point of this change.
 *
 * Quit unloads first
 * ------------------
 * Killing the backend takes whisper and the engine subprocesses with it (the
 * desktop tree-kills the backend). LM Studio does NOT go: it is a separate
 * application and never releases the model on its own. So quitting asks the
 * backend to unload everything BEFORE the teardown that would remove the only
 * process able to make that call.
 */

export const RESIDENCY_KINDS = ['stt', 'tts', 'llm'] as const

export type ResidencyKind = (typeof RESIDENCY_KINDS)[number]

export interface ResidencyEntry {
  id: string
  label: string
}

export interface ResidencyCategory {
  label: string
  loaded: ResidencyEntry[]
  selected: string
  warming: boolean
}

export type ResidencySnapshot = Record<ResidencyKind, ResidencyCategory> & { total: number }

/** A menu row, shaped like Electron's `MenuItemConstructorOptions`. */
export interface TrayMenuItem {
  label?: string
  enabled?: boolean
  type?: 'separator'
  click?: () => void
  submenu?: TrayMenuItem[]
}

export interface TrayMenuActions {
  onShow(): void
  onUnload(kind: ResidencyKind, id: string): void
  onUnloadAll(): void
  onQuit(): void
}

const KIND_FALLBACK_LABELS: Record<ResidencyKind, string> = {
  llm: 'Language model',
  stt: 'Speech recognition',
  tts: 'Voice'
}

function asEntries(raw: unknown): ResidencyEntry[] {
  if (!Array.isArray(raw)) {
    return []
  }

  return raw
    .map(row => {
      const id = typeof (row as any)?.id === 'string' ? (row as any).id : ''
      const label = typeof (row as any)?.label === 'string' && (row as any).label ? (row as any).label : id

      return { id, label }
    })
    .filter(entry => entry.id)
}

/**
 * Parse a `/api/fool/runtime/residency` body, or `null` when it isn't one.
 *
 * Defensive on purpose: a desktop build can outlive the backend it talks to
 * (a remote host, or a user-pinned older CLI). A menu that throws on an
 * unexpected shape would take the *quit item* down with it — the one row that
 * must always work.
 */
export function normalizeResidency(raw: unknown): null | ResidencySnapshot {
  if (!raw || typeof raw !== 'object') {
    return null
  }

  const source = raw as Record<string, any>
  const categories = {} as Record<ResidencyKind, ResidencyCategory>

  for (const kind of RESIDENCY_KINDS) {
    const node = source[kind]

    if (!node || typeof node !== 'object') {
      return null
    }

    categories[kind] = {
      label: typeof node.label === 'string' && node.label ? node.label : KIND_FALLBACK_LABELS[kind],
      loaded: asEntries(node.loaded),
      selected: typeof node.selected === 'string' ? node.selected : '',
      warming: node.warming === true
    }
  }

  return {
    ...categories,
    total: RESIDENCY_KINDS.reduce((sum, kind) => sum + categories[kind].loaded.length, 0)
  }
}

export interface TrayMenuLabels {
  loadedHeader: string
  noModels: string
  open: string
  quit: string
  unavailable: string
  unload: string
  unloadAll: string
  warming: string
}

export const DEFAULT_TRAY_LABELS: TrayMenuLabels = {
  loadedHeader: 'Loaded models',
  noModels: 'No models loaded',
  open: 'Open The Fool',
  quit: 'Quit The Fool',
  unavailable: 'Model status unavailable',
  unload: 'Unload',
  unloadAll: 'Unload all models',
  warming: 'loading…'
}

/**
 * The tray menu for a snapshot (`null` = the backend could not be asked).
 *
 * Each loaded model is a row with a one-item `Unload` submenu rather than a
 * click target of its own. A bare row reading "Voice: Kokoro" gives no hint
 * that clicking it drops the model, and an accidental unload costs a 24-second
 * reload — the submenu makes the action name itself.
 */
export function buildTrayMenuTemplate(
  snapshot: null | ResidencySnapshot,
  actions: TrayMenuActions,
  labels: TrayMenuLabels = DEFAULT_TRAY_LABELS
): TrayMenuItem[] {
  const template: TrayMenuItem[] = [{ click: () => actions.onShow(), label: labels.open }, { type: 'separator' }]

  if (!snapshot) {
    template.push({ enabled: false, label: labels.unavailable })
  } else if (snapshot.total === 0) {
    template.push({ enabled: false, label: labels.noModels })
  } else {
    template.push({ enabled: false, label: `${labels.loadedHeader} — ${snapshot.total}` })

    for (const kind of RESIDENCY_KINDS) {
      for (const entry of snapshot[kind].loaded) {
        template.push({
          label: `${snapshot[kind].label}: ${entry.label}`,
          submenu: [{ click: () => actions.onUnload(kind, entry.id), label: labels.unload }]
        })
      }
    }

    template.push({ click: () => actions.onUnloadAll(), label: labels.unloadAll })
  }

  // A category that is mid-load is neither "loaded" (nothing to drop yet) nor
  // absent — showing it keeps the user from reading a warm-up as a failure and
  // clicking around while the model is on its way in.
  if (snapshot) {
    for (const kind of RESIDENCY_KINDS) {
      if (snapshot[kind].warming) {
        template.push({ enabled: false, label: `${snapshot[kind].label}: ${labels.warming}` })
      }
    }
  }

  template.push({ type: 'separator' }, { click: () => actions.onQuit(), label: labels.quit })

  return template
}

/** Tooltip text — the tray icon should answer "is it holding anything?". */
export function trayTooltip(appName: string, snapshot: null | ResidencySnapshot): string {
  if (!snapshot || snapshot.total === 0) {
    return appName
  }

  return `${appName} — ${snapshot.total} model${snapshot.total === 1 ? '' : 's'} loaded`
}

/**
 * Does this window close hide to the tray instead of ending the app?
 *
 * `trayReady` is load-bearing, not a formality: tray creation fails on Linux
 * desktops without a StatusNotifier host, and hiding there would leave the
 * user with a running app and no way to reach or quit it. No tray, no
 * close-to-tray.
 */
export function shouldHideOnClose({ quitting, trayReady }: { quitting: boolean; trayReady: boolean }): boolean {
  return trayReady && !quitting
}

/** The `Tray` surface this module uses (injected so it can be tested). */
export interface TrayLike {
  destroy(): void
  displayBalloon?(options: { content: string; iconType?: string; title: string }): void
  isDestroyed?(): boolean
  on(event: string, listener: (...args: any[]) => void): unknown
  popUpContextMenu?(menu: unknown): void
  setContextMenu(menu: null | unknown): void
  setToolTip(tooltip: string): void
}

export interface TrayRuntimeDeps {
  appName?: string
  /** Ask the backend what is resident. Resolve `null` when it can't be asked. */
  fetchResidency(): Promise<unknown>
  /** `Menu.buildFromTemplate` (kept out of this module so it stays testable). */
  buildMenu(template: TrayMenuItem[]): unknown
  createTray(): null | TrayLike
  labels?: TrayMenuLabels
  log?(message: string): void
  onQuit(): void
  onShow(): void
  /**
   * Linux only: right-click carries no event there, so the menu has to be
   * attached ahead of time and refreshed on a timer. Windows and macOS build
   * it on the click itself and pay nothing while the menu is closed.
   */
  refreshIntervalMs?: number
  unload(kind: 'all' | ResidencyKind, id: string): Promise<unknown>
}

export interface TrayRuntime {
  destroy(): void
  isReady(): boolean
  /**
   * A one-off notice from the tray icon (Windows balloon; a no-op elsewhere).
   *
   * Used the first time the window disappears into the tray: without it the
   * app reads as "the close button did nothing", and the next stop is the task
   * manager.
   */
  notify(title: string, content: string): void
  /** Latest snapshot (`null` before the first successful read). */
  lastSnapshot(): null | ResidencySnapshot
  /** Re-read residency and re-render the menu/tooltip. */
  refresh(): Promise<null | ResidencySnapshot>
  start(): boolean
}

export function createTrayRuntime(deps: TrayRuntimeDeps): TrayRuntime {
  const appName = deps.appName ?? 'The Fool'
  const labels = deps.labels ?? DEFAULT_TRAY_LABELS
  const log = deps.log ?? (() => {})

  let tray: null | TrayLike = null
  let snapshot: null | ResidencySnapshot = null
  let inFlight: null | Promise<null | ResidencySnapshot> = null
  let timer: null | ReturnType<typeof setInterval> = null
  let destroyed = false

  const alive = () => Boolean(tray) && !(tray?.isDestroyed?.() ?? false)

  const actions: TrayMenuActions = {
    onQuit: () => deps.onQuit(),
    onShow: () => deps.onShow(),
    onUnload: (kind, id) => {
      void runUnload(kind, id)
    },
    onUnloadAll: () => {
      void runUnload('all', '')
    }
  }

  function render() {
    if (!alive()) {
      return
    }

    tray?.setToolTip(trayTooltip(appName, snapshot))

    // Only Linux keeps a menu attached; elsewhere the menu is built at click
    // time, and attaching one here would make Windows show a stale copy of it
    // on right-click instead of the fresh one.
    if (deps.refreshIntervalMs) {
      tray?.setContextMenu(deps.buildMenu(buildTrayMenuTemplate(snapshot, actions, labels)))
    }
  }

  function refresh(): Promise<null | ResidencySnapshot> {
    // One read at a time: a right-click during a pending read must not open a
    // second backend request, and the two answers could land out of order.
    if (inFlight) {
      return inFlight
    }

    inFlight = deps
      .fetchResidency()
      .then(raw => {
        snapshot = normalizeResidency(raw)

        return snapshot
      })
      .catch(error => {
        // A backend that is starting, gone, or older than this build is a
        // normal state, not an error the user needs. The menu says
        // "unavailable" and keeps its Open/Quit rows working.
        log(`[tray] residency read failed: ${error?.message || error}`)
        snapshot = null

        return null
      })
      .finally(() => {
        inFlight = null
        render()
      })

    return inFlight
  }

  async function runUnload(kind: 'all' | ResidencyKind, id: string) {
    try {
      await deps.unload(kind, id)
    } catch (error: any) {
      log(`[tray] unload ${kind}${id ? `/${id}` : ''} failed: ${error?.message || error}`)
    }

    await refresh()
  }

  function popUp() {
    // Build from what we already have and open immediately, THEN refresh: a
    // menu that waits on a backend round trip before appearing reads as a
    // click that did nothing. The refresh repaints the rows underneath (and is
    // what the next open shows).
    tray?.popUpContextMenu?.(deps.buildMenu(buildTrayMenuTemplate(snapshot, actions, labels)))
    void refresh()
  }

  return {
    destroy() {
      destroyed = true

      if (timer) {
        clearInterval(timer)
        timer = null
      }

      if (alive()) {
        tray?.setContextMenu(null)
        tray?.destroy()
      }

      tray = null
    },

    isReady: () => alive(),

    lastSnapshot: () => snapshot,

    notify(title, content) {
      if (!alive()) {
        return
      }

      try {
        tray?.displayBalloon?.({ content, iconType: 'info', title })
      } catch (error: any) {
        // Balloons are Windows-only and the shell can refuse them (focus
        // assist, notifications off). A refused notice must never take the
        // hide with it.
        log(`[tray] balloon not shown: ${error?.message || error}`)
      }
    },

    refresh,

    start() {
      if (destroyed || tray) {
        return alive()
      }

      try {
        tray = deps.createTray()
      } catch (error: any) {
        // No StatusNotifier host (bare Linux WMs), or the icon file is
        // missing. Returning false leaves close-to-tray off, which is the
        // correct fallback: the window keeps quitting the app.
        log(`[tray] could not create the tray icon: ${error?.message || error}`)
        tray = null
      }

      if (!tray) {
        return false
      }

      tray.on('click', () => deps.onShow())
      tray.on('double-click', () => deps.onShow())
      tray.on('right-click', () => popUp())

      if (deps.refreshIntervalMs) {
        timer = setInterval(() => void refresh(), deps.refreshIntervalMs)
        timer.unref?.()
      }

      void refresh()

      return true
    }
  }
}
