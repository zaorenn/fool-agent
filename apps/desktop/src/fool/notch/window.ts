/**
 * Notch penceresinin kimliği ve yaşam döngüsü.
 *
 * HUD ile AYNI sözleşme (``?win=hud``): pencere kendini sorgu dizesinden
 * tanıyor. Ayrı bir mekanizma icat etmemek kasıtlı — iki pencere türü aynı
 * şekilde çözülürse birinin bozulması diğerini de görünür kılar.
 *
 * Zone A: upstream bu dosyayı bilmiyor.
 */

let cache: boolean | null = null

/** Bu renderer notch penceresi mi? Pencerenin ömrü boyunca sabit. */
export function isNotchWindow(): boolean {
  if (cache !== null) {
    return cache
  }

  try {
    cache = new URLSearchParams(window.location.search).get('win') === 'notch'
  } catch {
    cache = false
  }

  return cache
}

/** Kabuk notch'u destekliyor mu (yalnızca masaüstü)? */
export const canUseNotch = (): boolean =>
  typeof window !== 'undefined' && typeof window.foolDesktop?.notch?.open === 'function'

export function openNotch(): void {
  window.foolDesktop?.notch?.open?.()
}

export function closeNotch(): void {
  window.foolDesktop?.notch?.close?.()
}

export const toggleNotch = (): void => {
  window.foolDesktop?.notch?.toggle?.()
}
