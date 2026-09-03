// FOOL-SEAM: i18n-brand
// Katalog, The Fool marka dönüşümünden geçirilir. Bu bir kopya değil bir
// dönüşüm olduğu için upstream yeni metin eklediğinde o da otomatik markalanır.
// Kaybolursa: tüm arayüz "The Fool"e döner. Bkz. docs/fool/SEAMS.md
//
// AÇILIŞTA YALNIZCA İNGİLİZCE
// ---------------------------
// Beş katalog da statik olarak içe aktarılıyor ve hepsi birden markalanıyordu::
//
//     export const TRANSLATIONS = applyFoolBrand({ en, zh, 'zh-hant', ja, ar })
//
// Ölçüldü (gerçek yapı ve gerçek kataloglar):
//
//     i18n parçası                 599,8 KB   AÇILIŞ grafiğinde
//     markalama, beş dil           9-15 ms    senkron, modül başlatmada
//     markalama, yalnız İngilizce  1,8 ms
//     dolaşılan düğüm              13.079 metin + 1.810 işlev + 1.181 nesne
//
// Kullanıcı her zaman TEK bir dil okuyor; diğer dördü ayrıştırılıp
// markalanıp bellekte tutuluyordu -- ``applyFoolBrand`` derin KOPYA ürettiği
// için hem özgün hem markalı hâli.
//
// İngilizce STATİK kalıyor: hem varsayılan hem de eksik anahtarların geri
// düşüşü (``runtime.translateFrom``), yani her zaman gerekli. Diğer dört dil
// istendiğinde geliyor.
import { applyFoolBrand } from '../fool/branding'

import { en } from './en'
import { DEFAULT_LOCALE } from './languages'
import type { Locale, Translations } from './types'

/** Yüklenmiş ve markalanmış kataloglar. İngilizce her zaman burada. */
const branded: Partial<Record<Locale, Translations>> = {
  en: applyFoolBrand(en)
}

/** ``null`` = statik (İngilizce). Diğerleri istendiğinde yükleniyor. */
const LOADERS: Record<Locale, (() => Promise<Translations>) | null> = {
  en: null,
  ar: async () => applyFoolBrand((await import('./ar')).ar),
  ja: async () => applyFoolBrand((await import('./ja')).ja),
  zh: async () => applyFoolBrand((await import('./zh')).zh),
  'zh-hant': async () => applyFoolBrand((await import('./zh-hant')).zhHant)
}

const inflight = new Map<Locale, Promise<void>>()
const listeners = new Set<() => void>()

/**
 * Bu dilin kataloğu — yüklenmediyse İNGİLİZCE.
 *
 * Geri düşüş sessiz ve doğru: ``translateFrom`` zaten eksik anahtarlarda
 * İngilizceye düşüyor, yani "henüz yüklenmedi" hâli o davranışın aynısı.
 */
export function catalogFor(locale: Locale): Translations {
  return branded[locale] ?? (branded[DEFAULT_LOCALE] as Translations)
}

export function isLocaleCatalogLoaded(locale: Locale): boolean {
  return branded[locale] !== undefined
}

/** Bu dilin kataloğunu yükle. Zaten yüklüyse/yükleniyorsa yeni iş başlatmaz. */
export function ensureLocaleCatalog(locale: Locale): Promise<void> {
  if (branded[locale]) {
    return Promise.resolve()
  }

  const load = LOADERS[locale]

  if (!load) {
    return Promise.resolve()
  }

  let pending = inflight.get(locale)

  if (!pending) {
    pending = load()
      .then(catalog => {
        branded[locale] = catalog
        listeners.forEach(notify => notify())
      })
      .catch(() => {
        // Katalog gelmezse arayüz İngilizce kalıyor -- boş ekrandan iyi.
      })
      .finally(() => {
        inflight.delete(locale)
      })

    inflight.set(locale, pending)
  }

  return pending
}

/**
 * Hazır bir kataloğu doğrudan kaydet (markalamadan GEÇİRİLİR).
 *
 * Üretim yolunda kullanılmıyor: orada kataloglar ``ensureLocaleCatalog`` ile
 * istendiğinde geliyor ve açılış grafiğinde durmuyorlar -- bu dosyanın
 * başındaki ölçüm bunun için.
 *
 * Sınav kurulumu (``vitest.setup.ts``) bunu STATİK içe aktarımla kullanıyor:
 * her sınav dosyası için ayrı ayrı dinamik yükleme yapmak, aynı modülleri 529
 * kez çözdürmek olurdu. Statik içe aktarım işçi başına bir kez çözülüyor ve
 * sınav dosyası başına ek maliyet kalmıyor.
 */
export function registerLocaleCatalog(locale: Locale, catalog: Translations): void {
  branded[locale] = applyFoolBrand(catalog)
  listeners.forEach(notify => notify())
}

/** Bir katalog indiğinde haber ver (modül düzeyi çevirmenler için). */
export function onLocaleCatalogLoaded(listener: () => void): () => void {
  listeners.add(listener)

  return () => {
    listeners.delete(listener)
  }
}
