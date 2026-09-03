/**
 * Runtime dizininin adı: ``fool-agent`` — ``hermes-agent`` DEĞİL.
 *
 * Neden
 * -----
 * İstenen: "hermes kalıntısı kalmasın, hermes kurulu bile olsa fool ayrı bir
 * uygulama olarak çalışsın."
 *
 * Veri dizini zaten ayrıydı (``%LOCALAPPDATA%\fool`` ile ``...\hermes`` farklı
 * kökler), ama runtime'ın klasörü hâlâ ``hermes-agent`` adını taşıyordu.
 * Kullanıcının gördüğü yer burası::
 *
 *     > where.exe fool
 *     C:\Users\...\AppData\Local\fool\hermes-agent\bin\fool.exe
 *
 * Yani ürün ayrı, ad değil.
 *
 * Neden ``runtime`` değil
 * -----------------------
 * O ad ZATEN KULLANIMDA: ``%LOCALAPPDATA%\fool\runtime`` başka bir şey için
 * var. Çakışan bir isim, göçü sessizce yanlış dizine yapardı.
 *
 * Göç neden yeniden adlandırma
 * ----------------------------
 * Klon gigabaytlarca ve içinde venv var. Kopyalamak diski ikiye katlar ve
 * yarıda kesilirse iki yarım kopya bırakır. Yeniden adlandırma tek işlem:
 * ya olur ya olmaz, arada bir hâl yok.
 *
 * Eski ad OKUNMAYA devam ediyor: göç edemeyen bir kurulum (dosya kilitli,
 * izin yok) çalışmayı sürdürmeli. Ad bir kolaylık, çalışmanın şartı değil.
 *
 * Zone A: upstream bu dosyayı bilmiyor.
 */

/** Yeni ad. Yeni kurulumlar ve başarılı göçler bunu kullanıyor. */
export const RUNTIME_DIR_NAME = 'fool-agent'

/** Yeniden adlandırmadan önceki ad. Sadece OKUNUYOR. */
export const LEGACY_RUNTIME_DIR_NAME = 'hermes-agent'

export interface RuntimeRootChoice {
  /** Kullanılacak dizin adı. */
  name: string
  /** Eski addan yeni ada taşıma denenmeli mi? */
  migrateFrom: null | string
}

/**
 * Hangi dizin kullanılacak, ve göç gerekiyor mu?
 *
 * ``exists`` bir ada bakıp o dizinin var olup olmadığını söyleyen işlev --
 * dosya sistemi buraya girmiyor ki karar sınanabilsin.
 *
 * Kurallar, ölçülen risklere göre:
 *
 *   * Yeni ad varsa o kullanılır. Eski de duruyorsa DOKUNULMAZ: iki dizinin
 *     birleştirilmesi veri kaybı riski taşır, ve kullanıcı eskisini bilerek
 *     bırakmış olabilir.
 *   * Yalnızca eski varsa: göç denenir, ama ad olarak yine ESKİSİ döner.
 *     Çağıran taraf göçü yapıp yeni ada geçiyor; başarısız olursa eskisiyle
 *     çalışmaya devam edebilsin diye karar burada değil orada veriliyor.
 *   * Hiçbiri yoksa yeni ad -- taze kurulum.
 */
export function chooseRuntimeRoot(exists: (name: string) => boolean): RuntimeRootChoice {
  const hasNew = exists(RUNTIME_DIR_NAME)
  const hasLegacy = exists(LEGACY_RUNTIME_DIR_NAME)

  if (hasNew) {
    return { migrateFrom: null, name: RUNTIME_DIR_NAME }
  }

  if (hasLegacy) {
    return { migrateFrom: LEGACY_RUNTIME_DIR_NAME, name: LEGACY_RUNTIME_DIR_NAME }
  }

  return { migrateFrom: null, name: RUNTIME_DIR_NAME }
}

/** Göç sonrası hangi ad geçerli? Başarısızlık eski adı korur. */
export function runtimeRootAfterMigration(choice: RuntimeRootChoice, migrated: boolean): string {
  if (choice.migrateFrom !== null && migrated) {
    return RUNTIME_DIR_NAME
  }

  return choice.name
}

/** Günlüğe yazılacak tek cümle. Sessiz göç, sessiz hata kadar kötü. */
export function describeMigration(choice: RuntimeRootChoice, migrated: boolean): null | string {
  if (choice.migrateFrom === null) {
    return null
  }

  if (migrated) {
    return `runtime dizini ${choice.migrateFrom} -> ${RUNTIME_DIR_NAME} olarak tasindi`
  }

  return (
    `runtime dizini ${choice.migrateFrom} adinda birakildi (tasima basarisiz); ` +
    'calismaya devam ediliyor'
  )
}
