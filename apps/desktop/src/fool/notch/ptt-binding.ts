/**
 * Bas-konuş tuşunun bağlanması — saf, DOM'suz, sınanabilir.
 *
 * Neden atanabilir olmalı
 * -----------------------
 * Varsayılan sağ Ctrl çoğu makinede boş, ama hepsinde değil: bazı dizüstülerde
 * sağ Ctrl fiziksel olarak yok (Fn ya da menü tuşu yerini almış), bazı
 * kullanıcılar onu IME değiştirmeye ya da ekran okuyucuya bağlamış durumda.
 * O makinelerde bas-konuş HİÇ çalışmıyor ve sebebi görünmüyor — kullanıcı
 * notch'u açık görüp konuşuyor, hiçbir şey olmuyor.
 *
 * Neden ``code``, ``key`` değil
 * -----------------------------
 * ``code`` FİZİKSEL tuşu gösterir ve klavye düzeninden etkilenmez. ``key``
 * düzene göre değişiyor: Türkçe Q ile Türkçe F klavyede aynı fiziksel tuş
 * farklı ``key`` üretiyor, yani kullanıcı düzen değiştirdiğinde bağlama
 * sessizce bozulurdu. Değiştirici tuşlarda ayrıca bırakma sırasına göre
 * ``key`` farklı gelebiliyor.
 *
 * Zone A: upstream bu dosyayı bilmiyor.
 */

/** Varsayılan fiziksel tuş: sağ Ctrl. */
export const DEFAULT_PTT_CODE = 'ControlRight'

/**
 * Bağlanamayacak tuşlar.
 *
 * ``Escape`` ve ``Tab`` kullanıcının kaçış yolları: birine bas-konuş bağlamak,
 * paneli kapatmayı ya da odak gezinmesini bas-konuşa çevirir ve kullanıcı
 * bağlamayı geri almak için o tuşlara ihtiyaç duyar. ``Enter`` ve ``Space``
 * düğme etkinleştirme: yeniden bağlama ekranında kullanıcı düğmeye basarak
 * yakalamayı açtığı an aynı tuş yakalanırdı.
 */
const UNBINDABLE = new Set(['Enter', 'Escape', 'NumpadEnter', 'Space', 'Tab'])

/** Geçerli bir ``KeyboardEvent.code`` biçimi mi? */
const CODE_SHAPE = /^[A-Za-z][A-Za-z0-9]*$/

export function isBindableCode(code: unknown): code is string {
  return typeof code === 'string' && CODE_SHAPE.test(code) && !UNBINDABLE.has(code)
}

/**
 * Saklanan değeri güvene al.
 *
 * ``localStorage`` kullanıcının elinde: elle düzenlenmiş ya da eski bir
 * sürümden kalmış bir değer bas-konuşu sessizce ölü bırakırdı. Tanınmayan
 * her şey varsayılana düşüyor.
 */
export function sanitizePttCode(raw: unknown): string {
  return isBindableCode(raw) ? raw : DEFAULT_PTT_CODE
}

/** Bilinen tuşların insan okur adları. */
const NAMES: Record<string, string> = {
  AltLeft: 'Left Alt',
  AltRight: 'Right Alt',
  CapsLock: 'Caps Lock',
  ContextMenu: 'Menu',
  ControlLeft: 'Left Ctrl',
  ControlRight: 'Right Ctrl',
  MetaLeft: 'Left Win',
  MetaRight: 'Right Win',
  ShiftLeft: 'Left Shift',
  ShiftRight: 'Right Shift'
}

/**
 * Kullanıcıya gösterilecek ad.
 *
 * ``ControlRight`` bir tanımlayıcı, arayüz metni değil. Ham hâlini göstermek
 * kullanıcıya hangi tuşa basacağını söylemiyor.
 */
export function formatPttCode(code: string): string {
  if (NAMES[code]) {
    return NAMES[code]
  }

  // ``KeyQ`` -> ``Q``, ``Digit7`` -> ``7``, ``F13`` -> ``F13``.
  const stripped = /^Key(?<letter>[A-Z])$/.exec(code)?.groups?.letter ?? /^Digit(?<digit>[0-9])$/.exec(code)?.groups?.digit

  return stripped ?? code
}


// ---------------------------------------------------------------------------
// Değiştiricili bağlamalar — ``Shift+ControlRight`` gibi
// ---------------------------------------------------------------------------

/**
 * Neden kombo gerekiyor
 * ---------------------
 * Tek bir tuş her makinede boş değil. Sağ Ctrl bazı dizüstülerde fiziksel
 * olarak yok, bazılarında IME değiştirmeye bağlı; kullanıcı o zaman başka bir
 * tuş seçiyor ama TEK tuş da çakışabiliyor -- ``KeyV`` bağlarsan yazarken
 * bas-konuş açılır. Bir değiştirici eklemek çakışmayı bitiriyor.
 *
 * Biçim ``Shift+Alt+ControlRight``: değiştiriciler SABİT sırada (Ctrl, Alt,
 * Shift, Meta) ve en sonda fiziksel tuş. Sabit sıra şart -- ``Shift+Alt+KeyV``
 * ile ``Alt+Shift+KeyV`` aynı bağlama ve iki farklı dize olarak saklanırsa
 * karşılaştırma sessizce başarısız olur.
 *
 * ESKİ DEĞERLER geçerli: değiştiricisiz saklanmış her şey ("ControlRight")
 * olduğu gibi çalışmaya devam ediyor -- bu bir biçim genişletmesi, göç değil.
 */
export interface PttBinding {
  code: string
  alt: boolean
  ctrl: boolean
  meta: boolean
  shift: boolean
}

const MODIFIER_ORDER: ReadonlyArray<[keyof PttBinding, string]> = [
  ['ctrl', 'Ctrl'],
  ['alt', 'Alt'],
  ['shift', 'Shift'],
  ['meta', 'Meta']
]

/** ``Shift+ControlRight`` -> yapı. Tanınmayan her şey varsayılana düşer. */
export function parsePttBinding(raw: unknown): PttBinding {
  const fallback = { alt: false, code: DEFAULT_PTT_CODE, ctrl: false, meta: false, shift: false }
  const text = typeof raw === 'string' ? raw.trim() : ''

  if (!text) {
    return fallback
  }

  // BOS parcalar ATILMIYOR -- ve bu bilerek.
  //
  // ``filter(Boolean)`` ile ``"Shift+"`` -> ``["Shift"]`` oluyor, sondaki tus
  // ``"Shift"`` diye okunuyor ve ``CODE_SHAPE``den geciyor. Ama ``"Shift"``
  // bir ``KeyboardEvent.code`` DEGIL (gercegi ``ShiftLeft``/``ShiftRight``),
  // yani baglama hicbir olayla eslesmiyor: bas-konus SESSIZCE oluyor -- bu
  // dosyanin var olma sebebi olan hatanin ta kendisi.
  const parts = text.split('+')
  const code = parts.pop() ?? ''
  const modifiers = parts.map(part => part.trim().toLowerCase())

  if (!isBindableCode(code)) {
    return fallback
  }

  // TANINMAYAN degistirici de bozuk bir degerdir. Yok saymak, kullanicinin
  // sakladigindan FARKLI bir baglama uretmek olurdu.
  const KNOWN = new Set(['alt', 'ctrl', 'meta', 'shift'])

  if (modifiers.some(name => !KNOWN.has(name))) {
    return fallback
  }

  const has = (name: string) => modifiers.includes(name)

  return {
    alt: has('alt'),
    code,
    ctrl: has('ctrl'),
    meta: has('meta'),
    shift: has('shift')
  }
}

/** Yapı -> saklanabilir dize. Sıra SABİT (yukarıdaki nota bak). */
export function formatPttBinding(binding: PttBinding): string {
  const parts = MODIFIER_ORDER.filter(([flag]) => binding[flag]).map(([, label]) => label)

  return [...parts, binding.code].join('+')
}

/**
 * Olay bu bağlamayla EŞLEŞİYOR mu?
 *
 * Değiştiriciler TAM eşleşiyor, "en az" değil: ``ControlRight`` bağlıyken
 * ``Shift+ControlRight`` bas-konuşu AÇMAMALI, yoksa kullanıcı Shift'e basılı
 * yazarken mikrofon açılır.
 *
 * TEK İSTİSNA bağlamanın kendi tuşu: ``ControlRight`` bağlıyken o tuşa basmak
 * ``ctrlKey``i zaten true yapıyor. Kendi değiştiricisini "fazladan basılmış"
 * saymak, bağlamayı hiç eşleşmez hâle getirirdi -- ölçülen hata buydu.
 */
export function bindingMatches(binding: PttBinding, event: {
  code?: string
  altKey?: boolean
  ctrlKey?: boolean
  metaKey?: boolean
  shiftKey?: boolean
}): boolean {
  if (event.code !== binding.code) {
    return false
  }

  // "Kendi ailesi" TEK yerden okunuyor (``modifierFamily``). Burada ayrı bir
  // liste tutmak ikinci kopya olurdu: yeni bir değiştirici tuş eklendiğinde
  // biri güncellenir, diğeri sessizce eskir ve bağlama hiç eşleşmez olurdu.
  const self = modifierFamily(binding.code)

  return (
    (self === 'ctrl' || Boolean(event.ctrlKey) === binding.ctrl) &&
    (self === 'alt' || Boolean(event.altKey) === binding.alt) &&
    (self === 'shift' || Boolean(event.shiftKey) === binding.shift) &&
    (self === 'meta' || Boolean(event.metaKey) === binding.meta)
  )
}

/** İnsan okur ad: ``Shift + Right Ctrl``. */
export function formatPttBindingLabel(binding: PttBinding): string {
  const mods = MODIFIER_ORDER.filter(([flag]) => binding[flag]).map(([, label]) => label)

  return [...mods, formatPttCode(binding.code)].join(' + ')
}


// ---------------------------------------------------------------------------
// Yakalama — ayarlar panelindeki "Rebind"
// ---------------------------------------------------------------------------

/** Hangi fiziksel tuş hangi değiştirici ailesinden. */
const MODIFIER_FAMILY: Record<string, 'alt' | 'ctrl' | 'meta' | 'shift'> = {
  AltLeft: 'alt',
  AltRight: 'alt',
  ControlLeft: 'ctrl',
  ControlRight: 'ctrl',
  MetaLeft: 'meta',
  MetaRight: 'meta',
  ShiftLeft: 'shift',
  ShiftRight: 'shift'
}

/** Bu tuş saf bir değiştirici mi — öyleyse hangi ailesinden? */
export function modifierFamily(code: string): 'alt' | 'ctrl' | 'meta' | 'shift' | null {
  return MODIFIER_FAMILY[code] ?? null
}

export interface PttCapture {
  binding: PttBinding
  /** Bağlama TAMAM mı, yoksa daha fazla tuş bekleniyor mu? */
  complete: boolean
}

/**
 * Basılan tuştan bağlama çıkar.
 *
 * ``complete`` neden var
 * ----------------------
 * ``Shift + Sağ Ctrl`` atamak için kullanıcı önce Shift'e basıyor. O anda
 * hemen bağlasaydık bağlama ``ShiftLeft`` olurdu ve kombo HİÇ kurulamazdı --
 * ikinci tuşa sıra gelmeden yakalama kapanırdı.
 *
 * O yüzden TEK BAŞINA basılan bir değiştirici ``complete: false`` dönüyor:
 * arayüz onu önizleme olarak gösterip bekliyor. İki yol var:
 *
 *   * Üstüne başka bir tuş gelir (``Shift`` basılıyken ``ControlRight``) --
 *     o basış ``complete: true`` ve kombo kurulur.
 *   * Kullanıcı tuşu bırakır -- arayüz bekleyeni tek başına bağlar, yani
 *     düz ``ControlRight`` atamak eskisi gibi çalışmaya devam eder.
 *
 * Tuşun KENDİ ailesi değiştirici sayılmıyor: ``ControlRight``e basmak
 * ``ctrlKey``i zaten true yapıyor ve onu saymak ``Ctrl+ControlRight`` gibi
 * hiçbir olayla eşleşmeyen bir bağlama üretirdi.
 */
export function captureKeyDown(event: {
  code?: string
  altKey?: boolean
  ctrlKey?: boolean
  metaKey?: boolean
  shiftKey?: boolean
}): null | PttCapture {
  const code = event.code ?? ''

  if (!isBindableCode(code)) {
    return null
  }

  const self = modifierFamily(code)

  const binding: PttBinding = {
    alt: self !== 'alt' && Boolean(event.altKey),
    code,
    ctrl: self !== 'ctrl' && Boolean(event.ctrlKey),
    meta: self !== 'meta' && Boolean(event.metaKey),
    shift: self !== 'shift' && Boolean(event.shiftKey)
  }

  const bare = !binding.alt && !binding.ctrl && !binding.meta && !binding.shift

  return { binding, complete: !(self !== null && bare) }
}


/**
 * Yakalama SIRASI — saf, DOM'suz, sınanabilir.
 *
 * ``captureKeyDown`` tek bir olaya bakıyor; asıl karar SIRADA. "Bekleyen tek
 * değiştirici" kuralı arayüzün içinde on satır olarak kalsaydı yalnızca metin
 * taramasıyla korunabilirdi -- ve bu depoda ölçülen bir ders var: metin
 * taraması davranışı yakalamıyor. Sıra buraya çıkarıldı ki gerçek tuş
 * dizileri (``Shift`` bas → ``ControlRight`` bas) doğrudan sınanabilsin.
 */
export interface BindingCapture {
  /**
   * Basış işle.
   *
   * ``null`` = tuş BAĞLANAMAZ, olaya hiç dokunulmadı. Çağıranın bunu ayırt
   * etmesi şart: ``Tab`` yakalamanın içinde de bir kaçış yolu ve onu yutmak
   * kullanıcıyı panelde kilitler.
   *
   * ``complete: false`` = tek başına değiştirici, önizleme göster ve bekle.
   */
  down: (event: Parameters<typeof captureKeyDown>[0]) => null | PttCapture
  /** Bırakma işle. Bekleyen tek değiştirici bırakıldıysa onu döner. */
  up: (event: { code?: string }) => null | PttBinding
}

export function createBindingCapture(): BindingCapture {
  // TEK BAŞINA basılmış değiştirici: üstüne ikinci bir tuş gelebilir, o yüzden
  // henüz bağlanmıyor.
  let pending: null | PttBinding = null

  return {
    down: event => {
      const capture = captureKeyDown(event)

      if (!capture) {
        return null
      }

      pending = capture.complete ? null : capture.binding

      return capture
    },
    up: event => {
      // Bekleyen değiştirici, ÜSTÜNE başka tuş gelmeden bırakıldı: kullanıcı
      // tek tuş istiyor. Başka bir tuşun bırakılması bunu tetiklememeli.
      if (!pending || event.code !== pending.code) {
        return null
      }

      const chosen = pending
      pending = null

      return chosen
    }
  }
}
