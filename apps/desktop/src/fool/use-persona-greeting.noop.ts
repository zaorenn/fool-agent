/**
 * Tanışma selamının YAYINLANAN yapıdaki hâli — bkz. ``use-persona-greeting.ts``.
 *
 * Gerekçe ``relationship-bar.noop.tsx``te yazılı: bayrağı bileşenin içinde
 * kontrol etmek özelliği çalışmaz yapıyor ama paketten ÇIKARMIYOR. Takas modül
 * düzeyinde, yani gerçek kanca içe aktarım grafiğine hiç girmiyor.
 *
 * Zone A: upstream bu dosyayı bilmiyor.
 */

export function usePersonaGreeting(_active: boolean): void {
  // Yayinlanan yapida eslik kipi YOK.
}
