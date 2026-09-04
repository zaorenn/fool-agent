/**
 * Friend penceresindeki ses seçicisinin davranış testleri.
 *
 * Sınanan şey, kullanıcının bildirdiği hatanın ta kendisi: panelde bir ses
 * görünüp başka bir sesin duyulması.
 */

import { describe, expect, it } from 'vitest'

import type { VoiceCatalog, VoiceItem } from '../voice-api'

import { isChoosableVoiceId, selectedVoiceId, voiceOptions } from './voice-choice'

function item(overrides: Partial<VoiceItem> = {}): VoiceItem {
  return {
    active: false,
    assets_installed: true,
    clone: '',
    clone_capable: false,
    clone_help: '',
    cpu_warning: '',
    cuda_available: false,
    cuda_ready: false,
    device: 'auto',
    devices: ['cpu'],
    engine_installed: true,
    id: 'kokoro',
    installed: true,
    kind: 'tts',
    label: 'Kokoro',
    provider_id: 'kokoro',
    size_mb: 0,
    summary: '',
    voice: '',
    voices: [],
    ...overrides
  } as VoiceItem
}

function catalog(items: VoiceItem[]): VoiceCatalog {
  return { active: {}, cuda_available: false, items, voice_dir: '' } as VoiceCatalog
}

describe('voiceOptions', () => {
  it('yalnizca kurulu seslendirme motorlarini veriyor', () => {
    const list = voiceOptions(
      catalog([
        item({ id: 'kokoro' }),
        item({ id: 'kyutai', installed: false }),
        item({ id: 'large-v3-turbo', kind: 'stt' })
      ])
    )

    expect(list.map(entry => entry.id)).toEqual(['kokoro'])
  })

  it('katalog yoksa bos liste -- pencere yine calisiyor', () => {
    expect(voiceOptions(null)).toEqual([])
  })

  /**
   * ASIL REGRESYON: listede BOS kimlikli bir secenek olamaz.
   *
   * Olculdu: ``voice_models.select("")`` -> ``ValueError: bilinmeyen oge:``
   * -> HTTP 400. Panelde duran "Default voice" secenegi tam olarak bunu
   * yapiyordu: hata bildirimi cikiyor, motor degismiyor, acilir liste yine de
   * o secenekte kaliyordu.
   */
  it('hicbir secenek BOS kimlik tasimiyor', () => {
    const list = voiceOptions(catalog([item({ id: 'kokoro' }), item({ id: 'styletts2' })]))

    expect(list.length).toBeGreaterThan(0)

    for (const entry of list) {
      expect(isChoosableVoiceId(entry.id)).toBe(true)
    }
  })
})

describe('isChoosableVoiceId', () => {
  it('bos kimlik sunucuya HIC gitmiyor', () => {
    expect(isChoosableVoiceId('')).toBe(false)
    expect(isChoosableVoiceId('   ')).toBe(false)
    expect(isChoosableVoiceId('kokoro')).toBe(true)
  })
})

describe('selectedVoiceId', () => {
  it('sunucuda AKTIF olani gosteriyor', () => {
    const id = selectedVoiceId(catalog([item({ id: 'kokoro' }), item({ active: true, id: 'styletts2' })]))

    expect(id).toBe('styletts2')
  })

  /**
   * Kullanici motoru Ayarlar'dan degistirdiginde Friend penceresi bunu
   * gormeli. Gosterim tek yonlu ve KAYNAK katalog: taze katalog gelince
   * secim de onunla degisiyor, penceredeki eski deger degil.
   */
  it('katalog tazelenince secim onunla degisiyor', () => {
    const before = catalog([item({ active: true, id: 'kokoro' }), item({ id: 'styletts2' })])
    const after = catalog([item({ id: 'kokoro' }), item({ active: true, id: 'styletts2' })])

    expect(selectedVoiceId(before)).toBe('kokoro')
    expect(selectedVoiceId(after)).toBe('styletts2')
  })

  it('kurulu ama aktif motor yoksa bos -- uydurma bir secim gostermiyor', () => {
    expect(selectedVoiceId(catalog([item({ id: 'kokoro' })]))).toBe('')
    expect(selectedVoiceId(null)).toBe('')
  })

  /** Aktif motor KURULU degilse secim gosterilmiyor: liste onu icermiyor. */
  it('aktif ama kurulu olmayan motoru secili gostermiyor', () => {
    expect(selectedVoiceId(catalog([item({ active: true, id: 'kyutai', installed: false })]))).toBe('')
  })
})

/**
 * Panel motorun DOĞRU eksiğini söylemeli.
 *
 * "Chatterbox has one voice" teknik olarak doğruydu ama yanıltıyordu.
 * Ölçüldü:
 *
 *   kokoro      7 hazır ses, klonlama YOK
 *   chatterbox  hazır ses YOK, klonlama VAR
 *   styletts2   hazır ses YOK, klonlama VAR
 *   piper       1 ses, klonlama YOK
 *
 * Chatterbox'ın ses bankası yok çünkü sesi KULLANICI veriyor. Bunu bir
 * kısıt gibi göstermek, motorun asıl özelliğini eksiklik gibi okutuyordu.
 */
