/**
 * Notch kısayolunun DENEME SIRASI.
 *
 * Neden ayrı bir dosya
 * --------------------
 * Kaydın kendisi ``globalShortcut``a bağlı ve ana süreçte yaşıyor, ama
 * hangi kombinasyonun hangi sırayla deneneceği saf bir karar. ``main.ts``
 * içinde gömülü kaldığı sürece sınanamıyordu ve tam da orada bir hata
 * yapmak, kullanıcının tuşa basıp hiçbir şey olmadığını görmesi demek.
 *
 * Neden bir merdiven
 * ------------------
 * Tek bir kısayola bağlı kalmak çalışmıyor: Windows'ta Ctrl+Shift+Space'i
 * klavye düzeni değiştirme ve birçok IME zaten tutuyor, ve Electron'un
 * ``register()``ı bu durumda sessizce ``false`` dönüyor (ölçüldü: günlükte
 * "NOT registered"). Sırayla denenip ilk boş olan alınıyor.
 */

/**
 * Varsayılan sıra. İlk aday Ctrl+Alt+V: kullanıcının açıkça istediği
 * kombinasyon. Önce Ctrl+Shift+Space baştaydı ve o tuş Windows'ta klavye
 * düzeni değiştirmeyle çarpışıyor.
 */
export const NOTCH_SHORTCUT_CANDIDATES = [
  'CommandOrControl+Alt+V',
  'CommandOrControl+Shift+Space',
  'CommandOrControl+Alt+Space',
  'CommandOrControl+Shift+Semicolon',
  'F13'
] as const

/**
 * Denenecek kombinasyonlar, sırayla.
 *
 * Kullanıcının seçimi HER ZAMAN başta. Merdivenden çıkarılıyor ki iki kez
 * denenmesin -- ikinci deneme ilkinin kendi kaydına takılıp "tutulmuş" gibi
 * görünürdü.
 */
export function shortcutOrder(preferred: unknown): string[] {
  const wanted = typeof preferred === 'string' ? preferred.trim() : ''
  const ladder = NOTCH_SHORTCUT_CANDIDATES.filter(item => item !== wanted)

  return wanted ? [wanted, ...ladder] : [...ladder]
}
