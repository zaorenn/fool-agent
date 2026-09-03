"""Uyandırma motorları: hangisi kurulu, hangisi ne dinleyebilir, nasıl kurulur.

Neden bu modül var
------------------
Üç motor var ve üçü de anahtarını FARKLI yerden alıyor -- bu ayrım hiçbir
yerde görünmüyordu ve doğrudan bir hataya yol açtı: ayarlar "hey fool"
gösterirken motor "hey hermes" dinliyordu (bkz.
``tools.wake_word.effective_wake_phrase``).

İkinci sebep kullanıcının kuralı: "benim bilgisayarımda senin manuel kurup
çalıştırdığın her bir ayrı şey uygulamadan doğrudan indirilebilir olmalı ki
yeni bilgisayarlarda da çalışsın aynı özellikler." Paket tanımları
``tools/lazy_deps.py`` içinde ZATEN vardı; eksik olan onları arayüze çıkaran
bir yüzeydi. Bu modül o yüzey.

Kurulum İŞ olarak yürüyor (arka plan iş parçacığı + yoklanabilir durum), çünkü
temiz bir makinede pip birkaç on saniye sürüyor ve bir RPC'yi o kadar bloke
etmek uygulamayı donmuş gösterirdi.
"""

from __future__ import annotations

import importlib.util
import logging
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EngineSpec:
    """Bir uyandırma motorunun DEĞİŞMEZ tanımı."""

    id: str
    label: str
    description: str
    #: ``tools/lazy_deps.py`` içindeki özellik anahtarı -- kurulum buradan.
    feature: str
    #: Kurulu olup olmadığını anlamak için içe aktarılabilirliği sınanan modül.
    module: str
    #: Kullanıcının YAZDIĞI ifadeyi gerçekten dinleyebiliyor mu?
    custom_phrase: bool
    #: Gerekiyorsa ortam değişkeni adı (yoksa motor seçilebilir olmamalı).
    env_key: str = ""


#: Sıra arayüzdeki sıra: önce kutudan çıkan, sonra özelleştirilebilen, en sonda
#: anahtar isteyen.
ENGINES: tuple[EngineSpec, ...] = (
    EngineSpec(
        id="openwakeword",
        label="Built-in",
        description="Ready-made phrases. Free, works offline, no setup.",
        feature="wake.openwakeword",
        module="openwakeword",
        custom_phrase=False,
    ),
    EngineSpec(
        id="sherpa",
        label="Custom phrase",
        description="Type any phrase and it is recognised - no training.",
        feature="wake.sherpa",
        module="sherpa_onnx",
        custom_phrase=True,
    ),
    EngineSpec(
        id="porcupine",
        label="Porcupine",
        description="Picovoice engine. Needs a free access key.",
        feature="wake.porcupine",
        module="pvporcupine",
        custom_phrase=False,
        env_key="PORCUPINE_ACCESS_KEY",
    ),
)

_BY_ID = {spec.id: spec for spec in ENGINES}


def spec(engine_id: object) -> EngineSpec | None:
    return _BY_ID.get(str(engine_id or "").strip().lower())


def _installed(spec_: EngineSpec) -> bool:
    """Motorun TÜM paketleri yerinde mi.

    Ölçülen hata
    ------------
    Önce yalnızca ANA modüle bakıyordu (``sherpa_onnx`` içe aktarılabiliyor
    mu). Motor "kurulu" görünüyor, seçilebiliyor ve arma sırasında bir alt
    bağımlılıkta düşüyordu::

        Wake word: "emily wake up" — off — No module named 'pypinyin'

    Kurulum düğmesi de çıkmıyordu, çünkü motor zaten kurulu sayılıyordu --
    kullanıcının kendi başına çıkamayacağı bir çıkmaz.

    ``lazy_deps`` zaten paket listesinin tek sahibi ve eksikleri sayabiliyor;
    doğru soru "ana modül var mı" değil, "bu özelliğin eksiği var mı".
    """
    try:
        from tools import lazy_deps

        return not lazy_deps.feature_missing(spec_.feature)
    except Exception:
        # Bozuk bir yarim kurulum sondayi attirabiliyor; o durumda motor
        # KURULU DEGIL saymak dogrusu -- secilebilir yapmak, kullaniciyi
        # calismayan bir motora goturmek olurdu.
        logger.debug("wake engine probe failed: %s", spec_.feature, exc_info=True)
        return False


def catalog(cfg: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Motorların CANLI durumu.

    ``usable`` ile ``installed`` bilerek AYRI: Porcupine'in paketi kurulu olsa
    bile anahtarı yoksa motor çalışmıyor. Kullanıcının kalıcı kuralı --
    "kurulu olmayan bir motor seçilebilir olmamalı" -- ``usable`` üzerinden
    uygulanıyor, ``installed`` üzerinden değil.
    """
    from tools.wake_word import _provider, load_wake_word_config, openwakeword_phrases

    cfg = cfg if cfg is not None else load_wake_word_config()
    active = _provider(cfg)

    items: list[dict[str, Any]] = []

    for spec_ in ENGINES:
        installed = _installed(spec_)
        blocked = ""

        if not installed:
            blocked = "not installed"
        elif spec_.env_key and not (os.getenv(spec_.env_key) or "").strip():
            blocked = spec_.env_key + " is not set"

        items.append({
            "id": spec_.id,
            "label": spec_.label,
            "description": spec_.description,
            "installed": installed,
            "usable": not blocked,
            "blocked_reason": blocked,
            "custom_phrase": spec_.custom_phrase,
            "active": spec_.id == active,
            "env_key": spec_.env_key,
            # Sabit dagarcikli motorun SUNDUGU ifadeler. Bos liste = motor
            # yazilan ifadeyi dinleyebiliyor demek.
            "phrases": openwakeword_phrases() if spec_.id == "openwakeword" else [],
        })

    return items


# --- Kurulum isleri --------------------------------------------------------


@dataclass
class InstallJob:
    id: str
    engine_id: str
    state: Literal["running", "done", "failed"] = "running"
    stage: str = "starting"
    detail: str = ""
    error: str = ""
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None

    def snapshot(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "engine_id": self.engine_id,
            "state": self.state,
            "stage": self.stage,
            "detail": self.detail,
            "error": self.error,
            "elapsed": round((self.finished_at or time.time()) - self.started_at, 1),
        }


_JOBS: dict[str, InstallJob] = {}
_ACTIVE_BY_ENGINE: dict[str, str] = {}
_LOCK = threading.Lock()


def get_job(job_id: object) -> InstallJob | None:
    with _LOCK:
        return _JOBS.get(str(job_id or ""))


def _run(job: InstallJob, spec_: EngineSpec) -> None:
    try:
        from tools import lazy_deps

        job.stage = "installing"
        job.detail = "Installing " + spec_.label + "..."
        # ``prompt=False``: burada TTY yok ve bir onay istemi sessizce
        # takilirdi.
        lazy_deps.ensure(spec_.feature, prompt=False)

        # sherpa AYRICA bir model indiriyor (~13 MB, tek seferlik). Bunu
        # kuruluma cekmek bilincli: birinci uyandirma denemesinde indirmek,
        # kullanicinin "kurdum ama calismiyor" diye gorecegi sessiz bir
        # bekleme olurdu.
        if spec_.id == "sherpa":
            job.stage = "model"
            job.detail = "Downloading the recognition model..."

            from tools.wake_word import _ensure_sherpa_model

            _ensure_sherpa_model()

        job.stage = "done"
        job.detail = spec_.label + " is ready"
        job.state = "done"
    except Exception as exc:
        logger.warning("wake engine install failed (%s): %s", spec_.id, exc)
        job.state = "failed"
        job.stage = "failed"
        job.error = str(exc)
    finally:
        job.finished_at = time.time()

        with _LOCK:
            if _ACTIVE_BY_ENGINE.get(spec_.id) == job.id:
                _ACTIVE_BY_ENGINE.pop(spec_.id, None)


def start_install(engine_id: object) -> dict[str, Any]:
    """Motoru arka planda kur; iş kimliğini döndür."""
    spec_ = spec(engine_id)

    if spec_ is None:
        raise ValueError("unknown wake engine: " + str(engine_id))

    with _LOCK:
        existing_id = _ACTIVE_BY_ENGINE.get(spec_.id)
        existing = _JOBS.get(existing_id or "")

        # Süren bir iş varsa YENİSİ başlatılmıyor: iki pip aynı hedefe yazarsa
        # ortam yarım kalmış bir kurulumla bozulur.
        if existing is not None and existing.state == "running":
            return existing.snapshot()

        job = InstallJob(id=uuid.uuid4().hex[:12], engine_id=spec_.id)
        _JOBS[job.id] = job
        _ACTIVE_BY_ENGINE[spec_.id] = job.id

    threading.Thread(
        target=_run, args=(job, spec_), daemon=True, name="fool-wake-install-" + job.id
    ).start()

    return job.snapshot()
