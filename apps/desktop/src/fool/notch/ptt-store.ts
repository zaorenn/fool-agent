/**
 * Bas-konuş tuşunun kalıcı hâli.
 *
 * Notch penceresi ile ayarlar paneli AYRI pencereler; ikisi de aynı bağlamayı
 * görmek zorunda.
 *
 * Burada ÖNCEDEN ``persistentAtom`` vardı ve bu yorum, değişikliğin ``storage``
 * olayıyla diğer pencereye ulaştığını söylüyordu. Ulaşmıyordu: o atom yazıyor
 * ama hiç dinlemiyor. Yorumun "kullanıcı notch'un yeniden başlatılmasını
 * beklerdi" diye tarif ettiği hata, tam olarak yaşanan hataydı -- ayarda tuşu
 * değiştiriyorsun, notch eski tuşu dinlemeye devam ediyor. Ölçüldü: depo
 * ``KeyQ``, notch penceresindeki atom ``ControlRight``.
 *
 * ``sharedAtom`` dinlemeyi de ekliyor (bkz. ``fool/cross-window-atom.ts``).
 *
 * Zone A: upstream bu dosyayı bilmiyor.
 */

import { sharedAtom } from '../cross-window-atom'

import { DEFAULT_PTT_CODE, formatPttBinding, parsePttBinding } from './ptt-binding'

/**
 * Saklanan degeri NORMALLESTIR.
 *
 * ``sanitizePttCode`` burada YETMIYOR: o yalnizca tek bir ``code`` kabul
 * ediyor ve ``"Shift+ControlRight"``i tanimadigi icin sessizce varsayilana
 * dusuruyordu -- yani kullanici komboyu kaydediyor, ayar paneli bir sonraki
 * acilista yine "Right Ctrl" gosteriyordu.
 *
 * Ayristirip geri yazmak ayni zamanda SIRAYI sabitliyor: ``Alt+Shift+KeyV``
 * ile ``Shift+Alt+KeyV`` ayni baglama ve tek bir dizeye indirgenmezse
 * karsilastirma sessizce basarisiz olur.
 */
const normalize = (raw: unknown): string => formatPttBinding(parsePttBinding(raw))

export const $pttCode = sharedAtom<string>('fool.desktop.notch.pushToTalkCode', DEFAULT_PTT_CODE, {
  // Saklanan değer kullanıcının elinde: bozuk bir giriş bas-konuşu sessizce
  // ölü bırakırdı, o yüzden okuma yolunda temizleniyor.
  decode: normalize,
  encode: normalize
})

/**
 * Bağlamayı ANA SÜRECE bildir.
 *
 * Ölçülen kırıklık: ``installPushToTalkForwarding`` ``'ControlRight'``e
 * SABİTLENMİŞTİ. Yani kullanıcı tuşu değiştirdiğinde çentik odaktayken
 * çalışıyor, odak ana pencereye geçtiği anda ölüyordu -- ve odak ilk cevap
 * çizilir çizilmez oraya geçiyor. Ayarın "bir tur çalışıp bozulması" buydu.
 *
 * Ana sürece YALNIZCA fiziksel tuş gidiyor, değiştiriciler değil: eşleşmenin
 * tamamı ``bindingMatches`` ile çentikte yapılıyor. Ana süreçte ikinci bir
 * eşleştirici yazmak, ayrışması an meselesi olan bir kopya olurdu -- ana
 * süreç ``src/`` içinden içe aktaramıyor (``tsconfig.electron.json``
 * ``src``i dışlıyor), yani o kopya paylaşılamazdı bile.
 */
function publishToMain(value: string): void {
  if (typeof window === 'undefined') {
    return
  }

  void window.foolDesktop?.notch?.setPushToTalk?.(parsePttBinding(value).code)
}

// Montajda BIR KEZ: ana surec varsayilanla basliyor ve kullanicinin ayari
// onceki oturumdan gelmis olabilir. ``listen`` yalnizca DEGISIMDE atesliyor.
publishToMain($pttCode.get())
$pttCode.listen(publishToMain)
