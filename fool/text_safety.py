"""İşletim sisteminden gelen metin UTF-8 OLMAYABİLİR.

Ölçülen çöküş
-------------
``agent/system_prompt.py`` saat dilimi kısaltmasını ``now.strftime("%Z")`` ile
alıyor. Windows bunu C çalışma zamanından, sistemin ANSI kod sayfasında
veriyor; bu makinede cp1254 ve saat diliminin adı ``Türkiye Standart Saati``.
Python o baytları çözemediğinde ``surrogateescape`` uyguluyor ve dizede
``\\udcfc`` gibi YARIM vekil karakterler kalıyor. Böyle bir dize UTF-8'e
kodlanamıyor:

    UnicodeEncodeError: 'utf-8' codec can't encode character '\\udcfc'
    in position 1: surrogates not allowed

Bedeli ölçüldü ve büyüktü: patlayan yer sistem promptunun kurulduğu satır.

    agent/conversation_loop.py::_restore_or_build_system_prompt
      -> run_agent.py::_build_system_prompt
        -> agent/system_prompt.py::build_system_prompt_parts   <-- burada

Yani ajan sistem promptunu HİÇ kuramıyor, tur hiç başlamıyor. Kullanıcının
"cevap bile vermiyordu" dediği şeyin altında bu vardı; ağ geçidinin çökme
kaydında altı kez görünüyor.

Neden düşürmek yerine KURTARMAK
-------------------------------
Vekiller kayıp bilgi değil: ``surrogateescape`` orijinal baytları dizenin
içinde saklıyor. Geri çıkarıp sistemin gerçek kod sayfasıyla çözünce
``Türkiye Standart Saati`` aynen geliyor. Sadece silmek, Türkçe bir kurulumda
saat diliminin adını sessizce yok etmek olurdu.

Kurtarılamayan bayt DÜŞÜRÜLÜYOR -- promptun kurulamamasındansa eksik bir
kısaltma kabul edilir. Saat dilimi bilgisi zaten ayrıca ``%z`` ofsetiyle
(``UTC+03:00``) taşınıyor ve o saf ASCII.

Zone A: upstream bu dosyayı bilmiyor.
"""

from __future__ import annotations

import locale


def has_surrogates(value: str) -> bool:
    """Dizede yarım vekil var mı? (UTF-8'e kodlanamaz demek.)"""
    return any("\ud800" <= char <= "\udfff" for char in value)


def _candidate_encodings() -> tuple[str, ...]:
    """Denenecek kod sayfaları -- en olasıdan başlayarak.

    Sistemin kendi tercihi başta: baytlar ORADAN geldi. ``mbcs`` Windows'un
    geçerli ANSI kod sayfası için takma ad; POSIX'te yok, o yüzden hata
    yutuluyor.
    """
    seen: list[str] = []
    for name in (locale.getpreferredencoding(False), "mbcs", "cp1252", "latin-1"):
        cleaned = (name or "").strip()
        if cleaned and cleaned.lower() not in {item.lower() for item in seen}:
            seen.append(cleaned)
    return tuple(seen)


def safe_os_text(value: object) -> str:
    """İşletim sisteminden gelen bir dizeyi UTF-8'e kodlanabilir hâle getir.

    Vekil taşımayan dize DEĞİŞTİRİLMEDEN dönüyor -- bu sıcak yol ve
    kopyalamaya gerek yok.
    """
    if not isinstance(value, str) or not value:
        return "" if value is None else str(value or "")

    if not has_surrogates(value):
        return value

    # ``surrogateescape`` orijinal baytlari dizenin icinde tutuyor; geri cikar.
    raw = value.encode("utf-8", "surrogateescape")

    for encoding in _candidate_encodings():
        try:
            recovered = raw.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue
        if not has_surrogates(recovered):
            return recovered

    # Kurtarilamadi: kodlanabilir olani birak. Promptun HIC kurulamamasindansa
    # eksik bir kisaltma kabul edilir.
    return raw.decode("utf-8", "replace")
