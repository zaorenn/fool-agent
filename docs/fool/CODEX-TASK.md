# Görev: sesli sohbeti gerçek bir konuşma deneyimine çevir + acımasız eksik denetimi

Bu dosya bir yapay zekâ kodlama ajanına verilecek görev tanımıdır. Kendi
kendine yeter: çalışma dizini, mimari kuralları, ölçülmüş sayılar ve bilinen
eksikler içindedir.

---

## 0. Çalışma alanı

```
Depo        : C:\thefool-desktop        (git, remote: origin = zaorenn/fool-agent)
Kurulu CLI  : %LOCALAPPDATA%\fool\hermes-agent   (aynı deponun git kopyası)
Backend venv: %LOCALAPPDATA%\fool\hermes-agent\venv
Geliştirme  : C:\thefool-desktop\.venv\Scripts\python.exe
Veri dizini : %LOCALAPPDATA%\fool         (config.yaml, .env, logs, sidecars, voices)
Platform    : Windows 11, PowerShell + Git Bash, RTX 4070 Ti SUPER (16 GB)
Model       : LM Studio :1234, qwen/qwen3.5-9b
```

Komutlar:

```bash
.venv/Scripts/python.exe -m pytest tests/fool/ -q      # 106 test
.venv/Scripts/python.exe -m fool.audit                 # marka denetimi
cd apps/desktop && npx tsc -p . --noEmit               # renderer tipleri
cd apps/desktop && npx tsc -p tsconfig.electron.json --noEmit
cd apps/desktop && npx eslint src/fool/
cd apps/desktop && npx vitest run --project ui src/fool/
fool update          # backend'i depodan günceller
fool desktop         # masaüstünü kaynaktan derler ve açar
```

**Değişikliği denemek için** `fool update && fool desktop` gerekir; masaüstü
uygulaması kurulu checkout'tan derleniyor.

---

## 1. Mimari kuralları — bunlara uy

Bu depo **NousResearch/hermes-agent** forku ve upstream birleştirmeleri sürecek.
Üç bölge var:

- **Zone A** — `fool/`, `apps/desktop/src/fool/`, `plugins/tts/fool-*`.
  Upstream bu yolları bilmiyor, çakışma imkânsız. **Yeni kod buraya.**
- **Zone B** — upstream'in kendi uzantı noktaları. Düzenleme yok.
- **Zone C** — upstream dosyalarındaki dikişler, `FOOL-SEAM: <id>` ile
  işaretli. Şu an **48 dikiş** var ve `tests/fool/test_branding.py` sayıyor.
  Yeni dikiş eklersen aynı yorumla işaretle ve teste ekle.

Yorumlar Zone A'da **Türkçe** yazılıyor ve *ne* değil *neden* anlatıyor.
Kullanıcıya görünen metinler **İngilizce** (uygulamanın varsayılan dili).

**Gizlilik:** API anahtarları ve kişisel bilgiler asla commit'e girmez. Sırlar
`%LOCALAPPDATA%\fool\.env` içinde, depo dışında. Commit öncesi
`git diff --cached` üzerinde jeton taraması yap.

---

## 2. Sesli sohbetin şu anki hâli

### Çalışan parçalar

`apps/desktop/src/fool/notch/` — ekranın üstünde macOS tarzı bir çentik.

- `Ctrl+Alt+V` bir **oturum** açar/kapatır (makineye göre değişir; aday
  merdiveninden ilk boş olan seçilir ve notch üzerinde yazılır)
- Oturum açıkken **sağ Ctrl** basılı tut → dinler, bırak → gönderir
- Wake word (`wake.detected`) de oturumu açar
- Cevap **akarken** seslendiriliyor (`startSpeechStream`, sadece yeni metin
  `append` ediliyor)
- Sağ Ctrl'ye basınca oynatma susuyor (araya girme)

`fool/engine_host.py` — TTS motorları **kalıcı süreçte**: bir kez açılır,
modeli bir kez yükler, stdin/stdout üzerinden JSON istek alır.

### Ölçülmüş gecikmeler (beş kelimelik cümle, CUDA)

| Motor | İlk çağrı | Sonraki |
|---|---|---|
| Kokoro | 7,6 sn | **0,08 sn** |
| Qwen3-TTS | 18,4 sn | 6,0 sn |
| Chatterbox | 58 sn | 28 sn |

STT (Whisper large-v3-turbo, 2,80 sn'lik kayıt): CPU 15,16 sn → **CUDA 0,23 sn**

Altı motorun hepsi kurulu ve `cuda_ready=True`.

---

## 3. GÖREV A — gerçek konuşma deneyimi

Şu anki akış **telsiz gibi**: bas, konuş, bırak, bekle, dinle. Bir insanla
konuşmaya benzemiyor. Hedef: karşılıklı, doğal, kesintisiz.

Eksik olanlar (kendi ölçümünü yap, bu listeyi doğrula ve genişlet):

1. **Sıra alma (turn-taking) yok.** Kullanıcı susunca sistem kendi anlamalı.
   Şu an tuş bırakmayı bekliyor. VAD (`use-voice-conversation.ts` içinde
   mevcut bir VAD döngüsü var — incele, yeniden yazma) ile bas-konuşu
   birleştirecek bir kip gerekiyor: **eller serbest mod**.

2. **Konuşurken araya girme yarım.** Sağ Ctrl'ye basınca susuyor, ama
   kullanıcı *konuşmaya başlayınca* (tuşa basmadan) susmuyor.
   `lib/voice-barge-in.ts` var, notch onu kullanmıyor.

3. **STT tur sonunda çalışıyor.** Kayıt bitmeden yazıya dökme başlamıyor;
   uzun cümlede saniyeler kaybediliyor. Akışlı STT (faster-whisper parça
   parça besleme) araştırılmalı.

4. **Düşünme sessizliği doldurulmuyor.** Model cevap üretirken 1-3 saniye
   tam sessizlik var; insan konuşmasında bu boşluk yok.

5. **Duraklama/nefes yok.** TTS metni tek blok okuyor; noktalama duraklamaya
   çevrilmiyor.

6. **Kesme sonrası bağlam kayboluyor.** Kullanıcı araya girip cümleyi
   bölerse, modelin yarım kalan cevabı bağlamda tutulmuyor.

7. **Konuşma sırası çakışması.** Aynı anda hem dinleme hem oynatma olabiliyor;
   mikrofon hoparlörü duyuyorsa yankı sorunu var (echo cancellation yok).

**Ölç, sonra tasarla.** Her iddianı sayıyla destekle; "daha hızlı hissettiriyor"
kabul edilmez.

---

## 4. GÖREV B — acımasız eksik denetimi

Uygulamanın **tüm** eksiklerini çıkar. Nazik olma; övgü isteme. Kural:

- Her bulgu **kanıtlı** olacak: dosya:satır, komut çıktısı, ölçüm ya da
  tekrar üretme adımı. "Muhtemelen yavaş" değil, "48,7 sn ölçtüm" .
- **Sessiz hatalara** öncelik ver: kullanıcının fark etmediği, hata vermeyen,
  ama yanlış olan şeyler. Bu depoda bugüne kadar en pahalı hatalar bunlardı:
  - Model "kurulu" görünüyordu, ağırlıkları inmemişti
  - Cihaz `cuda` yazıyordu, motor CPU'da koşuyordu
  - Sidecar izole sanılıyordu, `PYTHONPATH` sızıyordu
  - Açılış logosu "HERMES-AGENT" yazıyordu, metin taraması göremiyordu
    (harfler `█` karakterinden)
- Bulguları **etkiye göre** sırala, dosya sırasına göre değil.
- Düzeltebileceklerini düzelt; düzeltemediğini **neden** düzeltmediğini yaz.

Özellikle bakılacak alanlar:

- `fool/voice_models.py`, `fool/sidecar.py`, `fool/engine_host.py` — hata
  yolları, zaman aşımları, süreç sızıntısı
- `apps/desktop/src/fool/` — yarış durumları, odak yönetimi, bellek sızıntısı
- Platform güvenliği: `platform_toolsets` (telegram/whatsapp 6 araçla sınırlı;
  **diğer platformlar sınırsız** — discord, slack, sms, email, matrix… hepsi
  59 araçlık varsayılanda. Bu bir açık.)
- `fool update` yolu — arkadaş makinesinde birkaç kez takıldı
- CLI komut/gerçeklik uyumsuzluğu: ajan `fool telegram`, `fool gateway logs`
  gibi olmayan komutları deniyor

---

## 5. Bilinen açık eksikler (yeniden keşfetmene gerek yok)

1. **PDF/dosya üretimi WhatsApp'ta yok.** Dosya yazmak `file` takımını
   gerektiriyor, o da `read_file` getiriyor — yani tüm diski okutur.
   Gereken: yalnızca geçici çıktı klasörüne yazan, okuma yetkisi olmayan
   ayrı bir araç.
2. **Diğer mesajlaşma platformları kısıtsız** (yukarıda).
3. **Model başına test/dinleme düğmesi** ses panelinde yok.
4. **Telegram jetonu geçersiz** (401). Kullanıcı yenileyecek; senin işin değil.
5. **CUDA kütüphaneleri otomatik inmiyor** — panelden CUDA seçilince iniyor,
   ama varsayılan kurulumda yok.
6. **Chatterbox 28 sn** — difüzyon tabanlı, mimari değil model kaynaklı.
   Hızlandırılabilir mi, araştır (fp16, adım sayısı, derleme).

---

## 6. Bitirme koşulları

Aşağıdakilerin **hepsi** geçmeden "bitti" deme:

```bash
.venv/Scripts/python.exe -m pytest tests/fool/ -q       # tümü geçmeli
.venv/Scripts/python.exe -m fool.audit                  # ≤ 2 bulgu (ikisi kasıtlı)
cd apps/desktop && npx tsc -p . --noEmit                # çıkış 0
cd apps/desktop && npx tsc -p tsconfig.electron.json --noEmit
cd apps/desktop && npx eslint src/fool/                 # çıkış 0
cd apps/desktop && npx vitest run --project ui src/fool/
```

Ayrıca:

- Değiştirdiğin her davranış için **ölçüm** ver (önce/sonra).
- Yeni sessiz hata sınıfı kapattıysan **test** ekle.
- Uygulamayı gerçekten çalıştır (`fool desktop`) ve sesli turu **dene**;
  yalnızca birim testlerine güvenme.
- Commit mesajlarında *ne* değil **neden** anlat; ölçümü yaz.
- Sırları asla commit etme.

---

## 7. Bu görevde yapmayacakların

- Upstream dosyalarını gereksiz yere değiştirme (Zone C dikişleri sayılı).
- Marka dönüşümünü bozma (`fool/branding.py` ve `fool/audit.py` korumalı).
- `%LOCALAPPDATA%\hermes` (kullanıcının eski Hermes kurulumu) dizinine dokunma.
- Kullanıcının `.env` dosyasındaki değerleri okuyup bir yere yazma.
