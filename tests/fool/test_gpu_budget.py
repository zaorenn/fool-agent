"""16 GB kartta LLM + STT + TTS aynı belleği paylaşıyor.

Ölçüldü (RTX 4070 Ti SUPER, LM Studio'da qwen3.5-9b açıkken):

    nvidia-smi --query-gpu=memory.total,memory.used,memory.free
    -> 16376, 10480, 5582    (MB)

Yani model tek başına belleğin üçte ikisini tutuyor ve geriye 5,5 GB kalıyor.
Whisper large-v3-turbo (float16) ve Chatterbox aynı anda o boşluğa girmeye
çalışıyor.

Kimse koordine etmiyordu. Daha kötüsü: konuşma tanımanın
``unload_after_idle_seconds`` varsayılanı **0 = asla boşaltma**. Bir kez
konuşan kullanıcı, oturum boyunca whisper'ı VRAM'de tutuyor -- sohbet
sırasında hiç kullanmasa bile.

CUDA'da bellek dolduğunda olan şey de sessiz sınıftan: motor OOM alıp CPU'ya
düşüyor ya da model yükleme başarısız olup sağlayıcı değişiyor. Kullanıcı
yalnızca "yavaşladı" görüyor.
"""

from __future__ import annotations

import pytest

from fool import gpu_budget


# ---------------------------------------------------------------------------
# Boşta boşaltma varsayılanı
# ---------------------------------------------------------------------------

def test_dar_kartta_asla_bosaltma_varsayilani_kabul_edilmiyor() -> None:
    """16 GB paylaşılan bir kartta "asla boşaltma" doğru varsayılan değil."""
    assert gpu_budget.default_idle_unload_seconds(16_376) > 0


def test_genis_kartta_bosaltmaya_gerek_yok() -> None:
    """48 GB'da model de motorlar da rahatça sığıyor."""
    assert gpu_budget.default_idle_unload_seconds(49_152) == 0


def test_dar_kart_daha_erken_bosaltiyor() -> None:
    dar = gpu_budget.default_idle_unload_seconds(8_192)
    orta = gpu_budget.default_idle_unload_seconds(16_376)

    assert 0 < dar <= orta


def test_kart_bilinmiyorsa_davranis_degismiyor() -> None:
    """Ölçemiyorsak varsayılanı değiştirmek kör bir müdahale olurdu."""
    assert gpu_budget.default_idle_unload_seconds(None) == 0
    assert gpu_budget.default_idle_unload_seconds(0) == 0


def test_bosaltma_suresi_bir_sohbet_turundan_uzun() -> None:
    """Tur arasında boşaltmak, her cümlede yeniden yükleme demek.

    Ölçüldü: Whisper ilk yükleme CUDA'da saniyeler sürüyor. Sohbet ritmini
    bozacak kadar kısa bir zaman aşımı, çözdüğünden çok sorun üretirdi.
    """
    assert gpu_budget.default_idle_unload_seconds(16_376) >= 120


# ---------------------------------------------------------------------------
# Yükleme kararı
# ---------------------------------------------------------------------------

def test_bos_bellek_yetiyorsa_yukleniyor() -> None:
    assert gpu_budget.fits_in_vram("whisper-turbo", free_mb=5_582) is True


def test_bos_bellek_yetmiyorsa_yuklenmiyor() -> None:
    # 400 MB bosta: hicbir motor sigmaz.
    assert gpu_budget.fits_in_vram("whisper-turbo", free_mb=400) is False


def test_pay_birakiliyor() -> None:
    """Tam sığmak sığmak değil: parçalanma ve ara belleğe pay gerekiyor.

    Bosta kalan bellegin TAMAMINI doldurmak, CUDA ayiricisinin ilk
    genislemesinde OOM demek.
    """
    tam = gpu_budget.ENGINE_VRAM_MB["whisper-turbo"]

    assert gpu_budget.fits_in_vram("whisper-turbo", free_mb=tam) is False
    assert gpu_budget.fits_in_vram("whisper-turbo", free_mb=tam + gpu_budget.HEADROOM_MB) is True


def test_bilinmeyen_motor_engellenmiyor() -> None:
    """Tahmini olmayan bir motoru bloke etmek, calisan bir seyi kirmakti."""
    assert gpu_budget.fits_in_vram("bilinmeyen-motor", free_mb=1_000) is True


def test_olcum_yoksa_engellenmiyor() -> None:
    assert gpu_budget.fits_in_vram("whisper-turbo", free_mb=None) is True


@pytest.mark.parametrize("engine", ["chatterbox", "kokoro", "qwen3-tts", "whisper-turbo"])
def test_her_cuda_motorunun_bir_tahmini_var(engine: str) -> None:
    assert gpu_budget.ENGINE_VRAM_MB[engine] > 0


def test_nvidia_smi_cagrisi_stdin_kapatiyor() -> None:
    """Windows footgun: ``stdin=`` belirtilmeyen alt süreç blokluyor.

    Bu işlev transkripsiyon yükleme yolunda çağrılıyor -- orada bir
    kilitlenme sesli turu sonsuza kadar dondururdu. Deponun kendi denetimi
    var (``scripts/check_subprocess_stdin.py``); bu test aynı kuralı burada
    da tutuyor.
    """
    import inspect

    source = inspect.getsource(gpu_budget._nvidia_smi_mb)

    assert "stdin=subprocess.DEVNULL" in source


def test_nvidia_smi_cagrisi_zaman_asimli() -> None:
    """Asılı kalan bir ``nvidia-smi`` de aynı yolu kilitlerdi."""
    import inspect

    assert "timeout=" in inspect.getsource(gpu_budget._nvidia_smi_mb)
