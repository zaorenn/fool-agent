/**
 * Notch kısayolunu Electron'un anladığı biçime çevir.
 *
 * Neden ayrı bir dosya
 * --------------------
 * Yakalama tarayıcıda oluyor (``KeyboardEvent``), kayıt ana süreçte
 * (``globalShortcut.register``) ve ikisinin sözlüğü farklı: tarayıcı
 * ``ControlLeft`` / ``KeyV`` diyor, Electron ``CommandOrControl+Alt+V``
 * bekliyor. Çeviriyi kayıt yerinde yapmak, saf olarak sınanamayan bir yere
 * gömmek olurdu.
 *
 * ``CommandOrControl`` bilinçli: aynı ayar macOS'ta Command, Windows ve
 * Linux'ta Control olarak kaydolsun.
 *
 * Zone A: upstream bu dosyayı bilmiyor.
 */

/** Tek başına bir kısayol olamayacak tuşlar. */
const MODIFIER_CODES = new Set([
  'AltLeft',
  'AltRight',
  'ControlLeft',
  'ControlRight',
  'MetaLeft',
  'MetaRight',
  'ShiftLeft',
  'ShiftRight'
])

export interface AcceleratorInput {
  alt: boolean
  /** ``KeyboardEvent.code`` -- fiziksel tuş, klavye düzeninden etkilenmez. */
  code: string
  ctrl: boolean
  meta: boolean
  shift: boolean
}

/**
 * Ana tuşu Electron'un adına çevir ("" = kullanılamaz).
 *
 * Bilinmeyen bir ``code``u olduğu gibi geçirmek yanlış olurdu: Electron onu
 * reddeder ve kullanıcı ayarın neden uygulanmadığını göremez.
 */
export function acceleratorKey(code: string): string {
  if (/^Key[A-Z]$/.test(code)) {
    return code.slice(3)
  }

  if (/^Digit[0-9]$/.test(code)) {
    return code.slice(5)
  }

  if (/^F([1-9]|1[0-9]|2[0-4])$/.test(code)) {
    return code
  }

  const named: Record<string, string> = {
    ArrowDown: 'Down',
    ArrowLeft: 'Left',
    ArrowRight: 'Right',
    ArrowUp: 'Up',
    Backquote: '`',
    Backslash: '\\',
    BracketLeft: '[',
    BracketRight: ']',
    Comma: ',',
    Equal: '=',
    Minus: '-',
    Period: '.',
    Quote: "'",
    Semicolon: ';',
    Slash: '/',
    Space: 'Space',
    Tab: 'Tab'
  }

  return named[code] ?? ''
}

/**
 * Basılan tuş bileşimini hızlandırıcıya çevir ("" = geçersiz).
 *
 * DEĞİŞTİRİCİ ŞART: değiştiricisiz bir global kısayol her uygulamada o tuşu
 * çalar -- kullanıcı bir metin kutusuna ``v`` yazamaz hale gelirdi. Tek
 * istisna işlev tuşları; onlar zaten tek başına ayrılmış sayılıyor.
 */
export function toAccelerator(input: AcceleratorInput): string {
  if (MODIFIER_CODES.has(input.code)) {
    return ''
  }

  const key = acceleratorKey(input.code)

  if (!key) {
    return ''
  }

  const parts: string[] = []

  if (input.ctrl || input.meta) {
    parts.push('CommandOrControl')
  }

  if (input.alt) {
    parts.push('Alt')
  }

  if (input.shift) {
    parts.push('Shift')
  }

  const isFunctionKey = /^F([1-9]|1[0-9]|2[0-4])$/.test(key)

  if (parts.length === 0 && !isFunctionKey) {
    return ''
  }

  parts.push(key)

  return parts.join('+')
}

/** Kullanıcıya gösterilecek biçim. */
export function formatAccelerator(accelerator: string): string {
  if (!accelerator) {
    return 'Not set'
  }

  return accelerator
    .replace('CommandOrControl', navigator.platform.startsWith('Mac') ? 'Cmd' : 'Ctrl')
    .split('+')
    .join(' + ')
}

/** Uygulamanın istediği varsayılan -- kullanıcının açıkça belirttiği tuş. */
export const DEFAULT_NOTCH_SHORTCUT = 'CommandOrControl+Alt+V'
