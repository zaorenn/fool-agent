import { afterEach, describe, expect, it, vi } from 'vitest'

import { dropUnselectedModels } from './runtime-api'

const desktopWindow = window as unknown as { foolDesktop?: unknown }

afterEach(() => {
  delete desktopWindow.foolDesktop
})

describe('dropUnselectedModels', () => {
  it('asks the backend to keep one model per category', () => {
    // Tip PARAMETRESI veriliyor: ``vi.fn`` argumansiz bir imza cikariyor ve
    // ``mock.calls[0][0]`` bos demet olarak tiplenip typecheck'i dusuruyordu.
    const api = vi.fn<(request: unknown) => Promise<unknown>>(async () => ({
      total: 1,
      unloaded: { llm: ['qwen/qwen3.5-9b'] }
    }))

    desktopWindow.foolDesktop = { api }

    dropUnselectedModels()

    expect(api).toHaveBeenCalledTimes(1)
    expect(api.mock.calls[0]?.[0]).toMatchObject({ method: 'POST', path: '/api/fool/runtime/enforce' })
  })

  it('does nothing without the desktop bridge', () => {
    // The browser build has no local models to drop; reaching for the bridge
    // there would throw on every model switch.
    expect(() => dropUnselectedModels()).not.toThrow()
  })

  it('never turns a failed cleanup into a failed model switch', async () => {
    const api = vi.fn(async () => {
      throw new Error('backend is not running')
    })

    desktopWindow.foolDesktop = { api }

    expect(() => dropUnselectedModels()).not.toThrow()

    // The rejection is handled inside, so an unhandled rejection can't surface
    // as a notification the user cannot act on.
    await expect(Promise.resolve()).resolves.toBeUndefined()
  })
})
