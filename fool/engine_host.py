"""Kalıcı motor süreçleri — modeli bir kez yükle, açık tut.

Neden bu var
------------
İlk sidecar tasarımında her sentez çağrısı YENİ bir Python süreci
başlatıyordu: süreç torch'u içe aktarıyor (~5-10 sn), modeli diskten
yüklüyor (~10-40 sn), tek cümleyi sentezliyor ve ölüyordu. Sonraki cümlede
her şey baştan — hiçbir şey önbellekte kalmıyor, çünkü önbelleği tutacak
süreç yok.

Ölçüldü (Kokoro, 82M parametre, beş kelimelik cümle, CUDA):

    1. çağrı   48,7 sn
    2. çağrı   21,4 sn

Aynı model kalıcı bir süreçte saniyenin altında çalışıyor. Yani gecikmenin
neredeyse tamamı model yüklemeydi, sentez değil. Kullanıcının "CUDA'ya
rağmen aşırı yavaş" şikâyetinin tek sebebi buydu.

Protokol
--------
stdin/stdout üzerinde satır başına bir JSON. Basitliği kasıtlı: bir soket
port çakışması, erişim denetimi ve temizlik sorunları getirirdi — boru ise
süreçle birlikte kendiliğinden ölüyor.

stdout kirliliği
----------------
Motor kütüphaneleri açılışta stdout'a yazıyor (ilerleme çubukları, uyarılar)
ve bu protokolü bozar. Kurulum boyunca stdout stderr'e yönlendiriliyor;
protokol yalnızca saklanan gerçek stdout'u kullanıyor.

Zone A: upstream bu dosyayı bilmiyor.
"""

from __future__ import annotations

import hashlib
import json
import logging
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Any, Final

logger = logging.getLogger(__name__)

from fool.sidecar import _isolated_env, sidecar_python

#: İlk istek model yüklemeyi de bekliyor; sonrakiler yalnızca sentezi.
BOOT_TIMEOUT_SECONDS: Final = 600
REQUEST_TIMEOUT_SECONDS: Final = 300

#: Motoru saran koşucu. ``{setup}`` modeli yükler ve ``handle(req)`` tanımlar.
_RUNNER: Final = '''
import json
import sys

# Protokol icin GERCEK stdout saklaniyor; kurulum boyunca stdout stderr'e
# yonlendiriliyor cunku motor kutuphaneleri oraya ilerleme yaziyor.
_out = sys.stdout
sys.stdout = sys.stderr

# Kurulum EXEC ile calisiyor ki hatasi YAKALANABILSIN.
#
# Once dogrudan yazilmisti ve bir istisna stderr'e (DEVNULL) gidiyordu:
# ebeveyn yalnizca "surec oldu" goruyor, SEBEBI goremiyordu. Olculdu --
# F5-TTS'in "paylasilan FFmpeg kutuphaneleri gerekiyor" mesaji tamamen
# kayboluyor ve kullanici ham bir cokme ile bas basa kaliyordu.
#
# ``exec(..., globals())`` modul kapsamini koruyor: kurulumda tanimlanan
# ``handle`` ve ``global`` degiskenleri aynen calisiyor.
try:
    exec(compile({setup!r}, "<setup>", "exec"), globals())
except BaseException as _boot_exc:
    sys.stdout = _out
    _out.write(json.dumps({{"ready": False, "error": "%s: %s" % (type(_boot_exc).__name__, _boot_exc)}}) + "\\n")
    _out.flush()
    raise SystemExit(1)

sys.stdout = _out
_out.write(json.dumps({{"ready": True}}) + "\\n")
_out.flush()

for _line in sys.stdin:
    _line = _line.strip()
    if not _line:
        continue
    try:
        _req = json.loads(_line)
        sys.stdout = sys.stderr
        _result = handle(_req)
        sys.stdout = _out
        _payload = {{"ok": True, "result": _result}}
    except Exception as _exc:
        sys.stdout = _out
        _payload = {{"ok": False, "error": "%s: %s" % (type(_exc).__name__, _exc)}}
    _out.write(json.dumps(_payload) + "\\n")
    _out.flush()
'''


@dataclass
class _Engine:
    lock: threading.Lock
    process: subprocess.Popen
    setup_hash: str
    #: Son kullanim zamani -- VRAM tahliyesinde en eskisi once gidiyor.
    last_used: float = 0.0


_ENGINES: dict[str, _Engine] = {}
_ENGINES_LOCK = threading.Lock()

#: Ayni anda ayakta tutulacak EN FAZLA motor sayisi.
#:
#: FOOL-SEAM: engine-vram-eviction
#:
#: Bir varsayilan degil, olculmus bir zorunluluk. Her motor modelini VRAM'e
#: yukluyor ve kalici surec oldugu icin HIC birakmiyordu. Kullaniciya "TTS
#: calismiyor" diye gorunen sey buydu -- tek tek her motor calisiyor, hepsi
#: birlikte hicbiri calismiyor.
#:
#: TEK motor. Bir sure IKI idi ve o karar SEBEBIYLE dogruydu:
#:
#: Once 1 denendi ve daha kotu bir sorun uretti: o gun uygulamada AYNI ANDA
#: iki yuzey konusuyordu (sohbet paneli genel ``tts.provider`` ile, Friend
#: KENDI sectigiyle). Ikisi farkli motor secince her tur yukle-bosalt-yukle
#: dongusune giriyordu -- olculdu, qwen3 40 sn + styletts2 37 sn, yani makine
#: surekli model yukluyor ve hicbir cumle zamaninda seslendirilmiyor.
#: Kullanicinin "bilgisayarim deli gibi kasti ve yine ses gelmedi" dedigi
#: sey buydu. Sinir 2'ye cikarilinca iki yuzeyin cakismasi bitti.
#:
#: O SEBEP ARTIK YOK: kip basina ses uclari kaldirildi ve seslendirme motoru
#: her yuzeyde TEK yerden seciliyor -- ``tts.provider`` (bkz.
#: ``fool/voice_modes.py::FRIEND`` ve ``fool/voice_routes.py``deki kaldirma
#: notu). Iki yuzey artik ayni motoru istiyor, yani ikinci yuva yalnizca
#: ONCEKI secimi bellekte tutmaya yariyordu.
#:
#: Kullanicinin kurali da bu: ayni anda tek STT + tek TTS + tek LLM, ve bir
#: kategoride yeni bir sey secilince oncekisi TAMAMEN birakilsin
#: (``fool/residency.py``). Ikinci yuva o kurali sessizce bozuyordu:
#: Ayarlar'da bir motoru dinlemek (``voice_preview``) ikinci bir modeli
#: karta yukluyor ve secili motor yaninda oylece kaliyordu.
#:
#: Olculmus zemin degismedi: bes TTS motoru + whisper + LM Studio'daki 9B
#: model ayni 16 GB kartta birikince
#:
#:     nvidia-smi -> 15338 / 16376 MiB dolu, 724 MiB bos, 10 surec
#:
#: ve o noktadan sonra her sey bozuluyor: sentez saniyelerce takiliyor,
#: panelde "Speaking..." donuyor, cogu zaman hic ses cikmiyor.
MAX_RESIDENT_ENGINES = 1

#: Bosta kalan bir motor bu sureden sonra kendiliginden bosaltiliyor.
#:
#: Bes dakika bilincli: bir sohbet turu arasindan cok uzun (yeniden yukleme
#: bedelini her cumlede odemeyelim), ama kullanici baska ise gectiginde
#: karti sonsuza kadar tutmayacak kadar kisa. ``fool/gpu_budget.py``deki
#: konusma tanima esigiyle ayni buyukluk.
IDLE_UNLOAD_SECONDS = 300.0

#: SECILI motor icin bosta suresi -- BES DAKIKA (kullanicinin istegi).
#:
#: Sayac HER kullanimda sifirlaniyor (``last_used``), yani surekli konusulan
#: bir oturumda motor hic bosalmiyor; bes dakika SESSIZLIKTEN sonra
#: birakiliyor. Kullanicinin istedigi davranis birebir bu.
#:
#: Olculdu (urun yolu, Chatterbox Turbo): sicak 0,78 sn/cumle, soguk
#: 13,08 sn. Bes dakika, kartin bos yere tutulmasi ile her aradan sonra
#: soguk yukleme odemek arasindaki denge.
#:
#: Secili OLMAYAN motorlar da ayni surede birakiliyor.
SELECTED_IDLE_UNLOAD_SECONDS = 300.0


def _selected_engine() -> str:
    """Yapilandirmada secili seslendirme motorunun adi ("" = bilinmiyor).

    Hata YUTULUYOR: yapilandirma okunamiyorsa herkes ayni esige tabi olur --
    eski davranis, yani guvenli taraf.
    """
    try:
        from fool_cli.config import load_config

        return str(((load_config() or {}).get("tts") or {}).get("provider") or "").strip()
    except Exception:
        return ""


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _free_vram_from_llms(name: str) -> None:
    """Kart doluysa BOSTAKI dil modellerini birak.

    Olculdu (kullanicinin karti, 16 GB): gemma 6,33 GB + qwen 6,55 GB =
    12,88 GB, ustune Chatterbox ~3,5 GB. Kart asiliyor ve Windows GPU
    bellegini sistem RAM'ine tasimaya basliyor (WDDM paylasimli bellek) --
    makine cokmuyor ama DONUYOR.

    UREYEN model korunuyor (bkz. ``lmstudio_residency.busy_models``): suren
    bir turu ortasindan kesmek, ustune LM Studio'nun onu hemen yeniden
    yuklemesi demek -- 6,5 GB'lik bir yukle-bosalt dongusu.

    Hata YUTULUYOR: bir bellek temizligi ugruna sentezi dusurmek yanlis.
    """
    try:
        from fool.gpu_budget import fits_in_vram, free_vram_mb

        free = free_vram_mb()
        if free is None or fits_in_vram(name, free):
            return

        from fool import lmstudio_residency
        from fool_cli.config import load_config

        model_cfg = (load_config() or {}).get("model") or {}
        lmstudio_residency.enforce_single(
            str(model_cfg.get("base_url") or "http://localhost:1234/v1"),
            str(model_cfg.get("default") or model_cfg.get("model") or ""),
        )
    except Exception as exc:  # pragma: no cover
        logger.debug("LM Studio bosaltmasi atlandi: %s", exc)


def _evict_for(name: str) -> list[str]:
    """FOOL-SEAM: engine-vram-eviction

    Yeni bir motora yer ac: EN ESKI kullanilan motorlari durdur.

    Iki kosuldan biri yeterli:

    * Ayakta duran motor sayisi ``MAX_RESIDENT_ENGINES``i asiyor, ya da
    * kartta yer kalmadi (``fool/gpu_budget.py`` olcuyor).

    Ikinci kosul ilkinden bagimsiz olarak gerekiyor: iki motor bile kartta
    yer birakmayabilir (Chatterbox ~3,5 GB, Kyutai ~3,5 GB ve kartta zaten
    LM Studio'nun 9B modeli var).

    Durdurulan motor bir sonraki kullanimda yeniden yukleniyor -- bedeli
    olculdu ve kabul edilebilir (Kokoro 8 sn, StyleTTS 2 19 sn ilk cagri).
    Alternatif, hicbirinin calismamasi.
    """
    with _ENGINES_LOCK:
        # KULLANIMDA olan motor asla tahliye edilmiyor: kilidi tutulan bir
        # motoru durdurmak, suren bir sentezi ortasindan kesmek demek --
        # kullanici cumlenin yarisini duyar ve sebebini goremez.
        others = [
            (n, e.last_used)
            for n, e in _ENGINES.items()
            if n != name and not e.lock.locked()
        ]

    # Ses motorlarindan ONCE kullanilmayan DIL MODELLERINI birak.
    #
    # Buraya tasindi cunku asagidaki ``if not others: return []`` yolu en sik
    # yasanan durum: tek bir ses motoru var. Blok orada dururken hic
    # calismiyordu -- olculdu, sentez sirasinda VRAM 12.393 -> 15.768 MiB
    # (16.376'nin %96'si) cikti ve hicbir model birakilmadi.
    #
    # Kullanilmayan bir dil modelini birakmak, calisan bir ses motorunu
    # durdurmaktan her zaman daha ucuz: LM Studio onu bir sonraki istekte
    # zaten yeniden yukler, oysa durdurulan ses motoru KONUSMAYI kesiyor.
    _free_vram_from_llms(name)

    if not others:
        return []

    others.sort(key=lambda item: item[1])
    victims: list[str] = []

    # 1) Sayi siniri.
    overflow = (len(others) + 1) - MAX_RESIDENT_ENGINES
    while overflow > 0 and others:
        victims.append(others.pop(0)[0])
        overflow -= 1

    # 2) Bellek siniri. Sonda cokerse tahliye ETMIYORUZ: olcemedigimiz bir
    #    durumda calisan motorlari durdurmak, cozdugunden cok sorun uretir.
    try:
        from fool.gpu_budget import fits_in_vram, free_vram_mb

        free = free_vram_mb()

        while others and free is not None and not fits_in_vram(name, free):
            victim = others.pop(0)[0]
            victims.append(victim)
            # Durdurup YENIDEN olcuyoruz: tahmin etmek yerine karta sormak.
            _stop_locked(victim)
            free = free_vram_mb()
    except Exception as exc:  # pragma: no cover
        logger.debug("VRAM tahliyesi atlandi: %s", exc)

    for victim in victims:
        _stop_locked(victim)

    if victims:
        logger.info(
            "[The Fool] %s icin yer acildi; durdurulan motor(lar): %s",
            name, ", ".join(dict.fromkeys(victims)),
        )
    return victims


def _idle_sweep() -> list[str]:
    """FOOL-SEAM: engine-vram-eviction

    ``IDLE_UNLOAD_SECONDS``dan uzun sure kullanilmayan motorlari bosalt.

    KULLANIMDA olan motor sayilmiyor: kilidi tutulan bir surec suren bir
    sentezin ortasinda ve onu durdurmak cumleyi yarida kesmek demek.

    Neden bir izleyici gerekiyor: tahliye yalnizca YENI bir motor
    istendiginde caliyor. Kullanici konusmayi birakip baska ise gecerse
    hicbir istek gelmiyor ve son motor karti sonsuza kadar tutuyordu.
    """
    now = time.monotonic()

    # Secili motor daha uzun yasiyor: bir sonraki cumleyi o soyleyecek.
    selected = _selected_engine()

    with _ENGINES_LOCK:
        stale = [
            name
            for name, engine in _ENGINES.items()
            if not engine.lock.locked()
            and now - engine.last_used
            >= (SELECTED_IDLE_UNLOAD_SECONDS if name == selected else IDLE_UNLOAD_SECONDS)
        ]

    for name in stale:
        _stop_locked(name)

    if stale:
        logger.info(
            "[The Fool] bosta kalan motor(lar) bosaltildi: %s", ", ".join(stale)
        )
    return stale


_IDLE_THREAD: threading.Thread | None = None
_IDLE_THREAD_LOCK = threading.Lock()


def _ensure_idle_watcher() -> None:
    """Bosta-bosaltma izleyicisini calistir (tek, uzun omurlu, daemon)."""
    global _IDLE_THREAD

    with _IDLE_THREAD_LOCK:
        if _IDLE_THREAD is not None and _IDLE_THREAD.is_alive():
            return

        def _loop() -> None:
            while True:
                time.sleep(min(30.0, IDLE_UNLOAD_SECONDS / 4))
                try:
                    _idle_sweep()
                except Exception as exc:  # pragma: no cover
                    logger.debug("bosta tarama atlandi: %s", exc)

        _IDLE_THREAD = threading.Thread(
            target=_loop, name="fool-engine-idle", daemon=True
        )
        _IDLE_THREAD.start()


def _stop_locked(name: str) -> None:
    """``stop`` ama zaten durdurulmus olmasi sorun degil."""
    try:
        stop(name)
    except Exception as exc:  # pragma: no cover
        logger.debug("motor %s durdurulamadi: %s", name, exc)


def _spawn(name: str, setup: str) -> _Engine:
    python = sidecar_python(name)
    if not python.exists():
        raise RuntimeError(f"{name} sidecar ortami kurulu degil")

    process = subprocess.Popen(
        [str(python), "-u", "-c", _RUNNER.format(setup=setup)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        # stderr YUTULUYOR: motorlar oraya yuzlerce satir uyari yaziyor ve
        # okunmayan bir boru dolunca surec KILITLENIR.
        stderr=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        env=_isolated_env(),
        errors="replace",
    )

    # Hazır işaretini bekle: model yüklenmeden gönderilen bir istek
    # "motor çöktü" gibi görünürdü.
    deadline = time.monotonic() + BOOT_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"{name}: motor sureci acilista coktu")

        line = process.stdout.readline() if process.stdout else ""
        if not line:
            # ``readline()`` bos dize YALNIZCA EOF'ta doner: boru kapandi.
            #
            # Eski kod burada ``continue`` diyordu ve dongu ``poll()``a
            # bakiyordu -- ama surec stdout'u kapatip henuz cikmadiysa
            # ``poll()`` hala ``None``. Yani dongu 600 saniyelik acilis
            # suresi dolana kadar HIZLI DONUYOR: bir CPU cekirdegi doluyor ve
            # istemciye on dakika boyunca hicbir sey soylenmiyor -- ne
            # ``start``, ne ``end``, ne ``fallback``.
            #
            # EOF geri donusu olmayan bir hal: dongu yerine hata.
            process.kill()
            raise RuntimeError(f"{name}: motor sureci acilista ciktisini kapatti")

        try:
            payload = json.loads(line)
        except ValueError:
            # Protokol öncesi kaçak satır — yoksay, beklemeye devam et.
            continue

        if payload.get("ready"):
            return _Engine(lock=threading.Lock(), process=process, setup_hash=_hash(setup))

        # Kurulum SEBEBIYLE dustu: sebebi yukari tasi. Ham bir "surec coktu"
        # kullaniciyi hicbir yere goturmuyordu.
        if "error" in payload:
            process.kill()
            raise RuntimeError(f"{name}: {payload['error']}")

    process.kill()
    raise RuntimeError(f"{name}: motor {BOOT_TIMEOUT_SECONDS} sn icinde hazir olmadi")


def stop(name: str) -> None:
    """Çalışan motoru durdur. Idempotent."""
    with _ENGINES_LOCK:
        engine = _ENGINES.pop(name, None)

    if engine is None or engine.process.poll() is not None:
        return

    try:
        if engine.process.stdin:
            engine.process.stdin.close()
        engine.process.wait(timeout=5)
    except Exception:
        engine.process.kill()


def stop_gracefully(name: str, timeout: float = 30.0) -> None:
    """Motoru durdur ama SÜREN bir sentezi ortasından kesme.

    ``stop()`` stdin'i motorun kilidini ALMADAN kapatıyor. O sırada bir sentez
    sürüyorsa sidecar'ın ``for line in sys.stdin`` döngüsü bitiyor, süreç
    çıkıyor ve bekleyen ``readline()`` boş dönüyor -- yani kullanıcının o an
    dinlediği cümle ortasında susuyor ve çağıran "motor cevap vermeden
    kapandı" hatası alıyor.

    Somut tetik: ses panelinden başka bir motor seçmek (``voice_models.select``)
    ya da bir klon değiştirmek. Kullanıcı konuşurken ayar değiştirdiğinde ses
    kesiliyordu.

    ``_evict_for`` ve ``_idle_sweep`` bu inceliği zaten gözetiyor (kilitli
    motoru atlıyorlar); eksik olan açık ``stop`` yoluydu.

    Süre dolarsa yine de durduruluyor: kullanıcının açık isteği (motoru
    değiştir) sonsuza kadar bekletilemez.
    """
    with _ENGINES_LOCK:
        engine = _ENGINES.get(name)

    if engine is None:
        stop(name)
        return

    acquired = engine.lock.acquire(timeout=timeout)
    try:
        stop(name)
    finally:
        if acquired:
            engine.lock.release()


def stop_all() -> None:
    with _ENGINES_LOCK:
        names = list(_ENGINES)
    for name in names:
        stop(name)


def is_running(name: str) -> bool:
    with _ENGINES_LOCK:
        engine = _ENGINES.get(name)
    return engine is not None and engine.process.poll() is None


def running() -> list[str]:
    """Su an AYAKTA olan motorlarin adlari (en eski kullanilan basta).

    Kayitta OLUP sureci olmus motorlar eleniyor: ``_ENGINES`` anahtarlarini
    dogrudan okumak "yuklu" diye olu bir surec gostermek olurdu ve tepsi
    menusu kullaniciya bosaltacak bir sey olmadigi halde bosaltma dugmesi
    verirdi.

    Sira ``last_used``: tahliyenin kurbanini sectigi sirayla ayni, yani
    listeyi okuyan bir yuzey "sirada kim var" sorusunu da cevaplayabiliyor.
    """
    with _ENGINES_LOCK:
        rows = sorted(_ENGINES.items(), key=lambda item: item[1].last_used)

    return [name for name, engine in rows if engine.process.poll() is None]


#: Motor basina acilis kilidi. ``_SPAWN_LOCKS_LOCK`` yalnizca bu haritayi
#: koruyor -- acilisin kendisi motor basina kilitle serilestiriliyor.
_SPAWN_LOCKS: dict[str, threading.Lock] = {}
_SPAWN_LOCKS_LOCK = threading.Lock()


def _spawn_lock_for(name: str) -> threading.Lock:
    with _SPAWN_LOCKS_LOCK:
        lock = _SPAWN_LOCKS.get(name)
        if lock is None:
            lock = threading.Lock()
            _SPAWN_LOCKS[name] = lock
        return lock


def _read_reply_bounded(engine: Any, timeout: float) -> str | None:
    """Bir cevap satiri oku; ``None`` = sure doldu.

    ``readline()`` AYRI bir is parcaciginda kosuyor cunku boru okumalarinin
    tasinabilir bir zaman asimi yok. Sure dolunca cagiran sureci olduruyor;
    bu, asili kalan okumayi da bitiriyor ve is parcacigi kendiliginden
    sonlaniyor -- yani birikmiyor.
    """
    box: list[str] = []
    failure: list[BaseException] = []

    def _read() -> None:
        try:
            box.append(engine.process.stdout.readline())
        except BaseException as exc:  # noqa: BLE001 -- cagirana tasiniyor
            failure.append(exc)

    reader = threading.Thread(target=_read, daemon=True, name="fool-engine-reply")
    reader.start()
    reader.join(timeout)

    if reader.is_alive():
        return None

    if failure:
        raise failure[0]

    return box[0] if box else ""


def request(name: str, setup: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Motora bir istek gönder; gerekiyorsa önce başlat.

    ``setup`` değişirse (başka bir model ya da aygıt seçildi) süreç yeniden
    başlatılıyor: ayakta duran süreç ESKİ modeli tutuyor ve sessizce yanlış
    sesle cevap verirdi — sessiz yanlışlık, görünür hatadan kötüdür.
    """
    setup_hash = _hash(setup)

    with _ENGINES_LOCK:
        engine = _ENGINES.get(name)
        stale = engine is not None and (
            engine.setup_hash != setup_hash or engine.process.poll() is not None
        )

    if stale:
        stop(name)
        engine = None

    if engine is None:
        # Ayni motoru IKI kez baslatmayi engelle.
        #
        # Olculen hata: ``_spawn`` kilidin DISINDA kosuyordu. Iki is parcacigi
        # (isitma ucu + ilk cumle, ya da iki ses yuzeyi) ayni anda ``None``
        # goruyor, IKISI de bir surec baslatip modeli yukluyor ve ikincisi
        # birincinin kaydini eziyordu. Ezilen surec artik ``_ENGINES``te
        # olmadigi icin ``stop()``, ``_idle_sweep()`` ve ``stop_all()`` ona
        # ULASAMIYOR: VRAM'i uygulama kapanana kadar tutuyor.
        #
        # Bu, ``MAX_RESIDENT_ENGINES`` / ``engine-vram-eviction`` tasariminin
        # tam olarak onlemek icin var oldugu sonuc -- chatterbox'ta anlik ve
        # kalici 3,5 GB.
        #
        # Kilit MOTOR BASINA: farkli motorlarin paralel acilisi (STT + TTS
        # isitmasi) yavaslamamali.
        with _spawn_lock_for(name):
            # Kilidi bekleyen ikinci cagiran icin: birincisi kurmus olabilir.
            with _ENGINES_LOCK:
                existing = _ENGINES.get(name)
                if existing is not None and (
                    existing.setup_hash != setup_hash or existing.process.poll() is not None
                ):
                    existing = None
                engine = existing

            if engine is None:
                # FOOL-SEAM: engine-vram-eviction -- yer ACMADAN once yukleme yapma.
                _evict_for(name)
                spawned = _spawn(name, setup)
                with _ENGINES_LOCK:
                    _ENGINES[name] = spawned
                engine = spawned

    engine.last_used = time.monotonic()
    _ensure_idle_watcher()

    # Tek sürece aynı anda iki istek giderse cevaplar birbirine karışır:
    # protokol satır sıralı ve hangi cevabın hangi isteğe ait olduğunu
    # ayırt edecek bir kimlik taşımıyor.
    timed_out = False

    with engine.lock:
        if engine.process.poll() is not None:
            stop(name)
            raise RuntimeError(f"{name}: motor sureci kapandi")

        try:
            engine.process.stdin.write(json.dumps(payload) + "\n")  # type: ignore[union-attr]
            engine.process.stdin.flush()  # type: ignore[union-attr]
            # Cevap SINIRLI bir sure bekleniyor.
            #
            # Eski hali ciplak ``readline()`` idi ve ``REQUEST_TIMEOUT_SECONDS``
            # tanimliydi ama HICBIR YERDE kullanilmiyordu. Sidecar takilirsa
            # (CUDA kilidi, model kilitlenmesi, yarim kalmis indirme) o cagri
            # SONSUZA kadar bloke oluyor -- ustelik ``engine.lock`` elde
            # tutularak. Yani hata yerel kalmiyor: o motora giden BUTUN sonraki
            # istekler de ayni kilitte bekliyor ve ses kalici olarak susuyor,
            # hicbir hata da gorunmuyor.
            line = _read_reply_bounded(engine, REQUEST_TIMEOUT_SECONDS)
        except (BrokenPipeError, OSError) as exc:
            stop(name)
            raise RuntimeError(f"{name}: motorla iletisim koptu: {exc}") from exc

        if line is None:
            timed_out = True

        # Istek BITTIGINDE de tazeleniyor: uzun bir sentez sirasinda
        # baslangic damgasi eskiyor ve motor is biter bitmez "bosta"
        # sayilabiliyordu.
        engine.last_used = time.monotonic()

    if timed_out:
        # Surec OLDURULUYOR: takilmis bir motor kendine gelmiyor ve ayakta
        # birakmak bir sonraki istegi de ayni kilitte bekletirdi. Oldurunce
        # bekleyenler "surec kapandi" alip hemen dusuyor, cagiran da yedek
        # yola gecebiliyor.
        stop(name)
        raise RuntimeError(f"{name}: motor {REQUEST_TIMEOUT_SECONDS} sn icinde cevap vermedi")

    if not line:
        stop(name)
        raise RuntimeError(f"{name}: motor cevap vermeden kapandi")

    try:
        reply = json.loads(line)
    except ValueError as exc:
        stop(name)
        raise RuntimeError(f"{name}: motordan bozuk cevap geldi") from exc

    if not reply.get("ok"):
        raise RuntimeError(f"{name}: {reply.get('error') or 'bilinmeyen hata'}")

    return reply.get("result") or {}
