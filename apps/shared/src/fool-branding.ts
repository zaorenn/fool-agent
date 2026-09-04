/**
 * The Fool — marka kimliğinin TEK kaynağı (TypeScript tarafı).
 *
 * Bu dosya upstream'de yok, dolayısıyla `git merge upstream/main` sırasında
 * çakışmaz.
 *
 * `apps/shared` altında duruyor çünkü İKİ ayrı derleme onu kullanıyor:
 * masaüstü uygulaması (`apps/desktop`) ve web panosu (`web`). Kuralları iki
 * dosyaya kopyalamak, ikisinin zamanla ayrışması demekti — aynı ürünün iki
 * yüzeyi farklı markalar gösterirdi.
 *
 * Buradaki `applyFoolBrand()` bir *kopya* değil bir *dönüşümdür*. i18n
 * kataloğuna tek bir dikişten (FOOL-SEAM: i18n-brand, `src/i18n/catalog.ts`)
 * bağlanır ve tüm dillerdeki metinleri geçerken markalar. Bunun sonucu:
 * upstream yarın "The Fool" içeren 50 yeni metin eklerse, onlar da hiçbir şey
 * yapmadan The Fool olur. Bakım maliyeti sıfır.
 *
 * @see docs/fool/SEAMS.md
 * @see docs/fool/ARCHITECTURE.md
 */

export const BRAND = {
  /** Ürünün konuşma dilindeki adı. */
  name: 'The Fool',
  /** Açılış ekranındaki büyük harf logotype (intro.tsx). */
  wordmark: 'THE FOOL',
  /** Masaüstü uygulamasının tam adı. */
  desktop: 'The Fool Desktop',
  /**
   * Ajanın KENDİNİ tanıttığı ad — sistem promptuna giren kimlik.
   * Ürün "The Fool", ajan "Fool Agent"; upstream'deki
   * "The Fool" / "Fool Agent" ayrımının karşılığı.
   */
  agent: 'Fool Agent',
  /**
   * Projenin KENDİ üretici/yazar adı. Eskiden "Nous Research"ün
   * yerine geçen ad buydu; o değiştirme kaldırıldı -- gerekçesi
   * aşağıdaki RULES listesinde.
   */
  vendor: 'zaorenn',
  /** Terminal komutu — pyproject `[project.scripts]` ile eşleşmeli. */
  cli: 'fool',
  /** Veri dizini adı — `~/.fool`. Python tarafıyla eşleşmeli. */
  homeDirName: '.fool',
  /** electron-builder appId. */
  appId: 'com.fool.desktop',
  /** Derin bağlantı şeması — fool://... */
  protocol: 'fool'
} as const

/**
 * Sıra ÖNEMLİ: en uzun/en özel kalıp önce gelmeli, yoksa "The Fool Desktop"
 * daha genel olan "The Fool" kuralı tarafından yenir ve "The Fool Desktop"
 * yerine "The Fool Desktop" üretilemez.
 *
 * `\b` sınırları sayesinde iç sözleşmeye DOKUNULMAZ — regex'te `_` bir kelime
 * karakteri olduğu için:
 *   FOOL_HOME  → eşleşmez (HERMES'ten sonra `_` var, `\b` yok)
 *   fool_cli   → eşleşmez (aynı sebep)
 *   ~/.fool    → eşleşir  (`.` kelime karakteri değil) — ve zaten değişmesini
 *                  istediğimiz yer burası
 */
const RULES: ReadonlyArray<readonly [RegExp, string]> = [
  [/\bHERMES\s+DESKTOP\b/g, BRAND.desktop.toUpperCase()],
  [/\bHERMES\s+AGENT\b/g, BRAND.agent.toUpperCase()],
  [/\bHermes\s+Desktop\b/g, BRAND.desktop],
  // "Fool Agent" -> "Fool Agent": ajanın tam adı. Açılış logotype'ı bu
  // kuraldan GEÇMEZ, doğrudan BRAND.wordmark'tan geliyor (intro.tsx).
  [/\bHermes\s+Agent\b/g, BRAND.agent],
  // "Nous Research" İÇİN KURAL YOK -- bilerek.
  //
  // Hermes'i yeniden adlandırmak meşru: çatalladığımız ürün o.
  // Nous Research ise çatallanan bir şey değil, gerçek bir şirket --
  // Portal onun, kartı o çekiyor, Hermes 3/4 modelleri onun. Adını
  // değiştirmek metni YANLIŞ yapıyordu. Python tarafındaki _RULES
  // ile birebir aynı tutulmalı.
  [/\bHERMES\b/g, BRAND.wordmark],
  [/\bHermes\b/g, BRAND.name],
  [/\bhermes\b/g, BRAND.cli]
]

/**
 * Ad "The" içerdiği için ham değiştirme yer yer bozuk İngilizce üretir:
 *   "Restore a Fool backup"      -> "Restore a Fool backup"      ✗
 *   "Open the safe Fool console" -> "Open the safe Fool console"  ✗
 *
 * Bir artikel zaten varsa "The" düşer ve ad sıradan bir özel isim gibi davranır.
 * Tek başına geçtiğinde tam ad korunur ("The Fool couldn't start").
 *
 * Pencere bilinçli olarak BİR kelime: iki kelimelik pencere
 * "a standing goal The Fool works on" ifadesini de yanlışlıkla yakalıyordu —
 * oradaki artikel ürüne değil "goal" ismine ait.
 *
 * Python tarafındaki `_ARTICLE_FIX` ile birebir aynı tutulmalı.
 */
const ARTICLE_FIX: ReadonlyArray<readonly [RegExp, string]> = [
  [/\b(a|an|the|your|my|its|their)\s+((?:\w+\s+){0,1}?)The\s+Fool\b/gi, '$1 $2Fool'],
  [/\bThe\s+The\s+Fool\b/g, 'The Fool']
]

/**
 * URL'ler ve alan adları markalamadan MUAF.
 *
 * Ölçülen hata: son kural (``\bhermes\b`` -> ``fool``) ``-`` sınırında da
 * eşleşiyor, yani kataloğun içindeki
 *
 *     curl -fsSL https://hermes-agent.nousresearch.com/install.sh | sh
 *
 * kullanıcıya
 *
 *     curl -fsSL https://fool-agent.nousresearch.com/install.sh | sh
 *
 * olarak gösteriliyordu -- var olmayan bir alan adı, dört dilde birden, hem de
 * kullanıcının kopyalayıp çalıştırması beklenen bir komutun içinde.
 *
 * Argümanlar için bu koruma ZATEN vardı (``brandTextPreserving``, hemen
 * aşağıda -- ve gerekçesi aynı alan adını örnek veriyor); eksik olan şablonun
 * KENDİ metnindeki URL'lerdi. Bir alan adı marka değil ADRESTİR: yanlış olması,
 * metnin garip görünmesi değil komutun çalışmaması demek.
 *
 * İşaret kod noktasından kuruluyor (``brandTextPreserving`` ile aynı gerekçe):
 * kaynağa ham NUL yazmak dosyayı ikili yapar ve grep/diff körleşir.
 */
const URL_LIKE_RE = /\b(?:[a-z][a-z0-9+.-]*:\/\/|www\.)[^\s<>"'`]+|\b[a-z0-9](?:[a-z0-9-]*\.)+[a-z]{2,}(?:\/[^\s<>"'`]*)?/gi

/** Tek bir metni markala. Dışarıdan da kullanılabilir (ör. sabit stringler). */
export function brandText(input: string): string {
  // URL'ler ÖNCE saklanıyor: markalama kuralları onları göremesin.
  const mark = String.fromCharCode(0)
  const urls: string[] = []

  let out = input.replace(URL_LIKE_RE, match => {
    urls.push(match)

    return `${mark}url${urls.length - 1}${mark}`
  })

  for (const [pattern, replacement] of RULES) {
    out = out.replace(pattern, replacement)
  }

  for (const [pattern, replacement] of ARTICLE_FIX) {
    out = out.replace(pattern, replacement)
  }

  for (let i = urls.length - 1; i >= 0; i -= 1) {
    out = out.split(`${mark}url${i}${mark}`).join(urls[i])
  }

  return out
}

/**
 * Değeri tipine göre özyinelemeli markalar.
 *
 * i18n kataloğu düz bir string haritası DEĞİL: içinde iç içe nesneler,
 * diziler ve `project => \`New session in ${project}\`` gibi fonksiyonlar var.
 * Fonksiyonlar çağrı anında string ürettiği için, fonksiyonun kendisini değil
 * DÖNÜŞ DEĞERİNİ markalamamız gerekir — bu yüzden sarmalıyoruz.
 */
/**
 * ``input``u markalar ama ``args``tan gelen dizeleri OLDUĞU GİBİ bırakır.
 *
 * Yer tutucu, metinde kendiliğinden bulunamayacak bir işaret: markalama
 * kuralları onu göremez, sonra yerine aslı konur. Uzun argüman ÖNCE
 * korunuyor -- kısa olan uzunun içinde geçiyorsa önce kısayı değiştirmek
 * uzunu parçalardı.
 */
function brandTextPreserving(input: string, args: readonly unknown[]): string {
  const literals = args
    .filter((a): a is string => typeof a === 'string' && a.length > 0)
    .sort((a, b) => b.length - a.length)

  if (literals.length === 0) {
    return brandText(input)
  }

  // Isaret KACISLA degil kod noktasindan kuruluyor: kaynaga ham NUL
  // yazmak dosyayi ikili yapar ve grep/diff korlesir.
  const mark = String.fromCharCode(0)
  const kept: string[] = []
  let out = input

  for (const literal of literals) {
    if (!out.includes(literal)) {
      continue
    }

    const token = `${mark}fool${kept.length}${mark}`

    kept.push(literal)
    out = out.split(literal).join(token)
  }

  out = brandText(out)

  for (let i = kept.length - 1; i >= 0; i -= 1) {
    out = out.split(`${mark}fool${i}${mark}`).join(kept[i])
  }

  return out
}

function brandValue(value: unknown): unknown {
  if (typeof value === 'string') {return brandText(value)}

  if (typeof value === 'function') {
    const fn = value as (...args: unknown[]) => unknown

    return (...args: unknown[]) => {
      const out = fn(...args)

      // Sablonun KENDI sozcukleri markalanir, ICINE konan VERI markalanmaz.
      //
      // Once dogrudan ``brandValue(fn(...args))`` yaziliydi ve sonuc butun
      // haliyle donusumden geciyordu -- yani sablona interpolate edilen
      // calisma zamani verisi de. Olculen zarar:
      //
      //   hostnameOf(url)  "hermes-agent.nousresearch.com" ->
      //                    "fool-agent.nousresearch.com"   (var olmayan alan)
      //
      // Ayni sey dosya yollari, oturum baslıklari ve arama sorgulari icin de
      // gecerli: bu depoda calisan biri icin yollar surekli ``hermes-agent``
      // tasiyor, yani kullaniciya yanlis metin gosteriliyordu.
      return typeof out === 'string' ? brandTextPreserving(out, args) : brandValue(out)
    }
  }

  if (Array.isArray(value)) {return value.map(brandValue)}

  if (value !== null && typeof value === 'object') {
    const out: Record<string, unknown> = {}

    for (const [key, val] of Object.entries(value as Record<string, unknown>)) {
      out[key] = brandValue(val)
    }

    return out
  }

  // number | boolean | null | undefined | symbol — olduğu gibi geçer.
  return value
}

/**
 * i18n kataloğunun tamamını markalayarak döndürür. Tip korunur, böylece
 * upstream'in `Translations` sözleşmesi bozulmaz ve tip denetimi çalışmaya
 * devam eder.
 */
export function applyFoolBrand<T>(catalog: T): T {
  return brandValue(catalog) as T
}
