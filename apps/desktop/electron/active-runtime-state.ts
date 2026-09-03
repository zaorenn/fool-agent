export interface BootstrapMarkerLike {
  pinnedCommit?: unknown
  schemaVersion?: unknown
}

export interface ActiveRuntimeState {
  hasValidMarker: boolean
  shouldUseActiveRuntime: boolean
  usabilityReason: 'incomplete' | 'unusable' | 'usable'
}

export function hasValidBootstrapMarker(
  marker: BootstrapMarkerLike | null | undefined,
  schemaVersion: number
): boolean {
  if (!marker || typeof marker !== 'object') {
    return false
  }

  if (marker.schemaVersion !== schemaVersion) {
    return false
  }

  if (typeof marker.pinnedCommit !== 'string' || marker.pinnedCommit.length < 7) {
    return false
  }

  return true
}

// The active install at ~/.fool/hermes-agent can be real and runnable even if
// Desktop never wrote its first-run bootstrap marker (for example when The Fool
// was installed by the CLI first, or when a past desktop build forgot the
// marker). Runtime usability is authoritative for "can we launch local The Fool
// right now?"; the marker is only provenance about how that install was
// created. A missing/stale marker must never force a healthy local install into
// the first-run bootstrap UI.
export function classifyActiveRuntime(
  marker: BootstrapMarkerLike | null | undefined,
  schemaVersion: number,
  runtimeUsable: boolean,
  /**
   * Kurulum GERÇEKTEN bitmiş mi -- ``hermes-agent/bin`` içinde başlatıcılar
   * var mı. ``undefined`` verilirse eski davranış (yalnızca çalıştırılabilirlik)
   * korunuyor; sınavların çoğu bu soruyu sormuyor.
   */
  installComplete?: boolean
): ActiveRuntimeState {
  const hasValidMarker = hasValidBootstrapMarker(marker, schemaVersion)

  if (!runtimeUsable) {
    return {
      hasValidMarker,
      shouldUseActiveRuntime: false,
      usabilityReason: 'unusable'
    }
  }

  // YARIM kalmış kurulum: çalıştırılabilir ama BİTMEMİŞ.
  //
  // Ölçülen hâl (kullanıcının ikinci makinesi): ``%LOCALAPPDATA%\fool``
  // kalıntısı Denetim Masası'ndan kaldırmaya rağmen duruyor, ``fool_cli`` içe
  // aktarılabiliyor -- yani "kullanılabilir" -- ama ``fool`` komutu PATH'te yok,
  // yapılandırma yazılmamış, kurulum hiç bitmemiş. Eski kural bunu görüp
  // kurulum ekranını ATLIYOR, uygulama bozuk kurulumla açılıyor, ve YENİDEN
  // KURMAK da düzeltmiyor: aynı kalıntı aynı dalı tetikliyor. Kullanıcı bu
  // duruma kilitleniyor ve çıkış yolu yok.
  //
  // İşaret yoksa ve başlatıcılar da yoksa bu bir kurulum değil, kalıntı.
  if (installComplete === false && !hasValidMarker) {
    return {
      hasValidMarker,
      shouldUseActiveRuntime: false,
      usabilityReason: 'incomplete'
    }
  }

  return {
    hasValidMarker,
    shouldUseActiveRuntime: true,
    usabilityReason: 'usable'
  }
}
