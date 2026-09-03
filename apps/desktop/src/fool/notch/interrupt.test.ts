import { describe, expect, it, vi } from 'vitest'

import { interruptThenSubmit, shouldInterruptTurn, waitUntilSettled } from './interrupt'

describe('durdurma penceresi', () => {
  it('dusunme ve konusma sirasinda durduruyor', () => {
    expect(shouldInterruptTurn('thinking')).toBe(true)
    expect(shouldInterruptTurn('speaking')).toBe(true)
  })

  it('bosta, dinlerken ve yaziya dokerken durdurmuyor', () => {
    expect(shouldInterruptTurn('idle')).toBe(false)
    expect(shouldInterruptTurn('listening')).toBe(false)
    expect(shouldInterruptTurn('transcribing')).toBe(false)
  })
})

describe('durdur-sonra-gonder sirasi', () => {
  it('gonderim durdurma cozulmeden baslamiyor', async () => {
    // Ters sirada calistirmak yeni istemi MESGUL bir oturuma yollamakti.
    const order: string[] = []
    // Kapanis icinde atanan bir ``let``i TypeScript ``never``e daraltiyor
    // (atama akis analizinde gorunmuyor), o yuzden bir nesne alaninda
    // tutuluyor.
    const gate: { release: () => void } = { release: () => undefined }

    const pending = interruptThenSubmit({
      interrupt: () =>
        new Promise<void>(resolve => {
          order.push('interrupt:start')

          gate.release = () => {
            order.push('interrupt:done')
            resolve()
          }
        }),
      submit: () => {
        order.push('submit')
      }
    })

    // Durdurma hala askida: gonderim BASLAMAMIS olmali.
    await Promise.resolve()

    expect(order).toEqual(['interrupt:start'])

    gate.release()
    await pending

    expect(order).toEqual(['interrupt:start', 'interrupt:done', 'submit'])
  })

  it('durdurma dusse bile cumle yine de gonderiliyor', async () => {
    // Kullanicinin soyledigi cumle elimizde. Ag hatasini yutup onu cope
    // atmak, araya girmenin kendisinden daha kotu bir sonuc.
    const submit = vi.fn()
    const onInterruptError = vi.fn()

    await interruptThenSubmit({
      interrupt: () => Promise.reject(new Error('gateway down')),
      onInterruptError,
      submit
    })

    expect(submit).toHaveBeenCalledOnce()
    expect(onInterruptError).toHaveBeenCalledOnce()
    expect(onInterruptError.mock.calls[0][0]).toBeInstanceOf(Error)
  })

  it('senkron firlatan durdurma da akisi kesmiyor', async () => {
    const submit = vi.fn()

    await interruptThenSubmit({
      interrupt: () => {
        throw new Error('boom')
      },
      submit
    })

    expect(submit).toHaveBeenCalledOnce()
  })

  it('gonderim hatasi YUTULMUYOR', async () => {
    // Gonderim gercekten basarisizsa cagiran taraf bunu gormeli --
    // kullanici cevap beklerken sessizce hicbir sey olmamasi kabul edilemez.
    await expect(
      interruptThenSubmit({
        interrupt: () => undefined,
        submit: () => Promise.reject(new Error('submit failed'))
      })
    ).rejects.toThrow('submit failed')
  })
})

// ---------------------------------------------------------------------------
// Yatışmayı bekleme — iki yüzeyin ORTAK kuralı
//
// "notch bu conversation modun birebir aynısı ancak bas konuşlu hali olmalı."
// Farkın kaldığı son yer buydu: sohbet kipi araya girdikten sonra turun
// bitmesini bekliyordu, çentik beklemeden gönderiyordu.
// ---------------------------------------------------------------------------

describe('waitUntilSettled', () => {
  const sleep = () => Promise.resolve()

  it('tur bitmisse HEMEN donuyor', async () => {
    expect(await waitUntilSettled({ busy: () => false, sleep })).toBe(true)
  })

  it('tur bitene kadar BEKLIYOR', async () => {
    let left = 3

    const settled = await waitUntilSettled({
      busy: () => {
        left -= 1

        return left > 0
      },
      sleep
    })

    expect(settled).toBe(true)
    expect(left).toBeLessThanOrEqual(0)
  })

  it('yatismayan tur icin SURE DOLUYOR, sonsuza kadar beklemiyor', async () => {
    // Cumleyi sonsuza kadar tutmak, gec gondermekten kotu.
    const settled = await waitUntilSettled({ busy: () => true, timeoutMs: 0, sleep })

    expect(settled).toBe(false)
  })
})

describe('interruptThenSubmit + settle', () => {
  it('gonderim yatismadan BASLAMIYOR', async () => {
    const order: string[] = []
    let busy = true

    await interruptThenSubmit({
      interrupt: () => {
        order.push('interrupt')
        busy = false
      },
      settle: { busy: () => busy, sleep: () => Promise.resolve() },
      submit: () => order.push('submit')
    })

    expect(order).toEqual(['interrupt', 'submit'])
  })

  it('settle VERILMEZSE eski davranis korunuyor', async () => {
    const order: string[] = []

    await interruptThenSubmit({
      interrupt: () => order.push('interrupt'),
      submit: () => order.push('submit')
    })

    expect(order).toEqual(['interrupt', 'submit'])
  })

  it('durdurma DUSSE bile cumle gonderiliyor', async () => {
    // Kullanicinin konusmasini sessizce cope atmak, araya girmenin kendisinden
    // kotu bir sonuc.
    const order: string[] = []

    await interruptThenSubmit({
      interrupt: () => Promise.reject(new Error('ag hatasi')),
      onInterruptError: () => order.push('reported'),
      settle: { busy: () => false, sleep: () => Promise.resolve() },
      submit: () => order.push('submit')
    })

    expect(order).toEqual(['reported', 'submit'])
  })
})
