"""Uzak platformlarda dosya üretimi — diski okutmadan.

Neden ayrı bir araç
-------------------
WhatsApp'tan "bana bunun PDF'ini çıkar" demek bugüne kadar imkânsızdı. Dosya
yazmak ``file`` takımını gerektiriyor, o takım da ``read_file`` ve
``search_files`` getiriyor. Yani tek bir dosya ÜRETEBİLMEK için bota mesaj
yazabilen herkese TÜM DİSKİ okutmak gerekiyordu -- aile üyeleri, numarayı
bilen herhangi biri.

Bu modül düğümü çözüyor: yalnızca yazan, okuma yetkisi olmayan, tek bir çıktı
klasörüne kilitli bir araç. Kendi takımında (``output_file``) ve o takım uzak
platformların güvenli varsayılanında.

Savunma iki katmanlı ve bu bilinçli
-----------------------------------
1. **Ad doğrulaması** (``safe_filename``): ayırıcı yok, ``..`` yok, sürücü
   harfi yok, NTFS alternatif veri akışı yok, Windows aygıt adı yok,
   çalıştırılabilir uzantı yok.
2. **Yol denetimi** (``write_output``): yazılacak yol çözümlendikten SONRA
   gerçekten çıktı klasörünün içinde mi diye bakılıyor.

Tek hatta güvenmek, o hattaki bir boşluğun doğrudan disk erişimine dönüşmesi
demek. Bu araç uzak birinin elinde; sınır iki kez kontrol ediliyor.
"""

from __future__ import annotations

import base64
import binascii
import os
from pathlib import Path
from typing import Any

#: Tek bir çıktı için üst sınır. Mesajlaşma platformlarının kendi ek dosyası
#: sınırları bunun altında; asıl amaç diski doldurmayı engellemek.
MAX_OUTPUT_BYTES = 25 * 1024 * 1024

#: Windows'ta bu adlar dosya değil AYGIT açar. Yazma sessizce hiçbir yere
#: gider ya da beklenmedik bir aygıta -- ikisi de kötü.
_WINDOWS_DEVICES = frozenset(
    {"con", "prn", "aux", "nul"}
    | {f"com{i}" for i in range(1, 10)}
    | {f"lpt{i}" for i in range(1, 10)}
)

#: Uzak biri makineye çalıştırılabilir bırakamaz. Aracın işi belge üretmek.
_BLOCKED_SUFFIXES = frozenset({
    ".appref-ms", ".bat", ".cmd", ".com", ".cpl", ".dll", ".exe", ".hta",
    ".js", ".jse", ".lnk", ".msc", ".msi", ".pif", ".ps1", ".psm1", ".reg",
    ".scr", ".sh", ".vbe", ".vbs", ".wsf", ".wsh",
})

_MAX_NAME_LEN = 120

# Yalnizca ADIN kendisi. Karakter kumesi BILEREK duz bir kume olarak
# yaziliyor, regex sinifi olarak degil: bir kacis karakterinin yanlis
# yorumlanmasi (ters bolunun sinifta erimesi gibi) tam da bu sinirin
# sessizce acilmasi demek olurdu -- ilk yazimda tam bu oldu.
_FORBIDDEN_CHARS = frozenset(chr(92) + '/:*?"<>|') | {chr(c) for c in range(32)}


def safe_filename(name: Any) -> str:
    """Kullanıcıdan gelen adı doğrula; kabul edilebilir hâlini döndür.

    Temizlemek YERİNE reddediyor. Sessizce düzeltilen bir ad, kullanıcının
    istediğinden başka bir dosya üretir ve modelin ne yazdığını bilmemesine
    yol açar; ayrıca temizleme kuralları kaçış açıklarının klasik kaynağıdır.
    """
    if not isinstance(name, str):
        raise ValueError("dosya adi metin olmali")

    candidate = name.strip()
    if not candidate:
        raise ValueError("dosya adi bos olamaz")
    if len(candidate) > _MAX_NAME_LEN:
        raise ValueError(f"dosya adi cok uzun (en fazla {_MAX_NAME_LEN} karakter)")
    if _FORBIDDEN_CHARS & set(candidate):
        raise ValueError(
            "dosya adi klasor ayirici, iki nokta ya da kontrol karakteri iceremez"
        )
    if set(candidate) <= {"."}:
        raise ValueError("gecersiz dosya adi")
    # ``..`` bir ayirici olmadan da tehlikeli sayilir: alt katmanlarin
    # birlestirdigi bir yolda anlam kazanabiliyor.
    if ".." in candidate:
        raise ValueError("dosya adi '..' iceremez")

    stem = candidate.split(".", 1)[0].lower()
    if stem in _WINDOWS_DEVICES:
        raise ValueError(f"'{candidate}' bir aygit adi, dosya adi degil")

    suffix = os.path.splitext(candidate)[1].lower()
    if suffix in _BLOCKED_SUFFIXES:
        raise ValueError(f"'{suffix}' uretilemez -- bu arac belge uretir")

    return candidate


def output_dir(session_id: str | None = None) -> Path:
    """Çıktıların yazıldığı klasör.

    ``FOOL_HOME`` altında, oturum başına ayrı. Ayrı tutulması, bir oturumun
    ürettiği dosyanın başka bir oturumda adıyla tahmin edilerek istenmesini
    engelliyor.
    """
    from fool_cli.config import get_hermes_home

    base = Path(get_hermes_home()) / "outputs"
    if session_id:
        base = base / safe_filename(str(session_id))
    base.mkdir(parents=True, exist_ok=True)
    return base


def _unique_path(directory: Path, name: str) -> Path:
    """Var olanın ÜZERİNE yazma.

    Üzerine yazmak, önceki turda üretilen dosyayı sessizce yok etmekti:
    kullanıcı "az önceki raporu gönder" dediğinde eline yenisi geçerdi.
    """
    target = directory / name
    if not target.exists():
        return target

    stem, suffix = os.path.splitext(name)
    for index in range(2, 1000):
        candidate = directory / f"{stem}-{index}{suffix}"
        if not candidate.exists():
            return candidate
    raise ValueError("ayni adla cok fazla dosya var")


def write_output(
    filename: str,
    text: str | None = None,
    base64_content: str | None = None,
    session_id: str | None = None,
) -> dict:
    """Çıktı klasörüne tek bir dosya yaz. Okuma yok, başka yol yok."""
    name = safe_filename(filename)

    if text is None and base64_content is None:
        raise ValueError("icerik verilmedi: 'text' ya da 'base64_content' gerekli")
    if text is not None and base64_content is not None:
        raise ValueError("'text' ve 'base64_content' birlikte verilemez")

    if text is not None:
        payload = text.encode("utf-8")
    else:
        try:
            payload = base64.b64decode(base64_content or "", validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError(f"base64 cozulemedi: {exc}") from exc

    if len(payload) > MAX_OUTPUT_BYTES:
        raise ValueError(
            f"cikti cok buyuk ({len(payload)} bayt, sinir {MAX_OUTPUT_BYTES})"
        )

    directory = output_dir(session_id)
    target = _unique_path(directory, name)

    # Ikinci savunma hatti: ad dogrulamasindan gecmis olsa bile, YAZILACAK
    # yol gercekten cikti klasorunun icinde mi? Tek hatta guvenmek, o hattaki
    # bir bosluğun dogrudan disk erisimine donusmesi demek.
    resolved_dir = directory.resolve()
    resolved_target = target.resolve()
    if not resolved_target.is_relative_to(resolved_dir):
        raise ValueError("cozumlenen yol cikti klasorunun disinda")

    resolved_target.write_bytes(payload)

    return {
        "ok": True,
        "path": str(resolved_target),
        "filename": resolved_target.name,
        "bytes": len(payload),
    }


WRITE_OUTPUT_SCHEMA = {
    "type": "function",
    "function": {
        "name": "write_output",
        "description": (
            "Write a file (report, PDF, CSV, image, …) into this session's "
            "output folder so it can be sent back to the user. Write-only: "
            "it cannot read or list anything on the machine. Use base64_content "
            "for binary files and text for plain text."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "File name only — no folders, no path separators.",
                },
                "text": {
                    "type": "string",
                    "description": "UTF-8 text content. Mutually exclusive with base64_content.",
                },
                "base64_content": {
                    "type": "string",
                    "description": "Base64-encoded bytes for binary files.",
                },
            },
            "required": ["filename"],
        },
    },
}


# Kayit dosyanin SONUNDA: registry ithali modul yuklenirken calisiyor ve
# yukaridaki tanimlarin hazir olmasi gerekiyor.
try:
    from tools.registry import registry

    registry.register(
        name="write_output",
        toolset="output_file",
        schema=WRITE_OUTPUT_SCHEMA,
        handler=lambda args, **kw: write_output(
            filename=args.get("filename", ""),
            text=args.get("text"),
            base64_content=args.get("base64_content"),
            session_id=kw.get("session_id"),
        ),
        emoji="📤",
    )
except Exception:  # pragma: no cover - kayit defteri yoksa modul yine kullanilir
    pass
