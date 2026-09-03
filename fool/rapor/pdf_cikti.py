"""
DOCX'ten PDF -- kurulu bir dönüştürücüyle, yoksa AÇIKÇA yok diyerek.

Neden kendi PDF yazıcımız yok
-----------------------------
Resmî raporun asıl biçimi ``.docx``: müfettiş onu açıyor, düzeltiyor,
imzalıyor. PDF ondan türetilen bir çıktı. 10-15 sayfalık bir belgede Word'ün
sayfalamasını, tablo kırılmalarını ve satır sonlarını elle yazılmış bir PDF
üreticisiyle birebir taklit etmek gerçekçi değil; ufak bir fark bile sayfa
numaralarını ("1/12") kaydırır ve yönergeye aykırı bir belge çıkarır.

Onun yerine belgeyi zaten doğru sayfalayan bir program çağrılıyor.

Neden yoksa "yok" deniyor
-------------------------
Bu depoda F5-TTS'in bıraktığı ders var: arayüzde çalışıyormuş gibi duran ama
hiç ses üretmeyen bir motor, kullanıcıya hiç sunulmamasından kötüydü.
Dönüştürücü bulunamazsa burada da PDF "üretiliyormuş" gibi yapılmıyor --
hangi programların arandığı ve nasıl kurulacağı söyleniyor.

Zone A: upstream bu dosyayı bilmiyor.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

#: LibreOffice'in Windows'taki olağan yerleri. ``PATH``te olmayabiliyor:
#: kurulum ``soffice.exe``yi PATH'e eklemiyor.
_WINDOWS_ADAYLARI = (
    r"C:\Program Files\LibreOffice\program\soffice.exe",
    r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
)


def donusturucu_bul() -> str | None:
    """Kurulu bir DOCX->PDF dönüştürücüsünün yolu, yoksa ``None``."""
    for ad in ("soffice", "libreoffice"):
        bulunan = shutil.which(ad)
        if bulunan:
            return bulunan

    for aday in _WINDOWS_ADAYLARI:
        if Path(aday).exists():
            return aday

    return None


@dataclass
class PdfSonucu:
    """Dönüştürme denemesinin sonucu."""

    basarili: bool
    yol: Path | None = None
    gerekce: str = ""
    donusturucu: str = ""


def pdf_uret(docx: str | Path, hedef_klasor: str | Path | None = None) -> PdfSonucu:
    """``.docx``ten PDF üret.

    ``hedef_klasor`` verilmezse PDF belgenin yanına yazılıyor.
    """
    docx = Path(docx)

    if not docx.exists():
        return PdfSonucu(False, gerekce=f"belge bulunamadı: {docx}")

    arac = donusturucu_bul()

    if arac is None:
        return PdfSonucu(
            False,
            gerekce=(
                "Bu makinede DOCX'i PDF'e çevirecek bir program yok. "
                "LibreOffice kurulunca (soffice) çalışıyor. "
                "Rapor .docx olarak hazır; PDF üretilmedi."
            ),
        )

    klasor = Path(hedef_klasor) if hedef_klasor else docx.parent
    klasor.mkdir(parents=True, exist_ok=True)

    # ``-env:UserInstallation`` AYRI bir profil veriyor.
    #
    # Kullanicinin acik bir LibreOffice penceresi varsa headless cagri onun
    # profiline baglanmaya calisip sessizce hicbir sey uretmeden donuyor.
    # Ayri profil bu carpismayi bastan kesiyor.
    profil = (klasor / ".lo-profil").resolve().as_uri()

    sonuc = subprocess.run(
        [
            arac,
            f"-env:UserInstallation={profil}",
            "--headless",
            "--norestore",
            "--convert-to",
            "pdf",
            "--outdir",
            str(klasor),
            str(docx),
        ],
        capture_output=True,
        # stdin ACIKCA veriliyor: Windows'ta bos stdin ile subprocess asili
        # kaliyor (depo genelinde yasanmis bir tuzak).
        stdin=subprocess.DEVNULL,
        check=False,
        timeout=180,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )

    pdf = klasor / f"{docx.stem}.pdf"

    if not pdf.exists():
        hata = sonuc.stderr.decode("utf-8", "replace")[:300]
        return PdfSonucu(
            False,
            gerekce=f"dönüştürücü PDF üretmedi (çıkış {sonuc.returncode}): {hata}",
            donusturucu=arac,
        )

    return PdfSonucu(True, pdf, donusturucu=arac)
