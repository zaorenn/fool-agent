"""Kurulu olmak ile ÇALIŞMAK ayrı: motor sağlığı sondası.

Ölçülen hata (bu makine, F5-TTS):

    find_spec("f5_tts")  -> True     <- panelin gördüğü, "installed"
    import torchcodec    -> OSError  <- sentezin gördüğü

    FileNotFoundError: Could not find module
    ...torchcodec/libtorchcodec_core8.dll (or one of its dependencies)

Panel motoru "installed" VE "klonlanabilir" gösteriyordu. Kullanıcı bir ses
kaydı yükleyip klon seçiyor ve hiçbir şey duymuyordu -- yaptığı işin boşa
gittiğini bile öğrenemiyordu.
"""

from __future__ import annotations

import pytest

from fool import engine_health


class _Entry:
    """Sonda için yeterli olan en küçük öğe."""

    def __init__(self, entry_id="test-engine", modules=(), help_text="", sidecar=()):
        self.id = entry_id
        self.runtime_imports = modules
        self.runtime_help = help_text
        self.sidecar_specs = sidecar


@pytest.fixture(autouse=True)
def _clean_cache(tmp_path, monkeypatch):
    """Her sınav kendi önbelleğiyle koşsun."""
    monkeypatch.setattr(engine_health, "_cache_path", lambda: tmp_path / "engine-health.json")
    engine_health._MEMO.clear()
    yield
    engine_health._MEMO.clear()


# ---------------------------------------------------------------------------
# Sonda
# ---------------------------------------------------------------------------

def test_modul_bildirmeyen_motor_HIC_sondalanmiyor(monkeypatch) -> None:
    """Sondanın bedeli yalnızca ihtiyacı olan motor için ödeniyor.

    Katalog soğuk 1,25 sn / sıcak 0,14 sn ölçüldü; her motora alt süreç
    açmak paneli kullanılamaz hâle getirirdi.
    """
    def _boom(*a, **k):
        raise AssertionError("sonda kosmamaliydi")

    monkeypatch.setattr(engine_health, "_run_probe", _boom)

    assert engine_health.error_for(_Entry(modules=())) == ""


def test_saglikli_motor_bos_donuyor(monkeypatch) -> None:
    from fool import cuda_probe_cache

    monkeypatch.setattr(cuda_probe_cache, "fingerprint", lambda name: "mark-1")
    monkeypatch.setattr(engine_health, "_run_probe", lambda *a: "")

    assert engine_health.error_for(_Entry(modules=("torchcodec",))) == ""


def test_bozuk_motor_MOTORUN_KENDI_caresini_donuyor(monkeypatch) -> None:
    """Ham istisna metni panelde işe yaramıyor.

    Ölçüldü: torchcodec'in ilk satırı ``Could not load libtorchcodec. Likely
    causes:`` -- asıl bilgi 30 satır aşağıda. Kullanıcının görmesi gereken
    şey NE YAPACAĞI.
    """
    from fool import cuda_probe_cache

    monkeypatch.setattr(cuda_probe_cache, "fingerprint", lambda name: "mark-1")
    monkeypatch.setattr(
        engine_health, "_run_probe", lambda *a: "torchcodec: Could not load libtorchcodec. Likely causes:"
    )

    entry = _Entry(modules=("torchcodec",), help_text="Install a shared FFmpeg build.")

    assert engine_health.error_for(entry) == "Install a shared FFmpeg build."


def test_care_yoksa_HAM_hataya_dusuluyor(monkeypatch) -> None:
    """Belirsiz bir hata bile sessizlikten iyidir."""
    from fool import cuda_probe_cache

    monkeypatch.setattr(cuda_probe_cache, "fingerprint", lambda name: "mark-1")
    monkeypatch.setattr(engine_health, "_run_probe", lambda *a: "torchcodec: boom")

    assert engine_health.error_for(_Entry(modules=("torchcodec",))) == "torchcodec: boom"


def test_sonda_bir_kez_kosuyor(monkeypatch) -> None:
    """Parmak izi aynıyken ikinci çağrı alt süreç açmıyor.

    Ölçüldü: sonda 1,47 sn, önbellekli cevap 0,078 sn.
    """
    from fool import cuda_probe_cache

    monkeypatch.setattr(cuda_probe_cache, "fingerprint", lambda name: "mark-1")
    calls = []
    monkeypatch.setattr(engine_health, "_run_probe", lambda *a: calls.append(1) or "boom")

    entry = _Entry(modules=("torchcodec",))

    assert engine_health.error_for(entry) == "boom"
    assert engine_health.error_for(entry) == "boom"
    assert len(calls) == 1


def test_parmak_izi_degisince_sonda_YENIDEN_kosuyor(monkeypatch) -> None:
    """Kurulum bir DLL getirmiş olabilir; panel "çalışmıyor" demeye devam edemez."""
    from fool import cuda_probe_cache

    marks = iter(["mark-1", "mark-2", "mark-2"])
    monkeypatch.setattr(cuda_probe_cache, "fingerprint", lambda name: next(marks))

    answers = iter(["boom", ""])
    monkeypatch.setattr(engine_health, "_run_probe", lambda *a: next(answers))

    entry = _Entry(modules=("torchcodec",))

    assert engine_health.error_for(entry) == "boom"
    assert engine_health.error_for(entry) == ""


def test_sondanin_KENDISI_kosamazsa_motor_bozuk_SAYILMIYOR(monkeypatch) -> None:
    """Bilmemek ile bozuk olmak ayrı şeyler.

    Çalışan bir motoru bozuk göstermek, bozuk olanı çalışır göstermekten daha
    kötü: kullanıcı kullandığı sesi kaybediyor.
    """
    from fool import cuda_probe_cache

    monkeypatch.setattr(cuda_probe_cache, "fingerprint", lambda name: "mark-1")
    monkeypatch.setattr(engine_health, "_interpreter", lambda entry: None)

    assert engine_health.error_for(_Entry(modules=("torchcodec",))) == ""


def test_ortam_yoksa_saglik_sorusu_SORULMUYOR(monkeypatch) -> None:
    """Kurulu değil, ayrı bir durum -- "bozuk" demek yanlış olurdu."""
    from fool import cuda_probe_cache

    monkeypatch.setattr(cuda_probe_cache, "fingerprint", lambda name: "")

    def _boom(*a, **k):
        raise AssertionError("sonda kosmamaliydi")

    monkeypatch.setattr(engine_health, "_run_probe", _boom)

    assert engine_health.error_for(_Entry(modules=("torchcodec",))) == ""


# ---------------------------------------------------------------------------
# Sondanın gerçekten koştuğu alt süreç
# ---------------------------------------------------------------------------

def test_sonda_GERCEKTEN_ice_aktariyor() -> None:
    """``find_spec`` yetmiyordu; ayrım tam olarak burada.

    Gerçek bir alt süreçle sınanıyor: sahte bir sonda bu farkı ıskalardı.
    """
    entry = _Entry(modules=("this_module_does_not_exist_anywhere",))

    assert "this_module_does_not_exist_anywhere" in engine_health._run_probe(
        entry, entry.runtime_imports
    )


def test_ice_aktarilabilen_modul_saglikli() -> None:
    entry = _Entry(modules=("json",))

    assert engine_health._run_probe(entry, entry.runtime_imports) == ""


# ---------------------------------------------------------------------------
# Sonucun kullanıcıya dokunduğu yerler
# ---------------------------------------------------------------------------

def test_bozuk_motor_KLONLANABILIR_gorunmuyor(monkeypatch) -> None:
    """§6.2'nin somut zararı: klon yükleyip hiçbir şey duymamak.

    F5-TTS bu makinede kurulu görünüyor ve klonlama arayüzü ona AÇIKTI.
    Kullanıcı 5-10 saniyelik bir kayıt yüklüyor, klonu seçiyor, sonra hiçbir
    şey duymuyordu.
    """
    from fool import voice_models as vm

    monkeypatch.setattr(vm, "status", lambda entry_id: {
        "id": entry_id,
        "installed": True,
        "usable": False,
        "engine_error": "needs shared FFmpeg",
    })

    entry = vm.entry("f5-tts")
    assert entry is not None
    # Klonlama YETENEGI duruyor, ama bu KURULUMDA sunulmuyor.
    assert (entry.provider_id or entry.id) in vm.CLONE_CAPABLE

    row = vm._catalog_row(entry, {})
    assert row["clone_capable"] is False
    assert row["clone"] == ""
    assert row["clone_help"] == ""


def test_bozuk_motor_OTOMATIK_SECILMIYOR(monkeypatch) -> None:
    """``tts.provider`` yazılmamışken bozuk bir motora düşmek sessizliktir.

    ``f5tts`` yerel tercih sırasında beşinci: kokoro/piper/styletts2/kyutai
    kurulu olmayan bir makinede otomatik seçim onu seçerdi ve kullanıcı
    yalnızca bir günlük satırı bulurdu.
    """
    from fool import local_only, voice_models as vm
    from tools import tts_tool

    assert "f5tts" in local_only.LOCAL_TTS_PROVIDERS

    def _status(entry_id):
        e = vm.entry(entry_id)
        broken = (e.provider_id or e.id) == "f5tts"
        return {"installed": True, "usable": not broken}

    monkeypatch.setattr(vm, "status", _status)

    available = tts_tool._installed_local_tts()
    assert "f5tts" not in available
    assert "kokoro" in available


def test_f5tts_bu_MAKINEDE_caresini_tasiyor() -> None:
    """Katalog kaydı, ölçülen hatanın çaresini kullanıcı diliyle taşıyor."""
    from fool import voice_models as vm

    entry = vm.entry("f5-tts")
    assert entry is not None
    assert entry.runtime_imports == ("torchcodec",)
    assert "FFmpeg" in entry.runtime_help
    # Kullanıcıya görünen metin İNGİLİZCE.
    assert entry.runtime_help.isascii()
