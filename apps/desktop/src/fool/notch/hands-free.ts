/**
 * Eller serbest tur alma — saf, DOM'suz, sınanabilir.
 *
 * Neden bu kip var
 * ----------------
 * Bas-konuş telsiz gibi: bas, konuş, bırak, bekle, dinle. Bir insanla
 * konuşmaya benzemiyor. Oturum açıkken (Ctrl+Alt+V ya da uyandırma sözcüğü)
 * tur bittiği anda mikrofon kendiliğinden açılıyor; kullanıcı hiçbir şeye
 * dokunmadan cevap veriyor. Sağ Ctrl yine çalışıyor — gürültülü ortamda
 * kullanıcı kaydın sınırını kendi çizmek isteyebilir.
 *
 * Neden yeniden açma AYRI bir karar
 * ---------------------------------
 * Yanlış anda açmanın iki somut bedeli var ve ikisi de sessiz:
 *
 * 1. **Yankı döngüsü.** Ajan konuşurken mikrofonu açmak, hoparlörden çıkan
 *    sesi kullanıcı konuşması sanmak demek — Windows'ta yankı bastırma aynı
 *    uygulamanın kendi oynatmasını güvenilir biçimde kesmiyor. Ajan kendi
 *    cevabını duyup kendine cevap veriyor. Bu yüzden yeniden açma YALNIZCA
 *    tur tamamen bittiğinde (``idle``) oluyor; konuşma evresini araya girme
 *    izleyicisi (``barge-in.ts``) zaten kapsıyor.
 *
 * 2. **Sonsuz açık mikrofon.** Kullanıcı susarsa kayıt boşta zaman aşımıyla
 *    kapanıyor, durum ``idle``e dönüyor ve koşulsuz bir yeniden açma onu
 *    hemen tekrar açardı: mikrofon sonsuza kadar açık, kullanıcı odadan
 *    çıkmış. Art arda sessiz tur sayısı sınırlı; sınıra gelince kip
 *    kendini susturuyor ve kullanıcının konuşmaya dönmesini bekliyor.
 */

import type { NotchStatus } from './use-notch-voice'

export type NotchMode = 'hands-free' | 'push-to-talk'

/**
 * VAD ayarı ``tools.voice_mode`` varsayılanlarıyla AYNI.
 *
 * Tarayıcı döngüsünün CLI'dan farklı bir eşikte susması, aynı cümlenin iki
 * yüzeyde farklı yerde kesilmesi demekti — kullanıcı için "bazen cümlemi
 * yiyor" diye görünen, tekrar üretilemeyen bir hata.
 */
export const HANDS_FREE_VAD = {
  /** Bu seviyenin altı sessizlik sayılıyor. */
  silenceLevel: 0.075,
  /** Konuşmadan sonra bu kadar sessizlik turu bitiriyor. */
  silenceMs: 1_250,
  /** Hiç konuşulmazsa kayıt bu süre sonunda kendini kapatıyor. */
  idleSilenceMs: 12_000
} as const

/**
 * Art arda kaç sessiz tur sonra kip kendini susturur.
 *
 * Üç tur x 12 sn ≈ 36 saniye. Kullanıcı odadan çıktıysa mikrofon sonsuza
 * kadar açık kalmıyor; masaya döndüğünde sağ Ctrl ya da kısayol yeterli.
 */
export const MAX_IDLE_ROUNDS = 3

export interface RearmInput {
  mode: NotchMode
  status: NotchStatus
  /** Oturum açık mı? Kapalı oturumda mikrofon hiç açılmaz. */
  sessionActive: boolean
  /** Araya girme yakalaması sürüyor mu? O yol mikrofonu kendi yönetiyor. */
  capturing: boolean
  /** Art arda kaç tur hiç konuşulmadı. */
  idleRounds: number
}

/** Mikrofon kendiliğinden yeniden açılmalı mı? */
export function shouldRearmListening(input: RearmInput): boolean {
  if (input.mode !== 'hands-free' || !input.sessionActive) {
    return false
  }

  // Ajan hâlâ konuşuyor ya da düşünüyorsa açmak yankı döngüsü demek.
  if (input.status !== 'idle') {
    return false
  }

  if (input.capturing) {
    return false
  }

  return input.idleRounds < MAX_IDLE_ROUNDS
}

/**
 * Mikrofon hangi ayarlarla açılacak?
 *
 * Bas-konuşta ``undefined``: sessizlik saptayıcısı kullanıcı hâlâ tuşu basılı
 * tutarken kaydı kapatırdı — cümlenin ortasında kesilen bir kayıt.
 */
export function listenOptionsFor(mode: NotchMode): typeof HANDS_FREE_VAD | undefined {
  return mode === 'hands-free' ? HANDS_FREE_VAD : undefined
}

/**
 * Mikrofonu ne AÇTI?
 *
 * Kip oturumun değil, tek bir açılışın özelliği. Oturum eller serbest
 * olabilir ama kullanıcı yine de sağ Ctrl'ye basabilir — o kayıt bas-konuş
 * kuralıyla işlemeli. İkisini oturum düzeyinde bağlamak, tuşla açılan kaydın
 * kullanıcı hâlâ tuşu basılı tutarken sessizlik saptayıcısı yüzünden
 * kapanması demekti.
 */
export type BeginActivation = 'auto' | 'key'

export function modeForActivation(activation: BeginActivation): NotchMode {
  return activation === 'auto' ? 'hands-free' : 'push-to-talk'
}

/**
 * Sessiz tur sayacının yeni değeri.
 *
 * Konuşma duyulduysa sıfırlanıyor: kullanıcı orada, sayacın birikmiş olması
 * onu bir sonraki sessizlikte erken susturmamalı.
 */
export function nextIdleRounds(current: number, heardSpeech: boolean): number {
  return heardSpeech ? 0 : current + 1
}
