"""Yerel-önce denetimi: hangi yüzey ağa çıkıyor?

Bu denetimin varlık nedeni, bu oturumda ölçülen iki sızıntının ORTAK yanı:
ikisi de tek tek bakıldığında görünmüyordu. STT yerel görünüyordu (``stt.local``
doluydu) ama ``stt.provider`` yazılmadığı için otomatik algılama buluta
düşebiliyordu; TTS'in varsayılanı zaten Microsoft'tu ve kimse ``tts.provider``
yazmamıştı.

Tek tek bakmak çalışmıyor. Bütün yüzeyleri BİR ARADA gösteren bir liste
gerekiyor -- "uygulamayı arkadaşıma göndersem ne dışarı çıkar?" sorusunun
tek ekranda cevabı.
"""

from __future__ import annotations

from fool import local_only


def _ids(findings) -> set[str]:
    return {f.surface for f in findings}


def test_bos_yapilandirma_her_yuzeyi_denetliyor() -> None:
    findings = local_only.audit_local_only({})
    assert _ids(findings) == {"browser", "model", "stt", "tts", "web"}


def test_tamamen_yerel_yapilandirmada_hicbir_uyari_yok() -> None:
    cfg = {
        "model": {"provider": "lmstudio"},
        "stt": {"provider": "local"},
        "tts": {"provider": "kokoro"},
        "web": {"backend": "off"},
        "browser": {"backend": "off"},
    }
    dis_cikanlar = [f for f in local_only.audit_local_only(cfg) if not f.local]
    assert not dis_cikanlar, [f.surface for f in dis_cikanlar]


def test_bulut_model_saglayicisi_yakalaniyor() -> None:
    cfg = {"model": {"provider": "openai"}}
    model = next(f for f in local_only.audit_local_only(cfg) if f.surface == "model")
    assert model.local is False
    assert "openai" in model.detail


def test_bulut_tts_yakalaniyor() -> None:
    cfg = {"tts": {"provider": "edge"}}
    tts = next(f for f in local_only.audit_local_only(cfg) if f.surface == "tts")
    assert tts.local is False


def test_yazilmamis_stt_belirsiz_sayiliyor_yerel_degil() -> None:
    """``stt.provider`` yoksa sonuç ÇALIŞMA ZAMANINDA belli oluyor.

    Tam da bu belirsizlik yüzünden mikrofon sesi buluta gidebiliyordu;
    "muhtemelen yerel" diye geçiştirmek denetimin işini yapmaması olurdu.
    """
    stt = next(f for f in local_only.audit_local_only({}) if f.surface == "stt")
    assert stt.local is False
    assert "allow_cloud_fallback" in stt.remedy or "provider" in stt.remedy


def test_acik_bulut_tercihi_de_yerel_degil() -> None:
    cfg = {"stt": {"provider": "local", "allow_cloud_fallback": True}}
    stt = next(f for f in local_only.audit_local_only(cfg) if f.surface == "stt")
    assert stt.local is False


def test_yerel_model_saglayicilarinin_hepsi_taniniyor() -> None:
    for provider in ("lmstudio", "ollama", "llamacpp", "vllm", "custom"):
        cfg = {"model": {"provider": provider}}
        model = next(f for f in local_only.audit_local_only(cfg) if f.surface == "model")
        assert model.local is True, provider


def test_her_bulguda_nasil_duzeltilecegi_yaziyor() -> None:
    """Yalnızca "dışarı çıkıyor" demek kullanıcıyı belgelerde dolaştırıyordu."""
    for f in local_only.audit_local_only({"model": {"provider": "openai"}}):
        if not f.local:
            assert f.remedy.strip(), f"{f.surface}: cozum yazilmamis"


def test_bozuk_yapilandirmada_cokmuyor() -> None:
    for bad in (None, [], "nonsense", {"model": "openai", "stt": 7}):
        findings = local_only.audit_local_only(bad)
        assert len(findings) == 5
