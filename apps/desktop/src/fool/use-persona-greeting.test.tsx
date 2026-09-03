/**
 * Selamı GÖNDEREN taraf: doğru anda bir kez, yanlış anda hiç.
 *
 * Zone A: upstream bu dosyayı bilmiyor.
 */

import { cleanup, render, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { $activeSessionId, $busy, $messages } from '@/store/session'

import { PERSONA_KICKOFF } from './persona-greeting'
import { usePersonaGreeting } from './use-persona-greeting'

const requestGateway = vi.fn(() => Promise.resolve({}))
const fetchRelationship = vi.fn()

vi.mock('@/app/gateway/hooks/use-gateway-request', () => ({
  useGatewayRequest: () => ({ requestGateway })
}))

vi.mock('./relationship-bar', () => ({
  fetchRelationship: () => fetchRelationship()
}))

function Harness({ active = true }: { active?: boolean }) {
  usePersonaGreeting(active)

  return null
}

beforeEach(() => {
  requestGateway.mockClear()
  fetchRelationship.mockReset()
  $activeSessionId.set('live-1')
  $messages.set([])
  $busy.set(false)
})

afterEach(cleanup)

const persona = { enabled: true, met: false, started: false, warmth: 50, stance: 'neutral' as const, grievances: [] }

describe('usePersonaGreeting', () => {
  it('persona profilinde ILK sozu soyluyor', async () => {
    fetchRelationship.mockResolvedValue(persona)

    render(<Harness />)

    await waitFor(() => expect(requestGateway).toHaveBeenCalledTimes(1))
    expect(requestGateway).toHaveBeenCalledWith('prompt.submit', {
      session_id: 'live-1',
      text: PERSONA_KICKOFF
    })
  })

  it('siradan ajanda SUSUYOR', async () => {
    fetchRelationship.mockResolvedValue({ enabled: false })

    render(<Harness />)

    await waitFor(() => expect(fetchRelationship).toHaveBeenCalled())
    expect(requestGateway).not.toHaveBeenCalled()
  })

  it('daha once TANISILMISSA susuyor', async () => {
    fetchRelationship.mockResolvedValue({ ...persona, met: true })

    render(<Harness />)

    await waitFor(() => expect(fetchRelationship).toHaveBeenCalled())
    expect(requestGateway).not.toHaveBeenCalled()
  })

  it('SUREN bir sohbette sunucuya bile SORMUYOR', async () => {
    // Bos olmayan bir oturumda soru sormak bedava degil: her sohbet acilisinda
    // bir arka uc turu demek.
    $messages.set([{ id: 'm1', role: 'user', parts: [] }] as never)
    fetchRelationship.mockResolvedValue(persona)

    render(<Harness />)

    await new Promise(resolve => setTimeout(resolve, 20))
    expect(fetchRelationship).not.toHaveBeenCalled()
  })

  it('BIRINCIL gorunum degilse susuyor', async () => {
    // Her sohbet kutucugu ayni bilesenden turuyor ve hepsi ayni atomlari
    // okuyor; kapisiz kalsaydi acik kutucuk sayisi kadar selam giderdi.
    fetchRelationship.mockResolvedValue(persona)

    render(<Harness active={false} />)

    await new Promise(resolve => setTimeout(resolve, 20))
    expect(fetchRelationship).not.toHaveBeenCalled()
  })

  it('ajan CALISIRKEN susuyor', async () => {
    $busy.set(true)
    fetchRelationship.mockResolvedValue(persona)

    render(<Harness />)

    await new Promise(resolve => setTimeout(resolve, 20))
    expect(fetchRelationship).not.toHaveBeenCalled()
  })

  it('bekleme sirasinda kullanici YAZDIYSA vazgeciyor', async () => {
    // Sunucu cevabi gelene kadar gecen surede kullanici bir sey gonderebilir;
    // eski karara gore devam etmek turun ustune tur gondermek olurdu.
    let release: (value: unknown) => void = () => undefined

    fetchRelationship.mockReturnValue(
      new Promise(resolve => {
        release = resolve
      })
    )

    render(<Harness />)

    await waitFor(() => expect(fetchRelationship).toHaveBeenCalled())
    $messages.set([{ id: 'm1', role: 'user', parts: [] }] as never)
    release(persona)

    await new Promise(resolve => setTimeout(resolve, 20))
    expect(requestGateway).not.toHaveBeenCalled()
  })

  it('ag gecidi dusunce PATLAMIYOR', async () => {
    fetchRelationship.mockResolvedValue(persona)
    requestGateway.mockRejectedValueOnce(new Error('socket closed'))

    render(<Harness />)

    await waitFor(() => expect(requestGateway).toHaveBeenCalled())
  })
})
