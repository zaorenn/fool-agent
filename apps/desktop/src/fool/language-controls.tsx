/**
 * Cevap dili + konuşma dili — ARAYÜZDEN, modele söylemeden.
 *
 * Neden var
 * ---------
 * İstenen (kullanıcının kendi ifadesi): "arayüzde sohbetlerin sağ üstünde hem
 * cevap dilini hem ses dilini değiştirebilelim, illa modele söyleyip
 * değiştirmemize gerek kalmasın."
 *
 * İki ayar zaten vardı ve model onları ``set_language_mode`` aracıyla
 * değiştirebiliyordu; ama tek yol modele söylemekti. Bu, basit bir tercihi bir
 * sohbet turuna ve aracın doğru çağrılmasına bağımlı kılıyordu.
 *
 * Neden AÇILIR PANEL, neden iki açılır liste değil
 * ------------------------------------------------
 * İlk yazımda iki ``<select>`` doğrudan başlık çubuğuna konuldu. Ölçülen sonuç:
 * o şerit yalnızca ikon düğmeleri için boyutlanmış -- iki liste kümeyi
 * genişletip yanındaki düğmelerin üstüne bindi ve KULLANICI ARTIK HİÇBİRİNE
 * TIKLAYAMADI. Bir ayarı erişilebilir yapmak için çalışan düğmeleri
 * kaybetmek kabul edilemez.
 *
 * Şimdi başlık çubuğunda tek bir ikon var -- komşularıyla aynı genişlik --
 * ve ayarlar açılır panelde, nefes alacak yerleriyle duruyor.
 *
 * İki ayarın AYRI olması kasıtlı
 * ------------------------------
 * ``reply`` ekranda okunan dil, ``speech`` hoparlörden çıkan dil. Kullanıcı
 * cevabı anlayabilmek için İngilizce, sesi Japonca isteyebiliyor. Tek anahtar
 * olsalardı biri diğerini kaybettirirdi.
 *
 * Zone A: upstream bu dosyayı bilmiyor.
 */

import { useCallback, useEffect, useState } from 'react'

import { titlebarButtonClass } from '@/app/shell/titlebar'
import { TitlebarIcon } from '@/app/shell/titlebar-icon'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { cn } from '@/lib/utils'

import { type LanguageSettings, voiceApi } from './voice-api'

/** ``auto``/``same`` gerçek dil kodu DEĞİL: listede ayrı durmalılar. */
const AUTO = 'auto'
const SAME = 'same'

interface Option {
  code: string
  name: string
}

export interface LanguageControlsProps {
  /** Yükleme başarısız olursa çağrılır — çağıran taraf kontrolü gizleyebilir. */
  onUnavailable?: () => void
}

export function LanguageControls({ onUnavailable }: LanguageControlsProps) {
  const [settings, setSettings] = useState<LanguageSettings | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<null | string>(null)

  // ``onUnavailable`` KARARLI OLMAK ZORUNDA -- cagiran taraf onu bir
  // ``useCallback`` icinde veriyor (bkz. ``titlebar-controls.tsx``).
  //
  // Olculen hata: once satir ici bir ok islevi olarak veriliyordu, yani her
  // cizimde YENI bir kimlik. Baslik cubugu ise sik ciziliyor --
  // ``useModifierHeld`` her Ctrl/Alt basisinda ve birakisinda durum
  // guncelliyor. Bu etki bagimlilik listesinde o islevi tasidigi icin HER
  // CIZIMDE yeniden kosuyor ve her kosu bir ``GET /api/fool/voice/language``
  // demek: kullanici Ctrl'ye basili tuttugu surece arka uca istek yagmuru.
  //
  // Cozum cagiran tarafta: kararli bir kimlik burada etkiyi ACILISTA BIR KEZ
  // kosturuyor. Sonraki degisiklikler zaten ``update`` uzerinden, sunucunun
  // dondurdugu degerle yaziliyor.
  useEffect(() => {
    let alive = true

    voiceApi
      .language()
      .then(value => {
        if (alive) {
          setSettings(value)
        }
      })
      .catch(() => {
        if (alive) {
          onUnavailable?.()
        }
      })

    return () => {
      alive = false
    }
  }, [onUnavailable])

  const update = useCallback(async (patch: { reply_language?: string; speech_language?: string }) => {
    // İYİMSER GÜNCELLEME YOK.
    //
    // Yazma başarısız olursa açılır liste yeni değeri gösterip yapılandırma
    // eskisinde kalırdı: panel yalan söyler ve kullanıcı sebebini hiçbir
    // yerden göremez. Sunucunun döndürdüğü değer tek doğru kaynak.
    setBusy(true)
    setError(null)

    try {
      const next = await voiceApi.setLanguage(patch)

      setSettings(current => ({
        languages: current?.languages,
        reply_language: next.reply_language,
        speech_language: next.speech_language
      }))
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not change the language')
    } finally {
      setBusy(false)
    }
  }, [])

  if (!settings) {
    return null
  }

  const languages: Option[] = settings.languages ?? []
  // Varsayılandan sapan bir ayar varsa ikon bunu göstermeli: açılır paneli
  // açmadan "bir şey ayarlı mı" sorusunun cevabı görünür olmalı.
  const active = settings.reply_language !== AUTO || settings.speech_language !== SAME

  return (
    <Popover>
      <PopoverTrigger
        aria-label="Reply and voice language"
        className={cn(titlebarButtonClass, 'bg-transparent select-none', active && 'text-amber-400')}
        data-testid="language-controls-trigger"
        title="Reply and voice language"
      >
        <TitlebarIcon name="globe" />
      </PopoverTrigger>

      <PopoverContent align="end" className="w-72 space-y-3" data-testid="language-controls">
        <LanguagePicker
          disabled={busy}
          extraLabel="Match me"
          extraValue={AUTO}
          hint="The language your replies are WRITTEN in."
          label="Reply"
          onChange={value => void update({ reply_language: value })}
          options={languages}
          value={settings.reply_language}
        />

        <LanguagePicker
          disabled={busy}
          extraLabel="Same as reply"
          extraValue={SAME}
          hint="The language the voice SPEAKS. The written reply is not translated."
          label="Voice"
          onChange={value => void update({ speech_language: value })}
          options={languages}
          value={settings.speech_language}
        />

        {error === null ? null : (
          <p className="text-xs text-destructive" role="alert">
            {error}
          </p>
        )}
      </PopoverContent>
    </Popover>
  )
}

interface PickerProps {
  disabled: boolean
  /** ``auto``/``same`` gibi dil olmayan seçenek. */
  extraLabel: string
  extraValue: string
  hint: string
  label: string
  onChange: (value: string) => void
  options: Option[]
  value: string
}

function LanguagePicker({ disabled, extraLabel, extraValue, hint, label, onChange, options, value }: PickerProps) {
  return (
    <div className="space-y-1">
      <span className="text-xs font-medium">{label}</span>

      <Select disabled={disabled} onValueChange={onChange} value={value}>
        <SelectTrigger aria-label={label} className="h-8 w-full text-xs">
          <SelectValue />
        </SelectTrigger>

        <SelectContent>
          <SelectItem value={extraValue}>{extraLabel}</SelectItem>

          {options.map(option => (
            <SelectItem key={option.code} value={option.code}>
              {option.name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <p className="text-[11px] leading-snug text-muted-foreground">{hint}</p>
    </div>
  )
}
