/**
 * Araya girerken süren turu durdurma sırası — saf, DOM'suz, sınanabilir.
 *
 * Neden gerekiyor
 * ---------------
 * Notch araya girince yalnızca OYNATMAYI kesiyordu: ``stopVoicePlayback()`` +
 * akış oturumunu kapat. Model ise cevabı üretmeye devam ediyor. Sonuç, ölçülü
 * bir hata değil ama net bir davranış kırıklığı:
 *
 *   * Eski cevabın kalan tokenları gelmeye devam ediyor ve
 *     ``collectUnspokenTurnSpeech`` onları YENİ tur bittikten sonra
 *     seslendiriyor -- kullanıcı sözünü kesti, ajan biraz sonra kaldığı
 *     yerden devam ediyor.
 *   * Yeni istem, eski tur hâlâ meşgulken gönderiliyor.
 *
 * Composer tarafı bunu zaten doğru yapıyor (``use-voice-conversation.ts``:
 * üretim evresinde ``onInterrupt`` çağrılıyor ve ``busy`` yatışana kadar
 * bekleniyor). Notch o dikişi hiç kullanmıyordu.
 *
 * Neden durdurma BAŞARISIZ olsa da gönderiyoruz
 * ---------------------------------------------
 * Kullanıcının söylediği cümle elimizde. Durdurma çağrısı ağ hatasıyla
 * düşerse onu YUTMAK, kullanıcının konuşmasını sessizce çöpe atmak demek --
 * araya girmenin kendisinden daha kötü bir sonuç. Hata bildiriliyor, cümle
 * yine de gönderiliyor.
 *
 * Zone A: upstream bu dosyayı bilmiyor.
 */

import type { NotchStatus } from './use-notch-voice'

/**
 * Süren turu durdurmak gerekiyor mu?
 *
 * ``speaking`` de dahil: oynatma sürerken üretim çoktan bitmiş OLABİLİR ama
 * bunu notch bilmiyor ve bitmiş bir turu durdurmak ağ geçidinde işlemsiz.
 * Emin olmadığımızda durdurmak, emin olmadığımızda bırakmaktan ucuz.
 */
export function shouldInterruptTurn(status: NotchStatus): boolean {
  return status === 'thinking' || status === 'speaking'
}

/** Araya girmenin yatışması için beklenecek en uzun süre. */
export const INTERRUPT_SETTLE_TIMEOUT_MS = 5_000

export interface SettleOptions {
  /** Tur HÂLÂ sürüyor mu? Her yoklamada yeniden okunuyor. */
  busy: () => boolean
  timeoutMs?: number
  /** Sınav için enjekte edilebilir bekleme. */
  sleep?: (ms: number) => Promise<void>
}

/**
 * Durdurma İSTENDİ ile tur GERÇEKTEN bitti arasını bekle.
 *
 * Ağ geçidine "durdur" demek anında değil: istek dönüyor, tur hâlâ
 * çözülüyor. Gönderim yolu meşgul bir oturumu reddediyor, yani beklemeden
 * göndermek kullanıcının cümlesini sessizce düşürüyor.
 *
 * Süre sınırlı: yatışmayan bir tur yüzünden cümleyi sonsuza kadar tutmak,
 * geç göndermekten kötü. Süre dolarsa yine de gönderiliyor.
 */
export async function waitUntilSettled({
  busy,
  timeoutMs = INTERRUPT_SETTLE_TIMEOUT_MS,
  sleep = ms => new Promise(resolve => setTimeout(resolve, ms))
}: SettleOptions): Promise<boolean> {
  const deadline = Date.now() + timeoutMs

  while (busy() && Date.now() < deadline) {
    await sleep(100)
  }

  return !busy()
}

export interface InterruptThenSubmitSteps {
  interrupt: () => Promise<unknown> | unknown
  submit: () => Promise<unknown> | unknown
  /** Durdurma düştüyse haber ver — ama akışı kesme. */
  onInterruptError?: (cause: unknown) => void
  /**
   * Verilirse gönderimden ÖNCE turun yatışması bekleniyor.
   *
   * Sohbet kipi bunu baştan beri yapıyordu, notch yapmıyordu -- ve fark
   * kullanıcının gördüğü davranışta: üretim ortasında araya girince notch
   * yeni cümleyi hâlâ meşgul bir oturuma yolluyordu. İki yüzey "notch,
   * conversation'ın bas-konuşlu hâli olmalı" diye tanımlandığı için kural
   * TEK yerde duruyor.
   */
  settle?: SettleOptions
}

/**
 * Önce durdur, SONRA gönder.
 *
 * Sıra garanti: gönderim, durdurma çözülmeden başlamıyor. Ters sırada
 * çalıştırmak yeni istemi meşgul bir oturuma yollamak demekti.
 */
export async function interruptThenSubmit(steps: InterruptThenSubmitSteps): Promise<void> {
  try {
    await steps.interrupt()
  } catch (cause) {
    steps.onInterruptError?.(cause)
  }

  if (steps.settle) {
    await waitUntilSettled(steps.settle)
  }

  await steps.submit()
}
