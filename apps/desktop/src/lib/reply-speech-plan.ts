/**
 * Yazılı sohbette cevabı CÜMLE CÜMLE okumanın karar tablosu.
 *
 * Ölçülen hata
 * ------------
 * Otomatik sesli okuma yalnızca TAMAMLANMIŞ cevabı okuyordu::
 *
 *     if (!reply || reply.pending) return
 *
 * Yani model 30 saniye yazıyor, ses ancak bittikten sonra başlıyor.
 * Kullanıcının isteği bunun tersiydi: "uzun cevaplarda bile ilk cümle biter
 * bitmez cümle cümle sesli okumasını istiyorum ki daha hızlı olsun."
 *
 * Akış yolu (``startSpeechStream``) zaten vardı ama yalnızca sesli sohbete ve
 * çentiğe bağlıydı; klavyeden yazan kullanıcı ona hiç ulaşamıyordu.
 *
 * Neden AYRI bir dosya
 * --------------------
 * Karar üç durumun kesişimi: hangi cevap, ne kadarı gönderildi, oynatma boş
 * mu. Bunu kancanın içinde bırakmak, sınamak için mikrofon/ağ geçidi/depo
 * ayağa kaldırmak demekti -- ve bu kod tabanında tam olarak o yüzden gözden
 * kaçan hatalar oldu (bkz. ``fool/voice/voice-choice.ts``).
 *
 * Zone A: upstream bu dosyayı bilmiyor.
 */

/** Şu an ekranda büyüyen cevap. */
export interface ReplySnapshot {
  id: string
  /** Hâlâ akıyor mu? */
  pending: boolean
  text: string
}

/** Açık akış oturumunun defteri. */
export interface LiveSpeech {
  id: string
  /** Bu oturuma KAÇ karakter gönderildi. */
  sent: number
}

export interface PlanInput {
  /** Bu cevabı başka bir yüzey üstlendi -- bir daha talep etme. */
  declined: boolean
  live: LiveSpeech | null
  /** Oynatma boşta mı? Yeni bir oturum ancak boştayken açılıyor. */
  playbackIdle: boolean
  reply: null | ReplySnapshot
}

export type SpeechAction =
  /** Hiçbir şey yapma. */
  | { kind: 'wait' }
  /** Önceki oturumu kapat (yeni cevap geldi ya da cevap kayboldu). */
  | { kind: 'retire' }
  /** Bu kimlik için akış oturumu aç. */
  | { kind: 'open'; id: string }
  /** Bu metni gönder ve sayacı ilerlet. */
  | { kind: 'append'; sent: number; text: string }
  /** Metin bitti: oturumu kapat ve okundu olarak işaretle. */
  | { kind: 'finish' }

/**
 * Bir sonraki adım.
 *
 * Kurallar tek tek küçük ama birlikte bütün hatayı kapsıyor:
 *
 *   - Cevap DEĞİŞTİYSE önce eski oturum kapanır. Kapatmadan yenisini açmak
 *     iki sesin üst üste binmesi olurdu.
 *   - Oturum ancak oynatma BOŞTAYKEN açılır. Bu kural eskiden de vardı ve
 *     korunuyor: bir önceki cevap hâlâ konuşurken yenisine başlamak, ikisini
 *     birbirine karıştırmak demek.
 *   - Açılış geciktiyse hiçbir şey KAYBOLMUYOR: ``sent`` sıfırdan başlıyor ve
 *     ilk ``append`` o ana kadar birikmiş metnin TAMAMINI taşıyor.
 *   - ``finish`` yalnızca metnin tamamı gönderildikten sonra. Ters sırada
 *     yapmak son cümleyi kesmekti.
 */
export function planReplySpeech({ declined, live, playbackIdle, reply }: PlanInput): SpeechAction {
  if (!reply) {
    // Cevap kayboldu (oturum degisti, mesaj silindi): acik oturum kapanmali.
    return live ? { kind: 'retire' } : { kind: 'wait' }
  }

  if (live && live.id !== reply.id) {
    return { kind: 'retire' }
  }

  if (!live) {
    if (declined || !playbackIdle) {
      return { kind: 'wait' }
    }

    return { kind: 'open', id: reply.id }
  }

  if (reply.text.length > live.sent) {
    return {
      kind: 'append',
      sent: reply.text.length,
      text: reply.text.slice(live.sent)
    }
  }

  // Gonderilecek yeni metin yok. Cevap da bittiyse oturumu kapat.
  return reply.pending ? { kind: 'wait' } : { kind: 'finish' }
}
