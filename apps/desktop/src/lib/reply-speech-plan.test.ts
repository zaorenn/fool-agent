/**
 * Yazılı sohbette ses, cevap BİTMEDEN başlamalı.
 *
 * Ölçülen hata
 * ------------
 * Otomatik sesli okuma tek bir satırla tamamlanmayı bekliyordu::
 *
 *     if (!reply || reply.pending) return
 *
 * Model 30 saniye yazıyor, ses ancak bittikten sonra başlıyordu. Kullanıcının
 * ekran görüntüsünde tam olarak bu görünüyor: cevap hâlâ akarken "Reading
 * aloud" yeni başlamış. İsteği ise açıktı: "uzun cevaplarda bile ilk cümle
 * biter bitmez cümle cümle sesli okusun."
 *
 * Akış yolu (``startSpeechStream``) zaten vardı ama yalnızca sesli sohbete ve
 * çentiğe bağlıydı -- klavyeden yazan kullanıcı ona hiç ulaşamıyordu. Bu, bu
 * denetimin tekrar eden deseni: doğru mekanizma kod tabanında var, o yol onu
 * kullanmıyor.
 */

import { describe, expect, it } from 'vitest'

import { planReplySpeech } from './reply-speech-plan'

const streaming = { id: 'a1', pending: true, text: 'Bir varmis bir yokmus.' }
const done = { id: 'a1', pending: false, text: 'Bir varmis bir yokmus. Son.' }

describe('akis baslatma', () => {
  it('cevap HALA AKARKEN oturum aciliyor', () => {
    // Hatanin ta kendisi: eskiden burada ``wait`` donuyordu.
    expect(
      planReplySpeech({ declined: false, live: null, playbackIdle: true, reply: streaming })
    ).toEqual({ id: 'a1', kind: 'open' })
  })

  it('onceki klip CALARKEN yeni oturum acilmiyor', () => {
    // Iki cevabin ust uste binmesini onleyen eski kural KORUNUYOR.
    expect(
      planReplySpeech({ declined: false, live: null, playbackIdle: false, reply: streaming })
    ).toEqual({ kind: 'wait' })
  })

  it('baska pencere ustlendiyse acilmiyor', () => {
    expect(
      planReplySpeech({ declined: true, live: null, playbackIdle: true, reply: streaming })
    ).toEqual({ kind: 'wait' })
  })

  it('cevap yoksa ve oturum da yoksa bekliyor', () => {
    expect(
      planReplySpeech({ declined: false, live: null, playbackIdle: true, reply: null })
    ).toEqual({ kind: 'wait' })
  })
})

describe('metin gonderme', () => {
  it('yalnizca YENI kismi gonderiyor', () => {
    // Her tikte tum metni yollamak ayni cumleleri defalarca okuturdu.
    expect(
      planReplySpeech({
        declined: false,
        live: { id: 'a1', sent: 10 },
        playbackIdle: false,
        reply: streaming
      })
    ).toEqual({ kind: 'append', sent: 22, text: ' bir yokmus.' })
  })

  it('acilis gecikse bile bas taraf KAYBOLMUYOR', () => {
    // ``sent`` sifirdan basliyor: ilk gonderim o ana kadar birikmis her seyi
    // tasiyor.
    expect(
      planReplySpeech({
        declined: false,
        live: { id: 'a1', sent: 0 },
        playbackIdle: false,
        reply: streaming
      })
    ).toEqual({ kind: 'append', sent: 22, text: 'Bir varmis bir yokmus.' })
  })

  it('yeni metin yoksa ve cevap SURUYORSA bekliyor', () => {
    expect(
      planReplySpeech({
        declined: false,
        live: { id: 'a1', sent: 22 },
        playbackIdle: false,
        reply: streaming
      })
    ).toEqual({ kind: 'wait' })
  })
})

describe('kapatma', () => {
  it('metin BITTIKTEN sonra kapaniyor', () => {
    expect(
      planReplySpeech({
        declined: false,
        live: { id: 'a1', sent: done.text.length },
        playbackIdle: false,
        reply: done
      })
    ).toEqual({ kind: 'finish' })
  })

  it('kalan metin varken KAPATMIYOR -- son cumle kesilmesin', () => {
    // Ters sirada yapmak son cumleyi yutmakti.
    expect(
      planReplySpeech({
        declined: false,
        live: { id: 'a1', sent: 5 },
        playbackIdle: false,
        reply: done
      }).kind
    ).toBe('append')
  })

  it('YENI cevap gelince once eskisi kapaniyor', () => {
    expect(
      planReplySpeech({
        declined: false,
        live: { id: 'a1', sent: 5 },
        playbackIdle: true,
        reply: { id: 'a2', pending: true, text: 'Yeni.' }
      })
    ).toEqual({ kind: 'retire' })
  })

  it('cevap kaybolursa acik oturum kapaniyor', () => {
    // Oturum degisti ya da mesaj silindi.
    expect(
      planReplySpeech({ declined: false, live: { id: 'a1', sent: 5 }, playbackIdle: true, reply: null })
    ).toEqual({ kind: 'retire' })
  })
})

describe('kanca saf planlayiciyi kullaniyor', () => {
  it('tamamlanma bekleyen eski kapi KALKTI', async () => {
    const { readFileSync } = await import('node:fs')
    const { join } = await import('node:path')

    const hook = readFileSync(
      join(import.meta.dirname, '../app/chat/composer/hooks/use-auto-speak-replies.ts'),
      'utf8'
    )

    expect(hook.includes('planReplySpeech')).toBe(true)
    expect(hook.includes('startSpeechStream')).toBe(true)
    // Eski satir: cevap bitene kadar hicbir sey yapmiyordu.
    expect(hook.includes('if (!reply || reply.pending)')).toBe(false)
  })
})

/**
 * Oynatma kapısı YALNIZCA açılışta geçerli.
 *
 * Akışa geçerken ``$voicePlayback.get().status !== 'idle'`` kontrolü
 * ``speakLatest``in EN BAŞINDA bırakılmıştı. Sonuç, akışın kendi kendini
 * öldürmesiydi: ilk parça gidiyor, ses çalmaya başlıyor, durum 'speaking'
 * oluyor ve sonraki her ``$messages`` tiki en baştan geri dönüyordu. Kalan
 * metin ancak oynatma boşa düşünce gidiyor -- konuşma parça parça ilerliyor.
 *
 * Kullanıcının bildirdiği: "ilk cümle biter bitmez okumaya başlaması lazım,
 * öbür türlü çok gecikme hissediliyor."
 */
describe('oynatma kapisi yalnizca ACILISTA', () => {
  it('ses CALARKEN bile metin gonderilmeye devam ediyor', () => {
    // Hatanin ta kendisi: burada eskiden hicbir sey olmuyordu.
    const action = planReplySpeech({
      declined: false,
      live: { id: 'a1', sent: 3 },
      playbackIdle: false,
      reply: streaming
    })

    expect(action.kind).toBe('append')
  })

  it('ses CALARKEN bile oturum kapanabiliyor', () => {
    // Kapanma oynatmaya bagli olsaydi son cumle asili kalirdi.
    expect(
      planReplySpeech({
        declined: false,
        live: { id: 'a1', sent: done.text.length },
        playbackIdle: false,
        reply: done
      })
    ).toEqual({ kind: 'finish' })
  })

  it('kanca ust seviyede oynatma kapisi TUTMUYOR', async () => {
    const { readFileSync } = await import('node:fs')
    const { join } = await import('node:path')

    const hook = readFileSync(
      join(import.meta.dirname, '../app/chat/composer/hooks/use-auto-speak-replies.ts'),
      'utf8'
    )

    // Eski satir: her tiki en bastan kesiyordu.
    expect(hook.includes("conversationActive || $voicePlayback.get().status !== 'idle'")).toBe(false)
    // Karar planlayiciya GECIYOR.
    expect(hook.includes("playbackIdle: $voicePlayback.get().status === 'idle'")).toBe(true)
  })
})
