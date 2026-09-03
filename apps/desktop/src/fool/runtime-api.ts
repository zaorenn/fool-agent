/**
 * Bellek yerleşimi ucu: seçili olmayan modeller bırakılsın.
 *
 * Neden arayüz tarafından tetikleniyor
 * ------------------------------------
 * Kullanıcının kuralı üç kategoride de aynı: aynı anda tek STT, tek TTS, tek
 * LLM -- ve biri değişince öncekisi tamamen bırakılsın. Ses tarafında bunu
 * sunucu kendi görüyor (``fool/voice_models.py::select`` seçimi kendisi
 * yazıyor), ama DİL MODELİNDE seçim sunucudan geçmiyor: LM Studio modeli
 * kendiliğinden, ilk istekte yüklüyor ve eskisini asla bırakmıyor.
 *
 * Ölçüldü (kullanıcının kartı, RTX 4070 Ti SUPER, 16 GB):
 *
 *     google/gemma-4-e4b   6,33 GB   <- seçili olan
 *     qwen/qwen3.5-9b      6,55 GB   <- gün boyu hiç istenmedi
 *     ------------------------------------
 *     toplam              12,88 GB, geriye ~3 GB
 *
 * Seslendirme motorları AYNI kartta; günlüklerde sonucu görünüyordu
 * (``device=cuda istendi ama CUDA bulunamadi``). Yani ikinci model, hiç
 * kullanılmadığı hâlde sesin GPU'sunu yiyor.
 *
 * Modeli DEĞİŞTİREN yüzey burası olduğu için tetik de burada: yoklama
 * gerekmiyor, ve yoklamamak bu işin bütün amacı.
 *
 * Zone A: upstream bu dosyayı bilmiyor.
 */

/** Sunucunun bıraktıklarını kategori kategori sayan cevabı. */
export interface RuntimeEnforceResult {
  total: number
  unloaded: Record<string, string[]>
}

/**
 * Seçili olmayan her modeli bırak (ateşle-unut).
 *
 * SONUÇ BEKLENMİYOR ve hata YUTULUYOR: bu bir temizlik. Bir bellek
 * temizliğinin başarısızlığını model değiştirme hatası olarak göstermek,
 * kullanıcıya çalışan bir şeyin bozulduğunu söylemek olurdu.
 *
 * Masaüstü köprüsü yoksa (tarayıcı) işlemsiz: orada bırakılacak yerel bir
 * model zaten yok.
 */
export function dropUnselectedModels(): void {
  const desktop = window.foolDesktop

  if (!desktop?.api) {
    return
  }

  void desktop
    .api({
      method: 'POST',
      path: '/api/fool/runtime/enforce',
      // ``lms unload`` bir alt süreç ve birkaç saniye sürebiliyor; varsayılan
      // 15 sn'lik köprü zaman aşımı bunun için kısa kalabilir.
      timeoutMs: 30_000
    })
    .catch(() => {
      // Bilerek sessiz -- yukarıdaki gerekçe.
    })
}
