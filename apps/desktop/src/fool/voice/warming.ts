/**
 * "Model uyanık mı" göstergesi — saf, DOM'suz, sınanabilir.
 *
 * Neden gerekiyor
 * ---------------
 * Bir seslendirme motoru ilk kullanımda modelini yüklüyor ve bu ÖLÇÜLDÜĞÜ
 * kadar uzun sürüyor:
 *
 *     piper       4,67 sn     kokoro     31,63 sn
 *     styletts2  37,48 sn     kyutai     17,12 sn
 *     chatterbox 37,21 sn     qwen3-tts  40,52 sn
 *
 * O süre boyunca ekranda "Talking" yazıyor ve HİÇBİR ses çıkmıyordu.
 * Kullanıcı için bu "bozuk"tan ayırt edilemez -- nitekim öyle bildirildi:
 * "yine ses gelmedi".
 *
 * Bekleme kaçınılmaz (model diskten VRAM'e yüklenecek), ama GÖRÜNMEZ olması
 * değil. Eşiğin üstünde bekleyen her sentez artık ne beklediğini söylüyor.
 */

/**
 * Bu süreden uzun süren hazırlık "uyanıyor" sayılıyor.
 *
 * 1,2 saniye bilinçli: ısınmış motorlar 0,17-2,49 sn arasında ve onlarda
 * uyarı çıkarmak gürültü olurdu. Soğuk yükleme ise 4,67 sn'den başlıyor --
 * eşik ikisini net ayırıyor.
 */
export const WARMING_AFTER_MS = 1_200

export interface WarmingInput {
  /** Oynatma durumu ``preparing`` mi? */
  preparing: boolean
  /** Hazırlık ne zamandır sürüyor (ms). */
  elapsedMs: number
  /**
   * Bu motor bu oturumda DAHA ÖNCE konuştu mu?
   *
   * Etiketin kendisi "once per session" diyordu ama kod bunu uygulamıyordu:
   * ölçüt yalnızca "hazırlık 1,2 sn'yi geçti mi"ydi. Chatterbox SICAKKEN
   * bile hazırlık o eşiği aşabiliyor (sıcak sentez 0,78 sn + akış kurulumu),
   * yani uyarı HER mesajda çıkıyordu -- kullanıcının bildirdiği "her mesajda
   * sürekli waking chatterbox diyor".
   *
   * Motor bir kez konuştuysa yüklüdür; ikinci kez "yükleniyor" demek yalan.
   */
  spokeBefore?: boolean
}

/** Kullanıcıya "model uyanıyor" denmeli mi? */
export function isWarming(input: WarmingInput): boolean {
  if (input.spokeBefore) {
    return false
  }

  return input.preparing && input.elapsedMs >= WARMING_AFTER_MS
}

/**
 * Gösterilecek satır.
 *
 * Motor adı GEÇİYOR: "yükleniyor" tek başına hangi şeyin yüklendiğini
 * söylemiyor ve kullanıcı yanlış yerde sorun arıyor. Bir de bunun BİR KEZ
 * olduğu söyleniyor -- yoksa her turda bekleyeceğini sanır.
 */
export function warmingLabel(engine: string): string {
  const name = engine.trim() || 'the voice'

  return `Waking ${name} — loading the model, once per session`
}
