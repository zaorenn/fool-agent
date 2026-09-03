/**
 * Kullanıcının verisinin kaderini belirleyen kapı — GERÇEKTEN sınanıyor.
 *
 * Bu karar bir süre ``main.ts`` içinde dosya sistemine gömülü durdu ve
 * yalnızca KAYNAK OKUYAN testlerle korunuyordu: "şu satır dosyada duruyor mu".
 * Öyle bir test kapının VARLIĞINI tutar, DAVRANIŞINI tutmaz -- ve buradaki
 * yanlış cevabın bedeli kullanıcıya bütün verisini kaybetmiş gibi görünmek.
 *
 * İki yön de tehlikeli ve ikisi de burada:
 *
 *   * Fazla gevşek: atılmış bir yol kabul edilir, uygulama her açılışta boş
 *     bir dizine girer. ("girlfriend gitmiş, ses klonlarım gitmiş")
 *   * Fazla hevesli: gerçek bir ev reddedilir, uygulama sessizce başka bir
 *     yere bakar ve yeni oturumlar YANLIŞ eve yazılır. Aynı görüntü, tersten.
 *
 * Zone A: upstream bu dosyayı bilmiyor.
 */

import assert from 'node:assert/strict'

import { test } from 'vitest'

import { looksLikeDiscardedHome } from './home-gate'

const WIN_SEP = '\\'

/** Windows benzeri bir dünya: hangi dizinlerin VAR olduğunu sen söylüyorsun. */
function windowsWorld(existing: string[], overrides: Partial<Parameters<typeof looksLikeDiscardedHome>[1]> = {}) {
  const present = new Set(existing.map(p => p.toLowerCase()))

  return {
    defaultHome: () => 'C:\\Users\\u\\AppData\\Local\\fool',
    directoryExists: (p: string) => present.has(p.toLowerCase()),
    resolve: (p: string) => p,
    rootOf: (p: string) => (/^[A-Za-z]:/.test(p) ? p.slice(0, 2) + WIN_SEP : ''),
    sep: WIN_SEP,
    tempDir: () => 'C:\\Users\\u\\AppData\\Local\\Temp',
    ...overrides
  }
}

// ---------------------------------------------------------------------------
// Reddedilmesi GEREKEN evler
// ---------------------------------------------------------------------------

test('%TEMP% ALTINDAKI ev reddediliyor -- var olsa bile', () => {
  // Ölçülen hasarın ta kendisi: `test:desktop:fresh` sandbox evini kalıcı
  // FOOL_HOME'a yazdı. Geçici bir dizin kalıcı bir ev olamaz -- işletim
  // sistemi onu istediği an siler, yani VAR olması bile yeterli değil.
  const home = 'C:\\Users\\u\\AppData\\Local\\Temp\\hermes-desktop-fresh-install-fNWZmX\\hermes-home'
  const world = windowsWorld([home, 'C:\\', 'C:\\Users\\u\\AppData\\Local\\fool'])

  assert.match(String(looksLikeDiscardedHome(home, world)), /gecici dizin altinda/)
})

test('%TEMP% DIZININ KENDISI de reddediliyor', () => {
  const home = 'C:\\Users\\u\\AppData\\Local\\Temp'

  assert.match(
    String(looksLikeDiscardedHome(home, windowsWorld([home, 'C:\\', 'C:\\Users\\u\\AppData\\Local\\fool']))),
    /gecici dizin altinda/
  )
})

test('YOK olan ev, varsayilan ev DURURKEN reddediliyor', () => {
  // Yapılandırma bir hayaleti gösteriyor, oysa gerçek veri duruyor.
  const home = 'C:\\Users\\u\\AppData\\Local\\fool-old'
  const world = windowsWorld(['C:\\', 'C:\\Users\\u\\AppData\\Local\\fool'])

  assert.equal(looksLikeDiscardedHome(home, world), 'dizin yok, varsayilan ev ise duruyor')
})

// ---------------------------------------------------------------------------
// Reddedilmemesi GEREKEN evler -- aynı hatanın aynası
// ---------------------------------------------------------------------------

test('VAR OLAN bir ev kabul ediliyor', () => {
  const home = 'F:\\The Fool\\data'
  const world = windowsWorld([home, 'F:\\', 'C:\\Users\\u\\AppData\\Local\\fool'])

  assert.equal(looksLikeDiscardedHome(home, world), null)
})

test('BAGLI OLMAYAN surucudeki ev reddedilmiyor', () => {
  // Asıl düzeltme burada. Evi çıkarılabilir ya da ağ sürücüsünde olan bir
  // kullanıcı diski takmadan uygulamayı açtığında, kapı önce evi reddedip
  // sessizce varsayılana düşüyordu. Hiçbir şey SİLİNMEZ -- ama gördüğü şey tam
  // olarak şikâyet ettiği şey olurdu: boş bir uygulama. Daha kötüsü, oradan
  // sonra yeni oturumlar YANLIŞ eve yazılır ve durum ikiye bölünür.
  //
  // Ulaşılamayan bir ev atılmış bir ev değil: iddia YOK, yapılandırma korunur,
  // arka uç gürültüyle başarısız olur.
  const home = 'F:\\The Fool\\data'
  const world = windowsWorld(['C:\\', 'C:\\Users\\u\\AppData\\Local\\fool']) // F:\ YOK

  assert.equal(looksLikeDiscardedHome(home, world), null)
})

test('surucu BAGLI ama dizin silinmisse reddediliyor', () => {
  // Ayrımın diğer yarısı: birim erişilebilirken dizin yoksa o yol gerçekten
  // atılmıştır. Bu kapı kalkarsa iyileştirme de kalkar.
  const home = 'F:\\The Fool\\data'
  const world = windowsWorld(['F:\\', 'C:\\Users\\u\\AppData\\Local\\fool']) // F:\ VAR, ev YOK

  assert.equal(looksLikeDiscardedHome(home, world), 'dizin yok, varsayilan ev ise duruyor')
})

test('varsayilan ev de YOKSA hicbir sey iddia edilmiyor', () => {
  // Taze bir makine: ne yapılandırılan ev var ne varsayılan. Reddetmek burada
  // hiçbir şeyi kurtarmaz, yalnızca kurulumu başka bir yere yönlendirirdi.
  const home = 'D:\\fool'
  const world = windowsWorld(['D:\\'])

  assert.equal(looksLikeDiscardedHome(home, world), null)
})

test('BENZER adli dizin %TEMP% sayilmiyor', () => {
  // ``...\Temporary`` ``...\Temp``in altında DEĞİL. Ayraç sınırı olmadan
  // startsWith karşılaştırması gerçek bir evi yutardı.
  const home = 'C:\\Users\\u\\AppData\\Local\\Temporary\\fool'
  const world = windowsWorld([home, 'C:\\', 'C:\\Users\\u\\AppData\\Local\\fool'])

  assert.equal(looksLikeDiscardedHome(home, world), null)
})

// ---------------------------------------------------------------------------
// Bilinmeyen durumlarda İDDİA YOK
// ---------------------------------------------------------------------------

test('cozulemeyen TEMP icin sandbox iddia EDILMIYOR', () => {
  const home = 'C:\\Users\\u\\AppData\\Local\\fool'

  const world = windowsWorld([home, 'C:\\', 'C:\\Users\\u\\AppData\\Local\\fool'], {
    tempDir: () => {
      throw new Error('temp yok')
    }
  })

  assert.equal(looksLikeDiscardedHome(home, world), null)
})

test('TEMP null donerse kural atlaniyor', () => {
  const home = 'C:\\Users\\u\\AppData\\Local\\fool'
  const world = windowsWorld([home, 'C:\\'], { tempDir: () => null })

  assert.equal(looksLikeDiscardedHome(home, world), null)
})

test('cozulemeyen YOL sebebiyle reddediliyor', () => {
  const world = windowsWorld([], {
    resolve: () => {
      throw new Error('bozuk yol')
    }
  })

  assert.equal(looksLikeDiscardedHome('\0', world), 'cozulemeyen yol')
})

test('KOK cozulemiyorsa birim ERISILEBILIR sayiliyor', () => {
  // Bilmediğimiz bir şey için "atılmış" demek, gerçek bir evi reddetmek olurdu
  // -- ama kök yoksa (göreli/UNC benzeri yol) ikinci kural yine çalışmalı.
  const home = '\\\\sunucu\\paylasim\\fool'
  const world = windowsWorld(['C:\\Users\\u\\AppData\\Local\\fool'], { rootOf: () => '' })

  assert.equal(looksLikeDiscardedHome(home, world), 'dizin yok, varsayilan ev ise duruyor')
})

// ---------------------------------------------------------------------------
// POSIX
// ---------------------------------------------------------------------------

test('POSIX: /tmp altindaki ev reddediliyor, /home altindaki kabul ediliyor', () => {
  const posix = (existing: string[]) => ({
    defaultHome: () => '/home/u/.fool',
    directoryExists: (p: string) => existing.includes(p),
    resolve: (p: string) => p,
    rootOf: () => '/',
    sep: '/',
    tempDir: () => '/tmp'
  })

  assert.match(
    String(looksLikeDiscardedHome('/tmp/fool-sandbox/home', posix(['/tmp/fool-sandbox/home', '/', '/home/u/.fool']))),
    /gecici dizin altinda/
  )
  assert.equal(looksLikeDiscardedHome('/home/u/.fool', posix(['/home/u/.fool', '/'])), null)
  // Bağlı olmayan bir bağlama noktası: kök yoksa iddia yok.
  assert.equal(looksLikeDiscardedHome('/mnt/disk/fool', posix(['/home/u/.fool'])), null)
})
