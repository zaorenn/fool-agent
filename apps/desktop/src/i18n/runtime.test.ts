import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import { fieldCopyForSchemaKey } from '@/app/settings/field-copy'

import { catalogFor, ensureLocaleCatalog } from './catalog'
import { setRuntimeI18nLocale, translateNow } from './runtime'
import type { Locale } from './types'
import { zh } from './zh'

/**
 * Dili SEÇ ve kataloğunun İNMESİNİ bekle.
 *
 * İngilizce dışındaki kataloglar artık istendiğinde yükleniyor: beşini birden
 * açılışa bağlamak, gerçek yapıda ölçülen 599,8 KB'lık bir parçayı hiç
 * okunmayacak dört dil için de ayrıştırmak demekti. ``setRuntimeI18nLocale``
 * yüklemeyi başlatıyor; sınavlar senkron olduğu için burada bekleniyor.
 *
 * Beklemeden okumak yanlış DEĞİL, yalnızca erken: ``catalogFor`` katalog
 * inene kadar İngilizce dönüyor -- eksik anahtar davranışının aynısı.
 */
async function useLocale(locale: Locale): Promise<void> {
  setRuntimeI18nLocale(locale)
  await ensureLocaleCatalog(locale)
}

describe('desktop i18n runtime translator', () => {
  beforeEach(() => {
    setRuntimeI18nLocale('en')
  })

  afterEach(() => {
    setRuntimeI18nLocale('en')
  })

  it('translates string paths for the active runtime locale', async () => {
    await useLocale('zh')

    expect(translateNow('boot.ready')).toBe('The Fool 桌面版已就绪')
    expect(translateNow('notifications.voice.noSpeechDetected')).toBe('没有检测到语音')
    expect(translateNow('composer.lookupNoMatches')).toBe('没有匹配项。')
    expect(translateNow('assistant.tool.statusRecovered')).toBe('已恢复')
  })

  it('passes arguments to function translations', () => {
    expect(translateNow('notifications.updateReadyMessage', 2)).toBe('2 new changes available.')
  })

  it('translates migrated overlap keys for newly supported locales', async () => {
    await useLocale('ja')
    expect(translateNow('common.save')).toBe('保存')

    await useLocale('zh-hant')
    expect(translateNow('cron.promptPlaceholder')).toBe('代理每次執行時應做什麼？')
  })

  it('translates settings copy for newly supported locales', async () => {
    await useLocale('ja')
    expect(translateNow('settings.appearance.title')).toBe('外観')
    expect(translateNow('settings.nav.providers')).toBe('プロバイダー')

    await useLocale('zh-hant')
    expect(translateNow('settings.appearance.title')).toBe('外觀')
    expect(translateNow('settings.nav.providerApiKeys')).toBe('API 金鑰')

    await useLocale('ar')
    expect(translateNow('settings.appearance.reasoningCollapsedTitle')).toBe('طي التفكير افتراضيًا')
    expect(translateNow('settings.appearance.reasoningCollapsedDesc')).toBe(
      'أبقِ التفكير المتدفق متاحًا دون توسيعه حتى تفتحه.'
    )
  })

  it('keeps translated settings field copy addressable from schema keys', () => {
    const field = ['display', 'show_reasoning'].join('.')

    expect(fieldCopyForSchemaKey(zh.settings.fieldLabels, field)).toBe('推理过程块')
    expect(fieldCopyForSchemaKey(zh.settings.fieldDescriptions, field)).toBe('当后端提供推理内容时予以显示。')
  })

  it('falls back to English when the active locale cannot resolve a key', async () => {
    await ensureLocaleCatalog('ja')

    const boot = catalogFor('ja').boot as { ready?: string }
    const originalReady = boot.ready

    try {
      boot.ready = undefined
      setRuntimeI18nLocale('ja')

      expect(translateNow('boot.ready')).toBe('The Fool Desktop is ready')
    } finally {
      boot.ready = originalReady
    }
  })

  it('returns the key when no locale can resolve a path', async () => {
    await useLocale('zh')

    expect(translateNow('missing.path')).toBe('missing.path')
  })
})
