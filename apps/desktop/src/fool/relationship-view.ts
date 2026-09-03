/**
 * İlişki barının SAYIYA bakan kısmı — React'ten ayrı, çünkü sınanan şey bu.
 *
 * Bileşenin kendisi yalnızca çiziyor. "Ne kadar dolu", "hangi renk", "ne
 * kadar zaman önce" kararları burada duruyor; birer saf fonksiyon oldukları
 * için pencere açmadan sınanabiliyorlar.
 *
 * Zone A: upstream bu dosyayı bilmiyor.
 */

/** Sunucunun ``/api/fool/relationship`` cevabı. */
export interface RelationshipSnapshot {
  enabled: boolean
  /** Aranızda bir şey geçti mi. ``false`` ise duruş İDDİA EDİLMİYOR. */
  started?: boolean
  /** Bu kişiyle daha önce konuşulmuş mu -- tanışma selamının kapısı. */
  met?: boolean
  warmth?: number
  stance?: RelationshipStance
  label?: string
  summary?: string
  grievances?: { text: string; since: number; weight: number }[]
}

export type RelationshipStance = 'close' | 'fond' | 'neutral' | 'cool' | 'cold'

/**
 * Barın dolu oranı (0-100).
 *
 * Kırpma savunma amaçlı: sunucu aralığı zaten kısıtlıyor ama bar kırpmadan
 * çizilirse tek bir bozuk değer çubuğu kabın dışına taşırır.
 */
export function warmthPercent(warmth: number | undefined): number {
  if (typeof warmth !== 'number' || Number.isNaN(warmth)) {
    return 50
  }

  return Math.max(0, Math.min(100, warmth))
}

/**
 * Duruşun rengi.
 *
 * Yeşil/kırmızı DEĞİL: bu bir ölçü aleti değil, birinin sana nasıl baktığı.
 * Sıcak uçta amber, soğuk uçta mavi -- sıcaklığın kendi sözcüğüyle aynı yönde.
 */
export function stanceTone(stance: RelationshipStance | undefined): string {
  switch (stance) {
    case 'close':
      return 'text-amber-400'

    case 'fond':
      return 'text-amber-300/90'

    case 'cool':
      return 'text-sky-300/90'

    case 'cold':
      return 'text-sky-400'

    default:
      return 'text-muted-foreground'
  }
}

export function stanceFill(stance: RelationshipStance | undefined): string {
  switch (stance) {
    case 'close':
      return 'bg-amber-400'

    case 'fond':
      return 'bg-amber-300/80'

    case 'cool':
      return 'bg-sky-300/80'

    case 'cold':
      return 'bg-sky-400'

    default:
      return 'bg-muted-foreground/50'
  }
}

/**
 * "ne zamandır kırgın" — kaba ve okunur.
 *
 * Saniye GÖSTERİLMİYOR: bir kırgınlığın yaşını saniyeyle vermek onu bir
 * sayaca çevirir. Kullanıcının sorduğu soru "ne zamandan beri", "tam olarak
 * ne kadar" değil.
 */
export function describeSince(since: number, now: number): string {
  const seconds = Math.max(0, now / 1000 - since)

  if (seconds < 90) {
    return 'just now'
  }

  const minutes = Math.round(seconds / 60)

  if (minutes < 60) {
    return minutes + 'm ago'
  }

  const hours = Math.round(minutes / 60)

  if (hours < 24) {
    return hours + 'h ago'
  }

  const days = Math.round(hours / 24)

  if (days < 7) {
    return days + 'd ago'
  }

  const weeks = Math.round(days / 7)

  return weeks + 'w ago'
}

/**
 * Bar hiç çizilmeli mi?
 *
 * Sıradan ajanın ilişki durumu yok: orada bar GÖRÜNMEMELİ, boş da olsa.
 * Bir de henüz cevap gelmediyse (``null``) çizilmiyor -- açılışta bir anlık
 * "Neutral" göstermek, kullanıcının hiç yaşamadığı bir durumu iddia etmek
 * olurdu.
 */
export function shouldRender(snapshot: null | RelationshipSnapshot): boolean {
  return snapshot !== null && snapshot.enabled === true
}
