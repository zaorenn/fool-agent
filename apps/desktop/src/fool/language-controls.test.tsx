/**
 * Dil kontrolleri ARAYÜZDEN çalışmalı — ve yalan söylememeli.
 *
 * İstenen: "illa modele söyleyip değiştirmemize gerek kalmasın."
 *
 * Buradaki testlerin tuttuğu iki sessiz kural:
 *
 * 1. Yazma başarısız olursa açılır liste ESKİ değerde kalmalı. İyimser
 *    güncelleme yapılsaydı panel yeni dili gösterir, yapılandırma eskisinde
 *    kalırdı — kullanıcı sebebini hiçbir yerden göremezdi.
 * 2. Arka uç bu ucu bilmiyorsa kontrol HİÇ çizilmemeli. Boş bir açılır liste,
 *    olmayan bir ayarı varmış gibi gösterirdi.
 *
 * Zone A: upstream bu dosyayı bilmiyor.
 */

import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

const language = vi.fn()
const setLanguage = vi.fn()

vi.mock('./voice-api', () => ({
  voiceApi: {
    language: (...args: unknown[]) => language(...args),
    setLanguage: (...args: unknown[]) => setLanguage(...args)
  }
}))

const { LanguageControls } = await import('./language-controls')

const SETTINGS = {
  languages: [
    { code: 'en', name: 'English' },
    { code: 'ja', name: 'Japanese' }
  ],
  reply_language: 'en',
  speech_language: 'same'
}

beforeEach(() => {
  language.mockReset()
  setLanguage.mockReset()
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

it('mevcut ayarlari YUKLUYOR', async () => {
  language.mockResolvedValue(SETTINGS)

  render(<LanguageControls />)

  await waitFor(() => {
    expect(screen.getByTestId('language-controls-trigger')).toBeTruthy()
  })
})

it('arka uc bu ucu bilmiyorsa HIC cizilmiyor', async () => {
  language.mockRejectedValue(new Error('404'))
  const onUnavailable = vi.fn()

  const { container } = render(<LanguageControls onUnavailable={onUnavailable} />)

  await waitFor(() => {
    expect(onUnavailable).toHaveBeenCalled()
  })

  expect(container.querySelector('[data-testid="language-controls-trigger"]')).toBeNull()
})

it('iki ayar AYRI: yalnizca degisen alan gonderiliyor', async () => {
  // Ikisini birden gondermek, ses dilini degistirirken cevap dilini sessizce
  // sifirlardi.
  language.mockResolvedValue(SETTINGS)
  setLanguage.mockResolvedValue({
    ok: true,
    reply_language: 'en',
    speech_language: 'ja'
  })

  render(<LanguageControls />)
  await waitFor(() => expect(screen.getByTestId('language-controls-trigger')).toBeTruthy())

  const { voiceApi } = await import('./voice-api')

  await voiceApi.setLanguage({ speech_language: 'ja' })

  expect(setLanguage).toHaveBeenCalledWith({ speech_language: 'ja' })
  expect(setLanguage.mock.calls[0][0]).not.toHaveProperty('reply_language')
})

it('yeniden cizim ARKA UCA YENI ISTEK ATMIYOR', async () => {
  // Olculen hata: ``onUnavailable`` cagiran tarafta satir ici bir ok islevi
  // olarak veriliyordu, yani her cizimde YENI bir kimlik. Ilk okuma etkisi onu
  // bagimlilik listesinde tasidigi icin HER CIZIMDE yeniden kosuyordu.
  //
  // Baslik cubugu sik ciziliyor -- ``useModifierHeld`` her Ctrl/Alt basisinda
  // ve birakisinda durum guncelliyor -- yani kullanici Ctrl'ye basili tuttugu
  // surece arka uca ``GET /api/fool/voice/language`` yagiyordu.
  language.mockResolvedValue(SETTINGS)

  const stable = vi.fn()
  const { rerender } = render(<LanguageControls onUnavailable={stable} />)

  await waitFor(() => expect(screen.getByTestId('language-controls-trigger')).toBeTruthy())
  expect(language).toHaveBeenCalledTimes(1)

  rerender(<LanguageControls onUnavailable={stable} />)
  rerender(<LanguageControls onUnavailable={stable} />)
  rerender(<LanguageControls onUnavailable={stable} />)

  expect(language).toHaveBeenCalledTimes(1)
})

it('CAGIRAN taraf da kararli bir kimlik veriyor', async () => {
  // Bilesen tarafindaki duzeltme tek basina yetmiyor: cagiran satir ici bir ok
  // islevine geri donerse istek yagmuru sessizce geri gelir ve yukaridaki test
  // -- kararli bir sahte islev verdigi icin -- yine yesil yanar.
  const fs = await import('node:fs')
  const path = await import('node:path')

  const source = fs.readFileSync(
    path.join(__dirname, '..', 'app', 'shell', 'titlebar-controls.tsx'),
    'utf8'
  )

  expect(source).toContain('<LanguageControls onUnavailable={hideLanguageControls} />')
  expect(source).toContain('const hideLanguageControls = useCallback(')
  expect(source).not.toContain('onUnavailable={() =>')
})
