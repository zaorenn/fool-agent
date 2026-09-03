/**
 * Ses ayarları panelinin davranış testleri.
 *
 * Sınanan şey görünüm değil, kullanıcının gerçekten yaşadığı akış: kurulu olan
 * öğe "Installed" der, olmayan indirilebilir, süren bir kurulum panel yeniden
 * açıldığında kaldığı yerden görünür ve CUDA düğmesi kart yokken ÇIKMAZ.
 */

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { VoiceCatalog, VoiceItem, VoiceJob } from './voice-api'

const catalog = vi.fn()
const install = vi.fn()
const job = vi.fn()
const setKnob = vi.fn((..._args: unknown[]) => Promise.resolve({ ok: true }))

vi.mock('./voice-api', () => ({
  voiceApi: {
    cancel: (...args: unknown[]) => Promise.resolve({ cancelled: true }),
    catalog: (...args: unknown[]) => catalog(...args),
    install: (...args: unknown[]) => install(...args),
    job: (...args: unknown[]) => job(...args),
    setDevice: (...args: unknown[]) => Promise.resolve({ ok: true }),
    setVoice: (...args: unknown[]) => Promise.resolve({ ok: true }),
    setKnob: (...args: unknown[]) => setKnob(...args),
    clones: () => Promise.resolve({ clones: [] }),
    installCuda: () => Promise.resolve({}),
    uploadClone: () => Promise.resolve({ id: 'x', label: 'x' }),
    selectClone: () => Promise.resolve({ ok: true }),
    deleteClone: () => Promise.resolve({ ok: true }),
    select: (...args: unknown[]) => Promise.resolve({ ok: true })
  }
}))

const notifyError = vi.fn()

vi.mock('@/store/notifications', () => ({
  notifyError: (...args: unknown[]) => notifyError(...args)
}))

const { VoiceSettings } = await import('./voice-settings')

function item(overrides: Partial<VoiceItem> = {}): VoiceItem {
  return {
    active: false,
    device: 'auto',
    // ``provider_id`` yapilandirmaya YAZILAN ad (``qwen3-tts`` indirilir,
    // ``qwen3`` secilir). Sunucu zaten gonderiyordu; arayuzde tanimli degildi.
    provider_id: 'test-provider',
    // Varsayilan SAGLIKLI: motorun bozuk oldugunu iddia eden her sinav bunu
    // acikca yazsin.
    engine_error: '',
    usable: true,
    cpu_warning: '',
    voice: '',
    knobs: [],
    voices: [],
    clone_capable: false,
    cuda_ready: false,
    clone: '',
    clone_help: '',
    assets_installed: true,
    cuda_available: false,
    devices: ['cpu'],
    engine_installed: true,
    id: 'piper',
    installed: true,
    job: null,
    kind: 'tts',
    label: 'Piper',
    recommended: false,
    size_label: '~63 MB',
    summary: 'Fast and fully local.',
    ...overrides
  }
}

function reply(items: VoiceItem[], cudaAvailable = false): VoiceCatalog {
  return { active: { stt: '', tts: '' }, cuda_available: cudaAvailable, items, voice_dir: 'C:\\fool\\voices' }
}

beforeEach(() => {
  vi.clearAllMocks()
})

afterEach(cleanup)

describe('VoiceSettings', () => {
  it('AKTIF ogeyi "In use" olarak gosterir', async () => {
    catalog.mockResolvedValue(reply([item({ active: true })]))

    render(<VoiceSettings />)

    expect(await screen.findByText('In use')).toBeTruthy()
  })

  it('kurulu ama aktif OLMAYAN oge secilebilir', async () => {
    // Dort model de kurulu oldugunda hangisinin konustugu belirsizdi;
    // "Use" dugmesi o secimi mumkun kiliyor.
    catalog.mockResolvedValue(reply([item({ active: false })]))

    render(<VoiceSettings />)

    expect(await screen.findByText('Use')).toBeTruthy()
    expect(screen.queryByText('In use')).toBeNull()
  })

  it('kurulu OLMAYAN oge icin KURULUM dugmesi cikarir', async () => {
    catalog.mockResolvedValue(reply([item({ engine_installed: false, installed: false })]))

    render(<VoiceSettings />)

    // Dugme KURULUM oldugunu soylemeli. Once yalnizca 'CPU' yaziyordu ve ona
    // basmak gigabaytlarca indirme baslatiyordu -- bir cihaz secici gibi duran
    // tek eylem dugmesi.
    expect(await screen.findByText(/Install \(CPU\)/)).toBeTruthy()
    expect(screen.queryByText('In use')).toBeNull()
  })

  it('CUDA dugmesi kart YOKKEN cikmaz', async () => {
    // Sunmak, sessizce CPU'ya dusen bir kurulum demekti ve kullanici neden
    // yavas oldugunu anlamiyordu.
    catalog.mockResolvedValue(
      reply([item({ cuda_available: false, devices: ['cpu', 'cuda'], installed: false })])
    )

    render(<VoiceSettings />)

    await screen.findByText(/Install \(CPU\)/)
    expect(screen.queryByText(/Install \(CUDA\)/)).toBeNull()
  })

  it('CUDA dugmesi kart VARKEN cikar', async () => {
    catalog.mockResolvedValue(
      reply([item({ cuda_available: true, devices: ['cpu', 'cuda'], installed: false })], true)
    )

    render(<VoiceSettings />)

    expect(await screen.findByText(/Install \(CUDA\)/)).toBeTruthy()
  })

  it('sunucuda SUREN kurulumu panel acilir acilmaz gosterir', async () => {
    // Panel kapatilip acildiginda cubuk sifirlanmamali: is sunucuda duruyor.
    const running: VoiceJob = {
      detail: '12 / 63 MB',
      device: 'cpu',
      elapsed: 4,
      entry_id: 'piper',
      error: '',
      id: 'j1',
      percent: 41,
      stage: 'downloading voice model',
      state: 'running'
    }

    catalog.mockResolvedValue(reply([item({ installed: false, job: running })]))
    job.mockResolvedValue(running)

    render(<VoiceSettings />)

    expect(await screen.findByText(/downloading voice model/)).toBeTruthy()
    expect(screen.getByText('41%')).toBeTruthy()
    expect(screen.getByText('Installing…')).toBeTruthy()
  })

  it('basarisiz kurulumun HATASINI gosterir', async () => {
    // Sessiz basarisizlik en kotusu: kullanici neden calismadigini bilemez.
    catalog.mockResolvedValue(
      reply([
        item({
          installed: false,
          job: {
            detail: '',
            device: 'cpu',
            elapsed: 3,
            entry_id: 'piper',
            error: 'pip failed: no matching distribution',
            id: 'j2',
            percent: 12,
            stage: 'failed',
            state: 'failed'
          }
        })
      ])
    )

    render(<VoiceSettings />)

    expect(await screen.findByText(/pip failed/)).toBeTruthy()
  })

  it('katalog cekilemezse kullaniciya bildirir', async () => {
    catalog.mockRejectedValue(new Error('gateway down'))

    render(<VoiceSettings />)

    await waitFor(() => {
      expect(notifyError).toHaveBeenCalled()
    })
  })

  it('TTS ve STT ayri bolumlerde listelenir', async () => {
    catalog.mockResolvedValue(
      reply([item(), item({ id: 'faster-whisper', kind: 'stt', label: 'Faster-Whisper' })])
    )

    render(<VoiceSettings />)

    expect(await screen.findByText('Text to speech')).toBeTruthy()
    expect(screen.getByText('Speech to text')).toBeTruthy()
    expect(screen.getByText('Faster-Whisper')).toBeTruthy()
  })

  /**
   * KURULU ama CALISMIYOR.
   *
   * Olculdu (bu makine, F5-TTS): ``find_spec("f5_tts")`` True donuyordu ama
   * ``import torchcodec`` paylasilan FFmpeg DLL'lerini bulamadigi icin
   * dusuyordu. Panel motoru "installed" VE "klonlanabilir" gosteriyor,
   * kullanici bir ses kaydi yukleyip klonu seciyor ve HICBIR SEY duymuyordu.
   */
  describe('kurulu ama calismayan motor', () => {
    const broken = () =>
      item({
        clone_capable: false,
        engine_error: 'Needs a shared FFmpeg build. Use StyleTTS 2 instead.',
        installed: true,
        usable: false
      })

    it('"Use" DEGIL "Unavailable" gosteriyor', async () => {
      catalog.mockResolvedValue(reply([broken()]))

      render(<VoiceSettings />)

      expect(await screen.findByText('Unavailable')).toBeTruthy()
      expect(screen.queryByText('Use')).toBeNull()
      expect(screen.queryByText('In use')).toBeNull()
    })

    it('NEDEN calismadigini ve NE YAPILACAGINI yaziyor', async () => {
      catalog.mockResolvedValue(reply([broken()]))

      render(<VoiceSettings />)

      expect(
        await screen.findByText('Needs a shared FFmpeg build. Use StyleTTS 2 instead.')
      ).toBeTruthy()
    })

    it('dinleme dugmesi YOK -- basmak yalnizca hata verirdi', async () => {
      catalog.mockResolvedValue(reply([broken()]))

      render(<VoiceSettings />)

      await screen.findByText('Unavailable')
      expect(screen.queryByText('Listen')).toBeNull()
    })

    it('klonlama arayuzu ACILMIYOR', async () => {
      catalog.mockResolvedValue(reply([broken()]))

      render(<VoiceSettings />)

      await screen.findByText('Unavailable')
      expect(screen.queryByText(/Drop a .*clip/i)).toBeNull()
    })

    it('SAGLIKLI motor bundan etkilenmiyor', async () => {
      catalog.mockResolvedValue(reply([item({ active: false })]))

      render(<VoiceSettings />)

      expect(await screen.findByText('Use')).toBeTruthy()
      expect(screen.queryByText('Unavailable')).toBeNull()
    })
  })

  describe('ses klonlama', () => {
    it('klonlamayi DESTEKLEYEN kurulu bir motorda hem surukleme hem TIKLAMA sunuyor', async () => {
      // Bir dosyayi Gezgin'den suruklemek herkes icin dogal degil --
      // tiklayip taramak ayni yere ayni dosyayi getiren ikinci bir yol.
      catalog.mockResolvedValue(
        reply([item({ clone_capable: true, clone_help: 'Drop 5-10 seconds of clean speech.' })])
      )

      render(<VoiceSettings />)

      expect(await screen.findByText(/Drop a voice sample to clone it/)).toBeTruthy()
      expect(screen.getByText(/click to browse/)).toBeTruthy()
    })

    it('klonlamayi DESTEKLEMEYEN kurulu bir motorda hicbir seyi gostermiyor', async () => {
      catalog.mockResolvedValue(reply([item({ clone_capable: false })]))

      render(<VoiceSettings />)

      await screen.findByText('Piper')
      expect(screen.queryByText(/Drop a voice sample/)).toBeNull()
    })

    it('yardim dugmesi motora ozel aciklamayi ACIP KAPATIYOR', async () => {
      // Chatterbox/styletts2/f5-tts klonlamayi FARKLI uyguluyor -- tek bir
      // genel yazi bu farki gizlerdi. Aciklama varsayilan KAPALI: her
      // satirda acik durursa kucuk panel gereksiz uzardi.
      catalog.mockResolvedValue(
        reply([
          item({
            clone_capable: true,
            clone_help: 'StyleTTS 2 borrows the clip tone and pacing.',
            id: 'styletts2',
            label: 'StyleTTS 2'
          })
        ])
      )

      render(<VoiceSettings />)

      await screen.findByText(/Drop a voice sample/)
      expect(screen.queryByText(/borrows the clip tone/)).toBeNull()

      fireEvent.click(screen.getByRole('button', { name: /How cloning works on StyleTTS 2/ }))
      expect(screen.getByText(/borrows the clip tone/)).toBeTruthy()

      fireEvent.click(screen.getByRole('button', { name: /How cloning works on StyleTTS 2/ }))
      expect(screen.queryByText(/borrows the clip tone/)).toBeNull()
    })

    it('klonlama YOKKEN yardim dugmesi de yok', async () => {
      // Bos bir aciklama icin bos bir dugme gostermek kullaniciyi
      // tiklayip hicbir sey olmadigini gormeye davet ederdi.
      catalog.mockResolvedValue(reply([item({ clone_capable: true, clone_help: '' })]))

      render(<VoiceSettings />)

      await screen.findByText(/Drop a voice sample/)
      expect(screen.queryByRole('button', { name: /How cloning works/ })).toBeNull()
    })

    it('bolgeye TIKLAMAK gizli dosya secicisini aciyor', async () => {
      catalog.mockResolvedValue(reply([item({ clone_capable: true, clone_help: 'help text' })]))

      render(<VoiceSettings />)

      const dropZone = await screen.findByText(/Drop a voice sample/)
      const clickSpy = vi.spyOn(HTMLInputElement.prototype, 'click')

      fireEvent.click(dropZone)

      expect(clickSpy).toHaveBeenCalled()
      clickSpy.mockRestore()
    })

    it('bilgi dugmesine tiklamak dosya secicisini AÇMIYOR', async () => {
      // Info dugmesi drop-zone'un icinde -- tiklamasi disariya YAYILIRSA
      // yardimi acmaya calisan kullanici ayni anda dosya secici de acardi.
      catalog.mockResolvedValue(
        reply([item({ clone_capable: true, clone_help: 'help text', id: 'styletts2', label: 'StyleTTS 2' })])
      )

      render(<VoiceSettings />)

      await screen.findByText(/Drop a voice sample/)
      const clickSpy = vi.spyOn(HTMLInputElement.prototype, 'click')

      fireEvent.click(screen.getByRole('button', { name: /How cloning works on StyleTTS 2/ }))

      expect(clickSpy).not.toHaveBeenCalled()
      clickSpy.mockRestore()
    })
  })
})

// ---------------------------------------------------------------------------
// Motora ozel sayilar
//
// Bildirilen: "ayarlardan ses modellerinin exaggeration gibi ayarlarini
// yapamiyoruz." Degerler yapilandirmada duruyordu ve motor onlari okuyordu;
// eksik olan YALNIZCA bu yuzeydi.
// ---------------------------------------------------------------------------

const INTENSITY = {
  id: 'exaggeration',
  label: 'Intensity',
  min: 0.25,
  max: 2,
  step: 0.05,
  default: 0.5,
  help: 'How much feeling goes into a line.',
  value: 0.7
}

describe('motor ayarlari', () => {
  it('kurulu motorun kaydiraci GORUNUYOR, degeriyle', async () => {
    catalog.mockResolvedValue(reply([item({ installed: true, knobs: [INTENSITY] })]))

    render(<VoiceSettings />)

    expect(await screen.findByText('Intensity')).toBeTruthy()
    expect((screen.getByRole('slider') as HTMLInputElement).value).toBe('0.7')
  })

  it('KURULU OLMAYAN motorda cikmiyor', async () => {
    // Kurulmamis bir motorun tonunu ayarlamak, hicbir seyi ayarlamamak.
    catalog.mockResolvedValue(
      reply([item({ engine_installed: false, installed: false, knobs: [INTENSITY] })])
    )

    render(<VoiceSettings />)

    await screen.findByText('Piper')
    expect(screen.queryByRole('slider')).toBeNull()
  })

  it('kolu OLMAYAN motorda bos alan birakmiyor', async () => {
    catalog.mockResolvedValue(reply([item({ installed: true, knobs: [] })]))

    render(<VoiceSettings />)

    await screen.findByText('Piper')
    expect(screen.queryByRole('slider')).toBeNull()
  })

  it('surukleme sirasinda YAZMIYOR, duraklayinca yaziyor', async () => {
    // Bir kaydirac surukleninken onlarca olay uretiyor; her birinde
    // yapilandirmaya yazmak tek surukleyisde elli kayit demekti.
    vi.useFakeTimers()

    try {
      catalog.mockResolvedValue(reply([item({ installed: true, knobs: [INTENSITY] })]))

      render(<VoiceSettings />)

      await vi.waitFor(() => expect(screen.queryByRole('slider')).toBeTruthy())

      const slider = screen.getByRole('slider')

      fireEvent.change(slider, { target: { value: '0.9' } })
      fireEvent.change(slider, { target: { value: '1.1' } })
      fireEvent.change(slider, { target: { value: '1.25' } })

      // Ekrandaki sayi ANINDA oynuyor.
      expect((slider as HTMLInputElement).value).toBe('1.25')
      expect(setKnob).not.toHaveBeenCalled()

      await vi.advanceTimersByTimeAsync(500)

      expect(setKnob).toHaveBeenCalledTimes(1)
      expect(setKnob).toHaveBeenCalledWith('piper', 'exaggeration', 1.25)
    } finally {
      vi.useRealTimers()
    }
  })

  it('yardim metni gorunuyor -- sayinin kendisi hicbir sey anlatmiyor', async () => {
    catalog.mockResolvedValue(reply([item({ installed: true, knobs: [INTENSITY] })]))

    render(<VoiceSettings />)

    expect(await screen.findByText('How much feeling goes into a line.')).toBeTruthy()
  })
})
