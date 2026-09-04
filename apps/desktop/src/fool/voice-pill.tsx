/**
 * Ses hapı — composer'da, model hapının yanında.
 *
 * Neden burada, durum çubuğunda değil
 * -----------------------------------
 * İlk yazımda durum çubuğuna koydum ve kullanıcı bulamadı: "ekranımda herhangi
 * bir yerde şu an tts ve stt model seçim kısmı yok, sadece ayarlarda var."
 * Baktığı yer composer -- model seçimini de oradan yapıyor. Bir denetim,
 * kullanıcının aradığı yerde değilse yok demektir.
 *
 * Neden iki sütun
 * ---------------
 * İstenen birebir buydu: "chatterbox seçiliyken aynı modeldeki düşünme seviyesi
 * seçimi gibi ses tipleri de seçilmeli." Model hapı motorları solda, düşünme
 * seviyesini sağda gösteriyor; burası motorları solda, o motorun SESLERİNİ
 * sağda gösteriyor. Aynı şekil, öğrenilecek yeni bir şey yok.
 *
 * Neden yalnızca ÇALIŞTIĞI DOĞRULANMIŞ olanlar seçilebilir
 * --------------------------------------------------------
 * Kullanıcının kuralı: "kesinlikle çalıştığı emin olunmayan ses tipleri
 * çalışıyormuş gibi seçim açık olmamalı." O yüzden kapı ``installed`` değil
 * ``usable``: paket yerinde ama motor içe aktarılamıyorsa (``engine_error``)
 * seçim, sessizce çalışmayan bir motora geçmek olurdu. Sebep de gösteriliyor --
 * devre dışı bir satır sebebini söylemezse kullanıcı defalarca tıklar.
 *
 * Kurulum burada YOK: bu bir değiştirici. İndirme ses panelinde kalıyor.
 *
 * Zone A: upstream bu dosyayı bilmiyor.
 */

import { useCallback, useEffect, useState } from 'react'

import { Button } from '@/components/ui/button'
import { DropdownMenu, DropdownMenuContent, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { cn } from '@/lib/utils'
import { notifyError } from '@/store/notifications'

import { voiceApi, type VoiceCatalog, type VoiceClone, type VoiceItem } from './voice-api'

const ROW = 'flex w-full items-center justify-between gap-2 px-2.5 py-1.5 text-left text-[0.78rem] transition-colors'

/** Bir motorun neden seçilemediği. Boş = seçilebilir. */
function blockedReason(item: VoiceItem): string {
  if (!item.installed) {
    return 'not installed'
  }

  if (item.engine_error) {
    // Yeniden kurmak düzeltmiyor, o yüzden "Install" değil SEBEP gösteriliyor.
    return item.engine_error.slice(0, 40)
  }

  return item.usable ? '' : 'unavailable'
}

export function VoicePill({ disabled }: { disabled?: boolean }) {
  const [open, setOpen] = useState(false)
  const [catalog, setCatalog] = useState<null | VoiceCatalog>(null)
  // KLONLAR ayrı bir uçtan geliyor (``/voice/clones``) ve ilk yazımda hiç
  // okunmuyordu: kullanıcının beş klonu varken hap yalnızca "Built-in voice"
  // gösteriyordu. Katalogdaki ``voices`` motorun GÖMÜLÜ sesleri; klonlar
  // kullanıcının kendi kaydettikleri ve asıl kullandığı şey onlar.
  const [clones, setClones] = useState<VoiceClone[]>([])
  const [busy, setBusy] = useState(false)

  // TEMBEL: katalog çağrısı dokuz motorun CUDA sondasını çalıştırıyor
  // (ölçüldü: ilk açılışta ~6 sn). Menü açılmadan hiçbir istek gitmiyor --
  // kullanılmayan bir hap uğruna her açılışta o bedeli ödemek yanlış olurdu.
  useEffect(() => {
    if (!open || catalog) {
      return
    }

    let alive = true

    void Promise.allSettled([voiceApi.catalog(), voiceApi.clones()]).then(([cat, cl]) => {
      if (!alive) {
        return
      }

      if (cat.status === 'fulfilled') {
        setCatalog(cat.value)
      }

      // Klonlar DÜŞERSE motor listesi yine çiziliyor: bir listenin
      // gelmemesi diğerini de kaybettirmemeli.
      if (cl.status === 'fulfilled') {
        setClones(cl.value.clones ?? [])
      }
    })

    return () => {
      alive = false
    }
  }, [catalog, open])

  const refresh = useCallback(async () => {
    const [cat, cl] = await Promise.allSettled([voiceApi.catalog(), voiceApi.clones()])

    if (cat.status === 'fulfilled') {
      setCatalog(cat.value)
    }

    if (cl.status === 'fulfilled') {
      setClones(cl.value.clones ?? [])
    }
  }, [])

  const tts = (catalog?.items ?? []).filter(item => item.kind === 'tts')
  const stt = (catalog?.items ?? []).filter(item => item.kind === 'stt')
  const activeTts = tts.find(item => item.active)
  const activeStt = stt.find(item => item.active)

  const pick = useCallback(
    async (run: () => Promise<unknown>, label: string) => {
      setBusy(true)

      try {
        await run()
        await refresh()
      } catch (error) {
        notifyError(error, label)
      } finally {
        setBusy(false)
      }
    },
    [refresh]
  )

  const engineRows = (items: VoiceItem[]) =>
    items.map(item => {
      const blocked = blockedReason(item)

      return (
        <button
          className={cn(
            ROW,
            item.active && 'bg-accent/50 font-medium',
            blocked ? 'cursor-not-allowed opacity-45' : 'hover:bg-accent/40'
          )}
          disabled={Boolean(blocked) || busy}
          key={item.id}
          onClick={() => void pick(() => voiceApi.select(item.id), `Could not switch to ${item.label}`)}
          title={blocked ? `${item.label} — ${blocked}` : item.summary}
          type="button"
        >
          <span className="truncate">{item.label}</span>
          {blocked ? (
            <span className="shrink-0 text-[0.66rem] text-(--ui-text-tertiary)">{blocked}</span>
          ) : item.active ? (
            <span className="shrink-0 text-(--theme-primary)">✓</span>
          ) : null}
        </button>
      )
    })

  // SESLER: yalnızca seçili TTS motorunun, ve yalnızca o motor gerçekten
  // çalışıyorsa. Çalışmayan bir motorun ses listesini seçilebilir göstermek,
  // kullanıcının kuralını doğrudan çiğnerdi.
  const voices = activeTts && !blockedReason(activeTts) ? activeTts.voices : []

  // Klonlar da ayni kapidan geciyor: calismayan bir motorun klonlarini
  // secilebilir gostermek, kullanicinin kuralini ciğnerdi.
  const cloneRows = activeTts && !blockedReason(activeTts) ? clones : []

  return (
    <DropdownMenu onOpenChange={setOpen} open={open}>
      <DropdownMenuTrigger asChild>
        <Button
          className="h-7 shrink-0 gap-1 px-2 text-[0.72rem] font-normal text-(--ui-text-tertiary) hover:text-(--ui-text-secondary)"
          disabled={disabled}
          size="sm"
          title="Voice engines and voices"
          type="button"
          variant="ghost"
        >
          {activeTts?.label ?? 'Voice'}
          {activeTts?.voice ? <span className="opacity-60">· {activeTts.voice}</span> : null}
        </Button>
      </DropdownMenuTrigger>

      <DropdownMenuContent align="end" className="flex w-auto gap-0 p-0" side="top" sideOffset={8}>
        <div className="w-56 border-r border-(--ui-stroke-quaternary) py-1">
          <div className="px-2.5 pb-1 pt-1.5 text-[0.62rem] font-medium uppercase tracking-wider text-(--ui-text-tertiary)">
            Speaks with
          </div>
          {tts.length === 0 ? (
            <div className="px-2.5 py-1.5 text-[0.72rem] text-(--ui-text-tertiary)">Loading…</div>
          ) : (
            engineRows(tts)
          )}

          <div className="mt-1 border-t border-(--ui-stroke-quaternary) px-2.5 pb-1 pt-2 text-[0.62rem] font-medium uppercase tracking-wider text-(--ui-text-tertiary)">
            Listens with
          </div>
          {engineRows(stt)}
          {activeStt ? null : null}
        </div>

        <div className="max-h-80 w-56 overflow-y-auto py-1">
          <div className="px-2.5 pb-1 pt-1.5 text-[0.62rem] font-medium uppercase tracking-wider text-(--ui-text-tertiary)">
            Voice
          </div>
          {!activeTts ? (
            <div className="px-2.5 py-1.5 text-[0.72rem] text-(--ui-text-tertiary)">Pick an engine first.</div>
          ) : voices.length === 0 && cloneRows.length === 0 ? (
            <div className="px-2.5 py-1.5 text-[0.72rem] text-(--ui-text-tertiary)">This engine has one voice.</div>
          ) : (
            <>
              {voices.map(voice => (
                <button
                  className={cn(ROW, activeTts.voice === voice.id && 'bg-accent/50 font-medium', 'hover:bg-accent/40')}
                  disabled={busy}
                  key={voice.id}
                  onClick={() =>
                    void pick(() => voiceApi.setVoice(activeTts.id, voice.id), `Could not switch to ${voice.label}`)
                  }
                  type="button"
                >
                  <span className="truncate">{voice.label}</span>
                  {activeTts.voice === voice.id ? <span className="shrink-0 text-(--theme-primary)">✓</span> : null}
                </button>
              ))}

              {/* KLONLAR. Kullanicinin kendi kaydettikleri, ve pratikte asil
                  kullandigi sesler. Ilk yazimda hic okunmuyorlardi: bes klonu
                  varken hap yalnizca "Built-in voice" gosteriyordu. */}
              {cloneRows.length > 0 && (
                <div className="mt-1 border-t border-(--ui-stroke-quaternary) px-2.5 pb-1 pt-2 text-[0.62rem] font-medium uppercase tracking-wider text-(--ui-text-tertiary)">
                  Cloned
                </div>
              )}
              {cloneRows.map(clone => (
                <button
                  className={cn(ROW, activeTts.voice === clone.id && 'bg-accent/50 font-medium', 'hover:bg-accent/40')}
                  disabled={busy}
                  key={clone.id}
                  onClick={() =>
                    void pick(() => voiceApi.selectClone(activeTts.id, clone.id), `Could not switch to ${clone.label}`)
                  }
                  title={clone.label}
                  type="button"
                >
                  <span className="truncate">{clone.label}</span>
                  {activeTts.voice === clone.id ? <span className="shrink-0 text-(--theme-primary)">✓</span> : null}
                </button>
              ))}
            </>
          )}
        </div>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
