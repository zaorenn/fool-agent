/**
 * Paketlenen sürüm KENDİ kurulum betiğini taşımalı.
 *
 * Ölçülen hata
 * ------------
 * Paketlenmiş bir yapıda ``install.ps1`` GitHub'dan, install-stamp'teki
 * commit'ten indiriliyordu. Sonucu: kurulum betiğindeki düzeltmeler depoda
 * yazılmış olmasına rağmen ÇALIŞMADI, çünkü koşan dosya ağdan gelen eski
 * sürümdü::
 *
 *     [bootstrap] fetching install.ps1 for b08e32ec1aae from GitHub
 *     [OK] Added to user PATH: ...\Temp\hermes-desktop-fresh-install-...\bin
 *     [OK] Set FOOL_HOME=...\Temp\hermes-desktop-fresh-install-...
 *
 * Yani test sandbox'ı kullanıcının KALICI ortamını yeniden zehirledi --
 * düzeltmesi depoda dururken. Kullanıcının daha önce yaşadığı hasarın aynısı.
 *
 * İki ayrı sorun aynı köke bağlıydı:
 *   1. Bir sürümün davranışı, o sürümün içindeki koda değil, ağdaki bir
 *      dosyaya bağlıydı.
 *   2. İnternet yoksa ya da GitHub erişilmezse kurulum hiç başlamıyordu.
 *
 * Zone A: upstream bu dosyayı bilmiyor.
 */

import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

import { test } from 'vitest'

const RUNNER = readFileSync(join(__dirname, 'bootstrap-runner.ts'), 'utf8')
const PKG = JSON.parse(readFileSync(join(__dirname, '..', 'package.json'), 'utf8'))

test('kurulum betikleri PAKETE giriyor', () => {
  const targets = PKG.build.extraResources.map((e: { to: string }) => e.to)

  assert.ok(targets.includes('install.ps1'), 'install.ps1 extraResources icinde degil')
  assert.ok(targets.includes('install.sh'), 'install.sh extraResources icinde degil')
})

test('paketlenen betik DEPODAN aliniyor -- surumle es', () => {
  // Kaynak ağaçtan kopyalanıyor, yani derlenen sürümle tanım gereği aynı.
  const entries = PKG.build.extraResources.filter((e: { to: string }) =>
    e.to === 'install.ps1' || e.to === 'install.sh'
  )

  for (const entry of entries) {
    assert.ok(
      entry.from.startsWith('../../scripts/'),
      `${entry.to} depo scripts/ dizininden gelmeli, geldigi yer: ${entry.from}`
    )
  }
})

/** Yalnızca ``resolveInstallScript`` gövdesi.
 *
 * Dosyanın tamamında aramak yanlış cevap veriyor: ``indexOf`` bir yardımcının
 * TANIMINI bulup çağrı sırasını ölçüyormuş gibi yapıyor. Sıra sorusu yalnızca
 * çözümleyicinin içinde anlamlı. */
const RESOLVER = (() => {
  const start = RUNNER.indexOf('async function resolveInstallScript')
  const end = RUNNER.indexOf('\nasync function ', start + 1)

  assert.ok(start > 0, 'resolveInstallScript bulunamadi')

  return RUNNER.slice(start, end > 0 ? end : undefined)
})()

test('gomulu betik AGDAN once deneniyor', () => {
  const bundledAt = RESOLVER.indexOf('resolveBundledInstallScript()')
  const downloadAt = RESOLVER.indexOf('installRefForStamp(installStamp)')

  assert.ok(bundledAt > 0, 'gomulu betik cozumleyicisi cagrilmiyor')
  assert.ok(downloadAt > 0, 'indirme yolu bulunamadi')
  assert.ok(bundledAt < downloadAt, 'indirme gomulu betikten ONCE deneniyor')
})

test('YEREL klon hala en once -- push etmeden iterasyon bozulmadi', () => {
  const localAt = RESOLVER.indexOf('resolveLocalInstallScript(sourceRepoRoot)')
  const bundledAt = RESOLVER.indexOf('resolveBundledInstallScript()')

  assert.ok(localAt > 0)
  assert.ok(localAt < bundledAt)
})

test('indirme KALDIRILMADI -- yalnizca geri dusus', () => {
  // Kaynak ağacı olmayan ve resourcesPath taşımayan bir ortam (bazı test
  // koşumları) hâlâ çalışabilmeli.
  assert.ok(RUNNER.includes('downloadInstallScript'))
  assert.ok(RUNNER.includes('Geri dusus'))
})
