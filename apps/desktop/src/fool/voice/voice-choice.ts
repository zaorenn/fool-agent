/**
 * Friend penceresindeki ses seçicisinin saf mantığı.
 *
 * Neden ayrı dosya
 * ----------------
 * Buradaki hata bileşenin İÇİNDE yaşıyordu ve bileşeni render etmeden
 * görülemiyordu: mikrofon, ağ geçidi, depo, i18n -- hepsi ayağa kalkmadan bir
 * açılır listenin seçeneklerini sınayamıyordum. Seçim mantığı saf olunca
 * sınanabiliyor (aynı gerekçeyle notch kısayol sıralaması da ayrılmıştı).
 *
 * Zone A: upstream bu dosyayı bilmiyor.
 */

import type { VoiceCatalog, VoiceItem } from '../voice-api'

/** Seçilebilir motorlar: yalnızca KURULU olan seslendirme motorları. */
export function voiceOptions(catalog: null | VoiceCatalog): VoiceItem[] {
  return (catalog?.items ?? []).filter(item => item.kind === 'tts' && item.installed)
}

/**
 * Sunucuda AKTİF olan motorun katalog kimliği (`''` = hiçbiri).
 *
 * Gösterim tek yönlü: hakikat sunucudaki ``tts.provider``, buradaki değer
 * onun kopyası. Kopyayı yalnızca pencere açılışında doldurmak yetmiyordu --
 * kullanıcı motoru Ayarlar'dan değiştirdiğinde Friend penceresi ESKİ adı
 * tutuyor, panel bir şey gösterip başka bir ses duyuluyordu.
 */
export function selectedVoiceId(catalog: null | VoiceCatalog): string {
  return voiceOptions(catalog).find(item => item.active)?.id ?? ''
}

/**
 * Açılır listede BOŞ seçenek olamaz.
 *
 * Ölçüldü: ``voice_models.select("")`` -> ``ValueError: bilinmeyen oge:`` ->
 * HTTP 400. Yani listedeki "Default voice" seçeneğini seçmek bir hata
 * bildirimi çıkarıyor, motoru değiştirmiyor, ama açılır listeyi yine de o
 * seçenekte bırakıyordu. Panelde bir şey görüp başka bir sesi duymanın ta
 * kendisi -- kullanıcının bildirdiği hatanın aynısı.
 */
export function isChoosableVoiceId(entryId: string): boolean {
  return entryId.trim().length > 0
}
