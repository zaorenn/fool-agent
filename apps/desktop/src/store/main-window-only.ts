/**
 * Yalnızca ANA pencerede koş.
 *
 * Çentik ayrı bir ``BrowserWindow`` ama AYNI paketi yüklüyor (``?win=notch``,
 * bkz. ``electron/fool-notch.ts`` ve ``app/contrib/controller.tsx``). Yani içe
 * aktarma anında yan etkisi olan her modül İKİ KEZ koşuyor.
 *
 * Değer pencereye özelse zararsız. PAYLAŞILAN bir yere yazılıyorsa -- ana
 * süreç ya da pencereler arası bir atom -- çentiğin boş kopyası ana pencerenin
 * gerçeğini eziyor. İki kez yaşandı:
 *
 *   ``$voiceSessionId``  ses yanlış oturuma gitti, cevap bot panelinde çıktı
 *   ``setActiveWork``    çıkış muhafızı süren turu görmedi, akış kısıldı
 *
 * Yardımcı ORTAK çünkü her yayıncının kendi guard'ını yazması, birinin
 * unutması demek -- ve unutulan tam olarak yukarıdaki iki hatadır.
 *
 * Zone A: upstream bu dosyayı bilmiyor.
 */

let mainWindow: boolean | null = null

/**
 * ``fn`` yalnızca ana pencerede çalışır.
 *
 * Karar SENKRON. İlk yazımda dinamik ``import('@/fool/notch/window')``
 * kullanılmıştı -- katman ayrımı için, ama bedeli bir YARIŞ oldu: abonelik
 * ancak import çözüldükten sonra kuruluyordu ve o ana kadar başlayan tur
 * yayınlanmadan geçiyordu. ``store/active-work.test.ts``in üç sınavı tam
 * bunu gösteriyordu; yerel arayüz takımı ``@testing-library/react`` eksik
 * olduğu için hiç koşamadığından uzun süre görünmedi.
 *
 * Kontrolün kendisi tek satırlık bir sorgu okuması. Onu buraya kopyalamak,
 * arayüz katmanını depo katmanına bağlamamak için bilinçli: iki yer de aynı
 * ``?win=notch`` sözleşmesini okuyor (bkz. ``fool/notch/window.ts``).
 */
export function whenMainWindow(fn: () => void): void {
  if (typeof window === 'undefined') {
    return
  }

  if (mainWindow === null) {
    try {
      mainWindow = new URLSearchParams(window.location.search).get('win') !== 'notch'
    } catch {
      // Sorgu okunamadi: ANA pencere say. Yanlis tarafa dusmek, ana
      // pencerenin hic yayin yapmamasi demek olurdu -- sessiz sinif.
      mainWindow = true
    }
  }

  if (mainWindow) {
    fn()
  }
}
