/**
 * Kurulumda ses: iki model, tek düğme, görünen ilerleme.
 *
 * İstenen: "kullanıcı direkt olarak ilk mesajını atabilmeli ya da direkt
 * olarak ses modellerini indirebilmeli, TTS ve STT'yi, ve indirmenin durumunu
 * görebilmeli."
 *
 * Bugüne kadar ses yalnızca Ayarlar > Voice'ta kuruluyordu. Yeni kullanıcı
 * uygulamayı açıyor, mikrofona basıyor ve hiçbir şey olmuyor -- indirilecek
 * bir şey olduğunu hiçbir yerde görmediği için.
 *
 * Neden motor SEÇTİRMİYOR
 * -----------------------
 * Kurulum ekranı yedi motorluk bir liste değil. Kullanıcının o dakikadaki
 * sorusu "hangi TTS motoru?" değil, "konuşabilecek miyim?". Katalogdaki
 * önerilen çift seçiliyor, aygıt karta bakılarak kendiliğinden belirleniyor,
 * ve ikisi de Ayarlar'dan sonradan değiştirilebiliyor.
 *
 * Neden ATLANABİLİR ve neden bu kadar görünür
 * -------------------------------------------
 * "İlk mesajını direkt atabilmeli" da istendi. Ses birkaç yüz megabayt ve
 * yazarak kullanmak isteyeni indirme beklemeye zorlamak, ilk dakikayı bir
 * ilerleme çubuğuna bakarak geçirtmek olurdu. Atlamak bir vazgeçiş değil:
 * indirme arka planda sürerken de sohbet açılabiliyor.
 *
 * Zone A: upstream bu dosyayı bilmiyor.
 */

import { useCallback, useEffect, useRef, useState } from 'react'

import { Button } from '@/components/ui/button'
import { Check, Download, Loader2, Mic, Volume2 } from '@/lib/icons'

import { voiceApi, type VoiceCatalog, type VoiceItem, type VoiceJob } from '../voice-api'

import { installDevice, jobFor, overallPercent, pendingInstalls, recommendedPair, setupState } from './voice-setup'

/** İş durumu yoklama aralığı — kurulum panelindekiyle aynı. */
const POLL_MS = 1_000

export function VoiceSetupStep({ onDone }: { onDone?: () => void } = {}) {
  const [catalog, setCatalog] = useState<null | VoiceCatalog>(null)
  // Kart kendini KAPATABILIYOR: saglayici seciminin altinda duruyor ve
  // sesle ilgilenmeyen birinin ekraninda kalici bir kutu olmamali.
  const [dismissed, setDismissed] = useState(false)
  const [jobs, setJobs] = useState<Record<string, VoiceJob | null>>({})
  const [error, setError] = useState<null | string>(null)
  const [started, setStarted] = useState(false)
  const timer = useRef<number | undefined>(undefined)

  useEffect(() => {
    let cancelled = false

    void voiceApi
      .catalog()
      .then(data => {
        if (!cancelled) {
          setCatalog(data)
        }
      })
      .catch(() => {
        // Sessiz: katalog gelmezse adım kendini gizliyor (aşağıda). Kurulumun
        // ilk ekranında bir ağ hatası göstermek, henüz hiçbir şey denememiş
        // kullanıcıya uygulamanın bozuk olduğunu söylemek olurdu.
        if (!cancelled) {
          setCatalog(null)
        }
      })

    return () => {
      cancelled = true
    }
  }, [])

  const pair = catalog ? recommendedPair(catalog.items) : []
  const state = setupState(pair, jobs)
  const percent = overallPercent(pair, jobs)

  // Süren işleri yokla. Kurulum dakikalarca sürebiliyor ve tek geri bildirim
  // bu: yoklama durursa kullanıcı donmuş bir çubuğa bakar.
  //
  // ``timer`` bir ZAMANLAYICI TUTACAĞI, atom aynası değil: kuralın yasakladığı
  // şey reaktif bir değeri ref'e kopyalamak ve onu geri okumak.
  // eslint-disable-next-line no-restricted-syntax
  useEffect(() => {
    if (state !== 'installing') {
      window.clearInterval(timer.current)

      return
    }

    const tick = () => {
      const running = Object.values(jobs).filter((job): job is VoiceJob => job?.state === 'running')

      running.forEach(job => {
        void voiceApi
          .job(job.id)
          .then(next => setJobs(previous => ({ ...previous, [next.entry_id]: next })))
          .catch(() => undefined)
      })
    }

    timer.current = window.setInterval(tick, POLL_MS)

    return () => window.clearInterval(timer.current)
  }, [jobs, state])

  const install = useCallback(async () => {
    if (!catalog) {
      return
    }

    setStarted(true)
    setError(null)

    for (const item of pendingInstalls(recommendedPair(catalog.items))) {
      try {
        const job = await voiceApi.install(item.id, installDevice(item, catalog.cuda_available))

        setJobs(previous => ({ ...previous, [item.id]: job }))
      } catch (cause) {
        // Metin KULLANICIYA görünüyor.
        setError(cause instanceof Error ? cause.message : 'Could not start the download')
      }
    }
  }, [catalog])

  // Katalog gelmediyse ya da seslendirilecek bir çift yoksa adım YOK.
  // Boş bir ses kartı göstermek, kurulumun ilk ekranına anlamsız bir kutu
  // koymak olurdu.
  if (dismissed || !catalog || pair.length === 0) {
    return null
  }

  const ready = state === 'ready'

  return (
    <div className="grid gap-3">
      <div className="grid gap-2">
        {pair.map(item => (
          <VoiceRow item={item} job={jobFor(item, jobs)} key={item.id} />
        ))}
      </div>

      {started && !ready && (
        <div className="h-1 w-full overflow-hidden rounded-full bg-border/70">
          <div
            className="h-full rounded-full bg-(--theme-accent) transition-[width] duration-500"
            style={{ width: percent + '%' }}
          />
        </div>
      )}

      {error && <p className="text-[0.68rem] leading-snug text-(--theme-warm)">{error}</p>}

      <div className="flex items-center justify-between gap-3">
        <Button
          className="font-medium"
          onClick={() => {
            setDismissed(true)
            onDone?.()
          }}
          size="xs"
          type="button"
          variant="text"
        >
          {/* Indirme surerken de sohbet acilabiliyor: bekletmek bir sey
              kazandirmiyor. */}
          {state === 'installing' ? 'Continue while it downloads' : 'Skip — I will type'}
        </Button>

        {ready ? (
          <span className="flex items-center gap-1.5 text-[0.68rem] text-muted-foreground">
            <Check className="size-3.5" />
            Voice is ready
          </span>
        ) : (
          <Button disabled={state === 'installing'} onClick={() => void install()} size="sm" type="button">
            {state === 'installing' ? (
              <>
                <Loader2 className="size-3.5 animate-spin" />
                {percent}%
              </>
            ) : (
              <>
                <Download className="size-3.5" />
                {state === 'failed' ? 'Try again' : 'Set up voice'}
              </>
            )}
          </Button>
        )}
      </div>
    </div>
  )
}

function VoiceRow({ item, job }: { item: VoiceItem; job: VoiceJob | null }) {
  const Icon = item.kind === 'stt' ? Mic : Volume2
  const done = item.installed || job?.state === 'done'

  return (
    <div className="flex items-center gap-2.5 rounded-md border border-border/60 bg-muted/20 px-2.5 py-2">
      <Icon className="size-4 shrink-0 text-muted-foreground" />
      <div className="min-w-0 flex-1">
        <div className="truncate text-[0.72rem] font-medium">
          {item.kind === 'stt' ? 'Hearing you' : 'Speaking to you'}
        </div>
        <div className="truncate text-[0.62rem] text-muted-foreground">
          {item.label}
          {item.size_label ? ' · ' + item.size_label : ''}
        </div>
      </div>
      {done ? (
        <Check className="size-3.5 shrink-0 text-(--theme-accent)" />
      ) : job?.state === 'running' ? (
        <span className="shrink-0 font-mono text-[0.62rem] text-muted-foreground">
          {job.percent.toFixed(0)}%
        </span>
      ) : job?.state === 'failed' ? (
        <span className="shrink-0 text-[0.62rem] text-(--theme-warm)">failed</span>
      ) : null}
    </div>
  )
}
