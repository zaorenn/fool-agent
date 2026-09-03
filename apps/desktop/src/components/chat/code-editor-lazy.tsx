/**
 * ``CodeEditor``ın TEMBEL kapısı.
 *
 * Neden
 * -----
 * CodeMirror çekirdeği (``@codemirror/state`` + ``view`` + ``language`` +
 * ``commands``) gerçek yapıda ölçüldü: 271 KB, kendi parçasında. Editör
 * açılış yolundaki iki yerden statik olarak içe aktarılıyordu -- profil
 * değiştirici (``app/chat/sidebar/profile-switcher.tsx``) ve dosya önizleme
 * (``app/chat/right-rail/preview-file.tsx``) -- yani hiçbir dosya açmayan,
 * hiçbir profil düzenlemeyen kullanıcı da her açılışta bedelini ödüyordu.
 *
 * İkisi de editörü ancak bir kullanıcı eylemiyle GÖSTERİYOR (bir panel
 * açılıyor, bir dosya seçiliyor). Yani modülün o ana kadar var olması
 * gerekmiyor.
 *
 * ``Suspense`` sınırı BURADA: çağıran ``<CodeEditor …/>`` yazmaya devam
 * ediyor ve kendi sınırını kurmak zorunda kalmıyor. Yer tutucu, editörün
 * kendi arka planıyla aynı yüzey -- gelirken bir boşluk parlamıyor.
 */

import { type ComponentProps, lazy, Suspense } from 'react'

import type { CodeEditor as CodeEditorType } from './code-editor'

export type { CodeEditorApi } from './code-editor'

const CodeEditorLazy = lazy(async () => ({ default: (await import('./code-editor')).CodeEditor }))

export function CodeEditor(props: ComponentProps<typeof CodeEditorType>) {
  return (
    <Suspense fallback={<div className="min-h-0 flex-1 bg-[var(--ui-editor-background,transparent)]" />}>
      <CodeEditorLazy {...props} />
    </Suspense>
  )
}
