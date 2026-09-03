/**
 * Çentik ile konuşma kipi AYNI yoldan geçmeli.
 *
 * Kullanıcının talimatı: "çentik aynı akışın birebir aynısı, sadece atanan tuş
 * ile bas-konuş hâli olmalı."
 *
 * İki yol da bugün şunları paylaşıyor:
 *
 *   * YAZIYA DÖKME -- ``blobToDataUrl`` + ``transcribeAudio``. Ayrışırlarsa
 *     aynı cümle iki yüzeyde farklı sürede ve farklı doğrulukta çözülür.
 *   * GÖNDERİM -- composer'ın ``submitText`` boru hattı. Çentik oraya
 *     ``use-voice-submit-requests`` üzerinden giriyor; kendi
 *     ``prompt.submit``ini attığı sürece composer'ın İYİMSER kullanıcı balonu
 *     çizilmiyordu ve kullanıcı konuşup ekranda hiçbir şey görmüyordu.
 *
 * BİR DÜZELTME, kayda geçsin: bir ara "konuşma kipi akış tabanlı STT kullanıyor,
 * çentik tek seferlik" diye okundu. Yanlıştı -- o dosyadaki
 * ``SpeechStreamSession`` TTS ÇIKTI akışı, girdi değil. İki yol da aynı tek
 * seferlik yazıya dökmeyi çağırıyor; hız farkının gerçek sebebi çentiğin
 * gönderimden ÖNCE oturum beklemesiydi (12 sn'ye kadar) ve o kaldırıldı.
 *
 * Zone A: upstream bu dosyayı bilmiyor.
 */

import { readFileSync } from 'node:fs'
import { join } from 'node:path'

import { describe, expect, it } from 'vitest'

const read = (...parts: string[]) => readFileSync(join(__dirname, ...parts), 'utf8')

const NOTCH = read('use-notch-voice.ts')
const COMPOSER = read('..', '..', 'app', 'session', 'hooks', 'use-prompt-actions', 'index.ts')
const BRIDGE = read('use-voice-submit-requests.ts')

describe('yaziya dokme AYNI', () => {
  it('iki yol da ayni iki ilkeli cagiriyor', () => {
    for (const source of [NOTCH, COMPOSER]) {
      expect(source).toContain('blobToDataUrl(audio)')
      expect(source).toContain('transcribeAudio(dataUrl, audio.type)')
    }
  })

  it('centigin KENDI sinirini tasimasi bir AYRISMA degil', () => {
    // Paylasilan zaman asimi TABANI 180 saniye (``hermes.ts``) -- uzun bir
    // dikte icin makul, iki saniyelik bir bas-konus klibi icin felaket.
    // Sinir yalnizca bu yuzeyde ve SEBEBI kullaniciya soyleniyor; paylasilan
    // sabit degistirilmedi, cunku ayni deger besteci diktesini de besliyor.
    expect(NOTCH).toContain('TRANSCRIBE_LIMIT_MS')
    expect(NOTCH).toContain('taking too long')
    expect(COMPOSER).not.toContain('TRANSCRIBE_LIMIT_MS')
  })
})

describe('gonderim AYNI', () => {
  it('centik KENDI prompt.submit ini ATMIYOR', () => {
    // Atarken composer'in IYIMSER kullanici balonu cizilmiyordu: mesaj
    // gidiyor, ekranda hicbir sey olmuyor ve model dusunurken uygulama olu
    // gorunuyordu.
    expect(NOTCH).not.toContain("requestGateway('prompt.submit'")
    expect(NOTCH).toContain('requestVoiceSubmit(text, interrupted)')
  })

  it('kopru ANA PENCERENIN submitText ini cagiriyor', () => {
    expect(BRIDGE).toContain('submitText')
    // Centik penceresi kendi istegine kendisi cevap verirse mesaj IKI KEZ
    // gonderilirdi.
    expect(BRIDGE).toContain('isNotchWindow()')
  })

  it('gonderimden ONCE oturum BEKLENMIYOR', () => {
    // Gecikmenin asil kaynagi buydu: acik oturum yoksa 12 saniyeye kadar bir
    // tane acilmasi bekleniyordu -- konusma bittikten SONRA. Ana pencere
    // zaten oturumu acan taraf.
    const submit = NOTCH.slice(NOTCH.indexOf('const submitAudio'))
    const upToSend = submit.slice(0, submit.indexOf('requestVoiceSubmit'))

    expect(upToSend).not.toContain('await resolveSessionId()')
  })
})

describe('TEK fark giris olmali', () => {
  it('centik bas-konus, konusma kipi kendi dongusu', () => {
    // Bas-konusta ses ile araya girme KAPALI: "basmadan konusursak bile
    // algiliyor" bildirimi bunun eksikligiydi.
    expect(NOTCH).toContain("const handsFree = listenMode === 'hands-free'")
    expect(NOTCH).toContain('(handsFree && shouldMonitorBargeIn(status)) || capturing')
  })

  it('uyandirma da AYNI yakalamayi kullaniyor', () => {
    // Uyandirma turu yeni bir yol acmiyor: ``begin('auto')`` zaten eller
    // serbest VAD'ini veriyor.
    expect(NOTCH).toContain("begin('auto')")
  })
})
