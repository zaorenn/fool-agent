/**
 * Seçili seslendirme motorunu UYGULAMA AÇILIR AÇILMAZ ısıt.
 *
 * İstenen: "her sohbette ses modelinin ısınması çok geç sürüyor; uygulama
 * açılıyken seçili ses modeli direkt olarak ısıtılsın, ne seçili olursa olsun,
 * ve sadece ısınma hazır olduğunda notch bas-konuş çalışsın; o zamana kadar
 * notchta 'TTS ısınıyor' gibi bilgi yazsın."
 *
 * Neden açılışta
 * --------------
 * Isıtma bugüne kadar yalnızca TEPKİSELDİ: mikrofon açılınca, çentik oturumu
 * açılınca, otomatik okuma açıkken. Hepsi kullanıcı zaten konuşmaya
 * hazırlanmışken tetikleniyor, yani soğuk yükleme onun bekleyişine biniyor.
 * Ölçüldü (bu makine, Chatterbox + CUDA): soğuk 36,8 sn / sıcak 0,8 sn.
 *
 * 36 saniye "kullanıcının konuşmasına gizlenebilecek" bir süre değil. Açılışta
 * ısıtmak o bedeli kimsenin beklemediği bir ana taşıyor.
 *
 * Neden durumu YAYINLIYOR
 * -----------------------
 * Çentik ayrı bir pencere ve arka uca kendi soramaz -- daha doğrusu sorabilir
 * ama iki pencere aynı motoru iki kez ısıtmaya çalışırdı. Durum paylaşılan
 * değerden geçiyor (bkz. ``cross-window-atom.ts``), yani ısıtmayı BİR taraf
 * yürütüyor ve diğerleri yalnızca okuyor.
 *
 * Zone A: upstream bu dosyayı bilmiyor.
 */

import { whenMainWindow } from '@/store/main-window-only'

import { sharedAtom } from './cross-window-atom'
import { voiceApi } from './voice-api'

/** Seslendirmenin ısınma durumu — çentiğin bas-konuşu buna bakıyor. */
export type VoiceWarmState = 'unknown' | 'warming' | 'ready' | 'failed'

export const $voiceWarm = sharedAtom<VoiceWarmState>('fool.desktop.voice.warm', 'unknown', {
  decode: raw => (raw === 'warming' || raw === 'ready' || raw === 'failed' ? raw : 'unknown'),
  encode: value => value
})

/** Arka uç ayağa kalkana kadar yeniden deneme aralığı. */
const RETRY_MS = 2_000
/** Isınma sürerken durum yoklama aralığı. */
const POLL_MS = 1_500
/**
 * Vazgeçme sınırı.
 *
 * Süresiz yoklamak, motoru hiç kurulmamış bir kullanıcının makinesinde sonsuza
 * kadar iki saniyede bir istek atmak olurdu. Sınıra gelince durum
 * ``failed``e düşüyor ve bas-konuş AÇILIYOR: ısınmayı bekleyemediğimiz için
 * kullanıcıyı susturmak, ısınmamış bir motorla konuşmasına izin vermekten
 * kötü.
 */
const GIVE_UP_MS = 5 * 60_000

function normalize(status: unknown): VoiceWarmState {
  const value = String(status ?? '').toLowerCase()

  if (value === 'warm') {
    return 'ready'
  }

  if (value === 'warming' || value === 'loading') {
    return 'warming'
  }

  return value === 'failed' ? 'failed' : 'unknown'
}

if (typeof window !== 'undefined') {
  // YALNIZCA ana pencere ısıtıyor. Çentik aynı paketi yüklüyor; kapısız
  // kalsaydı iki pencere aynı motoru iki kez yüklemeye çalışır ve tek-motor
  // kuralı yüzünden yükle-boşalt döngüsüne girerdi.
  whenMainWindow(() => {
    const startedAt = Date.now()

    const tick = () => {
      // Çağrı ETKİSİZ tekrarlanabilir: motor zaten sıcaksa ya da ısınıyorsa
      // yeni iş başlatmıyor, yalnızca durumu döndürüyor. Bu yüzden yoklama
      // ile başlatma aynı çağrı olabiliyor.
      void voiceApi
        .warmVoice()
        .then(reply => {
          const state = normalize(reply?.tts?.status)

          $voiceWarm.set(state === 'unknown' ? 'warming' : state)

          if (state === 'ready' || state === 'failed') {
            return
          }

          window.setTimeout(tick, POLL_MS)
        })
        .catch(() => {
          // Arka uç henüz ayakta değil. Bu bir hata değil, açılış sırası.
          if (Date.now() - startedAt > GIVE_UP_MS) {
            $voiceWarm.set('failed')

            return
          }

          window.setTimeout(tick, RETRY_MS)
        })
    }

    tick()
  })
}
