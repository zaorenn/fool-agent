// One window owns each cross-window ambient cue (turn-end sound, spoken reply)
// so N open full windows don't all fire it for the same backend event. The main
// process is the race-free owner (see electron/event-dedupe.ts). Off Electron —
// or when the bridge/claim fails — every window emits, preserving the
// single-window behavior rather than going silent.
/**
 * Bir turun konuşmasını üstlenen talep NE KADAR tutulur.
 *
 * Ölçülen hata: hakemin tek bir aralığı vardı (1 sn) ve konuşma için çok
 * kısaydı. Çentik İLK TOKEN'da talep ediyor, besteci ise cevap TAMAMLANINCA
 * -- aradan saniyeler geçtiği için ilk talep çoktan düşmüş oluyor, ikincisi
 * de kazanıyor ve kullanıcı aynı cümleleri iki kez duyuyordu.
 *
 * Anahtar TUR kapsamlı, o yüzden uzun tutmak güvenli: bir sonraki tur zaten
 * yeni bir anahtar alıyor.
 */
export const SPEECH_CLAIM_TTL_MS = 10 * 60 * 1000

export async function ownsAmbientCue(key: string, ttlMs?: number): Promise<boolean> {
  const claim = window.foolDesktop?.claimAmbientCue

  if (!claim) {
    return true
  }

  try {
    return await claim(key, ttlMs)
  } catch {
    return true
  }
}
