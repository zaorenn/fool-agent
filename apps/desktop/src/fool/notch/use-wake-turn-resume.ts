/**
 * Uyandırma turu bitince dinleyiciyi GERİ AÇ -- ana pencerede.
 *
 * Ölçülen hata
 * ------------
 * Uyandırma sözcüğü bir kez çalışıp susuyordu. Kullanıcının bildirdiği: "ilk
 * hey hermesten sonra notch açıkken bir daha hey hermes demem bir işe
 * yaramıyor... wake word dinlemesi açılıp kapanana ya da notch açılıp
 * kapanana kadar tekrardan wake word çalışmıyor." Ve kuralı da o koydu: "bu
 * sorunu hermes için değil GENEL wake word için çöz."
 *
 * Sunucu ``wake.detected``i yayınlamadan hemen önce dinleyiciyi duraklatıyor
 * (``tui_gateway/server.py::_on_detect`` → ``pause_listening``) ve kendi geri
 * açması yalnızca SUNUCU tarafındaki ses döngüsünün geri çağrılarında
 * (``_resume_voice_wake``). Masaüstü yakalamayı tarayıcı tarafında yapıyor:
 * o döngü hiç koşmuyor, yani duraklatmayı istemci geri almak zorunda.
 *
 * Composer'ın konuşma kipi bunu yapıyordu; uyandırmayı çentiğe yönlendirince
 * o yol devre dışı kaldı ve borcu ödeyen kimse kalmadı. Kanca borcu geri
 * getiriyor -- ama artık FAZA değil TURA bağlı: çentik turun bittiğini
 * yazıyor, burası geri açıyor.
 *
 * Neden ana pencere
 * -----------------
 * Kira burada: ``resumeWakeAfterVoice`` ``surface: 'gui'`` ile uzlaştırıyor.
 * Çentik ayrı bir ``BrowserWindow`` ve oradan istemek kirayı başka bir
 * taşıyıcıya devrederdi.
 *
 * Zone A: upstream bu dosyayı bilmiyor.
 */

import { useEffect } from 'react'

import { isNotchWindow } from '@/fool/notch/window'
import { resumeWakeAfterVoice } from '@/store/wake-word'

import { $wakeTurnActive, wakeTurnIsActive } from './active-session'

export function useWakeTurnResume(): void {
  useEffect(() => {
    if (isNotchWindow()) {
      return undefined
    }

    // ``subscribe`` açılışta mevcut değeri de veriyor. İlki BİR GEÇİŞ DEĞİL:
    // uygulama açılırken depoda kalmış bir bayrağı tur bitişi sayıp
    // gereksiz bir uzlaştırma tetiklerdi.
    let first = true
    let previous = false

    const unsubscribe = $wakeTurnActive.subscribe(value => {
      const active = wakeTurnIsActive(value)

      if (first) {
        first = false
        previous = active

        return
      }

      const ended = previous && !active
      previous = active

      if (!ended) {
        return
      }

      // ``resumeWakeAfterVoice`` yapılandırmaya göre UZLAŞTIRIYOR: kullanıcı
      // tur sırasında uyandırmayı kapattıysa kapalı kalıyor, mikrofonun
      // bırakılmasını bekleyip yeniden deniyor ve hiçbir zaman ``persist``
      // yazmıyor. Yani burada "aç" demiyoruz, "olması gereken yere dön"
      // diyoruz.
      void resumeWakeAfterVoice()
    })

    return unsubscribe
  }, [])
}
