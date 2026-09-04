/**
 * Eski bir runtime "hazır" sayılmamalı.
 *
 * Ölçülen hata: kullanıcı yeni sürümü ikinci makineye kurdu; kurulum
 * tamamlandı, ``fool.exe`` yerindeydi, ``FOOL_HOME`` doğruydu -- ve uygulama
 * yine "background stopped" dedi, terminalde ``fool`` "Hermes Agent" açtı.
 * Yeni installer eski bir runtime'ın üstüne kurulmuş, onu güncellememişti.
 *
 * ``ensureRuntime`` sürümü hiç sormuyordu: kaynak dosyalar + Git Bash + venv
 * kontrolü YILLAR öncesine ait bir klonda da geçer.
 *
 * Zone A: upstream bu dosyayı bilmiyor.
 */

import assert from 'node:assert/strict'

import { test } from 'vitest'

import { classifyRuntimeVersion, describeRuntimeVersion, isUsableCommit, needsRepair } from './runtime-version'

const PINNED = 'b08e32ec1aae0f4631ccef9b07dce1de600e5b49'

test('ayni commit GUNCEL sayiliyor', () => {
  assert.equal(classifyRuntimeVersion(PINNED, PINNED), 'current')
  assert.equal(needsRepair(classifyRuntimeVersion(PINNED, PINNED)), false)
})

test('KISA bicim uzun bicimle ayni commit sayiliyor', () => {
  // git ikisini birlikte kullaniyor. Uzunluk farkini esitsizlik saymak,
  // guncel bir kurulumu SONSUZ onarim dongusune sokardi.
  assert.equal(classifyRuntimeVersion('b08e32ec1aae', PINNED), 'current')
  assert.equal(classifyRuntimeVersion(PINNED, 'b08e32ec1aae'), 'current')
})

test('FARKLI commit onarim gerektiriyor', () => {
  const old = '1111111111111111111111111111111111111111'

  assert.equal(classifyRuntimeVersion(old, PINNED), 'stale')
  assert.equal(needsRepair(classifyRuntimeVersion(old, PINNED)), true)
})

test('ILERIDEKI runtime onarilmiyor', () => {
  // Runtime pin'i ZATEN iceriyorsa eski olan runtime degil PAKET. Onarim
  // burada bir sey duzeltmez: mevcut bir klonu pakete geri cekmiyoruz
  // (``pinCommit = !existingCheckout``), yani karar her acilista ayni kalir
  // ve kullanici HER ACILISTA yukleyicinin tam turunu oderdi.
  const newer = '2222222222222222222222222222222222222222'

  assert.equal(classifyRuntimeVersion(newer, PINNED, true), 'ahead')
  assert.equal(needsRepair(classifyRuntimeVersion(newer, PINNED, true)), false)
})

test('pin runtime gecmisinde DEGILSE onarim suruyor', () => {
  const old = '1111111111111111111111111111111111111111'

  assert.equal(classifyRuntimeVersion(old, PINNED, false), 'stale')
  assert.equal(needsRepair(classifyRuntimeVersion(old, PINNED, false)), true)
})

test('ata sorusu CEVAPLANAMADIYSA eski davranis suruyor', () => {
  // ``null`` = git yok / klon bozuk / pin bu depoda degil. Iddia yok demek
  // "ileride" demek DEGIL: farkli commit hala onarilmali.
  const old = '1111111111111111111111111111111111111111'

  assert.equal(classifyRuntimeVersion(old, PINNED, null), 'stale')
})

test('karsilastirilamayan durum onarim TETIKLEMIYOR', () => {
  // Bilmedigimiz bir sey hakkinda "yanlis" demek, calisan bir kurulumu
  // sebepsiz yeniden kurmak olurdu.
  for (const bad of [null, undefined, '', '   ', 'abc', 123, {}]) {
    assert.equal(classifyRuntimeVersion(bad, PINNED), 'unknown')
    assert.equal(classifyRuntimeVersion(PINNED, bad), 'unknown')
    assert.equal(needsRepair('unknown'), false)
  }
})

test('SIFIR doldurulmus damga gercek surum sayilmiyor', () => {
  // Yapi damgasi olmayan derlemeler bunu tasiyor; gercek sanmak her acilista
  // gereksiz onarim tetiklerdi.
  const zeros = '0000000000000000000000000000000000000000'

  assert.equal(isUsableCommit(zeros), false)
  assert.equal(classifyRuntimeVersion(zeros, PINNED), 'unknown')
})

test('cok kisa commit karsilastirilmiyor', () => {
  assert.equal(isUsableCommit('b08e32'), false)
})

test('onarim SESSIZ degil', () => {
  const message = describeRuntimeVersion('stale', '1111111111111111', PINNED)

  assert.match(message, /FARKLI/)
  assert.match(message, /onariliyor/)
  // Iki surum de gorunmeli: kullanici neyin neyle degistigini okuyabilmeli.
  assert.match(message, /1111111111/)
  assert.match(message, /b08e32ec1aae/)
})

test('guncel, ileri ve bilinmeyen durumlar da aciklaniyor', () => {
  assert.match(describeRuntimeVersion('current', PINNED, PINNED), /guncel/)
  assert.match(describeRuntimeVersion('unknown', null, PINNED), /karsilastirilamadi/)
  assert.match(describeRuntimeVersion('ahead', '2222222222222222', PINNED), /ILERIDE/)
})

// ---------------------------------------------------------------------------
// Bağlantı: kontrol GERÇEKTEN hazır-kararının içinde mi
// ---------------------------------------------------------------------------

import { readFileSync } from 'node:fs'
import { join } from 'node:path'

const MAIN = readFileSync(join(__dirname, 'main.ts'), 'utf8')

/** Yalnızca ``ensureRuntime`` gövdesi.
 *
 * Dosyanın tamamında aramak yanlış cevap veriyor: ``getVenvPython(VENV_ROOT)``
 * üç ayrı yerde geçiyor ve ``indexOf`` ilkini buluyor. Sıra sorusu yalnızca bu
 * fonksiyonun içinde anlamlı. */
const ENSURE = (() => {
  const start = MAIN.indexOf('async function ensureRuntime')
  const end = MAIN.indexOf('\nasync function ', start + 1)

  assert.ok(start > 0, 'ensureRuntime bulunamadi')

  return MAIN.slice(start, end > 0 ? end : undefined)
})()

test('surum kontrolu ensureRuntime icinde cagriliyor', () => {
  // Modül var olup çağrılmazsa hiçbir şey değişmez.
  assert.ok(MAIN.includes('classifyRuntimeVersion(runtimeHead, pinnedCommit, runtimeHasPin)'))
  assert.ok(MAIN.includes('needsRepair(versionState)'))
})

test('ata sorusu GERCEKTEN soruluyor', () => {
  // Ucuncu argumani beslemeyen bir cagri, "ileride" halini olusmaz kilar ve
  // her guncellenmis runtime yeniden ``stale`` olurdu.
  assert.ok(MAIN.includes('checkoutContainsCommit(ACTIVE_HERMES_ROOT, pinnedCommit)'))
})

test('basarisiz onarim ACILISLAR ARASINDA da tekrarlanmiyor', () => {
  // Surec ici bayrak yalnizca ozyinelemeyi kesiyor. Kalici damga olmadan
  // kullanici her acilista yukleyicinin tam turunu oder.
  assert.ok(MAIN.includes('runtimeRepairAlreadyAttempted(runtimeHead, pinnedCommit)'))
  assert.ok(MAIN.includes('rememberRuntimeRepairAttempt(runtimeHead, pinnedCommit)'))
  assert.ok(ENSURE.includes('!repairAlreadyTried'))
})

test('kontrol venv kontrolunden ONCE geliyor', () => {
  // Eski bir runtime'in venv'i saglam olabilir; venv testine takilmadan
  // gecer ve "hazir" sayilirdi. Surum sorusu once sorulmali.
  const check = ENSURE.indexOf('classifyRuntimeVersion(runtimeHead, pinnedCommit, runtimeHasPin)')
  const venv = ENSURE.indexOf('const venvPython = getVenvPython(VENV_ROOT)')

  assert.ok(check > 0 && venv > 0)
  assert.ok(check < venv)
})

test('SONSUZ dongu korumasi var', () => {
  // Onarim commit'i duzeltemezse ikinci tur ayni karara varir.
  assert.ok(MAIN.includes('runtimeVersionRepairAttempted'))
  assert.ok(MAIN.includes('!runtimeVersionRepairAttempted'))
})

test('onarim MEVCUT yolu kullaniyor, yeni API uydurmuyor', () => {
  // ``bootstrapRepairRequested`` zaten test edilmis seam: kullanilabilir
  // gorunen runtime'i atlayip yukleyiciyi yeniden kosuyor.
  const block = ENSURE.slice(
    ENSURE.indexOf('needsRepair(versionState) && !runtimeVersionRepairAttempted'),
    ENSURE.indexOf('const venvPython = getVenvPython(VENV_ROOT)')
  )

  assert.ok(block.includes('bootstrapRepairRequested = true'))
})

test('karar SESSIZ degil -- desktop.log a yaziliyor', () => {
  // console.log desktop.log'a DUSMUYOR: olculdu, karar gorunmez kaliyordu.
  assert.ok(ENSURE.includes('rememberLog(`[runtime] ${describeRuntimeVersion('))
})
