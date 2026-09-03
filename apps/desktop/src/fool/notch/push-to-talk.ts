/**
 * Bas-konuş tuş mantığı — saf, DOM'suz, sınanabilir.
 *
 * Neden ayrı ve saf
 * -----------------
 * Bu mantığın kaçırdığı tek bir ``keyup`` mikrofonu sonsuza kadar açık bırakır:
 * kullanıcı tuşu bıraktığını sanır, notch dinlemeye devam eder ve kaydedilen
 * her şey bir sonraki mesaja karışır. Sessiz ve kötü bir hata. Bu yüzden karar
 * verme React'ten ayrıldı ve doğrudan sınanıyor.
 *
 * Kaçırılan keyup'ın üç gerçek yolu var ve üçü de burada karşılanıyor:
 *
 * 1. **Pencere odağı kaybediyor.** Alt-Tab basılıyken tuş bırakılırsa keyup
 *    başka uygulamaya gider; bize hiç gelmez. ``blur`` bu yüzden bırakma
 *    sayılıyor.
 * 2. **Tuş tekrarı.** Basılı tutulan tuş art arda ``keydown`` üretir; her biri
 *    yeni bir kayıt başlatsaydı ilk hece kaybolurdu. Tekrarlar yutuluyor.
 * 3. **Değiştirici tuş bırakma sırası.** Sağ Ctrl bırakıldığında bazı
 *    düzenlerde ``key`` alanı farklı gelebiliyor; eşleştirme ``code`` üzerinden
 *    yapılıyor (``ControlRight``), çünkü o fiziksel tuşu gösterir ve klavye
 *    düzeninden etkilenmez.
 */

import { bindingMatches, DEFAULT_PTT_CODE, parsePttBinding } from './ptt-binding'

/**
 * Bas-konuş için varsayılan fiziksel tuş: sağ Ctrl.
 *
 * ``DEFAULT_PTT_CODE``ten TÜRETİLİYOR, ikinci bir sabit değil: iki yerde ayrı
 * yazılan aynı varsayılan, biri değiştiğinde sessizce ayrışır ve hangisinin
 * canlı olduğu görünmez.
 */
export const PUSH_TO_TALK_CODE = DEFAULT_PTT_CODE

/** Bu süreden kısa basışlar yanlışlıkla dokunma sayılır ve gönderilmez. */
export const MIN_HOLD_MS = 180

/**
 * Bu süreden uzun süren bir "basılı" kaydı BAYAT sayılıyor.
 *
 * Ölçülen hata: ``heldSince`` yalnızca ``keyup`` ile temizleniyordu. Notch
 * odağı kaybettiğinde ``keyup`` ARTIK BİZE GELMİYOR -- o olay odağı alan
 * uygulamaya gidiyor. Bayrak takılı kalıyor ve sonraki HER ``keydown``
 * ``null`` dönüyor: kullanıcının gördüğü "sağ ctrl bir kez çalışıyor,
 * sonrasında işe yaramaz hale geliyor".
 *
 * ``blur`` dinleyicisi bu durumu yakalamak için vardı ama her yolu
 * kapatmıyor: pencere hiç odak almamışsa ya da odak Electron'un ``blur``
 * olayını tetiklemeden gittiyse bayrak orada kalıyor.
 *
 * Kimse tuşu 30 saniye basılı tutmuyor. O süreyi geçmiş bir kayıt kaybolmuş
 * bir ``keyup``tır; yeni basış TAZE sayılır.
 */
export const STALE_HOLD_MS = 30_000

export type PushToTalkEvent =
  | { type: 'start' }
  /** Tuş yeterince uzun tutuldu — kaydı gönder. */
  | { type: 'commit'; heldMs: number }
  /** Çok kısa basıldı ya da odak kaybedildi — kaydı at, gönderme. */
  | { type: 'cancel'; reason: 'too-short' | 'blur' }

export interface PushToTalkState {
  heldSince: null | number
}

export function createPushToTalkState(): PushToTalkState {
  return { heldSince: null }
}

export interface KeyLike {
  code: string
  /** Tuş tekrarı mı? Basılı tutuş art arda keydown üretir. */
  repeat?: boolean
  // Değiştiriciler kombo bağlamalar için (``Shift+ControlRight``). İSTEĞE
  // BAĞLI: değiştiricisiz bir bağlamada hiç okunmuyorlar ve ``undefined``
  // "basılı değil" sayılıyor -- ana süreçten iletilen sentetik olay bu
  // alanları taşımadığında eşleşme sessizce bozulmasın diye.
  altKey?: boolean
  ctrlKey?: boolean
  metaKey?: boolean
  shiftKey?: boolean
}

/**
 * Tuşa basıldı.
 *
 * Zaten basılıysa ya da tekrar ise ``null`` döner — çağıran hiçbir şey yapmaz.
 */
export function onKeyDown(
  state: PushToTalkState,
  event: KeyLike,
  now: number,
  binding: string = PUSH_TO_TALK_CODE
): null | PushToTalkEvent {
  if (!bindingMatches(parsePttBinding(binding), event) || event.repeat) {
    return null
  }

  if (state.heldSince !== null) {
    if (now - state.heldSince < STALE_HOLD_MS) {
      // Gerçekten basılı. İkinci bir 'start' kaydı sıfırlar ve ilk heceyi yer.
      return null
    }

    // Bayat: ``keyup`` kaybolmuş. Yeni basış taze sayılıyor -- aksi hâlde
    // bas-konuş bir daha hiç açılmaz.
    state.heldSince = null
  }

  state.heldSince = now

  return { type: 'start' }
}

/** Tuş bırakıldı. Kısa basış gönderilmez — yanlışlıkla dokunma. */
export function onKeyUp(
  state: PushToTalkState,
  event: KeyLike,
  now: number,
  binding: string = PUSH_TO_TALK_CODE
): null | PushToTalkEvent {
  // BIRAKMA yalnizca ``code``a bakiyor -- degistiricilere DEGIL, ve bu bilerek.
  //
  // ``Shift+ControlRight`` bagliyken kullanici tuslari SIRAYLA birakiyor. Once
  // Shift birakilirsa ControlRight'in ``keyup``i ``shiftKey: false`` ile
  // geliyor: tam eslesme istemek o olayi ELERDI, ``heldSince`` takili kalirdi
  // ve mikrofon sonsuza kadar acik kalirdi -- bu dosyanin var olma sebebi olan
  // hatanin ta kendisi. Basis zaten tam eslesmeden gecti; birakmayi kacirmak
  // hicbir seyi guvenli yapmiyor.
  if (event.code !== parsePttBinding(binding).code || state.heldSince === null) {
    return null
  }

  const heldMs = now - state.heldSince
  state.heldSince = null

  return heldMs < MIN_HOLD_MS ? { type: 'cancel', reason: 'too-short' } : { type: 'commit', heldMs }
}

/**
 * Pencere odağı kaybetti.
 *
 * Tuş hâlâ basılı olabilir ama ``keyup`` artık BİZE gelmeyecek — o olay odağı
 * alan uygulamaya gider. Basılı sayılmaya devam etmek mikrofonu sonsuza kadar
 * açık bırakırdı, o yüzden bu bir iptal.
 */
export function onBlur(state: PushToTalkState): null | PushToTalkEvent {
  if (state.heldSince === null) {
    return null
  }

  state.heldSince = null

  return { type: 'cancel', reason: 'blur' }
}

export const isHolding = (state: PushToTalkState): boolean => state.heldSince !== null
