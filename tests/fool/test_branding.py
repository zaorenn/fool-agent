"""The Fool markalaşmasının koruma testleri.

Bu testlerin varlık sebebi tek bir senaryo: ``git merge upstream/main``
sırasında bir çakışma **sessizce** upstream lehine çözülür ve markalaşma geri
alınır. Çakışmanın kendisi tehlikeli değil — görürsün, çözersin. Tehlikeli
olan, hiçbir şey söylemeden kaybolmasıdır.

Çalıştırma::

    python -m pytest tests/fool/ -q
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

from fool import branding

REPO_ROOT = Path(__file__).resolve().parents[2]


# =============================================================================
# Metin dönüşümü
# =============================================================================


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("Hermes Desktop is ready", "The Fool Desktop is ready"),
        ("Starting Hermes Desktop…", "Starting The Fool Desktop…"),
        ("HERMES AGENT", "FOOL AGENT"),
        ("Update Hermes", "Update The Fool"),
        ("Update Hermes Agent", "Update Fool Agent"),
        ("You are Hermes Agent", "You are Fool Agent"),
        ("Nous Research", "Fool Labs"),
        ("Hermes couldn't start", "The Fool couldn't start"),
        ("edit ~/.hermes/.env", "edit ~/.fool/.env"),
        ("run: fool update", "run: fool update"),
    ],
)
def test_user_visible_text_is_rebranded(source: str, expected: str) -> None:
    assert branding.brand_text(source) == expected


@pytest.mark.parametrize(
    "source",
    [
        # Backend sözleşmesi: bunlar ASLA değişmemeli.
        "Set FOOL_HOME to override",
        "from fool_cli.main import main",
        "FOOL_API_TIMEOUT=1800",
        "import fool_constants",
        "run_agent.py --help",
        "acp_adapter.entry:main",
    ],
)
def test_internal_contract_is_untouched(source: str) -> None:
    """``\\b`` sınırları ``_`` üzerinden eşleşmediği için sözleşme korunur."""
    assert branding.brand_text(source) == source


def test_no_hermes_survives_in_mixed_ui_text() -> None:
    text = "Hermes Desktop could not reach the Hermes backend. Restart Hermes."
    out = branding.brand_text(text)
    assert "Hermes" not in out
    # Artikelli konumda "The" düşer ("the Fool backend"), tek başına korunur.
    assert out == "The Fool Desktop could not reach the Fool backend. Restart The Fool."


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        # Artikel varsa ad sıradan özel isim gibi davranır.
        ("Restore a Hermes backup", "Restore a Fool backup"),
        ("Open the safe Hermes command console", "Open the safe Fool command console"),
        ("View your Hermes plan", "View your Fool plan"),
        # Artikel ürüne ait değilse tam ad korunmalı.
        (
            "Set a standing goal Hermes works on across turns",
            "Set a standing goal The Fool works on across turns",
        ),
        # Tek başına: tam ad.
        ("Hermes could not start", "The Fool could not start"),
    ],
)
def test_article_grammar_is_repaired(source: str, expected: str) -> None:
    """Ad "The" içerdiği için ham değiştirme bozuk İngilizce üretiyordu."""
    assert branding.brand_text(source) == expected


def test_brand_value_walks_nested_structures() -> None:
    payload = {
        "title": "Hermes",
        "items": ["Start Hermes", {"deep": "Nous Research"}],
        "count": 3,
        "flag": True,
        "nothing": None,
    }
    out = branding.brand_value(payload)
    assert out["title"] == "The Fool"
    assert out["items"][0] == "Start The Fool"
    assert out["items"][1]["deep"] == "Fool Labs"
    # String olmayanlar olduğu gibi geçmeli.
    assert out["count"] == 3
    assert out["flag"] is True
    assert out["nothing"] is None


# =============================================================================
# Python <-> TypeScript sabit senkronu
# =============================================================================


def _read_ts_brand() -> dict[str, str]:
    """``fool-branding.ts`` içindeki ``BRAND`` nesnesini kabaca ayrıştır.

    Tanım ``apps/shared`` altında: aynı dönüşümü hem masaüstü uygulaması hem
    web panosu kullanıyor (FOOL-SEAM: shared-branding). Masaüstündeki
    ``src/fool/branding.ts`` artık yalnızca yeniden dışa aktarım.
    """
    ts = (REPO_ROOT / "apps/shared/src/fool-branding.ts").read_text(encoding="utf-8")
    block = re.search(r"export const BRAND = \{(.*?)\} as const", ts, re.DOTALL)
    assert block, "branding.ts içinde BRAND bloğu bulunamadı"
    return dict(re.findall(r"(\w+):\s*'([^']*)'", block.group(1)))


def test_python_and_typescript_brand_constants_agree() -> None:
    """İki taraf ayrışırsa arayüz ve backend farklı isimler gösterir."""
    ts = _read_ts_brand()
    assert ts["name"] == branding.NAME
    assert ts["wordmark"] == branding.WORDMARK
    assert ts["desktop"] == branding.DESKTOP
    assert ts["agent"] == branding.AGENT
    assert ts["vendor"] == branding.VENDOR
    assert ts["cli"] == branding.CLI
    assert ts["homeDirName"] == branding.HOME_DIR_NAME
    assert ts["appId"] == branding.APP_ID
    assert ts["protocol"] == branding.PROTOCOL


# =============================================================================
# Dikişler yerinde mi
# =============================================================================

#: docs/fool/SEAMS.md tablosuyla eşleşmeli.
#:
#: Not: ``brand-dist`` burada yok çünkü hedefi ``package.json`` ve JSON yorum
#: kabul etmiyor — o dikiş aşağıdaki
#: :func:`test_desktop_package_carries_fool_identity` ile korunuyor.
EXPECTED_SEAMS = {
    "platform-failure-not-fatal",
    "local-sentence-streaming",
    "i18n-brand",
    "wordmark",
    "theme-preset",
    "update-origin",
    "banner-repo",
    "cli-scripts",
    "version-banner",
    "command-descriptions",
    "home-dir",
    "prog-name",
    "argparse-brand",
    "fool-packaging",
    "html-title",
    "bot-display-name",
    "bot-handle",
    "default-mode",
    "model-catalog",
    "diagnostics-endpoint",
    "nous-account-commands",
    "agent-identity",
    "anthropic-sanitize",
    "client-attribution",
    "brand-mark",
    "bootstrap-repo",
    "env-compat",
    "locale-brand",
    "web-i18n-brand",
    "shared-branding",
    "tts-device",
    "local-tts-deps",
    "context-file-names",
    "first-run-autodetect",
    "ready-token",
    "cli-launchers",
    "session-header",
    "browser-default",
    "toolset-rename",
    "remote-platform-default",
    "local-only-stt",
    "local-only-tts",
    "shared-gpu-budget",
    "output-file-toolset",
    "benchmark-gated-authority",
    "profile-memory-consent",
    "local-only-doctor",
    "speech-pauses",
    "slow-voice-engine",
    "companion-scope",
    "voice-mode-provider",
    "update-self-deadlock",
    "engine-vram-eviction",
    "one-voice",
    "voice-persona",
    "voice-session-bridge",
    "context-floor",
    "main-window-only-publisher",
    "os-text-encoding",
    "engine-namespaced-config",
    "espeak-ascii-path",
    "ipv4-loopback",
    "bundled-installer",
    "runtime-version",
    "runtime-dir-name",
    "home-repair",
    "speech-language",
    "language-mode",
    "plugin-tts-config",
    "resmi-rapor",
    "accent-override",
    "api-title",
    "cuda-dlls",
    "dotted-name-containers",
    "first-sentence-latency",
    "fool-guidance",
    "notch-ipc",
    "notch-no-chrome",
    "notch-quit",
    "notch-route",
    "notch-shortcut",
    "notch-window",
    "npm-bin-path",
    "packaged-exe-name",
    "release-repo-url",
    "shared-voice-policy",
    "skill-body-brand",
    "voice-models",
    "voice-owner",
    "voice-routes",
    "relationship-bar",
    "persona-greeting",
    "persona-kickoff",
    "setup-voice",
    "setup-voice-intro",
    "notch-profile",
    "notch-opens-session",
    "notch-submits-through-main",
    "default-memory",
    "shared-window-values",
    "voice-stop-bridge",
    "voice-warm-on-open",
    "defer-browser-tools",
    "whatsapp-toolset",
    "delivery-command-name",
    "system-tray",
    "single-model-residency",
}


def _grep_seams() -> set[str]:
    proc = subprocess.run(
        ["git", "grep", "-h", "-o", r"FOOL-SEAM: [a-z0-9-]\+"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    return {line.split(": ", 1)[1].strip() for line in proc.stdout.splitlines() if ": " in line}


def test_every_seam_in_the_tree_is_declared() -> None:
    """Ve kayıt bir dikişi ATLADIYSA da burada yakalanır.

    Muhafız uzun süre TEK YÖNLÜYDÜ: yalnızca ``EXPECTED_SEAMS - found``
    bakılıyordu, yani kayıttan düşen dikiş yakalanıyordu ama koda YENİ eklenen
    dikiş görülmüyordu. 83 dikişin 21'i böyle kayıt dışı kalmıştı.

    Kaçırdığı şey tam olarak var oluş sebebiydi: kayıt dışı bir dikişi upstream
    merge yutarsa hiçbir şey ötmez. Muhafız yeşil yanarken korumuyordu.
    """
    undeclared = _grep_seams() - EXPECTED_SEAMS
    assert not undeclared, (
        f"Kayıt dışı dikiş(ler): {sorted(undeclared)}. "
        "Her upstream düzenlemesi EXPECTED_SEAMS'e girmeli; yoksa bir merge "
        "onu sessizce geri alabilir. Riskliyse docs/fool/SEAMS.md'ye de yaz."
    )


def test_every_declared_seam_is_still_in_the_tree() -> None:
    """Merge bir dikişi yuttuysa burada yakalanır."""
    found = _grep_seams()
    missing = EXPECTED_SEAMS - found
    assert not missing, (
        f"Kayıp dikiş(ler): {sorted(missing)}. "
        "Muhtemelen bir upstream merge markalaşmayı geri aldı. "
        "docs/fool/SEAMS.md tablosundaki 'geri koyma' sütununa bak."
    )


# =============================================================================
# Dağıtım kimliği
# =============================================================================


def test_desktop_package_carries_fool_identity() -> None:
    pkg = json.loads((REPO_ROOT / "apps/desktop/package.json").read_text(encoding="utf-8"))
    assert pkg["build"]["appId"] == branding.APP_ID
    assert pkg["build"]["productName"] == branding.NAME
    assert "nousresearch" not in json.dumps(pkg["build"]).lower()


def test_cli_entry_points_are_rebranded() -> None:
    text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    scripts = re.search(r"\[project\.scripts\](.*?)(?:\n\[|\Z)", text, re.DOTALL)
    assert scripts, "pyproject.toml içinde [project.scripts] bulunamadı"
    body = scripts.group(1)
    assert f"{branding.CLI} =" in body
    # Modül yolları korunmalı — yalnızca komut adı değişti.
    assert "fool_cli.main:main" in body


# =============================================================================
# Python CLI yüzeyleri
# =============================================================================


def test_command_descriptions_carry_no_upstream_brand() -> None:
    """``/help`` listesinde "Hermes" görünmemeli.

    ``CommandDef.__post_init__`` tüm açıklamaları geçerken markalar, bu yüzden
    upstream yeni komut eklediğinde de otomatik kapsanır.
    """
    from fool_cli.commands import COMMAND_REGISTRY

    leftovers = [c.name for c in COMMAND_REGISTRY if "Hermes" in c.description]
    assert not leftovers, f"Markalanmamış komut açıklamaları: {leftovers}"


def test_version_banner_is_branded() -> None:
    from fool_cli.banner import format_banner_version_label

    label = format_banner_version_label()
    assert label.startswith(branding.NAME)
    assert "Hermes" not in label


# =============================================================================
# Veri dizini: Python <-> Electron
# =============================================================================


def test_python_and_electron_agree_on_data_dir() -> None:
    """İki taraf ayrışırsa masaüstü uygulaması backend'ini bulamaz.

    Python ``fool_constants._get_platform_default_hermes_home()`` ve Electron
    ``main.ts::resolveFoolHome()`` veri dizinini BAĞIMSIZ hesaplıyor. Bu test
    ikisinin aynı adı kullandığını doğrular.
    """
    posix_name = branding.HOME_DIR_NAME           # ".fool"
    windows_name = posix_name.lstrip(".")          # "fool"

    py = (REPO_ROOT / "fool_constants.py").read_text(encoding="utf-8")
    assert f'base / "{windows_name}"' in py, "Python Windows yolu ayrışmış"
    assert f'Path.home() / "{posix_name}"' in py, "Python POSIX yolu ayrışmış"

    ts = (REPO_ROOT / "apps/desktop/electron/main.ts").read_text(encoding="utf-8")
    assert f"path.join(process.env.LOCALAPPDATA, '{windows_name}')" in ts, (
        "Electron Windows yolu ayrışmış"
    )
    assert f"path.join(app.getPath('home'), '{posix_name}')" in ts, (
        "Electron POSIX yolu ayrışmış"
    )


def test_the_fool_never_uses_the_upstream_hermes_data_dir() -> None:
    """Kullanıcının kurulu Hermes verisine dokunmama garantisi."""
    import fool_constants

    home = str(fool_constants.get_hermes_home()).lower().replace("\\", "/")
    assert not home.endswith("local/hermes")
    assert not home.endswith("/.hermes")


# =============================================================================
# Nous bağlarının kesildiği
# =============================================================================


def test_model_catalog_makes_no_network_call_by_default() -> None:
    """Katalog sürümle birlikte geliyor; her açılışta Nous'a istek gitmiyor."""
    from fool_cli import model_catalog

    assert model_catalog.DEFAULT_CATALOG_URL == ""
    assert model_catalog.DEFAULT_CATALOG_FALLBACK_URLS == ()
    # URL yoksa fetch zinciri ağa hiç dokunmadan None döner.
    assert model_catalog._fetch_manifest_with_fallback("", 5.0, ()) is None


def test_diagnostics_upload_is_disabled_by_default() -> None:
    """Loglar ve sistem bilgisi üçüncü tarafa gitmemeli."""
    import fool_cli.diagnostics_upload as diag

    assert diag.NAS_BASE == ""
    with pytest.raises(RuntimeError, match="disabled in The Fool"):
        diag.request_upload_url()


def test_nous_account_commands_are_gone() -> None:
    """Var olmayan bir planı vaat eden komut, olmayan komuttan kötüdür."""
    from fool_cli.commands import COMMAND_REGISTRY

    names = {c.name for c in COMMAND_REGISTRY}
    assert "subscription" not in names
    assert "topup" not in names


def test_no_command_promises_a_plan_we_do_not_have() -> None:
    from fool_cli.commands import COMMAND_REGISTRY

    bogus = [c.name for c in COMMAND_REGISTRY if branding.VENDOR in c.description]
    assert not bogus, f"'{branding.VENDOR}' vaadi taşıyan komutlar: {bogus}"


# =============================================================================
# Ajanın kendini tanıması
# =============================================================================


def test_agent_identifies_itself_as_fool_agent() -> None:
    """Kullanıcı "hangi uygulamayı kullanıyorum?" dediğinde verilen cevap.

    Markalaşmanın en derin katmanı: arayüzdeki her yazı değişse bile bu
    değişmezse ajan kendini hâlâ Hermes Agent sanır.
    """
    from agent.prompt_builder import DEFAULT_AGENT_IDENTITY, FOOL_AGENT_HELP_GUIDANCE

    assert DEFAULT_AGENT_IDENTITY.startswith(f"You are {branding.AGENT},")
    assert "Hermes" not in DEFAULT_AGENT_IDENTITY
    assert "Nous Research" not in DEFAULT_AGENT_IDENTITY

    assert branding.AGENT in FOOL_AGENT_HELP_GUIDANCE
    assert "nousresearch.com" not in FOOL_AGENT_HELP_GUIDANCE


def test_anthropic_sanitizer_covers_the_fool_identity() -> None:
    """Anthropic OAuth ucuna markalı prompt gitmemeli.

    Kimlik "Fool Agent" olduğu için sanitize listesi güncellenmezse
    upstream'in filtre-kaçınma korumasi sessizce delinir.
    """
    src = (REPO_ROOT / "agent/anthropic_adapter.py").read_text(encoding="utf-8")
    assert f'text.replace("{branding.AGENT}", "Claude Code")' in src
    assert f'text.replace("{branding.NAME}", "Claude Code")' in src


def test_tool_schema_branding_preserves_the_call_contract() -> None:
    """Açıklamalar markalanır, çağrı sözleşmesi ASLA değişmez.

    Araç adı / parametre anahtarı / enum markalanırsa model var olmayan bir
    aracı çağırır — sessiz ve teşhisi zor bir bozulma.
    """
    sample = [
        {
            "type": "function",
            "function": {
                "name": "hermes_screenshot",
                "description": "Otherwise Hermes falls back to a vision model.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "hermes_path": {"type": "string", "description": "Path used by Hermes."},
                        "mode": {"type": "string", "enum": ["hermes", "fast"]},
                    },
                    "required": ["hermes_path"],
                },
            },
        }
    ]
    fn = branding.brand_tool_schemas(sample)[0]["function"]

    # Sözleşme aynen durmalı.
    assert fn["name"] == "hermes_screenshot"
    assert list(fn["parameters"]["properties"]) == ["hermes_path", "mode"]
    assert fn["parameters"]["properties"]["mode"]["enum"] == ["hermes", "fast"]
    assert fn["parameters"]["required"] == ["hermes_path"]

    # Açıklamalar markalanmalı.
    assert "Hermes" not in fn["description"]
    assert "Hermes" not in fn["parameters"]["properties"]["hermes_path"]["description"]


def test_skill_index_branding_preserves_skill_names() -> None:
    """Beceri adları ``skill_view(name=…)`` ile çağrılıyor — değişemez."""
    index = (
        "  agents: Delegate work to other agents.\n"
        "    - hermes-agent: Use, configure, and orchestrate Hermes Agent.\n"
        "    - codex: Delegate coding to OpenAI Codex CLI.\n"
    )
    out = branding.brand_skill_index(index)

    assert "- hermes-agent:" in out, "beceri adı korunmalı"
    assert "orchestrate Fool Agent." in out, "açıklama markalanmalı"
    assert "- codex:" in out


def test_default_soul_matches_the_agent_identity() -> None:
    """SOUL.md, DEFAULT_AGENT_IDENTITY'yi gölgeler — ikisi ayrışmamalı."""
    from agent.prompt_builder import DEFAULT_AGENT_IDENTITY
    from fool_cli.default_soul import DEFAULT_SOUL_MD

    assert DEFAULT_SOUL_MD == DEFAULT_AGENT_IDENTITY


def test_upstream_default_soul_is_upgradable_in_place() -> None:
    """Hermes'ten gelen makine-serili SOUL.md sessizce kimliği ele geçirmemeli."""
    from fool_cli.default_soul import is_legacy_template_soul

    upstream_soul = (
        "You are Hermes Agent, an intelligent AI assistant created by Nous Research. "
        "You are helpful, knowledgeable, and direct. You assist users with a wide "
        "range of tasks including answering questions, writing and editing code, "
        "analyzing information, creative work, and executing actions via your tools. "
        "You communicate clearly, admit uncertainty when appropriate, and prioritize "
        "being genuinely useful over being verbose unless otherwise directed below. "
        "Be targeted and efficient in your exploration and investigations."
    )
    assert is_legacy_template_soul(upstream_soul)
    # Kullanıcının kendi yazdığı bir persona ASLA üzerine yazılmamalı.
    assert not is_legacy_template_soul("You are a grumpy pirate.")


# =============================================================================
# Bootstrap: paketlenmiş uygulama HANGİ depoyu kuruyor
# =============================================================================


def test_bootstrap_installs_the_fool_not_upstream() -> None:
    """FOOL-SEAM: bootstrap-repo — en sinsi kaçak buydu.

    Paketlenmiş uygulama backend'ini kurmak için bir kurulum betiği indirip
    çalıştırıyor, o betik de bir depo klonluyor. Bu adresler upstream'de
    kalırsa uygulama The Fool gibi görünür ama HER KULLANICIYA upstream
    Hermes kurar — ve markalaşmanın tamamı çalışma anında geri alınır.

    Belirti (gözlendi): bootstrap upstream'i klonluyor, sonra The Fool'un
    commit'ini checkout etmeye çalışıp ``exit 128`` ile ölüyor.
    """
    targets = [
        "apps/desktop/electron/bootstrap-runner.ts",
        "apps/desktop/electron/update-remote.ts",
        "scripts/install.ps1",
        "scripts/install.sh",
    ]
    offenders = []
    for rel in targets:
        text = (REPO_ROOT / rel).read_text(encoding="utf-8", errors="replace")
        if "NousResearch/hermes-agent" in text:
            offenders.append(rel)
        assert "zaorenn/fool-agent" in text, f"{rel}: fork deposu geçmiyor"

    assert not offenders, f"upstream deposunu kuran dosyalar: {offenders}"


# =============================================================================
# Ortam değişkeni geriye dönük uyumluluğu
# =============================================================================


def test_legacy_hermes_env_still_resolves(monkeypatch: pytest.MonkeyPatch) -> None:
    """FOOL-SEAM: env-compat — eski ayarlar sessizce yok sayılmamalı.

    Kullanıcı ``setx FOOL_HOME`` yapmış olabilir. Yok sayılırsa uygulama
    hatasız açılır ama YANLIŞ dizini kullanır — oturumlar ve hafıza kaybolmuş
    görünür. Teşhisi en zor hata türü.
    """
    from fool import compat

    monkeypatch.delenv("FOOL_HOME", raising=False)
    monkeypatch.setenv("FOOL_HOME", r"C:\eski\yol")
    assert compat.getenv("FOOL_HOME") == r"C:\eski\yol"


def test_new_env_name_wins_over_legacy(monkeypatch: pytest.MonkeyPatch) -> None:
    """İkisi birden ayarlıysa davranış belirsiz kalmamalı."""
    from fool import compat

    monkeypatch.setenv("FOOL_HOME", r"C:\eski")
    monkeypatch.setenv("FOOL_HOME", r"C:\yeni")
    assert compat.getenv("FOOL_HOME") == r"C:\yeni"


def test_home_resolution_honours_legacy_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Uçtan uca: gerçek veri dizini çözümlemesi eski değişkeni görüyor mu."""
    import fool_constants

    monkeypatch.delenv("FOOL_HOME", raising=False)
    monkeypatch.setenv("FOOL_HOME", r"C:\eski\fool-home")
    assert str(fool_constants._hermes_home_from_env()) == r"C:\eski\fool-home"


# =============================================================================
# TTS: cihaz seçimi
# =============================================================================


def test_tts_device_explicit_cpu_is_honoured() -> None:
    from fool import tts_device

    assert tts_device.resolve({"device": "cpu"}) == "cpu"


def test_tts_device_reads_legacy_use_cuda_flag() -> None:
    """Piper'ın eski `use_cuda` anahtarı okunmaya devam etmeli.

    Mevcut yapılandırmalar sessizce yok sayılırsa kullanıcı GPU'yu açtığını
    sanıp CPU'da çalışmaya devam eder.
    """
    from fool import tts_device

    assert tts_device.resolve({"use_cuda": False}) == "cpu"


def test_tts_device_falls_back_to_cpu_when_cuda_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`cuda` istenip bulunamadığında çalışmaya devam etmeli — ama sessizce değil."""
    from fool import tts_device

    monkeypatch.setattr(tts_device, "cuda_available", lambda: False)
    assert tts_device.resolve({"device": "cuda"}) == "cpu"


def test_tts_device_auto_picks_cuda_when_present(monkeypatch: pytest.MonkeyPatch) -> None:
    from fool import tts_device

    monkeypatch.setattr(tts_device, "cuda_available", lambda: True)
    assert tts_device.resolve({}) == "cuda"
    assert tts_device.resolve({"device": "auto"}) == "cuda"


def test_local_tts_engines_are_registered_for_lazy_install() -> None:
    """FOOL-SEAM: local-tts-deps — Piper yerleşik ama kayıtsızdı.

    Kayıt olmayınca seçildiğinde "pip install piper-tts" diyen bir hata
    veriyordu; kullanıcının gördüğü hata tam buydu.
    """
    from tools.lazy_deps import LAZY_DEPS

    for feature in ("tts.piper", "tts.chatterbox", "tts.kokoro"):
        assert feature in LAZY_DEPS, f"{feature} tembel kurulum kaydinda yok"


# =============================================================================
# İlk açılışta yerel sunucu keşfi
# =============================================================================


def test_autodetect_skips_embedding_models() -> None:
    """Gömme modeli sohbet edemez — seçilirse kullanıcı hiç cevap alamaz."""
    from fool import autodetect

    models = ["text-embedding-nomic-embed-text-v1.5", "qwen/qwen3.5-9b"]
    assert autodetect.choose_model(models) == "qwen/qwen3.5-9b"


def test_autodetect_prefers_tool_capable_family() -> None:
    """The Fool ajan bir uygulama: araç çağıramayan model iş yapamaz."""
    from fool import autodetect

    models = ["some-unknown-model", "qwen/qwen3.5-9b"]
    assert autodetect.choose_model(models) == "qwen/qwen3.5-9b"


def test_autodetect_returns_none_when_only_embeddings() -> None:
    from fool import autodetect

    assert autodetect.choose_model(["bge-large-en", "text-embedding-3"]) is None


def test_autodetect_lmstudio_needs_no_base_url() -> None:
    """LM Studio birinci sınıf sağlayıcı — varsayılan ucu zaten biliyor."""
    from fool import autodetect

    runner = autodetect.RUNNERS[0]
    assert runner.key == "lmstudio"
    patch = autodetect.config_patch(
        autodetect.Detection(runner=runner, models=["m"], chosen_model="m")
    )
    assert patch["model"]["provider"] == "lmstudio"
    assert "base_url" not in patch["model"]


def test_autodetect_generic_runner_gets_base_url() -> None:
    """Ollama/llama.cpp gibi genel uçlar `custom` olarak base_url ile bağlanır."""
    from fool import autodetect

    ollama = next(r for r in autodetect.RUNNERS if r.key == "ollama")
    patch = autodetect.config_patch(
        autodetect.Detection(runner=ollama, models=["x"], chosen_model="x")
    )
    assert patch["model"]["provider"] == "custom"
    assert patch["model"]["base_url"] == ollama.base_url


# =============================================================================
# Süreçler arası sözleşmeler — sessiz kırılmalar
# =============================================================================


def test_backend_ready_token_matches_on_both_sides() -> None:
    """FOOL-SEAM: ready-token — eşleşmezse masaüstü backend'i hiç göremez.

    Backend portunu duyurur, Electron duymaz, 90 saniye sonra
    "Timed out waiting for backend port announcement" der. Hata mesajı
    backend'i suçlu gösterir; oysa backend sorunsuz çalışıyordur.

    Toplu marka dönüşümü tam olarak bunu atlamıştı: regex içindeki
    ``HERMES_`` bir env değişkeni değil, desenin parçası.
    """
    py = (REPO_ROOT / "fool_cli/web_server.py").read_text(encoding="utf-8")

    assert '"FOOL_BACKEND_READY"' in py, "backend farkli bir token yaziyor"

    # TEK BIR DOSYAYA bakmak yetmiyordu -- olculdu.
    #
    # Bu muhafiz uzun sure yalnizca ``backend-ready.ts``e bakiyordu ve YESILDI.
    # Oysa aynı desenin IKINCI bir kopyasi ``remote-lifecycle.ts``te duruyordu
    # ve orada ``HERMES_`` kalmisti: uzak (SSH) arka uc sorunsuz basliyor,
    # portunu duyuruyor, masaustu duymuyor ve her baglanti
    # "Timed out waiting for the remote dashboard to announce its port" ile
    # oluyordu. Deponun kendi testi bunu yakalamisti; muhafiz gormedi.
    #
    # Artik dosya adi degil DESEN araniyor: masaustunun hangi dosyasinda
    # olursa olsun, yeni token'i tanimayan bir hazir-olma deseni hata.
    electron = REPO_ROOT / "apps/desktop/electron"
    ready_files = [
        path
        for path in sorted(electron.rglob("*.ts"))
        if not path.name.endswith(".test.ts")
        and "_READY port=" in path.read_text(encoding="utf-8")
    ]

    assert ready_files, "hazir-olma desenini tasiyan hicbir dosya bulunamadi"

    for path in ready_files:
        source = path.read_text(encoding="utf-8")
        pattern = re.search(r"/\^[^\n]*_READY port=\(\\d\+\)/[gm]+", source)

        assert pattern, f"{path.name}: hazir-olma deseni okunamadi"
        assert "FOOL" in pattern.group(0), (
            f"{path.name}: masaustu FOOL_ token'ini tanimiyor -- "
            "backend portunu duyurur, bu taraf duymaz"
        )


def test_update_check_asks_OUR_repo_how_far_behind_you_are() -> None:
    """FOOL-SEAM: update-origin — yanlış depo = sayı hiç gelmez.

    ``_github_compare_behind`` iki SHA'yı GitHub'ın compare API'sine soruyor.
    Marka dönüşümü ``_OFFICIAL_REPO_CANONICAL``i yeni depoya taşımış ama bu
    URL'i ``nousresearch/hermes-agent`` olarak bırakmıştı. Bizim
    commit'lerimiz o depoda YOK: istek 404 dönüyor, işlev ``None`` veriyor ve
    banner "kaç commit geridesin" sorusunu ASLA cevaplayamıyordu.

    Sessiz bozulma: hata görünmüyor, yalnızca bilgi hiç gelmiyor -- ve sığ
    klonlarda (yükleyicinin kurduğu her kurulum) bu TEK sayım yolu.
    """
    import inspect

    from fool_cli import banner

    source = inspect.getsource(banner._github_compare_behind)

    assert "_OFFICIAL_REPO_CANONICAL" in source, (
        "depo adi gomulmemeli -- sabitten turetilmeli, yoksa bir sonraki "
        "yeniden adlandirma ayni sessiz kirilmayi tekrar uretir"
    )

    host, slug = banner._OFFICIAL_REPO_CANONICAL.split("/", 1)

    assert slug == "zaorenn/fool-agent"
    assert f"https://api.{host}/repos/{slug}/compare/" == (
        f"https://api.github.com/repos/zaorenn/fool-agent/compare/"
    )


def test_terminal_logo_does_not_SPELL_hermes() -> None:
    """FOOL-SEAM: wordmark — çizim, dize değil; tarama onu göremiyor.

    Harfler ``█`` karakterinden çiziliyor, yani söz-markasının içinde "Hermes"
    DİZESİ hiç geçmiyor. Yeniden adlandırma aracı değişken adını
    ``FOOL_AGENT_LOGO`` yaptı ve testler yeşil kaldı -- ama çizim
    "HERMES-AGENT" yazmaya devam etti, altındaki şekil de Caduceus'tu:
    Hermes'in asası. ``fool`` yazan herkesin gördüğü İLK ekran buydu.

    ``cli.py`` bir noktada elle düzeltildi, ``fool_cli/banner.py``
    düzeltilmedi -- ve CANLI olan ikincisiydi.

    Bu test çizimi ÇÖZÜYOR: her harf sütununun dolu/boş desenini okuyup
    baş harfleri çıkarıyor. Böylece "içinde Hermes yazmıyor" iddiası gerçekten
    sınanabiliyor.
    """
    import re

    from fool_cli import banner

    rows = [
        re.sub(r"\[[^\]]*\]", "", line)
        for line in banner.FOOL_AGENT_LOGO.splitlines()
    ]
    rows = [r for r in rows if r.strip()]

    assert rows, "soz-markasi bos"

    # Blok harfler ``█`` ve kutu cizgilerinden olusuyor. "HERMES" yazan bir
    # marka ilk satirinda H'nin iki dik sutununu tasir: ``██╗  ██╗``.
    first = rows[0]

    assert not first.startswith("██╗  ██╗"), (
        "soz-markasi HERMES ile basliyor -- cizim geri gelmis"
    )
    assert first.startswith("████████╗██╗  ██╗███████╗"), (
        "soz-markasi THE ile baslamiyor; beklenen 'THE FOOL'"
    )

    # Caduceus braille ile ciziliydi; Fool isareti kutu cizgileriyle.
    assert "⣿" not in banner.FOOL_CADUCEUS, "Caduceus (Hermes'in asasi) geri gelmis"


def test_terminal_logo_has_only_ONE_copy() -> None:
    """İki kopya bir kez ayrıştı ve canlı olan yanlış kaldı.

    ``cli.py`` ile ``fool_cli/banner.py`` aynı çizimi ayrı ayrı taşıyordu.
    Biri elle düzeltilince diğeri geride kaldı -- ve düzeltilmeyen taraf
    kullanıcının gördüğü taraftı. Artık ikisi de ``fool/brand_art.py``den
    içe aktarıyor: ayrışacak ikinci bir yer yok.
    """
    from fool import brand_art
    from fool_cli import banner

    assert banner.FOOL_AGENT_LOGO is brand_art.WORDMARK
    assert banner.FOOL_CADUCEUS is brand_art.MARK

    for path in ("cli.py", "fool_cli/banner.py"):
        source = (REPO_ROOT / path).read_text(encoding="utf-8")

        assert "from fool.brand_art import" in source, f"{path}: cizim tek kaynaktan gelmiyor"
        assert '████' not in source.split("from fool.brand_art import")[0][-2000:], (
            f"{path}: yerel bir cizim kopyasi geri gelmis"
        )


def test_installer_publishes_the_fool_cli_launchers() -> None:
    """FOOL-SEAM: cli-launchers — yanlış ad = terminalde hiçbir şey.

    venv ``fool.exe`` üretiyor. Kurulum betiği ``hermes.exe`` kopyalamaya
    çalışırsa sessizce hiçbir şey kopyalanmaz: kurulum "başarılı" görünür
    ama ``fool`` komutu PATH'e hiç girmez.
    """
    ps1 = (REPO_ROOT / "scripts/install.ps1").read_text(encoding="utf-8", errors="replace")
    assert '"fool.exe", "fool-acp.exe"' in ps1
    assert '@("hermes.exe"' not in ps1

    sh = (REPO_ROOT / "scripts/install.sh").read_text(encoding="utf-8", errors="replace")
    assert '"$command_link_dir/fool"' in sh
    assert '"$command_link_dir/hermes"' not in sh


def test_session_header_matches_on_both_sides() -> None:
    """FOOL-SEAM: session-header — üç ayrı şekilde kırılabilir.

    1. Boşluk içeremez. Dönüşüm ``X-Hermes-Session-Token``ı
       ``X-The Fool-Session-Token`` yaptı ve Node ERR_INVALID_HTTP_TOKEN
       fırlattı: her API çağrısı patladı.
    2. İki taraf ayrışabilir. TS düzeltilip Python eski adda kalırsa
       başlık geçerli olur ama kimlik doğrulama SESSİZCE reddedilir.
    3. Eski ad geri gelebilir (upstream merge).
    """
    py = (REPO_ROOT / "fool_cli/web_server.py").read_text(encoding="utf-8")
    ts = (REPO_ROOT / "apps/desktop/electron/main.ts").read_text(encoding="utf-8")

    header = "X-Fool-Session-Token"
    assert f'_SESSION_HEADER_NAME = "{header}"' in py
    assert f"'{header}'" in ts

    # HTTP başlık adı: boşluk YASAK.
    assert " " not in header
    for text, label in ((py, "python"), (ts, "electron")):
        assert "X-The Fool-" not in text, f"{label}: bosluklu baslik geri gelmis"
        assert "X-Hermes-" not in text, f"{label}: eski baslik geri gelmis"


def test_browser_backend_defaults_to_builtin_stack() -> None:
    """FOOL-SEAM: browser-default — yanlış varsayılan ajanı kör bırakıyordu.

    Upstream'de ``browser.backend`` varsayılanı Browser Use (bulut, API
    anahtarı ister). Anahtar yoksa çalışmaz VE bu mod açıkken yerleşik
    ``browser_*`` araçları da devre dışı kalır. Ajanın elinde hiç tarayıcı
    kalmaz; her şeyi computer use ile — ekran görüntüsü alıp piksel
    koordinatına tıklayarak — yapmaya çalışır.
    """
    src = (REPO_ROOT / "fool_cli/config.py").read_text(encoding="utf-8")
    assert 'patch.setdefault("browser", {})["backend"] = "off"' in src


def test_browser_binary_detection_covers_common_installs() -> None:
    """Chromium bulunmazsa ``backend: off`` tek başına yetmez."""
    from fool import browser_detect

    joined = " ".join(browser_detect._WINDOWS_CANDIDATES).lower()
    assert "chrome.exe" in joined
    assert "msedge.exe" in joined, "Edge cogu Windows makinesinde HAZIR kurulu"
    assert browser_detect.ENV_VAR == "AGENT_BROWSER_EXECUTABLE_PATH"

class TestSkillBodyBranding:
    """Beceri govdesi ajanin OKUDUGU talimattir.

    Sistem promptu "sen Fool Agent'sin" dese bile, ajan bir beceri acip
    "Hermes Agent is an open-source AI agent framework by Nous Research"
    okuyunca kendini oyle tanitiyor: beceri govdesi daha somut ve daha yakin
    bir kaynak. Bu yuzden govde de markalanmali -- ama govde, dizinden farkli
    olarak CALISTIRILABILIR seyler tasiyor ve onlar bozulmamali.
    """

    def test_kimlik_cumlesi_markalanir(self):
        out = branding.brand_skill_body(
            "Hermes Agent is an open-source AI agent framework by Nous Research."
        )
        assert out == "Fool Agent is an open-source AI agent framework by Fool Labs."

    def test_cagrilabilir_beceri_kimligi_korunur(self):
        """``hermes-agent`` bir ADdir; markalanirsa skill_view yanlis cagrilir."""
        src = 'Load it with skill_view(name="hermes-agent") first.'
        assert branding.brand_skill_body(src) == src

    def test_upstream_depo_atfi_korunur(self):
        src = "Source: https://github.com/NousResearch/hermes-agent"
        assert branding.brand_skill_body(src) == src

    def test_modul_ve_ortam_adlari_korunur(self):
        src = "Import fool_cli.config after setting FOOL_HOME."
        assert branding.brand_skill_body(src) == src

    def test_ev_dizini_markalanir(self):
        """Ev dizini artik gercekten ``.fool`` -- korumak yanlis yolu birakirdi."""
        assert branding.brand_skill_body("~/.hermes/skills") == "~/.fool/skills"

    def test_kod_blogu_degismez(self):
        """Blok ici metin CALISTIRILAN komut; ikinci kez dokunmak bozar."""
        src = chr(10).join(["Hermes runs it.", "```bash", "fool run --name Hermes", "```", "Hermes stops."])
        out = branding.brand_skill_body(src).split(chr(10))
        assert out[0] == "The Fool runs it."
        assert out[2] == "fool run --name Hermes"   # blok ici DOKUNULMADI
        assert out[4] == "The Fool stops."

    def test_idempotent(self):
        """Iki kez uygulamak tek kez uygulamakla ayni olmali."""
        src = "Hermes Agent, hermes-agent, ~/.hermes, Nous Research"
        once = branding.brand_skill_body(src)
        assert branding.brand_skill_body(once) == once

    def test_skills_tool_dikisi_gercek_dosyayi_markalar(self):
        """Uctan uca: DEPODAKI gercek beceri dosyasi dikisten gecirilir.

        ``skill_view``i dogrudan cagirmak beceri KESFINE baglidir (calisma
        dizini, FOOL_HOME, yapilandirma) ve testi kirilgan yapar. Onemli olan
        sozlesme su: skills_tool okudugu metni markalayarak donduruyor. Burada
        tam o dikis, gercek girdiyle sinaniyor.
        """
        import re as _re

        from tools.skills_tool import _fool_brand_skill

        skill_md = (
            Path(__file__).resolve().parents[2]
            / "skills"
            / "autonomous-ai-agents"
            / "hermes-agent"
            / "SKILL.md"
        )
        assert skill_md.exists(), f"test dayanagi kayboldu: {skill_md}"

        raw = skill_md.read_text(encoding="utf-8-sig", errors="replace")
        assert _re.search(r"\b(Hermes|Nous Research)\b", raw), (
            "kaynak dosya artik marka tasimiyor; bu test anlamini yitirdi"
        )

        out = _fool_brand_skill(raw)
        leaks = [
            line
            for line in out.split(chr(10))
            if _re.search(r"\b(Hermes|Nous Research)\b", line)
            and "NousResearch/hermes-agent" not in line
        ]
        assert not leaks, f"markasiz satirlar: {leaks[:5]}"
        assert "name: hermes-agent" in out, "cagrilabilir kimlik bozuldu"


class TestIlkAcilisTespiti:
    """Yerel model sunucusunun ilk acilista bulunmasi.

    Kullanicinin sarti: uygulamayi denemesi icin birine gonderdiginde o kisi
    "saglayici sec, base URL yaz, model kimligi kopyala" adimlarina
    girmemeli. Bu testler o vaadin sessizce bozulmasina karsi.
    """

    def test_bionic_katalogda(self):
        from fool.autodetect import RUNNERS

        assert "bionic" in {r.key for r in RUNNERS}

    def test_yaygin_portlar_dogru_sirada(self):
        """3000 SONDA olmali: her Node dev sunucusu orada dinliyor.

        Onde olsaydi otomatik algilama gercek bir model sunucusu yerine
        rastgele bir web uygulamasina baglanirdi.
        """
        from fool.autodetect import RUNNERS

        keys = [r.key for r in RUNNERS]
        assert keys[0] == "lmstudio"
        assert keys[-1] == "bionic"

    def test_dolu_saglayici_EZILMEZ(self, tmp_path):
        """Kullanicinin bilincli secimi otomatik algilamayla degistirilemez."""
        import yaml

        from fool_cli.config import _fool_seed_local_model

        (tmp_path / "config.yaml").write_text(
            yaml.safe_dump({"model": {"provider": "openai", "default": "gpt-4o"}}),
            encoding="utf-8",
        )
        _fool_seed_local_model(tmp_path)

        after = yaml.safe_load((tmp_path / "config.yaml").read_text(encoding="utf-8"))
        assert after["model"]["provider"] == "openai"

    def test_saglayicisiz_yapilandirmada_ALGILAR_ve_kalanini_korur(self, tmp_path):
        """Dosyanin VARLIGI algilamayi engellememeli.

        Once yalnizca ``config.yaml`` yoksa calisiyordu; baska bir nedenle
        (tema, kisayol) olusmus bir dosya, LM Studio acik olmasina ragmen
        kullaniciyi sonsuza kadar "saglayici sec" ekraninda birakiyordu.
        """
        import yaml

        from fool.autodetect import detect
        from fool_cli.config import _fool_seed_local_model

        if detect() is None:
            pytest.skip("bu makinede calisan yerel model sunucusu yok")

        (tmp_path / "config.yaml").write_text(
            yaml.safe_dump({"display": {"skin": "mono"}, "tts": {"provider": "piper"}}),
            encoding="utf-8",
        )
        _fool_seed_local_model(tmp_path)

        after = yaml.safe_load((tmp_path / "config.yaml").read_text(encoding="utf-8"))
        assert (after.get("model") or {}).get("provider"), "saglayici eklenmedi"
        assert after["tts"]["provider"] == "piper", "var olan ayar silindi"


def test_pyproject_extras_kendine_referans_verir():
    """Ek paket gruplari KENDI paketimize referans vermeli.

    ``fool-agent`` icindeki bir extra ``hermes-agent[cron]`` derse, cozumleyici
    PyPI'daki UPSTREAM paketi cekmeye calisiyor ve surumler catisiyor:
    "hermes-agent<=0.16.0 depends on pyjwt==2.12.1" vs bizim 2.13.0. Sonuc
    "No solution found" ve ``fool update`` isteğe bagli ozellikleri SESSIZCE
    atliyor -- kullanici yalnizca "Optional extras failed" satirini goruyor.

    Yeniden adlandirma araci bunu kaciriyor cunku ``hermes-agent`` korunan
    listede (beceri kimligi ve upstream depo atfi icin). Orada dogru, burada
    yanlis; ayrimi bu test tutuyor.
    """
    root = Path(__file__).resolve().parents[2]
    text = (root / "pyproject.toml").read_text(encoding="utf-8")

    assert '"hermes-agent[' not in text, (
        "pyproject extras'i upstream pakete referans veriyor; "
        '"fool-agent[...]" olmali'
    )


def test_cli_acilis_logosu_THE_FOOL_yazar():
    """Açılış logosu ASCII ÇİZİM: içinde "Hermes" DİZESİ geçmez.

    Bu yüzden marka denetimi onu göremiyor. Gerçekte yaşandı: yeniden
    adlandırma aracı değişken adını ``FOOL_AGENT_LOGO`` yaptı, çizim ise blok
    karakterlerle "HERMES-AGENT" yazmaya devam etti -- ve yeni kuran herkesin
    gördüğü İLK ekran buydu. Yanındaki sembol de Caduceus'tu: Hermes'in asası.

    Bu test bir kez daha yaşandı, çünkü YALNIZCA ``cli.py``ye bakıyordu.
    Çizimin ikinci bir kopyası ``fool_cli/banner.py``de duruyordu ve CANLI
    olan oydu: ``cli.py`` düzeltilince test yeşile döndü, kullanıcı hâlâ
    HERMES-AGENT görüyordu. Artık çizim tek kaynakta ve test kaynağı sınıyor.
    """
    from fool import brand_art

    art = brand_art.WORDMARK

    # Upstream'in altın paleti: geri dönüşün en net işareti.
    for gold in ("#FFD700", "#FFBF00", "#CD7F32", "#B8860B"):
        assert gold not in art, f"logo upstream'in altin paletine donmus ({gold})"

    # "HERMES" harflerinin ANSI Shadow biçimindeki imzası: 'H' harfi
    # ``██║  ██║`` deseniyle başlıyor. "THE FOOL" ise ``████████╗`` (T) ile.
    first_line = art.strip().split(chr(10))[0]

    assert "████████╗" in first_line, "logo artik THE FOOL ile baslamiyor"

    assert "⣿" not in brand_art.MARK, "Caduceus (Hermes'in asasi) geri gelmis"
def test_whatsapp_uzak_kullaniciya_makineyi_actirmaz() -> None:
    """WhatsApp'tan gelen mesajlar makineyi KONTROL edememeli.

    Upstream'in ``hermes-whatsapp`` varsayilani 59 arac veriyor ve icinde
    ``computer_use``, ``execute_code``, 13 tane ``browser_*``, ``cronjob`` ve
    Home Assistant kontrolu var. WhatsApp'a yazabilen herkes -- aile uyeleri,
    numarayi bilen herhangi biri -- makineyi surebilir demek.

    Bu test once ``ensure_hermes_home()`` uzerinden kuruluyordu ve o yol
    kisitlamayi yalnizca ilk acilista CALISAN bir yerel model sunucusu
    bulunursa yaziyordu. LM Studio kapaliyken ``config.yaml`` hic yazilmiyor,
    kisitlama hic uygulanmiyordu -- yani guvenlik denetimi, olcmeye calistigi
    sey gibi, sessizce kapanabiliyordu. Ayni erken cikis, saglayicisi zaten
    ayarli olan MEVCUT kurulumlara da kisitlamayi hic indirmiyordu.

    Politika artik ``config.yaml``dan bagimsiz: bos yapilandirmayla sor.
    Ayrintili kapsam icin ``tests/fool/test_platform_toolsets.py``.
    """
    from fool_cli.tools_config import _get_platform_tools
    from toolsets import resolve_toolset

    sets = _get_platform_tools({}, "whatsapp")
    assert sets, "temiz kurulumda whatsapp hic arac takimi almiyor"

    tools = set()
    for name in sets:
        tools |= set(resolve_toolset(name))

    # Makineyi SUREN ya da HAKKINDA bilgi veren hicbir arac olmamali.
    forbidden = {
        "computer_use",
        "cronjob",
        "delegate_task",
        "execute_code",
        "patch",
        "read_file",
        "search_files",
        "terminal_run",
        "write_file",
    }
    leaked = forbidden & tools
    assert not leaked, f"WhatsApp'a tehlikeli arac siziyor: {sorted(leaked)}"

    browser = sorted(t for t in tools if t.startswith("browser") or t.startswith("ha_"))
    assert not browser, f"WhatsApp'a tarayici/ev kontrolu siziyor: {browser}"

    # Sahibinin gorev panosu da uzak birinin isi degil.
    board = sorted(t for t in tools if t.startswith("kanban"))
    assert not board, f"WhatsApp'a gorev panosu siziyor: {board}"
