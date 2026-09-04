/**
 * Runtime dizininde ``hermes`` kalıntısı kalmamalı — ama göç veri kaybetmemeli.
 *
 * İstenen: "hermes kalıntısı kalmasın, hermes kurulu bile olsa fool ayrı bir
 * uygulama olarak çalışsın."
 *
 * Kullanıcının kalıntıyı gördüğü yer::
 *
 *     > where.exe fool
 *     C:\Users\...\AppData\Local\fool\hermes-agent\bin\fool.exe
 *
 * Buradaki testler göçün iki ucunu birden tutuyor: yeni ada geçiş GERÇEKTEN
 * oluyor, ve göç edemeyen bir kurulum çalışmayı SÜRDÜRÜYOR.
 *
 * Zone A: upstream bu dosyayı bilmiyor.
 */

import assert from 'node:assert/strict'

import { test } from 'vitest'

import {
  chooseRuntimeRoot,
  describeMigration,
  LEGACY_RUNTIME_DIR_NAME,
  RUNTIME_DIR_NAME,
  runtimeRootAfterMigration
} from './runtime-root'

const only =
  (...present: string[]) =>
  (name: string) =>
    present.includes(name)

test('yeni ad hermes ICERMIYOR', () => {
  assert.ok(!RUNTIME_DIR_NAME.includes('hermes'))
  assert.equal(RUNTIME_DIR_NAME, 'fool-agent')
})

test('CAKISAN bir ad secilmedi', () => {
  // ``%LOCALAPPDATA%\fool\runtime`` baska bir sey icin ZATEN kullanimda;
  // o adi secmek gocu sessizce yanlis dizine yapardi.
  assert.notEqual(RUNTIME_DIR_NAME, 'runtime')
})

test('taze kurulum YENI adi kullaniyor', () => {
  const choice = chooseRuntimeRoot(only())

  assert.equal(choice.name, RUNTIME_DIR_NAME)
  assert.equal(choice.migrateFrom, null)
})

test('yalnizca ESKI varsa goc deneniyor', () => {
  const choice = chooseRuntimeRoot(only(LEGACY_RUNTIME_DIR_NAME))

  assert.equal(choice.migrateFrom, LEGACY_RUNTIME_DIR_NAME)
  // Ad olarak ESKISI donuyor: goc basarisiz olursa cagiran taraf onunla
  // calismaya devam edebilsin.
  assert.equal(choice.name, LEGACY_RUNTIME_DIR_NAME)
})

test('IKISI de varsa eskisine DOKUNULMUYOR', () => {
  // Iki dizini birlestirmek veri kaybi riski; kullanici eskisini bilerek
  // birakmis olabilir.
  const choice = chooseRuntimeRoot(only(RUNTIME_DIR_NAME, LEGACY_RUNTIME_DIR_NAME))

  assert.equal(choice.name, RUNTIME_DIR_NAME)
  assert.equal(choice.migrateFrom, null)
})

test('BASARILI goc yeni ada geciyor', () => {
  const choice = chooseRuntimeRoot(only(LEGACY_RUNTIME_DIR_NAME))

  assert.equal(runtimeRootAfterMigration(choice, true), RUNTIME_DIR_NAME)
})

test('BASARISIZ goc eski adla CALISMAYA devam ediyor', () => {
  // Ad bir kolaylik, calismanin sarti degil. Kilitli bir dosya yuzunden
  // uygulamanin acilmamasi kabul edilemez.
  const choice = chooseRuntimeRoot(only(LEGACY_RUNTIME_DIR_NAME))

  assert.equal(runtimeRootAfterMigration(choice, false), LEGACY_RUNTIME_DIR_NAME)
})

test('goc SESSIZ degil', () => {
  const choice = chooseRuntimeRoot(only(LEGACY_RUNTIME_DIR_NAME))

  assert.match(String(describeMigration(choice, true)), /tasindi/)
  assert.match(String(describeMigration(choice, false)), /basarisiz/)
  // Goc yoksa soylenecek bir sey de yok.
  assert.equal(describeMigration(chooseRuntimeRoot(only()), false), null)
})

// ---------------------------------------------------------------------------
// Bağlantı: göç GERÇEKTEN yapılıyor ve venv doğrulanıyor
// ---------------------------------------------------------------------------

import { readFileSync } from 'node:fs'
import { join } from 'node:path'

const MAIN = readFileSync(join(__dirname, 'main.ts'), 'utf8')

test('runtime koku artik SABIT bir isim degil', () => {
  // Eski hali: path.join(FOOL_HOME, 'hermes-agent')
  assert.ok(MAIN.includes('path.join(FOOL_HOME, RUNTIME_ROOT_NAME)'))
  assert.ok(!MAIN.includes("path.join(FOOL_HOME, 'hermes-agent')"))
})

test('goc yeniden ADLANDIRMA -- kopyalama degil', () => {
  // Klon gigabaytlarca; kopyalamak diski ikiye katlar ve yarida kesilirse
  // iki yarim kopya birakir.
  assert.ok(MAIN.includes('fs.renameSync('))
})

test('goc sonrasi venv DOGRULANIYOR', () => {
  // Windows'ta venv konsol betikleri mutlak yol gomuyor; ust dizin adi
  // degisince dosya yerinde durur ama calismaz. Yalnizca fileExists bakmak
  // bunu kacirirdi.
  assert.ok(MAIN.includes('canImportFoolCli(venvPython)'))
})

test('kirik venv ONARIM tetikliyor', () => {
  // Sabit uzunlukta bir pencereye bakmak KIRILGAN: bir aciklama satiri
  // eklenince test sebepsiz duser. Blogun gercek sinirina bakiliyor.
  const start = MAIN.indexOf('HER ACILISTA sinaniyor')
  const end = MAIN.indexOf('backend.command = getVenvPython(VENV_ROOT)', start)

  assert.ok(start > 0 && end > start)
  assert.ok(MAIN.slice(start, end).includes('bootstrapRepairRequested = true'))
})

test('goc sonrasi LAUNCHER da sinaniyor', () => {
  // Ölçüldü: venv python'ı geçti ama terminal komutu kırıldı --
  //
  //     > fool --version
  //     error: uv trampoline failed to canonicalize script path
  //
  // ``bin\fool.exe`` bir uv trampoline'i ve MUTLAK yol gömüyor; venv python'ı
  // ise kendi konumuna göre çözülüyor. Yalnızca python'ı sınamak masaüstünü
  // çalışır, kullanıcının terminalini kırık bırakıyordu.
  assert.ok(MAIN.includes('verifyFoolCli(migratedLauncher)'))
  assert.ok(MAIN.includes('launcherOk'))

  // Kontrol HER acilista kosuyor -- yalnizca gocun yapildigi acilista degil.
  // Olculdu: goc bir onceki acilista yapildi, launcher o sirada kirildi, ve
  // bir sonraki acilista kapi kapali oldugu icin kimse bakmadi.
  assert.ok(MAIN.includes('if (!runtimeSelfCheckDone) {'))
})

test('dogrulama surum onarimindan AYRI bir bayrakta', () => {
  // Ikisi ayni bayragi paylasirken surum onariminin tetiklendigi acilista
  // launcher HIC sinanmiyordu -- oysa tam o acilis en riskli olan: yukleyici
  // az once klonu ve venv'i kimildatti.
  assert.ok(MAIN.includes('let runtimeSelfCheckDone = false'))
  assert.ok(MAIN.includes('let runtimeVersionRepairAttempted = false'))
})
