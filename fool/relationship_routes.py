"""İlişki durumunun arayüze açıldığı uç.

İstenen: "bu kız arkadaş modu için de ayrı bir bar hazırla, arayüzde görünen
ilişki durumu neye kızgın, ne moralini bozuyor, neye trip atıyor görülsün ve
kullanıcı onunla konuşup gönlünü alabilsin."

Neden modelin dediğine değil DEFTERE bakıyor
--------------------------------------------
Ekrandaki barın işi, kullanıcının göremediği bir durumu göstermek. O durum
``memories/recall.db`` içinde duruyor ve ``relationship()`` aracıyla değişiyor.
Barı modelin cevabından çıkarmak (ör. "kızgın görünüyor musun") aynı bilgiyi
İKİNCİ bir yerden tahmin etmek olurdu ve ikisi ayrıştığı anda ekran yalan
söylerdi.

Neden salt okunur
-----------------
Ekranda "bu derdi kapat" düğmesi YOK. Kullanıcının istediği şey gönlünün
alınabilmesi -- ama bunun yolu konuşmak. Tek tıkla kapatılabilen bir kırgınlık,
kırgınlık değil; bar o zaman yalnızca kendini sıfırlayan bir süs olurdu.
Dertleri kapatan tek yol ``relationship()`` aracı, yani gerçekten konuşmak.

Neden ``touch_seen`` ÇAĞIRMIYOR
-------------------------------
Sağlayıcının kendi ``system_prompt_block``u "görüldü" damgası atıyor; zaman
farkındalığı (bkz. ``fool/time_context.py``) o damgadan besleniyor. Bar saniyede
bir yoklanıyor -- oradan geçse damga sürekli tazelenir ve "dün gece iyi geceler
demeden gittin" hiçbir zaman gerçekleşmezdi. Bu yüzden burası sağlayıcıyı
kurmuyor, defteri doğrudan okuyor.

Zone A: upstream bu dosyayı bilmiyor.
"""

from __future__ import annotations

import os
import time
from typing import Any

from fastapi import APIRouter

router = APIRouter()


def _db_path() -> str:
    from pathlib import Path

    from fool_constants import get_hermes_home

    return str(Path(get_hermes_home()) / "memories" / "recall.db")


def _enabled() -> bool:
    """``memory.recall.relationship`` açık mı -- yani bu profil bir persona mı.

    Sıradan ajanın ilişki durumu yok; barın orada hiç görünmemesi gerekiyor.
    """
    try:
        # Salt okunur varyant: bu uç saniyede bir yoklanıyor ve hiçbir şeyi
        # değiştirmiyor, savunma amaçlı deepcopy'ye gerek yok.
        from fool_cli.config import load_config_readonly

        memory = load_config_readonly().get("memory")

        if not isinstance(memory, dict):
            return False

        recall = memory.get("recall")

        return bool(isinstance(recall, dict) and recall.get("relationship"))
    except Exception:  # noqa: BLE001
        return False


def snapshot() -> dict[str, Any]:
    """Defterin o anki hâli. Yazmıyor, damga atmıyor."""
    if not _enabled():
        return {"enabled": False}

    path = _db_path()

    if not os.path.exists(path):
        # Henüz hiç konuşulmamış: bar başlangıç hâlinde görünüyor.
        return _render(None, met=False)

    try:
        import json
        import sqlite3

        connection = sqlite3.connect("file:" + path.replace("?", "%3f") + "?mode=ro", uri=True)

        try:
            rows = dict(
                connection.execute(
                    "SELECT key, value FROM meta WHERE key IN ('relationship', 'last_seen')"
                ).fetchall()
            )
        finally:
            connection.close()
    except Exception:  # noqa: BLE001
        return _render(None, met=False)

    payload = None
    raw = rows.get("relationship")

    if raw:
        try:
            candidate = json.loads(raw)
            payload = candidate if isinstance(candidate, dict) else None
        except ValueError:
            payload = None

    return _render(payload, met=bool(rows.get("last_seen")))


def _render(payload: dict | None, *, met: bool) -> dict[str, Any]:
    from fool import relationship as relationship_module

    state = relationship_module.from_dict(payload)
    # Ekranda görünen sıcaklık, promptun göreceğiyle AYNI olmalı: sağlayıcı da
    # okumadan önce çürütüyor. Çürütmeden göstermek, uzun bir aradan sonra
    # barı olduğundan soğuk (ya da sıcak) gösterirdi.
    state.decay(time.time())
    name, _description = state.stance()

    return {
        "enabled": True,
        # Bu kişiyle DAHA ÖNCE konuşulmuş mu. Tanışma selamının kapısı bu
        # (bkz. ``apps/desktop/src/fool/persona-greeting.ts``): sağlayıcı ilk
        # turun sistem promptunu kurarken "görüldü" damgasını atıyor, yani
        # selamın kendi turu bile kapıyı kapatıyor ve istemcinin kalıcı olarak
        # hatırlaması gereken bir şey kalmıyor.
        "met": met,
        # Aranızda hiçbir şey geçmediyse bar "durum" iddia etmiyor.
        "started": bool(state.updated_at or state.grievances),
        "warmth": round(state.warmth, 1),
        "stance": name,
        "label": relationship_module.STANCE_LABELS[name][0],
        "summary": relationship_module.STANCE_LABELS[name][1],
        "grievances": [
            {"text": item.text, "since": item.created_at, "weight": round(item.weight, 1)}
            for item in sorted(state.open_grievances(), key=lambda g: -g.weight)
        ],
    }


@router.get("/api/fool/relationship")
async def get_relationship() -> dict[str, Any]:
    return snapshot()
