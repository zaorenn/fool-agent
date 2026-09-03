"""
Kaynak belge okuma -- ve okunanın GÜVENİLİR olup olmadığının ölçülmesi.

Neden kalite denetimi bu kadar önemli
-------------------------------------
Kullanıcının elindeki 72 sayfalık "DSİ Disiplin Soruşturma Rehberi" PDF'i
ölçüldü: metin katmanında **küçük "i" harfi hiç yok**. İki bağımsız çıkarıcı
aynı sonucu veriyor:

    pdftotext -enc UTF-8 : "Memur d s pl n rej m n n genel çerçeves ..."
    pdfminer.six         : "Memur dspln rejmnn genel çerçeves ..."

PDF'in 404 font eşlemesi tarandı: 'i' hedefli eşleşme yalnızca 69 tane, oysa
'e' 292, 'a' 284, noktasız 'ı' 173. Türkçede 'i' en sık harflerden biri
olduğu için bu, fontta eşlemenin GERÇEKTEN olmadığı anlamına geliyor --
pdftotext'in koyduğu boşluklar glif konumundan geliyor, kayıp harften değil.

Bunu modele vermek "disiplin" yerine "dspln" öğretmek olurdu; üretilen resmî
rapor da sessizce yanlış çıkardı. Devlet işinde sessiz yanlış, görünür hatadan
çok daha pahalı. O yüzden okuma tek başına yeterli sayılmıyor: her belge bir
kalite ölçümünden geçiyor ve şüpheli olan modele SOKULMUYOR.

Harf ise KAYIP DEĞİLMİŞ
-----------------------
Glif sayfada duruyor, yalnızca Unicode karşılığı bildirilmemiş. ``pdf_kurtar``
belgeyi karakter karakter okuyup bu glifleri geri koyuyor; ölçüldü, 72 sayfada
17.190 glif (%7,9 -- Türkçede 'i' harfinin beklenen sıklığı) geri geldi ve
metin kalite denetiminden geçer hâle geldi.

Bu yüzden sıra şöyle: önce hızlı ``pdftotext``, metin denetimden geçmezse
kurtarma, sonra denetim TEKRAR. Kurtarma da işe yaramazsa belge yine
reddediliyor -- "düzeltilmiş gibi" göstermek en kötüsü olurdu.

Bağlam sınırı
-------------
Modelin penceresi 64-128 bin token. 73 sayfalık rehber tek başına ~41 bin
token; yanına 10 dilekçe ve yarım rapor eklenince hiçbir şey sığmıyor. Bu
yüzden belgeler bütün olarak değil, ``parcala`` ile sınırlı parçalar hâlinde
veriliyor ve her parça sayfa numarasını taşıyor -- rapora atıf yapılabilsin.

Zone A: upstream bu dosyayı bilmiyor.
"""

from __future__ import annotations

import html
import re
import shutil
import subprocess
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from . import pdf_kurtar
from .turkce import kucuk

#: Türkçe düzyazıda 'i' harfinin harfler içindeki payı ~%8. Bu eşiğin altı,
#: metnin kendisi değil ÇIKARMANIN bozuk olduğu anlamına geliyor.
I_ORANI_ESIGI = 0.02

#: Ölçüm için en az bu kadar harf gerekli; kısa metinde oran anlamsız.
ASGARI_HARF = 400

#: "d s pl n" biçimi: tek harflik parçacıkların payı bu eşiği geçerse
#: çıkarma harfleri boşluğa çevirmiş demektir.
TEK_HARF_ESIGI = 0.20


@dataclass
class Kalite:
    """Bir belgeden çıkarılan metnin güvenilirliği."""

    guvenilir: bool
    gerekce: str = ""
    i_orani: float = 0.0
    tek_harf_orani: float = 0.0
    harf_sayisi: int = 0

    def __bool__(self) -> bool:
        return self.guvenilir


def kalite_olc(metin: str) -> Kalite:
    """Çıkarılan metin modele verilebilir mi?

    İki ayrı bozulma biçimi yakalanıyor, çünkü iki çıkarıcı aynı kusuru
    farklı gösteriyor: pdfminer harfi ATIYOR ("dspln"), pdftotext yerine
    BOŞLUK koyuyor ("d s pl n").
    """
    harfler = [k for k in metin if k.isalpha()]
    harf_sayisi = len(harfler)

    if harf_sayisi < ASGARI_HARF:
        # Kisa metinde oran guvenilir degil; okundugu gibi kabul ediliyor.
        return Kalite(True, "olcum icin kisa metin", harf_sayisi=harf_sayisi)

    i_sayisi = sum(1 for k in harfler if k == "i")
    i_orani = i_sayisi / harf_sayisi

    parcalar = metin.split()
    tek_harf = sum(1 for p in parcalar if len(p) == 1 and p.isalpha())
    tek_harf_orani = tek_harf / len(parcalar) if parcalar else 0.0

    # Turkce metin olup olmadigini anlamak icin: Turkce'ye ozgu harfler.
    turkce_isaret = sum(1 for k in harfler if k in "şğüöçıŞĞÜÖÇI")
    turkce_mi = turkce_isaret / harf_sayisi > 0.01

    if turkce_mi and i_orani < I_ORANI_ESIGI:
        return Kalite(
            False,
            f"Türkçe metinde 'i' harfi payı %{i_orani * 100:.2f} "
            f"(beklenen ~%8). PDF'in metin katmanında bu harf yok; "
            f"çıkarma bozuk, OCR gerekiyor.",
            i_orani,
            tek_harf_orani,
            harf_sayisi,
        )

    if tek_harf_orani > TEK_HARF_ESIGI:
        return Kalite(
            False,
            f"Parçaların %{tek_harf_orani * 100:.0f}'i tek harf "
            f"('d s pl n' biçimi). Çıkarma harfleri boşluğa çevirmiş.",
            i_orani,
            tek_harf_orani,
            harf_sayisi,
        )

    return Kalite(True, "", i_orani, tek_harf_orani, harf_sayisi)


# ---------------------------------------------------------------------------
# Okuma
# ---------------------------------------------------------------------------


def _docx_metin(yol: Path) -> list[str]:
    """DOCX paragrafları.

    ``</w:p>`` ile bölünüyor: paragraflar iç içe geçebiliyor (tablo, metin
    kutusu) ve ``<w:p ...>.*?</w:p>`` düzenli ifadesi o durumda yanlış
    eşleşip ham XML sızdırıyor -- ilk denemede tam bu oldu.
    """
    with zipfile.ZipFile(yol) as paket:
        xml = paket.read("word/document.xml").decode("utf-8")

    xml = xml.replace("<w:br/>", "\n").replace("<w:tab/>", "\t")
    satirlar = []

    for parca in xml.split("</w:p>"):
        metinler = re.findall(r"<w:t(?:\s[^>]*)?>(.*?)</w:t>", parca, re.S)
        if not metinler:
            continue
        satir = html.unescape("".join(metinler)).strip()
        if satir:
            satirlar.append(satir)

    return satirlar


def _pdftotext_sayfalar(yol: Path) -> list[str]:
    """PDF sayfaları -- poppler ``pdftotext``, yereldeki ikili."""
    arac = shutil.which("pdftotext")
    if arac is None:
        raise RuntimeError(
            "pdftotext bulunamadı; PDF okumak için poppler gerekiyor."
        )

    sonuc = subprocess.run(
        [arac, "-enc", "UTF-8", "-layout", str(yol), "-"],
        capture_output=True,
        # stdin ACIKCA veriliyor: Windows'ta bos birakilan stdin ile
        # subprocess asili kaliyor (depo genelinde yasanmis bir tuzak).
        stdin=subprocess.DEVNULL,
        check=False,
    )

    if sonuc.returncode != 0:
        raise RuntimeError(f"pdftotext hata verdi: {sonuc.stderr[:200]!r}")

    # Sayfa ayraci form feed.
    return sonuc.stdout.decode("utf-8", "replace").split("\f")


def _pdf_oku(yol: Path) -> tuple[list[str], str]:
    """PDF'i oku; fontun eşlemesi bozuksa metni geri kazanmayı dene.

    Önce ``pdftotext`` deneniyor -- hızlı ve çoğu belgede yeterli. Çıkan metin
    kalite denetiminden geçmezse ``pdf_kurtar`` devreye giriyor: glif glif
    okuyup eşlemesi olmayanları geri koyuyor. Sıra bu yönde çünkü kurtarma
    ölçülü olarak daha yavaş ve yalnızca bozuk belgelerde gerekli.
    """
    try:
        sayfalar = _pdftotext_sayfalar(yol)
    except RuntimeError:
        sayfalar = []

    if sayfalar and kalite_olc("\n".join(sayfalar)).guvenilir:
        return sayfalar, ""

    if not pdf_kurtar.kullanilabilir():
        return sayfalar, (
            "Metin katmanı bozuk görünüyor ve kurtarma için gereken "
            "pdfminer.six kurulu değil."
        )

    kurtarilan = pdf_kurtar.kurtar(yol)

    if not kurtarilan.secilen_harf:
        return sayfalar or kurtarilan.sayfalar, kurtarilan.aciklama()

    return kurtarilan.sayfalar, kurtarilan.aciklama()


@dataclass
class Belge:
    """Okunmuş bir kaynak belge."""

    yol: Path
    sayfalar: list[str]
    kalite: Kalite
    #: PDF'te eşlemesi düşen glifler geri konduysa nasıl yapıldığı.
    kurtarma_aciklamasi: str = ""

    @property
    def ad(self) -> str:
        return self.yol.name

    @property
    def metin(self) -> str:
        return "\n".join(self.sayfalar)

    @property
    def sayfa_sayisi(self) -> int:
        return len(self.sayfalar)


def oku(yol: str | Path) -> Belge:
    """Belgeyi oku ve kalitesini ölç.

    Kalite düşükse hata FIRLATILMIYOR: karar çağırana ait. Ama ``kalite``
    alanı ``False`` dönüyor ve sebebini taşıyor, böylece bozuk metin
    sessizce modele gitmiyor.
    """
    yol = Path(yol)
    uzanti = yol.suffix.lower()
    kurtarma = ""

    if uzanti == ".docx":
        sayfalar = ["\n".join(_docx_metin(yol))]
    elif uzanti == ".pdf":
        sayfalar, kurtarma = _pdf_oku(yol)
    elif uzanti in {".txt", ".md"}:
        sayfalar = [yol.read_text(encoding="utf-8", errors="replace")]
    else:
        raise ValueError(f"desteklenmeyen belge türü: {uzanti}")

    return Belge(yol, sayfalar, kalite_olc("\n".join(sayfalar)), kurtarma)


# ---------------------------------------------------------------------------
# Bağlam sınırına göre parçalama
# ---------------------------------------------------------------------------

#: Kaba token tahmini: Türkçe metinde karakter/token ~3. Tokenizer
#: çağırmıyoruz çünkü yerel modelin tokenizer'ı sağlayıcıya göre değişiyor
#: ve bu tahmin sınırı BELİRLEMEK için değil, ALTINDA KALMAK için.
KARAKTER_BASINA_TOKEN = 3


def token_tahmini(metin: str) -> int:
    return len(metin) // KARAKTER_BASINA_TOKEN


@dataclass
class Parca:
    """Bir belgenin, bağlama sığacak bir dilimi."""

    belge: str
    ilk_sayfa: int
    son_sayfa: int
    metin: str

    @property
    def atif(self) -> str:
        """Rapora yazılabilir kaynak göstergesi."""
        if self.ilk_sayfa == self.son_sayfa:
            return f"{self.belge} s.{self.ilk_sayfa}"
        return f"{self.belge} s.{self.ilk_sayfa}-{self.son_sayfa}"


def _satirlara_bol(metin: str, token_butcesi: int) -> list[str]:
    """Tek bir sayfayı bütçeye sığan dilimlere böl.

    DOCX'te sayfa sınırı YOK: ``.docx`` sayfalamayı Word'e bırakıyor, dosyada
    böyle bir bilgi durmuyor. Bu yüzden bir DOCX tek "sayfa" olarak okunuyor
    ve ölçüldü: Yönerge dosyası tek parçada ~135 bin token çıkıyor -- 64 binlik
    pencereye de 128 binliğe de sığmıyor. Sayfaya göre bölmek burada işe
    yaramadığı için satır sınırında bölünüyor.
    """
    dilimler: list[str] = []
    yigin: list[str] = []

    for satir in metin.split("\n"):
        aday = "\n".join([*yigin, satir])

        if yigin and token_tahmini(aday) > token_butcesi:
            dilimler.append("\n".join(yigin))
            yigin = [satir]
        else:
            yigin.append(satir)

    if yigin:
        dilimler.append("\n".join(yigin))

    return dilimler


def parcala(belge: Belge, token_butcesi: int = 6000) -> list[Parca]:
    """Belgeyi bütçeye sığan parçalara böl; her parça sayfasını hatırlar.

    Önce sayfa sınırında bölünüyor: bir parça rapora atıf verecekse hangi
    sayfadan geldiğini kesin bilmesi gerekiyor. Tek bir sayfa bile bütçeyi
    aşıyorsa -- DOCX'te olağan hâl -- o sayfa satır sınırında bölünüyor.
    """
    parcalar: list[Parca] = []
    yigin: list[str] = []
    ilk = 1

    def bosalt(son: int) -> None:
        if yigin:
            parcalar.append(Parca(belge.ad, ilk, son, "\n".join(yigin)))

    for no, sayfa in enumerate(belge.sayfalar, start=1):
        if token_tahmini(sayfa) > token_butcesi:
            # Sayfanin KENDISI butceden buyuk: once bekleyeni kapat, sonra bu
            # sayfayi satir sinirinda dilimle.
            bosalt(no - 1)
            yigin = []

            for dilim in _satirlara_bol(sayfa, token_butcesi):
                parcalar.append(Parca(belge.ad, no, no, dilim))

            ilk = no + 1
            continue

        aday = "\n".join([*yigin, sayfa])

        if yigin and token_tahmini(aday) > token_butcesi:
            bosalt(no - 1)
            yigin = [sayfa]
            ilk = no
        else:
            if not yigin:
                ilk = no
            yigin.append(sayfa)

    bosalt(len(belge.sayfalar))

    return parcalar


# ---------------------------------------------------------------------------
# Delil kartı -- 10 belgeyi bağlama sığdırmanın yolu
# ---------------------------------------------------------------------------


@dataclass
class DelilKarti:
    """Bir delil belgesinin sıkıştırılmış künyesi.

    On dilekçenin tam metni bağlama sığmıyor; künyeleri sığıyor. Rapor
    yazılırken model önce kartlara bakıyor, yalnızca gerekeni açıyor.
    """

    ek_no: int
    ad: str
    tur: str = ""
    tarih: str = ""
    sayi: str = ""
    kisiler: list[str] = field(default_factory=list)
    sayfa_sayisi: int = 1
    ozet: str = ""

    def satir(self) -> str:
        alanlar = [f"Ek:{self.ek_no}", self.ad]
        if self.tur:
            alanlar.append(self.tur)
        if self.tarih:
            alanlar.append(self.tarih)
        if self.sayi:
            alanlar.append(f"sayı {self.sayi}")
        if self.kisiler:
            alanlar.append("kişiler: " + ", ".join(self.kisiler))
        return " | ".join(alanlar)


# Resmi yazilarda tarih: 01.06.2026
_TARIH = re.compile(r"\b(\d{2}\.\d{2}\.\d{4})\b")
# "10.04.2026 tarih ve 7032434 sayili" kalibi
_SAYI = re.compile(r"tarih\s+ve\s+([0-9\-/]+)\s+sayılı", re.IGNORECASE)
# Resmi yazida kisi adi: "Sefer TOPKAFA" -- soyadi TAMAMEN BUYUK.
_KISI = re.compile(r"\b([A-ZÇĞİÖŞÜ][a-zçğıöşü]+(?:\s+[A-ZÇĞİÖŞÜ][a-zçğıöşü]+)*)\s+([A-ZÇĞİÖŞÜ]{2,}(?:\s+[A-ZÇĞİÖŞÜ]{2,})?)\b")

_TUR_ISARETLERI = (
    ("şikâyet dilekçesi", ("şikayet", "şikâyet", "dilekçe")),
    ("ifade tutanağı", ("ifade tutanağı", "ifadesi alınmış", "ifade veren")),
    # "esas" ve "karar" TEK BASINA yeterli sayilmiyor.
    #
    # Ikisi de Turkce resmi yazinin siradan sozcukleri: "hakedise esas
    # puantaj", "kararlastirilmistir". Olculdu -- bir ifade tutanagi ile bir
    # resmi yazi, yalnizca icinde "esas" gectigi icin "mahkeme karari" diye
    # siniflandi ve bu tur, EK DIZININE yazilan icerigin varsayilani
    # (``arac.delil_ekle``). Yani raporun resmi ek dizininde bir ifade
    # tutanagi "mahkeme karari" olarak gorunuyordu.
    ("mahkeme kararı", ("mahkemesi", "esas no", "karar no", "gerekçeli karar")),
    ("makam onayı", ("makam onayı", "makam oluru")),
    ("teftiş raporu", ("cevaplı teftiş", "teftiş raporu")),
    ("resmî yazı", ("bilgilerinize arz", "gereğini arz", "ilgi yazınız")),
)


def kart_cikar(belge: Belge, ek_no: int) -> DelilKarti:
    """Belgeden künye çıkar -- uydurmadan, yalnızca metinde YAZANI.

    Bulunamayan alan boş bırakılıyor. Bir dilekçenin tarihini tahmin etmek,
    o tarihin rapora girip resmî bir iddiaya dönüşmesi demek olurdu.
    """
    metin = belge.metin

    # ``turkce.kucuk``, ``str.lower`` DEGIL.
    #
    # Python "İFADE".lower() cagrisini "i" + U+0307 (birlesik nokta) olarak
    # cozuyor, yani sonuc "ifade" ile esit DEGIL. Olculdu: basligi "İFADE
    # TUTANAĞI" olan bir belgede "ifade tutanağı" isareti hic tutmuyor ve
    # belge yanlis siniflaniyordu. Turkce resmi evrakta basliklar buyuk
    # harfle yazildigi icin bu, istisna degil olagan hal.
    dusuk = kucuk(metin)

    tur = ""
    for ad, isaretler in _TUR_ISARETLERI:
        if any(isaret in dusuk for isaret in isaretler):
            tur = ad
            break

    tarihler = _TARIH.findall(metin)
    sayilar = _SAYI.findall(metin)

    kisiler: list[str] = []
    for ad, soyad in _KISI.findall(metin):
        tam = f"{ad} {soyad}"
        if tam not in kisiler:
            kisiler.append(tam)

    return DelilKarti(
        ek_no=ek_no,
        ad=belge.ad,
        tur=tur,
        tarih=tarihler[0] if tarihler else "",
        sayi=sayilar[0] if sayilar else "",
        kisiler=kisiler[:8],
        sayfa_sayisi=belge.sayfa_sayisi,
        ozet="",
    )
