/**
 * The HUD's minimum size is written in two processes and must agree.
 *
 * `spawnHudWindow` creates the window with `minWidth`/`minHeight`, and the
 * renderer's corner handle clamps its own drag to the same numbers. They are
 * separate copies and CANNOT be shared: main is compiled with `src` excluded
 * (tsconfig.electron.json), so it cannot import from the renderer.
 *
 * A comment saying "same as spawnHudWindow" is exactly how two copies drift —
 * this repo has measured that failure more than once. If they diverge the user
 * keeps dragging the handle inward, the OS refuses past its own minimum, and
 * the handle slides out from under the cursor while the window sits still.
 *
 * Zone A: upstream doesn't know about HUD mode.
 */

import { readFileSync } from 'node:fs'
import { join } from 'node:path'

import { describe, expect, it } from 'vitest'

const read = (...parts: string[]) => readFileSync(join(__dirname, ...parts), 'utf8')

const HANDLE = read('resize-handle.ts')
const MAIN = read('..', '..', '..', 'electron', 'main.ts')

const only = (pattern: RegExp, text: string, what: string): string => {
  const found = [...text.matchAll(pattern)].map(match => match[1] ?? '')

  // More than one definition is the very thing this test prevents.
  expect(found, `${what}: expected exactly one definition`).toHaveLength(1)

  return found[0]
}

describe('HUD minimum size', () => {
  it('the handle clamps to the size main creates the window with', () => {
    expect(only(/const HUD_MIN_WIDTH = (\d+)/g, HANDLE, 'handle width')).toBe(
      only(/const HUD_MIN_WIDTH = (\d+)/g, MAIN, 'main width')
    )
    expect(only(/const HUD_MIN_HEIGHT = (\d+)/g, HANDLE, 'handle height')).toBe(
      only(/const HUD_MIN_HEIGHT = (\d+)/g, MAIN, 'main height')
    )
  })

  it('main has no bare copy of the numbers left', () => {
    // `spawnHudWindow` and the `fool:hud:set-bounds` clamp both used to spell
    // the literals out. Two copies in ONE file is the cheapest kind to fix and
    // the easiest to reintroduce.
    const spawn = MAIN.slice(MAIN.indexOf('function spawnHudWindow'))

    expect(spawn.slice(0, 400)).toContain('minWidth: HUD_MIN_WIDTH')
    expect(spawn.slice(0, 400)).toContain('minHeight: HUD_MIN_HEIGHT')

    const clamp = MAIN.slice(MAIN.indexOf("ipcMain.on('fool:hud:set-bounds'"))

    expect(clamp.slice(0, 500)).toContain('Math.max(HUD_MIN_WIDTH')
    expect(clamp.slice(0, 500)).toContain('Math.max(HUD_MIN_HEIGHT')
  })
})

describe('the edge poll', () => {
  it('is not armed while the layout is pinned', () => {
    // `measure` returns before reading anything when HUD_THREAD_ALWAYS_BELOW is
    // on, so the interval woke 3.3x/s forever — in an always-on-top window —
    // to re-set the same value.
    const shell = read('hud-shell.tsx')
    const effect = shell.slice(shell.indexOf('const FLIP_ON = 0'))

    const guard = effect.indexOf('if (HUD_THREAD_ALWAYS_BELOW) {\n      return\n    }')
    const interval = effect.indexOf('setInterval(measure, 300)')

    expect(guard).toBeGreaterThan(-1)
    expect(interval).toBeGreaterThan(guard)
  })
})
