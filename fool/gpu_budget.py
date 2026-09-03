"""LLM, konuşma tanıma ve seslendirme aynı 16 GB'ı paylaşıyor.

Ölçüldü (RTX 4070 Ti SUPER, LM Studio'da qwen3.5-9b açıkken):

    nvidia-smi --query-gpu=memory.total,memory.used,memory.free
    -> 16376, 10480, 5582    (MB)

Model tek başına belleğin üçte ikisini tutuyor; geriye 5,5 GB kalıyor ve
Whisper large-v3-turbo ile TTS motorları o boşluğu paylaşmak zorunda.

Kimse koordine etmiyordu. Daha kötüsü: konuşma tanımanın
``unload_after_idle_seconds`` varsayılanı **0 = asla boşaltma**. Bir kez
konuşan kullanıcı oturum boyunca whisper'ı VRAM'de tutuyor -- sohbet
sırasında bir daha hiç kullanmasa bile.

Bellek dolduğunda olan da sessiz sınıftan: motor OOM alıp CPU'ya düşüyor ya
da yükleme başarısız olup sağlayıcı değişiyor. Kullanıcı yalnızca "yavaşladı"
görüyor -- bu depodaki en pahalı hataların hepsi bu şekilde görünüyordu.

Bu modül ölçer ve karar verir; hiçbir şeyi kendi başına yüklemez/boşaltmaz.
"""

from __future__ import annotations

import shutil
import subprocess

#: Motor başına kabaca VRAM tüketimi (MB).
#:
#: Tahminler ağırlık boyutundan ve ölçülen kullanımdan geliyor; kesin sayı
#: değiller ve olmaları da gerekmiyor -- karar "sığar mı" sorusunun kaba
#: cevabı. Fazla iyimser olmamak için yukarı yuvarlandılar: az tahmin etmek
#: OOM demek, fazla tahmin etmek yalnızca gereksiz bir uyarı.
ENGINE_VRAM_MB = {
    "chatterbox": 3_500,
    "faster-whisper": 1_600,
    "kokoro": 700,
    "piper": 300,
    "qwen3-tts": 2_500,
    # StyleTTS 2: ~150M parametre + BERT/ASR yardimci aglari. Olculdukten
    # sonra bu sayi gercek degerle degistirilecek.
    "styletts2": 1_200,
    # Kyutai 1,6B parametre; F5-TTS ~300M + vocoder. Olculdukten sonra
    # gercek degerlerle degistirilecek.
    "kyutai": 3_500,
    "f5-tts": 2_000,
    "whisper-turbo": 2_000,
}

#: Boşta kalan belleğin TAMAMINI doldurmak, CUDA ayırıcısının ilk
#: genişlemesinde OOM demek. Parçalanma ve ara bellek için pay.
HEADROOM_MB = 768

#: Bu boyutun altındaki kartlarda motorlar boşta tutulmuyor. 24 GB üstünde
#: 9B'lik bir model + motorlar rahatça sığıyor ve boşaltmak yalnızca yeniden
#: yükleme gecikmesi üretirdi.
SHARED_CARD_LIMIT_MB = 24_576


def _nvidia_smi_mb(field: str) -> int | None:
    """``nvidia-smi``den tek bir bellek alanını MB olarak oku.

    Torch ithal edilmiyor: bu işlev yükleme yolunda çağrılıyor ve torch'u
    oraya sokmak saniyeler ekliyor (ayrıca faster-whisper torch kullanmıyor).
    """
    if not shutil.which("nvidia-smi"):
        return None
    try:
        out = subprocess.run(
            ["nvidia-smi", f"--query-gpu={field}", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
            # ``stdin`` ACIKCA kapatiliyor (depo kurali, bkz.
            # ``scripts/check_subprocess_stdin.py``). Windows'ta stdin
            # belirtilmeyen bir alt surec ebeveynin konsol tutamacini miras
            # aliyor ve okumaya kalkarsa BLOKLUYOR. Bu islev transkripsiyon
            # yukleme yolunda cagriliyor -- orada bir kilitlenme sesli turu
            # sonsuza kadar dondururdu.
            stdin=subprocess.DEVNULL,
        )
    except Exception:
        return None

    first = out.stdout.strip().splitlines()
    if not first:
        return None
    try:
        return int(first[0].strip())
    except ValueError:
        return None


def total_vram_mb() -> int | None:
    return _nvidia_smi_mb("memory.total")


def free_vram_mb() -> int | None:
    return _nvidia_smi_mb("memory.free")


def fits_in_vram(engine_id: str, free_mb: int | None) -> bool:
    """*engine_id* şu anki boş belleğe sığar mı?

    Bilmediğimiz her durumda ``True``: ölçemediğimiz ya da tahmini olmayan
    bir motoru bloke etmek, çalışan bir şeyi kırmak olurdu. Bu işlevin görevi
    öngörülebilir bir OOM'u önlemek, belirsizlikte yasak koymak değil.
    """
    if free_mb is None:
        return True

    need = ENGINE_VRAM_MB.get(engine_id)
    if need is None:
        return True

    return free_mb >= need + HEADROOM_MB


def default_idle_unload_seconds(total_mb: int | None) -> int:
    """Boşta boşaltma varsayılanı (saniye). ``0`` = asla.

    Kart ölçülemiyorsa ``0``: varsayılanı kör bir tahminle değiştirmek,
    çözdüğünden çok sorun üretirdi.

    Süre bilerek bir sohbet turundan uzun. Whisper'ın ilk yüklemesi CUDA'da
    saniyeler sürüyor; tur arasında boşaltmak her cümlede yeniden yükleme
    demekti ve sohbet ritmini bozardı.
    """
    if not total_mb or total_mb <= 0:
        return 0
    if total_mb >= SHARED_CARD_LIMIT_MB:
        return 0
    if total_mb <= 8_192:
        return 180
    return 300
