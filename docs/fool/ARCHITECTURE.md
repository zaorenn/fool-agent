# The Fool — Upstream-Güvenli Mimari

Bu belge tek bir soruyu cevaplar:

> **Ben yeni özellikler eklerken (ses klonlama, özelleştirilebilir temalar, sesli
> sohbet için notch/popup), `git merge upstream/main` bunları nasıl bozmaz?**

## Temel ilke

Git çakışması **yalnızca iki tarafın aynı satırları değiştirdiği yerde** olur.
Upstream'in hiç dokunmadığı bir dosyada çakışma **matematiksel olarak imkânsızdır.**

Bu yüzden strateji şudur: kodun %95'i upstream'in adını bile bilmediği dosyalarda
yaşar; upstream dosyalarına dokunduğumuz yerler **sayılabilir, tek satırlık ve
kayıt altında** olur.

---

## Üç bölge

### Bölge A — Fool'a ait (çakışma riski: sıfır, kalıcı)

Upstream'de `fool` adında hiçbir dizin yok ve olmayacak. Buraya yazdığın hiçbir
şey hiçbir merge'de çakışmaz.

```
fool/                              # Python: ajan tarafı kodun
  __init__.py
  branding.py                      # markanın TEK kaynağı
  voice/                           # ses klonlama motoru
plugins/tts/fool-voice/            # TTS sağlayıcı eklentisi (upstream'in ABC'si, senin implementasyonun)
apps/desktop/src/fool/             # React: masaüstü arayüzün
  branding.ts                      # marka dönüştürücü
  themes/                          # tema tanımların
  overlay/                         # notch/popup arayüzü
apps/desktop/electron/fool/        # Electron ana süreç: kendi pencerelerin
  overlay-window.ts                # desen: upstream'in link-title-window.ts'i
docs/fool/                         # dokümanların
  SEAMS.md                         # dikiş kayıt defteri
tests/fool/                        # koruma testlerin
```

### Bölge B — Uzantı noktaları (çakışma riski: sıfır, upstream kodu hiç düzenlenmez)

Hermes zaten **katkı-güdümlü** tasarlanmış. `apps/desktop/src/contrib/registry.ts`
merkezî bir kayıt defteri ve **çekirdek kendi yüzeylerini tıpkı bir eklenti gibi
kaydediyor.** Yani eklenti yolu ikinci sınıf değil, gerçek yol.

| İstediğin özellik | Kullanılacak mekanizma | Düzenlenen upstream dosyası |
|---|---|---|
| **Ses klonlama** | `TTSProvider` ABC + `PluginContext.register_tts_provider()` | **yok** |
| **Özelleştirilebilir temalar** | `THEMES_AREA` katkısı + `themes/user-themes.ts` | **yok** |
| Yeni panel | `PANES_AREA` | **yok** |
| Yeni sayfa + kenar çubuğu | `ROUTES_AREA`, `SIDEBAR_NAV_AREA` | **yok** |
| Komut paleti + kısayol | `PALETTE_AREA`, `KEYBINDS_AREA` | **yok** |
| Yazı alanı eklentisi | `COMPOSER_AREAS` | **yok** |
| Durum/başlık çubuğu | `STATUSBAR_AREAS`, `TITLEBAR_AREAS` | **yok** |
| Konuşma tanıma | `transcription_provider.py` ABC | **yok** |
| Model sağlayıcı | `model-provider-plugin` | **yok** |

> Ses klonlama için özel not: `agent/tts_provider.py` diyor ki *"None ship in-tree
> as of issue #30398 — the hook is additive infrastructure waiting for a real
> consumer."* Yani bu kanca **tam da senin gibi bir kullanıcı için** hazır
> bekliyor. Sıfır çakışma, sıfır upstream düzenlemesi.

### Bölge C — Dikişler (seams) — tek gerçek risk alanı

Bazı şeyler eklenti olamaz. Bunlar sayılır, kayıt altına alınır, testle korunur.

**Kural:** mantık her zaman Bölge A'daki bir dosyadadır; upstream dosyası
**yalnızca bir import + bir çağrı** alır.

#### Bilinen dikişler

**1. `i18n-brand` — marka dönüşümü (en önemlisi)**

`apps/desktop/src/i18n/catalog.ts` yalnızca **14 satır**:

```ts
// FOOL-SEAM: i18n-brand
import { applyFoolBrand } from '../fool/branding'

export const TRANSLATIONS: Record<Locale, Translations> = applyFoolBrand({
  en, zh, 'zh-hant': zhHant, ja, ar
})
```

Bu iki satır, `en.ts` içindeki **141 "Hermes" geçişini ve tüm dillerdeki
karşılıklarını** aynı anda halleder. Daha önemlisi: bu bir *kopya* değil bir
*dönüşüm* olduğu için, upstream yarın "Hermes" içeren 50 yeni metin eklerse
**onlar da otomatik olarak The Fool olur.** Bakım maliyeti sıfır.

Aynı desen Python tarafında `locales/*.yaml` için uygulanır (Türkçe `tr.yaml`
zaten mevcut).

**2. `overlay-window` — sesli sohbet notch/popup'ı**

Bu, eklenti SDK'sının yapamadığı tek şey: gerçek bir Electron `BrowserWindow`
gerekiyor (çerçevesiz, her zaman üstte, ekran kenarına yapışık). Pencere
oluşturma ana süreçte olmak zorunda.

`apps/desktop/electron/main.ts` **11.500+ satır** — bu dosyaya asla açılıp
düzenleme yapılmaz. Bunun yerine:

- Tüm mantık → `apps/desktop/electron/fool/overlay-window.ts`
  (desen olarak upstream'in kendi `link-title-window.ts`'i birebir örnek alınır —
  o da ayrı bir dosyada kendi `BrowserWindow`'unu kuruyor)
- `main.ts`'e giren tek şey: bir import + uygulama hazır olduğunda bir çağrı.

**3. `brand-dist` — dağıtım kimliği**

`apps/desktop/package.json`: `appId`, `productName`, `executableName`, protokol
şeması. Bunlar upstream'de nadiren değişir, çakışsa bile çözümü üç saniyelik.

**4. `update-origin` — güncelleme adresi**

`fool_cli/update_cmd.py:1600` (`OFFICIAL_REPO_URL`) ve
`fool_cli/banner.py:141` (`_UPSTREAM_REPO_URL`) → senin repona çevrilir.
Kullanıcıların güncellemeyi senden alması bu.

---

## Dikiş kayıt defteri ve koruma

Her dikişin yanında greplenebilir bir işaret durur:

```
FOOL-SEAM: <id>
```

Merge sonrası tek komut sana neyin hayatta kaldığını söyler:

```bash
grep -rn "FOOL-SEAM" --exclude-dir=.git .
```

`docs/fool/SEAMS.md` her dikişi listeler: dosya, ne, neden, merge'de kaybolursa
nasıl geri konur.

`tests/fool/` altındaki testler dikiş sessizce kaybolursa **kırmızı yanar.** Bu
kritik: en tehlikeli senaryo çakışma değil, çakışmanın *sessizce* upstream lehine
çözülüp markanın geri gelmesidir.

---

## Merge protokolü

```bash
git fetch upstream
git merge upstream/main
npm run fool:verify        # dikiş + marka + özellik testleri
```

Çakışma çıkarsa yalnızca Bölge C'de çıkar — yani sayısı bir elin parmaklarını
geçmeyen, ne olduğunu bildiğin satırlarda.

---

## Neden derin yeniden adlandırma yapmıyoruz

`fool_cli` → `fool_cli`, `HERMES_*` → `THEFOOL_*` cazip görünür ama sonucu
şudur: neredeyse her dosya değişir → **her merge her yerde çakışır** → bir süre
sonra merge etmeyi bırakırsın → korumak istediğin zekâyı tam da bu yüzden
kaybedersin.

Kullanıcı `fool_cli` yazısını hiçbir yerde görmez. Gördüğü her şey — uygulama
adı, ikon, tema, metinler, komut adı, kurulum sihirbazı, güncelleme kaynağı —
The Fool'dur. Görünmeyen iç isimler, upstream'e açık kalan kapıdır.

Bu, bir maliyet değil; **fork'un hayatta kalma mekanizmasıdır.**
