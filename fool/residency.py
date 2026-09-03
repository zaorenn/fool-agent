"""Bellekte AYNI ANDA ne var: tek STT, tek TTS, tek LLM.

Neden bu var
------------
Uc kategori de AYNI karti paylasiyor ama ucunu de baska bir yer yukluyor:

===========  =============================================================
Kategori     Modeli TUTAN yer
===========  =============================================================
STT          ana surecteki global onbellek
             (``tools/transcription_tools.py::_local_model``)
TTS          izole ALT SURECLER (``fool/engine_host.py::_ENGINES``) ve
             ana surecteki kucuk motor onbellekleri (piper, kittentts)
LLM          bambaska bir UYGULAMA (LM Studio) --
             ``fool/lmstudio_residency.py``
===========  =============================================================

Uc ayri yerde duran uc ayri "yuklu mu" cevabi hicbir yerde birlesmiyordu:
"su an ne tutuluyor" sorusunun tek bir cevabi yoktu -- ne kullanici icin, ne
kod icin. Kullanici yalnizca sonucunu goruyordu.

Olculdu (RTX 4070 Ti SUPER, 16 GB): gemma 6,33 GB + qwen 6,55 GB +
whisper 1,6 GB + chatterbox 3,5 GB. Kart asiliyor ve Windows GPU bellegini
sistem RAM'ine tasimaya basliyor (WDDM paylasimli bellek) -- makine
cokmuyor, DONUYOR.

Bu modul o uc yeri tek yuzeyde topluyor:

``snapshot()``        ne yuklu, ne isiniyor, ne secili
``unload(kind)``      birak (kullanicinin acik istegi)
``enforce_single()``  her kategoride SECILI olmayan her seyi birak

ITHAL ETMEYEN SONDA
-------------------
``snapshot()`` agir modulleri ITHAL ETMIYOR, ``sys.modules``e bakiyor.
Sebebi dogrudan: modul hic ithal edilmemisse zaten hicbir sey yuklu degil ve
onu yalnizca "yuklu mu" diye sormak icin ithal etmek, sorunun kendisini
yaratmak olurdu -- ``tools.transcription_tools`` ithali torch/ctranslate2
zincirini aciyor.

Zone A: upstream bu dosyayi bilmiyor.
"""

from __future__ import annotations

import logging
import sys
from typing import Any, Final, Iterable

logger = logging.getLogger(__name__)

#: Kategoriler ve kullaniciya gorunen adlari. Sira BILINCLI: tepsi menusu
#: bunu oldugu gibi ciziyor ve konusma zinciri bu sirayla isliyor
#: (duyuyorum -> dusunuyorum -> konusuyorum).
KIND_LABELS: Final[dict[str, str]] = {
    "stt": "Speech recognition",
    "tts": "Voice",
    "llm": "Language model",
}

KINDS: Final[tuple[str, ...]] = tuple(KIND_LABELS)

#: LM Studio sondasinin ust siniri (saniye).
#:
#: Varsayilan 20 sn DEGIL: bu sonda tepsi menusu acilirken kosuyor ve orada
#: 20 saniye beklemek menunun HIC acilmamasi demek. LM Studio kapaliysa
#: baglanti zaten aninda reddediliyor; acikken yerel bir istek milisaniyeler
#: suruyor. Iki saniye ikisi icin de fazlasiyla yeterli.
SNAPSHOT_TIMEOUT_SECONDS: Final = 2.0


# ---------------------------------------------------------------------------
# Yapilandirma
# ---------------------------------------------------------------------------


def _config() -> dict[str, Any]:
    """Yapilandirma (okunamazsa bos sozluk -- cagiran taraf dallanmasin)."""
    try:
        from fool_cli.config import load_config

        return load_config() or {}
    except Exception as exc:  # noqa: BLE001
        logger.debug("yapilandirma okunamadi: %s", exc)
        return {}


def _llm_base_url(cfg: dict[str, Any] | None = None) -> str:
    model_cfg = (cfg if cfg is not None else _config()).get("model") or {}
    return str(model_cfg.get("base_url") or "http://localhost:1234/v1").strip()


def _selected_llm(cfg: dict[str, Any] | None = None) -> str:
    model_cfg = (cfg if cfg is not None else _config()).get("model") or {}
    return str(model_cfg.get("default") or model_cfg.get("model") or "").strip()


def _selected_tts(cfg: dict[str, Any] | None = None) -> str:
    tts_cfg = (cfg if cfg is not None else _config()).get("tts") or {}
    return str(tts_cfg.get("provider") or "").strip()


def _selected_stt(cfg: dict[str, Any] | None = None) -> str:
    stt_cfg = (cfg if cfg is not None else _config()).get("stt") or {}
    return str((stt_cfg.get("local") or {}).get("model") or "").strip()


def _entry_label(entry_id: str) -> str:
    """Katalog etiketi (bulunamazsa kimligin kendisi).

    Kullaniciya ``chatterbox`` degil ``Chatterbox`` gosterilmeli; katalog
    zaten bu esleme icin var.
    """
    try:
        from fool import voice_models

        found = voice_models.entry(entry_id)
        if found is not None:
            return found.label

        for candidate in voice_models.CATALOG:
            if (candidate.provider_id or candidate.id) == entry_id:
                return candidate.label
            if candidate.kind == "stt" and candidate.model_id == entry_id:
                return candidate.label
    except Exception as exc:  # noqa: BLE001
        logger.debug("katalog etiketi okunamadi (%s): %s", entry_id, exc)

    return entry_id


def _tts_entry_id(provider: str) -> str:
    """Saglayici adindan MOTOR adi (``qwen3`` -> ``qwen3-tts``).

    Motor surecleri katalog kimligiyle aniliyor, yapilandirmada ise saglayici
    adi duruyor. Ikisini karistirmak, secili motoru "secili degil" sayip
    kullanicinin tam o an konustugu motoru bosaltmak olurdu.

    Esleme ``voice_models`` icinde ZATEN var; ikinci bir kopya yazmak, katalog
    degistiginde birinin geride kalmasi demekti.
    """
    if not (provider or "").strip():
        return ""

    try:
        from fool import voice_models

        return voice_models._entry_id_for_provider(provider)
    except Exception as exc:  # noqa: BLE001
        logger.debug("motor kimligi cozulemedi (%s): %s", provider, exc)
        return provider.strip().lower()


# ---------------------------------------------------------------------------
# Ne yuklu
# ---------------------------------------------------------------------------


def _module(name: str) -> Any | None:
    """ITHAL ETMEDEN modul (yuklenmemisse ``None``) -- bkz. modul basligi."""
    return sys.modules.get(name)


def _stt_loaded() -> list[dict[str, str]]:
    tt = _module("tools.transcription_tools")
    if tt is None or getattr(tt, "_local_model", None) is None:
        return []

    model_id = str(getattr(tt, "_local_model_name", "") or "local")
    return [{"id": model_id, "label": _entry_label(model_id)}]


#: Ana surecte model tutan seslendirme motorlari: ``(onbellek adi, saglayici)``.
#:
#: Piper ile KittenTTS sidecar KULLANMIYOR -- modelleri ana surecin
#: sozluklerinde duruyor ve yalnizca sureclere bakan bir sonda onlari hic
#: gormezdi ("hicbir sey yuklu degil" derken bellekte model tutmak).
_IN_PROCESS_TTS: Final[tuple[tuple[str, str], ...]] = (
    ("_piper_voice_cache", "piper"),
    ("_kittentts_model_cache", "kittentts"),
)


def _tts_loaded() -> list[dict[str, str]]:
    """Ayakta duran seslendirme motorlari (kalici surecler + ana surec)."""
    rows: list[dict[str, str]] = []

    host = _module("fool.engine_host")
    if host is not None:
        try:
            for name in host.running():
                rows.append({"id": name, "label": _entry_label(name)})
        except Exception as exc:  # noqa: BLE001
            logger.debug("motor listesi okunamadi: %s", exc)

    tts_tool = _module("tools.tts_tool")
    if tts_tool is not None:
        for attr, provider in _IN_PROCESS_TTS:
            if getattr(tts_tool, attr, None):
                rows.append({"id": provider, "label": _entry_label(provider)})

    return rows


def _llm_loaded(base_url: str, timeout: float = SNAPSHOT_TIMEOUT_SECONDS) -> list[dict[str, str]]:
    try:
        from fool import lmstudio_residency

        return [
            {"id": model_id, "label": model_id}
            for model_id in lmstudio_residency.loaded_models(base_url, timeout=timeout)
        ]
    except Exception as exc:  # noqa: BLE001
        logger.debug("LM Studio listesi okunamadi: %s", exc)
        return []


def _warming(kind: str) -> bool:
    """Bu kategoride ISITMA suruyor mu?

    Menude "yuklu degil" ile "su anda yukleniyor" ayni gorunmesin: ikincisinde
    bosaltma dugmesine basmak, bir saniye sonra geri gelecek bir seyi
    bosaltmak olur.
    """
    module = _module(f"fool.{kind}_warmup")
    if module is None:
        return False

    try:
        return str(module.status().get("status") or "") == "warming"
    except Exception:  # noqa: BLE001
        return False


def snapshot(timeout: float = SNAPSHOT_TIMEOUT_SECONDS) -> dict[str, Any]:
    """Uc kategorinin tamami: ne yuklu, ne secili, ne isiniyor."""
    cfg = _config()

    categories: dict[str, Any] = {
        "stt": {
            "label": KIND_LABELS["stt"],
            "loaded": _stt_loaded(),
            "selected": _selected_stt(cfg),
            "warming": _warming("stt"),
        },
        "tts": {
            "label": KIND_LABELS["tts"],
            "loaded": _tts_loaded(),
            "selected": _tts_entry_id(_selected_tts(cfg)),
            "warming": _warming("tts"),
        },
        "llm": {
            "label": KIND_LABELS["llm"],
            "loaded": _llm_loaded(_llm_base_url(cfg), timeout=timeout),
            "selected": _selected_llm(cfg),
            # LM Studio modeli KENDI yukluyor; burada bekleyen bir isitma is
            # parcacigi yok.
            "warming": False,
        },
    }

    return {
        **categories,
        "total": sum(len(row["loaded"]) for row in categories.values()),
    }


# ---------------------------------------------------------------------------
# Birak
# ---------------------------------------------------------------------------


def _unload_stt() -> list[str]:
    tt = _module("tools.transcription_tools")
    if tt is None or getattr(tt, "_local_model", None) is None:
        return []

    name = str(getattr(tt, "_local_model_name", "") or "local")
    try:
        tt._unload_local_model()
    except Exception as exc:  # noqa: BLE001
        logger.debug("whisper bosaltilamadi: %s", exc)
        return []

    _mark_cold("stt")
    _collect()
    return [name]


def _unload_tts(ident: str = "") -> list[str]:
    """Motorlari durdur. ``ident`` bossa HEPSI.

    ``stop_gracefully``: duz ``stop`` motorun kilidini almadan stdin'i
    kapatiyor ve o sirada suren bir sentezi ortasindan kesiyor -- kullanici
    konusurken tepsiden bosaltmaya basarsa cumle yarida susardi.
    """
    dropped: list[str] = []

    host = _module("fool.engine_host")
    if host is not None:
        try:
            targets = [name for name in host.running() if not ident or name == ident]
        except Exception as exc:  # noqa: BLE001
            logger.debug("motor listesi okunamadi: %s", exc)
            targets = []

        for name in targets:
            try:
                host.stop_gracefully(name)
                dropped.append(name)
            except Exception as exc:  # noqa: BLE001
                logger.debug("motor durdurulamadi (%s): %s", name, exc)

    tts_tool = _module("tools.tts_tool")
    if tts_tool is not None:
        for attr, provider in _IN_PROCESS_TTS:
            if ident and ident != provider:
                continue
            cache = getattr(tts_tool, attr, None)
            if cache:
                cache.clear()
                dropped.append(provider)

    if dropped:
        _mark_cold("tts")
        _collect()

    return dropped


def _unload_llm(ident: str = "", *, base_url: str = "", force: bool = True) -> list[str]:
    """LM Studio'daki sohbet modellerini birak. ``ident`` bossa HEPSI.

    ``force`` VARSAYILAN olarak acik: bu yol kullanicinin ACIK istegi
    (tepsiden bosalt / uygulamadan cik). Ureten modeli korumak
    ``enforce_single`` yolunun isi -- orada bosaltma kullanicinin degil kodun
    karari ve suren bir turu kesmemesi gerekiyor.
    """
    try:
        from fool import lmstudio_residency
    except Exception as exc:  # noqa: BLE001
        logger.debug("LM Studio modulu yuklenemedi: %s", exc)
        return []

    url = base_url or _llm_base_url()
    busy: set[str] = set()
    if not force:
        try:
            busy = lmstudio_residency.busy_models()
        except Exception:  # noqa: BLE001
            busy = set()

    dropped: list[str] = []
    for model_id in lmstudio_residency.loaded_models(url):
        if ident and model_id != ident:
            continue
        if model_id in busy:
            continue
        if lmstudio_residency.unload(model_id):
            dropped.append(model_id)

    return dropped


def unload(kind: str, ident: str = "") -> dict[str, Any]:
    """Bir kategoriyi (``all`` ile hepsini) birak.

    Donen sozluk kategori basina BIRAKILANLARI sayiyor: cagiran taraf
    "denedim" ile "gercekten birakildi"yi ayirt edebilsin. Tepsi menusu bunu
    dogrudan gosteriyor.
    """
    key = (kind or "").strip().lower()
    if key not in {*KINDS, "all"}:
        raise ValueError(f"bilinmeyen kategori: {kind}")

    unloaded: dict[str, list[str]] = {"stt": [], "tts": [], "llm": []}

    if key in ("stt", "all"):
        unloaded["stt"] = _unload_stt()
    if key in ("tts", "all"):
        unloaded["tts"] = _unload_tts(ident if key == "tts" else "")
    if key in ("llm", "all"):
        unloaded["llm"] = _unload_llm(ident if key == "llm" else "")

    total = sum(len(rows) for rows in unloaded.values())
    if total:
        logger.info(
            "[The Fool] bosaltildi: %s",
            ", ".join(f"{k}={'/'.join(v)}" for k, v in unloaded.items() if v),
        )

    return {"kind": key, "total": total, "unloaded": unloaded}


def unload_all() -> dict[str, Any]:
    """Her sey birakilsin -- uygulamadan cikarken cagriliyor.

    Ana surec olduruldugunde whisper ve motor SURECLERI zaten onunla birlikte
    gidiyor (masaustu arka ucu surec AGACI olarak olduruyor). LM Studio
    GITMIYOR: ayri bir uygulama ve yukledigi modeli kendiliginden birakmiyor
    -- yani cikista bosaltilmasi gereken tek sey aslinda o. Ucu birden yine de
    bosaltiliyor: bu yolun tek bir dogru anlami olsun ve arka ucun oldurulmesi
    gecikirse (ya da hic olmezse) kart yine de birakilsin.
    """
    return unload("all")


# ---------------------------------------------------------------------------
# Tek kalsin
# ---------------------------------------------------------------------------


def enforce_single(kinds: Iterable[str] = KINDS) -> dict[str, Any]:
    """Her kategoride SECILI olmayan her seyi birak.

    Kullanicinin kurali birebir: ayni anda tek STT, tek TTS, tek LLM. Secim
    degistigi ANDA cagriliyor (``fool/voice_models.py::select``) -- bosta
    bosaltmayi beklemek, o sure boyunca iki modelluk bellek tutmak demek.

    ``kinds`` DARALTILABILIYOR ve bu bir hiz karari: dil modeli kurali ``lms
    ps`` alt surecini calistiriyor (olculdu: birkac yuz milisaniye). Ses
    motoru secimi o bedeli odemek zorunda degil -- kullanici bir dugmeye basti
    ve cevabi bekliyor.

    UREYEN dil modeline DOKUNULMUYOR: burada bosaltma kullanicinin degil
    kodun karari ve suren bir turu ortasindan kesmek, ustune LM Studio'nun onu
    hemen yeniden yuklemesi demek -- 6,5 GB'lik bir yukle-bosalt dongusu.
    """
    wanted = {str(kind).strip().lower() for kind in kinds}
    cfg = _config()
    dropped: dict[str, list[str]] = {"stt": [], "tts": [], "llm": []}

    # STT: yuklu model SECILI modelden farkliysa gitsin. Yenisi bir sonraki
    # transkripsiyonda (ya da isitmada) yukleniyor.
    #
    # Model adi ``_normalize_local_model``den gecirilmiyor: yapilandirmada
    # gecersiz bir ad varsa yuklu model zaten varsayilan olur ve ikisi
    # tutmaz. O durumda bosaltmak dogru davranis -- yanlis adin bedeli bir
    # yeniden yukleme, sessizce iki model tutmak degil.
    selected_stt = _selected_stt(cfg)
    if "stt" in wanted and selected_stt:
        for row in _stt_loaded():
            if row["id"] != selected_stt:
                dropped["stt"] = _unload_stt()

    # TTS: secili motor DISINDAKI her motor.
    selected_tts = _tts_entry_id(_selected_tts(cfg))
    if "tts" in wanted and selected_tts:
        for row in _tts_loaded():
            if row["id"] != selected_tts:
                dropped["tts"].extend(_unload_tts(row["id"]))

    # LLM: mevcut kural aynen (secili olan ve UREYEN korunuyor).
    keep = _selected_llm(cfg)
    if "llm" in wanted and keep:
        try:
            from fool import lmstudio_residency

            dropped["llm"] = lmstudio_residency.enforce_single(_llm_base_url(cfg), keep)
        except Exception as exc:  # noqa: BLE001
            logger.debug("LM Studio tek-model kurali atlandi: %s", exc)

    return {"unloaded": dropped, "total": sum(len(rows) for rows in dropped.values())}


# ---------------------------------------------------------------------------
# Yardimcilar
# ---------------------------------------------------------------------------


def _mark_cold(kind: str) -> None:
    """Isitma durumunu ``cold`` yap (yuklenmemis modulu ITHAL ETMEDEN).

    Durum kendiliginden de duzeliyor (iki isitma modulu de gercekten yerlesik
    mi diye bakiyor), ama yalan soyleyen bir ara durum birakmak tepsi
    menusunun bosaltmadan hemen sonra "isiniyor" yazmasi olurdu.
    """
    module = _module(f"fool.{kind}_warmup")
    if module is None:
        return

    try:
        module.mark_cold()
    except Exception as exc:  # noqa: BLE001
        logger.debug("isitma durumu sifirlanamadi (%s): %s", kind, exc)


def _collect() -> None:
    """Bellegi GERCEKTEN birak.

    Sozlukten dusurmek yalnizca SON referansi dusuruyor; ctranslate2 ve torch
    bellegi nesne yok edildiginde birakiyor. CPython'da bu genellikle aninda
    oluyor ama dongusel referanslar toplayiciyi bekliyor -- ve burada beklenen
    sey gigabaytlarca VRAM.
    """
    import gc

    gc.collect()

    # Torch YUKLUYSE onbellegini de birak. Ithal EDILMIYOR: yuklu degilse
    # bosaltacak bir sey de yok.
    torch = _module("torch")
    if torch is None:
        return

    try:
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception as exc:  # noqa: BLE001
        logger.debug("torch cuda onbellegi bosaltilamadi: %s", exc)
