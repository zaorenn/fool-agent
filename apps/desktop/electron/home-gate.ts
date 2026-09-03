/**
 * Yapılandırılmış bir ev KÖR KÖRÜNE kabul edilemez — ama kolayca da
 * reddedilemez.
 *
 * Ölçülen hasar
 * -------------
 * Masaüstünün kendi ``test:desktop:fresh`` sınavı ``install.ps1``i ``%TEMP%``
 * altındaki bir sandbox eviyle çalıştırdı ve o geçici yol KULLANICI kapsamlı
 * ``FOOL_HOME``a yazıldı. Sınav bitti, klasör silindi, değer kaldı. Uygulama o
 * günden sonra her açılışta var olmayan bir dizine girdi::
 *
 *     oturum geçmişi yok    profil yok    ses klonu yok
 *     "hiçbir TTS motoru kurulu değil"    modeller baştan iniyor
 *
 * Kullanıcının bildirdiği: "girlfriend gitmiş, ses klonlarım gitmiş, bütün
 * sohbetlerim gitmiş." Hiçbiri silinmemişti -- ama onun için farkı yoktu.
 *
 * Yazma tarafı artık korunuyor (``install.ps1``), ama BOZULMUŞ makineler
 * dışarıda duruyor ve yeni sürümü kurmak onları kendiliğinden iyileştirmeli.
 * Bu yüzden okuma tarafı da soruyor: bu ev GERÇEK olabilir mi?
 *
 * Neden ayrı bir dosya
 * --------------------
 * Bu, uygulamadaki en pahalı yanlış cevabın verildiği yer: yanlış tarafa
 * düşmek kullanıcıya bütün verisini kaybetmiş gibi görünüyor. Karar
 * ``main.ts`` içinde dosya sistemine gömülüyken yalnızca KAYNAK OKUYAN
 * testlerle korunabiliyordu -- yani "şu satır dosyada duruyor mu" ile. Burada
 * dosya sistemi enjekte ediliyor ve kararın kendisi sınanabiliyor.
 *
 * Zone A: upstream bu dosyayı bilmiyor.
 */

export interface HomeGateDeps {
  /** Bir dizin var mı? */
  directoryExists: (path: string) => boolean
  /** İşletim sisteminin geçici dizini (çözülemiyorsa ``null``). */
  tempDir: () => null | string
  /** Yapılandırma olmasaydı kullanılacak ev. */
  defaultHome: () => string
  /** Yolu mutlaklaştır. */
  resolve: (path: string) => string
  /** Yolun birim kökü (``C:\`` / ``/``); yoksa boş dize. */
  rootOf: (path: string) => string
  /** Platform yol ayracı. */
  sep: string
}

/**
 * Bu ev atılmış görünüyor mu? Görünmüyorsa ``null``, görünüyorsa SEBEP.
 *
 * Sebep dizesi taşınıyor çünkü sessizce düzeltmek, sessizce bozmak kadar kötü:
 * kullanıcı "verilerim neden geri geldi" sorusunu da cevaplayabilmeli.
 */
export function looksLikeDiscardedHome(home: string, deps: HomeGateDeps): null | string {
  let resolved: string

  try {
    resolved = deps.resolve(home)
  } catch {
    return 'cozulemeyen yol'
  }

  // 1. ``%TEMP%`` altında -- geçici bir dizin kalıcı bir ev OLAMAZ. Var olsa
  //    bile: işletim sistemi onu istediği an siler.
  try {
    const temp = deps.tempDir()

    if (temp) {
      const resolvedTemp = deps.resolve(temp)
      const lower = resolved.toLowerCase()
      const lowerTemp = resolvedTemp.toLowerCase()

      if (lower === lowerTemp || lower.startsWith(lowerTemp + deps.sep)) {
        return `gecici dizin altinda (${resolvedTemp})`
      }
    }
  } catch {
    // Çözülemeyen bir temp için IDDIA YOK: yanlış tarafa düşmek, gerçek bir
    // evi reddetmek olurdu.
  }

  // 2. Yok VE varsayılan ev var -- yapılandırma bir hayaleti gösteriyor, oysa
  //    gerçek veri duruyor.
  if (deps.directoryExists(resolved) || !deps.directoryExists(deps.defaultHome())) {
    return null
  }

  // ULAŞILAMAYAN bir ev ATILMIŞ bir ev DEĞİL.
  //
  // Kural tek başına çok genişti: evi çıkarılabilir ya da ağ sürücüsünde olan
  // bir kullanıcı (örneğin ``F:\The Fool\data``) diski takmadan uygulamayı
  // açtığında kapı evi reddedip sessizce varsayılana düşerdi. Hiçbir şey
  // SİLİNMEZ -- ama kullanıcının gördüğü şey tam olarak şikâyet ettiği şey
  // olurdu: boş bir uygulama. Daha kötüsü, oradan sonra yeni oturumlar YANLIŞ
  // eve yazılır ve durum ikiye bölünür.
  //
  // Ayrım: birim (sürücü/kök) ERİŞİLEBİLİRSE ve dizin yoksa, o yol gerçekten
  // atılmıştır. Birim erişilemiyorsa yol GEÇİCİ olarak yok demektir ve
  // hakkında hiçbir iddiada bulunulmuyor -- yapılandırılan ev korunuyor ve
  // arka uç gürültüyle başarısız olur. Sessizce başka bir yere bakmaktan iyi.
  if (!volumeIsAvailable(resolved, deps)) {
    return null
  }

  return 'dizin yok, varsayilan ev ise duruyor'
}

/** Bu yolun birimi (sürücü kökü / bağlı nokta) şu an erişilebilir mi? */
export function volumeIsAvailable(resolved: string, deps: HomeGateDeps): boolean {
  try {
    const root = deps.rootOf(resolved)

    // Kök çözülemiyorsa iddia YOK: bilmediğimiz bir şey için "atılmış" demek,
    // gerçek bir evi reddetmek olurdu.
    return root ? deps.directoryExists(root) : true
  } catch {
    return true
  }
}
