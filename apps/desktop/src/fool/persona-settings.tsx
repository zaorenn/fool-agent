/**
 * Persona seçimi — sesin kimliği ve uygulamanın rengi tek karar.
 *
 * Friend/Jarvis kiplerinin yerini bu aldı (kullanıcının kararı). Kipler araç
 * kümesini ayırıyordu; ses artık doğrudan açık sohbete konuştuğu için ayıracak
 * bir kapsam kalmadı. Geriye seçilmeye değer olan şey kaldı: KİM konuşuyor.
 *
 * Zone A: upstream bu dosyayı bilmiyor.
 */

import { useEffect, useState } from 'react'

import { ListRow, SettingsContent, SettingsSection } from '@/app/settings/primitives'
import { Volume2 } from '@/lib/icons'
import { notifyError } from '@/store/notifications'

import { voiceApi, type VoiceCatalog } from './voice-api'
import {
  applyAccent,
  canChangeVoice,
  idleClone,
  persistAccent,
  persona,
  PERSONAS,
  readAccent,
  speakingSummary,
  voiceForPersona
} from './voice/persona'

export function PersonaSettings() {
  const [active, setActive] = useState(() => readAccent())
  const [catalog, setCatalog] = useState<null | VoiceCatalog>(null)
  const [reload, setReload] = useState(0)

  useEffect(() => {
    let cancelled = false

    void voiceApi
      .catalog()
      .then(data => {
        if (!cancelled) {
          setCatalog(data)
        }
      })
      .catch(() => undefined)

    return () => {
      cancelled = true
    }
  }, [reload])

  const engine = (catalog?.items ?? []).find(item => item.kind === 'tts' && item.active) ?? null
  // Klon BASKA bir motorda duruyorsa kullanici bunu gormeli: aksi halde
  // klonladigi sesi hic duymaz ve sebebini hicbir yerde bulamaz.
  const stranded = idleClone(catalog?.items ?? [])

  const switchTo = async (entryId: string) => {
    try {
      await voiceApi.select(entryId)
      // Katalogu yeniden cek: "Speaking now" satiri eski motoru gosterirse
      // panel bir sey soyleyip baska bir ses duyulur -- bu kod tabaninda
      // yasanmis bir hata.
      setReload(token => token + 1)
    } catch (error) {
      notifyError(error, 'Could not switch the voice engine')
    }
  }

  const choose = async (id: string) => {
    const entry = persona(id)

    if (!entry) {
      return
    }

    setActive(id)
    applyAccent(entry.accent)
    persistAccent(id)

    // Motorun birden cok sesi varsa personanin sesini de uygula. Tek sesli
    // motorda yalnizca renk degisiyor ve panel bunu SOYLUYOR -- sessizce
    // yanlis bir ses secmek, gordugun ile duydugunun ayrismasi olurdu.
    if (!engine || !canChangeVoice(engine)) {
      return
    }

    const wanted = voiceForPersona(entry, engine.voices)

    if (!wanted || wanted === (engine.voice || '')) {
      return
    }

    try {
      await voiceApi.setVoice(engine.id, wanted)
    } catch (error) {
      notifyError(error, `Could not switch to ${entry.label}`)
    }
  }

  return (
    <SettingsContent>
      <SettingsSection icon={Volume2} title="Persona">
        <ListRow
          description="One choice sets both the voice and the app's accent colour."
          title="Who is speaking"
        />

        <div className="flex flex-wrap gap-2 px-1 pt-1 pb-2">
          {PERSONAS.map(entry => (
            <button
              className={`flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs transition-all duration-200 ${
                active === entry.id
                  ? 'border-(--theme-primary) bg-(--theme-primary)/10 text-(--text-primary)'
                  : 'border-(--stroke-nous)/70 text-muted-foreground hover:bg-(--surface-hover)'
              }`}
              key={entry.id}
              onClick={() => void choose(entry.id)}
              title={entry.summary}
              type="button"
            >
              <span className="size-3 rounded-full" style={{ background: entry.accent }} />
              {entry.label}
            </button>
          ))}
        </div>

        {engine && (
          <ListRow
            description={speakingSummary(engine)}
            title="Speaking now"
          />
        )}

        {stranded && (
          <ListRow
            action={
              <button
                className="rounded-md border border-(--stroke-nous)/70 px-2 py-1 text-xs hover:bg-(--surface-hover)"
                onClick={() => void switchTo(stranded.id)}
                type="button"
              >
                Use it
              </button>
            }
            description={`"${stranded.clone}" is cloned onto ${stranded.label}, which is not the engine speaking right now — so you never hear it.`}
            title="A cloned voice is sitting idle"
          />
        )}

        {engine && !canChangeVoice(engine) && (
          <ListRow
            description={
              engine.clone_capable
                ? 'This engine takes its voice from the clip you upload below, so a persona only changes the accent colour.'
                : `${engine.label} has a single fixed voice, so a persona only changes the accent colour.`
            }
            title="Voice comes from the engine"
          />
        )}
      </SettingsSection>
    </SettingsContent>
  )
}
