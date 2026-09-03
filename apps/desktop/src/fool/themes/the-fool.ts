/**
 * The Fool — crimson kimlik teması.
 *
 * Bölge A: upstream bu dosyayı bilmez, çakışma imkânsız. `presets.ts` içine
 * tek satırlık bir dikişle (FOOL-SEAM: theme-preset) kaydedilir.
 *
 * Palet karanlık-öncelikli tasarlandı: uygulamanın açılış ekranı koyu ve
 * wordmark `mix-blend-plus-lighter` ile karışıyor, bu yüzden crimson'ın
 * koyu zeminde doygun ama gözü yormayan bir tonu seçildi.
 */

import type { DesktopTheme } from '../../themes/types'

/** Ana crimson — logo, odak halkaları, aktif oturum vurguları. */
const CRIMSON = '#D01A3F'
/** Koyu temada biraz açılmış crimson: koyu zeminde kontrastı korur. */
const CRIMSON_LIFT = '#E8365A'
/** Derin şarap tonu — koyu yüzeylerin altına kayan sıcaklık. */
const WINE = '#4A0A18'

const tint = (pct: number) => `color-mix(in srgb, ${CRIMSON} ${pct}%, #FFFFFF)`
const tintTransparent = (pct: number) => `color-mix(in srgb, ${CRIMSON} ${pct}%, transparent)`
const liftTransparent = (pct: number) => `color-mix(in srgb, ${CRIMSON_LIFT} ${pct}%, transparent)`

export const theFoolTheme: DesktopTheme = {
  name: 'the-fool',
  label: 'The Fool',
  description: 'Crimson accents over deep neutrals — The Fool identity',

  // Açık varyant: kâğıt beyazı zemin, crimson vurgu.
  colors: {
    background: '#FBF8F8',
    foreground: '#1A1416',
    card: '#FFFFFF',
    cardForeground: '#1A1416',
    muted: tint(5),
    mutedForeground: '#6E5A60',
    popover: '#FFFFFF',
    popoverForeground: '#1A1416',
    primary: CRIMSON,
    primaryForeground: '#FFFAFB',
    secondary: tint(8),
    secondaryForeground: '#2A1D21',
    accent: tint(12),
    accentForeground: '#241A1D',
    border: tintTransparent(20),
    input: tintTransparent(28),
    ring: CRIMSON,
    midground: CRIMSON,
    composerRing: CRIMSON,
    destructive: '#B3261E',
    destructiveForeground: '#FFFFFF',
    sidebarBackground: '#F6EFF1',
    sidebarBorder: tintTransparent(16),
    userBubble: tint(10),
    userBubbleBorder: tintTransparent(24)
  },

  // Koyu varyant: uygulamanın asıl yüzü.
  darkColors: {
    background: '#100B0D',
    foreground: '#F2E9EC',
    card: '#181114',
    cardForeground: '#F2E9EC',
    muted: '#1F1619',
    mutedForeground: '#A08A91',
    popover: '#181114',
    popoverForeground: '#F2E9EC',
    primary: CRIMSON_LIFT,
    primaryForeground: '#12090C',
    secondary: '#241A1E',
    secondaryForeground: '#EFE2E6',
    accent: WINE,
    accentForeground: '#FFE8ED',
    border: liftTransparent(24),
    input: liftTransparent(32),
    ring: CRIMSON_LIFT,
    midground: CRIMSON_LIFT,
    composerRing: CRIMSON_LIFT,
    destructive: '#F2545B',
    destructiveForeground: '#1A0509',
    sidebarBackground: '#0C0809',
    sidebarBorder: liftTransparent(18),
    userBubble: '#241A1E',
    userBubbleBorder: liftTransparent(28)
  },

  // Terminal ANSI paleti — crimson ailesiyle uyumlu.
  darkTerminal: {
    foreground: '#F2E9EC',
    cursor: CRIMSON_LIFT,
    selectionBackground: liftTransparent(30)
  }
}
