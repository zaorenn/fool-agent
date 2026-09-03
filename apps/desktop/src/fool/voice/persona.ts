/**
 * Persona: sesin KİMLİĞİ ve uygulamanın rengi tek seçim.
 *
 * Neden birlikte
 * --------------
 * Ses ile renk aynı şeyin iki yüzü. Kullanıcının isteği birebir buydu: "kızdan
 * erkek sesine geçince vurgu rengi de değişsin". Ayrı iki ayar olsaydı ikisi
 * ayrışırdı ve panel bir kimlik gösterip başka bir kimlik konuşurdu -- bu
 * kod tabanında zaten yaşanmış bir hata (bkz. ``FOOL-SEAM: one-voice``).
 *
 * Eşleştirme TAHMİN DEĞİL
 * -----------------------
 * Motorların ses listeleri gerçek ve okunabilir. Ölçüldü:
 *
 *   kokoro     af_heart / af_bella / af_nicole / am_michael / am_puck /
 *              bf_emma / bm_george        -- ikinci harf cinsiyet (f/m)
 *   qwen3-tts  ryan / serena / aiden / dylan / eric / vivian / ...
 *              -- etiketler "male"/"female" diyor
 *   piper / styletts2 / chatterbox        -- TEK ses, seçim yok
 *   kyutai     expresso konuşmacı dosyaları -- cinsiyet kodlanmamış
 *
 * Yani eşleştirici önce ETİKETE, sonra kokoro'nun kimlik kuralına bakıyor.
 * Hiçbiri tutmuyorsa persona sesi DEĞİŞTİRMİYOR ve arayüz bunu söylüyor --
 * sessizce yanlış bir ses seçmek, kullanıcının duyduğu ile gördüğünün
 * ayrışması olurdu.
 *
 * Zone A: upstream bu dosyayı bilmiyor.
 */

import type { VoiceItem } from '../voice-api'

export type PersonaId = 'ember' | 'frost' | 'iris' | 'slate'

export interface Persona {
  id: PersonaId
  /** Kullanıcıya görünen ad (İngilizce). */
  label: string
  /** Tek cümlelik karakter. */
  summary: string
  /** Uygulamanın vurgu rengi. */
  accent: string
  /** Aradığı ses karakteri; sırayla denenen ipuçları. */
  hints: string[]
}

/**
 * Renkler tema paletinden TÜRETİLMİYOR, kasten.
 *
 * Her biri kendi başına bir kimlik: koyu zeminde okunaklı, açık zeminde
 * boğulmayan doygunlukta. Tema crimson kalıyor; persona yalnızca vurguyu
 * alıyor, yani seçim geri alınabilir ve uygulamanın karakterini bozmuyor.
 */
export const PERSONAS: Persona[] = [
  {
    accent: '#E8365A',
    hints: ['female - warm', 'warm female', 'female'],
    id: 'ember',
    label: 'Ember',
    summary: 'Warm, close. The default.'
  },
  {
    accent: '#3B82F6',
    hints: ['male - even', 'even male', 'male'],
    id: 'slate',
    label: 'Slate',
    summary: 'Even and grounded.'
  },
  {
    accent: '#14B8A6',
    hints: ['female - clear', 'clear female', 'british female', 'female'],
    id: 'frost',
    label: 'Frost',
    summary: 'Clear and precise.'
  },
  {
    accent: '#A855F7',
    hints: ['male - lively', 'young male', 'lively', 'male'],
    id: 'iris',
    label: 'Iris',
    summary: 'Bright and quick.'
  }
]

export function persona(id: string): Persona | null {
  return PERSONAS.find(entry => entry.id === id) ?? null
}

/** Kokoro kimlik kuralı: ``af_``/``bf_`` kadın, ``am_``/``bm_`` erkek. */
function genderFromKokoroId(voiceId: string): 'female' | 'male' | null {
  const match = /^[ab]([fm])_/.exec(voiceId.trim().toLowerCase())

  if (!match) {
    return null
  }

  return match[1] === 'f' ? 'female' : 'male'
}

/**
 * Bu personaya en uygun ses ("" = motorun uygun bir sesi yok).
 *
 * Boş dönmek BAŞARISIZLIK DEĞİL, doğru cevap: Piper'ın tek sesi var ve onu
 * "erkek sesi" diye sunmak yalan olurdu.
 */
export function voiceForPersona(entry: Persona, voices: { id: string; label: string }[]): string {
  if (voices.length < 2) {
    return ''
  }

  const rows = voices.map(voice => ({
    gender: genderFromKokoroId(voice.id),
    id: voice.id,
    text: `${voice.label} ${voice.id}`.toLowerCase()
  }))

  // 1. Etiket eslesmesi, en OZGUL ipucundan baslayarak.
  for (const hint of entry.hints) {
    const found = rows.find(row => row.text.includes(hint))

    if (found) {
      return found.id
    }
  }

  // 2. Kokoro kimlik kurali: etiket dili degisse bile kimlik degismiyor.
  const wanted = entry.hints.some(hint => hint.includes('female')) ? 'female' : 'male'
  const byId = rows.find(row => row.gender === wanted)

  return byId?.id ?? ''
}

/** Seçili motorda bu persona sesi gerçekten değiştirebiliyor mu? */
export function canChangeVoice(item: null | VoiceItem): boolean {
  return (item?.voices?.length ?? 0) > 1
}

/**
 * Vurgu rengini uygula.
 *
 * ``documentElement`` üzerine satır içi yazılıyor: stil sayfasındaki tanımı
 * ezer ve geri almak tek ``removeProperty``. Temanın kendi değişkenlerine
 * dokunmuyor, yani persona seçimi temayı BOZMUYOR.
 */
export function applyAccent(accent: string): void {
  if (typeof document === 'undefined') {
    return
  }

  const root = document.documentElement

  if (!accent) {
    root.style.removeProperty('--theme-primary')
    root.style.removeProperty('--theme-ring')

    return
  }

  root.style.setProperty('--theme-primary', accent)
  root.style.setProperty('--theme-ring', accent)
}

/** Seçili personanın kalıcı hâli. */
const STORAGE_KEY = 'fool.desktop.friend.persona'

/**
 * Kalıcılık ``localStorage``a DOĞRUDAN yazılıyor, bir atom üzerinden değil.
 *
 * Değer tek bir dizeden ibaret ve okuyanı tek: açılışta rengi uygulayan
 * efekt. Bunun için ayrı bir depo kurmak, okuyanı olmayan bir soyutlama
 * eklemek olurdu.
 */
export function readAccent(): string {
  try {
    return window.localStorage.getItem(STORAGE_KEY) ?? ''
  } catch {
    return ''
  }
}

export function persistAccent(id: string): void {
  try {
    if (id) {
      window.localStorage.setItem(STORAGE_KEY, id)
    } else {
      window.localStorage.removeItem(STORAGE_KEY)
    }
  } catch {
    // Kalıcılık yoksa persona yine çalışıyor, yalnızca yeniden açılışta
    // varsayılana dönüyor. Bunun için kullanıcıya hata göstermek oransız.
  }
}

/**
 * KONUŞAN motorun ve sesin tek satırlık özeti.
 *
 * Kullanıcının bildirdiği hâl: "şuan uygulamada duyduğum ses kadın." Sebebi
 * yapılandırmada açıkça duruyordu -- ``provider: kokoro``, ``voice: bf_emma``
 * (İngiliz kadın sesi) -- ama arayüzde HİÇBİR YERDE yazmıyordu. Persona
 * seçicisi renkleri gösteriyor, hangi sesin konuştuğunu söylemiyordu.
 */
export function speakingSummary(engine: null | VoiceItem): string {
  if (!engine) {
    return ''
  }

  if (engine.clone) {
    return `${engine.label} — cloned voice "${engine.clone}"`
  }

  const voice = engine.voices.find(entry => entry.id === engine.voice)

  return voice ? `${engine.label} — ${voice.label}` : engine.label
}

/**
 * Klon BAŞKA bir motorda duruyorsa onu döndür (``null`` = yok).
 *
 * Ölçülen hata: kullanıcı Ultron sesini chatterbox'a klonladı ama konuşan
 * motor kokoro'ydu. Klon diskte, yapılandırmada, panelde -- ama hiç
 * duyulmuyor. Persona seçicisi yalnızca AKTİF motorun ses listesinde arama
 * yapıyor ve motor değiştirmiyor, yani o klona ulaşmanın seçiciden hiçbir
 * yolu yoktu.
 *
 * Sessizce motor değiştirmek yanlış cevap olurdu: kullanıcı hızlı bir motor
 * seçmiş olabilir (ölçüldü, kokoro 200 ms / chatterbox 1894 ms). Doğru cevap
 * durumu SÖYLEMEK ve geçişi bir tıka indirmek.
 */
export function idleClone(items: VoiceItem[]): null | VoiceItem {
  return (
    items.find(item => item.kind === 'tts' && item.installed && !item.active && Boolean(item.clone)) ??
    null
  )
}
