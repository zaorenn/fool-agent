/**
 * Chat ↔ Cowork anahtarı — kenar çubuğunun tepesinde.
 *
 * ``Cowork`` uygulamanın bugünkü hâli. ``Chat`` hızlı konuşmak için: model
 * okuyabiliyor (web, dosya, geçmiş, hafıza) ama hiçbir şeyi değiştiremiyor, ve
 * kenar çubuğu sohbetlere iniyor.
 *
 * DEĞİŞİM ONAY İSTİYOR ve sebebi görünür: araç kümesi değişince ağ geçidi canlı
 * ajanı bırakıyor, yani değişimden sonraki ilk cevap önbelleksiz geliyor
 * (bkz. ``fool/session_scope.py`` ve ``store/chat-mode.ts``). Sessizce yapmak,
 * kullanıcının sebebini anlamadığı yavaş bir tur demekti.
 *
 * Görünüm bilerek SADE: mevcut kenar çubuğu satırlarının diliyle aynı. Burası
 * yeni bir tasarım önermiyor, var olan kabuğa bir satır ekliyor.
 *
 * Zone A: upstream bu dosyayı bilmiyor.
 */

import { useStore } from '@nanostores/react'
import { useState } from 'react'

import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { triggerHaptic } from '@/lib/haptics'
import { cn } from '@/lib/utils'
import { $newChatMode, type ChatMode, modeOfSession, setSessionMode } from '@/store/chat-mode'
import { notifyError } from '@/store/notifications'
import { $selectedStoredSessionId, $sessions } from '@/store/session'

const MODES: ReadonlyArray<{ id: ChatMode; label: string; title: string }> = [
  {
    id: 'chat',
    label: 'Chat',
    title: 'Fast conversation. Reads the web, your files and past chats — changes nothing.'
  },
  {
    id: 'cowork',
    label: 'Cowork',
    title: 'The full agent: terminal, file edits, browser, delegation.'
  }
]

export function ChatModeSwitch() {
  const selected = useStore($selectedStoredSessionId)
  // ``$sessions`` OKUNUYOR ama kullanılmıyor gibi görünebilir: kip oturumun
  // ``source``undan çıkıyor ve o alan bu atomda yaşıyor. Abone olmadan,
  // kip değiştikten sonra anahtar eski hâlinde kalırdı.
  useStore($sessions)

  const newChatMode = useStore($newChatMode)
  // Acik sohbet varsa ONUN kipi; yoksa yeni sohbet tercihi. Sohbet yokken
  // ``cowork`` varsaymak, kullanicinin sectigi kipi anahtarda gostermemek
  // olurdu -- secim yapilmis ama gorunmuyor.
  const mode = selected ? modeOfSession(selected) : newChatMode
  const [pending, setPending] = useState<ChatMode | null>(null)

  const request = (next: ChatMode) => {
    triggerHaptic()

    if (next === mode) {
      return
    }

    // Acik sohbet YOKSA onaylanacak bir bedel de yok: yeniden kurulacak bir
    // ajan yok, tercih bir sonraki sohbette gecerli olacak. Burada da diyalog
    // gostermek, bedeli olmayan bir secim icin kullaniciyi durdurmak olurdu.
    if (!selected) {
      $newChatMode.set(next)

      return
    }

    setPending(next)
  }

  return (
    <>
      <div
        aria-label="Chat or Cowork"
        className="mb-1.5 flex items-center gap-px rounded-md bg-(--ui-fill-quinary) p-px"
        role="group"
      >
        {MODES.map(item => (
          <button
            aria-pressed={mode === item.id}
            className={cn(
              'flex-1 rounded-[calc(var(--radius-sm)-1px)] px-2 py-1 text-[0.75rem] font-medium transition-colors',
              mode === item.id
                ? 'bg-(--ui-bg-card) text-(--ui-text-primary) shadow-[0_1px_2px_rgba(0,0,0,0.06)]'
                : 'text-(--ui-text-tertiary) hover:text-(--ui-text-secondary)'
            )}
            key={item.id}
            onClick={() => request(item.id)}
            title={item.title}
            type="button"
          >
            {item.label}
          </button>
        ))}
      </div>

      <ConfirmDialog
        confirmLabel={pending === 'chat' ? 'Switch to Chat' : 'Switch to Cowork'}
        description={
          pending === 'chat'
            ? 'This conversation keeps its history, but the agent loses the terminal, file edits and the browser — it can still read. The next reply is a little slower while it reloads.'
            : 'This conversation gets the full agent back: terminal, file edits, browser. The next reply is a little slower while it reloads.'
        }
        dismissOnConfirm
        onClose={() => setPending(null)}
        onConfirm={async () => {
          if (!selected || !pending) {
            return
          }

          try {
            await setSessionMode(selected, pending)
            // Yeni sohbetler de TAKIP etsin. Aksi halde anahtar "sifirlaniyor"
            // gibi gorunurdu: bu sohbeti Chat yaparsin, yeni sohbet acarsin ve
            // anahtar Cowork'e donmus olur.
            $newChatMode.set(pending)
          } catch (error) {
            // Depo değişikliği zaten geri aldı; kullanıcıya SÖYLENİYOR --
            // sessizce eski kipte kalmak, Chat sandığı bir sohbette modele
            // terminal vermek olurdu.
            notifyError(error, 'Could not switch mode')
          }
        }}
        open={pending !== null}
        title={pending === 'chat' ? 'Switch this chat to Chat mode?' : 'Switch this chat to Cowork mode?'}
      />
    </>
  )
}
