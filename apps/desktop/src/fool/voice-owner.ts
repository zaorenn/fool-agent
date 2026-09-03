/**
 * Aynı PENCERE içinde tek yüzey konuşur.
 *
 * Kapsam SINIRI, en başta yazılmalı
 * ---------------------------------
 * Burası ``atom`` -- yani değer PENCEREYE ÖZEL. Çentik ayrı bir
 * ``BrowserWindow`` ve aynı paketi yüklüyor, dolayısıyla kendi kopyasını
 * tutuyor. ``claimVoice('notch')`` çentikte çalışınca ana penceredeki
 * ``$voiceOwner`` ``null`` kalıyor ve oradaki ``canSpeak('composer')``
 * her zaman ``true`` dönüyor.
 *
 * Bu dosya uzun süre bunun TERSİNİ iddia etti: başlığı "aynı anda tek yüzey
 * konuşur" diyordu, gerekçesi çentik ile sohbet panelini örnek veriyordu --
 * yani tam olarak taşıyamadığı durumu. Kullanıcının duyduğu sonuç: aynı cümle
 * iki kez okunuyordu.
 *
 * Pencereler arası güvence BURADA DEĞİL
 * -------------------------------------
 * O iş ``store/ambient.ts::ownsAmbientCue`` ile yapılıyor: talep ANA SÜREÇTE
 * çözülüyor (``electron/event-dedupe.ts``), yarışsız, kalıcılık yok. Cevap
 * başına tek sahip. Hem besteci hem çentik oraya katılıyor.
 *
 * ``sharedAtom`` neden kullanılmadı: o ``localStorage`` tabanlı ve sahiplik
 * GEÇİCİ bir durum. Kalıcılaştırmak, uygulama çentik konuşurken kapanınca
 * "sahip: notch" yazısını diske bırakırdı; bir sonraki açılışta çentik kapalı
 * olur, besteci sonsuza kadar susardı. Sessiz sınıf, yeni biçimde.
 *
 * Geriye kalan iş
 * ---------------
 * Aynı pencerede iki yüzey birden (besteci sesli turu + otomatik sesli okuma)
 * uyanabiliyor; bu ikisini ayıran hâlâ burası.
 *
 * Zone A: upstream bu dosyayı bilmiyor.
 */

import { atom } from 'nanostores'

/**
 * ``friend`` KALDIRILDI: Friend penceresi kullanıcının kararıyla silindi ve
 * geride yalnızca çentikten YÜKSEK öncelikli, hiç talep edilmeyen bir katman
 * bıraktı. Ölü bir öncelik katmanı okurken "bir şey bunu ezebilir" izlenimi
 * veriyordu.
 */
export type VoiceSurface = 'composer' | 'notch'

/**
 * Öncelik: büyük olan kazanır.
 *
 * Çentik önde çünkü kullanıcı onu AÇARAK konuşmayı seçti ve akış yolunu
 * kullanıyor (ilk cümlede ses). Besteci geride: orada ses bir yan özellik.
 */
const PRIORITY: Record<VoiceSurface, number> = {
  composer: 1,
  notch: 2
}

/** Şu an konuşmaya yetkili yüzey. ``null`` = kimse. */
export const $voiceOwner = atom<VoiceSurface | null>(null)

/**
 * Sahipliği talep et.
 *
 * Daha yüksek öncelikli bir yüzey sahipse ``false`` döner ve çağıran
 * SESSİZ kalır -- konuşmaya çalışıp diğerini iptal etmek yerine.
 */
export function claimVoice(surface: VoiceSurface): boolean {
  const current = $voiceOwner.get()

  if (current === surface) {
    return true
  }

  if (current !== null && PRIORITY[current] > PRIORITY[surface]) {
    return false
  }

  $voiceOwner.set(surface)

  return true
}

/** Sahipliği bırak -- yalnızca gerçekten sahipsen. */
export function releaseVoice(surface: VoiceSurface): void {
  if ($voiceOwner.get() === surface) {
    $voiceOwner.set(null)
  }
}

/**
 * Bu yüzey şu an konuşabilir mi?
 *
 * Sahip YOKSA da ``true``: sahiplik seslendirmeyi engellemek için değil,
 * ÇAKIŞMAYI engellemek için var. Tek yüzey açıkken hiçbir şey talep
 * etmemişse yine konuşulmalı.
 */
export function canSpeak(surface: VoiceSurface): boolean {
  const current = $voiceOwner.get()

  return current === null || current === surface
}
