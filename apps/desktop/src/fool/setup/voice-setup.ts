/**
 * Kurulumda sesi indirme kararları — React'ten ayrı.
 *
 * İstenen: "kullanıcı direkt olarak ilk mesajını atabilmeli ya da direkt
 * olarak ses modellerini indirebilmeli, TTS ve STT'yi, ve indirmenin durumunu
 * görebilmeli."
 *
 * Bugün ses yalnızca Ayarlar > Voice'ta kuruluyor: yeni kullanıcı uygulamayı
 * açıyor, konuşmayı deniyor ve hiçbir şey olmuyor -- çünkü indirilecek bir şey
 * olduğunu hiçbir yerde görmedi.
 *
 * Buradaki her şey saf: hangi motorlar önerilir, ilerleme nasıl birleşir,
 * adım ne zaman biter. Pencere açmadan sınanabilmesi için.
 *
 * Zone A: upstream bu dosyayı bilmiyor.
 */

import type { VoiceItem, VoiceJob } from '../voice-api'

export type VoiceSetupState = 'idle' | 'installing' | 'ready' | 'failed'

/**
 * Kurulumda önerilecek TEK STT ve TEK TTS.
 *
 * Seçim katalogdan geliyor (``recommended``), elle yazılmıyor: önerilen motor
 * değiştiğinde kurulum ekranının eskimesi, kullanıcıyı ilk dakikasında yanlış
 * modele sokmak olurdu.
 *
 * Kurulu olan varsa O seçiliyor -- zaten diskte duran 1,3 GB'ı tekrar
 * indirtmek, "bir kaç tıkla hallolsun" isteğinin tam tersi.
 */
export function recommendedPair(items: VoiceItem[]): VoiceItem[] {
  const pick = (kind: 'stt' | 'tts') => {
    const ofKind = items.filter(item => item.kind === kind)

    return (
      ofKind.find(item => item.active && item.installed) ??
      ofKind.find(item => item.installed) ??
      ofKind.find(item => item.recommended) ??
      ofKind[0] ??
      null
    )
  }

  return [pick('stt'), pick('tts')].filter((item): item is VoiceItem => item !== null)
}

/** Bu öğe için gösterilecek iş (yoksa ``null``). */
export function jobFor(item: VoiceItem, jobs: Record<string, VoiceJob | null>): VoiceJob | null {
  return jobs[item.id] ?? item.job ?? null
}

/**
 * İki indirmenin BİRLEŞİK yüzdesi.
 *
 * Kurulu olan %100 sayılıyor: kullanıcının gördüğü çubuk "ne kadar kaldı"
 * sorusunu cevaplamalı, "şu an kaç iş koşuyor" sorusunu değil.
 */
export function overallPercent(items: VoiceItem[], jobs: Record<string, VoiceJob | null>): number {
  if (items.length === 0) {
    return 0
  }

  const total = items.reduce((sum, item) => {
    if (item.installed) {
      return sum + 100
    }

    const job = jobFor(item, jobs)

    return sum + (job?.state === 'done' ? 100 : Math.max(0, Math.min(100, job?.percent ?? 0)))
  }, 0)

  return Math.round(total / items.length)
}

/**
 * Adımın durumu.
 *
 * ``failed`` yalnızca DENENMİŞ ve düşmüş bir iş varken: hiç denenmemiş bir
 * kurulumu "başarısız" göstermek, kullanıcıya olmayan bir hatayı bildirmek
 * olurdu.
 */
export function setupState(items: VoiceItem[], jobs: Record<string, VoiceJob | null>): VoiceSetupState {
  if (items.length === 0) {
    return 'idle'
  }

  const states = items.map(item => (item.installed ? 'done' : jobFor(item, jobs)?.state ?? null))

  if (states.some(state => state === 'failed')) {
    return 'failed'
  }

  if (states.some(state => state === 'running')) {
    return 'installing'
  }

  return states.every(state => state === 'done') ? 'ready' : 'idle'
}

/** Hangi öğeler GERÇEKTEN indirilecek -- kurulu olan atlanıyor. */
export function pendingInstalls(items: VoiceItem[]): VoiceItem[] {
  return items.filter(item => !item.installed)
}

/**
 * Bu öğe CUDA ile mi kurulsun?
 *
 * Karar burada çünkü kurulum ekranında kullanıcıya CPU/CUDA sormak, "bir kaç
 * tıkla hallolsun" isteğini bozar. Kart varsa ve motor kullanabiliyorsa CUDA;
 * yoksa CPU. Yanlış tarafa düşerse sonuç yavaş bir motor, bozuk bir motor
 * değil -- ve aygıt Ayarlar'dan sonradan değiştirilebiliyor.
 */
export function installDevice(item: VoiceItem, cudaAvailable: boolean): 'cpu' | 'cuda' {
  return cudaAvailable && item.devices.includes('cuda') ? 'cuda' : 'cpu'
}
