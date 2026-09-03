/**
 * Bar SIRADAN ajanda hiç görünmemeli — ve pencere arkadayken yoklamamalı.
 *
 * İkisi de sessizce bozulabilecek kurallar: bar kod yazarken kullanılan
 * profilde belirirse anlamsız bir süs olur, ve pencere arkadayken yoklarsa
 * kimse bakmıyorken sesin ihtiyacı olan CPU'yu yer.
 *
 * Zone A: upstream bu dosyayı bilmiyor.
 */

import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { RelationshipBar } from './relationship-bar'

const api = vi.fn()

vi.mock('@/hermes', () => ({ getApiRequestProfile: () => 'persona' }))

beforeEach(() => {
  api.mockReset()
  ;(window as unknown as { foolDesktop: unknown }).foolDesktop = { api }
  // Kural DOM'a sorgu icin uzanmayi engelliyor; burada gorunurlugu TAKLIT
  // ediyoruz ve bunun testing-library karsiligi yok.
  // eslint-disable-next-line no-restricted-globals
  vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('visible')
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe('RelationshipBar', () => {
  it('siradan ajanda HIC cizilmiyor', async () => {
    api.mockResolvedValue({ enabled: false })

    const { container } = render(<RelationshipBar />)

    await waitFor(() => expect(api).toHaveBeenCalled())
    expect(container.querySelector('[data-testid="relationship-bar"]')).toBeNull()
  })

  it('koprude yokken cizilmiyor', async () => {
    ;(window as unknown as { foolDesktop: unknown }).foolDesktop = undefined

    const { container } = render(<RelationshipBar />)

    await waitFor(() => expect(container.firstChild).toBeNull())
  })

  it('AKTIF profile soruyor', async () => {
    // Olculen hata sinifi: profil kapsami tasimayan cagrilar her zaman
    // BIRINCIL arka uca gidiyordu, yani bar yanlis iliskiyi gosterirdi.
    api.mockResolvedValue({ enabled: false })

    render(<RelationshipBar />)

    await waitFor(() => expect(api).toHaveBeenCalled())
    expect(api.mock.calls[0][0]).toMatchObject({ profile: 'persona', path: '/api/fool/relationship' })
  })

  it('dertleri ve durusu gosteriyor', async () => {
    api.mockResolvedValue({
      enabled: true,
      started: true,
      warmth: 18,
      stance: 'cold',
      label: 'Cold',
      summary: 'Closed off, and not pretending otherwise.',
      grievances: [{ text: 'he left without saying goodnight', since: Date.now() / 1000 - 7200, weight: 12 }]
    })

    render(<RelationshipBar />)

    expect(await screen.findByText('Cold')).toBeTruthy()
    expect(screen.getByText('he left without saying goodnight')).toBeTruthy()
    expect(screen.getByText('1 thing unresolved')).toBeTruthy()
    expect(screen.getByText('2h ago')).toBeTruthy()
  })

  it('ilk karsilasmada DURUS iddia etmiyor', async () => {
    api.mockResolvedValue({ enabled: true, started: false, warmth: 50, stance: 'neutral', label: 'Neutral', summary: 'x', grievances: [] })

    render(<RelationshipBar />)

    expect(await screen.findByText('Not met yet')).toBeTruthy()
    expect(screen.queryByText('Neutral')).toBeNull()
  })

  it('dertleri KAPATAN bir dugme yok', async () => {
    // Tek tikla silinebilen bir kirginlik kirginlik degil; gonlunu almanin
    // tek yolu konusmak.
    api.mockResolvedValue({
      enabled: true,
      started: true,
      warmth: 20,
      stance: 'cool',
      label: 'Cool',
      summary: 'x',
      grievances: [{ text: 'a thing', since: Date.now() / 1000, weight: 5 }]
    })

    render(<RelationshipBar />)

    await screen.findByText('a thing')
    expect(screen.queryAllByRole('button')).toHaveLength(0)
  })

  it('pencere ARKADAYKEN yoklamiyor', async () => {
    // Yukaridaki gerekce.
    // eslint-disable-next-line no-restricted-globals
    vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('hidden')
    api.mockResolvedValue({ enabled: true })

    render(<RelationshipBar />)

    await new Promise(resolve => setTimeout(resolve, 20))
    expect(api).not.toHaveBeenCalled()
  })

  it('yoklama bir kez dusunce PATLAMIYOR', async () => {
    api.mockRejectedValue(new Error('gateway not up yet'))

    const { container } = render(<RelationshipBar />)

    await waitFor(() => expect(api).toHaveBeenCalled())
    expect(container.firstChild).toBeNull()
  })
})
