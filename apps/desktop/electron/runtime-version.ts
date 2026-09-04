/**
 * Çalışan runtime, KURULU uygulamayla aynı sürümde mi?
 *
 * Ölçülen hata
 * ------------
 * Kullanıcı yeni sürümü ikinci bir makineye kurdu. Kurulum tamamlandı,
 * ``fool.exe`` yerindeydi, ``FOOL_HOME`` doğruydu -- ve uygulama yine de
 * "background stopped" dedi, terminalde ``fool`` yazınca "Hermes Agent"
 * açıldı. Yani yeni installer eski bir runtime'ın üstüne kuruldu ve onu
 * güncellemedi.
 *
 * Sebep: ``ensureRuntime`` üç şey soruyordu --
 *
 *   1. kaynak dosyalar yerinde mi (``isFoolSourceRoot``)
 *   2. Git Bash var mı
 *   3. venv var mı
 *
 * Üçü de YILLAR ÖNCESİNE ait bir klonda geçer. Sürüm hiç sorulmuyordu, yani
 * "hazır" kararı kodun güncelliği hakkında hiçbir şey söylemiyordu.
 *
 * Sonucu iki kat kötü: hata sessiz. Kullanıcı yeni sürümü kurduğunu biliyor,
 * uygulama "hazır" diyor, ama koşan kod eski. Belirti (durmuş backend, yanlış
 * marka) sebebi hiç göstermiyor.
 *
 * Bu dosya sürümü KARŞILAŞTIRILABİLİR yapıyor. Karar saf: iki commit ve bir
 * cevap. Onarımı çağıran taraf yapıyor.
 *
 * Zone A: upstream bu dosyayı bilmiyor.
 */

export type RuntimeVersionState =
  /**
   * Runtime uygulamanın pin'inden İLERİDE: geçmişi o commit'i zaten içeriyor.
   * Onarım YOK -- aşağıdaki ``needsRepair`` notuna bak.
   */
  | 'ahead'
  /** Runtime uygulamanın sabitlediği commit'te -- yapacak bir şey yok. */
  | 'current'
  /** Runtime BAŞKA bir commit'te: onarılmalı. */
  | 'stale'
  /** Karşılaştırılamıyor (damga yok, git yok) -- iddia edilmiyor. */
  | 'unknown'

/** Bir commit kimliği anlamlı mı? Kısa/boş/sıfır değerler karşılaştırılamaz. */
export function isUsableCommit(value: unknown): value is string {
  if (typeof value !== 'string') {
    return false
  }

  const trimmed = value.trim()

  if (trimmed.length < 7) {
    return false
  }

  // Yapı damgası olmayan derlemeler sıfır doldurulmuş bir commit taşıyor;
  // onu gerçek bir sürüm sanmak her açılışta gereksiz onarım tetiklerdi.
  return !/^0+$/.test(trimmed)
}

/**
 * Runtime'ın commit'i uygulamanın sabitlediğiyle aynı mı?
 *
 * Karşılaştırma ÖNEK duyarlı: git kısa ve uzun biçimi birlikte kullanıyor
 * (``b08e32ec1aae`` ile ``b08e32ec1aae0f46...`` aynı commit). Uzunluk farkını
 * eşitsizlik saymak, güncel bir kurulumu sonsuz onarım döngüsüne sokardı.
 */
export function classifyRuntimeVersion(
  runtimeCommit: unknown,
  appPinnedCommit: unknown,
  runtimeContainsPin: boolean | null = null
): RuntimeVersionState {
  if (!isUsableCommit(runtimeCommit) || !isUsableCommit(appPinnedCommit)) {
    return 'unknown'
  }

  const runtime = runtimeCommit.trim().toLowerCase()
  const pinned = appPinnedCommit.trim().toLowerCase()

  if (runtime.startsWith(pinned) || pinned.startsWith(runtime)) {
    return 'current'
  }

  // FARKLI ile ESKI ayni sey DEGIL.
  //
  // Ilk yazim her farki ``stale`` sayiyordu ve olculen sonucu su olurdu:
  // runtime uygulamadan ILERIDE oldugu anda (kullanici ``fool update``
  // calistirdi, ya da dal uygulamanin derlendigi commit'ten sonra ilerledi)
  // her acilista onarim tetikleniyor. Onarim ise mevcut bir klonu pin'e
  // GERI CEKMIYOR -- bilerek: eski bir paket, guncel bir kurulumu geriye
  // dusurmemeli. Yani karar her seferinde ayni kaliyor ve kullanici HER
  // ACILISTA yukleyicinin tam turunu odemeye devam ediyor.
  //
  // Dogru soru "ayni commit mi" degil, "runtime uygulamanin kodunu ICERIYOR
  // mu": ``git merge-base --is-ancestor <pin> HEAD``. Iceriyorsa runtime
  // yeni ya da esit -- onaracak bir sey yok.
  if (runtimeContainsPin === true) {
    return 'ahead'
  }

  return 'stale'
}

/**
 * Bu durum onarım gerektiriyor mu?
 *
 * ``unknown`` onarım TETİKLEMİYOR: karşılaştıramadığımız bir şey hakkında
 * "yanlış" demek, çalışan bir kurulumu sebepsiz yeniden kurmak olurdu. Kapının
 * yanlış tarafa düşmesinin bedeli asimetrik -- gereksiz onarım kullanıcının
 * dakikalarını ve bant genişliğini yakar.
 *
 * ``ahead`` de tetiklemiyor: runtime uygulamanın pin'ini zaten içeriyor, yani
 * eski olan runtime değil PAKET. Onarım burada bir şey düzeltmez, yalnızca
 * yükleyiciyi her açılışta yeniden koşturur.
 */
export function needsRepair(state: RuntimeVersionState): boolean {
  return state === 'stale'
}

/** Günlüğe yazılacak tek cümle -- sessiz onarım da sessiz hata kadar kötü. */
export function describeRuntimeVersion(
  state: RuntimeVersionState,
  runtimeCommit: unknown,
  appPinnedCommit: unknown
): string {
  const short = (value: unknown) => (isUsableCommit(value) ? value.trim().slice(0, 12) : 'bilinmiyor')

  if (state === 'stale') {
    return (
      `runtime ${short(runtimeCommit)} uygulamanin surumunden (${short(appPinnedCommit)}) ` + 'FARKLI -- onariliyor'
    )
  }

  if (state === 'current') {
    return `runtime ${short(appPinnedCommit)} ile guncel`
  }

  if (state === 'ahead') {
    return (
      `runtime ${short(runtimeCommit)} uygulamanin pin'ini (${short(appPinnedCommit)}) ` +
      'zaten iceriyor -- ILERIDE, onarim gerekmiyor'
    )
  }

  return 'runtime surumu karsilastirilamadi; onarim tetiklenmedi'
}
