/**
 * Dinleme kipi: eller serbest mi, bas-konuş mu.
 *
 * Neden PAYLAŞILAN bir depo
 * -------------------------
 * Friend penceresi ve notch aynı mikrofonu ve aynı ses kanalını kullanıyor.
 * Kip her yüzeyde ayrı tutulunca kullanıcı iki ayrı hakikatle karşılaşıyordu:
 * Friend'de bas-konuşa alıyor, notch'a geçince mikrofon yine sürekli açık.
 * Aynı hata sesin kendisinde de yaşandı ve kullanıcı "Friend'in sesi ile
 * global ses aynı olmalı" dedi -- kip için de aynısı geçerli.
 *
 * Kalıcı, çünkü notch ve Friend AYRI pencereler: biri kapanıp açıldığında
 * diğerinin seçtiği kipi görmek zorunda.
 *
 * Zone A: upstream bu dosyayı bilmiyor.
 */

import { sharedAtom } from '../cross-window-atom'

export type ListenMode = 'hands-free' | 'push-to-talk'

/**
 * Varsayılan ELLER SERBEST.
 *
 * Sesli arayüzün amacı klavyeye dokunmadan konuşmak; varsayılanı bas-konuş
 * yapmak o amacı baştan iptal ederdi. Bas-konuş, gürültülü ortam için
 * bilinçli bir tercih.
 */
export const DEFAULT_LISTEN_MODE: ListenMode = 'hands-free'

const isListenMode = (value: unknown): value is ListenMode => value === 'hands-free' || value === 'push-to-talk'

/** Tanınmayan her şey varsayılana düşüyor. */
export const sanitizeListenMode = (raw: unknown): ListenMode => (isListenMode(raw) ? raw : DEFAULT_LISTEN_MODE)

export const $listenMode = sharedAtom<ListenMode>('fool.desktop.voice.listen-mode', DEFAULT_LISTEN_MODE, {
  decode: raw => sanitizeListenMode(raw),
  encode: value => sanitizeListenMode(value)
})

/** Kipi çevir -- notch'taki küçük düğme bunu çağırıyor. */
export function toggleListenMode(): ListenMode {
  const next: ListenMode = $listenMode.get() === 'hands-free' ? 'push-to-talk' : 'hands-free'

  $listenMode.set(next)

  return next
}

/** Düğmenin ipucu metni (İngilizce -- deponun kuralı). */
export function listenModeHint(mode: ListenMode, key: string): string {
  return mode === 'hands-free'
    ? `Hands-free — click for push-to-talk (${key})`
    : `Push-to-talk (${key}) — click for hands-free`
}
