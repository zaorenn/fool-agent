"""Aynı anda TEK dil modeli yüklü kalsın.

Ölçüldü (kullanıcının kartı, RTX 4070 Ti SUPER, 16 GB):

    google/gemma-4-e4b   6,33 GB   TTL yok   <- seçili olan
    qwen/qwen3.5-9b      6,55 GB   TTL 1 sa  <- gün boyu hiç istenmedi
    ------------------------------------------
    toplam              12,88 GB, geriye ~3 GB

Seslendirme motorları AYNI kartta. Günlüklerde sonucu görünüyordu:
``[TTS/piper] device=cuda istendi ama CUDA bulunamadi; CPU'ya dusuluyor``.
qwen boşaltıldıktan sonra ölçüldü: VRAM 12,88 GB -> 3,73 GB.
"""

from __future__ import annotations

import pytest

from fool import lmstudio_residency as residency

#: Fikstür ``unload``u taklit ediyor; bu yolun KENDİSİNİ sınayan testler
#: gerçeğini geri koyuyor, yoksa taklidin taklidi sınanırdı.
_REAL_UNLOAD = residency.unload


@pytest.fixture(autouse=True)
def _no_real_cli(monkeypatch):
    """Sınavlar GERÇEK modelleri boşaltmasın."""
    monkeypatch.setattr(residency, "unload", lambda model_id: True)


def _loaded(monkeypatch, ids):
    monkeypatch.setattr(residency, "loaded_models", lambda base_url: list(ids))


# ---------------------------------------------------------------------------
# Uç nokta çözümlemesi
# ---------------------------------------------------------------------------

def test_api_koku_v1_ekini_atiyor() -> None:
    """Yüklü model listesi ``/v1`` altında DEĞİL, kökte."""
    assert residency._api_root("http://localhost:1234/v1") == "http://localhost:1234"
    assert residency._api_root("http://localhost:1234/v1/") == "http://localhost:1234"
    assert residency._api_root("http://127.0.0.1:9999") == "http://127.0.0.1:9999"


def test_bos_adres_varsayilana_dusuyor() -> None:
    assert residency._api_root("") == "http://localhost:1234"


# ---------------------------------------------------------------------------
# Tek-model kuralı
# ---------------------------------------------------------------------------

def test_secili_OLMAYANLAR_birakiliyor(monkeypatch) -> None:
    _loaded(monkeypatch, ["google/gemma-4-e4b", "qwen/qwen3.5-9b"])

    dropped = residency.enforce_single("http://localhost:1234/v1", "google/gemma-4-e4b")

    assert dropped == ["qwen/qwen3.5-9b"]


def test_secili_model_ASLA_birakilmiyor(monkeypatch) -> None:
    """Kullanıcının o an konuştuğu modeli kapatmak en kötü sonuç."""
    _loaded(monkeypatch, ["google/gemma-4-e4b"])

    assert residency.enforce_single("http://localhost:1234/v1", "google/gemma-4-e4b") == []


def test_KEEP_bos_ise_hicbir_sey_yapilmiyor(monkeypatch) -> None:
    """Hangisinin korunacağını bilmeden boşaltmak körlemesine kapatmaktır."""
    _loaded(monkeypatch, ["google/gemma-4-e4b", "qwen/qwen3.5-9b"])

    assert residency.enforce_single("http://localhost:1234/v1", "") == []
    assert residency.enforce_single("http://localhost:1234/v1", "   ") == []


def test_birakilamayan_model_LISTEDE_gorunmuyor(monkeypatch) -> None:
    """Rapor gerçeği söylemeli: boşaltılamadıysa boşaltılmış sayılmaz."""
    _loaded(monkeypatch, ["a", "b"])
    monkeypatch.setattr(residency, "unload", lambda model_id: model_id == "a")

    assert residency.enforce_single("http://localhost:1234/v1", "keep") == ["a"]


def test_hicbiri_yuklu_degilse_sessizce_geciyor(monkeypatch) -> None:
    _loaded(monkeypatch, [])

    assert residency.enforce_single("http://localhost:1234/v1", "google/gemma-4-e4b") == []


# ---------------------------------------------------------------------------
# Dayanıklılık
# ---------------------------------------------------------------------------

def test_LM_Studio_kapaliysa_COKMUYOR() -> None:
    """Başka bir sağlayıcı kullanılıyor olabilir; burada yapılacak iş yok."""
    assert residency.loaded_models("http://127.0.0.1:59999") == []


def test_lms_komutu_yoksa_bosaltma_DENENMIYOR(monkeypatch) -> None:
    """Bir iyileştirme uğruna sesli oturumu düşürmek yanlış olurdu.

    ``unload`` burada BİLEREK gerçek işlev: fikstürün taklidi geri alınıyor,
    yoksa sınav kendi taklidini sınardı.
    """
    monkeypatch.setattr(residency, "unload", residency.unload.__wrapped__
                        if hasattr(residency.unload, "__wrapped__") else _REAL_UNLOAD)
    monkeypatch.setattr(residency, "_cli", lambda: "")

    assert residency.unload("google/gemma-4-e4b") is False


def test_bos_model_kimligi_bosaltilmiyor(monkeypatch) -> None:
    monkeypatch.setattr(residency, "unload", _REAL_UNLOAD)
    monkeypatch.setattr(residency, "_cli", lambda: "C:/lms.exe")

    assert residency.unload("") is False


# ---------------------------------------------------------------------------
# Isıtma ucuna bağlı mı?
# ---------------------------------------------------------------------------

def test_isitma_ucu_temizligi_ARKA_PLANDA_yapiyor() -> None:
    """Isıtma HEMEN dönmeli.

    Bir bellek temizliği uğruna sesli oturumun açılışını bekletmek, tam
    olarak düzeltilmek istenen yavaşlığı geri getirirdi.
    """
    from pathlib import Path

    source = (Path(__file__).resolve().parents[2] / "fool" / "voice_routes.py").read_text(
        encoding="utf-8"
    )

    assert "_free_unused_llms()" in source
    # Is parcaciginda kosuyor -- ucun kendisi beklemiyor.
    assert "threading.Thread" in source
    assert "enforce_single" in source


# ---------------------------------------------------------------------------
# Katalog budaması
# ---------------------------------------------------------------------------

def test_YAVAS_motorlar_panelde_GORUNMUYOR() -> None:
    """Ölçülen hızları gerçek zamanın çok altında.

        kyutai      2,5-11 sn/cümle
        qwen3-tts   9,42 sn/cümle
        f5-tts      bu makinede hiç çalışmıyor (torchcodec/FFmpeg)

    Karşılaştırma: kokoro 0,13-0,20 sn, piper 0,12 sn, styletts2 0,56 sn.
    """
    from fool import voice_models as vm

    visible = {e.id for e in vm.visible_catalog() if e.kind == "tts"}

    for slow in ("kyutai", "qwen3-tts", "f5-tts"):
        assert slow not in visible or vm.active_providers().get("tts") == (
            vm.entry(slow).provider_id or slow
        ), f"{slow} panelde gorunuyor"


def test_HIZLI_motorlar_panelde_DURUYOR() -> None:
    from fool import voice_models as vm

    visible = {e.id for e in vm.visible_catalog() if e.kind == "tts"}

    assert {"piper", "kokoro", "styletts2", "chatterbox"} <= visible


def test_kayitlar_SILINMEDI_yalnizca_gizlendi() -> None:
    """Kurulu bir motoru katalogdan silmek, kullanıcının diskindeki
    gigabaytları görünmez yapardı. Gizlemek geri alınabilir."""
    from fool import voice_models as vm

    for slow in ("kyutai", "qwen3-tts", "f5-tts"):
        entry = vm.entry(slow)

        assert entry is not None, f"{slow} katalogdan SILINMIS"
        assert entry.hidden is True


def test_SECILI_gizli_motor_yine_gosteriliyor(monkeypatch) -> None:
    """Aksi hâlde kullanıcı ayarlarda hiçbir şey seçili görmez ve sesin
    nereden geldiğini anlayamaz."""
    from fool import voice_models as vm

    monkeypatch.setattr(vm, "active_providers", lambda: {"stt": "", "tts": "kyutai"})

    assert "kyutai" in {e.id for e in vm.visible_catalog()}


# ---------------------------------------------------------------------------
# ÜREYEN modele dokunulmuyor
# ---------------------------------------------------------------------------

def test_UREYEN_model_birakilmiyor(monkeypatch) -> None:
    """Süren bir turu ortasından kesmek: kullanıcı cevabın yarısını alır.

    Ve LM Studio onu hemen yeniden yükler -- 6,5 GB'lik bir yükle-boşalt
    döngüsü, ki donmanın sebeplerinden biri tam olarak bu. Kullanıcının 43
    oturumu qwen'e sabitli, yani başka bir modelin üstünde gerçekten bir tur
    koşuyor olabiliyor.
    """
    _loaded(monkeypatch, ["google/gemma-4-e4b", "qwen/qwen3.5-9b"])
    monkeypatch.setattr(residency, "busy_models", lambda: {"qwen/qwen3.5-9b"})

    assert residency.enforce_single("http://localhost:1234/v1", "google/gemma-4-e4b") == []


def test_BOSTAKI_model_birakiliyor(monkeypatch) -> None:
    _loaded(monkeypatch, ["google/gemma-4-e4b", "qwen/qwen3.5-9b"])
    monkeypatch.setattr(residency, "busy_models", lambda: set())

    assert residency.enforce_single("http://localhost:1234/v1", "google/gemma-4-e4b") == [
        "qwen/qwen3.5-9b"
    ]


def test_lms_okunamazsa_mesgul_kumesi_BOS(monkeypatch) -> None:
    """Sonda koşamıyorsa çağıran taraf normal kurala düşüyor."""
    monkeypatch.setattr(residency, "_cli", lambda: "")

    assert residency.busy_models() == set()


# ---------------------------------------------------------------------------
# VRAM baskısında ÖNCE dil modeli
# ---------------------------------------------------------------------------

def test_VRAM_baskisinda_ONCE_dil_modeli_birakiliyor() -> None:
    """Ölçüldü (16 GB kart): gemma 6,33 + qwen 6,55 = 12,88 GB, üstüne
    Chatterbox ~3,5 GB. Kart aşılıyor, Windows GPU belleğini sistem RAM'ine
    taşıyor ve makine çökmeden DONUYOR.

    Kullanılmayan bir dil modelini bırakmak, çalışan bir ses motorunu
    durdurmaktan her zaman daha ucuz: LM Studio onu bir sonraki istekte zaten
    yeniden yükler, oysa durdurulan ses motoru KONUŞMAYI kesiyor.
    """
    from pathlib import Path

    source = (Path(__file__).resolve().parents[2] / "fool" / "engine_host.py").read_text(
        encoding="utf-8"
    )

    assert "lmstudio_residency" in source
    # Ses motorlarini tahliye eden donguden ONCE.
    llm_free = source.index("lmstudio_residency.enforce_single")
    engine_evict = source.index("while others and free is not None")

    assert llm_free < engine_evict, "dil modeli birakmasi ses tahliyesinden SONRA"


# ---------------------------------------------------------------------------
# Bağlam tabanı YAPILANDIRILABİLİR
# ---------------------------------------------------------------------------

def test_baglam_tabani_SABIT_yazili_degil() -> None:
    """Upstream 64K'yi sabit yazmış ve altındaki her modeli REDDEDİYOR.

    Yani 32K'lik bir yerel model uygulamayı hiç açtıramıyor. Kullanıcının
    isteği: "32k context ile bile çalışmalı ve iyi çalışmalı."

    Varsayılan DEĞİŞMİYOR (64K) -- küçük bir pencere araç çağırmayı gerçekten
    zorluyor ve bunu herkes için sessizce düşürmek yanlış olurdu. Karar
    kullanıcının: ``agent.minimum_context_length``.
    """
    from pathlib import Path

    source = (Path(__file__).resolve().parents[2] / "agent" / "agent_init.py").read_text(
        encoding="utf-8"
    )

    assert "FOOL-SEAM: context-floor" in source
    assert "minimum_context_length" in source
    # Karsilastirma YAPILANDIRILAN taban ile.
    assert "_ctx < _floor" in source
    # Ham sabitle karsilastirma GERI GELMEMELI.
    assert "_ctx < MINIMUM_CONTEXT_LENGTH" not in source


def test_varsayilan_taban_DEGISMEDI() -> None:
    """Ayar yazılmamışsa upstream davranışı aynen sürüyor."""
    from agent.model_metadata import MINIMUM_CONTEXT_LENGTH

    assert MINIMUM_CONTEXT_LENGTH == 64_000
