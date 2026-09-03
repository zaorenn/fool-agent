/**
 * "Sesi kes" isteği PENCERELER ARASI.
 *
 * Ölçülen hata
 * ------------
 * Çentikten araya girildiğinde konuşma durmuyordu. Sebebi ekran görüntüsünde
 * duruyordu: alt çubukta "Reading aloud" yazan yer ANA PENCERE. Cevabı
 * seslendiren taraf oydu (çentik ``canSpeak('notch')`` ile susuyor, bkz.
 * ``fool/voice-owner.ts``), ama araya girme yolu ``stopVoicePlayback()``
 * çağırıyordu -- ve o, çağrıldığı pencerenin KENDİ ``AudioContext``ini
 * durduran modül düzeyinde bir işlev.
 *
 * Yani çentik kendi sessizliğini kesiyor, kullanıcının duyduğu ses başka bir
 * renderer sürecinde çalmaya devam ediyordu. Kullanıcının bildirdiği
 * "konuşurken Ctrl'ye basıp konuştuğumda speaking aloud durmadı ve cümlem
 * görmezden gelindi" tam olarak bu.
 *
 * Çözüm, oturum kimliğiyle aynı yoldan: paylaşılan bir değer. Değer bir DURUM
 * değil OLAY -- üst üste iki araya girme ayırt edilebilmeli -- o yüzden damga.
 *
 * Bu modül HER pencerede koşuyor (``whenMainWindow`` YOK): sesi kimin çaldığı
 * baştan belli değil ve durması gereken taraf tam da çalan taraf.
 *
 * Zone A: upstream bu dosyayı bilmiyor.
 */

import { stopVoicePlayback } from '@/lib/voice-playback'

import { sharedAtom } from './cross-window-atom'

/** Son "sesi kes" isteğinin damgası. */
export const $voiceStopRequest = sharedAtom<string>('fool.desktop.voice.stop', '', {
  decode: raw => raw,
  encode: value => value
})

/** Her pencerede sesi kes. Çağıran kendi penceresini zaten susturuyor. */
export function requestVoiceStopEverywhere(): void {
  $voiceStopRequest.set(String(Date.now()))
}

if (typeof window !== 'undefined') {
  // ``listen`` DEĞİL: açılışta depoda duran eski bir damga yeni bir pencerenin
  // sesini kesmemeli. ``subscribe`` mevcut değeri de verirdi.
  $voiceStopRequest.listen(value => {
    if (value) {
      stopVoicePlayback()
    }
  })
}
