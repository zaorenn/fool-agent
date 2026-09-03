/**
 * Yeniden adlandırmadan ÖNCEKİ işaret dosyası hâlâ okunmalı.
 *
 * Ölçülen hasar (kullanıcının makinesi)
 * -------------------------------------
 * İşaret 2026-08-18'de ``.hermes-bootstrap-complete`` olarak yazılmıştı. Ürün
 * ``fool`` adını alınca YAZAN taraf ``.fool-bootstrap-complete``a geçti, ama
 * OKUYAN taraf eski dosyaları hiç görmedi.
 *
 * Sonuç: geçerli, doğru ``schemaVersion``lı bir işaret diskte dururken
 * "işaret yok" sayıldı. ``hermes-agent/bin`` de bulunmayınca kurulum "yarım"
 * diye sınıflandı ve uygulama HER açılışta ilk kurulum akışına girdi:
 *
 *     [bootstrap] ... is a half-finished install (no launcher in bin/, no
 *     bootstrap marker); running first-run setup instead of launching it.
 *
 * Kullanıcıya görünen: zaten kurulu olan ses motorlarının baştan indirilmeye
 * başlaması. Sessiz sınıf -- hata yok, yalnızca sonsuz yeniden kurulum.
 *
 * Zone A: upstream bu dosyayı bilmiyor.
 */

import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

import { test } from 'vitest'

const MAIN = readFileSync(join(__dirname, 'main.ts'), 'utf8')

test('eski isaret adi KODDA taniniyor', () => {
  assert.ok(MAIN.includes('.hermes-bootstrap-complete'))
  assert.ok(MAIN.includes('LEGACY_BOOTSTRAP_COMPLETE_MARKER'))
})

test('okuyucu ONCE yeni adi, sonra eskisini deniyor', () => {
  // Sıra önemli: eski dosya önce okunsaydı, yeniden yazılan güncel işaret
  // eski bir dosya tarafından gölgelenirdi.
  const reader = MAIN.slice(
    MAIN.indexOf('function readBootstrapMarker()'),
    MAIN.indexOf('function readBootstrapMarker()') + 400
  )

  const newIdx = reader.indexOf('BOOTSTRAP_COMPLETE_MARKER')
  const legacyIdx = reader.indexOf('LEGACY_BOOTSTRAP_COMPLETE_MARKER')

  assert.ok(newIdx >= 0 && legacyIdx >= 0)
  assert.ok(newIdx < legacyIdx, 'yeni ad once okunmali')
})

test('YAZAN taraf yalnizca YENI adi kullaniyor', () => {
  // Eski ada geri yazmak, adlandırmayı kalıcı olarak ikiye bölerdi.
  const writer = MAIN.slice(MAIN.indexOf('function writeBootstrapMarker'))
  const firstThousand = writer.slice(0, 1000)

  assert.ok(!firstThousand.includes('LEGACY_BOOTSTRAP_COMPLETE_MARKER'))
})
