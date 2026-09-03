/**
 * Açılışta konuşmak — ve beklerken susmamak.
 *
 * Neden konuşarak açılıyor
 * ------------------------
 * Sesli bir yüzeyin ilk işi sesli olduğunu KANITLAMAK. Sessiz açılan bir
 * pencerede kullanıcı önce mikrofonu deniyor, sonra çalışıp çalışmadığını
 * merak ediyor. Tek cümle bunu bitiriyor.
 *
 * Isınma anlatımının ÇIKMAZI ve çözümü
 * -------------------------------------
 * "Model yüklenmediyse aşamaları sesli söylesin" isteğinin içinde bir çıkmaz
 * var: aşamayı söylemek için de seslendirme motorunun yüklü olması gerekiyor.
 * Soğuk bir motorla "yükleniyorum" demek mümkün değil.
 *
 * Çözüm sıralamada: İLK cümle ısınmanın kendisi. O cümle söylenene kadar
 * geçen süre zaten modelin yüklenme süresi (ölçüldü: styletts2 soğuk 22,5 sn,
 * kokoro 24,2 sn, piper 4,7 sn). Cümle duyulduğu anda motor SICAK demektir --
 * sonraki her satır yarım saniyenin altında (ölçüldü: styletts2 sıcak
 * 0,52 sn). Yani ilk cümleden sonra aşamalar gerçekten hızlı akıyor.
 *
 * Beklerken ekran susmuyor: aşamalar yazıyla da gösteriliyor, çünkü 22
 * saniyelik sessizlik "bozuldu" gibi görünüyor.
 *
 * Zone A: upstream bu dosyayı bilmiyor.
 */

/** Bir ısınma yüzeyinin durumu (sunucunun ``/api/fool/voice/warm`` cevabı). */
export interface WarmStatus {
  error?: string
  status?: string
}

export interface WarmReply {
  stt?: WarmStatus
  tts?: WarmStatus
}

/**
 * Açılış selamı.
 *
 * Tek cümle ve soru DEĞİL: bir sohbeti soruyla açmak onu görevleştiriyor.
 * Friend/Jarvis kipleri kaldırıldığı için kipe göre ayrı selam da yok.
 */
export function greeting(): string {
  return 'Ready when you are.'
}

/** Uyanma cümlesi: motor SOĞUKKEN söylenen ilk şey. */
export const WAKING_LINE = 'Waking up. One moment.'

/** Bir yüzey hazır mı? */
export function isWarm(status: undefined | WarmStatus): boolean {
  return (status?.status ?? '') === 'warm'
}

/** Bu yüzey ısınmayı hiç başaramadı mı? */
export function hasFailed(status: undefined | WarmStatus): boolean {
  return (status?.status ?? '') === 'failed'
}

/**
 * Her şey hazır mı?
 *
 * Başarısız da "beklemeyi bitir" sayılıyor: kilitli kalmış bir açılış
 * ekranında sonsuza kadar beklemek, geç konuşmaktan kötü. İlk gerçek cümle
 * modeli zaten kendisi yükler.
 */
export function warmupSettled(reply: WarmReply): boolean {
  const done = (entry: undefined | WarmStatus) => isWarm(entry) || hasFailed(entry)

  return done(reply.tts) && done(reply.stt)
}

/** Açılışta motor soğuk mu -- yani uyanma cümlesi gerekiyor mu? */
export function needsWaking(reply: WarmReply): boolean {
  return !isWarm(reply.tts)
}

/**
 * Aşama tamamlandığında söylenecek satır ("" = söylenecek bir şey yok).
 *
 * Yalnızca SOĞUKTAN sıcağa geçişte konuşuyor. Zaten sıcak olan bir yüzey için
 * "hazır" demek, kullanıcıya hiçbir şey söylemeyen bir cümle olurdu.
 */
export function stageLine(surface: 'stt' | 'tts', before: WarmReply, after: WarmReply): string {
  const rose = !isWarm(before[surface]) && isWarm(after[surface])

  if (!rose) {
    return ''
  }

  return surface === 'tts' ? 'Voice ready.' : 'Hearing ready.'
}

/** Ekranda gösterilen ısınma satırı ("" = gösterilecek bir şey yok). */
export function warmupCaption(reply: WarmReply): string {
  if (warmupSettled(reply)) {
    return ''
  }

  const pending: string[] = []

  if (!isWarm(reply.tts)) {
    pending.push('voice')
  }

  if (!isWarm(reply.stt)) {
    pending.push('hearing')
  }

  // Ölçülen süre kullanıcıya SÖYLENİYOR: 22 saniyelik sessiz bir bekleme
  // "bozuldu" gibi görünüyor, "yaklaşık yarım dakika" görünmüyor.
  return `Loading ${pending.join(' and ')} — first time takes about half a minute`
}
