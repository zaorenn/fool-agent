"""Yerel ses modelleri: katalog, durum tespiti ve ilerlemeli kurulum.

Neden bu var
------------
TTS ve STT motorları upstream'de "ilk kullanımda kendiliğinden inen" şeyler.
Pratikte bu şu demek: kullanıcı sesi açıyor, ajan bir şey söylemeye çalışıyor,
arka planda 200 MB'lık bir indirme başlıyor ve arayüzde hiçbir şey görünmüyor.
Ne kadar sürdüğü, ne indiği, bittiği belli değil — sadece "çalışmıyor" gibi
duruyor. Kullanıcı bunu üç kez istedi: modeller uygulama içinden indirilebilmeli
ve ilerleme görülebilmeli.

İlerleme neden iki farklı biçimde ölçülüyor
-------------------------------------------
İki ayrı iş var ve dürüst ilerleme ikisinde aynı şey değil:

1. **Motor kurulumu** (pip). pip'in gerçek bir yüzdesi yoktur; paketleri
   sırayla indirir ve çözümleyicisi ne kadar iş kaldığını önceden bilmez.
   Burada uydurma bir yüzde çubuğu göstermek yalan olurdu, o yüzden AŞAMA
   bildiriliyor ("çözümleniyor", "downloading", "installing") ve pip'in kendi
   çıktısının son satırı canlı gösteriliyor.
2. **Model dosyası** (HTTP). Burada ``Content-Length`` var, yani gerçek bir
   yüzde var. Baytlar sayılıyor ve yüzde gerçekten baytlardan geliyor.

Bu ayrım kasıtlı: bir çubuk gösteriyorsak arkasında gerçek bir ölçü olmalı.

Zone A
------
Bu dosyayı upstream bilmiyor; birleştirmede çakışamaz.
"""

from __future__ import annotations

import hashlib
import queue
import re
import shutil
import threading
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Final, Iterable, Literal

Kind = Literal["tts", "stt"]
Device = Literal["cpu", "cuda"]


# ---------------------------------------------------------------------------
# Katalog
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VoiceAsset:
    """İndirilebilir tek bir dosya (ses modeli, yapılandırma)."""

    url: str
    filename: str
    #: Yaklaşık boyut (bayt). Sunucu ``Content-Length`` vermezse ilerleme
    #: yüzdesi için bu kullanılır; vermezse yüzde yerine inen bayt gösterilir.
    approx_bytes: int = 0


CudaProbe = Literal["ctranslate2", "onnxruntime", "torch"]


@dataclass(frozen=True)
class VoiceKnob:
    """Motorun KENDİ ad alanından okuduğu, ayarlanabilir tek bir sayı.

    Neden katalogda
    ---------------
    Kullanıcı "ayarlardan ses modellerinin exaggeration gibi ayarlarını
    yapamıyoruz" dedi ve haklıydı: bu değerler ``config.yaml``da duruyor,
    motor onları okuyor, ama arayüzde hiçbir yerde görünmüyorlardı. Tek yolu
    dosyayı elle açmaktı.

    Kolları burada tutmanın sebebi, panelin YALAN SÖYLEMEMESİ. Arayüze elle
    kaydırıcı koymak, motorun gerçekten okumadığı bir değeri ayarlıyormuş gibi
    göstermeye çok açık -- ölçülmüş bir hata sınıfı: ``tts.<motor>.voice``
    yıllarca yazılıyor ve hiç okunmuyordu. Kol katalogda, motorun kaydının
    yanında duruyor; kimse okumuyorsa kayıt da yok.

    Kapsam DAR: yalnızca motorun ``config["<motor>"]`` sözlüğünden okuduğu
    değerler. Üst seviye ``tts.speed`` burada YOK, çünkü o motora değil bütün
    motorlara ait ve motor başına gösterilseydi her birinde ayrı sanılırdı.
    """

    #: Yapılandırma anahtarı: ``tts.<motor>.<id>``.
    id: str
    label: str
    minimum: float
    maximum: float
    step: float
    #: Ayarlanmamışken motorun kullandığı değer.
    default: float
    #: Kullanıcı diliyle NE YAPTIĞI -- sayının kendisi hiçbir şey anlatmıyor.
    help: str = ""


@dataclass(frozen=True)
class VoiceEntry:
    """Katalogda tek bir kurulabilir öğe."""

    id: str
    label: str
    kind: Kind
    #: Kullanıcıya tek cümlelik açıklama — neden bunu seçsin?
    summary: str
    #: ``tts.provider`` / ``stt.provider`` yapılandırmasına yazılan ad.
    #:
    #: Katalog kimliğinden AYRI tutuluyor çünkü ikisi farklı şeyler: kimlik
    #: indirilen paketi, bu ad ise ajanın konuşurken kullandığı sağlayıcıyı
    #: gösteriyor (``qwen3-tts`` indirilir, ``qwen3`` seçilir). Boş bırakılırsa
    #: kimliğin kendisi kullanılır.
    provider_id: str = ""
    #: ``tools.lazy_deps`` grubu; motor paketi bundan kurulur.
    dep_group: str | None = None
    #: Bu öğeyi "kurulu" sayan Python modülü.
    probe_module: str | None = None
    #: CUDA için ek paket grubu (varsa).
    cuda_group: str | None = None
    devices: tuple[Device, ...] = ("cpu",)
    #: CUDA'yi HANGI calisma zamani belirliyor.
    #:
    #: Bu alan var cunku "kart var mi" ile "motor kullanabiliyor mu" farkli
    #: sorular ve her motor farkli bir yigina soruyor. Ornekler olculdu:
    #: faster-whisper torch degil ``ctranslate2`` kullaniyor; Piper
    #: ``onnxruntime`` kullaniyor ve bu makinede saglayicilari
    #: ``['AzureExecutionProvider', 'CPUExecutionProvider']`` -- yani CUDA
    #: YOK, ama ``nvidia-smi`` var oldugu icin panel CUDA yaziyordu.
    #:
    #: ``sidecar_specs`` doluysa bu alan yok sayilir: cevap sidecar'in kendi
    #: torch derlemesinden gelir.
    cuda_probe: CudaProbe = "torch"
    #: Doluysa motor ANA ortama DEGIL, kendi izole ortamina kurulur.
    #: Gerekce ``fool/sidecar.py`` basliginda olculerek anlatildi: bu
    #: motorlarin ucu de paylasilan paketleri geriye dusuruyor (biri bir CVE
    #: duzeltmesini, biri Hindsight'i kiriyor).
    sidecar_specs: tuple[str, ...] = ()
    #: CUDA icin ana kurulumdan SONRA uygulanan paketler ve indeksleri.
    sidecar_cuda_specs: tuple[str, ...] = ()
    sidecar_cuda_index: str = ""
    #: PyPI'da olmayan, resmi URL'den gelen ek tekerlekler.
    sidecar_wheels: tuple[str, ...] = ()
    #: GERCEKTEN ice aktarilabilmesi gereken modul(ler).
    #:
    #: ``probe_module`` yalnizca DISKTE var mi diye bakiyor (``find_spec``).
    #: Bu alan ise "ice aktariliyor mu" sorusunun cevabini istiyor ve ikisi
    #: ayrisabiliyor: F5-TTS'in ``f5_tts``i diskte duruyor ama ``torchcodec``
    #: paylasilan FFmpeg DLL'lerini bulamadigi icin patliyor. Panel "kurulu"
    #: diyor, sentez sessizce dusuyordu.
    #:
    #: AYIRT EDICI ve UCUZ modul secilmeli: motorun kendisini ice aktarmak
    #: torch yuklemek demek (olculdu, motor basina 4-5 sn), oysa torchcodec
    #: DLL asamasinda 0,9 sn'de dusuyor. Sonuc zaten onbellekleniyor
    #: (``fool/engine_health.py``).
    #: Motorun ILK KULLANIMDA indirdigi HuggingFace deposu.
    #:
    #: Paketin kurulu olmasi ile motorun CALISABILIR olmasi ayri seyler.
    #: Katalog yalnizca pakete bakiyordu, yani agirliklar hic inmemisken de
    #: "installed" diyordu -- ve panel indirme dugmesini GOSTERMIYORDU.
    #: Kullanicinin arkadasinin makinesinde tam olarak bu oldu: modeller
    #: yuklu degil ama yukluymus gibi gorunuyor ve indirtme yolu yok.
    weights_repo: str = ""
    runtime_imports: tuple[str, ...] = ()
    #: Panelde GOSTERILMIYOR.
    #:
    #: Kayit SILINMIYOR: kurulu bir motoru katalogdan cikarmak, kullanicinin
    #: diskindeki gigabaytlari gorunmez yapardi ve secili olan oysa sesi
    #: sessizce keserdi. Gizlemek geri alinabilir; silmek degil.
    #:
    #: KURAL (yalnizca "yavas" DEGIL -- iki kosul):
    #:
    #:   1. Cumle basina olculen sure ``SLOW_ENGINE_MS``i asiyorsa gizlenir.
    #:      Olculen degerler (sicak, cumle basina):
    #:        piper 120 / kokoro 200 / styletts2 556 / chatterbox 1894 /
    #:        kyutai 2517 / qwen3-tts 9423
    #:
    #:   2. AMA motor tek klonlama yoluysa gizlenMEZ. Chatterbox 1894 ms ile
    #:      esigin altinda kaliyor; kyutai 2517 ile ustunde. Aradaki fark 0,6
    #:      saniye ve yalnizca hiza bakan biri "tutarsiz" deyip chatterbox'i da
    #:      gizlerdi -- bu, kullanicinin klonladigi sesi (Ultron) seciciden
    #:      sessizce silmek olurdu.
    #:
    #: Kural BURAYA yazildi cunku daha once yalnizca "yavas olan gizlenir"
    #: yaziyordu ve gercek kural o degildi. ``tests/fool/test_voice_visibility``
    #: ikisini birden sabitliyor.
    hidden: bool = False
    #: ``runtime_imports`` dustugunde KULLANICIYA gosterilecek cumle.
    #:
    #: Ham istisna metni yetmiyor: torchcodec'in ilk satiri ``Could not load
    #: libtorchcodec. Likely causes:`` ve asil bilgi 30 satir asagida.
    #: Kullanicinin panelde gormesi gereken sey NE YAPACAGI.
    runtime_help: str = ""
    #: Paket kurulduktan SONRA agirliklari indiren Python parcasi.
    #:
    #: Neden gerekli: faster-whisper paketi model agirliklarini TASIMIYOR;
    #: ilk kullanimda sessizce indiriyor. Kullanici o an sadece "cok yavas"
    #: goruyor. Burada indirme kurulumun parcasi oluyor, yani ilerleme
    #: cubugunda gorunuyor.
    warmup: str = ""
    #: Isinma ve model kimligi icin kullanilan ad.
    model_id: str = ""
    #: Bu motorun SES listesi: (kimlik, aciklama).
    #:
    #: Sabit liste yalnizca kendi ses kumesi olan motorlar icin. Piper'in
    #: sesleri ayri ayri INEN dosyalar oldugu icin listesi diskten uretiliyor:
    #: inmemis bir sesi sunmak, secildiginde calisma aninda patlardi.
    voices: tuple[tuple[str, str], ...] = ()
    #: Bu motorun ayarlanabilir sayıları (bkz. ``VoiceKnob``).
    knobs: tuple[VoiceKnob, ...] = ()
    assets: tuple[VoiceAsset, ...] = ()
    #: Yaklaşık toplam indirme boyutu, kullanıcıya gösterilir.
    size_label: str = ""
    recommended: bool = False


#: Piper sesleri Rhasspy'nin HuggingFace deposundan geliyor; ``.onnx`` ve yanında
#: ``.onnx.json`` olmak zorunda — Piper ikisini birden arar, biri eksikse
#: çalışma anında anlaşılmaz bir hata verir.
_PIPER_BASE: Final = (
    "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium"
)


CATALOG: Final[tuple[VoiceEntry, ...]] = (
    VoiceEntry(
        id="piper",
        label="Piper",
        kind="tts",
        summary=(
            "Fast and fully local. Runs faster than real time even on CPU — "
            "the most balanced choice for everyday use."
        ),
        dep_group="tts.piper",
        probe_module="piper",
        cuda_group="tts.piper_cuda",
        devices=("cpu", "cuda"),
        cuda_probe="onnxruntime",
        assets=(
            VoiceAsset(
                url=f"{_PIPER_BASE}/en_US-lessac-medium.onnx",
                filename="en_US-lessac-medium.onnx",
                approx_bytes=63_000_000,
            ),
            VoiceAsset(
                url=f"{_PIPER_BASE}/en_US-lessac-medium.onnx.json",
                filename="en_US-lessac-medium.onnx.json",
                approx_bytes=5_000,
            ),
        ),
        size_label="~63 MB",
        recommended=True,
        #: SEÇİLEBİLİR sesler -- ve bu liste bir DİL listesi.
        #:
        #: Piper'ın sağlayıcısı zaten herhangi bir ses adını kabul edip ilk
        #: kullanımda indiriyor (``_resolve_piper_voice_path`` ->
        #: ``piper.download_voices``). Yani motor 40+ dili destekliyordu; ama
        #: katalog TEK bir İngilizce ses bağlıyor ve ``voices`` boştu, yani
        #: arayüzde seçilecek hiçbir şey yoktu.
        #:
        #: Ölçülen sonuç: Türkçe konuşmak isteyen kullanıcı için CPU'da hızlı
        #: çalışan bir seçenek VARDI ama ulaşılamıyordu -- motor İngilizce sesle
        #: Türkçe metni okuyup anlaşılmaz bir şey üretiyordu.
        #:
        #: İndirme ilk kullanımda ve ses BAŞINA oluyor; her biri ~63 MB.
        voices=(
            ("tr_TR-dfki-medium", "Türkçe - dfki (orta kalite, ~63 MB)"),
            ("en_US-lessac-medium", "English (US) - lessac (~63 MB)"),
            ("en_GB-alba-medium", "English (GB) - alba (~63 MB)"),
            ("de_DE-thorsten-medium", "Deutsch - thorsten (~63 MB)"),
            ("fr_FR-siwis-medium", "Français - siwis (~63 MB)"),
            ("es_ES-davefx-medium", "Español - davefx (~63 MB)"),
            ("it_IT-riccardo-x_low", "Italiano - riccardo (~20 MB)"),
            ("ru_RU-dmitri-medium", "Русский - dmitri (~63 MB)"),
        ),
    ),
    VoiceEntry(
        id="kokoro",
        weights_repo="hexgrad/Kokoro-82M",
        label="Kokoro",
        kind="tts",
        summary=(
            "Surprisingly natural for its size. Better intonation than Piper, "
            "still local and quick."
        ),
        probe_module="kokoro",
        sidecar_specs=("kokoro==0.9.4", "soundfile==0.14.0"),
        sidecar_cuda_index="https://download.pytorch.org/whl/cu126",
        voices=(
            ("af_heart", "American female - warm"),
            ("af_bella", "American female - clear"),
            ("af_nicole", "American female - soft"),
            ("am_michael", "American male - even"),
            ("am_puck", "American male - lively"),
            ("bf_emma", "British female"),
            ("bm_george", "British male"),
        ),
        # Kokoro spaCy'nin ``en_core_web_sm`` modelini istiyor ve o PyPI'da
        # YOK. Bu adim olmadan motor kuruluyor ama ilk sentezde E050 veriyor.
        sidecar_wheels=(
            "https://github.com/explosion/spacy-models/releases/download/"
            "en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl",
        ),
        devices=("cpu", "cuda"),
        size_label="~1,3 GB",
    ),
    VoiceEntry(
        id="styletts2",
        label="StyleTTS 2",
        kind="tts",
        summary=(
            "Kokoro-class speed with noticeably more natural prosody. "
            "Not autoregressive, so it stays steady on long sentences "
            "instead of drifting. English."
        ),
        provider_id="styletts2",
        knobs=(
            VoiceKnob(
                id="expressiveness",
                label="Expressiveness",
                minimum=0.0,
                maximum=1.0,
                step=0.05,
                default=0.3,
                help="How much the reference voice's style carries into the reading.",
            ),
            VoiceKnob(
                id="diffusion_steps",
                label="Quality steps",
                minimum=3,
                maximum=20,
                step=1,
                default=5,
                help="More steps sound better and take longer, per sentence.",
            ),
        ),
        probe_module="styletts2",
        # Kendi ortamina SART: paketin pinleri 2024'ten ve sert --
        # ``huggingface-hub<0.20``, ``accelerate<0.26``, ``langchain<0.2``,
        # ``filelock<3.13``. Ana ortama kurmak faster-whisper'i ve
        # transformers'i geriye dusururdu. Python 3.13'te 133 pakete
        # cozuluyor (uv ile dogrulandi, tahmin degil).
        # ``soundfile`` BILEREK pinlenmiyor: styletts2 kendisi
        # ``soundfile>=0.12.1,<0.13`` istiyor ve ustune ``0.14.0`` yazmak
        # kurulumu "requirements are unsatisfiable" ile dusuruyordu (olculdu).
        # Diger motorlarda pin var cunku onlar soundfile'i kendileri
        # cekmiyor.
        sidecar_specs=("styletts2==0.1.6",),
        sidecar_cuda_index="https://download.pytorch.org/whl/cu126",
        devices=("cpu", "cuda"),
        cuda_probe="torch",
        # Yerlesik ses bir tane; ikinci bir ses referans kayit birakilarak
        # klonlaniyor (bkz. eklentinin ``target_voice_path`` yolu).
        voices=(("default", "Built-in voice - or drop in a reference clip"),),
        size_label="~1,5 GB",
    ),
    VoiceEntry(
        id="kyutai",
        # Olculdu: 2,5-11 sn/cumle. Sesli sohbet icin kullanilamaz.
        hidden=True,
        label="Kyutai TTS",
        kind="tts",
        summary=(
            "Built for live conversation, not for reading. Streams audio as it "
            "generates, so the first word starts before the sentence is done. "
            "English and French."
        ),
        provider_id="kyutai",
        probe_module="moshi",
        # Adaylar arasinda EN YALIN bagimlilik agaci: Python 3.13'te 38
        # pakete cozuluyor (styletts2 133, f5-tts 148 -- uv ile olculdu).
        # Yine de kendi ortaminda: torch surumunu kendi pinliyor.
        # ``soundfile`` ACIKCA ekleniyor: moshi onu cekmiyor ve saglayici
        # ciktiyi PCM_16 yazmak icin ona ihtiyac duyuyor. Olculdu -- ilk
        # sentez "No module named 'soundfile'" ile dustu.
        sidecar_specs=("moshi==0.2.13", "soundfile==0.14.0"),
        sidecar_cuda_index="https://download.pytorch.org/whl/cu126",
        devices=("cpu", "cuda"),
        cuda_probe="torch",
        # Eklentideki ``_VOICES`` ile AYNI olmak zorunda: panel katalogu
        # okuyor, eklentiyi degil. Once burasi bostu ve kullanici uc sesi
        # olan bir motorun tek sesi varmis gibi goruyordu.
        # ``tests/fool/test_voice_choices.py`` ikisini karsilastiriyor.
        voices=(
            ("expresso/ex03-ex01_happy_001_channel1_334s.wav", "Cheerful, lively"),
            ("expresso/ex03-ex02_narration_001_channel1_674s.wav", "Narrator, calm"),
            ("expresso/ex04-ex01_happy_001_channel1_334s.wav", "Cheerful, second speaker"),
        ),
        size_label="~3,5 GB",
    ),
    VoiceEntry(
        id="f5-tts",
        weights_repo="SWivid/F5-TTS",
        # Bu makinede hic calismiyor (torchcodec/paylasilan FFmpeg) ve yavas.
        hidden=True,
        label="F5-TTS",
        kind="tts",
        summary=(
            "Clones a voice from a few seconds of reference audio. Flow "
            "matching, so it is fast for what it does. English."
        ),
        provider_id="f5tts",
        knobs=(
            VoiceKnob(
                id="nfe_step",
                label="Quality steps",
                minimum=8,
                maximum=48,
                step=1,
                default=32,
                help="More steps sound better and take longer, per sentence.",
            ),
        ),
        probe_module="f5_tts",
        # Olculdu (bu makine): ``import torchcodec`` -> OSError, cunku
        # torchcodec 0.15.0'in libtorchcodec_core4..8.dll'lerinin her biri
        # PAYLASILAN FFmpeg kutuphanelerini ariyor ve sistemde statik bir
        # FFmpeg 9 var. Paket kurulu, motor calismiyor.
        runtime_imports=("torchcodec",),
        runtime_help=(
            "F5-TTS cannot run here: it loads audio through torchcodec, which "
            "needs shared FFmpeg libraries (avcodec/avformat/avutil, version "
            "4-7). This machine has a static FFmpeg build, which ships no "
            "DLLs. Install a shared ('full-shared') FFmpeg build and put its "
            "bin folder on PATH, then reinstall F5-TTS. Until then use "
            "StyleTTS 2 or Chatterbox for voice cloning."
        ),
        sidecar_specs=("f5-tts==1.1.22",),
        sidecar_cuda_index="https://download.pytorch.org/whl/cu126",
        devices=("cpu", "cuda"),
        cuda_probe="torch",
        # Tek yerlesik ses; asil kimlik yuklenen referans kayittan geliyor.
        # Bos birakmak panelde "ses secilemiyor" olarak gorunuyordu -- oysa
        # dogru cevap "tek secenek var, o da bu".
        voices=(("default", "Reference clip - upload one to clone"),),
        size_label="~3 GB",
    ),
    VoiceEntry(
        id="chatterbox",
        # Iki kol da ISTEK BASINA da geciliyor (bkz. ``fool/voice_emotion.py``):
        # model bir cumleyi ``[laughing]`` diye acarsa o cumle icin buradaki
        # deger yerine etiketin degeri kullaniliyor. Yani bu ayar TABAN ton --
        # yardim metni bunu soyluyor, cunku "ayarladigim deger neden hep
        # tutmuyor" tam olarak burada sorulur.
        knobs=(
            VoiceKnob(
                id="exaggeration",
                label="Intensity",
                minimum=0.25,
                maximum=2.0,
                step=0.05,
                default=0.5,
                help=(
                    "How much feeling goes into a line. Higher is more "
                    "dramatic, and also a little faster. This is the baseline; "
                    "a single line can still be delivered differently."
                ),
            ),
            VoiceKnob(
                id="cfg_weight",
                label="Pace",
                minimum=0.2,
                maximum=1.0,
                step=0.05,
                default=0.5,
                help=(
                    "Lower is slower and heavier, higher is tighter and "
                    "quicker. Pair a low value with high intensity for a "
                    "voice that lingers."
                ),
            ),
        ),
        weights_repo="ResembleAI/chatterbox",
        label="Chatterbox",
        kind="tts",
        summary=(
            "The most realistic option, and the best at cloning a voice from "
            "a short clip. Runs Turbo: measured 0.78s per sentence warm."
        ),
        probe_module="chatterbox",
        # ``setuptools<81`` SART: chatterbox -> perth -> ``pkg_resources``,
        # ve o modul setuptools 81'de kaldirildi. ``uv venv`` setuptools'u
        # hic kurmuyor, yani ikisi birlesince perth sessizce yariq yukleniyor
        # ve ``PerthImplicitWatermarker`` None kaliyor -- sentez
        # "TypeError: 'NoneType' object is not callable" ile dusuyor.
        sidecar_specs=("chatterbox-tts==0.1.7", "soundfile==0.14.0", "setuptools==80.10.2"),
        sidecar_cuda_index="https://download.pytorch.org/whl/cu126",
        devices=("cpu", "cuda"),
        # Yerlesik ses bir tane; cesitlilik KLONDAN geliyor (``CLONE_CAPABLE``).
        voices=(("default", "Built-in voice - or clone one from a clip"),),
        size_label="~3 GB",
    ),
    VoiceEntry(
        id="qwen3-tts",
        weights_repo="Qwen/Qwen3-TTS",
        # Olculdu: 9,42 sn/cumle. Sesli sohbet icin kullanilamaz.
        hidden=True,
        label="Qwen3-TTS",
        kind="tts",
        summary=(
            "Alibaba'nin cok dilli modeli: 9 konusmaci, 10 dil (Ingilizce, "
            "Almanca, Fransizca, Ispanyolca, Italyanca, Portekizce, Rusca, "
            "Cince, Japonca, Korece). TURKCE DESTEKLENMIYOR."
        ),
        provider_id="qwen3",
        probe_module="qwen_tts",
        # Ana ortama KURULAMAZ: transformers==4.57.3 huggingface-hub'i
        # 1.27.0 -> 0.36.2'ye dusuruyor ve lazy_deps.py bunun Hindsight'i
        # cokerttigini (#60783) yaziyor. Kendi ortamina kuruluyor.
        sidecar_specs=("qwen-tts==0.1.1",),
        # Modelin ``get_supported_speakers()`` ciktisindan alindi, tahmin degil.
        voices=(
            ("ryan", "Even male"),
            ("serena", "Clear female"),
            ("aiden", "Young male"),
            ("dylan", "Low, calm male"),
            ("eric", "Narration tone"),
            ("vivian", "Warm female"),
            ("ono_anna", "Female, native Japanese"),
            ("sohee", "Female, native Korean"),
            ("uncle_fu", "Mature male, native Chinese"),
        ),
        # PyPI'nin Windows torch tekerlegi CPU-only. Gercek CUDA derlemesi
        # yalnizca PyTorch'un kendi indeksinde; olculdu: CPU'da kisa bir
        # cumle 7.8 saniye surdu.
        sidecar_cuda_index="https://download.pytorch.org/whl/cu126",
        devices=("cpu", "cuda"),
        size_label="~3 GB",
    ),
    VoiceEntry(
        id="whisper-turbo",
        label="Whisper Large-v3 Turbo",
        kind="stt",
        summary=(
            "En iyi yerel konusma tanima. Turkce ve Ingilizce dahil 99 dil, "
            "large-v3'un dogruluguna yakin ama belirgin sekilde hizli."
        ),
        dep_group="stt.faster_whisper",
        probe_module="faster_whisper",
        cuda_probe="ctranslate2",
        model_id="large-v3-turbo",
        warmup=(
            "from faster_whisper import WhisperModel; "
            "WhisperModel('large-v3-turbo', device='cpu', compute_type='int8')"
        ),
        devices=("cpu", "cuda"),
        size_label="~1,6 GB",
        recommended=True,
    ),
    VoiceEntry(
        id="faster-whisper",
        label="Faster-Whisper",
        kind="stt",
        summary=(
            "Local speech recognition. Far above real time on CUDA, and usable "
            "on CPU too."
        ),
        dep_group="stt.faster_whisper",
        probe_module="faster_whisper",
        cuda_probe="ctranslate2",
        #: Kendi AGIRLIGI olmadan "kurulu" gorunuyordu.
        #:
        #: Bu giris ``whisper-turbo`` ile AYNI ``probe_module``u paylasiyor
        #: (ikisi de ``faster_whisper`` paketi). ``model_id`` yokken durum
        #: yalnizca pakete bakiyordu: turbo kurulunca bu satir da "use"
        #: gosteriyor, indirme dugmesi hic cikmiyordu -- kullanicinin
        #: bildirdigi tam olarak bu. Secilince ise ``stt.local.model`` ``base``
        #: oluyor ve ILK CUMLEDE 150 MB sessizce inmeye basliyor; kullanici
        #: yalnizca "cok yavas" goruyor.
        model_id="base",
        #: ``warmup`` kurulumun agirliklari GERCEKTEN indirmesini sagliyor
        #: (bkz. ``_run_warmup``). Olmazsa "Install" yalnizca paketi kurar ve
        #: durum ``base`` inmedigi icin hala "kurulu degil" derdi -- dugme
        #: basiliyor, hicbir sey degismiyor gibi gorunurdu.
        warmup=(
            "from faster_whisper import WhisperModel; "
            "WhisperModel('base', device='cpu', compute_type='int8')"
        ),
        devices=("cpu", "cuda"),
        size_label="~150 MB",
    ),
)


def entry(entry_id: str) -> VoiceEntry | None:
    return next((e for e in CATALOG if e.id == entry_id), None)


# ---------------------------------------------------------------------------
# Durum tespiti
# ---------------------------------------------------------------------------


def _module_available(name: str) -> bool:
    """Modül İTHAL EDİLMEDEN varlığına bakılır.

    Gerçekten ithal etmek ağır modelleri belleğe yükler ve CUDA bağlamı
    açabilir — durum sorgusu bunu yapmamalı; panel her açılışta saniyeler
    sürerdi.
    """
    import importlib.util

    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def voice_dir() -> Path:
    """Ses varlıklarının indiği dizin.

    MAKINE kokunde; kullanicinin orijinal Hermes kurulumuna dokunulmaz.
    Profil evinin ALTINDA DEGIL: indirilen agirliklar ve yuklenen klonlar
    makine varligi, kullanici durumu degil -- profil basina kopyalamak her
    profilin ayni gigabaytlari yeniden indirmesi demekti (bkz.
    ``fool/machine_assets.py``).
    """
    from fool.machine_assets import machine_home

    path = machine_home() / "voices"
    path.mkdir(parents=True, exist_ok=True)
    return path


def asset_present(asset: VoiceAsset) -> bool:
    target = voice_dir() / asset.filename
    # Boyut kontrolü kasıtlı: yarıda kesilmiş bir indirme dosyayı bırakır ve
    # varlık kontrolü onu "inmiş" sayardı. Piper o dosyayı açmaya çalışıp
    # anlaşılmaz bir hata verirdi.
    return target.exists() and target.stat().st_size > 1024


def status(entry_id: str) -> dict[str, Any]:
    e = entry(entry_id)
    if e is None:
        return {"id": entry_id, "installed": False, "error": "bilinmeyen oge"}

    # Isinmasi olan oge icin AGIRLIKLAR da inmis olmali. Yalnizca pakete
    # bakmak "kurulu" derdi ama ilk konusmada model sessizce inmeye baslar ve
    # kullanici sadece "cok yavas" gorur -- panelin tam kacinmasi gereken sey.
    # ``warmup`` KOSULU KALDIRILDI: bir girisin ``model_id``si varsa
    # agirliklari da SORULUYOR. Eskiden ikisi birden gerekiyordu, yani
    # ``warmup``i olmayan bir ``model_id`` sessizce kontrolsuz kaliyordu --
    # ``faster-whisper`` tam olarak o bosluktan "kurulu" gorunuyordu.
    if e.model_id and not _weights_present(e.model_id):
        engine_ok = False
    elif e.weights_repo and not _weights_present(e.weights_repo):
        # Paket kurulu olabilir ama AGIRLIKLAR inmemis. Bunu "kurulu" saymak,
        # kullaniciya indirme dugmesini hic gostermemek demek -- ve motor ilk
        # cumlede gigabaytlarca indirmeye baslar, kullanici yalnizca "cok
        # yavas" gorur.
        engine_ok = False
    elif e.sidecar_specs:
        # Sidecar'li motor ANA ortamda asla gorunmez; orada aramak her zaman
        # "kurulu degil" derdi.
        from fool import sidecar as _sidecar

        engine_ok = _sidecar.is_ready(e.id, e.probe_module)
    else:
        engine_ok = _module_available(e.probe_module) if e.probe_module else True
    assets_ok = all(asset_present(a) for a in e.assets)

    # KURULU ile CALISIYOR ayri sorular. Ikincisini sormadan "installed"
    # demek, kullaniciyi klon yukleyip hicbir sey duymayacagi bir yola
    # sokuyordu -- bkz. ``fool/engine_health.py``.
    engine_error = ""
    if engine_ok and assets_ok:
        from fool import engine_health

        engine_error = engine_health.error_for(e)

    return {
        "id": e.id,
        "provider_id": e.provider_id or e.id,
        "label": e.label,
        "kind": e.kind,
        "summary": e.summary,
        "devices": list(e.devices),
        "size_label": e.size_label,
        "recommended": e.recommended,
        "engine_installed": engine_ok,
        "assets_installed": assets_ok,
        "installed": engine_ok and assets_ok,
        #: Paket yerinde ama motor ice aktarilamiyor. ``installed`` BILEREK
        #: True kaliyor: yeniden kurmak bunu duzeltmiyor, o yuzden panelde
        #: "Install" degil SEBEP gosterilmeli.
        "engine_error": engine_error,
        "usable": engine_ok and assets_ok and not engine_error,
        "cuda_available": _cuda_available() if "cuda" in e.devices else False,
        # Buyuk bir modeli CPU'ya almanin bedelini ONCEDEN soyle.
        "cpu_warning": cpu_warning(e),
    }


def _weights_present(model_id: str) -> bool:
    """HuggingFace onbelleginde model agirliklari var mi?

    faster-whisper agirliklari ``Systran/faster-whisper-<model>`` altinda
    tutuyor. Dizin varligi degil, ICINDE gercek bir dosya olup olmadigi
    kontrol ediliyor: yarida kesilen bir indirme bos dizin birakiyor.
    """
    from pathlib import Path as _Path

    root = _Path.home() / ".cache" / "huggingface" / "hub"
    # ``owner/repo`` verildiyse HF'in onbellek adina cevir; ciplak bir ad
    # verildiyse eski desenler gecerli (faster-whisper boyle cagriliyor).
    if "/" in model_id:
        patterns = ("models--" + model_id.replace("/", "--") + "*",)
    else:
        patterns = (f"models--Systran--faster-whisper-{model_id}", f"models--*{model_id}*")
    for pattern in patterns:
        for candidate in root.glob(pattern):
            if any(f.is_file() and f.stat().st_size > 1_000_000 for f in candidate.rglob("*")):
                return True
    return False


def _nvidia_driver_present() -> bool:
    """NVIDIA SÜRÜCÜSÜ kurulu mu?

    Tek başına hiçbir şey kanıtlamıyor ve asla tek başına kullanılmamalı --
    aşağıdaki motor sondalarının hepsi pahalı bir ithal yapıyor, bu ise
    ucuz bir ön eleme: sürücü yoksa sormaya gerek yok.
    """
    return bool(shutil.which("nvidia-smi"))


def _torch_cuda_available() -> bool:
    """Ana ortamdaki ``torch`` CUDA görebiliyor mu?"""
    try:
        import torch  # noqa: PLC0415

        return bool(torch.cuda.is_available())
    except Exception:
        return False


def _ctranslate2_cuda_devices() -> int:
    """``ctranslate2`` kaç CUDA aygıtı görüyor?

    faster-whisper torch değil ``ctranslate2`` kullanıyor ve ikisinin CUDA
    gereksinimleri AYRI: cuBLAS/cuDNN eksikse torch mutlu, ctranslate2 sıfır
    aygıt görüyor ve motor sessizce CPU'ya düşüyor -- ölçülen fark 0,23 sn
    yerine 15,16 sn.
    """
    import ctranslate2  # noqa: PLC0415

    return int(ctranslate2.get_cuda_device_count())


def _onnxruntime_cuda_available() -> bool:
    """``onnxruntime`` CUDA saglayicisini sunuyor mu?

    Piper onnxruntime kullaniyor. Varsayilan ``onnxruntime`` tekerlegi
    CPU-only; CUDA icin ``onnxruntime-gpu`` gerekiyor. Olculdu (bu makine,
    RTX 4070 Ti SUPER, surucu kurulu):
    ``['AzureExecutionProvider', 'CPUExecutionProvider']`` -- yani CUDA yok.
    Eski kod ``nvidia-smi`` gordugu icin yine de "CUDA" diyordu.
    """
    import onnxruntime  # noqa: PLC0415

    return "CUDAExecutionProvider" in onnxruntime.get_available_providers()


def _cuda_available() -> bool:
    """Bu MAKİNEDE kullanılabilir bir NVIDIA GPU var mı?

    Bu, ``cuda_ready(entry)``den FARKLI bir soru ve ikisini karıştırmak
    panelde "no CUDA on this machine" yazdırdı -- 16 GB'lık bir kartın
    üstünde.

      * ``cuda_available``  -> KUTUDA kart var mı? Panel CUDA düğmesini buna
        göre etkinleştiriyor.
      * ``cuda_ready(e)``   -> ŞU MOTOR onu kullanabiliyor mu? Her motor
        kendi çalışma zamanına soruyor (torch / ctranslate2 / onnxruntime).

    Makine sorusunun cevabı ana ortamdaki torch OLAMAZ: motorlar kendi izole
    ortamlarında koşuyor ve ana ortamda torch hiç kurulu değil. O yüzden
    sürücünün bildirdiği aygıt sayısına bakılıyor -- ithal maliyeti de yok.
    """
    if not _nvidia_driver_present():
        return False
    try:
        from fool.gpu_budget import total_vram_mb

        return bool(total_vram_mb())
    except Exception:
        # Sonda cokerse surucunun varligina guveniliyor: makine sorusunda
        # yanlis "hayir" demek, kullanicinin CUDA dugmesini KAYBETMESI
        # demek -- nitekim tam bu oldu.
        return True


def active_providers() -> dict[str, str]:
    """Su an SECILI olan TTS/STT saglayicilari.

    Panel bunu gostermeden kullanici hangi modelin konustugunu bilemiyordu:
    dort model "kurulu" yaziyor, hangisinin aktif oldugu hicbir yerde yok.
    """
    try:
        from fool_cli.config import load_config

        cfg = load_config() or {}
    except Exception:
        return {"stt": "", "tts": ""}

    tts = str((cfg.get("tts") or {}).get("provider") or "")
    stt_cfg = cfg.get("stt") or {}
    stt = str(stt_cfg.get("provider") or "")
    # Yerel STT'de asil kimlik MODEL: "local" dort farkli whisper boyutu
    # olabiliyor ve panel hangisini gosterecegini bilemez.
    if stt == "local":
        stt = str((stt_cfg.get("local") or {}).get("model") or "local")
    return {"stt": stt, "tts": tts}


def _entry_id_for_provider(provider: str) -> str:
    """Saglayici adindan katalog kimligi (``qwen3`` -> ``qwen3-tts``).

    Motor surecleri KATALOG kimligiyle aniliyor; yapilandirmada ise saglayici
    adi duruyor. Ikisini karistirmak, var olmayan bir motoru durdurmaya
    calismak olurdu.
    """
    key = (provider or "").strip().lower()
    for entry in CATALOG:
        if entry.kind == "tts" and (entry.provider_id or entry.id).lower() == key:
            return entry.id
    return key


def select(entry_id: str) -> dict[str, Any]:
    """Bu ogeyi AKTIF saglayici yap."""
    e = entry(entry_id)
    if e is None:
        raise ValueError(f"bilinmeyen oge: {entry_id}")
    if not status(entry_id).get("installed"):
        raise ValueError(f"{e.label} kurulu degil")

    from fool_cli.config import set_config_value

    if e.kind == "tts":
        set_config_value("tts.provider", e.provider_id or e.id)
    else:
        # Yerel whisper: saglayici "local", asil secim model boyutu.
        set_config_value("stt.provider", "local")
        set_config_value("stt.local.model", e.model_id or "base")
        # Dil OTOMATIK kalmali: sabitlemek baska dilde konusmayi bozuyor.
        set_config_value("stt.local.language", "")

    # ESKISINI HEMEN birak. Kullanicinin istegi birebir buydu: "bir kategoride
    # digeri secildiginde oncekiler tamamen unload edilmeli".
    #
    # Bosta-bosaltmayi beklemek, o bes dakika boyunca IKI modelluk bellek
    # tutmak demek -- ve ikisi ayni karti paylasiyor.
    return {"ok": True, "active": active_providers(), "unloaded": _drop_unselected(e.kind)}


def _drop_unselected(kind: Kind) -> dict[str, list[str]]:
    """Bu kategoride SECILI olmayan her seyi birak.

    Yalnizca DEGISEN kategori: dil modeli kurali ``lms ps`` alt surecini
    calistiriyor ve kullanici bir ses motoru secip cevabi bekliyor.

    Hata YUTULUYOR: bosaltma yapilamadiysa bosta-bosaltma zaten yakalayacak;
    kullanicinin secimini bir temizlik ugruna dusurmek oransiz olurdu.
    """
    try:
        from fool import residency

        return residency.enforce_single(kinds=(kind,)).get("unloaded", {})
    except Exception as exc:  # pragma: no cover
        import logging

        logging.getLogger(__name__).debug("onceki model birakilamadi: %s", exc)
        return {}


def device_key(e: VoiceEntry) -> str:
    """Bu ogenin cihaz ayarinin yapilandirmadaki yeri."""
    if e.kind == "stt":
        return "stt.local.device"
    return f"tts.{e.provider_id or e.id}.device"


def current_device(e: VoiceEntry) -> str:
    """Secili cihaz: ``auto`` | ``cpu`` | ``cuda``."""
    try:
        from fool_cli.config import load_config

        cfg = load_config() or {}
    except Exception:
        return "auto"

    node: Any = cfg
    for part in device_key(e).split("."):
        node = (node or {}).get(part) if isinstance(node, dict) else None
    value = str(node or "auto").strip().lower()
    return value if value in ("auto", "cpu", "cuda") else "auto"


def _forget_cuda_probe(entry_id: str) -> None:
    """Bu motorun saklanan sonda cevaplarini birak (sessizce).

    Saglik sondasi da burada: yeni bir kurulum eksik bir DLL'i getirmis
    olabilir ve panelin "calismiyor" demeye devam etmesi, kullanicinin
    duzelttigi seyi gormemesi olurdu.
    """
    try:
        from fool import cuda_probe_cache, engine_health

        cuda_probe_cache.invalidate(entry_id)
        engine_health.invalidate(entry_id)
    except Exception:
        # Onbellek gecersizlestirilemedi: en kotu ihtimalle parmak izi
        # degisene kadar eski cevap gorunur. Kurulumu bunun icin
        # basarisiz saymak oransiz olurdu.
        pass


def set_device(entry_id: str, device: str) -> dict[str, Any]:
    """Ogenin CALISMA cihazini ayarla.

    Kurulum sirasindaki secimden AYRI: kurulum hangi paketin inecegini
    belirler, bu ise modelin her calismada nerede kosacagini. Ikisini tek
    dugmeye baglamak, kurduktan sonra cihaz degistirmeyi imkansiz kiliyordu.
    """
    e = entry(entry_id)
    if e is None:
        raise ValueError(f"bilinmeyen oge: {entry_id}")
    if device not in ("auto", "cpu", "cuda"):
        raise ValueError(f"gecersiz aygit: {device}")

    from fool_cli.config import set_config_value

    set_config_value(device_key(e), device)

    # CUDA secildi ama ortam onu calistiramiyor: yalnizca yapilandirmaya
    # yazmak sessiz bir yalan olurdu. Gercek CUDA derlemesi kuruluyor.
    needs_runtime = device == "cuda" and not cuda_ready(e)

    return {"ok": True, "device": device, "needs_cuda_runtime": needs_runtime}


def available_voices(e: VoiceEntry) -> list[dict[str, str]]:
    """Bu motor icin SECILEBILIR sesler.

    Piper ozel: sesleri ayri ayri inen ``.onnx`` dosyalari, yani liste
    DISKTEN uretiliyor. Inmemis bir sesi sunmak secildiginde calisma aninda
    patlardi -- panelin tam kacinmasi gereken sey.
    """
    if e.id == "piper":
        # KATALOG + DİSK, yalnızca disk değil.
        #
        # Eski hâl listeyi SADECE diskten üretiyordu ve gerekçesi şuydu:
        # "inmemiş bir sesi sunmak seçildiğinde çalışma anında patlardı."
        # O gerekçe Piper için DOĞRU DEĞİL -- sağlayıcı inmemiş bir sesi ilk
        # kullanımda kendisi indiriyor
        # (``tools/tts_tool.py::_resolve_piper_voice_path``, Case 3).
        #
        # Ölçülen sonuç kısır bir döngüydü: Türkçe ses inmediği için listede
        # görünmüyor, listede görünmediği için seçilemiyor, seçilemediği için
        # inmiyor. Piper CPU'da gerçek zamandan hızlı çalışan tek seçenekti ve
        # Türkçe konuşmak isteyen kullanıcı ona hiç ulaşamıyordu.
        #
        # Etiket İNMİŞ Mİ bilgisini taşıyor: kullanıcı 63 MB'lık bir indirmeye
        # girdiğini seçmeden önce bilmeli.
        try:
            on_disk = {f.stem for f in voice_dir().glob("*.onnx")}
        except OSError:
            on_disk = set()

        rows = [
            {
                "id": vid,
                "label": desc if vid in on_disk else f"{desc} — indirilecek",
            }
            for vid, desc in e.voices
        ]

        known = {vid for vid, _ in e.voices}
        rows.extend(
            {"id": name, "label": name}
            for name in sorted(on_disk - known)
        )

        return rows
    return [{"id": vid, "label": desc} for vid, desc in e.voices]


def current_voice(e: VoiceEntry) -> str:
    try:
        from fool_cli.config import load_config

        cfg = load_config() or {}
    except Exception:
        return ""
    node = ((cfg.get("tts") or {}).get(e.provider_id or e.id) or {})
    return str(node.get("voice") or "")


def set_voice(entry_id: str, voice: str) -> dict[str, Any]:
    """Motorun konusacagi sesi ayarla."""
    e = entry(entry_id)
    if e is None:
        raise ValueError(f"bilinmeyen oge: {entry_id}")

    valid = {v["id"] for v in available_voices(e)}
    if valid and voice not in valid:
        raise ValueError(f"{e.label} icin bilinmeyen ses: {voice}")

    from fool_cli.config import set_config_value

    set_config_value(f"tts.{e.provider_id or e.id}.voice", voice)
    return {"ok": True, "voice": voice}


#: Bu boyutun ustundeki modeller CPU'da kullanilamaz derecede yavas.
#:
#: Olculdu (bu makine): Chatterbox CUDA'da 2,10 sn -- CPU'da difuzyon
#: adimlari dakikalara cikiyor. Kokoro (~1,3 GB) CPU'da hala kullanilabilir,
#: Chatterbox (~3 GB) ve Kyutai (~3,5 GB) degil. Esik oraya konuldu.
CPU_IMPRACTICAL_GB = 2.0


def _size_gb(e: VoiceEntry) -> float:
    """Katalog etiketinden kaba boyut. Okunamazsa 0 -- uyari cikmaz."""
    label = (e.size_label or "").lower().replace(",", ".")
    try:
        number = float("".join(c for c in label if c.isdigit() or c == ".").strip("."))
    except ValueError:
        return 0.0
    return number if "gb" in label else number / 1024.0


def cpu_warning(e: VoiceEntry) -> str:
    """CPU'da calistirmak pratik mi? Degilse kullaniciya soylenecek cumle.

    Panel "CPU" dugmesini gizlemiyor -- kullanicinin makinesinde ne olacagina
    o karar verir. Ama sessizce dakikalarca bekletmek yerine ONCEDEN
    soylemek gerekiyor: bir kez tiklayip 4 dakika bekleyen kullanici
    uygulamanin dondugunu saniyor.
    """
    if "cuda" not in e.devices or _size_gb(e) < CPU_IMPRACTICAL_GB:
        return ""
    return (
        f"{e.label} is {e.size_label} — on CPU a single sentence can take "
        "minutes. CUDA is strongly recommended."
    )


def cuda_ready(e: VoiceEntry) -> bool:
    """Bu motor GERCEKTEN CUDA calistirabiliyor mu?

    Kart ve surucu yetmiyor; soru her motorun KENDI calisma zamanina
    soruluyor, cunku uc ayri yoldan sessizce CPU'ya dusulebiliyor:

    * **Sidecar motorlari** (kokoro, chatterbox, qwen3-tts): PyPI'dan gelen
      torch Windows'ta CPU-only derlemedir. Kart da surucu de yerinde, motor
      yine CPU'da -- Chatterbox dakikalarca tek kelime uretmiyor.
    * **faster-whisper**: torch degil ``ctranslate2`` kullaniyor. cuBLAS ya da
      cuDNN eksikse ctranslate2 sifir aygit goruyor ve sessizce CPU'ya
      dusuyor. Olculdu: 0,23 sn yerine 15,16 sn.
    * **Ana ortamdaki digerleri**: torch'un kendisi soruluyor.

    Sonda cokerse cevap ``False``. "Bilmiyorum"u "evet" saymak tam da bu
    hatanin ilk halini uretmisti.
    """
    if e.sidecar_specs:
        from fool import cuda_probe_cache, sidecar as _sidecar

        def _probe() -> bool:
            try:
                return bool(_sidecar.has_cuda_torch(e.id))
            except Exception:
                return False

        # ONBELLEKLI: sonda izole bir yorumlayicida ``import torch`` demek ve
        # motor basina 4-5 sn suruyor. Katalog bunu her ogede yapinca ayarlarin
        # ses bolumu 15-20 sn bos duruyordu. Onbellek torch dizininin parmak
        # izine bagli -- derleme degisince kendiliginden gecersiz oluyor.
        return cuda_probe_cache.cached(e.id, _probe)

    # Surucu on elemesi BILEREK yok: her sondanin kendi cevabi zaten kesin ve
    # surucusuz bir makinede olumsuz doner. Ustune bir ``nvidia-smi`` kontrolu
    # koymak, PATH'inde o ikili olmayan ama CUDA'si calisan kurulumlarda dogru
    # cevabi YANLISA cevirirdi. Modul kurulu degilse motor da kurulu degildir;
    # ``False`` dogru cevap.
    try:
        if e.cuda_probe == "ctranslate2":
            return _ctranslate2_cuda_devices() > 0
        if e.cuda_probe == "onnxruntime":
            return _onnxruntime_cuda_available()
        return _torch_cuda_available()
    except Exception:
        return False


def install_cuda_runtime(entry_id: str) -> dict[str, Any]:
    """Sidecar'in torch'unu CUDA derlemesiyle degistir.

    Surum SABITLENMIYOR: her motorun kendi torch pini var (chatterbox 2.6.0,
    kokoro 2.13.0) ve ustune baska bir surum yazmak motoru bozar. Kurulu surum
    okunup AYNI surumun CUDA derlemesi isteniyor.
    """
    e = entry(entry_id)
    if e is None or not e.sidecar_specs:
        raise ValueError(f"{entry_id}: izole ortami yok")
    if not e.sidecar_cuda_index:
        raise ValueError(f"{e.label}: CUDA indeksi tanimli degil")

    from fool import sidecar as _sidecar

    version = _sidecar.installed_version(e.id, "torch")
    if not version:
        raise ValueError(f"{e.label}: torch kurulu degil")

    base = version.split("+")[0]

    # YEREL SURUM ETIKETI sart: ``torch==2.13.0`` kurulu ``2.13.0+cpu``i
    # KARSILIYOR sayiliyor ve uv hicbir sey yapmadan cikiyor (olculdu: 2 sn,
    # cuda hala False). CUDA derlemesi ancak ``+cu126`` ile isteniyor.
    tag = e.sidecar_cuda_index.rstrip("/").rsplit("/", 1)[-1]
    _sidecar.pip_install(
        e.id, (f"torch=={base}+{tag}",), index_url=e.sidecar_cuda_index, timeout=2400
    )
    # torch DEGISTI: saklanan cevap kesinlikle eskidi.
    _forget_cuda_probe(e.id)

    return {"ok": True, "cuda_ready": cuda_ready(e)}


# ---------------------------------------------------------------------------
# Ses klonlari
# ---------------------------------------------------------------------------


def clone_dir() -> Path:
    """Kullanicinin surukleyip biraktigi referans kayitlari."""
    path = voice_dir() / "clones"
    path.mkdir(parents=True, exist_ok=True)
    return path


#: Klonlamayi DESTEKLEYEN motorlar. Digerleri sabit ses kumesiyle calisiyor ve
#: onlara referans kayit vermek sessizce yok sayilirdi -- kullanici sesini
#: yukleyip hicbir sey degismedigini gorurdu.
#:
#: Ucu de zaten sifir-atis klonluyordu (egitim yok, tek referans kayit
#: yetiyor) ama yalnizca chatterbox arayuzden erisilebilirdi -- styletts2 ve
#: f5-tts'in kendi eklentileri ``reference`` kwarg'ini zaten okuyordu, panel
#: hic yol vermiyordu. Kullanici bunu "her ses modeli icin klonlamayi
#: arayuzden yapalim" diye istedi.
#: Cumle basina bu surenin ustundeki motor panelde GIZLENIR (bkz.
#: ``VoiceEntry.hidden``). Esik olculmus degerlerin arasina konuldu:
#: styletts2 556 ms ile rahat altinda, kyutai 2517 ms ile ustunde.
SLOW_ENGINE_MS: Final[int] = 2_000

CLONE_CAPABLE: Final[frozenset[str]] = frozenset({"chatterbox", "styletts2", "f5tts"})

#: Her motorun REFERANS DOSYASINI okudugu yapilandirma anahtari -- AYNI degil.
#: Chatterbox'in kendi eklentisi ``voice_sample`` diyor (Resemble AI'nin
#: orijinal API'siyle uyumlu kalmak icin), styletts2 ve f5-tts ``reference``
#: (kendi API'lerinin adi). Tek bir sabit anahtar kullanmak SESSIZCE yanlis
#: alana yazardi -- motor referansi hic gormez, kullanici yukledigini
#: duymaya devam ederdi.
CLONE_CONFIG_KEY: Final[dict[str, str]] = {
    "chatterbox": "voice_sample",
    "styletts2": "reference",
    "f5tts": "reference",
}

#: Kabul edilen bicimler. Uc motor da 5-10 saniyelik temiz bir kayitla calisiyor.
CLONE_SUFFIXES: Final[tuple[str, ...]] = (".wav", ".mp3", ".flac", ".m4a", ".ogg")

#: Panelde "nasil calisir" dugmesinin gosterdigi kisa aciklama. Motor basina
#: farkli: f5-tts kaydin METNINI de istiyor gibi gorunse de BOS birakilirsa
#: kendi ic Whisper'i ile otomatik cikariyor -- kullaniciya bunu soylemezsek
#: gereksiz bir alan bekler.
CLONE_HELP: Final[dict[str, str]] = {
    "chatterbox": (
        "Drop 5-10 seconds of clean, single-speaker speech (no music, no "
        "background noise). Chatterbox clones the voice instantly — no "
        "training step, no waiting."
    ),
    "styletts2": (
        "Drop 5-10 seconds of clean speech. StyleTTS 2 borrows the clip's "
        "tone and pacing on top of its own voice — closer to a style "
        "transfer than a perfect copy."
    ),
    "f5tts": (
        "Drop 5-10 seconds of clean speech. F5-TTS transcribes the clip "
        "itself before cloning, so you don't need to type out what's said "
        "in it."
    ),
}


def list_clones() -> list[dict[str, Any]]:
    """Yuklenmis referans kayitlari."""
    try:
        entries = sorted(clone_dir().iterdir())
    except OSError:
        return []

    out: list[dict[str, Any]] = []
    for f in entries:
        if f.is_file() and f.suffix.lower() in CLONE_SUFFIXES:
            out.append({"id": f.name, "label": f.stem, "path": str(f), "bytes": f.stat().st_size})
    return out


def _safe_clone_name(name: str, suffix: str) -> str:
    """Dosya adini guvenli hale getir.

    Kullanicidan gelen ad dogrudan yola yazilirsa ``../`` ile dizin disina
    cikilabilir. Yalnizca sade karakterler birakiliyor.
    """
    import re

    stem = re.sub(r"[^A-Za-z0-9 _-]", "", pathlib_stem(name)).strip() or "ses"
    return f"{stem[:48]}{suffix}"


def pathlib_stem(name: str) -> str:
    return Path(name).stem


def save_clone(filename: str, data: bytes) -> dict[str, Any]:
    """Referans kaydi diske yaz."""
    suffix = Path(filename).suffix.lower()
    if suffix not in CLONE_SUFFIXES:
        raise ValueError(f"desteklenmeyen bicim: {suffix or '?'}")
    # 50 MB: 5-10 saniyelik bir kayit birkac yuz KB. Bunun ustu ya yanlis
    # dosya ya da kotu niyet.
    if len(data) > 50 * 1024 * 1024:
        raise ValueError("dosya cok buyuk (en fazla 50 MB)")
    if len(data) < 1024:
        raise ValueError("dosya cok kucuk ya da bos")

    target = clone_dir() / _safe_clone_name(filename, suffix)
    target.write_bytes(data)
    return {"ok": True, "id": target.name, "label": target.stem, "path": str(target)}


def delete_clone(clone_id: str) -> dict[str, Any]:
    # Ad yeniden guvenlestiriliyor: gelen deger dogrudan yola yazilmamali.
    target = clone_dir() / Path(clone_id).name
    if target.is_file():
        target.unlink()
    return {"ok": True}


def set_clone(entry_id: str, clone_id: str) -> dict[str, Any]:
    """Bir motorun klon referansini ayarla ("" = kapali)."""
    e = entry(entry_id)
    if e is None:
        raise ValueError(f"bilinmeyen oge: {entry_id}")
    provider = e.provider_id or e.id
    if provider not in CLONE_CAPABLE:
        raise ValueError(f"{e.label} ses klonlamayi desteklemiyor")

    # Motor basina FARKLI anahtar -- bkz. CLONE_CONFIG_KEY. Yanlis anahtara
    # yazmak motorun referansi hic gormemesi demek, ama HATA da vermiyor:
    # kullanici yukledigini duymaya devam eder, sebebini asla ogrenemez.
    key = CLONE_CONFIG_KEY.get(provider, "voice_sample")

    from fool_cli.config import set_config_value

    if not clone_id:
        set_config_value(f"tts.{provider}.{key}", "")
        return {"ok": True, "clone": ""}

    target = clone_dir() / Path(clone_id).name
    if not target.is_file():
        raise ValueError(f"klon bulunamadi: {clone_id}")

    set_config_value(f"tts.{provider}.{key}", str(target))
    return {"ok": True, "clone": target.name}


def current_clone(e: VoiceEntry) -> str:
    try:
        from fool_cli.config import load_config

        cfg = load_config() or {}
    except Exception:
        return ""
    provider = e.provider_id or e.id
    key = CLONE_CONFIG_KEY.get(provider, "voice_sample")
    node = ((cfg.get("tts") or {}).get(provider) or {})
    return Path(str(node.get(key) or "")).name


def _catalog_row(e: VoiceEntry, active: dict[str, str]) -> dict[str, Any]:
    row = status(e.id)
    key = e.model_id if (e.kind == "stt" and e.model_id) else (e.provider_id or e.id)
    row["active"] = active.get(e.kind, "") == key
    row["device"] = current_device(e)
    # GERCEK yetenek: yapilandirmada "cuda" yazmasi CUDA calistigi anlamina
    # gelmiyor. Sidecar'in torch'u CPU derlemesiyse motor sessizce CPU'ya
    # dusuyor ve kullanici yalnizca "cok yavas" goruyor.
    row["cuda_ready"] = cuda_ready(e)
    # Bozuk bir motoru "klonlanabilir" gostermek, kullanicinin ses kaydi
    # yukleyip hicbir sey duymamasi demek. §6.2'nin somut zarari buydu.
    row["clone_capable"] = (e.provider_id or e.id) in CLONE_CAPABLE and row.get("usable", True)
    row["clone"] = current_clone(e) if row["clone_capable"] else ""
    row["clone_help"] = CLONE_HELP.get(e.provider_id or e.id, "") if row["clone_capable"] else ""
    row["voices"] = available_voices(e) if e.kind == "tts" else []
    row["voice"] = current_voice(e) if e.kind == "tts" else ""
    row["knobs"] = knob_status(e)
    return row


def knob_status(e: VoiceEntry) -> list[dict[str, Any]]:
    """Motorun kollari + O ANKI degerleri.

    Deger yapilandirmada YOKSA katalogdaki varsayilan doniyor -- yani panel
    hep motorun gercekten kullanacagi sayiyi gosteriyor. Bos gostermek,
    kullaniciya "ayarli degil" dedirtirdi; oysa motorun bir varsayilani var ve
    kaydiraci oynatmak o degeri hicbir yerde gormeden degistirmek olurdu.
    """
    if not e.knobs:
        return []

    provider = e.provider_id or e.id

    try:
        from fool_cli.config import load_config_readonly

        node = ((load_config_readonly().get("tts") or {}).get(provider) or {})
    except Exception:  # noqa: BLE001
        node = {}

    rows: list[dict[str, Any]] = []

    for knob in e.knobs:
        raw = node.get(knob.id) if isinstance(node, dict) else None
        value = knob.default

        if isinstance(raw, (int, float)) and not isinstance(raw, bool):
            value = float(raw)
        elif isinstance(raw, str) and raw.strip():
            try:
                value = float(raw)
            except ValueError:
                value = knob.default

        rows.append(
            {
                "id": knob.id,
                "label": knob.label,
                "min": knob.minimum,
                "max": knob.maximum,
                "step": knob.step,
                "default": knob.default,
                "help": knob.help,
                "value": round(_clamp_knob(knob, value), 4),
            }
        )

    return rows


def _clamp_knob(knob: VoiceKnob, value: float) -> float:
    return max(knob.minimum, min(knob.maximum, value))


def set_knob(entry_id: str, knob_id: str, value: float) -> dict[str, Any]:
    """Bir kolu ayarla.

    Deger KIRPILIYOR, reddedilmiyor: aralik disi bir sayi cogu motorda
    sessizce bozuk ses veriyor (Chatterbox'ta ``cfg_weight=0`` konusmayi
    tamamen durduruyor) ve panelin kaydiraci zaten araligi biliyor. Buraya
    aralik disi bir deger yalnizca elle bir cagriyla gelebilir.
    """
    e = entry(entry_id)

    if e is None:
        raise ValueError(f"bilinmeyen oge: {entry_id}")

    knob = next((k for k in e.knobs if k.id == knob_id), None)

    if knob is None:
        raise ValueError(f"{e.label} icin bilinmeyen ayar: {knob_id}")

    clamped = _clamp_knob(knob, float(value))
    # Tamsayi kollar (adim sayilari) yapilandirmaya TAMSAYI yaziliyor: motor
    # ``range(5.0)`` ile patlar.
    stored: float | int = int(round(clamped)) if float(knob.step).is_integer() else round(clamped, 4)

    from fool_cli.config import set_config_value

    set_config_value(f"tts.{e.provider_id or e.id}.{knob.id}", stored)

    return {"ok": True, "id": knob.id, "value": stored}


def visible_catalog() -> list[VoiceEntry]:
    """Panelde gosterilecek ogeler.

    Gizli bir motor SECILIYSE yine gosteriliyor: aksi halde kullanici
    ayarlarda hicbir sey secili gormez ve sesin nereden geldigini anlayamaz.
    """
    active = active_providers()
    return [
        e
        for e in CATALOG
        if not e.hidden
        or active.get(e.kind, "") == (e.model_id if (e.kind == "stt" and e.model_id) else (e.provider_id or e.id))
    ]


def catalog_status() -> list[dict[str, Any]]:
    """Panelin gordugu tam liste.

    Satirlar PARALEL kuruluyor. Maliyetin neredeyse tamami alt surec
    beklemesi: her sidecar motorunun CUDA sondasi izole bir yorumlayicida
    ``import torch`` yapiyor ve 4-5 sn suruyor. Sirayla kosunca dokuz oge
    27,6 saniye ediyordu -- kullanici bunu "ayarlardaki ses kismi gec
    yukleniyor" diye bildirdi.

    Bekleme GIL'i birakiyor, yani is parcaciklari burada gercekten paralel.
    Onbellekle birlikte (bkz. ``fool/cuda_probe_cache.py``) ilk acilis
    ~6 sn'ye, sonrakiler 1 sn altina iniyor.

    Sira KORUNUYOR: ``map`` girdi sirasiyla donuyor ve panelin listesi her
    acilista yer degistirseydi kullanici aradigini bulamazdi.
    """
    from concurrent.futures import ThreadPoolExecutor

    active = active_providers()
    # Yavas motorlar panelde YOK (bkz. ``VoiceEntry.hidden``). Kayitlari
    # duruyor: kurulu bir motoru katalogdan silmek, kullanicinin diskindeki
    # gigabaytlari gorunmez yapardi.
    entries = visible_catalog()

    if len(entries) < 2:
        return [_catalog_row(e, active) for e in entries]

    with ThreadPoolExecutor(max_workers=len(entries), thread_name_prefix="fool-catalog") as pool:
        return list(pool.map(lambda e: _catalog_row(e, active), entries))


# ---------------------------------------------------------------------------
# Kurulum işleri
# ---------------------------------------------------------------------------


@dataclass
class Job:
    """Tek bir kurulum işi ve canlı ilerlemesi."""

    id: str
    entry_id: str
    device: Device
    state: Literal["running", "done", "failed", "cancelled"] = "running"
    #: 0..100. Model dosyası indirilirken GERÇEK baytlardan hesaplanır; pip
    #: aşamasında adım sayısından gelir (bkz. modül başlığı).
    percent: float = 0.0
    stage: str = "starting"
    detail: str = ""
    error: str = ""
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    _cancel: threading.Event = field(default_factory=threading.Event)

    def snapshot(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "entry_id": self.entry_id,
            "device": self.device,
            "state": self.state,
            "percent": round(self.percent, 1),
            "stage": self.stage,
            "detail": self.detail,
            "error": self.error,
            "elapsed": round((self.finished_at or time.time()) - self.started_at, 1),
        }


_JOBS: dict[str, Job] = {}
_JOBS_LOCK = threading.Lock()
#: Aynı öğe için ikinci bir işe izin verilmez: iki pip aynı hedefe aynı anda
#: yazarsa ortam yarım kalmış bir kurulumla bozulur.
_ACTIVE_BY_ENTRY: dict[str, str] = {}


def get_job(job_id: str) -> Job | None:
    with _JOBS_LOCK:
        return _JOBS.get(job_id)


def active_job_for(entry_id: str) -> Job | None:
    with _JOBS_LOCK:
        job_id = _ACTIVE_BY_ENTRY.get(entry_id)
        return _JOBS.get(job_id) if job_id else None


def cancel_job(job_id: str) -> bool:
    job = get_job(job_id)
    if job is None or job.state != "running":
        return False
    job._cancel.set()
    return True


def _download(asset: VoiceAsset, job: Job, base: float, span: float) -> None:
    """Tek varlığı indir; yüzdeyi GERÇEK baytlardan güncelle."""
    target = voice_dir() / asset.filename
    if asset_present(asset):
        job.percent = base + span
        return

    # Geçici dosyaya indirilip sonra taşınıyor: yarıda kesilen bir indirme
    # hedef adı asla almamalı, yoksa ``asset_present`` onu geçerli sanar.
    tmp = target.with_suffix(target.suffix + ".part")
    request = urllib.request.Request(asset.url, headers={"User-Agent": "TheFool"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            declared = response.headers.get("Content-Length")
            total = int(declared) if declared else asset.approx_bytes
            read = 0
            with tmp.open("wb") as fh:
                while True:
                    if job._cancel.is_set():
                        raise InterruptedError("cancelled")
                    chunk = response.read(256 * 1024)
                    if not chunk:
                        break
                    fh.write(chunk)
                    read += len(chunk)
                    if total > 0:
                        job.percent = base + span * min(read / total, 1.0)
                        job.detail = f"{read // 1_000_000} / {total // 1_000_000} MB"
                    else:
                        job.detail = f"{read // 1_000_000} MB"
        tmp.replace(target)
    except InterruptedError:
        tmp.unlink(missing_ok=True)
        raise
    except (urllib.error.URLError, OSError) as exc:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"could not download {asset.filename}: {exc}") from exc
    finally:
        tmp.unlink(missing_ok=True)

    job.percent = base + span


#: pip'in çıktısındaki aşama işaretleri. Yüzde uydurmak yerine kullanıcıya
#: gerçekten ne olduğu söyleniyor.
_PIP_STAGES: Final[tuple[tuple[re.Pattern[str], str], ...]] = (
    (re.compile(r"Collecting|Resolving", re.I), "resolving packages"),
    (re.compile(r"Downloading", re.I), "downloading"),
    (re.compile(r"Building|Preparing", re.I), "preparing"),
    (re.compile(r"Installing", re.I), "installing"),
)


def _weights_warmup(e: VoiceEntry) -> str:
    """``weights_repo`` icin indirme parcasi ("" = gerek yok).

    ``huggingface_hub`` ANA ortamda (1.27.0) ve onbellek paylasilan, yani
    sidecar da ayni dosyalari goruyor. Motorun kendi kutuphanesini ithal
    etmeye gerek yok -- o sidecar'da ve bu kod ana yorumlayicida kosuyor.

    Neden gerekli: kurulum yalnizca ``warmup`` tanimliysa agirlik indiriyordu
    ve hicbir TTS motorunun ``warmup``i yok. Yani paket kuruluyor, agirliklar
    inmiyor; panel "kurulu degil" demeye devam ediyor ve kullanici ayni
    dugmeye tekrar tekrar basiyor.
    """
    if e.warmup or not e.weights_repo:
        return e.warmup

    return (
        "from huggingface_hub import snapshot_download\n"
        f"snapshot_download({e.weights_repo!r})\n"
    )


def _run_warmup(e: VoiceEntry) -> None:
    """Model agirliklarini indir (ana yorumlayicida, alt surec olarak).

    Alt surec kasitli: indirme sirasinda ithal edilen agir moduller ana
    surecte kalmasin ve bir cokme paneli dusurmesin.
    """
    import subprocess
    import sys

    completed = subprocess.run(
        [sys.executable, "-c", _weights_warmup(e)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=1800,
        check=False,
    )
    if completed.returncode != 0:
        tail = (completed.stderr or completed.stdout or "").strip()
        last = tail.splitlines()[-1] if tail else "bilinmeyen hata"
        raise RuntimeError(f"model agirliklari indirilemedi: {last}")


def _install_sidecar(e: VoiceEntry, job: Job, base: float, span: float, device: Device = "cpu") -> None:
    """Motoru KENDI izole ortamina kur.

    Ilerleme yine uydurulmuyor: uv'nin cikti satirlari ``job.detail``e
    aktariliyor, yuzde ise ``_creep`` gibi asamayi asmayan bir tahmin.
    Kullanici en azindan hangi paketin indigini goruyor.
    """
    from fool import sidecar as _sidecar

    job.stage = "installing engine (isolated)"

    stop = threading.Event()

    def _creep() -> None:
        crept = 0.0
        while not stop.wait(0.5):
            crept = min(crept + span * 0.004, span * 0.9)
            job.percent = base + crept

    def _line(text: str) -> None:
        # uv satirlari uzun olabiliyor; arayuzde tek satira sigsin.
        job.detail = text[:90]

    ticker = threading.Thread(target=_creep, daemon=True)
    ticker.start()
    try:
        _sidecar.create(
            _sidecar.SidecarSpec(
                name=e.id,
                specs=e.sidecar_specs,
                probe_module=e.probe_module or "",
                cuda_specs=e.sidecar_cuda_specs,
                cuda_index_url=e.sidecar_cuda_index,
                extra_wheels=e.sidecar_wheels,
            ),
            on_output=_line,
            cuda=device == "cuda",
        )
    finally:
        stop.set()

    job.percent = base + span
    job.detail = ""


def _install_engine(e: VoiceEntry, device: Device, job: Job, base: float, span: float) -> None:
    if e.sidecar_specs:
        _install_sidecar(e, job, base, span, device)
        return

    groups = [g for g in (e.dep_group, e.cuda_group if device == "cuda" else None) if g]
    # Sessiz basari yasak. Kurulacak paket yoksa is "tamamlandi" demeden
    # once durur: aksi halde kullanici dugmeye basar, cubuk %100'e gider ve
    # oge hala kurulmamis kalir -- hicbir hata da gorunmez.
    if not groups:
        raise RuntimeError(f"{e.label} icin kurulabilir paket tanimli degil")

    from tools.lazy_deps import LAZY_DEPS, install_specs

    specs: list[str] = []
    for group in groups:
        specs.extend(LAZY_DEPS.get(group, ()))
    if not specs:
        raise RuntimeError(f"{e.label} icin paket listesi bos: {groups}")

    job.stage = "installing engine"
    job.detail = ", ".join(specs)

    # pip senkron çalışıyor ve ilerleme yayınlamıyor. Çubuğu donuk bırakmamak
    # için ayrı bir iş parçacığı yavaşça ilerletiyor; bu yüzde bir TAHMİN ve
    # asla span'in sonuna varmıyor — bittiğinde gerçek değere sıçrar.
    stop = threading.Event()

    def _creep() -> None:
        crept = 0.0
        while not stop.wait(0.5):
            crept = min(crept + span * 0.01, span * 0.9)
            job.percent = base + crept

    ticker = threading.Thread(target=_creep, daemon=True)
    ticker.start()
    try:
        outcome = install_specs(specs, timeout=900)
    finally:
        stop.set()

    if getattr(outcome, "blocked", False):
        raise RuntimeError(getattr(outcome, "reason", "install blocked"))
    if not getattr(outcome, "ok", False):
        tail = (getattr(outcome, "stderr", "") or getattr(outcome, "stdout", "") or "").strip()
        last = tail.splitlines()[-1] if tail else "unknown error"
        raise RuntimeError(f"pip failed: {last}")

    job.percent = base + span


def _run(job: Job, e: VoiceEntry) -> None:
    try:
        # Ağırlık dağılımı işin gerçek maliyetini yansıtıyor: motor paketleri
        # model dosyalarından belirgin biçimde büyük.
        engine_span = 70.0 if (e.assets or e.weights_repo) else 100.0
        _install_engine(e, job.device, job, 0.0, engine_span)

        if e.warmup or e.weights_repo:
            job.stage = "downloading model weights"
            job.detail = e.model_id
            _run_warmup(e)

        if e.assets:
            job.stage = "downloading voice model"
            remaining = 100.0 - engine_span
            each = remaining / len(e.assets)
            for i, asset in enumerate(e.assets):
                if job._cancel.is_set():
                    raise InterruptedError("cancelled")
                _download(asset, job, engine_span + i * each, each)

        job.percent = 100.0
        job.stage = "done"
        job.detail = ""
        job.state = "done"
        # Kurulum torch'u degistirmis olabilir: CUDA sondasinin saklanan
        # cevabini birak. Parmak izi zaten degisiyor ama dosya sistemi zaman
        # damgasi cozunurlugu dusuk olabilir ve hemen sorulan soru eski
        # cevabi gorebilirdi.
        _forget_cuda_probe(e.id)
    except InterruptedError:
        job.state = "cancelled"
        job.stage = "cancelled"
    except Exception as exc:  # noqa: BLE001 - hata kullanıcıya gösterilecek
        job.state = "failed"
        job.stage = "failed"
        job.error = str(exc)
    finally:
        job.finished_at = time.time()
        with _JOBS_LOCK:
            if _ACTIVE_BY_ENTRY.get(e.id) == job.id:
                _ACTIVE_BY_ENTRY.pop(e.id, None)


def _install_stt_cuda(job: Job) -> None:
    """Ana ortama CTranslate2'nin CUDA kutuphanelerini kur.

    STT sidecar'da DEGIL, ana ortamda kosuyor; o yuzden torch degil
    ``nvidia-cublas``/``nvidia-cudnn`` gerekiyor. Bunlar olmadan
    faster-whisper ``device="cuda"`` istegini "cublas64_12.dll not found" ile
    reddediyor ve SESSIZCE CPU'ya dusuyor -- olculdu: 15,16 sn vs 0,23 sn.
    """
    from tools.lazy_deps import LAZY_DEPS, install_specs

    specs = list(LAZY_DEPS.get("stt.cuda", ()))
    if not specs:
        raise RuntimeError("stt.cuda paket listesi bos")

    job.stage = "installing CUDA libraries"
    job.detail = ", ".join(specs)

    stop = threading.Event()

    def _creep() -> None:
        crept = 0.0
        while not stop.wait(0.5):
            crept = min(crept + 1.2, 90.0)
            job.percent = crept

    ticker = threading.Thread(target=_creep, daemon=True)
    ticker.start()
    try:
        outcome = install_specs(specs, timeout=1800)
    finally:
        stop.set()

    if getattr(outcome, "blocked", False):
        raise RuntimeError(getattr(outcome, "reason", "kurulum engellendi"))
    if not getattr(outcome, "ok", False):
        tail = (getattr(outcome, "stderr", "") or getattr(outcome, "stdout", "") or "").strip()
        raise RuntimeError(f"pip basarisiz: {tail.splitlines()[-1] if tail else 'bilinmeyen'}")

    # Yeni kurulan DLL'ler bu surecte de bulunur olsun; yoksa ayar
    # yeniden baslatmaya kadar etkisiz kalir.
    try:
        from fool.cuda_runtime import enable

        enable()
    except Exception:
        pass


def _run_cuda(job: Job, e: VoiceEntry) -> None:
    try:
        if e.sidecar_specs:
            install_cuda_runtime(e.id)
        else:
            _install_stt_cuda(job)

        job.percent = 100.0
        job.stage = "done"
        job.detail = ""
        job.state = "done"
        _forget_cuda_probe(e.id)
    except Exception as exc:  # noqa: BLE001 - hata kullaniciya gosterilecek
        job.state = "failed"
        job.stage = "failed"
        job.error = str(exc)
    finally:
        job.finished_at = time.time()
        with _JOBS_LOCK:
            if _ACTIVE_BY_ENTRY.get(e.id) == job.id:
                _ACTIVE_BY_ENTRY.pop(e.id, None)


def start_cuda_install(entry_id: str) -> dict[str, Any]:
    """CUDA calisma zamanini arka planda kur, is kimligini dondur."""
    e = entry(entry_id)
    if e is None:
        raise ValueError(f"bilinmeyen oge: {entry_id}")
    if "cuda" not in e.devices:
        raise ValueError(f"{e.label} CUDA desteklemiyor")

    with _JOBS_LOCK:
        existing_id = _ACTIVE_BY_ENTRY.get(entry_id)
        if existing_id and (existing := _JOBS.get(existing_id)) and existing.state == "running":
            return existing.snapshot()

        job = Job(id=uuid.uuid4().hex[:12], entry_id=entry_id, device="cuda")
        _JOBS[job.id] = job
        _ACTIVE_BY_ENTRY[entry_id] = job.id

    threading.Thread(target=_run_cuda, args=(job, e), daemon=True, name=f"fool-cuda-{job.id}").start()
    return job.snapshot()


def start_install(entry_id: str, device: Device = "cpu") -> dict[str, Any]:
    """Kurulumu arka planda başlat, iş kimliğini döndür."""
    e = entry(entry_id)
    if e is None:
        raise ValueError(f"bilinmeyen oge: {entry_id}")
    if device not in e.devices:
        raise ValueError(f"{e.label} icin desteklenmeyen aygit: {device}")

    with _JOBS_LOCK:
        existing_id = _ACTIVE_BY_ENTRY.get(entry_id)
        if existing_id and (existing := _JOBS.get(existing_id)) and existing.state == "running":
            # Zaten süren bir iş varsa yenisini başlatmak yerine mevcut olan
            # döndürülüyor: iki pip aynı hedefe yazarsa ortam bozulur.
            return existing.snapshot()

        job = Job(id=uuid.uuid4().hex[:12], entry_id=entry_id, device=device)
        _JOBS[job.id] = job
        _ACTIVE_BY_ENTRY[entry_id] = job.id

    threading.Thread(target=_run, args=(job, e), daemon=True, name=f"fool-voice-{job.id}").start()
    return job.snapshot()
