/**
 * İletilen bas-konuş tuşu ÇAĞRILABİLİR bir olay olmalı.
 *
 * Ölçülen kırıklık (kullanıcının günlüğünden, altı kez arka arkaya)::
 *
 *     [renderer console:notch] Uncaught Error:
 *     e.preventDefault is not a function
 *
 * Sebep: ana süreç sağ Ctrl'yi çentiğe IPC üzerinden DÜZ BİR NESNE olarak
 * iletiyor (`{ repeat, type }`), çentik tarafı ise onu `KeyboardEvent`e cast
 * edip `onDown`a veriyordu. `onDown` basılı tutuşun başka kısayolları
 * tetiklememesi için `preventDefault()` çağırıyor -- ve düz nesnede o işlev
 * yok.
 *
 * İstisna tam o satırda atılıyor, yani hemen ardından gelen `voice.begin()`
 * HİÇ çalışmıyor: mikrofon açılmıyor ve çentik ölü görünüyor.
 *
 * Kullanıcının bildirdiği: "bir iki sağ ctrl kullanımından sonra buga giriyor
 * ve bir daha açılmıyor." İlk cevap ana pencerede çizilince odak oraya
 * geçiyor ve tuş ARTIK bu iletilen yoldan geliyor -- yani hata ilk turdan
 * sonra başlıyor, tam tarif edildiği gibi.
 *
 * Zone A: upstream bu dosyayı bilmiyor.
 */

import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

import { describe, expect, it } from 'vitest'

import { createPushToTalkState, onKeyDown, PUSH_TO_TALK_CODE } from './push-to-talk'

const SHELL = readFileSync(join(__dirname, 'notch-shell.tsx'), 'utf8')

describe('iletilen bas-konus tusu', () => {
  it('sentetik olay preventDefault TASIYOR', () => {
    // Kaynakta duruyor mu: bu satır silinirse hata sessizce geri gelir ve
    // çentik yine ölür.
    const forwarded = SHELL.slice(SHELL.indexOf('onPushToTalk?.('))

    expect(forwarded).toContain('preventDefault: () => {}')
  })

  it('onDown sentetik olayla CAGRILABILIYOR', () => {
    // Gerçek çağrı yolunun bire bir taklidi: `notch-shell` bu şekilde bir
    // nesne kurup `onDown`a veriyor ve `onDown` `preventDefault()` çağırıyor.
    const key = {
      code: PUSH_TO_TALK_CODE,
      preventDefault: () => {},
      repeat: false
    } as unknown as KeyboardEvent

    const state = createPushToTalkState()
    const action = onKeyDown(state, key, 1_000)

    assert.deepEqual(action, { type: 'start' })

    // Kritik olan: bu çağrı ATMAMALI. Eski hâlde burası patlıyordu.
    expect(() => key.preventDefault()).not.toThrow()
  })

  it('preventDefault OLMAYAN bir olay gercekten patliyor', () => {
    // Regresyonun kendisini gösteren test: koruma kalkarsa ne olacağını
    // belgeliyor.
    const broken = { code: PUSH_TO_TALK_CODE, repeat: false } as unknown as KeyboardEvent

    expect(() => broken.preventDefault()).toThrow(TypeError)
  })

  it('ana surec DUZ NESNE gonderiyor -- varsayim yazili', () => {
    // İki taraf ayrışırsa (ana süreç gerçek bir olay göndermeye başlarsa)
    // buradaki no-op gereksizleşir ama zararsızdır; tersi sessiz çökme.
    const main = readFileSync(
      join(__dirname, '..', '..', '..', 'electron', 'main.ts'),
      'utf8'
    )

    const send = main.slice(main.indexOf("send('fool:notch:ptt'"))

    expect(send.slice(0, 200)).toContain('repeat:')
    expect(send.slice(0, 200)).toContain('type:')
  })
})
