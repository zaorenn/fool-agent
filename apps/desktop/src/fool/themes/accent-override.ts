/**
 * Canlı vurgu rengi katmanı — "biraz daha yeşil yap" dendiğinde anında değişir.
 *
 * Neden ayrı bir katman gerekti
 * -----------------------------
 * Backend'de ``fool skin set ui_accent '#22c55e'`` çalışıyor, dosyaya yazıyor
 * ve ağ geçidi ``skin.changed`` yayınlıyor. Masaüstünde HİÇBİR ŞEY olmuyordu.
 * Sebebi ölçüldü: ``the-fool`` teması ``BUILTIN_THEMES`` içinde kayıtlı ve
 * ``ingestBackendSkin`` yerleşik adları bilerek gölgelemiyor ("built-in names
 * already have a hand-tuned desktop palette — we never shadow it"). Yani el
 * yapımı palet kazanıyor ve backend'in rengi hiç görünmüyor.
 *
 * İki çözüm vardı: temayı yerleşiklikten çıkarmak (el yapımı paleti kaybetmek)
 * ya da paletin ÜSTÜNE ince bir vurgu katmanı sermek. İkincisi seçildi, çünkü
 * o zaman renk değiştirme HANGİ tema aktifse onunla çalışıyor — mono, slate,
 * kullanıcının kendi teması, hepsi.
 *
 * Neden CSS değişkeni, neden tema nesnesi değil
 * ---------------------------------------------
 * Tema nesnesini yeniden türetmek tüm paleti (kontrast hesapları, karışımlar)
 * yeniden üretir ve gözle görülür bir sıçrama yaratır. Yalnızca vurguya bağlı
 * değişkenleri yazmak tek karede biter ve geçiş yumuşak olur.
 *
 * Zone A: upstream bu dosyayı bilmiyor.
 */

import { atom } from 'nanostores'

/** Backend'in bildirdiği vurgu rengi. ``null`` = temanın kendi rengi kalsın. */
export const $accentOverride = atom<null | string>(null)

/**
 * Vurguya bağlı değişkenler.
 *
 * Liste kasıtlı olarak dar: paletin tamamını ezmek temayı bozar (arka planlar,
 * kenarlıklar, metin kontrastları el yapımı). Burada yalnızca "vurgu" anlamına
 * gelen değişkenler var — odak halkası, aktif sekme, düğme, notch dalga formu.
 */
const ACCENT_VARS = [
  '--theme-primary',
  '--theme-midground',
  '--ring',
  '--primary',
  '--composer-ring'
] as const

/** Hex rengi geçerli mi? Geçersiz değer tüm arayüzü renksiz bırakırdı. */
export function isValidHex(value: unknown): value is string {
  return typeof value === 'string' && /^#[0-9a-f]{3,8}$/i.test(value.trim())
}

/**
 * Vurgu rengini uygula (ya da ``null`` ile geri al).
 *
 * ``setProperty`` doğrudan ``:root``a yazıyor; tema motoru da aynı değişkenleri
 * yazdığı için bu katman her zaman ONUN ÜSTÜNDE kalır ve tema değişince
 * yeniden uygulanması gerekir (bkz. context.tsx'teki dikiş).
 */
export function applyAccentOverride(color: null | string): void {
  if (typeof document === 'undefined') {
    return
  }

  const root = document.documentElement

  for (const name of ACCENT_VARS) {
    if (color && isValidHex(color)) {
      root.style.setProperty(name, color)
    } else {
      root.style.removeProperty(name)
    }
  }
}

/**
 * Backend skin'inden vurgu rengini çıkar.
 *
 * Koyu/açık ayrımı: masaüstü koyu modda ``colors``, açık modda ``light_colors``
 * okuyor. Yanlış bölümü almak "yeşil yap" dediğinde hiçbir şeyin değişmemesine
 * yol açıyordu — ilk denemede tam bu oldu.
 */
export function accentFromSkin(skin: unknown, dark: boolean): null | string {
  if (!skin || typeof skin !== 'object') {
    return null
  }

  const record = skin as Record<string, unknown>

  const section = (dark ? record.colors : record.light_colors ?? record.colors) as
    | Record<string, unknown>
    | undefined

  const value = section?.ui_accent

  return isValidHex(value) ? value.trim() : null
}
