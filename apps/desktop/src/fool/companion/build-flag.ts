/**
 * Eşlik kipi bu YAPIDA var mı.
 *
 * İstenen: eşlik kipi seçili değilse hiçbir şey görünmemeli, ve kurulumda ya
 * da publish sürümlerinde asla olmamalı, bu kısım sadece bu bilgisayara özel
 * kalmalı."
 *
 * Çalışma zamanı kapısı zaten vardı: özellik ``memory.recall.relationship``
 * kapalıyken hiçbir şey çizmiyor ve taze bir kurulumda o anahtar yok. Ama
 * "kapalı" ile "YOK" aynı şey değil -- kapalı bir şey açılabilir, ve
 * kullanıcının istediği ikincisi.
 *
 * Bu yüzden karar DERLEME ZAMANINDA veriliyor: yayınlanan pakette bu dosyanın
 * yerine ``build-flag.noop.ts`` geçiyor, sabit ``false`` oluyor ve arayüzün
 * tamamı ağaç sarsmayla paketten düşüyor. Yapılandırmayı elle düzenlemek bile
 * geri getirmiyor, çünkü kod orada değil.
 *
 * Takas ``vite.config.ts``te; aynı kalıp ``src/debug`` için de kullanılıyor.
 *
 * Zone A: upstream bu dosyayı bilmiyor.
 */

export const COMPANION_BUILD = true
