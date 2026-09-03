/**
 * Çentiğin sıvı akışı ve üst kenar dalgaları.
 *
 * Kırmızı top KALDIRILDI
 * ----------------------
 * Önce ayrı bir top vardı: ekranın ortasına düşüyor, yerçekimi tersine yukarı
 * çekiliyor, sıçrayarak çentiği oluşturuyordu. Kullanıcının kararı net --
 * "notchun açılış animasyonu bok gibi, onu basitleştir, o kırmızı topu komple
 * kaldır ve basit bir şekilde sıvıymış gibi notch o minimal haline aksın."
 *
 * Doğru olan da bu: akan şey çentiğin KENDİSİ olmalı, ona eşlik eden ayrı bir
 * nesne değil. İki hareketli parça (top + şerit) aynı anda ekrandayken göz
 * hangisine bakacağını bilmiyordu.
 *
 * Akış üst kenardan aşağı: ``transform-origin`` tepede, yani şerit oradan
 * dökülüyor gibi iniyor. Hafif bir aşma (overshoot) sıvı hissini veriyor --
 * abartılmadan, tek bir salınım.
 *
 * Neden CSS keyframe: animasyon her karede React işi üretmemeli. Şerit modelin
 * cevabı akarken de çiziliyor ve orada zaten kare başına metin güncelleniyor.
 *
 * Zone A: upstream bu dosyayı bilmiyor.
 */

import { useEffect, useState } from 'react'

/** Akışın süresi -- çentik bundan sonra yerine oturmuş olur. */
export const LIQUID_OPEN_MS = 420

/** Geri çekilme: şerit üst kenara doğru toplanıp kayboluyor. */
export const LIQUID_CLOSE_MS = 260

export type LiquidPhase = 'closing' | 'idle' | 'opening'

const KEYFRAMES = `
@keyframes fool-notch-pour {
  /* Üst kenarda ezilmiş bir damla. */
  0%   { transform: scaleY(0.04) scaleX(0.7); opacity: 0; }
  /* Dökülüyor ve yayılıyor. */
  55%  { transform: scaleY(1.12) scaleX(1.04); opacity: 1; }
  /* Tek salınım: sıvı yerine oturuyor. */
  78%  { transform: scaleY(0.94) scaleX(0.99); }
  100% { transform: scaleY(1) scaleX(1); opacity: 1; }
}

@keyframes fool-notch-drain {
  0%   { transform: scaleY(1) scaleX(1); opacity: 1; }
  100% { transform: scaleY(0.04) scaleX(0.72); opacity: 0; }
}

/* Dalgalar çentikten ÇIKIYOR: üst kenar boyunca dışa doğru akıyor. */
@keyframes fool-wave-out {
  0%   { transform: scaleX(0.04); opacity: 0; }
  30%  { opacity: 0.9; }
  100% { transform: scaleX(1); opacity: 0; }
}
`

/** Keyframe'ler bir kez sayfaya girsin. */
export function NotchLiquidStyles() {
  return <style>{KEYFRAMES}</style>
}

/**
 * Akış stilini üret.
 *
 * ``idle`` iken HİÇBİR animasyon yok: sürekli oynayan bir şerit, kaldırılan
 * topun yaptığı dikkat dağıtmanın aynısı olurdu.
 */
export function liquidPourStyle(phase: LiquidPhase): React.CSSProperties {
  if (phase === 'idle') {
    return {}
  }

  const opening = phase === 'opening'

  return {
    animation: `${opening ? 'fool-notch-pour' : 'fool-notch-drain'} ${
      opening ? LIQUID_OPEN_MS : LIQUID_CLOSE_MS
    }ms cubic-bezier(.34,.8,.3,1) both`,
    // Sıvı ÜST kenardan dökülüyor: kaynağı ekranın tepesi.
    transformOrigin: 'top center'
  }
}

/**
 * ÜST KENAR dalgaları -- yalnızca dinlerken.
 *
 * Çentiğin iki yanından dışa doğru akan ince çizgiler. Konuşma algılandığında
 * ``active`` düşüyor ve dalgalar çentiğe geri çekiliyor: kullanıcının istediği
 * "konuşma algılandığında dalgalar tekrardan notcha geri çekilsin".
 */
export function NotchEdgeWaves({ active }: { active: boolean }) {
  return (
    <div className="pointer-events-none absolute inset-x-0 top-0 flex justify-center" style={{ height: 3 }}>
      {([0, 1, 2] as const).map(index => (
        <span
          className="absolute top-0 h-px"
          key={index}
          style={{
            background:
              'linear-gradient(90deg, transparent 0%, var(--theme-primary) 50%, transparent 100%)',
            animation: active
              ? `fool-wave-out 1500ms ease-out ${index * 420}ms infinite`
              : undefined,
            inset: '0 0 auto 0',
            opacity: active ? undefined : 0,
            transform: active ? undefined : 'scaleX(0)',
            transition: active ? undefined : 'transform 260ms ease-in, opacity 260ms ease-in'
          }}
        />
      ))}
    </div>
  )
}

/**
 * Oturum açılıp kapanırken GEÇİŞ evresini üret.
 *
 * Evre kendiliğinden sönüyor: akış bir OLAY, bir durum değil. Süre dolduğunda
 * ``idle``a dönmezse şerit sürekli animasyonlu kalırdı.
 */
export function useLiquidPhase(sessionActive: boolean): LiquidPhase {
  const [phase, setPhase] = useState<LiquidPhase>('idle')
  const [seen, setSeen] = useState(sessionActive)

  useEffect(() => {
    if (sessionActive === seen) {
      return undefined
    }

    setSeen(sessionActive)
    setPhase(sessionActive ? 'opening' : 'closing')

    const timer = setTimeout(
      () => setPhase('idle'),
      sessionActive ? LIQUID_OPEN_MS : LIQUID_CLOSE_MS
    )

    return () => clearTimeout(timer)
  }, [seen, sessionActive])

  return phase
}
