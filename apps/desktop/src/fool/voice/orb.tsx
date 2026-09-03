/**
 * Sesli yüzeyin küresi — bir enstrüman, bir "parlayan top" değil.
 *
 * Tasarım kararı
 * --------------
 * Kullanıcının istediği "sci-fi ama minimal, AI slop olmasın". Slop dolu bir
 * arayüzün somut işaretleri var: neon gradyanlar, her şeyin üstünde blur, her
 * köşede parıltı. Buradaki karşı yaklaşım HASSASİYET: ince çizgiler, gerçek
 * ölçeğe oturan çentikler, tek bir vurgu rengi ve sesin gerçek seviyesini
 * takip eden tek bir yay. Bilim kurgu hissi süslemeden değil, ALETİN
 * kendisinden geliyor.
 *
 * Neden React state YOK
 * ---------------------
 * Önceki hâli her karede ``setFrame`` çağırıyordu -- saniyede 60 React
 * render'ı, üstüne çocuk bileşenlerin uzlaştırması. Panel ağır hissettiriyordu
 * ve bu his kullanıcının bildirdiği "çok düşünüyor" izleniminin bir parçası.
 * Animasyon reaktif bir değer değil, sürekli bir sinyal: doğrudan DOM'a
 * yazılıyor ve React hiç uyandırılmıyor.
 *
 * Zone A: upstream bu dosyayı bilmiyor.
 */

import { useEffect, useRef } from 'react'

import {
  advance,
  createOrbState,
  isHearing,
  type OrbPhase,
  ringOpacity,
  scaleFor
} from './orb-motion'

/** Çevredeki çentik sayısı. 48 = 7,5 derecede bir; sayılamayacak kadar sık,
 *  düzensiz görünmeyecek kadar seyrek. */
const TICKS = 48

/** Dışa doğru açılan halkalar. */
const RINGS = 3

/**
 * Notch'tan DAMLAYAN açılış.
 *
 * Küre yukarıdan bir damla gibi düşüyor, yere değince eziliyor ve küreye
 * dönüşüyor. Süre kısa (760 ms) ve bilerek: uzun bir açılış animasyonu ikinci
 * kez izlendiğinde gecikmeye dönüşüyor.
 *
 * Fizik gerçek: düşüşte ivmelenme (``cubic-bezier(.55,0,.85,.35)`` -- yerçekimi
 * eğrisi), çarpmada ezilme, sonra yaylanarak oturma. Sabit hızla düşen bir
 * damla animasyon gibi görünüyor; ivmelenen bir damla DÜŞÜYOR gibi görünüyor.
 */
const DROP_KEYFRAMES = `
@keyframes fool-orb-drop {
  0%   { transform: translateY(-46vh) scaleX(0.42) scaleY(1.55); opacity: 0; }
  12%  { opacity: 1; }
  55%  { transform: translateY(0) scaleX(0.62) scaleY(1.34); }
  70%  { transform: translateY(0) scaleX(1.24) scaleY(0.72); }
  84%  { transform: translateY(0) scaleX(0.92) scaleY(1.08); }
  100% { transform: translateY(0) scaleX(1) scaleY(1); }
}
@media (prefers-reduced-motion: reduce) {
  @keyframes fool-orb-drop {
    0%   { opacity: 0; }
    100% { opacity: 1; }
  }
}
`

export function Orb({
  dropping = false,
  level,
  phase,
  size = 256
}: {
  /** Açılış damlaması oynasın mı? */
  dropping?: boolean
  level: number
  phase: OrbPhase
  /**
   * Kenar uzunluğu (px).
   *
   * Çentik 184 px yüksekliğinde ve oraya 256'lık bir küre sığmıyor. Ölçü
   * PARAMETRE çünkü çentikteki ile tam sayfadaki aynı alet: iki ayrı bileşen
   * yazmak, birinde düzeltilen fiziğin diğerinde eski kalması demek.
   */
  size?: number
}) {
  const rootRef = useRef<HTMLDivElement | null>(null)
  const levelRef = useRef(level)
  const phaseRef = useRef(phase)

  levelRef.current = level
  phaseRef.current = phase

  useEffect(() => {
    const root = rootRef.current

    if (!root) {
      return
    }

    const state = createOrbState()
    let raf = 0
    let last = performance.now()

    const tick = (now: number) => {
      const dt = now - last

      last = now

      const next = advance(state, levelRef.current, dt)
      const current = phaseRef.current

      // Tek bir yazma noktası: alt öğeler bu değişkenleri okuyor. Her öğeye
      // ayrı ayrı yazmak aynı karede birden çok düzen hesabı tetikliyordu.
      root.style.setProperty('--orb-scale', scaleFor(next, current).toFixed(4))
      root.style.setProperty('--orb-level', next.level.toFixed(4))
      root.style.setProperty('--orb-hearing', isHearing(next, current) ? '1' : '0')

      for (let index = 0; index < RINGS; index += 1) {
        root.style.setProperty(`--orb-ring-${index}`, ringOpacity(next, current, index).toFixed(4))
      }

      raf = window.requestAnimationFrame(tick)
    }

    raf = window.requestAnimationFrame(tick)

    return () => window.cancelAnimationFrame(raf)
  }, [])

  return (
    <div
      className="relative grid shrink-0 place-items-center [--orb-hearing:0] [--orb-level:0] [--orb-scale:1]"
      ref={rootRef}
      style={
        dropping
          ? {
              height: size,
              width: size,
              animation: 'fool-orb-drop 760ms cubic-bezier(.55,0,.85,.35) both',
              // Ezilme ALTTAN olmali: bir damla merkezinden degil, degdigi
              // yerden yayiliyor.
              transformOrigin: '50% 100%'
            }
          : { height: size, width: size }
      }
    >
      <style>{DROP_KEYFRAMES}</style>
      {/* Çentik halkası: dönmüyor, SABİT duruyor. Dönen bir halka "yükleniyor"
          demek ve burada hiçbir şey yüklenmiyor -- alet açık, o kadar. */}
      <svg className="absolute size-full" viewBox="0 0 200 200">
        <g opacity="0.28">
          {Array.from({ length: TICKS }, (_, index) => {
            const angle = (index / TICKS) * Math.PI * 2 - Math.PI / 2
            const major = index % 6 === 0
            const inner = major ? 86 : 90

            return (
              <line
                key={index}
                stroke="var(--theme-primary)"
                strokeLinecap="round"
                strokeWidth={major ? 1.4 : 0.7}
                x1={100 + Math.cos(angle) * inner}
                x2={100 + Math.cos(angle) * 95}
                y1={100 + Math.sin(angle) * inner}
                y2={100 + Math.sin(angle) * 95}
              />
            )
          })}
        </g>

        {/* Seviye yayı: çevrenin ne kadarının dolduğu GERÇEK mikrofon
            seviyesi. Rastgele bir animasyon ilk bakışta aynı görünür ama
            kullanıcı sustuğunda oynamaya devam eder ve his anında bozulur. */}
        <circle
          cx="100"
          cy="100"
          fill="none"
          pathLength={1}
          r="95"
          stroke="var(--theme-primary)"
          strokeDasharray="1"
          strokeLinecap="round"
          strokeWidth="1.6"
          style={{
            opacity: 'calc(0.35 + var(--orb-level) * 0.65)',
            strokeDashoffset: 'calc(1 - var(--orb-level) * 0.92)',
            transform: 'rotate(-90deg)',
            transformOrigin: '100px 100px'
          }}
        />
      </svg>

      {/* Dışa açılan halkalar -- sesin odada yayılması. */}
      {Array.from({ length: RINGS }, (_, index) => (
        <span
          className="absolute rounded-full border border-(--theme-primary)"
          key={index}
          style={{
            height: `${52 + index * 13}%`,
            opacity: `var(--orb-ring-${index})`,
            transform: 'scale(calc(var(--orb-scale) - ' + index * 0.028 + '))',
            width: `${52 + index * 13}%`
          }}
        />
      ))}

      {/* Çekirdek. Düz dolgu DEĞİL: merkeze doğru açılan çok yumuşak bir
          radyal geçiş, kenarında hairline bir çizgi. Düz disk oyuncak
          görünüyordu, blur'lu bir küre ise tam da kaçınılan şey. */}
      <span
        className="absolute rounded-full"
        style={{
          background:
            'radial-gradient(circle at 50% 42%, color-mix(in srgb, var(--theme-primary) 92%, white) 0%, var(--theme-primary) 58%, color-mix(in srgb, var(--theme-primary) 78%, black) 100%)',
          boxShadow: 'inset 0 0 0 0.5px color-mix(in srgb, white 22%, transparent)',
          height: '38%',
          // Gecis SURESI yok: kare basina zaten yumusatiliyor ve ustune CSS
          // gecisi koymak iki kat yumusatma demek -- kure sesin GERISINDE
          // kaliyor ve "duymuyor" hissi geri geliyor.
          opacity: 'calc(0.68 + var(--orb-hearing) * 0.27)',
          transform: 'scale(var(--orb-scale))',
          width: '38%'
        }}
      />
    </div>
  )
}
