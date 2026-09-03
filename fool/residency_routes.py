"""Bellek yerlesimi uclari: ne yuklu, birak, tek kalsin.

Neden ayri bir dosya
--------------------
``fool/voice_routes.py`` SES kataloguna bakiyor; buradaki uclar dil modelini
de kapsiyor (LM Studio'da yuklu olan sohbet modeli de karti yiyor). Ikisini
ayni dosyada tutmak, ses panelinin dosyasina bir gun "modeli degistir" ucu
eklemenin davetiyesi olurdu.

Yonlendirici ``voice_routes``a takiliyor (tek satir), yani ``web_server.py``
tarafinda YENI bir dikis yok -- var olan voice-routes dikisinin iki satiri
ikisini birden getiriyor.

Uclar
-----
``GET  /api/fool/runtime/residency``  -- kategori basina yuklu/secili/isiniyor
``POST /api/fool/runtime/unload``     -- ``{kind, id}`` ile birak
``POST /api/fool/runtime/enforce``    -- secili olmayan her seyi birak

Kim cagiriyor
-------------
Sistem tepsisi menusu (``apps/desktop/electron/tray-runtime.ts``). Menu her
acilista ``residency``yi okuyor ve satirlara basildiginda ``unload``a
gidiyor; uygulamadan cikarken ``{"kind": "all"}`` cagriliyor.

Zone A: upstream bu dosyayi bilmiyor.
"""

from __future__ import annotations

import asyncio
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from fool import residency

router = APIRouter()


class UnloadBody(BaseModel):
    #: ``all`` = uc kategori birden (cikista kullanilan yol).
    kind: Literal["stt", "tts", "llm", "all"] = "all"
    #: Bos = kategorideki HER SEY. Dolu = yalnizca bu kimlik.
    id: str = ""


@router.get("/api/fool/runtime/residency")
async def runtime_residency() -> dict[str, Any]:
    """IS PARCACIGINDA: LM Studio sondasi bir HTTP istegi.

    ``async def`` icinden senkron cagirmak olay dongusunu o istek boyunca
    durdurur -- ve o dongu ayni anda konusan ``speak-stream`` soketine PCM
    gonderiyor. Yani tepsi menusunu acmak, calmakta olan konusmayi kesecekti
    (ayni hata ``voice_catalog``da bir kez yasandi ve orada da is parcacigina
    tasinarak cozuldu).
    """
    return await asyncio.to_thread(residency.snapshot)


@router.post("/api/fool/runtime/unload")
async def runtime_unload(body: UnloadBody) -> dict[str, Any]:
    """IS PARCACIGINDA: ``lms unload`` bir alt surec, motor durdurmak bir
    ``process.wait``.
    """
    try:
        return await asyncio.to_thread(residency.unload, body.kind, body.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/fool/runtime/enforce")
async def runtime_enforce() -> dict[str, Any]:
    """Her kategoride SECILI olmayan her seyi birak."""
    return await asyncio.to_thread(residency.enforce_single)
