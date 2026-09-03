# Dikiş Kayıt Defteri (SEAMS)

Bu dosya, The Fool'un upstream (`NousResearch/hermes-agent`) dosyalarına
dokunduğu yerleri listeler. Başka hiçbir yerde upstream kodu değişmez.

**Tam envanter bu dosya değil**, `tests/fool/test_branding.py::EXPECTED_SEAMS`.
Kayıt orada çünkü orası kırılabiliyor: iki yönlü bir muhafız her dikişin hem
ağaçta hem kayıtta olmasını zorluyor, yani liste bayatlayamıyor. Aşağıdaki
tablolar riskli olanları **nesir olarak** açıklar -- kaybolursa ne olduğunu bir
merge'in ortasında okuyabilesin diye. Tümünü görmek için:

```bash
git grep -h -o "FOOL-SEAM: [a-z0-9-]\+" | sort -u
```

Amaç: `git merge upstream/main` sonrasında neyin risk altında olduğunu tahmin
etmek zorunda kalmamak.

## Nasıl kontrol edilir

Merge sonrası, sırayla:

```bash
grep -rn "FOOL-SEAM" --exclude-dir=.git --exclude-dir=node_modules .
```

Sonra koruma testleri — bir dikiş sessizce kaybolduysa burası kırmızı yanar:

```bash
python -m pytest tests/fool/ -q
```

En tehlikeli senaryo çakışma değil; çakışmanın **sessizce** upstream lehine
çözülüp markalaşmanın geri alınmasıdır. Testler tam bunun için var.

## Dikişler

### Markalaşma — dönüşümler

Bunlar tek tek metin düzenlemesi değil, **dönüşüm**. Upstream yeni metin
eklediğinde onlar da otomatik markalanır; bakım maliyeti sıfır.

| id | Dosya | Ne yapar |
|----|-------|----------|
| `i18n-brand` | `apps/desktop/src/i18n/catalog.ts` | Masaüstü çeviri kataloğunun tamamı `applyFoolBrand()`'den geçer. Tek satır, 141+ metin, tüm diller. |
| `argparse-brand` | `fool_cli/__init__.py` | argparse'ın metin kabul ettiği 4 nokta sarmalanır → tüm `--help` çıktısı. Yalnızca yardım metnine dokunur; argüman adları/`dest`/`choices` ellenmez. |
| `command-descriptions` | `fool_cli/commands.py` | `CommandDef.__post_init__` tüm `/help` açıklamalarını markalar. |

### Markalaşma — noktasal

| id | Dosya | Kaybolursa |
|----|-------|------------|
| `wordmark` | `apps/desktop/src/components/chat/intro.tsx` | Açılış ekranında "HERMES AGENT" yazar |
| `html-title` | `apps/desktop/index.html` | Sekme/pencere başlığı "Hermes" olur |
| `version-banner` | `fool_cli/_startup_fast.py`, `banner.py`, `cli.py` | Sürüm satırı "Hermes Agent v…" olur |
| `prog-name` | `fool_cli/_parser.py`, `console_engine.py` | `usage: hermes` yazar |
| `bot-display-name` | `apps/desktop/src/plugins/hermes-bots/plugin.js` | Varsayılan profil "Hermes" görünür |
| `theme-preset` | `apps/desktop/src/themes/presets.ts` | Crimson tema kaybolur, varsayılan `nous`a döner |
| `default-mode` | `apps/desktop/src/themes/context.tsx` | Uygulama açık modda açılır, crimson kimlik zayıflar |
| `brand-mark` | `apps/desktop/src/components/brand-mark.tsx` | Hakkında/güncelleme rozeti `nous-girl.jpg`'e döner (işaret: `public/fool-mark.svg`) |

### Ses ve çentik

Kullanıcının en çok kullandığı yol. Bunlar kaybolursa uygulama açılır ama
konuşmaz -- sessiz sınıf: hata yok, yalnızca hiçbir şey olmuyor.

| id | Dosya | Kaybolursa |
|----|-------|------------|
| `plugin-tts-config` | `tools/tts_tool.py` | Motora `config` hiç gitmez: klon sesi, cihaz ve ses seçimi sessizce yok sayılır, herkes varsayılan kadın sesiyle konuşur |
| `home-repair` | `apps/desktop/electron/main.ts` | Bozuk bir `FOOL_HOME` (silinmiş sandbox yolu) kör körüne kabul edilir; uygulama boş bir dizine açılır ve kullanıcı her şeyini kaybetmiş görünür |
| `runtime-dir-name` | `apps/desktop/electron/runtime-root.ts`, `main.ts`, `scripts/install.ps1`, `scripts/install.sh`, `fool/user_data.py`, `fool_cli/backup.py` | Runtime klasörü `hermes-agent` adında kalır: kullanıcı `where fool` çıktısında Hermes görür, ürün ayrı ama ad değil |
| `runtime-version` | `apps/desktop/electron/runtime-version.ts`, `bootstrap-runner.ts`, `main.ts` | Eski bir runtime "hazır" sayılır: yeni sürüm kurulur ama koşan kod eskidir — backend durur, terminalde "Hermes Agent" görünür. Ters yön de tehlikeli: her farkı "eski" saymak, güncel bir runtime'da HER AÇILIŞTA yükleyiciyi koşturur (`checkoutContainsCommit` + onarım damgası bunu kesiyor) |
| `bundled-installer` | `apps/desktop/electron/bootstrap-runner.ts`, `apps/desktop/package.json` | Kurulum betiği GitHub'dan indirilir: sürümdeki düzeltmeler çalışmaz (ağdaki eski dosya koşar) ve internet yoksa kurulum hiç başlamaz |
| `espeak-ascii-path` | `apps/desktop/electron/backend-env.ts`, `tools/tts_tool.py` | espeak-ng ASCII olmayan bir yolu açamıyor ve C tarafında `exit()` çağırıyor: TTS başarısız olmuyor, **bütün arka uç ölüyor**. Kullanıcı adında Türkçe harf olan her makinede on saniyede bir "backend stopped" — ve indirmeler, gateway, sohbet hepsi onunla gidiyor |
| `ipv4-loopback` | `fool/loopback.py`, `fool_cli/config.py` | `localhost` IPv6'ya çözülüp her istekte 2 sn zaman aşımı bekler; her mesaj iki saniye geç başlar |
| `engine-namespaced-config` | `tools/tts_tool.py` | Motora özel ses (`tts.<motor>.voice`) genel ayara ezdirilir |
| `speech-language` | `tools/tts_tool.py` | Konuşulan dil cevabın diline geri düşer: kullanıcı İngilizce okuyup Japonca duyamaz |
| `language-mode` | `fool/language_mode.py`, `agent/system_prompt.py`, `tools/tts_tool.py`, `fool_cli/config_defaults.py` | Model dil ayarlarını göremez ve değiştiremez: "ses dilini japonca yap" dendiğinde "tamam" der, hiçbir şey değişmez |
| `first-sentence-latency` | `tools/tts_streaming.py` | Ses ilk cümlede değil, tüm cevap bitince başlar; uzun cevaplarda dakikalarca sessizlik |
| `local-sentence-streaming` | `tools/tts_streaming.py` | Cümle cümle akış kapanır |
| `speech-pauses` | `tools/tts_streaming.py` | Duraklamalar kaybolur, konuşma robotlaşır |
| `voice-persona` | `fool/voice_models.py` | Persona ile ses/vurgu rengi birlikte değişmez |
| `one-voice` | `fool/voice_models.py` | Aynı anda birden çok motor yüklü kalır |
| `voice-routes` | `fool/voice_routes.py`, `fool_cli/web_server.py` | Arayüz ses modellerini listeleyemez/indiremez |
| `voice-models` | `apps/desktop/src/app/settings/index.tsx` | Ayarlarda ses modeli bölümü kaybolur |
| `voice-owner` | `apps/desktop/src/app/chat/composer/hooks/use-auto-speak-replies.ts` | Aynı cevabı iki yüzey birden okur |
| `shared-voice-policy` | `apps/desktop/src/app/chat/composer/hooks/use-voice-conversation.ts` | Çentik ve besteci ayrı kurallarla çalışır |
| `voice-session-bridge` | `apps/desktop/src/store/active-work.ts` | Ses `session_id: null` gider, cevap bot panelinde çıkar |
| `main-window-only-publisher` | `apps/desktop/src/store/*` | Çentiğin boş kopyası ana pencerenin değerini ezer |
| `relationship-bar` | `apps/desktop/src/app/chat/sidebar/index.tsx` | Persona ile aranda ne olduğu (neye kırgın, ne kadar yakın) hiçbir yerde görünmez |
| `persona-greeting` | `apps/desktop/src/app/chat/index.tsx` | Persona ilk sözü hiç söylemez; tanışma kullanıcının "selam" yazmasını bekler |
| `persona-kickoff` | `apps/desktop/src/lib/chat-messages.ts` | Uygulamanın gönderdiği tanışma çağrısı, kullanıcının yazdığı bir mesajmış gibi transkriptte görünür |
| `setup-voice` | `apps/desktop/src/components/onboarding/index.tsx` | Kurulumda ses modelleri indirilemez; yeni kullanıcı mikrofona basar ve hiçbir şey olmaz |
| `setup-voice-intro` | `apps/desktop/src/components/assistant-ui/thread/index.tsx` | Yerel model kendiliğinden bulunduğunda karşılama ekranı hiç görünmez ve ses kurulumu ulaşılamaz kalır |
| `notch-profile` | `apps/desktop/electron/main.ts` | Çentik birincil arka uca bağlanır; başka bir profildeki açık sohbeti göremez ve "No chat is open yet" der |
| `notch-opens-session` | `apps/desktop/src/app/contrib/wiring.tsx` | Açık sohbet yokken çentik konuşulanı atıp "önce pencerede bir sohbet aç" der |
| `notch-submits-through-main` | `apps/desktop/src/app/contrib/wiring.tsx` | Çentik kendi `prompt.submit`ini atar, composer'ın iyimser kullanıcı balonu hiç çizilmez ve konuşan kişi ekranda hiçbir şey görmez |
| `default-memory` | `plugins/memory/__init__.py` | Taze kurulum hafızasız çalışır; kullanıcı bunu ancak "neden hatırlamıyorsun" diye sorunca öğrenir |
| `shared-window-values` | `apps/desktop/electron/{main,preload}.ts`, `apps/desktop/src/fool/cross-window-atom.ts` | Paketlenmiş sürümde çentik ana pencerenin değerlerini hiç görmez (`file://` ayrı localStorage) |
| `voice-stop-bridge` | `apps/desktop/src/main.tsx` | Çentikten araya girmek sesi durdurmaz; ses başka bir pencerede çalmaya devam eder |
| `voice-warm-on-open` | `apps/desktop/src/main.tsx` | Motor yalnızca kullanıcı konuşmaya hazırlanınca ısınır; ilk cümle soğuk yüklemeyi bekler (ölçüldü: 36,8 sn) |
| `defer-browser-tools` | `scripts/install.ps1`, `apps/desktop/electron/bootstrap-runner.ts` | İlk açılış tarayıcı araçlarını bekler: tek başına 10 dk, toplam kurulum 20 dk+ |
| `accent-override` | `apps/desktop/src/themes/*` | Persona vurgu rengi uygulanmaz |
| `notch-window` / `notch-route` / `notch-ipc` / `notch-shortcut` / `notch-quit` / `notch-no-chrome` | `apps/desktop/electron/main.ts`, `preload.ts`, `app/contrib/*` | Çentik açılmaz ya da Ctrl+Alt+V ölür |
| `slow-voice-engine` | `fool/voice_models.py` | Gerçek zamandan yavaş motorlar listeye geri döner |
| `engine-vram-eviction` | `fool/engine_host.py` | LLM + TTS birlikte VRAM'i doldurur, iki iş aynı anda koşunca makine donar |
| `shared-gpu-budget` | `fool/engine_host.py` | Aynı sınıf, bütçe tarafı |
| `single-model-residency` | `apps/desktop/src/app/session/hooks/use-model-controls.ts` | Model değiştirilince eskisi LM Studio'da yüklü kalır; iki model kartı doldurur ve ses motorları CPU'ya düşer |
| `system-tray` | `apps/desktop/electron/main.ts` | Kapatma düğmesi uygulamayı bitirir (tepsiye inmez) ve çıkışta LM Studio'daki model VRAM'de kalır — uygulama kapalıyken kart dolu |

### Yapılandırma ve dayanıklılık

| id | Dosya | Kaybolursa |
|----|-------|------------|
| `dotted-name-containers` | `fool_cli/config.py` | Noktalı model kimlikleri (`qwen3.5`, `gpt-4.1`) anahtar bölünürken parçalanır; `fool config set` "✓ Set" der, ayar hiç okunmaz |
| `os-text-encoding` | `agent/system_prompt.py` | Türkçe Windows'ta sistem istemi kurulamaz, ajan hiç cevap vermez |
| `context-floor` | `agent/agent_init.py` | 32K bağlamda çalışmayı reddeder |
| `release-repo-url` | `scripts/release.py` | Release upstream depoya gitmeye çalışır |
| `ready-token` | `fool_cli/web_server.py`, `apps/desktop/electron/backend-ready.ts`, `remote-lifecycle.ts`, `windows-remote-lifecycle.ts` | Backend `FOOL_BACKEND_READY port=<n>` yazar; masaüstü onu duymaz ve zaman aşımıyla ölür. Hata mesajı backend'i suçlu gösterir, oysa backend çalışıyordur. **ÜÇ ayrı kopya var** — toplu marka dönüşümü üçünü de atlayabiliyor; muhafız (`tests/fool/test_branding.py`) artık dosya adı değil DESEN arıyor. |

### Ajanın kendini tanıması

Kullanıcı "hangi uygulamayı kullanıyorum?" diye sorduğunda verilen cevap.
Arayüzdeki her yazı değişse bile bunlar değişmezse ajan kendini Hermes Agent
sanar — markalaşmanın en derin katmanı.

| id | Dosya | Ne yapar |
|----|-------|----------|
| `agent-identity` | `fool_cli/default_soul.py` | **En kritiği.** `SOUL.md`, `DEFAULT_AGENT_IDENTITY`'yi gölgeler — dosya varsa sabit hiç okunmaz. Eski Hermes metni `_LEGACY_TEMPLATE_SOULS`'a eklendi, böylece makine-serili dosya yerinde tazeleniyor. Kullanıcının elle yazdığı persona asla ellenmez. |
| `agent-identity` | `agent/prompt_builder.py`, `agent/system_prompt.py`, `agent/agent_init.py` | Kimlik metni, yardım rehberi, profil satırları, steer açıklaması |
| `agent-identity` | `agent/prompt_builder.py` → `brand_skill_index()` | Beceri dizini açıklamaları. **Beceri ADLARI dokunulmaz** — `skill_view(name='…')` ile çağrılıyorlar. |
| `agent-identity` | `model_tools.py` → `brand_tool_schemas()` | Araç şeması açıklamaları. Şemalar sistem promptundan **ayrı** gönderiliyor. **Araç adları, parametre anahtarları, enum, required dokunulmaz** — aksi halde model var olmayan aracı çağırır. |
| `anthropic-sanitize` | `agent/anthropic_adapter.py` | Anthropic OAuth ucuna giderken ürün adı "Claude Code" ile değiştirilir. Kimlik "Fool Agent" olunca eski replace listesi eşleşmiyordu; yeni adlar eklendi, yoksa upstream'in filtre-kaçınma koruması sessizce delinir. |
| `client-attribution` | `agent/anthropic_adapter.py`, `agent/auxiliary_client.py` | `X-Title` başlığı — sağlayıcılara giden istemci kimliği |

### Kimlik ve dağıtım

| id | Dosya | Kaybolursa |
|----|-------|------------|
| `cli-scripts` | `pyproject.toml` | Komut adı `hermes`e döner |
| `fool-packaging` | `pyproject.toml` | **`import fool` patlar — markalaşmanın TAMAMI çöker** |
| `home-dir` | `fool_constants.py` **ve** `apps/desktop/electron/main.ts` | Veri dizini `hermes`e döner ve kullanıcının kurulu Hermes'iyle çakışır |
| `bot-handle` | `apps/desktop/src/plugins/hermes-bots/plugin.js` (2 yer) | `@fool` hiçbir bota çözülmez |

### Nous bağlarının kesilmesi

| id | Dosya | Ne yapar |
|----|-------|----------|
| `update-origin` | `fool_cli/update_cmd.py` | Güncellemeler The Fool deposundan gelir. Kaybolursa kullanıcılar **sessizce upstream Hermes'e güncellenir** ve markalaşma silinir. |
| `banner-repo` | `fool_cli/banner.py` | Sürüm bağlantıları The Fool deposunu gösterir |
| `model-catalog` | `fool_cli/model_catalog.py` | Katalog sürümle gelir; her açılışta Nous'a istek gitmez |
| `diagnostics-endpoint` | `fool_cli/diagnostics_upload.py` | Loglar/sistem bilgisi hiçbir yere yüklenmez |
| `nous-account-commands` | `fool_cli/commands.py` | `/subscription`, `/topup` kaldırıldı (Nous hesabına özel faturalama) |

### İşaretsiz dikiş

`brand-dist` → `apps/desktop/package.json`
(`appId`, `productName`, `executableName`, protokol, dmg/nsis/mac/linux adları,
`publish` bloğu).

JSON yorum kabul etmediği için `FOOL-SEAM` işareti konamıyor. Bunun yerine
`tests/fool/test_branding.py::test_desktop_package_carries_fool_identity`
koruyor.

## İkili dikişler — dikkat

Üç dikiş **iki yeri birden** değiştirmek zorunda. Yalnızca birini değiştirmek
sessiz bozulma üretir:

- **`home-dir`** — Python ve Electron veri dizinini BAĞIMSIZ hesaplıyor.
  Ayrışırlarsa masaüstü uygulaması backend'ini bulamaz.
- **`bot-handle`** — `botHandle()` görünen etiketi, mention çözücüsü ise
  çağrıyı üretir. Ayrışırlarsa kullanıcının yazdığı `@fool` kimseye gitmez.
- **Marka sabitleri** — `fool/branding.py` ve `apps/desktop/src/fool/branding.ts`
  elle senkron tutulur.

Üçü de testle korunuyor.

## Kural

Yeni bir dikiş eklemek zorunda kaldığında:

1. Mantığı **`fool/` veya `src/fool/` altına** yaz. Upstream dosyasına giren şey
   yalnızca bir import + bir çağrı olsun.
2. Yanına `FOOL-SEAM: <id>` yorumunu koy.
3. Bu tabloya bir satır ekle.
4. `tests/fool/` altına dikişi koruyan bir test yaz.

Dikiş sayısı arttıkça merge maliyeti artar. Yeni özellikler dikişten değil,
**eklenti noktalarından** girmeli.

## Sıfır dikişle çalışan uzantı noktaları

Hermes zaten uzantı için tasarlanmış. Aşağıdakiler **upstream kodu hiç
düzenlenmeden** çalışır:

- **Görsel kimlik (CLI + TUI + GUI)** → `~/.fool/skins/the-fool.yaml`.
  `skin_engine.py`: *"A skin dropped in ~/.hermes/skins/ therefore themes all
  three surfaces at once."*
- **Ses klonlama** → `agent/tts_provider.py` ABC'si. Dosyanın kendi ifadesiyle:
  *"the hook is additive infrastructure waiting for a real consumer."*
- **Konuşma tanıma** → `agent/transcription_provider.py`
- **Masaüstü panel / sayfa / komut / kısayol** → `contrib/registry.ts` katkı
  alanları (`PANES_AREA`, `ROUTES_AREA`, `PALETTE_AREA`, `KEYBINDS_AREA`, …)
- **Ek temalar** → `THEMES_AREA`
- **Model sağlayıcı** → model-provider eklenti SDK'sı

Notch/popup penceresi bunun tek istisnası: gerçek bir Electron `BrowserWindow`
gerektiği için ileride bir `overlay-window` dikişi gerekecek. Mantık
`apps/desktop/electron/fool/` altına yazılacak, `main.ts`'e yalnızca bir import
ve bir çağrı girecek — deseni upstream'in kendi `link-title-window.ts`'i.
