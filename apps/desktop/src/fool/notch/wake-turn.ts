/**
 * Uyandırma turunun BİTTİĞİNİ anlamak.
 *
 * Turun sonu geri açma anıdır: dinleyici saptamada duraklatılıyor ve tur
 * bitmeden geri açılırsa saptayıcı kendi TTS cevabımızı dinler (bkz.
 * ``active-session.ts::$wakeTurnActive``).
 *
 * "Durum ``idle`` olunca bitmiştir" TEK BAŞINA yanlış, iki ayrı yerden:
 *
 *   * Tur BAŞLARKEN durum zaten ``idle`` -- onay sesi çalıyor, mikrofon henüz
 *     açılmadı. Naif kural turu daha başlamadan bitmiş sayardı.
 *   * Mikrofon hiç açılamazsa (izin yok, aygıt meşgul) ``begin`` doğrudan
 *     ``idle``a düşüyor ve tur ``idle`` DIŞINA hiç çıkmıyor. "Bir kez etkin
 *     gördüysem" latch'i tek başına bu turda hiç kurulmaz ve bayrak sonsuza
 *     kadar takılı kalır -- yani kulak kalıcı olarak kapanır. Düzeltilen
 *     hatanın TA KENDİSİ.
 *
 * Bu yüzden iki aşama var: tur etkin olduğunu bir kez gösterene kadar KISA bir
 * mühlet, sonrasında ``idle`` gerçekten bitiş demek. Mühlet yalnızca hiç
 * başlayamamış bir turda dolabilir -- konuşma sürerken durum ``idle`` değil,
 * o yüzden turun ortasında geri açma riski yok.
 *
 * Zone A: upstream bu dosyayı bilmiyor.
 */

import type { NotchStatus } from './use-notch-voice'

/**
 * Turun etkin olduğunu göstermesi için tanınan süre.
 *
 * Yalnızca BAŞLAYAMAMIŞ bir turu kurtarmak için: mikrofon açılıyorsa durum
 * saniyeler içinde ``listening`` oluyor. Uzun tutmak, kulağın hatalı bir turdan
 * sonra o kadar süre sağır kalması demek.
 */
export const WAKE_TURN_START_GRACE_MS = 10_000

export type WakeTurnStep =
  /** Tur bitti -- dinleyici geri açılmalı. */
  | 'ended'
  /** Tur sürüyor: dinleniyor, yazıya dökülüyor, düşünülüyor ya da konuşuluyor. */
  | 'running'
  /** Henüz etkin olmadı; mühlet dolarsa hiç başlayamamış sayılır. */
  | 'waiting-start'

export function wakeTurnStep(seenActive: boolean, status: NotchStatus): WakeTurnStep {
  if (status !== 'idle') {
    return 'running'
  }

  return seenActive ? 'ended' : 'waiting-start'
}
