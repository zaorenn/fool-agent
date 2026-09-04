/**
 * Ses ayarları: yerel TTS/STT motorlarını uygulama içinden indir.
 *
 * Neden
 * -----
 * Upstream'de bu modeller "ilk kullanımda kendiliğinden iner". Pratikte
 * kullanıcı sesi açıyor, arka planda yüzlerce MB inmeye başlıyor ve arayüzde
 * hiçbir şey görünmüyor — sadece "çalışmıyor" gibi duruyor. Burada ne olduğu,
 * ne kadar kaldığı ve bittiği görülüyor.
 *
 * Çubuk dürüst: model dosyası inerken yüzde GERÇEK baytlardan geliyor. pip
 * aşamasında gerçek bir yüzde yok, o yüzden aşama adı yazılıyor ve çubuk
 * sonuna dayanmıyor (bkz. ``fool/voice_models.py``).
 *
 * Zone A: upstream bu dosyayı bilmiyor; birleştirmede çakışamaz.
 */

import { useStore } from '@nanostores/react'
import { useCallback, useEffect, useRef, useState } from 'react'

import { ListRow, ListRowSkeleton, Pill, SettingsContent, SettingsSection } from '@/app/settings/primitives'
import { Button } from '@/components/ui/button'
import { triggerHaptic } from '@/lib/haptics'
import { Download, Info, Keyboard, Mic, Play, Volume2, Zap } from '@/lib/icons'
import { notifyError } from '@/store/notifications'
import {
  $wakeEngines,
  cancelWakeTest,
  installWakeEngine,
  loadWakeEngines,
  resetWakeTest,
  setWakeEngine,
  setWakeModel,
  startWakeTest,
  type WakeTestState
} from '@/store/wake-engines'
import { $wakeWord, setWakePhrase } from '@/store/wake-word'

import {
  createBindingCapture,
  DEFAULT_PTT_CODE,
  formatPttBinding,
  formatPttBindingLabel,
  parsePttBinding,
  type PttBinding
} from './notch/ptt-binding'
import { $pttCode } from './notch/ptt-store'
import { DEFAULT_NOTCH_SHORTCUT, formatAccelerator, toAccelerator } from './notch/shortcut-accelerator'
import {
  voiceApi,
  type VoiceCatalog,
  type VoiceClone,
  type VoiceItem,
  type VoiceJob,
  type VoiceKnob
} from './voice-api'

//: Süren bir kurulum varken yoklama aralığı. Saniyede bir, dakikalarca sürebilen
//: bir iş için fazlasıyla yeterli ve ağ geçidini meşgul etmiyor.
const POLL_MS = 1000

function ProgressBar({ job }: { job: VoiceJob }) {
  return (
    <div className="mt-2">
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
        <div
          className="h-full rounded-full bg-primary transition-[width] duration-300 ease-out"
          style={{ width: `${Math.max(job.percent, 2)}%` }}
        />
      </div>
      <div className="mt-1 flex items-center justify-between text-[0.68rem] text-muted-foreground">
        <span>
          {job.stage}
          {job.detail ? ` — ${job.detail}` : ''}
        </span>
        <span className="font-mono">{job.percent.toFixed(0)}%</span>
      </div>
    </div>
  )
}

/**
 * Model başına dinleme düğmesi.
 *
 * Dört motor "kurulu" yazıyor ve kullanıcı hangisinin nasıl konuştuğunu
 * duymadan seçim yapıyordu. Ses seçmek kulakla yapılan bir iş.
 *
 * Asıl kazanç ölçüm: geçen süre de gösteriliyor. Bu depodaki en pahalı hata
 * sınıfı -- "cihaz cuda yazıyordu, motor CPU'da koşuyordu" -- tam burada
 * görünür oluyor. Kokoro CUDA'da 0,08 sn; CPU'da saniyeler. Bir düğmeye basıp
 * "3,4 s" görmek, panelin "CUDA" yazmasından daha inandırıcı bir kanıt.
 */
function PreviewButton({ item }: { item: VoiceItem }) {
  const [busy, setBusy] = useState(false)
  const [elapsed, setElapsed] = useState<null | number>(null)

  const play = useCallback(async () => {
    setBusy(true)
    triggerHaptic()

    try {
      const result = await voiceApi.preview(item.id)

      setElapsed(result.elapsed_ms)
      // Ses ``data:`` URI olarak calindi: gecici dosya sunucuda zaten
      // siliniyor ve tarayiciya ikinci bir istek yaptirmak, motorun
      // sentezini bir kez daha tetikleme riski demekti.
      const audio = new Audio(`data:${result.mime};base64,${result.audio_base64}`)

      await audio.play()
    } catch (error) {
      notifyError(error, `Could not preview ${item.label}`)
    } finally {
      setBusy(false)
    }
  }, [item.id, item.label])

  // Bozuk motorda dinleme dugmesi YOK: basmak yalnizca bir hata bildirimi
  // uretirdi ve kullaniciya motorun calistigini ima ederdi.
  if (!item.installed || item.engine_error) {
    return null
  }

  return (
    <div className="flex items-center gap-1.5">
      <Button disabled={busy} onClick={() => void play()} size="sm" variant="ghost">
        <Play className="size-3.5" />
        {busy ? 'Speaking…' : 'Listen'}
      </Button>
      {elapsed !== null && (
        <span className="text-[0.62rem] text-muted-foreground tabular-nums">{(elapsed / 1000).toFixed(2)} s</span>
      )}
    </div>
  )
}

function VoiceRow({
  item,
  onInstall,
  onDevice,
  clones,
  onClone,
  onSelect,
  onVoice,
  onKnob,
  pending
}: {
  item: VoiceItem
  onInstall: (id: string, device: 'cpu' | 'cuda') => void
  onDevice: (id: string, device: 'auto' | 'cpu' | 'cuda') => void
  onSelect: (id: string) => void
  onVoice: (id: string, voice: string) => void
  onKnob: (entryId: string, knobId: string, value: number) => void
  clones: VoiceClone[]
  onClone: (action: 'select' | 'delete' | 'upload', payload: string | File, entryId: string) => void
  pending: VoiceJob | null
}) {
  const running = pending?.state === 'running'
  const supportsCuda = item.devices.includes('cuda')

  let action = null

  if (running) {
    action = (
      <Button disabled size="sm" variant="outline">
        Installing…
      </Button>
    )
  } else if (item.engine_error) {
    // Kurulu ama CALISMIYOR. "Use" gostermek kullaniciyi hicbir sey
    // duymayacagi bir secime goturuyordu; yeniden kurmak da duzeltmiyor,
    // o yuzden "Install" de yanlis cevap. Dogru cevap: secilemez + sebep.
    action = <Pill tone="warn">Unavailable</Pill>
  } else if (item.installed) {
    // Kurulu olmak ile KULLANILIYOR olmak ayri seyler. Yalnizca "Installed"
    // gostermek, dort modelin de kurulu oldugu bir listede hangisinin
    // konustugunu belirsiz birakiyordu.
    action = item.active ? (
      <Pill tone="primary">In use</Pill>
    ) : (
      <Button
        onClick={() => {
          triggerHaptic('open')
          onSelect(item.id)
        }}
        size="sm"
        variant="outline"
      >
        Use
      </Button>
    )
  } else {
    // KURULU DEGIL: dugmeler "kur" demeli, "cpu/cuda" degil.
    //
    // Onceki hali yalnizca ``CPU`` ve ``CUDA`` yaziyordu ve bunlara basmak
    // kurulumu BASLATIYORDU. Kullanicinin bildirdigi: "modelleri indirmek icin
    // buton yok, cpu ya da cuda tuslarina basinca indirme basliyor, bu sacma."
    // Haksiz degil -- o iki dugme bir CIHAZ SECICI gibi duruyor, oysa
    // gigabaytlarca indirmeyi baslatan tek eylem onlar.
    //
    // Mekanizma aynen duruyor (cihaz hala hangi paketin inecegini belirliyor);
    // degisen sey dugmenin NE YAPTIGINI soylemesi ve BOYUTU onceden gostermesi.
    // ``VoiceRow`` hem TTS hem STT satirlarinda kullaniliyor, yani duzeltme
    // katalogun tamamini kapsiyor.
    const sizeSuffix = item.size_label ? ` · ${item.size_label}` : ''

    action = (
      <div className="flex gap-2">
        <Button
          onClick={() => {
            triggerHaptic('open')
            onInstall(item.id, 'cpu')
          }}
          size="sm"
          title={`Download and install ${item.label} for CPU${sizeSuffix}`}
          variant="outline"
        >
          <Download className="mr-1 size-3.5" />
          Install (CPU){sizeSuffix}
        </Button>
        {/* CUDA düğmesi yalnızca GERÇEKTEN kullanılabilir olduğunda çıkıyor.
            Kartı olmayan birine sunmak, sessizce CPU'ya düşen bir kurulum
            demekti ve kullanıcı neden yavaş olduğunu anlamıyordu. */}
        {supportsCuda && item.cuda_available && (
          <Button
            onClick={() => {
              triggerHaptic('open')
              onInstall(item.id, 'cuda')
            }}
            size="sm"
            title={`Download and install ${item.label} for CUDA${sizeSuffix}`}
          >
            <Zap className="mr-1 size-3.5" />
            Install (CUDA){sizeSuffix}
          </Button>
        )}
      </div>
    )
  }

  const row = (
    <ListRow
      action={action}
      below={
        pending && pending.state === 'running' ? (
          <ProgressBar job={pending} />
        ) : item.engine_error ? (
          /* Motorun NEDEN calismadigi ve NE YAPILACAGI.
           *
           * Cihaz dugmelerinin YERINE geciyor, yanina degil: calismayan bir
           * motorda CPU/CUDA secmek anlamsiz ve motorun calistigini ima
           * ediyor. Ayrica ``supportsCuda`` kapisinin DISINDA -- CPU-only
           * bozuk bir motor da sebebini gostermeli. */
          <div className="mt-2 text-[0.62rem] leading-snug text-(--theme-warm)">{item.engine_error}</div>
        ) : item.installed && supportsCuda ? (
          // Kurulumdaki CPU/CUDA secimi hangi PAKETIN inecegini belirler;
          // bu ise modelin her calismada NEREDE kosacagini. Ikisini tek
          // dugmeye baglamak, kurduktan sonra aygit degistirmeyi imkansiz
          // kiliyordu.
          <div className="mt-2 flex flex-wrap items-center gap-1">
            {/* Ses secimi: bir motorun birden cok sesi var ve hangisinin
                konustugu panelde hic gorunmuyordu. Piper'in listesi DISKTEN
                geliyor -- inmemis bir sesi sunmak calisma aninda patlardi. */}
            {item.voices.length > 1 && (
              <select
                className="mr-2 h-6 rounded border border-(--stroke-nous) bg-transparent px-1 text-[0.66rem]"
                onChange={event => onVoice(item.id, event.target.value)}
                value={item.voice || item.voices[0]?.id || ''}
              >
                {item.voices.map(voice => (
                  <option key={voice.id} value={voice.id}>
                    {voice.label}
                  </option>
                ))}
              </select>
            )}
            {(['auto', 'cpu', 'cuda'] as const).map(device => (
              <Button
                className="h-6 px-2 text-[0.66rem]"
                disabled={device === 'cuda' && !item.cuda_available}
                key={device}
                onClick={() => {
                  triggerHaptic('open')
                  onDevice(item.id, device)
                }}
                size="sm"
                variant={item.device === device ? 'default' : 'ghost'}
              >
                {device === 'auto' ? 'Auto' : device.toUpperCase()}
              </Button>
            ))}
            {!item.cuda_available ? (
              <span className="ml-1 text-[0.62rem] text-muted-foreground">no CUDA on this machine</span>
            ) : item.device === 'cuda' && !item.cuda_ready ? (
              // Yapilandirmada "cuda" yazmasi ile motorun GERCEKTEN CUDA
              // calistirmasi ayri seyler; ikincisi olmadan sessizce CPU'ya
              // duser. Fark burada gorunur oluyor.
              <span className="ml-1 text-[0.62rem] text-(--theme-warm)">CUDA runtime missing</span>
            ) : null}
            {/* Kulakla secim + gercek gecikme. Panelin "CUDA" yazmasindan
                daha inandirici bir kanit. */}
            {item.kind === 'tts' && <PreviewButton item={item} />}
            {/* Buyuk bir modeli CPU'ya almanin bedelini ONCEDEN soyle:
                bir kez tiklayip dort dakika bekleyen kullanici uygulamanin
                dondugunu saniyor. Dugme gizlenmiyor -- karar onun. */}
            {item.cpu_warning && item.device === 'cpu' && (
              <span className="ml-1 text-[0.62rem] text-(--theme-warm)">{item.cpu_warning}</span>
            )}
          </div>
        ) : null
      }
      className={item.installed && item.clone_capable ? 'pb-1' : undefined}
      description={item.summary}
      hint={
        pending?.state === 'failed'
          ? `Failed: ${pending.error}`
          : [item.size_label, supportsCuda ? 'CPU / CUDA' : 'CPU'].filter(Boolean).join(' · ')
      }
      title={
        <span className="flex items-center gap-2">
          {item.label}
          {item.recommended && <Pill tone="primary">Recommended</Pill>}
        </span>
      }
    />
  )

  const knobs = <KnobSection item={item} onCommit={(knobId, value) => onKnob(item.id, knobId, value)} />

  if (!item.installed || !item.clone_capable) {
    return knobs ? (
      <div>
        {row}
        {knobs}
      </div>
    ) : (
      row
    )
  }

  // Klonlama YALNIZCA destekleyen ve KURULU motorlarda. Digerlerine referans
  // kayit sunmak sessizce yok sayilirdi -- kullanici sesini yukleyip hicbir
  // sey degismedigini gorurdu.
  return (
    <div>
      {row}
      {knobs}
      <CloneSection
        clones={clones}
        item={item}
        onDelete={id => onClone('delete', id, item.id)}
        onSelect={(entryId, cloneId) => onClone('select', cloneId, entryId)}
        onUpload={file => onClone('upload', file, item.id)}
      />
    </div>
  )
}

/**
 * Motora özel sayılar: yoğunluk, tempo, adım sayısı.
 *
 * Bildirilen: "ayarlardan ses modellerinin exaggeration gibi ayarlarını
 * yapamıyoruz." Değerler ``config.yaml``da duruyordu ve motor onları okuyordu
 * -- eksik olan yalnızca burasıydı; tek yol dosyayı elle açmaktı.
 *
 * Yalnızca KURULU motorlarda: kurulmamış bir motorun tonunu ayarlamak, hiçbir
 * şeyi ayarlamamak demek.
 *
 * Yazma GECİKTİRİLİYOR
 * --------------------
 * Bir kaydıraç sürüklenirken onlarca olay üretiyor. Her birinde
 * yapılandırmaya yazmak, tek bir sürüklemede ``config.yaml``ı elli kez
 * kaydetmek olurdu. Ekrandaki sayı anında oynuyor (yerel durum), yazma
 * duraklamayı bekliyor.
 */
function KnobSection({ item, onCommit }: { item: VoiceItem; onCommit: (knobId: string, value: number) => void }) {
  if (!item.installed || item.knobs.length === 0) {
    return null
  }

  return (
    <div className="mt-1 mb-2 flex flex-col gap-2 pl-1">
      {item.knobs.map(knob => (
        <KnobRow key={knob.id} knob={knob} onCommit={onCommit} />
      ))}
    </div>
  )
}

/** Yazmadan önce beklenen duraklama. */
const KNOB_COMMIT_MS = 400

function KnobRow({ knob, onCommit }: { knob: VoiceKnob; onCommit: (knobId: string, value: number) => void }) {
  const [value, setValue] = useState(knob.value)
  // Zamanlayıcı tutacağı -- atom aynası DEĞİL, bu yüzden ref uygun.
  const timer = useRef<number | undefined>(undefined)

  // Sunucudan gelen değer değiştiğinde (profil değişimi, dışarıdan düzenleme)
  // kaydıraç ona uyuyor. Sürükleme sırasında bu tetiklenmiyor: katalog knob
  // yazımından SONRA yeniden çekilmiyor, tam da bunun için.
  useEffect(() => {
    setValue(knob.value)
  }, [knob.value])

  useEffect(() => () => window.clearTimeout(timer.current), [])

  const change = (next: number) => {
    setValue(next)
    window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => onCommit(knob.id, next), KNOB_COMMIT_MS)
  }

  return (
    <div className="flex flex-col gap-0.5">
      <div className="flex items-center gap-2">
        <span className="w-24 shrink-0 text-[0.66rem] text-muted-foreground">{knob.label}</span>
        <input
          className="h-1 min-w-0 flex-1 accent-(--theme-accent)"
          max={knob.max}
          min={knob.min}
          onChange={event => change(Number(event.target.value))}
          step={knob.step}
          type="range"
          value={value}
        />
        <span className="w-8 shrink-0 text-right font-mono text-[0.62rem] text-muted-foreground">
          {knob.step >= 1 ? value.toFixed(0) : value.toFixed(2)}
        </span>
      </div>
      {knob.help && <p className="pl-26 text-[0.62rem] leading-snug text-muted-foreground/70">{knob.help}</p>}
    </div>
  )
}

/**
 * Ses klonlama: referans kaydı sürükle-bırak, klonlar arasından seç.
 *
 * Chatterbox sıfır-atış klonlama yapıyor — 5-10 saniyelik temiz bir kayıt
 * yeterli, eğitim yok. Yetenek arka uçta zaten vardı ama kaydı vermenin
 * hiçbir yolu yoktu: yapılandırmaya elle dosya yolu yazmak gerekiyordu.
 */
function CloneSection({
  item,
  clones,
  onDelete,
  onSelect,
  onUpload
}: {
  item: VoiceItem
  clones: VoiceClone[]
  onDelete: (id: string) => void
  onSelect: (entryId: string, cloneId: string) => void
  onUpload: (file: File) => void
}) {
  const [dragging, setDragging] = useState(false)
  // Motorlar ayni ozelligi FARKLI davraniyor -- chatterbox gercek klonlama,
  // styletts2 ton/ritim odunc alan bir stil aktarimi, f5-tts kaydin metnini
  // kendisi cikariyor. Tek bir genel "drop to clone" yazisi bu farki
  // gizliyordu; kullanici "her ses modeli icin nasil yapilacagi anlatilsin"
  // istedi. Aciklama varsayilan KAPALI -- her satirda acik durursa kucuk
  // panel gereksiz uzuyor.
  const [showHelp, setShowHelp] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  return (
    <div className="mt-3 rounded-lg border border-dashed border-(--stroke-nous) p-3">
      {/* Suruklemek TEK yol degil -- bir dosyayi Gezgin'den bu pencereye
          suruklemek herkes icin dogal degil (dokunmatik, ekran okuyucu,
          bir dosyayi bulup elle suruklemek istemeyen kullanici). Tiklamak
          AYNI yere ayni dosyayi getiriyor, gizli bir input uzerinden. */}
      <input
        accept=".wav,.mp3,.flac,.m4a,.ogg"
        className="hidden"
        onChange={event => {
          const file = event.target.files?.[0]

          if (file) {
            onUpload(file)
          }

          event.target.value = ''
        }}
        ref={fileInputRef}
        type="file"
      />
      <div
        className={`flex cursor-pointer flex-col items-center justify-center gap-1 rounded-md px-3 py-4 text-center transition-colors ${
          dragging ? 'bg-(--theme-primary)/10' : ''
        }`}
        onClick={() => fileInputRef.current?.click()}
        onDragLeave={() => setDragging(false)}
        onDragOver={event => {
          event.preventDefault()
          setDragging(true)
        }}
        onDrop={event => {
          event.preventDefault()
          setDragging(false)

          const file = event.dataTransfer.files?.[0]

          if (file) {
            onUpload(file)
          }
        }}
      >
        <Mic className="size-4 text-(--theme-primary)" />
        <div className="flex items-center gap-1">
          <span className="text-[0.72rem] font-medium">Drop a voice sample to clone it — or click to browse</span>
          {item.clone_help && (
            <button
              aria-label={`How cloning works on ${item.label}`}
              className="text-muted-foreground hover:text-(--text-primary)"
              onClick={event => {
                event.stopPropagation()
                setShowHelp(previous => !previous)
              }}
              type="button"
            >
              <Info className="size-3" />
            </button>
          )}
        </div>
        <div className="text-[0.66rem] text-muted-foreground">
          5–10 seconds of clean speech · wav, mp3, flac, m4a, ogg
        </div>
        {showHelp && item.clone_help && (
          <div className="mt-1 max-w-xs text-[0.64rem] text-(--text-secondary)">{item.clone_help}</div>
        )}
      </div>

      {clones.length > 0 && (
        <div className="mt-2 flex flex-col gap-1">
          {/* Motorun KENDI sesine donus: klonu kapatmanin tek yolu bu.
              Olmazsa kullanici bir kez klon sectikten sonra geri donemez. */}
          <button
            className={`flex items-center justify-between rounded px-2 py-1 text-left text-[0.7rem] ${
              item.clone ? 'text-muted-foreground' : 'bg-(--theme-primary)/15 font-medium'
            }`}
            onClick={() => onSelect(item.id, '')}
            type="button"
          >
            <span>Model&rsquo;s own voice</span>
            {!item.clone && <span className="text-[0.62rem]">in use</span>}
          </button>

          {clones.map(clone => (
            <div
              className={`flex items-center justify-between rounded px-2 py-1 text-[0.7rem] ${
                item.clone === clone.id ? 'bg-(--theme-primary)/15 font-medium' : ''
              }`}
              key={clone.id}
            >
              <button
                className="min-w-0 flex-1 truncate text-left"
                onClick={() => onSelect(item.id, clone.id)}
                type="button"
              >
                {clone.label}
              </button>
              <span className="ml-2 shrink-0 text-[0.62rem] text-muted-foreground">
                {item.clone === clone.id ? 'in use' : `${Math.round(clone.bytes / 1024)} KB`}
              </span>
              <Button
                className="ml-1 h-5 px-1 text-[0.62rem]"
                onClick={() => onDelete(clone.id)}
                size="sm"
                variant="ghost"
              >
                ×
              </Button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

/**
 * Bas-konuş tuşunu yeniden bağla — KOMBO dahil.
 *
 * Varsayılan sağ Ctrl her makinede yok: bazı dizüstülerde fiziksel olarak
 * bulunmuyor, bazı kullanıcılar onu IME değiştirmeye ya da ekran okuyucuya
 * bağlamış. O makinelerde bas-konuş hiç çalışmıyordu ve sebebi görünmüyordu —
 * kullanıcı notch'u açık görüp konuşuyor, hiçbir şey olmuyor.
 *
 * Tek tuş da yetmiyor: kullanıcı sağ Ctrl yerine ``KeyV`` seçtiğinde bu kez
 * YAZARKEN mikrofon açılıyor. Bir değiştirici eklemek (``Shift + Sağ Ctrl``)
 * çakışmayı bitiriyor, o yüzden yakalama komboyu da kabul ediyor.
 *
 * Yakalama ``code`` okuyor, ``key`` değil: ``code`` fiziksel tuşu gösterir ve
 * klavye düzeninden etkilenmez.
 */
function PushToTalkRow() {
  const stored = useStore($pttCode)
  const binding = parsePttBinding(stored)
  const [capturing, setCapturing] = useState(false)
  // Yakalama sürerken CANLI önizleme. Kullanıcı Shift'i basılı tutup bekliyor
  // ve ekranda hiçbir şey değişmiyorsa, komboyu kurabildiğini bilemez.
  const [preview, setPreview] = useState<null | PttBinding>(null)

  useEffect(() => {
    if (!capturing) {
      setPreview(null)

      return
    }

    // Sıra mantığı ``ptt-binding.ts``te ve SAF: "bekleyen tek değiştirici"
    // kuralı burada on satır olarak kalsaydı yalnızca metin taramasıyla
    // korunabilirdi.
    const capture = createBindingCapture()

    const commit = (chosen: PttBinding) => {
      $pttCode.set(formatPttBinding(chosen))
      setCapturing(false)
    }

    const onKey = (event: KeyboardEvent) => {
      // Escape yakalamayı İPTAL eder — bağlanabilir tuşlar arasında da
      // değil, yani kullanıcının her zaman bir çıkış yolu var.
      if (event.code === 'Escape') {
        event.preventDefault()
        setCapturing(false)

        return
      }

      const seen = capture.down(event)

      // ``null`` = bağlanamaz tuş. Yutmuyoruz: ``Tab`` yakalamanın içinde de
      // kullanıcının kaçış yolu.
      if (!seen) {
        return
      }

      event.preventDefault()
      setPreview(seen.binding)

      if (seen.complete) {
        commit(seen.binding)
      }
    }

    const onKeyUp = (event: KeyboardEvent) => {
      const done = capture.up(event)

      if (!done) {
        return
      }

      event.preventDefault()
      commit(done)
    }

    window.addEventListener('keydown', onKey, true)
    window.addEventListener('keyup', onKeyUp, true)

    return () => {
      window.removeEventListener('keydown', onKey, true)
      window.removeEventListener('keyup', onKeyUp, true)
    }
  }, [capturing])

  // Yakalarken: bekleyen varsa onu göster ("Shift + …" gibi), yoksa davet.
  const label = capturing
    ? preview
      ? `${formatPttBindingLabel(preview)} …`
      : 'Press a key or combo…'
    : formatPttBindingLabel(binding)

  return (
    <ListRow
      action={
        <div className="flex items-center gap-2">
          <Pill>{label}</Pill>
          <Button
            onClick={() => {
              triggerHaptic()
              setCapturing(previous => !previous)
            }}
            size="sm"
            variant="outline"
          >
            {capturing ? 'Cancel' : 'Rebind'}
          </Button>
          {stored !== DEFAULT_PTT_CODE && (
            <Button
              onClick={() => {
                triggerHaptic()
                $pttCode.set(DEFAULT_PTT_CODE)
              }}
              size="sm"
              variant="ghost"
            >
              Reset
            </Button>
          )}
        </div>
      }
      description="Hold this while the notch session is open to talk. Add a modifier (hold Shift, then press the key) to avoid clashing with typing. Escape cancels a rebind."
      title="Push to talk key"
    />
  )
}

/**
 * Uyandırma MOTORU: hangisi kurulu, hangisi seçili, kurulmamışsa indir.
 *
 * Neden motor seçimi arayüzde
 * ---------------------------
 * Üç motor var ve üçü de anahtarını FARKLI yerden alıyor. Bu ayrım hiçbir
 * yerde görünmüyordu ve doğrudan bir hataya yol açtı: ayarlar "hey fool"
 * gösterirken motor "hey hermes" dinliyordu. Kullanıcının istediği de bu ayrımı
 * eline almak: "kullanıcılar wake wordün farklı motorları varsa seçebilir...
 * mesela hey hermes kullanmak istiyorsa onu da kullanabilir ya da kendi
 * yazacağı bir şeyi kullanabilir."
 *
 * KURULMAMIŞ motor seçilemiyor, kurulabiliyor -- kullanıcının kalıcı kuralı:
 * "kurulu olmayan bir motor seçilebilir olmamalı", ve "senin manuel kurup
 * çalıştırdığın her bir ayrı şey uygulamadan doğrudan indirilebilir olmalı."
 */
function WakeEngineRow() {
  const state = useStore($wakeEngines)
  const [busy, setBusy] = useState('')

  const select = useCallback(async (id: string) => {
    setBusy(id)

    try {
      await setWakeEngine(id)
    } catch (error) {
      notifyError(error, 'Could not switch the wake engine')
    } finally {
      setBusy('')
    }
  }, [])

  const install = useCallback(async (id: string) => {
    try {
      const job = await installWakeEngine(id)

      if (job.state === 'failed') {
        // SEBEBI tasi. Ilk yazimda hem baslik hem govde "Could not install
        // the engine" yaziyordu ve kullanicinin elinde hicbir sey kalmiyordu
        // -- oysa arka uc tam olarak neyin cozulemedigini soylemisti
        // ("no version of pypinyin==0.57.0"). Sebepsiz bir hata, kullaniciyi
        // ayni dugmeye tekrar basmaktan baska bir seye goturmuyor.
        notifyError(new Error(job.error || 'the installer gave no reason'), `Could not install ${id}`)
      }
    } catch (error) {
      notifyError(error, `Could not install ${id}`)
    }
  }, [])

  // Basarisiz kurulum EKRANDA da kaliyor: bildirim kapanip gidiyor ve
  // kullanici sebebi bir daha goremiyordu.
  const failure = Object.values(state.installs).find(job => job.state === 'failed')

  return (
    <ListRow
      action={
        <div className="flex flex-wrap items-center justify-end gap-1">
          {state.engines.map(engine => {
            const job = state.installs[engine.id]
            const installing = job?.state === 'running'

            if (!engine.installed) {
              return (
                <Button
                  className="h-6 px-2 text-[0.66rem]"
                  disabled={installing}
                  key={engine.id}
                  onClick={() => {
                    triggerHaptic('open')
                    void install(engine.id)
                  }}
                  size="sm"
                  title={`Download and install ${engine.label}`}
                  variant="outline"
                >
                  <Download className="mr-1 size-3" />
                  {installing ? job.detail || 'Installing…' : engine.label}
                </Button>
              )
            }

            return (
              <Button
                className="h-6 px-2 text-[0.66rem]"
                // Kurulu ama KULLANILAMAZ (ör. anahtarı yok) motor seçilemiyor:
                // seçilebilir görünmesi, kullanıcıyı sessizce çalışmayan bir
                // uyandırmaya götürürdü.
                disabled={!engine.usable || busy === engine.id}
                key={engine.id}
                onClick={() => {
                  triggerHaptic('open')
                  void select(engine.id)
                }}
                size="sm"
                title={engine.usable ? engine.description : `${engine.label}: ${engine.blocked_reason}`}
                variant={engine.active ? 'default' : 'ghost'}
              >
                {engine.label}
              </Button>
            )
          })}
        </div>
      }
      description={
        (failure && `${failure.engine_id}: ${failure.error || 'install failed'}`) ||
        state.notice ||
        'Built-in phrases work offline with no setup. “Custom phrase” recognises anything you type.'
      }
      title="Wake engine"
    />
  )
}

/** Sınama durumunun kullanıcıya söylediği şey. */
function wakeTestLabel(test: WakeTestState): string {
  switch (test.phase) {
    case 'detected':
      return 'Heard it'

    case 'failed':
      return test.reason

    case 'listening':
      return `Say “${test.phrase}”…`

    case 'timeout':
      return 'Did not hear it'

    default:
      return ''
  }
}

/**
 * Uyandırma ifadesi + SINAMA.
 *
 * İfade alanı motora göre şekil değiştiriyor ve bu bilinçli:
 *
 *   * Açık sözcük dağarcıklı motorda (``sherpa``) SERBEST METİN -- yazılan
 *     ifade çalışma anında tokenize ediliyor, eğitim yok.
 *   * Sabit dağarcıklı motorda (``openwakeword``) LİSTE -- model ne
 *     eğitildiyse onu duyuyor. Orada serbest metin sunmak, yazılanın hiçbir
 *     zaman tanınmaması demekti. Ölçülen hata tam olarak buydu: alan "hey
 *     fool" gösteriyor, kulak "hey hermes" bekliyordu.
 *
 * Sınama düğmesi CANLI dinleyiciyi kullanıyor, ikinci bir mikrofon açmıyor; ve
 * sınama penceresi açıkken saptama çentiğe GİTMİYOR -- "çalışıyor mu" diye
 * bakan kullanıcının karşısına açılmış bir çentik çıkmamalı.
 */
function WakePhraseRow() {
  const wake = useStore($wakeWord)
  const engines = useStore($wakeEngines)
  const [draft, setDraft] = useState<null | string>(null)
  const [busy, setBusy] = useState(false)

  const active = engines.engines.find(engine => engine.active) ?? null
  const custom = active?.custom_phrase ?? true
  const phrases = active?.phrases ?? []

  // Gösterilen ifade motorun GERÇEKTEN dinlediği ifade.
  const effective = engines.effectivePhrase || wake.phrase
  const value = draft ?? effective
  const dirty = draft !== null && draft.trim() !== effective.trim()

  const save = useCallback(async () => {
    const next = (draft ?? '').trim()

    if (!next || busy) {
      return
    }

    setBusy(true)

    try {
      await setWakePhrase(next)
      await loadWakeEngines()
      setDraft(null)
    } catch (error) {
      notifyError(error, 'Could not save the wake phrase')
    } finally {
      setBusy(false)
    }
  }, [busy, draft])

  const pick = useCallback(async (model: string) => {
    setBusy(true)

    try {
      await setWakeModel(model)
    } catch (error) {
      notifyError(error, 'Could not change the wake phrase')
    } finally {
      setBusy(false)
    }
  }, [])

  const test = useCallback(async () => {
    resetWakeTest()
    await startWakeTest()
  }, [])

  const testing = engines.test.phase === 'listening'
  const testLabel = wakeTestLabel(engines.test)

  // Sınama sonucu kendiliğinden sönüyor: ekranda kalan eski bir "Heard it",
  // bir sonraki denemede yanlış bir güven verirdi.
  useEffect(() => {
    if (engines.test.phase !== 'detected' && engines.test.phase !== 'timeout') {
      return undefined
    }

    const timer = setTimeout(resetWakeTest, 6_000)

    return () => clearTimeout(timer)
  }, [engines.test.phase])

  return (
    <ListRow
      action={
        <div className="flex items-center gap-2">
          {custom ? (
            <input
              className="h-7 w-44 rounded-md border border-(--ui-stroke-tertiary) bg-(--ui-bg-card) px-2 text-[0.78rem] text-(--ui-text-primary) outline-none focus:border-(--theme-primary)"
              disabled={busy}
              onChange={event => setDraft(event.target.value)}
              onKeyDown={event => {
                if (event.key === 'Enter') {
                  void save()
                }
              }}
              placeholder="hey fool"
              spellCheck={false}
              value={value}
            />
          ) : (
            <select
              className="h-7 rounded-md border border-(--ui-stroke-tertiary) bg-(--ui-bg-card) px-2 text-[0.78rem] text-(--ui-text-primary)"
              disabled={busy}
              onChange={event => {
                triggerHaptic('open')
                void pick(event.target.value)
              }}
              value={phrases.find(item => item.phrase === effective)?.model ?? phrases[0]?.model ?? ''}
            >
              {phrases.map(item => (
                <option key={item.model} value={item.model}>
                  {item.phrase}
                </option>
              ))}
            </select>
          )}
          {dirty && custom && (
            <Button
              disabled={busy}
              onClick={() => {
                triggerHaptic()
                void save()
              }}
              size="sm"
              variant="outline"
            >
              {busy ? 'Saving…' : 'Save'}
            </Button>
          )}
          <Button
            // Sınama CANLI dinleyiciyi kullanıyor, o yüzden kulak kapalıyken
            // sınanacak bir şey yok.
            disabled={testing || !wake.listening}
            onClick={() => {
              triggerHaptic('open')
              void test()
            }}
            size="sm"
            title={wake.listening ? 'Say the wake word and see whether it fires' : 'Turn the wake word on first'}
            variant="outline"
          >
            <Play className="mr-1 size-3" />
            {testing ? 'Listening…' : 'Test'}
          </Button>
        </div>
      }
      description={
        testLabel ||
        (custom
          ? 'Say this to wake the notch — it answers out loud, then listens until you stop talking. A few syllables detect more reliably than one word.'
          : 'This engine only hears the phrases it was trained on. Pick one, or switch to “Custom phrase” above to type your own.')
      }
      title="Wake phrase"
    />
  )
}

/**
 * Notch'u acan GLOBAL kisayol.
 *
 * Bas-konus tusundan (yukaridaki satir) FARKLI bir sey ve ikisini
 * karistirmak kolay:
 *
 *   * Global kisayol notch'u ACAR ve arkadas turunu baslatir; uygulama
 *     odakta olmasa bile calisir.
 *   * Bas-konus tusu yalnizca notch ACIKKEN ve odaktayken is gorur.
 *
 * Kayit BASARISIZ olabiliyor: istenen tusu baska bir uygulama tutuyorsa
 * Electron sessizce ``false`` donuyor. O durum kullaniciya SOYLENIYOR --
 * yoksa tusa basip hicbir sey olmadigini gorur ve sebebini ogrenemez.
 */
function NotchShortcutRow() {
  const [shortcut, setShortcut] = useState('')
  const [capturing, setCapturing] = useState(false)
  const [taken, setTaken] = useState(false)

  useEffect(() => {
    let cancelled = false

    void (async () => {
      const state = await window.foolDesktop?.notch?.shortcut?.()

      if (!cancelled && state) {
        setShortcut(state.shortcut ?? '')
        setTaken(Boolean(state.preferred && state.shortcut !== state.preferred))
      }
    })()

    return () => {
      cancelled = true
    }
  }, [])

  const apply = useCallback(async (accelerator: string) => {
    const result = await window.foolDesktop?.notch?.setShortcut?.(accelerator)

    if (result) {
      setShortcut(result.shortcut ?? '')
      setTaken(Boolean(result.taken))
    }
  }, [])

  useEffect(() => {
    if (!capturing) {
      return
    }

    const onKey = (event: KeyboardEvent) => {
      // Escape her zaman cikis yolu -- yakalamayi iptal eder.
      if (event.code === 'Escape') {
        event.preventDefault()
        setCapturing(false)

        return
      }

      // Bos donen bilesim (tek basina degistirici, bilinmeyen tus) YOK
      // SAYILIYOR: yakalama acik kaliyor ve kullanici tekrar deneyebiliyor.
      // Gecersiz bir seyi kaydedip "olmadi" demek daha kotu olurdu.
      const accelerator = toAccelerator({
        alt: event.altKey,
        code: event.code,
        ctrl: event.ctrlKey,
        meta: event.metaKey,
        shift: event.shiftKey
      })

      if (!accelerator) {
        return
      }

      event.preventDefault()
      setCapturing(false)
      void apply(accelerator)
    }

    window.addEventListener('keydown', onKey, true)

    return () => window.removeEventListener('keydown', onKey, true)
  }, [apply, capturing])

  return (
    <ListRow
      action={
        <div className="flex items-center gap-2">
          <Pill>{capturing ? 'Press a combination…' : formatAccelerator(shortcut)}</Pill>
          <Button
            onClick={() => {
              triggerHaptic()
              setCapturing(previous => !previous)
            }}
            size="sm"
            variant="outline"
          >
            {capturing ? 'Cancel' : 'Rebind'}
          </Button>
          {shortcut !== DEFAULT_NOTCH_SHORTCUT && (
            <Button
              onClick={() => {
                triggerHaptic()
                void apply(DEFAULT_NOTCH_SHORTCUT)
              }}
              size="sm"
              variant="ghost"
            >
              Reset
            </Button>
          )}
        </div>
      }
      description={
        taken
          ? `Another app already owns your choice — ${formatAccelerator(shortcut)} is active instead.`
          : 'Opens the notch and starts a Friend turn, even when the app is not focused. Escape cancels a rebind.'
      }
      title="Notch shortcut"
    />
  )
}

export function VoiceSettings() {
  const [catalog, setCatalog] = useState<VoiceCatalog | null>(null)

  // Uyandirma motorlari katalogu: hangisi kurulu, hangisi yazilan ifadeyi
  // dinleyebiliyor. Ayarlar KAPANIRKEN suren bir sinama birakilmiyor --
  // acik unutulmus bir sinama penceresi gercek uyandirmalari yutmaya devam
  // ederdi.
  useEffect(() => {
    void loadWakeEngines()

    return () => {
      void cancelWakeTest()
    }
  }, [])
  const [jobs, setJobs] = useState<Record<string, VoiceJob>>({})
  const [loading, setLoading] = useState(true)

  // Kapatma ANINDA gizleniyor, katalogun yeniden yuklenmesi BEKLENMIYOR:
  // katalog cagrisi dokuz motorun CUDA sondasini calistiriyor (olculdu: ilk
  // acilista ~6 sn) ve o sure boyunca uyari ekranda kalirdi -- kullanici
  // dugmenin calismadigini dusunurdu.
  const dismissSpeechHint = useCallback(async () => {
    triggerHaptic()
    setCatalog(previous => (previous ? { ...previous, speech_language_hint: null } : previous))

    // Hata YUTULUYOR: kapatma bir kolaylik ve basarisiz olsa bile kullanici
    // uyariyi bir daha gormek zorunda degil (bir sonraki acilista donerse
    // yeniden kapatabilir).
    try {
      await voiceApi.dismissSpeechLanguageHint()
    } catch {
      // sessiz
    }
  }, [])

  // Katalogu yeniden cekmek icin sayac. Bir "reload" geri cagrimi yerine bunu
  // kullanmak, iptal bayragini efektin KENDI kapanisinda tutmayi mumkun
  // kiliyor; ref'e alinmis bir bayrak bir render geç kalir ve bayat okur.
  const [reloadToken, setReloadToken] = useState(0)
  const [clones, setClones] = useState<VoiceClone[]>([])

  useEffect(() => {
    let cancelled = false

    void (async () => {
      try {
        const data = await voiceApi.catalog()

        if (cancelled) {
          return
        }

        setCatalog(data)
        // Sunucudaki suren isler aliniyor: panel kapatilip acildiginda cubuk
        // kaldigi yerden devam etsin.
        setJobs(previous => {
          const next = { ...previous }

          for (const item of data.items) {
            if (item.job) {
              next[item.id] = item.job
            }
          }

          return next
        })
      } catch (error) {
        if (!cancelled) {
          notifyError(error, 'Could not load voice models')
        }
      } finally {
        if (!cancelled) {
          setLoading(false)
        }
      }
    })()

    return () => {
      cancelled = true
    }
  }, [reloadToken])

  // Suren is VARKEN yokla. Bosta yoklama yapmamak kasitli: panel acik kalirsa
  // saniyede bir gereksiz istek uretirdi.
  useEffect(() => {
    const running = Object.values(jobs).filter(job => job.state === 'running')

    if (running.length === 0) {
      return
    }

    let cancelled = false

    const timer = setInterval(() => {
      void (async () => {
        for (const job of running) {
          try {
            const fresh = await voiceApi.job(job.id)

            if (cancelled) {
              return
            }

            setJobs(previous => ({ ...previous, [fresh.entry_id]: fresh }))

            // Is bittiginde katalog yeniden cekiliyor: "Installed" rozeti
            // gercek duruma gore gelsin, iyimser tahminle degil.
            if (fresh.state !== 'running') {
              setReloadToken(token => token + 1)
            }
          } catch {
            // Tek bir yoklama hatasi kurulumu iptal etmez; sonraki tur dener.
          }
        }
      })()
    }, POLL_MS)

    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [jobs])

  const select = useCallback(async (id: string) => {
    try {
      await voiceApi.select(id)
      setReloadToken(token => token + 1)
    } catch (error) {
      notifyError(error, 'Could not switch model')
    }
  }, [])

  const setDevice = useCallback(async (id: string, device: 'auto' | 'cpu' | 'cuda') => {
    try {
      const result = await voiceApi.setDevice(id, device)

      // CUDA secildi ama ortam onu CALISTIRAMIYOR: yalnizca yapilandirmaya
      // yazmak sessiz bir yalan olurdu -- motor CPU'ya duser ve kullanici
      // yalnizca "cok yavas" gorur. Gercek calisma zamani hemen kuruluyor.
      if ((result as { needs_cuda_runtime?: boolean }).needs_cuda_runtime) {
        const job = await voiceApi.installCuda(id)

        setJobs(previous => ({ ...previous, [id]: job }))
      }

      setReloadToken(token => token + 1)
    } catch (error) {
      notifyError(error, 'Could not change device')
    }
  }, [])

  // Klon listesi katalogla AYNI anda yenileniyor: yukleme sonrasi liste
  // guncellenmezse kullanici sesini yukleyip goremez.
  useEffect(() => {
    let cancelled = false

    void voiceApi
      .clones()
      .then(r => {
        if (!cancelled) {
          setClones(r.clones)
        }
      })
      .catch(() => undefined)

    return () => {
      cancelled = true
    }
  }, [reloadToken])

  const onClone = useCallback(
    async (action: 'select' | 'delete' | 'upload', payload: File | string, entryId: string) => {
      try {
        if (action === 'upload' && payload instanceof File) {
          // Dosya kopruden gectigi icin ham bayt tasinamiyor; base64'e
          // cevriliyor. ``readAsDataURL`` basina MIME onEki koyuyor, o
          // kirpiliyor.
          const dataUrl = await new Promise<string>((resolve, reject) => {
            const reader = new FileReader()

            reader.onerror = () => reject(reader.error ?? new Error('okunamadi'))
            reader.onload = () => resolve(String(reader.result ?? ''))
            reader.readAsDataURL(payload)
          })

          await voiceApi.uploadClone(payload.name, dataUrl.slice(dataUrl.indexOf(',') + 1))
        } else if (action === 'delete' && typeof payload === 'string') {
          await voiceApi.deleteClone(payload)
        } else if (action === 'select' && typeof payload === 'string') {
          await voiceApi.selectClone(entryId, payload)
        }

        setReloadToken(token => token + 1)
      } catch (error) {
        notifyError(error, 'Voice clone action failed')
      }
    },
    []
  )

  const setVoice = useCallback(async (id: string, voice: string) => {
    try {
      await voiceApi.setVoice(id, voice)
      setReloadToken(token => token + 1)
    } catch (error) {
      notifyError(error, 'Could not change voice')
    }
  }, [])

  const setKnob = useCallback(async (entryId: string, knobId: string, value: number) => {
    try {
      await voiceApi.setKnob(entryId, knobId, value)
    } catch (error) {
      // Katalog YENIDEN CEKILMIYOR (basarida da): tam bir katalog kurulumu
      // saniyeler suruyor ve kaydiracin altindaki degeri kullanici hala
      // surukluyorken degistirirdi. Yazilan deger zaten ekranda duruyor.
      notifyError(error, 'Could not change that setting')
    }
  }, [])

  const install = useCallback(async (id: string, device: 'cpu' | 'cuda') => {
    try {
      const job = await voiceApi.install(id, device)

      setJobs(previous => ({ ...previous, [id]: job }))
    } catch (error) {
      notifyError(error, 'Could not start the install')
    }
  }, [])

  if (loading) {
    return (
      <SettingsContent>
        <ListRowSkeleton />
        <ListRowSkeleton />
        <ListRowSkeleton />
      </SettingsContent>
    )
  }

  const tts = catalog?.items.filter(item => item.kind === 'tts') ?? []
  const stt = catalog?.items.filter(item => item.kind === 'stt') ?? []

  return (
    <SettingsContent>
      <SettingsSection
        icon={Volume2}
        meta={catalog?.cuda_available ? 'CUDA available' : 'CPU only'}
        title="Text to speech"
      >
        {/* OLCULMUS yavaslik uyarisi.
            Sayi geciyor, cunku "daha hizli bir secenek var" tek basina
            inandirici degil ve kullanici bir motoru bilerek secmis. Olculen
            fark ise karar verdirir (kyutai 2,52 sn / kokoro 0,20 sn).
            Kalite dususu ONERILMIYOR: piper daha da hizli ama kyutai'yi
            gercekciligi icin secen kisiye onu onermek, cozulen sorunu geri
            getirmek olurdu (bkz. fool/voice_bench.py::BASIC_QUALITY). */}
        {catalog?.slow_engine && (
          <div className="mb-2 rounded-md border border-(--theme-warm)/40 bg-(--theme-warm)/10 px-3 py-2 text-xs text-(--text-secondary)">
            {catalog.slow_engine.message}
          </div>
        )}
        {/* Konusma dili AYARSIZKEN yabanci dil seslendirildi.
            Tek dilli bir motor Turkceyi Ingilizce fonetigiyle okuyor
            (Merhaba -> Mehabal): ses cikiyor, hata yok, kullanici yalnizca
            bozuk telaffuz duyuyor ve sebebi hicbir yerde gorunmuyor.
            Ilk kurulumda SORULMUYOR (kullanicinin karari): Ingilizce konusan
            kimse bu ayari gormek zorunda degil. Uyari sorun gercekten ortaya
            ciktigi anda beliriyor.
            KAPATILABILIR ve kapatma KALICI: kapatilamayan bir uyari, sorunu
            bilerek gormezden gelen kullaniciya kalici bir gurultu olurdu. */}
        {catalog?.speech_language_hint && (
          <div className="mb-2 flex items-start gap-2 rounded-md border border-(--theme-warm)/40 bg-(--theme-warm)/10 px-3 py-2 text-xs text-(--text-secondary)">
            <span className="flex-1">{catalog.speech_language_hint.message}</span>
            <Button onClick={() => void dismissSpeechHint()} size="sm" variant="ghost">
              Dismiss
            </Button>
          </div>
        )}
        {tts.map(item => (
          <VoiceRow
            clones={clones}
            item={item}
            key={item.id}
            onClone={onClone}
            onDevice={setDevice}
            onInstall={install}
            onKnob={setKnob}
            onSelect={select}
            onVoice={setVoice}
            pending={jobs[item.id] ?? null}
          />
        ))}
      </SettingsSection>

      <SettingsSection icon={Keyboard} title="Voice controls">
        <NotchShortcutRow />
        <PushToTalkRow />
        <WakeEngineRow />
        <WakePhraseRow />
      </SettingsSection>

      <SettingsSection icon={Mic} title="Speech to text">
        {stt.map(item => (
          <VoiceRow
            clones={clones}
            item={item}
            key={item.id}
            onClone={onClone}
            onDevice={setDevice}
            onInstall={install}
            onKnob={setKnob}
            onSelect={select}
            onVoice={setVoice}
            pending={jobs[item.id] ?? null}
          />
        ))}
      </SettingsSection>

      {catalog?.voice_dir && (
        <div className="flex items-center gap-2 pt-1 text-[0.68rem] text-muted-foreground">
          <Download className="size-3.5" />
          <span className="font-mono">{catalog.voice_dir}</span>
        </div>
      )}
    </SettingsContent>
  )
}
