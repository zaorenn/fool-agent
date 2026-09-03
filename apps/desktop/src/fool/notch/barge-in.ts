/**
 * Notch turunda araya girme (barge-in) kapısı — saf, DOM'suz, sınanabilir.
 *
 * Neden ayrı bir kapı gerekiyor
 * ------------------------------
 * Ajan konuşurken kullanıcının araya girmesinin İKİ yolu var ve ikisi de aynı
 * anda gerçekleşebiliyor:
 *
 *   1. Sağ Ctrl'ye basmak (bas-konuş).
 *   2. Sadece konuşmaya başlamak — ``lib/voice-barge-in.ts`` mikrofonu tur
 *      boyunca izliyor, sürekli konuşmayı yakalayınca oynatmayı kesiyor ve
 *      söylenen cümleyi ÖN KAYITLA birlikte teslim ediyor.
 *
 * İnsan konuşmasında bu ikisi tam olarak birlikte olur: kullanıcı konuşmaya
 * başlarken refleksle tuşa da basar. Kapı olmadan sonuç iki ayrı gönderim
 * oluyor — aynı cümle modele iki kez gidiyor ve ikinci tur birincinin cevabını
 * yarıda kesiyor. Sessiz sınıftan: hata yok, sadece ajan kendi kendine
 * konuşuyor.
 *
 * Kapı turu ilk talep edene veriyor. İkinci talep sahibi ``false`` alıyor ve
 * hiçbir şey yapmıyor.
 *
 * Zone A: upstream bu dosyayı bilmiyor.
 */

import type { NotchStatus } from './use-notch-voice'

/**
 * İzleyicinin ilgilendiği evreler.
 *
 * Notch ``NotchStatus``, Friend penceresi ``OrbPhase`` kullanıyor ve ikisinin
 * adları çakışıyor (``thinking`` / ``speaking``). Ortak tip bu: iki yüzey de
 * AYNI kapıyı çağırsın diye. Friend'in kendi satır içi kopyası vardı ve
 * kopyalar ayrışır -- burada ayrışmanın bedeli, bir yüzeyde araya girmenin
 * sessizce ölmesi.
 */
export type VoiceTurnPhase = NotchStatus | 'idle' | 'listening' | 'speaking' | 'thinking'

/** Turu kimin talep ettiği. */
export type BargeClaimant = 'key' | 'voice'

export interface BargeGate {
  claimedBy: BargeClaimant | null
}

export const createBargeGate = (): BargeGate => ({ claimedBy: null })

/**
 * Turu talep et.
 *
 * İlk çağıran ``true`` alır. Aynı talep sahibi tekrar çağırırsa yine ``true``
 * alır — tuş tekrarı ya da art arda gelen VAD olayı yüzünden kullanıcının
 * kendi girişimi kendini engellemesin diye.
 */
export function claimBarge(gate: BargeGate, who: BargeClaimant): boolean {
  if (gate.claimedBy !== null && gate.claimedBy !== who) {
    return false
  }

  gate.claimedBy = who

  return true
}

/**
 * Turu ZORLA talep et.
 *
 * Açık kullanıcı eylemi — sağ Ctrl'ye basmak — her zaman kazanır. Sesle
 * yakalama yarım saniye önce başlamış olabilir; kullanıcı buna rağmen tuşa
 * bastıysa niyeti nettir ve kaydı kendisi yönetmek istiyordur. Kapıyı ilk
 * gelene bırakmak burada tuşu sessizce yutardı: mikrofon açılmaz, kullanıcı
 * boşluğa konuşur.
 */
export function forceClaimBarge(gate: BargeGate, who: BargeClaimant): void {
  gate.claimedBy = who
}

/** Tur bitti (ya da iptal edildi) — kapıyı serbest bırak. */
export function releaseBarge(gate: BargeGate): void {
  gate.claimedBy = null
}

/**
 * Mikrofon izleyicisi hangi durumlarda açık olmalı?
 *
 * ``thinking`` DE dahil, ``speaking`` ile birlikte: model cevabı üretirken
 * 1-3 saniye tam sessizlik oluyor ve kullanıcı çoğu zaman tam o boşlukta
 * fikrini değiştirip konuşuyor. Yalnızca oynatma sırasında izlemek o araya
 * girmeyi tamamen kaçırıyordu.
 *
 * ``listening`` sırasında KAPALI: mikrofon zaten kaydediyor, ikinci bir
 * ``getUserMedia`` akışı açmak Windows'ta kaydı bozuyor.
 */
export function shouldMonitorBargeIn(status: VoiceTurnPhase): boolean {
  return status === 'thinking' || status === 'speaking'
}

/**
 * TTS sesi ŞU AN akıyor mu?
 *
 * İzleyicinin evre farkındalığını bu besliyor: gürültü tabanı yalnızca sessiz
 * evrede ölçülüyor, oynatma sırasında tetik eşiği hoparlör sızıntısının
 * altında kalmasın diye yukarı kenetleniyor.
 */
export function isPlayingPhase(status: VoiceTurnPhase): boolean {
  return status === 'speaking'
}
