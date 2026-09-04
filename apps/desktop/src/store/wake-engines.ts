/**
 * Uyandırma motorları: katalog, seçim, KURULUM ve SINAMA.
 *
 * Neden ayrı bir depo
 * -------------------
 * ``wake-word.ts`` dinleyicinin CANLI durumunu tutuyor (armlı mı, duyuyor mu).
 * Burası ise bir AYARLAR yüzeyi: hangi motorlar var, hangisi kurulu, hangisi
 * yazılan ifadeyi dinleyebiliyor. İkisini karıştırmak, ayarlar ekranı kapalıyken
 * de katalog yoklamak olurdu.
 *
 * Kullanıcının iki kuralı burada birleşiyor:
 *
 *   * "o ayarlardaki neyse o sözcük wake wordümüz olmalı" -- gösterilen ifade
 *     ``effective_phrase``, ham yapılandırma alanı değil.
 *   * "senin manuel kurup çalıştırdığın her bir ayrı şey uygulamadan doğrudan
 *     indirilebilir olmalı ki yeni bilgisayarlarda da çalışsın" -- kurulum
 *     düğmesi ``wake.install`` işini başlatıyor.
 *
 * Zone A: upstream bu dosyayı bilmiyor.
 */

import { atom } from 'nanostores'

import { $gateway } from '@/store/gateway'
import { rearmWakeAfterConfigChange } from '@/store/wake-word'

export interface WakeEnginePhrase {
  model: string
  phrase: string
}

export interface WakeEngine {
  /** Bu motor şu an seçili mi. */
  active: boolean
  /** Kullanılamıyorsa SEBEBİ -- kullanıcıya olduğu gibi gösteriliyor. */
  blocked_reason: string
  /** Kullanıcının YAZDIĞI ifadeyi gerçekten dinleyebiliyor mu. */
  custom_phrase: boolean
  description: string
  env_key: string
  id: string
  installed: boolean
  label: string
  /** Sabit dağarcıklı motorun sunduğu ifadeler; boş = serbest ifade. */
  phrases: WakeEnginePhrase[]
  /** Kurulu VE çalıştırılabilir (anahtarı varsa o da yerinde). */
  usable: boolean
}

export interface WakeInstallJob {
  detail: string
  elapsed: number
  engine_id: string
  error: string
  id: string
  stage: string
  state: 'done' | 'failed' | 'running'
}

export type WakeTestState =
  | { phase: 'detected' }
  | { phase: 'failed'; reason: string }
  | { phase: 'idle' }
  | { phase: 'listening'; phrase: string; timeoutMs: number }
  | { phase: 'timeout' }

export interface WakeEnginesState {
  /** Motorun GERÇEKTEN dinlediği ifade. */
  effectivePhrase: string
  engines: WakeEngine[]
  /** Motor kimliğine göre süren kurulum işi. */
  installs: Record<string, WakeInstallJob>
  loaded: boolean
  notice: string
  test: WakeTestState
}

const INITIAL: WakeEnginesState = {
  effectivePhrase: '',
  engines: [],
  installs: {},
  loaded: false,
  notice: '',
  test: { phase: 'idle' }
}

export const $wakeEngines = atom<WakeEnginesState>(INITIAL)

/** Kurulum isteginin zaman asimi -- pip temiz bir makinede uzun surer. */
const WAKE_INSTALL_TIMEOUT_MS = 180_000

export type WakeRequester = <T>(method: string, params?: Record<string, unknown>) => Promise<T>

const gatewayRequester: WakeRequester = async <T>(method: string, params: Record<string, unknown> = {}) => {
  const gateway = $gateway.get()

  if (!gateway) {
    throw new Error('The Fool gateway unavailable')
  }

  // Kurulum pip calistiriyor ve temiz bir makinede dakikalar surebiliyor;
  // varsayilan 30 sn'lik zaman asimi kurulum ortasinda tetiklenir ve
  // kullanici basarili biten bir kurulumu "basarisiz" gorurdu.
  return method === 'wake.install'
    ? gateway.request<T>(method, params, WAKE_INSTALL_TIMEOUT_MS)
    : gateway.request<T>(method, params)
}

const patch = (next: Partial<WakeEnginesState>): void => {
  $wakeEngines.set({ ...$wakeEngines.get(), ...next })
}

const messageOf = (error: unknown): string => (error instanceof Error ? error.message : String(error))

/** Katalogu ağ geçidinden tazele. */
export async function loadWakeEngines(request: WakeRequester = gatewayRequester): Promise<void> {
  try {
    const result = await request<{ effective_phrase?: string; engines?: WakeEngine[] }>('wake.engines', {})

    patch({
      effectivePhrase: result?.effective_phrase?.trim() ?? '',
      engines: Array.isArray(result?.engines) ? result.engines : [],
      loaded: true,
      notice: ''
    })
  } catch (error) {
    // Eski bir arka uçta bu metot yok. Ayarlar ekranını karartmak yerine
    // sebebi yazıp boş bir katalogla devam ediyoruz.
    patch({ loaded: true, notice: messageOf(error) })
  }
}

/**
 * Motoru değiştir.
 *
 * Kapı ``usable``da, ``installed``da DEĞİL: Porcupine'in paketi kurulu olsa
 * bile anahtarı yoksa motor çalışmıyor ve seçilebilir görünmesi, kullanıcıyı
 * sessizce çalışmayan bir uyandırmaya götürürdü. Ağ geçidinde de aynı kapı
 * var -- arayüz kapısına güvenilmiyor.
 */
export async function setWakeEngine(engineId: string, request: WakeRequester = gatewayRequester): Promise<void> {
  const result = await request<{ effective_phrase?: string }>('wake.engine', { engine: engineId })

  patch({ effectivePhrase: result?.effective_phrase?.trim() ?? '' })

  // Dinleyici YENIDEN kuruluyor. Motor kurulumda cozumleniyor, yani bu
  // olmadan yapilandirma degisiyor ama kulak eski motorda kaliyor --
  // kullanicinin bildirdigi "hey hermes disindaki hicbiri calismiyor" tam
  // olarak buydu.
  await rearmWakeAfterConfigChange(request)
  await loadWakeEngines(request)
}

/** ``openwakeword``ün hazır ifadelerinden birini seç. */
export async function setWakeModel(model: string, request: WakeRequester = gatewayRequester): Promise<void> {
  const result = await request<{ effective_phrase?: string }>('wake.model', { model })

  patch({ effectivePhrase: result?.effective_phrase?.trim() ?? '' })

  await rearmWakeAfterConfigChange(request)
  await loadWakeEngines(request)
}

/** Yoklama aralığı: pip aşamaları saniyeler sürüyor, daha sık sormak boşuna. */
const POLL_MS = 900

/**
 * Motoru UYGULAMADAN kur.
 *
 * İş arka planda yürüyor ve burada yoklanıyor: temiz bir makinede pip birkaç
 * on saniye sürüyor ve tek bir isteği o kadar bekletmek uygulamayı donmuş
 * gösterirdi.
 */
export async function installWakeEngine(
  engineId: string,
  request: WakeRequester = gatewayRequester
): Promise<WakeInstallJob> {
  const job = await request<WakeInstallJob>('wake.install', { engine: engineId })

  patch({ installs: { ...$wakeEngines.get().installs, [engineId]: job } })

  let live = job

  while (live.state === 'running') {
    await new Promise<void>(resolve => setTimeout(resolve, POLL_MS))

    try {
      live = await request<WakeInstallJob>('wake.install_status', { job_id: job.id })
    } catch (error) {
      live = { ...live, error: messageOf(error), stage: 'failed', state: 'failed' }
    }

    patch({ installs: { ...$wakeEngines.get().installs, [engineId]: live } })
  }

  // Kurulum bitince katalog TAZELENIYOR: motor artık seçilebilir olmalı ve
  // kullanıcının bunu görmek için ayarları kapatıp açması gerekmemeli.
  await loadWakeEngines(request)

  return live
}

/** Sınamanın kendi kendine bitmesi için tanınan süre. */
export const WAKE_TEST_TIMEOUT_MS = 15_000

/**
 * Uyandırma sözcüğünü SINA.
 *
 * Sonuç bir OLAY olarak geliyor (``wake.test.result``), çünkü sınama kullanıcı
 * konuşana kadar sürüyor -- isteği o kadar bekletmek bir zaman aşımına
 * yakalanırdı. ``applyWakeTestResult`` olayı bu depoya bağlıyor.
 */
export async function startWakeTest(request: WakeRequester = gatewayRequester): Promise<void> {
  const phrase = $wakeEngines.get().effectivePhrase

  patch({ test: { phase: 'listening', phrase, timeoutMs: WAKE_TEST_TIMEOUT_MS } })

  try {
    const result = await request<{ phrase?: string; timeout_ms?: number }>('wake.test', {})

    patch({
      test: {
        phase: 'listening',
        phrase: result?.phrase?.trim() || phrase,
        timeoutMs: result?.timeout_ms ?? WAKE_TEST_TIMEOUT_MS
      }
    })
  } catch (error) {
    // En sık sebep: dinleyici kapalı. Mesaj ağ geçidinden geldiği gibi
    // gösteriliyor -- yalnızca "başarısız" demek, kullanıcıya sebebini
    // söylemiyor.
    patch({ test: { phase: 'failed', reason: messageOf(error) } })
  }
}

/** Süren sınamayı bırak (ayarlar kapandı ya da kullanıcı vazgeçti). */
export async function cancelWakeTest(request: WakeRequester = gatewayRequester): Promise<void> {
  patch({ test: { phase: 'idle' } })

  try {
    await request('wake.test_cancel', {})
  } catch {
    // Sunucuda zaten bitmiş olabilir; yerel durum şimdiden temiz.
  }
}

/** ``wake.test.result`` olayını depoya uygula. */
export function applyWakeTestResult(payload: unknown): void {
  const data = (payload ?? {}) as { cancelled?: boolean; detected?: boolean; timed_out?: boolean }

  if (data.cancelled) {
    patch({ test: { phase: 'idle' } })

    return
  }

  patch({ test: data.detected ? { phase: 'detected' } : { phase: 'timeout' } })
}

/** Sınama sonucunu başlangıç durumuna al. */
export function resetWakeTest(): void {
  patch({ test: { phase: 'idle' } })
}
