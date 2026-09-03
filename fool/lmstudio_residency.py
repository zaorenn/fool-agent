"""Aynı anda TEK dil modeli yüklü kalsın.

Ölçülen sorun
-------------
LM Studio yüklediği modeli kendiliğinden bırakmıyor. Kullanıcının kartında
ölçüldü (RTX 4070 Ti SUPER, 16 GB):

    google/gemma-4-e4b   6,33 GB   TTL yok   <- yapılandırmada seçili olan
    qwen/qwen3.5-9b      6,55 GB   TTL 1 sa  <- gün boyunca hiç istenmedi
    ------------------------------------------
    toplam              12,88 GB

Geriye ~3 GB kalıyor ve seslendirme motorları da AYNI kartta. Sonucu
günlüklerde görünüyor: ``[TTS/piper] device=cuda istendi ama CUDA bulunamadi;
CPU'ya dusuluyor``. Yani ikinci model, kullanılmadığı hâlde sesin GPU'sunu
yiyor ve her cümle yavaşlıyor.

İkinci model oraya nasıl geliyor: oturumlar modele sabitleniyor
(``sessions.model``) ve eski bir oturum sürdürülünce LM Studio o modeli de
yüklüyor. Sürdürme tarafı ayrıca düzeltildi
(``apps/desktop/src/fool/friend/friend-session.ts``) ama zaten yüklü kalmış
bir modeli oradan boşaltmanın yolu yok -- bu modül onu yapıyor.

Neden ``lms`` komutu
--------------------
LM Studio'nun REST yüzeyi (``/api/v0/models``) yüklü olanı SÖYLÜYOR ama
boşaltma ucu vermiyor. ``lms unload <kimlik>`` veriyor ve LM Studio ile
birlikte kuruluyor. Komut yoksa bu modül hiçbir şey yapmıyor: bir
iyileştirme uğruna sesli oturumu düşürmek yanlış olurdu.

Zone A: upstream bu dosyayı bilmiyor.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

#: Sorgu ve boşaltma için üst sınır. Boşaltma diski değil belleği bırakıyor,
#: yani hızlı; asılı kalan bir komutun sesli oturumu bekletmemesi için var.
_TIMEOUT_SECONDS = 20

#: Gömme modelleri sohbet modeli DEĞİL ve küçükler; tek-model kuralı onlara
#: uygulanmıyor. Yanlışlıkla boşaltmak arama/hafıza yollarını kırardı.
_CHAT_TYPES = frozenset({"llm", "vlm"})


def _cli() -> str:
    """``lms`` komutunun yolu ("" = kurulu değil)."""
    home = os.environ.get("USERPROFILE") or os.environ.get("HOME") or ""
    candidates = [
        Path(home) / ".lmstudio" / "bin" / ("lms.exe" if os.name == "nt" else "lms"),
        Path(home) / ".cache" / "lm-studio" / "bin" / "lms",
    ]
    for path in candidates:
        if path.is_file():
            return str(path)

    from shutil import which

    return which("lms") or ""


def _api_root(base_url: str) -> str:
    """``http://host:1234/v1`` -> ``http://host:1234``."""
    cleaned = (base_url or "").strip().rstrip("/")
    if cleaned.endswith("/v1"):
        cleaned = cleaned[: -len("/v1")]
    return cleaned or "http://localhost:1234"


#: Bu makinenin KENDİSİNİ gösteren adlar.
#:
#: ``agent.model_metadata.is_local_endpoint`` BURADA kullanılamaz: o, zaman
#: aşımı ayarı için "yeterince yakın" diye soruyor ve 192.168/16'yı yerel
#: sayıyor. Buradaki soru farklı -- "aynı makine mi", çünkü verilecek karar
#: ``lms unload`` çalıştırmak.
_LOOPBACK = frozenset({"localhost", "127.0.0.1", "::1", "[::1]", "0.0.0.0"})


def is_same_machine(base_url: str) -> bool:
    """LM Studio BU makinede mi koşuyor?

    Neden gerekli: kullanıcı güçlü masaüstündeki LM Studio'yu alt kattaki
    zayıf dizüstünden sağlayıcı olarak kullanmak istedi. O düzende
    ``loaded_models()`` UZAKTAKİ makineyi doğru okuyor ama ``unload()`` yerel
    ``lms`` komutunu çalıştırıyor -- yani dizüstü, masaüstünün listesine
    bakarak KENDİ modellerini boşaltmaya çalışıyor. En iyi hâlde hiçbir şey
    yapmıyor; dizüstünde de LM Studio varsa yanlış makinede model kapatıyor.

    Okunamayan bir adres ``False`` dönüyor: emin olmadan boşaltmamak, gereksiz
    yere bellekte model bırakmaktan daha ucuz.
    """
    from urllib.parse import urlparse

    cleaned = (base_url or "").strip()

    if not cleaned:
        # Adres yoksa varsayılan ``http://localhost:1234`` -- yani bu makine.
        return True

    candidate = cleaned if "://" in cleaned else "http://" + cleaned

    try:
        host = (urlparse(candidate).hostname or "").strip().lower()
    except ValueError:
        return False

    return host in _LOOPBACK


def busy_models() -> set[str]:
    """ŞU AN üretim yapan modeller -- bunlara DOKUNULMAZ.

    ``lms ps --json`` her model için ``status`` veriyor (``idle`` /
    ``generating``). Üreten bir modeli boşaltmak, süren bir turu ortasından
    kesmek demek: kullanıcı cevabın yarısını alır ve sebebini göremez.

    Sonda koşamıyorsa BOŞ küme DÖNMÜYOR -- ``None`` gibi davranmak yerine
    çağıran taraf hiçbir şey boşaltmıyor (bkz. ``enforce_single``).
    """
    cli = _cli()
    if not cli:
        return set()

    try:
        completed = subprocess.run(
            [cli, "ps", "--json"],
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            timeout=_TIMEOUT_SECONDS,
            check=False,
        )
        rows = json.loads(completed.stdout or "[]")
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        logger.debug("lms ps okunamadi: %s", exc)
        return set()

    if not isinstance(rows, list):
        return set()

    return {
        str(row.get("modelKey") or "")
        for row in rows
        if isinstance(row, dict)
        and str(row.get("status") or "").lower() not in ("idle", "")
        and row.get("modelKey")
    }


def loaded_models(base_url: str, timeout: float = _TIMEOUT_SECONDS) -> list[str]:
    """ŞU AN yüklü sohbet modellerinin kimlikleri.

    Hata YUTULUYOR: LM Studio kapalıysa ya da başka bir sağlayıcı
    kullanılıyorsa burada yapılacak bir şey yok.

    ``timeout`` çağırana bırakıldı: sistem tepsisi menüsü bunu MENÜ AÇILIRKEN
    soruyor ve orada varsayılan 20 saniyeyi beklemek, menünün hiç açılmaması
    demek (bkz. ``fool/residency.py::SNAPSHOT_TIMEOUT_SECONDS``).
    """
    url = f"{_api_root(base_url)}/api/v0/models"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError, urllib.error.URLError) as exc:
        logger.debug("LM Studio model listesi okunamadi: %s", exc)
        return []

    rows = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return []

    return [
        str(row.get("id") or "")
        for row in rows
        if isinstance(row, dict)
        and str(row.get("state") or "") == "loaded"
        and str(row.get("type") or "").lower() in _CHAT_TYPES
        and row.get("id")
    ]


def unload(model_id: str) -> bool:
    """Bu modeli bellekten bırak. ``False`` = yapılamadı."""
    cli = _cli()
    if not cli or not model_id:
        return False

    try:
        completed = subprocess.run(
            [cli, "unload", model_id],
            capture_output=True,
            text=True,
            # ``stdin`` ACIKCA veriliyor: ``lms unload`` birden fazla model
            # varken INTERAKTIF secim soruyor ve devralinan bir tanitici ile
            # asili kaliyor.
            stdin=subprocess.DEVNULL,
            timeout=_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.debug("lms unload basarisiz (%s): %s", model_id, exc)
        return False

    return completed.returncode == 0


def enforce_single(base_url: str, keep: str) -> list[str]:
    """``keep`` DIŞINDAKİ yüklü sohbet modellerini bırak.

    Bırakılanların listesi döner. ``keep`` boşsa hiçbir şey yapılmıyor:
    hangisinin korunacağını bilmeden boşaltmak, kullanıcının o an konuştuğu
    modeli kapatmak olurdu.
    """
    wanted = (keep or "").strip()
    if not wanted:
        return []

    if not is_same_machine(base_url):
        # Sağlayıcı BAŞKA bir makinede. Boşaltma yerel ``lms`` komutuyla
        # yapılıyor, yani buradan çalıştırmak uzaktaki modeli bırakmıyor --
        # yalnızca yerelde ne varsa ona dokunuyor. Doğru davranış hiçbir şey
        # yapmamak: kartı paylaşan makine zaten burası değil.
        logger.debug(
            "[The Fool] LM Studio %s uzakta; yerlesim zorlamasi atlandi", base_url
        )

        return []

    # UREYEN modele dokunulmuyor.
    #
    # Kullanicinin sohbet oturumlarinin 43'u qwen'e sabitli
    # (``sessions.model``), yani bu makinede baska bir modelin ustunde
    # gercekten bir tur koseabiliyor. Onu boslatmak turu ortasindan keser ve
    # LM Studio hemen yeniden yukler -- 6,5 GB'lik bir yukle-bosalt dongusu,
    # ki donmanin sebeplerinden biri tam olarak bu.
    busy = busy_models()

    dropped: list[str] = []
    for model_id in loaded_models(base_url):
        if model_id == wanted or model_id in busy:
            continue
        if unload(model_id):
            dropped.append(model_id)

    if dropped:
        logger.info(
            "[The Fool] LM Studio: %s bosaltildi (%s korundu)", ", ".join(dropped), wanted
        )

    return dropped
