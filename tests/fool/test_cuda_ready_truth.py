"""``cuda_ready`` sürücüyü değil MOTORU sormalı.

Bu deponun en pahalı hata sınıflarından biri: "cihaz ``cuda`` yazıyordu,
motor CPU'da koşuyordu". Panel güvenle CUDA gösteriyor, kullanıcı 15 saniye
bekliyor ve neden yavaş olduğunu hiçbir yerde göremiyor.

Kök neden ölçüldü: ``_cuda_available()`` yalnızca ``nvidia-smi``nin PATH'te
olup olmadığına bakıyordu -- yani NVIDIA SÜRÜCÜSÜ kurulu olan HER makinede
``True``. Sürücünün varlığı, çıkarım motorunun CUDA kullanabildiği anlamına
gelmiyor:

  * faster-whisper ``ctranslate2`` kullanıyor, torch değil. cuBLAS/cuDNN
    eksikse ``ctranslate2.get_cuda_device_count()`` 0 döner ve motor sessizce
    CPU'ya düşer -- 0,23 sn yerine 15,16 sn.
  * Sidecar motorlarında PyPI'dan gelen torch Windows'ta CPU-only derlemedir;
    kart da sürücü de yerinde ama motor CPU'da koşar.

Bu testler "kart var mı" ile "motor kullanabiliyor mu" arasındaki farkı
tutuyor.
"""

from __future__ import annotations

import pytest

from fool import voice_models as vm


def _entry(entry_id: str):
    e = vm.entry(entry_id)
    assert e is not None, f"katalogda {entry_id} yok"
    return e


# ---------------------------------------------------------------------------
# STT: ctranslate2 sorulmali
# ---------------------------------------------------------------------------

def test_stt_surucuye_degil_ctranslate2ye_soruyor(monkeypatch) -> None:
    """Sürücü kurulu ama ctranslate2 CUDA göremiyorsa cevap ``False``."""
    e = _entry("whisper-turbo")

    # Surucu yerinde: nvidia-smi PATH'te.
    monkeypatch.setattr(vm.shutil, "which", lambda name: "/usr/bin/nvidia-smi")
    # Ama motor goremiyor -- cuBLAS/cuDNN eksik.
    monkeypatch.setattr(vm, "_ctranslate2_cuda_devices", lambda: 0)

    assert vm.cuda_ready(e) is False


def test_stt_ctranslate2_gorunce_dogru_soyluyor(monkeypatch) -> None:
    """Motorun kendi cevabi KESIN -- ustune surucu sondasi konmuyor.

    ``nvidia-smi`` on elemesi eklemek, PATH'inde o ikili olmayan ama CUDA'si
    calisan kurulumlarda dogru cevabi yanlisa cevirirdi.
    """
    e = _entry("whisper-turbo")

    monkeypatch.setattr(vm.shutil, "which", lambda name: None)
    monkeypatch.setattr(vm, "_ctranslate2_cuda_devices", lambda: 1)

    assert vm.cuda_ready(e) is True


def test_ctranslate2_yoksa_cokmuyor(monkeypatch) -> None:
    """Motor hiç kurulu değilse cevap ``False``, istisna değil."""
    def _boom() -> int:
        raise ImportError("ctranslate2 yok")

    monkeypatch.setattr(vm, "_ctranslate2_cuda_devices", _boom)

    assert vm.cuda_ready(_entry("whisper-turbo")) is False


@pytest.mark.parametrize("entry_id", ["whisper-turbo", "faster-whisper"])
def test_butun_stt_girdileri_ayni_yolu_kullaniyor(entry_id: str, monkeypatch) -> None:
    monkeypatch.setattr(vm.shutil, "which", lambda name: "/usr/bin/nvidia-smi")
    monkeypatch.setattr(vm, "_ctranslate2_cuda_devices", lambda: 0)

    assert vm.cuda_ready(_entry(entry_id)) is False


# ---------------------------------------------------------------------------
# Sidecar motorlari: torch derlemesi sorulmali (mevcut davranis korunuyor)
# ---------------------------------------------------------------------------

def test_sidecar_motoru_kendi_torchunu_soruyor(monkeypatch) -> None:
    e = _entry("kokoro")
    assert e.sidecar_specs, "kokoro sidecar motoru olmali"

    from fool import sidecar as _sidecar

    monkeypatch.setattr(vm.shutil, "which", lambda name: "/usr/bin/nvidia-smi")
    monkeypatch.setattr(_sidecar, "has_cuda_torch", lambda entry_id: False)

    assert vm.cuda_ready(e) is False


# ---------------------------------------------------------------------------
# Genel kural
# ---------------------------------------------------------------------------

def test_piper_onnxruntimeye_soruyor(monkeypatch) -> None:
    """Piper torch degil ``onnxruntime`` kullaniyor.

    Bu makinede olculdu: saglayicilar
    ``['AzureExecutionProvider', 'CPUExecutionProvider']`` -- CUDA YOK. Eski
    kod ``nvidia-smi`` gordugu icin yine de "CUDA" diyordu ve panel Piper icin
    guvenle CUDA sunuyordu.
    """
    e = _entry("piper")
    assert e.cuda_probe == "onnxruntime"

    monkeypatch.setattr(vm.shutil, "which", lambda name: "/usr/bin/nvidia-smi")
    monkeypatch.setattr(vm, "_torch_cuda_available", lambda: True)
    monkeypatch.setattr(vm, "_onnxruntime_cuda_available", lambda: False)

    assert vm.cuda_ready(e) is False

    monkeypatch.setattr(vm, "_onnxruntime_cuda_available", lambda: True)

    assert vm.cuda_ready(e) is True


def test_her_cuda_sunan_motorun_acik_bir_sondasi_var() -> None:
    """Yeni bir motor eklerken sonda secmek ZORUNLU olsun.

    Varsayilan ``torch``; yanlis yigina soran bir motor sessizce CPU'da
    kosardi. Bu test en azindan bilinen yiginlarin dogru esleştigini tutuyor.
    """
    beklenen = {
        "faster-whisper": "ctranslate2",
        "piper": "onnxruntime",
        "whisper-turbo": "ctranslate2",
    }

    for entry_id, probe in beklenen.items():
        assert _entry(entry_id).cuda_probe == probe, f"{entry_id}: yanlis sonda"


def test_nvidia_smi_tek_basina_yetmiyor(monkeypatch) -> None:
    """Sürücünün varlığı hiçbir motor için tek başına kanıt değil.

    Bu testin varlık nedeni: eski ``_cuda_available()`` tam bunu yapıyordu ve
    panel sürücü kurulu her makinede CUDA yazıyordu.
    """
    monkeypatch.setattr(vm.shutil, "which", lambda name: "/usr/bin/nvidia-smi")
    monkeypatch.setattr(vm, "_ctranslate2_cuda_devices", lambda: 0)
    monkeypatch.setattr(vm, "_torch_cuda_available", lambda: False)
    monkeypatch.setattr(vm, "_onnxruntime_cuda_available", lambda: False)

    from fool import sidecar as _sidecar

    monkeypatch.setattr(_sidecar, "has_cuda_torch", lambda entry_id: False)

    hazir = [e.id for e in vm.CATALOG if vm.cuda_ready(e)]

    assert not hazir, f"surucu disinda kanit olmadan CUDA diyen motorlar: {hazir}"


# ---------------------------------------------------------------------------
# MAKINE sorusu ile MOTOR sorusu AYRI
# ---------------------------------------------------------------------------
#
# Bu bölüm bir regresyonun ardından yazıldı. ``cuda_ready``yi motora sormaya
# çevirirken ``cuda_available``ı da ana ortamın torch'una bağlamıştım. Ama
# motorlar KENDİ izole ortamlarında koşuyor ve ana ortamda torch hiç kurulu
# değil -- sonuç: panel 16 GB'lık bir kartın üstünde "no CUDA on this machine"
# yazdı ve kullanıcı CUDA düğmesini kaybetti.
#
# İki ayrı soru:
#   cuda_available  -> KUTUDA kart var mı?      (panel düğmeyi buna göre açar)
#   cuda_ready(e)   -> ŞU MOTOR kullanabilir mi? (her motor kendi runtime'ına sorar)

def test_makine_sorusu_ana_ortam_torchuna_BAGLI_DEGIL(monkeypatch) -> None:
    """Ana ortamda torch yok ve olmaması normal -- motorlar sidecar'da."""
    monkeypatch.setattr(vm, "_nvidia_driver_present", lambda: True)
    monkeypatch.setattr(vm, "_torch_cuda_available", lambda: False)

    from fool import gpu_budget

    monkeypatch.setattr(gpu_budget, "total_vram_mb", lambda: 16_376)

    assert vm._cuda_available() is True


def test_makine_sorusu_surucu_yoksa_hayir(monkeypatch) -> None:
    monkeypatch.setattr(vm, "_nvidia_driver_present", lambda: False)

    assert vm._cuda_available() is False


def test_makine_sorusu_sonda_cokerse_SURUCUYE_guveniyor(monkeypatch) -> None:
    """Makine sorusunda yanlış "hayır", kullanıcının CUDA düğmesini kaybetmesi."""
    monkeypatch.setattr(vm, "_nvidia_driver_present", lambda: True)

    from fool import gpu_budget

    def _boom():
        raise OSError("nvidia-smi cokti")

    monkeypatch.setattr(gpu_budget, "total_vram_mb", _boom)

    assert vm._cuda_available() is True


def test_iki_soru_BIRBIRINDEN_bagimsiz(monkeypatch) -> None:
    """Kart var ama motor kullanamıyor: ikisi aynı anda doğru olabilmeli.

    Piper'da tam bu durum ölçüldü -- kart yerinde, onnxruntime'da
    CUDAExecutionProvider yok.
    """
    monkeypatch.setattr(vm, "_nvidia_driver_present", lambda: True)
    monkeypatch.setattr(vm, "_onnxruntime_cuda_available", lambda: False)

    from fool import gpu_budget

    monkeypatch.setattr(gpu_budget, "total_vram_mb", lambda: 16_376)

    assert vm._cuda_available() is True
    assert vm.cuda_ready(_entry("piper")) is False


# ---------------------------------------------------------------------------
# CPU'da pratik mi
# ---------------------------------------------------------------------------
#
# Ölçüldü: Chatterbox CUDA'da 2,10 sn. CPU'da difüzyon adımları dakikalara
# çıkıyor. Kullanıcı bir kez tıklayıp dört dakika bekleyince uygulamanın
# donduğunu sanıyor -- bunu ÖNCEDEN söylemek gerekiyor.

def test_buyuk_modeller_CPU_icin_uyariliyor() -> None:
    for entry_id in ("chatterbox", "kyutai", "qwen3-tts", "f5-tts"):
        assert vm.cpu_warning(_entry(entry_id)), f"{entry_id}: uyari yok"


def test_kucuk_modeller_uyarilmiyor() -> None:
    """Kokoro CPU'da hâlâ kullanılabilir; her modelde uyarmak gürültü."""
    for entry_id in ("piper", "kokoro", "styletts2"):
        assert vm.cpu_warning(_entry(entry_id)) == "", f"{entry_id}: gereksiz uyari"


def test_uyari_SEBEBI_ve_onerisi_iceriyor() -> None:
    message = vm.cpu_warning(_entry("chatterbox"))

    assert "minutes" in message
    assert "CUDA is strongly recommended" in message


def test_cuda_sunmayan_motor_uyarilmiyor(monkeypatch) -> None:
    """CUDA seçeneği yoksa "CUDA öner" demek anlamsız."""
    entry = _entry("chatterbox")
    cpu_only = type(entry)(**{**entry.__dict__, "devices": ("cpu",)})

    assert vm.cpu_warning(cpu_only) == ""


def test_okunamayan_boyut_uyari_URETMIYOR() -> None:
    """Tahmin edemediğimiz bir şey için uyarmak, uydurmak olurdu."""
    entry = _entry("chatterbox")
    unknown = type(entry)(**{**entry.__dict__, "size_label": ""})

    assert vm.cpu_warning(unknown) == ""
