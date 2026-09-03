"""Aynı anda tek STT + tek TTS + tek LLM.

Kullanıcının kuralı birebir: "aynı anda sadece tek bir stt, tts ve llm,
toplamda 3 şey yüklü olmalı; her bir kategoride diğerleri seçildiğinde
öncekiler tamamen unload edilmeli".

Neden ölçülebilir bir şey: üçü de AYNI kartı paylaşıyor. Ölçüldü (RTX 4070 Ti
SUPER, 16 GB): gemma 6,33 GB + qwen 6,55 GB + whisper 1,6 GB + chatterbox
3,5 GB. Kart aşılıyor ve Windows GPU belleğini sistem RAM'ine taşımaya
başlıyor -- makine çökmüyor, DONUYOR.

Sahteler ``sys.modules``e konuyor, çünkü ``fool/residency.py`` bilerek
İTHAL ETMİYOR: yüklü olmayan bir modülü yalnızca "yüklü mü" diye sormak için
ithal etmek, sorunun kendisini yaratmak olurdu.
"""

from __future__ import annotations

import sys
import types

import pytest

from fool import residency


# ---------------------------------------------------------------------------
# Sahteler
# ---------------------------------------------------------------------------


def _fake_transcription(model: object | None, name: str = "large-v3-turbo"):
    module = types.ModuleType("tools.transcription_tools")
    module._local_model = model
    module._local_model_name = name
    module.unloaded = False

    def _unload_local_model() -> None:
        module._local_model = None
        module._local_model_name = None
        module.unloaded = True

    module._unload_local_model = _unload_local_model
    return module


def _fake_engine_host(*names: str):
    module = types.ModuleType("fool.engine_host")
    module.live = list(names)
    module.stopped = []

    module.running = lambda: list(module.live)

    def _stop_gracefully(name: str, timeout: float = 30.0) -> None:
        module.stopped.append(name)
        if name in module.live:
            module.live.remove(name)

    module.stop_gracefully = _stop_gracefully
    return module


def _fake_tts_tool(piper: bool = False, kitten: bool = False):
    module = types.ModuleType("tools.tts_tool")
    module._piper_voice_cache = {"en_US-lessac": object()} if piper else {}
    module._kittentts_model_cache = {"kitten": object()} if kitten else {}
    return module


def _fake_lmstudio(*loaded: str, busy: tuple[str, ...] = ()):
    module = types.ModuleType("fool.lmstudio_residency")
    module.live = list(loaded)
    module.unloaded = []
    module.busy_models = lambda: set(busy)
    module.loaded_models = lambda base_url, timeout=20: list(module.live)

    def _unload(model_id: str) -> bool:
        module.unloaded.append(model_id)
        module.live.remove(model_id)
        return True

    module.unload = _unload

    def _enforce_single(base_url: str, keep: str) -> list[str]:
        dropped = [m for m in list(module.live) if m != keep and m not in set(busy)]
        for model_id in dropped:
            _unload(model_id)
        return dropped

    module.enforce_single = _enforce_single
    return module


def _fake_warmup(name: str, status: str = "warm"):
    module = types.ModuleType(f"fool.{name}_warmup")
    module.state = {"status": status}
    module.status = lambda: dict(module.state)
    module.mark_cold = lambda: module.state.update(status="cold")
    return module


@pytest.fixture
def install(monkeypatch):
    """Sahte modülleri ``sys.modules``e tak.

    PAKET NİTELİĞİ de değiştiriliyor. Sebebi ölçülmüş bir sınav yanılgısı:
    ``from fool import lmstudio_residency`` önce ``fool`` paketinin
    niteliğine bakıyor ve o nitelik modül bir kez ithal edildikten sonra
    kalıcı. Yalnızca ``sys.modules``i değiştiren bir sahte, başka bir testin
    ithal ettiği GERÇEK modülün önüne geçemiyordu -- sınav sessizce gerçek
    LM Studio'yu sorguluyordu.
    """

    def _install(module) -> object:
        name = module.__name__
        monkeypatch.setitem(sys.modules, name, module)

        package, _, leaf = name.rpartition(".")
        parent = sys.modules.get(package)
        if parent is not None:
            monkeypatch.setattr(parent, leaf, module, raising=False)

        return module

    return _install


@pytest.fixture(autouse=True)
def _quiet_modules(monkeypatch):
    """Gerçek ağır modüller sızmasın.

    Bu testler ``sys.modules``e bakan bir sondayı sınıyor: başka bir testin
    ithal ettiği gerçek ``tools.tts_tool`` burada "yüklü model" gibi
    görünebilirdi ve sınav sessizce anlamsızlaşırdı.
    """
    for name in (
        "tools.transcription_tools",
        "tools.tts_tool",
        "fool.engine_host",
        "fool.lmstudio_residency",
        "fool.stt_warmup",
        "fool.tts_warmup",
        "torch",
    ):
        monkeypatch.delitem(sys.modules, name, raising=False)


@pytest.fixture(autouse=True)
def _config(monkeypatch):
    """Seçili olanlar: whisper turbo, kokoro, qwen."""
    monkeypatch.setattr(
        residency,
        "_config",
        lambda: {
            "stt": {"provider": "local", "local": {"model": "large-v3-turbo"}},
            "tts": {"provider": "kokoro"},
            "model": {"default": "qwen/qwen3.5-9b", "base_url": "http://localhost:1234/v1"},
        },
    )


# ---------------------------------------------------------------------------
# Sonda İTHAL ETMİYOR
# ---------------------------------------------------------------------------


def test_yuklenmemis_modul_sorgulanmiyor(monkeypatch) -> None:
    """Hiçbir şey ithal edilmemişse cevap boş -- ve ithal DE edilmiyor.

    ``tools.transcription_tools`` ithali torch/ctranslate2 zincirini açıyor.
    Onu yalnızca "yüklü mü" diye sormak için ithal etmek, tepsi menüsünü
    açmanın modeli yüklemesi olurdu.

    LLM sondası SAHTELENIYOR. O sonda gerçek bir HTTP çağrısı: makinede LM
    Studio açıksa yüklü modeli döndürüyor ve ``total`` sıfır olmuyordu -- yani
    sınav, ilgilenmediği bir şeye (geliştiricinin o an neyi açık bıraktığına)
    bağlıydı ve bu makinede ``qwen/qwen3.5-9b`` yüzünden düşüyordu. Sınavın
    sorusu İTHALLER; onu ölçmek için LLM tarafının sessiz olması yeterli.
    """
    monkeypatch.setattr(residency, "_llm_loaded", lambda base_url, timeout=0: [])

    snapshot = residency.snapshot(timeout=0.01)

    assert snapshot["total"] == 0
    assert "tools.transcription_tools" not in sys.modules
    assert "fool.engine_host" not in sys.modules


def test_secili_olanlar_yuklu_olmasa_da_raporlaniyor() -> None:
    """Panel "seçili ama yüklü değil"i gösterebilmeli."""
    snapshot = residency.snapshot(timeout=0.01)

    assert snapshot["stt"]["selected"] == "large-v3-turbo"
    assert snapshot["tts"]["selected"] == "kokoro"
    assert snapshot["llm"]["selected"] == "qwen/qwen3.5-9b"


# ---------------------------------------------------------------------------
# Ne yüklü
# ---------------------------------------------------------------------------


def test_yuklu_whisper_gorunuyor(install) -> None:
    install(_fake_transcription(object()))

    snapshot = residency.snapshot(timeout=0.01)

    assert [row["id"] for row in snapshot["stt"]["loaded"]] == ["large-v3-turbo"]
    # Kullanıcıya kimlik değil ETIKET gösteriliyor.
    assert snapshot["stt"]["loaded"][0]["label"] == "Whisper Large-v3 Turbo"


def test_ayakta_olan_motorlar_gorunuyor(install) -> None:
    install(_fake_engine_host("kokoro"))

    snapshot = residency.snapshot(timeout=0.01)

    assert [row["id"] for row in snapshot["tts"]["loaded"]] == ["kokoro"]
    assert snapshot["tts"]["loaded"][0]["label"] == "Kokoro"


def test_ANA_SUREC_motorlari_da_sayiliyor(install) -> None:
    """Piper ile KittenTTS sidecar kullanmıyor.

    Modelleri ana sürecin sözlüklerinde duruyor; yalnızca süreçlere bakan bir
    sonda "hiçbir şey yüklü değil" derken bellekte model tutardı.
    """
    install(_fake_engine_host())
    install(_fake_tts_tool(piper=True))

    snapshot = residency.snapshot(timeout=0.01)

    assert [row["id"] for row in snapshot["tts"]["loaded"]] == ["piper"]


def test_yuklu_dil_modelleri_gorunuyor(install) -> None:
    install(_fake_lmstudio("qwen/qwen3.5-9b", "google/gemma-4-e4b"))

    snapshot = residency.snapshot(timeout=0.01)

    assert [row["id"] for row in snapshot["llm"]["loaded"]] == [
        "qwen/qwen3.5-9b",
        "google/gemma-4-e4b",
    ]
    assert snapshot["total"] == 2


def test_isinma_suruyorsa_soyleniyor(install) -> None:
    """"Yüklü değil" ile "şu anda yükleniyor" aynı görünmemeli."""
    install(_fake_warmup("stt", status="warming"))

    assert residency.snapshot(timeout=0.01)["stt"]["warming"] is True


# ---------------------------------------------------------------------------
# Bırak
# ---------------------------------------------------------------------------


def test_stt_birakiliyor_ve_isitma_soguyor(install) -> None:
    tt = install(_fake_transcription(object()))
    warm = install(_fake_warmup("stt"))

    result = residency.unload("stt")

    assert result["unloaded"]["stt"] == ["large-v3-turbo"]
    assert tt.unloaded is True
    # Isıtma durumu "warm" kalsaydı tepsi menüsü boşaltmadan hemen sonra
    # "sıcak" yazardı ve kullanıcı isteğinin işlemediğini sanırdı.
    assert warm.state["status"] == "cold"


def test_yuklu_degilse_bosaltma_islemsiz(install) -> None:
    install(_fake_transcription(None))

    assert residency.unload("stt")["total"] == 0


def test_motor_NAZIKCE_durduruluyor(install) -> None:
    """Düz ``stop`` süren bir sentezi ortasından keser.

    Kullanıcı konuşurken tepsiden boşaltmaya bassa cümle yarıda susardı.
    """
    host = install(_fake_engine_host("kokoro", "chatterbox"))

    result = residency.unload("tts")

    assert sorted(host.stopped) == ["chatterbox", "kokoro"]
    assert sorted(result["unloaded"]["tts"]) == ["chatterbox", "kokoro"]


def test_tek_motor_hedeflenebiliyor(install) -> None:
    host = install(_fake_engine_host("kokoro", "chatterbox"))

    residency.unload("tts", "chatterbox")

    assert host.stopped == ["chatterbox"]
    assert host.live == ["kokoro"]


def test_ana_surec_onbellegi_de_temizleniyor(install) -> None:
    install(_fake_engine_host())
    tts_tool = install(_fake_tts_tool(piper=True, kitten=True))

    result = residency.unload("tts")

    assert tts_tool._piper_voice_cache == {}
    assert tts_tool._kittentts_model_cache == {}
    assert sorted(result["unloaded"]["tts"]) == ["kittentts", "piper"]


def test_dil_modelleri_ACIK_istekte_UREYENE_ragmen_birakiliyor(install) -> None:
    """Tepsiden "boşalt" kullanıcının AÇIK isteği.

    Üreyen modeli korumak ``enforce_single`` yolunun işi: orada boşaltma
    kodun kararı ve süren bir turu kesmemesi gerekiyor. Burada ise kullanıcı
    düğmeye bastı -- "yaptım ama aslında yapmadım" en kötü cevap olurdu.
    """
    lms = install(_fake_lmstudio("qwen/qwen3.5-9b", busy=("qwen/qwen3.5-9b",)))

    result = residency.unload("llm")

    assert result["unloaded"]["llm"] == ["qwen/qwen3.5-9b"]
    assert lms.unloaded == ["qwen/qwen3.5-9b"]


def test_hepsi_tek_cagrida(install) -> None:
    """Uygulamadan çıkarken tek yol: her şey bıraksın."""
    tt = install(_fake_transcription(object()))
    host = install(_fake_engine_host("kokoro"))
    lms = install(_fake_lmstudio("qwen/qwen3.5-9b"))

    result = residency.unload_all()

    assert result["total"] == 3
    assert tt.unloaded is True
    assert host.stopped == ["kokoro"]
    assert lms.unloaded == ["qwen/qwen3.5-9b"]


def test_bilinmeyen_kategori_reddediliyor() -> None:
    with pytest.raises(ValueError):
        residency.unload("gpu")


# ---------------------------------------------------------------------------
# Tek kalsın
# ---------------------------------------------------------------------------


def test_secili_olmayan_motor_birakiliyor(install) -> None:
    host = install(_fake_engine_host("kokoro", "chatterbox"))

    dropped = residency.enforce_single()["unloaded"]

    assert dropped["tts"] == ["chatterbox"]
    assert host.live == ["kokoro"], "secili motor korunmali"


def test_secili_olmayan_whisper_birakiliyor(install) -> None:
    tt = install(_fake_transcription(object(), name="base"))

    dropped = residency.enforce_single()["unloaded"]

    assert dropped["stt"] == ["base"]
    assert tt.unloaded is True


def test_secili_whisper_KORUNUYOR(install) -> None:
    tt = install(_fake_transcription(object(), name="large-v3-turbo"))

    assert residency.enforce_single()["total"] == 0
    assert tt.unloaded is False


def test_kategori_daraltilabiliyor(install) -> None:
    """Ses motoru seçimi ``lms ps`` bedelini ödememeli.

    Ölçüldü: ``lms ps`` bir alt süreç ve birkaç yüz milisaniye. Kullanıcı bir
    düğmeye bastı ve cevabı bekliyor.
    """
    host = install(_fake_engine_host("chatterbox"))
    lms = install(_fake_lmstudio("google/gemma-4-e4b"))

    residency.enforce_single(kinds=("tts",))

    assert host.live == []
    assert lms.unloaded == [], "dil modeline dokunulmamali"


def test_secim_bilinmiyorsa_HICBIR_SEY_birakilmiyor(install, monkeypatch) -> None:
    """Neyin korunacağını bilmeden boşaltmak, kullanıcının o an konuştuğu
    modeli kapatmak olurdu.
    """
    monkeypatch.setattr(residency, "_config", dict)
    host = install(_fake_engine_host("kokoro"))
    tt = install(_fake_transcription(object()))

    assert residency.enforce_single()["total"] == 0
    assert host.live == ["kokoro"]
    assert tt.unloaded is False


# ---------------------------------------------------------------------------
# Uçlar gerçekten takılı mı
# ---------------------------------------------------------------------------


def test_uclar_ses_yonlendiricisine_takili(monkeypatch) -> None:
    """Uçlar ``voice_routes`` üzerinden servis ediliyor.

    Bu sınav bir bağlantı sınavı: ``fool/residency_routes.py`` tek satırla
    ``voice_routes``a takılıyor ve ``web_server.py`` yalnızca onu tanıyor
    (FOOL-SEAM: voice-routes). O satır bir birleştirmede kaybolursa uçlar
    sessizce 404 döner -- tepsi menüsü "durum bilinmiyor" der ve sebebini
    hiçbir yerde göremezsin.
    """
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from fool import voice_routes

    app = FastAPI()
    app.include_router(voice_routes.router)

    with TestClient(app) as client:
        snapshot = client.get("/api/fool/runtime/residency")
        assert snapshot.status_code == 200
        assert set(snapshot.json()) >= {"stt", "tts", "llm", "total"}

        dropped = client.post("/api/fool/runtime/unload", json={"kind": "tts"})
        assert dropped.status_code == 200
        assert dropped.json()["kind"] == "tts"

        # Bilinmeyen kategori sunucu arızası DEĞİL: gövde şeması onu daha
        # işleyiciye girmeden reddediyor (422).
        assert client.post("/api/fool/runtime/unload", json={"kind": "gpu"}).status_code == 422
