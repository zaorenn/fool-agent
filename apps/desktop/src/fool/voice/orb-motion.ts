/**
 * Friend penceresinin canlı küresi — saf matematik, DOM'suz, sınanabilir.
 *
 * Neden ayrı ve saf
 * -----------------
 * Bu şeyin tek işi "makine seni duyuyor" hissini vermek. O his ölçülebilir
 * bir şeye dayanıyor: küre GERÇEK mikrofon seviyesini takip etmeli, rastgele
 * kıpırdamamalı. Rastgele animasyon ilk bakışta aynı görünüyor ama kullanıcı
 * konuşmayı kestiğinde de oynamaya devam ediyor ve his anında bozuluyor --
 * "beni duymuyor, sadece oynuyor".
 *
 * Matematik React'ten ayrıldı çünkü asıl kırılganlık burada: yumuşatma
 * sabitleri yanlışsa küre ya titriyor ya da geç kalıyor, ve ikisi de bir
 * render testinde görünmüyor.
 */

/** Kürenin dinlenme yarıçapı (0..1 ölçeğinde). */
export const BASE_SCALE = 1

/** Sesin ekleyebileceği en fazla büyüme. */
export const MAX_GROWTH = 0.38

/**
 * Yükselirken hızlı, düşerken yavaş.
 *
 * Simetrik yumuşatma yanlış hissettiriyor: konuşma başladığında küre geç
 * tepki veriyor, bittiğinde ise aniden sönüyor. İnsan sesi de böyle
 * davranmıyor -- atak keskin, sönüm yumuşak.
 */
export const ATTACK = 0.45
export const RELEASE = 0.12

/** Bu seviyenin altı sessizlik sayılıyor -- ``HANDS_FREE_VAD`` ile aynı eşik. */
export const SILENCE_LEVEL = 0.075

export type OrbPhase = 'idle' | 'listening' | 'speaking' | 'thinking'

export interface OrbState {
  /** Yumuşatılmış seviye 0..1. */
  level: number
  /** Kesintisiz artan faz -- nefes/dönme animasyonlarını besliyor. */
  phase: number
}

export const createOrbState = (): OrbState => ({ level: 0, phase: 0 })

/**
 * Bir kare ilerlet.
 *
 * ``dtMs`` gerçek geçen süre: sabit varsaymak, kare atlayan bir makinede
 * animasyonu yavaşlatıyordu. Faz süreye bağlı, kare sayısına değil.
 */
export function advance(state: OrbState, input: number, dtMs: number): OrbState {
  const target = Number.isFinite(input) ? Math.min(1, Math.max(0, input)) : 0
  const rising = target > state.level
  const smoothing = rising ? ATTACK : RELEASE

  // Yumusatma kare hizindan BAGIMSIZ: 60 fps'te ayni sabit, 30 fps'te iki
  // kat daha az uygulanirdi ve animasyon makineye gore degisirdi.
  const step = 1 - Math.pow(1 - smoothing, Math.max(dtMs, 1) / 16.67)

  state.level += (target - state.level) * step
  state.phase = (state.phase + dtMs / 1000) % 1_000

  return state
}

/**
 * Kürenin o andaki ölçeği.
 *
 * ``thinking`` fazında ses YOK ama küre ölmemeli: model 1-3 saniye
 * üretiyor ve donmuş bir küre "kilitlendi" gibi duruyor. O yüzden orada
 * yavaş bir nefes var.
 */
export function scaleFor(state: OrbState, phase: OrbPhase): number {
  if (phase === 'thinking') {
    return BASE_SCALE + 0.06 * (0.5 + 0.5 * Math.sin(state.phase * 2.4))
  }

  if (phase === 'idle') {
    // Bostayken cok hafif bir nefes: tamamen hareketsiz bir kure kapali
    // gorunuyor, kullanici tiklayip tiklamayacagini bilemiyor.
    return BASE_SCALE + 0.02 * (0.5 + 0.5 * Math.sin(state.phase * 1.1))
  }

  return BASE_SCALE + MAX_GROWTH * state.level
}

/** Halkaların opaklığı — seviye yükseldikçe belirginleşiyor. */
export function ringOpacity(state: OrbState, phase: OrbPhase, index: number): number {
  const base = phase === 'idle' ? 0.06 : 0.12
  const spread = 1 - index * 0.22

  return Math.max(0, Math.min(1, (base + state.level * 0.55) * spread))
}

/**
 * Kullanıcı şu an konuşuyor mu?
 *
 * Kürenin rengini değiştirmek için değil, "duyuyorum" ipucunu göstermek
 * için: eşiğin altındaki oda gürültüsünde ipucu yanıp sönmemeli.
 */
export function isHearing(state: OrbState, phase: OrbPhase): boolean {
  return phase === 'listening' && state.level >= SILENCE_LEVEL
}
