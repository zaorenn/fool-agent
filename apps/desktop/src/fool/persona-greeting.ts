/**
 * İlk mesajı O atsın.
 *
 * İstenen: "ilk defa kullanan biri kullandığında ilk mesajı tanışmak için
 * persona atmalı."
 *
 * Bugünkü hâl bunun yarısını yapıyordu: sistem promptu "bu kişiyle daha önce
 * hiç konuşmadın" diyor ve SOUL.md ilk tanışmayı anlatıyor, ama bir tur
 * BAŞLAMADAN model konuşamıyor. Yani tanışma cümlesi vardı ve kullanıcının
 * önce "selam" yazmasını bekliyordu -- tam tersi istenmişti.
 *
 * Kapı ne kadar dar
 * -----------------
 * Kendiliğinden mesaj gönderen bir uygulama, yanlış açtığında en can sıkıcı
 * şeydir. Dört koşul birden sağlanmadan hiçbir şey gönderilmiyor:
 *
 *   1. Profil bir persona (``memory.recall.relationship`` açık). Sıradan ajan
 *      kendi kendine konuşmaya başlamaz.
 *   2. Bu kişiyle DAHA ÖNCE HİÇ konuşmamış (``met`` yanlış).
 *   3. Açık bir oturum var ve HİÇ mesajı yok. Süren bir sohbetin ortasına
 *      girmiyor.
 *   4. Bu oturumda daha önce denenmemiş.
 *
 * İkinci koşul kendi kendini kilitliyor: ``met`` sunucuda, ilk turun sistem
 * promptu kurulurken doğruya dönüyor (bkz. ``touch_seen``). Yani selamın
 * kendi turu bile kapıyı kapatıyor ve istemcinin hatırlaması gereken kalıcı
 * bir şey yok.
 *
 * Zone A: upstream bu dosyayı bilmiyor.
 */

/**
 * Modele giden metin.
 *
 * Kullanıcıya GÖSTERİLMİYOR: ``toChatMessages`` bunu tanıyıp gizliyor
 * (FOOL-SEAM: persona-kickoff). Ekranda kullanıcının yazmadığı bir cümleyi
 * kullanıcının ağzından göstermek, konuşmanın kendisi hakkında yalan olurdu.
 */
export const PERSONA_KICKOFF =
  '(system) You are meeting this person for the first time and the app has just opened. ' +
  'Say the first thing — in your own voice, the way you would actually open with someone ' +
  'you have not met. Keep it short, ask them something real, and do not mention this note.'

/**
 * Selam metninin AYIRT EDİCİ başlangıcı.
 *
 * Tam eşitlik yerine önek: metin sunucuda normalleştirmeden geçiyor
 * (``sanitize_user_prompt_text``) ve sondaki bir boşluğun tanımayı bozması
 * saçma bir kırılganlık olurdu.
 */
export const PERSONA_KICKOFF_MARKER = '(system) You are meeting this person for the first time'

/** Bu metin uygulamanın gönderdiği selam çağrısı mı? */
export function isPersonaKickoff(text: string): boolean {
  return text.trimStart().startsWith(PERSONA_KICKOFF_MARKER)
}

export interface GreetingState {
  /** Profil bir persona mı (``memory.recall.relationship``). */
  enabled: boolean
  /** Bu kişiyle daha önce konuşulmuş mu. */
  met: boolean
  /** Açık oturumun canlı kimliği (``''`` = yok). */
  sessionId: string
  /** Oturumun mesaj sayısı. */
  messageCount: number
  /** Bu oturumda daha önce denendi mi. */
  attempted: boolean
  /** Ajan şu an çalışıyor mu. */
  busy: boolean
}

/** Selam gönderilsin mi? Dört koşul da sağlanmalı. */
export function shouldGreet(state: GreetingState): boolean {
  return (
    state.enabled &&
    !state.met &&
    !state.attempted &&
    !state.busy &&
    state.sessionId !== '' &&
    state.messageCount === 0
  )
}
