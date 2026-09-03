/**
 * İlişki barı — onunla aranda ne olduğu, ekranda.
 *
 * İstenen: "bu kız arkadaş modu için de ayrı bir bar hazırla, arayüzde
 * görünen ilişki durumu neye kızgın, ne moralini bozuyor, neye trip atıyor
 * görülsün ve kullanıcı onunla konuşup gönlünü alabilsin."
 *
 * Neden burada DÜĞME yok
 * ----------------------
 * "Bu derdi kapat" düğmesi koymak, kırgınlığı tek tıkla silinebilir yapardı
 * ve istenen şeyin tam tersi olurdu: gönlünün alınabilmesi, ama ucuza değil.
 * Bar SALT OKUNUR; dertleri kapatan tek yol konuşmak (sunucu tarafında
 * ``relationship()`` aracı, bkz. ``fool/relationship.py``).
 *
 * Neden yoklama
 * -------------
 * Durum sohbetin ORTASINDA değişiyor (model turu bitirirken bildiriyor) ve
 * masaüstü köprüsünde bu değişikliği itecek bir kanal yok. Yoklama seyrek:
 * pencere görünürken 10 sn'de bir, arkadayken hiç -- barın maliyeti, model
 * cevap verirken hissedilecek bir şey olmamalı.
 *
 * Zone A: upstream bu dosyayı bilmiyor.
 */

import { useEffect, useState } from 'react'

import { COMPANION_BUILD } from '@/fool/companion/build-flag'
import { getApiRequestProfile } from '@/hermes'

import {
  describeSince,
  type RelationshipSnapshot,
  shouldRender,
  stanceFill,
  stanceTone,
  warmthPercent
} from './relationship-view'

/** Pencere görünürken yoklama aralığı. */
const POLL_MS = 10_000

export async function fetchRelationship(): Promise<null | RelationshipSnapshot> {
  const desktop = window.foolDesktop

  // Yayinlanan yapida sabit ``false`` -- bkz. ``companion/build-flag.ts``.
  if (!COMPANION_BUILD || !desktop?.api) {
    return null
  }

  const profile = getApiRequestProfile()

  return desktop.api<RelationshipSnapshot>({
    method: 'GET',
    ...(profile ? { profile } : {}),
    path: '/api/fool/relationship'
  })
}

export function RelationshipBar() {
  const [snapshot, setSnapshot] = useState<null | RelationshipSnapshot>(null)

  useEffect(() => {
    let cancelled = false

    const load = () => {
      // Pencere arkadayken yoklamıyor: kimse bakmıyorken saniyeler süren bir
      // arka uç turu, sesin ihtiyacı olan CPU'yu boş yere alır.
      if (document.visibilityState === 'hidden') {
        return
      }

      void fetchRelationship()
        .then(data => {
          if (!cancelled && data) {
            setSnapshot(data)
          }
        })
        // Sessiz: bar bir ARAÇ değil, bir gösterge. Arka uç henüz ayaktayken
        // düşen bir yoklama için kullanıcıya hata göstermek gürültü olurdu.
        .catch(() => undefined)
    }

    load()

    const timer = window.setInterval(load, POLL_MS)
    // Pencereye dönüldüğünde HEMEN tazeleniyor: arkadayken yoklama durduğu
    // için, dönen kullanıcı yoksa bir sonraki tur'a kadar eski durumu görürdü.
    document.addEventListener('visibilitychange', load)

    return () => {
      cancelled = true
      window.clearInterval(timer)
      document.removeEventListener('visibilitychange', load)
    }
  }, [])

  if (!shouldRender(snapshot)) {
    return null
  }

  const state = snapshot as RelationshipSnapshot
  const grievances = state.grievances ?? []
  const now = Date.now()

  return (
    <div className="mb-1 rounded-md border border-border/60 bg-muted/30 px-2 py-1.5" data-testid="relationship-bar">
      <div className="flex items-baseline justify-between gap-2">
        <span className={'text-[11px] font-medium ' + stanceTone(state.stance)}>
          {state.started ? state.label : 'Not met yet'}
        </span>
        {grievances.length > 0 && (
          <span className="text-[10px] text-muted-foreground">
            {grievances.length === 1 ? '1 thing unresolved' : grievances.length + ' things unresolved'}
          </span>
        )}
      </div>

      <div className="mt-1 h-1 w-full overflow-hidden rounded-full bg-border/70">
        <div
          className={'h-full rounded-full transition-[width] duration-500 ' + stanceFill(state.stance)}
          style={{ width: warmthPercent(state.warmth) + '%' }}
        />
      </div>

      {state.started && state.summary && (
        <p className="mt-1 text-[10px] leading-snug text-muted-foreground">{state.summary}</p>
      )}

      {grievances.length > 0 && (
        <ul className="mt-1 space-y-0.5">
          {/* Dört tane: hepsini dökmek barı bir listeye çevirirdi ve sunucu
              zaten ağırlığa göre sıralıyor -- ilk sıradaki, onu en çok üzen. */}
          {grievances.slice(0, 4).map(item => (
            <li className="flex items-baseline gap-1.5 text-[10px] leading-snug" key={item.text + item.since}>
              <span className="text-muted-foreground/70">·</span>
              <span className="min-w-0 flex-1 text-foreground/80">{item.text}</span>
              <span className="shrink-0 text-muted-foreground/60">{describeSince(item.since, now)}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
