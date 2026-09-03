import { configure } from '@testing-library/react'

// Node 26 defines its own `localStorage` accessor on the global object, which
// returns `undefined` unless the process was started with --localstorage-file
// (it warns: "localStorage is not available because --localstorage-file was
// not provided"). In the jsdom environment `globalThis` IS the window, so that
// accessor shadows jsdom's Storage and every `localStorage.getItem(...)` in a
// test throws "Cannot read properties of undefined". Install a real in-memory
// Storage when the global resolves to nothing, before any test module reads it.
if (typeof (globalThis as any).localStorage === 'undefined') {
  const store = new Map<string, string>()
  const storage: Storage = {
    get length() {
      return store.size
    },
    key: (i: number) => [...store.keys()][i] ?? null,
    getItem: (k: string) => store.get(String(k)) ?? null,
    setItem: (k: string, v: string) => void store.set(String(k), String(v)),
    removeItem: (k: string) => void store.delete(String(k)),
    clear: () => store.clear(),
  }
  for (const target of [globalThis, (globalThis as any).window].filter(Boolean)) {
    Object.defineProperty(target, 'localStorage', {
      value: storage,
      configurable: true,
      writable: true,
    })
  }
}

// React 19 + Testing Library 16: opt into the act environment so render(),
// fireEvent(), and findBy* queries automatically flush state updates without
// spurious "not wrapped in act(...)" warnings.
;(globalThis as any).IS_REACT_ACT_ENVIRONMENT = true

// findBy*/waitFor default to a 1000ms deadline — too tight for async-heavy
// panels (radix menus, refetch chains) when the full suite runs under xdist
// CPU contention in CI. Success still resolves the instant the node appears;
// the wider deadline only absorbs a starved runner, killing timing flakes.
configure({ asyncUtilTimeout: 5000 })

// Çeviri katalogları sınavlarda ÖNCEDEN yüklü.
//
// Uygulamada İngilizce dışındaki kataloglar istendiğinde yükleniyor (bkz.
// `src/i18n/catalog.ts` — beşini birden açılışa bağlamak, gerçek yapıda
// ölçülen 599,8 KB'lık bir parçayı hiç okunmayacak dört dil için de
// ayrıştırmak demekti).
//
// Sınavların büyük çoğunluğu ÇEVİRİ İÇERİĞİNİ soruyor, yükleme ZAMANLAMASINI
// değil: `initialLocale="ja"` ile render edip Japonca metni arıyorlar. Her
// birine ayrı ayrı bekleme eklemek, sınavları asıl sordukları şeyden
// uzaklaştırırdı. Yükleme zamanlaması sözleşmesinin kendi sınavı var
// (`src/i18n/context.test.tsx`), ve o bilerek bekliyor.
//
// İçe aktarım STATİK: dinamik `import()` her sınav dosyasında yeniden
// çözülürdü (529 dosya x 4 katalog). Bu dosya yalnızca sınavlarda çalışıyor,
// yani üretim paketine hiçbir şey eklemiyor.
import { registerLocaleCatalog } from './src/i18n/catalog'
import { ar } from './src/i18n/ar'
import { ja } from './src/i18n/ja'
import { zh } from './src/i18n/zh'
import { zhHant } from './src/i18n/zh-hant'

registerLocaleCatalog('ar', ar)
registerLocaleCatalog('ja', ja)
registerLocaleCatalog('zh', zh)
registerLocaleCatalog('zh-hant', zhHant)

// Marka ikonu tablosu da ÖNCEDEN çözülü.
//
// `lib/external-link.tsx` onu dinamik `import()` ile çekiyor (167 `Si*`
// bileşeni açılış grafiğinde 229 KB tutuyordu). Sınavlarda o dinamik çözüm,
// paralel koşan 530 dosyanın yükü altında `waitFor` penceresini aşabiliyor ve
// ikonu bekleyen sınav zaman zaman düşüyordu -- ürün doğru, sınav kırılgan.
//
// Statik içe aktarım modülü işçinin grafiğine sokuyor; dinamik `import()`
// sonra onu önbellekten anında alıyor. Ürün yolu değişmiyor.
import './src/lib/brand-icon'
