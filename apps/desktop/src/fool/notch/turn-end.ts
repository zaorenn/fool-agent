/**
 * Tur NE ZAMAN biter — saf, DOM'suz, sınanabilir.
 *
 * Ölçülen hata
 * ------------
 * Çentik turu METİN bitince bitmiş sayıyordu::
 *
 *     if (!pending.pending) {
 *       session?.finish()
 *       setStatus('idle')        // <- ses HÂLÂ çalıyor
 *     }
 *
 * Metin akışı sesin saniyelerce önünde gidiyor: model cümleyi yazmayı
 * bitirdiğinde seslendirme daha yarısındadır. O anda ``idle`` demek, üç şeyi
 * birden bozuyordu ve üçü de kullanıcının bildirdiği hâl:
 *
 * 1. **Çentik kapanıyor.** Görünürlük ``status !== 'idle'`` ile sürüyor
 *    (``notch-shell.tsx``), yani model konuşmaya devam ederken pencere
 *    kendiliğinden daralıyordu.
 * 2. **Sesle araya girme ölüyor.** ``shouldMonitorBargeIn`` yalnızca
 *    ``thinking``/``speaking`` evrelerinde açık; ``idle`` olur olmaz mikrofon
 *    izleyicisi sökülüyor ve kullanıcı konuşarak araya giremiyor.
 * 3. **Tuşla araya girme ölüyor.** Aynı sebep: tur bitmiş sayıldığı için sağ
 *    Ctrl'nin kesecek bir şeyi kalmıyor.
 *
 * Yani "model cevabını bitirene kadar araya giremiyoruz" şikâyetinin tamamı
 * bu tek karardan geliyordu.
 *
 * Doğru kural tek cümle: **tur, SES bitince biter.**
 *
 * Zone A: upstream bu dosyayı bilmiyor.
 */

import type { NotchStatus } from './use-notch-voice'

export interface TurnEndInput {
  /** Asistan baloncuğu tamamlandı mı? (metin akışı bitti) */
  replyComplete: boolean
  /** Seslendirme kanalı boşta mı? */
  playbackIdle: boolean
  /** Çentiğin şu anki durumu. */
  status: NotchStatus
}

export type TurnEndAction =
  /** Henüz bir şey yapma. */
  | 'wait'
  /** Turu bitir: ``idle``e dön. */
  | 'end'
  /** Metin bitti ama ses sürüyor: turu AYAKTA tut. */
  | 'hold-for-audio'

/**
 * Bir sonraki adım.
 *
 * ``listening`` DOKUNULMAZ: kullanıcı çoktan yeni bir tur açmışsa (araya
 * girdi, ya da eller serbest mikrofonu yeniden açtı) turu bitirmek onun
 * kaydını yarıda keserdi.
 */
export function turnEndAction({ playbackIdle, replyComplete, status }: TurnEndInput): TurnEndAction {
  if (!replyComplete) {
    return 'wait'
  }

  if (status === 'listening') {
    return 'wait'
  }

  return playbackIdle ? 'end' : 'hold-for-audio'
}
