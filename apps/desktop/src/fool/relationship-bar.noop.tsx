/**
 * İlişki barının YAYINLANAN yapıdaki hâli — bkz. ``relationship-bar.tsx``.
 *
 * Neden ayrı bir dosya, neden bayrak yetmedi
 * ------------------------------------------
 * Önce ``COMPANION_BUILD`` sabiti bileşenin İÇİNDE kontrol ediliyordu. Bayrak
 * derleme zamanında ``false`` oluyordu ve bar hiç çizilmiyordu -- ama gövdesi
 * paketin içinde duruyordu. Ölçüldü: yayınlanacak pakette ``Not met yet`` ve
 * ``thing unresolved`` metinleri aranınca bulunuyordu.
 *
 * "Çalışmıyor" ile "yok" aynı şey değil ve istenen ikincisiydi: paketi açan
 * biri özelliğin metinlerini okuyabiliyorsa o özellik oradadır.
 *
 * Bu yüzden takas MODÜL düzeyinde: ``vite.config.ts`` yayınlanan yapıda bu
 * dosyayı koyuyor ve gerçek bileşen içe aktarım grafiğine hiç girmiyor.
 * Aynı kalıp ``src/debug/dev-only`` için de kullanılıyor.
 *
 * Zone A: upstream bu dosyayı bilmiyor.
 */

import type { RelationshipSnapshot } from './relationship-view'

export function RelationshipBar() {
  return null
}

export async function fetchRelationship(): Promise<null | RelationshipSnapshot> {
  return null
}
