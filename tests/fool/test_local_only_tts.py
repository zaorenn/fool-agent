"""Seslendirme varsayılanı buluta gitmemeli.

``tools/tts_tool.py`` içinde ``DEFAULT_PROVIDER = "edge"``. Edge TTS
Microsoft'un çevrimiçi "Read Aloud" servisi: ajanın söylediği HER cümlenin
metni websocket üzerinden Microsoft'a gidiyor.

STT sızıntısından farkı ve daha kötü yanı: bu bir HATA yolu değil, VARSAYILAN
yol. ``tts.provider`` yazmamış temiz bir kurulumda -- yani her yeni
kullanıcıda -- yerel motorlar kurulu olsa bile Edge seçiliyor.

Kullanıcının kendi ``config.yaml``ında ``tts.provider: qwen3`` yazıyor, o
yüzden bu makinede sızmıyor; ama uygulamayı denemesi için birine
gönderdiğinde sızıyor.
"""

from __future__ import annotations

import pytest

from fool import local_only


def test_bulut_varsayilan_olarak_kapali() -> None:
    assert local_only.cloud_tts_allowed({}) is False


def test_acik_tercih_bulutu_acar() -> None:
    assert local_only.cloud_tts_allowed({"allow_cloud_fallback": "yes"}) is True


def test_bozuk_yapilandirma_kapali_tarafa_duser() -> None:
    assert local_only.cloud_tts_allowed(None) is False
    assert local_only.cloud_tts_allowed(["edge"]) is False


def test_kurulu_yerel_motorlardan_en_hizlisi_seciliyor() -> None:
    """Sıra ölçülmüş gecikmeye göre: Kokoro 0,08 sn, Chatterbox 28 sn."""
    assert local_only.preferred_local_tts({"chatterbox", "kokoro"}) == "kokoro"
    assert local_only.preferred_local_tts({"chatterbox", "qwen3"}) == "qwen3"
    assert local_only.preferred_local_tts(["piper"]) == "piper"


def test_hicbiri_kurulu_degilse_none() -> None:
    assert local_only.preferred_local_tts(set()) is None
    assert local_only.preferred_local_tts({"edge", "openai"}) is None


def test_bozuk_girdide_cokmuyor() -> None:
    assert local_only.preferred_local_tts(None) is None


# ---------------------------------------------------------------------------
# Gerçek çözümleyici
# ---------------------------------------------------------------------------

@pytest.fixture
def tts(monkeypatch):
    from tools import tts_tool

    return tts_tool


def test_acik_secim_hic_dokunulmuyor(tts, monkeypatch) -> None:
    """``tts.provider: edge`` yazan kullanıcı bilerek Edge istiyor."""
    monkeypatch.setattr(tts, "_installed_local_tts", lambda: {"kokoro"})

    assert tts._get_provider({"provider": "edge"}) == "edge"
    assert tts._get_provider({"provider": "openai"}) == "openai"


def test_secim_yokken_kurulu_yerel_motor_seciliyor(tts, monkeypatch) -> None:
    monkeypatch.setattr(tts, "_installed_local_tts", lambda: {"kokoro", "chatterbox"})

    assert tts._get_provider({}) == "kokoro"


def test_yerel_motor_yoksa_sessizce_edge_secilmiyor(tts, monkeypatch) -> None:
    monkeypatch.setattr(tts, "_installed_local_tts", lambda: set())

    assert tts._get_provider({}) == "none"


def test_acik_tercihle_edge_yine_calisiyor(tts, monkeypatch) -> None:
    monkeypatch.setattr(tts, "_installed_local_tts", lambda: set())

    assert tts._get_provider({"allow_cloud_fallback": True}) == "edge"


# ---------------------------------------------------------------------------
# "none" GERÇEKTEN durduruyor mu?
# ---------------------------------------------------------------------------
#
# Bu bölüm uçtan uca ses turunun (fool/voice_roundtrip.py) yakaladığı bir
# hatanın ardından yazıldı. ``_get_provider`` doğru şekilde "none" dönüyordu
# ama ``text_to_speech_tool`` o değeri tanımıyor ve VARSAYILAN dala düşüyordu
# -- varsayılan ise Edge, yani tam kaçınmak için "none" döndüğümüz şey.
#
# Yani koruma vardı, sözleşme yoktu. Birim testleri iki ucu ayrı ayrı doğru
# gördü; boşluk aralarındaydı.

def test_none_saglayicisi_EDGE_e_dusmuyor(tmp_path) -> None:
    from tools.tts_tool import text_to_speech_tool
    import json as _json

    raw = text_to_speech_tool("merhaba", output_path=str(tmp_path / "x.wav"), provider="none")
    payload = _json.loads(raw)

    assert payload["success"] is False
    assert "NOT sent to Microsoft" in payload["error"]


def test_none_mesaji_nasil_duzeltilecegini_soyluyor(tmp_path) -> None:
    from tools.tts_tool import text_to_speech_tool
    import json as _json

    payload = _json.loads(
        text_to_speech_tool("merhaba", output_path=str(tmp_path / "x.wav"), provider="none")
    )

    assert "Settings > Text to speech" in payload["error"]
    assert "allow_cloud_fallback" in payload["error"]


# ---------------------------------------------------------------------------
# Katalogdaki her ses AYRI AYRI inebilmeli
# ---------------------------------------------------------------------------

#: ``lang_REGION-konusmaci-kalite`` -- Rhasspy'nin ses adlandirmasi. Piper'in
#: indirme yardimcisi HF yolunu bu addan turetiyor, yani bicimi bozuk bir
#: kimlik CALISMA ANINDA "voice download failed" oluyor.
_PIPER_VOICE_ID = __import__("re").compile(r"^[a-z]{2}_[A-Z]{2}-[a-z0-9_]+-(x_low|low|medium|high)$")


def test_katalogdaki_piper_seslerinin_KIMLIGI_gecerli() -> None:
    """Seçilebilen bir ses inebilmeli.

    Kullanıcının kuralı: "yüklü olmayan bir şey zaten seçilememeli." Piper'da
    seçim indirmeyi tetikliyor, yani kural şuna dönüşüyor: listelenen her ses
    GERÇEKTEN indirilebilir olmalı. Yanlış yazılmış tek bir kimlik, kullanıcının
    seçip hiçbir şey duymadığı bir satır demek.

    Ağ İSTENMİYOR: biçim burada tutuluyor, varlık ise
    ``test_piper_sesleri_UPSTREAMDE_var`` ile (integration).
    """
    from fool.voice_models import CATALOG

    piper = [e for e in CATALOG if e.id == "piper"][0]

    assert piper.voices, "piper icin secilebilir ses yok"

    for vid, label in piper.voices:
        assert _PIPER_VOICE_ID.match(vid), f"gecersiz piper ses kimligi: {vid!r}"
        assert label.strip(), f"{vid}: etiket bos"


def test_TURKCE_ses_katalogda() -> None:
    """CPU'da gerçek zamandan hızlı çalışan tek seçenek Piper; Türkçe konuşan
    kullanıcı ona ulaşabilmeli."""
    from fool.voice_models import CATALOG

    piper = [e for e in CATALOG if e.id == "piper"][0]
    ids = [vid for vid, _ in piper.voices]

    assert any(vid.startswith("tr_TR-") for vid in ids), f"Turkce ses yok: {ids}"


@pytest.mark.integration
def test_piper_sesleri_UPSTREAMDE_var() -> None:
    """Her kimlik Rhasspy deposunda ``.onnx`` + ``.onnx.json`` olarak var mı?

    İkisi birden şart: Piper ikisini de arıyor, biri eksikse çalışma anında
    anlaşılmaz bir hata veriyor.
    """
    import urllib.request

    from fool.voice_models import CATALOG

    base = "https://huggingface.co/rhasspy/piper-voices/resolve/main"
    piper = [e for e in CATALOG if e.id == "piper"][0]

    for vid, _ in piper.voices:
        lang_region = vid.split("-", 1)[0]
        lang = lang_region.split("_", 1)[0]
        speaker, quality = vid.split("-")[1], vid.split("-")[-1]

        for ext in ("onnx", "onnx.json"):
            url = f"{base}/{lang}/{lang_region}/{speaker}/{quality}/{vid}.{ext}"
            req = urllib.request.Request(url, method="HEAD")

            with urllib.request.urlopen(req, timeout=30) as resp:
                assert resp.status == 200, f"{vid}: {ext} bulunamadi ({url})"
