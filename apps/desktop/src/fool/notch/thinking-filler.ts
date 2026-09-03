/**
 * Düşünme sessizliğini doldurma — saf, DOM'suz, sınanabilir.
 *
 * Sorun
 * -----
 * Kullanıcı konuşmayı bitiriyor, model cevabı üretmeye başlıyor ve arada
 * 1-3 saniye TAM sessizlik oluyor. Ekranda "Thinking…" yazıyor ama kullanıcı
 * çoğu zaman ekrana bakmıyor — notch'un bütün amacı bu. Kulakta hiçbir şey
 * yok ve konuşma ölmüş gibi duyuluyor: kullanıcı ya tekrar konuşuyor (araya
 * girme sayılıyor) ya da bekleyip bekleyemeyeceğini bilemiyor.
 *
 * Neden her boşluk doldurulmuyor
 * ------------------------------
 * Kısa bir duraklama insan konuşmasında ZATEN var ve doldurulması gereken bir
 * kusur değil. Her turda "hmm" demek, bir süre sonra bir tik gibi duyuluyor
 * ve asıl sinir bozucu şey o oluyor. Kural bu yüzden dar:
 *
 *   * yalnızca boşluk GERÇEKTEN uzunsa (eşik altı hiç dolmuyor),
 *   * tur başına en fazla bir kez,
 *   * ve arka arkaya aynı sözcük gelmiyor.
 *
 * Zone A: upstream bu dosyayı bilmiyor.
 */

/**
 * Bu süreden kısa boşluklar doldurulmuyor.
 *
 * 1,2 sn insan konuşmasında normal bir düşünme duraklaması; altına inmek
 * doldurmayı gereksiz ve gürültülü yapardı. Ölçülen model gecikmesi 1-3 sn
 * olduğu için eşik hızlı cevapları eliyor ve yalnızca gerçekten uzun olanı
 * yakalıyor.
 */
export const FILL_AFTER_MS = 1_200

/**
 * Doldurma sözcükleri.
 *
 * Kısa, alçak sesli ve BİLGİ TAŞIMIYOR: "bir saniye" gibi bir söz verirsek
 * ve cevap hemen gelirse yalan söylemiş oluyoruz. Bunlar yalnızca "buradayım,
 * duydum" demek.
 */
export const FILLERS = ['Mm-hm.', 'Let me think.', 'One sec.', 'Right.'] as const

export interface FillerState {
  /** Bu turda dolduruldu mu? */
  usedThisTurn: boolean
  /** En son hangi sözcük söylendi — arka arkaya tekrar etmemek için. */
  lastIndex: number
}

export const createFillerState = (): FillerState => ({ lastIndex: -1, usedThisTurn: false })

/** Yeni tur başladı: sayaç sıfırlanır ama SON SÖZCÜK hatırlanır. */
export function resetTurn(state: FillerState): void {
  state.usedThisTurn = false
}

export interface ShouldFillInput {
  /** Model cevabı üretmeye başlayalı ne kadar oldu (ms). */
  elapsedMs: number
  /** Cevaptan HERHANGİ bir metin geldi mi? Geldiyse sessizlik bitti. */
  hasSpeechStarted: boolean
  /** Kullanıcı araya mı giriyor? O zaman doldurmak üstüne konuşmak olur. */
  interrupted: boolean
  /** Kullanıcı bu özelliği açık tutuyor mu? */
  enabled: boolean
}

/** Şimdi bir doldurma sözcüğü söylenmeli mi? */
export function shouldFill(state: FillerState, input: ShouldFillInput): boolean {
  if (!input.enabled || state.usedThisTurn) {
    return false
  }

  // Cevap gelmeye basladiysa sessizlik zaten bitti; ustune konusmak
  // kullanicinin duymak istedigi seyi bastirirdi.
  if (input.hasSpeechStarted || input.interrupted) {
    return false
  }

  return input.elapsedMs >= FILL_AFTER_MS
}

/**
 * Söylenecek sözcüğü seç ve durumu güncelle.
 *
 * Arka arkaya aynı sözcük gelmiyor: iki kez üst üste "Mm-hm" duymak, insanla
 * konuşmayı taklit etmeye çalışan bir makineye benziyor -- olmak istediğimiz
 * şeyin tam tersi.
 */
export function takeFiller(state: FillerState, random: () => number = Math.random): string {
  const options = FILLERS.map((_, index) => index).filter(index => index !== state.lastIndex)
  const picked = options[Math.floor(random() * options.length)] ?? 0

  state.lastIndex = picked
  state.usedThisTurn = true

  return FILLERS[picked]
}
