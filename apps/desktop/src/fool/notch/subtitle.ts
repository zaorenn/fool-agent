/**
 * Alt yazı: konuşulan cümlenin DUYULMUŞ kısmı.
 *
 * Kullanıcının isteği birebir: "model cevap verirken notchta modelin
 * söyledikleri eş zamanlı, alt yazı geçer gibi seslendirilen şey notchta parça
 * parça gözükmeli -- hem az yer kaplar böylece hem de modelin neyi
 * seslendirdiği görülür."
 *
 * Eskiden cümle DUYULMAYA başladığı anda BÜTÜN olarak yazılıyordu. Doğruydu
 * ama iri: uzun bir cümle tek karede çentiğe düşüyor ve okunan yer ile
 * ekrandaki metin ancak cümle başlarında hizalanıyordu.
 *
 * İki kural bu dosyada:
 *
 *   * KELİME sınırında aç. Karakter karakter açmak, yarım kelimeler
 *     ("merhab") üretir ve okunaksızdır.
 *   * KUYRUĞU göster. Uzun bir cümlenin tamamı yine yer kaplardı; ekranda
 *     son birkaç kelime duruyor, yani şerit sabit kalıyor.
 *
 * Zone A: upstream bu dosyayı bilmiyor.
 */

/**
 * Ekranda tutulan en fazla kelime sayısı.
 *
 * Şerit artık ekranın enine yayılıyor (bkz. ``notch-shell.tsx``
 * ``SUBTITLE_MARGIN`` ve ``electron/fool-notch.ts``), o yüzden sınır dar bir
 * kutuya göre değil o genişliğe göre seçildi -- kullanıcının beklentisi
 * "modelin cevabı tamamen sığar çoğu zaman".
 *
 * Sınır yine de VAR: sınırsız bırakmak, uzun bir cevabın şeridi taşırıp
 * ortadan kesilmesi demekti. Kuyruk gösterildiği için konuşulan yer her zaman
 * görünüyor.
 */
export const SUBTITLE_TAIL_WORDS = 30

/**
 * Cümlenin ``ratio`` kadarını KELİME sınırında aç.
 *
 * ``ratio`` sesin kendi saatinden geliyor (bkz.
 * ``lib/voice-playback.ts::onSentenceProgress``), yani açılan metin gerçekten
 * duyulmuş olanla hizalı.
 */
export function subtitleUpTo(sentence: string, ratio: number): string {
  const text = sentence.trim()

  if (!text) {
    return ''
  }

  const clamped = Math.min(Math.max(ratio, 0), 1)

  if (clamped >= 1) {
    return text
  }

  const words = text.split(/\s+/)
  // ``ceil``: oran sıfırın üstüne çıkar çıkmaz İLK kelime görünsün. ``floor``
  // ile cümlenin başında bir süre boş şerit kalıyordu.
  const shown = Math.min(words.length, Math.ceil(clamped * words.length))

  return words.slice(0, shown).join(' ')
}

/**
 * Şeridi sabit tutan kuyruk.
 *
 * Sadece son ``limit`` kelime kalıyor. Kesildiğinde başa bir elips geliyor --
 * yoksa cümle ortasından başlıyormuş gibi okunurdu.
 */
export function subtitleTail(text: string, limit: number = SUBTITLE_TAIL_WORDS): string {
  const words = text.trim().split(/\s+/).filter(Boolean)

  if (words.length <= limit) {
    return words.join(' ')
  }

  return `… ${words.slice(-limit).join(' ')}`
}

/** Duyulan kısmın, şerit boyuna kırpılmış hâli. */
export function spokenSubtitle(sentence: string, ratio: number, limit: number = SUBTITLE_TAIL_WORDS): string {
  return subtitleTail(subtitleUpTo(sentence, ratio), limit)
}
