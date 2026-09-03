/**
 * Capabilities yüzeyinin SDK kapısı — TEMBEL.
 *
 * Neden ayrı bir dosya
 * --------------------
 * ``@fool/plugin-sdk`` tek bir modül (barrel). Bir modül BÖLÜNMEZ: eklenti
 * ondan tek bir sabit alsa bile bütün grafiği yüklenir. Barrel
 * ``SkillsView``i doğrudan dışa veriyordu ve o da ``CodeEditor`` üzerinden
 * bütün CodeMirror dil tablolarını çekiyordu.
 *
 * Ölçüldü (gerçek yapı, ``dist/index.html``in modulepreload grafiği):
 *
 *     skills-*.js       105,4 KB
 *     code-editor-*.js   49,6 KB
 *     dist-*.js         271,2 KB   (CodeMirror language-data + unicode)
 *     ------------------------
 *     toplam            426,2 KB   AÇILIŞTA, tek bir ``export`` satırı için
 *
 * Uygulamanın kendi yolları bu sayfayı ZATEN ``lazy()`` ile yüklüyor
 * (``app/chat/route-tile.tsx``, ``app/contrib/surfaces.tsx``); açılışa
 * çiviyi yalnızca SDK satırı çakıyordu.
 *
 * Neden sarmalayıcı, neden düz ``lazy`` değil
 * -------------------------------------------
 * Dışa verilen adın DAVRANIŞI değişmemeli: eklenti yazarı ``<SkillsView />``
 * yazıyor ve bir ``Suspense`` sınırı kurması beklenmiyor. Çıplak bir
 * ``lazy()`` dışa vermek, sınırı olmayan her eklentiyi kırardı -- yani
 * kütüphane hatasını kullanıcı koduna taşımak olurdu. Sınır burada.
 */

import { type ComponentProps, lazy, Suspense } from 'react'

import type { SkillsView as SkillsViewType } from '@/app/skills'
import type { McpTab as McpTabType } from '@/app/skills/mcp-tab'

const SkillsViewLazy = lazy(async () => ({ default: (await import('@/app/skills')).SkillsView }))

const McpTabLazy = lazy(async () => ({ default: (await import('@/app/skills/mcp-tab')).McpTab }))

/** THE whole Capabilities surface (Skills / Tools / MCP tabs, installed
 *  lists, full-skill detail pane, embedded hub picker with one-click
 *  installs). For plugin dialogs pass `embedded` (tab state stays local —
 *  never touches the page router) and `fixedProfile` to pin every tab to one
 *  bot's backend; the internal profile selector hides itself. Bot Mode's
 *  Advanced section is the reference consumer. */
export function SkillsView(props: ComponentProps<typeof SkillsViewType>) {
  return (
    <Suspense fallback={null}>
      <SkillsViewLazy {...props} />
    </Suspense>
  )
}

/** THE full MCP tab core Settings renders — per-server enable + OAuth sign-in
 *  + API-key setup + live probes, not a checkbox list. Route-decoupled so it
 *  renders anywhere (a plugin dialog); pass a live `gateway` (see
 *  `host.getGateway()`) and an optional `profile` to scope it to one bot. */
export function McpTab(props: ComponentProps<typeof McpTabType>) {
  return (
    <Suspense fallback={null}>
      <McpTabLazy {...props} />
    </Suspense>
  )
}
