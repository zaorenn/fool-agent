"""
Raporu ÜRETMEDEN ÖNCE şartnameye karşı denetle.

Neden üretimden önce
--------------------
Bu depoda hâlihazırda iki denetim var ve ikisi de GEÇ: ``rapor_yaz`` belgeyi
yazdıktan sonra ``eksik_alanlar`` döndürüyor, ``bicim_devral.yonergeye_uygunluk``
ise zaten var olan bir belgeyi ölçüyor. İkisi de "belge çıktı, şu yanları
yanlış" diyor. Kullanıcının şartı "hata payı yok" ve bunun pratikteki karşılığı
şu: yanlış belge hiç ÜRETİLMEMELİ, çünkü üretilen belge imzalanıyor.

Bu yüzden denetim taslağın üstünde çalışıyor -- diskteki JSON'un, .docx'in
değil. Model bir bölümü yazdıktan sonra denetleyip düzeltebiliyor; düzeltme
tek bir ``rapor_taslak_bolum`` çağrısı, yeniden üretim değil.

Neden ``taslak.durum`` yetmiyor
-------------------------------
``durum`` bölüm başlıklarını sayıyor ve kısa bölümleri işaretliyor. Saymadığı
şeyler tam olarak yönergenin en bağlayıcı kuralları:

* Bölümlerin SIRASI (yönerge sırayı sayıyor ve sıra bağlayıcı).
* Sonuç bölümündeki KESİN İFADE. ``yonerge.RaporTuru.sonuc_ifadeleri`` ve
  ``KAPANIS_IFADESI`` bu depoda veri olarak duruyordu ve hiçbir yerde
  kullanılmıyordu -- yalnızca testler onlara bakıyordu. Yani yönergenin
  "rapor şu ifadeyle son bulur" kuralı hiç uygulanmıyordu.
* Maddi tespitin EKE DAYANMASI. ``delil_ekle`` ekleri kaydediyor ama hiçbir
  şey paragrafın gerçekten bir eke atıf yapıp yapmadığına bakmıyordu.
* ŞİŞİRME. Yönerge sayfa sayısını tekrarla artırmayı açıkça yasaklıyor;
  sayfa hedefi olan bir üretimde bu, modelin en kolay çıkış yolu.

Engel mi uyarı mı
-----------------
``engel`` üretimi durduruyor, ``uyari`` durdurmuyor. Ayrımın ölçütü şu: kural
yönergede SAYIYLA ya da KESİN İFADEYLE yazılıysa engel (eksik bölüm, yanlış
sıra, kapanış ifadesi); yorum gerektiriyorsa uyarı (bir paragrafın maddi
tespit sayılıp sayılmayacağı). Her uyarıyı engel yapmak aracı kullanılamaz
kılardı; hiçbirini engel yapmamak denetimi süse çevirirdi.

Zone A: upstream bu dosyayı bilmiyor.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .sartname import Sartname
from .turkce import kucuk, sade_baslik
from .yonerge import KAPANIS_IFADESI, RAPOR_TURLERI

ENGEL = "engel"
UYARI = "uyari"


@dataclass
class Bulgu:
    """Şartnameye aykırı tek bir nokta."""

    agirlik: str
    alan: str
    aciklama: str
    dayanak: str = ""

    def __str__(self) -> str:
        yer = f" [{self.dayanak}]" if self.dayanak else ""
        return f"{self.agirlik.upper()} · {self.alan}: {self.aciklama}{yer}"

    def sozluk(self) -> dict:
        return {
            "agirlik": self.agirlik,
            "alan": self.alan,
            "aciklama": self.aciklama,
            "dayanak": self.dayanak,
        }


@dataclass
class Rapor_Denetimi:
    """Bir taslağın şartnameye uygunluğu."""

    bulgular: list[Bulgu] = field(default_factory=list)
    #: Denetimin gerçekten neyi ölçebildiği. Şartname bir kuralı taşımıyorsa
    #: o kural DENETLENMEDİ demektir ve bu, "uygun" demekle aynı şey değil.
    denetlenmeyenler: list[str] = field(default_factory=list)

    @property
    def engeller(self) -> list[Bulgu]:
        return [b for b in self.bulgular if b.agirlik == ENGEL]

    @property
    def uyarilar(self) -> list[Bulgu]:
        return [b for b in self.bulgular if b.agirlik == UYARI]

    @property
    def uygun(self) -> bool:
        """Üretilebilir mi? Uyarılar engel değil."""
        return not self.engeller

    def sozluk(self) -> dict:
        return {
            "uygun": self.uygun,
            "engel_sayisi": len(self.engeller),
            "uyari_sayisi": len(self.uyarilar),
            "bulgular": [b.sozluk() for b in self.bulgular],
            "denetlenmeyenler": list(self.denetlenmeyenler),
        }


# ---------------------------------------------------------------------------
# Taslaktan metin çıkarma
# ---------------------------------------------------------------------------


def _oge_metni(oge: dict) -> str:
    """Bir bölüm öğesinin taşıdığı düz metin."""
    if not isinstance(oge, dict):
        return ""

    parcalar = [str(oge.get("metin", "")), str(oge.get("baslik", ""))]

    for satir in oge.get("satirlar") or []:
        parcalar += [str(h) for h in satir]

    return " ".join(p for p in parcalar if p)


def bolum_metni(bolum: dict) -> str:
    return " ".join(_oge_metni(o) for o in bolum.get("ogeler", []))


def _bolum_bul(bolumler: list[dict], hedef: str) -> dict | None:
    """Başlığı sadeleştirerek bölümü bul (bkz. ``turkce.sade_baslik``)."""
    sade = sade_baslik(hedef)

    for bolum in bolumler:
        mevcut = sade_baslik(str(bolum.get("baslik", "")))
        if mevcut == sade or mevcut.startswith(sade) or sade.startswith(mevcut):
            return bolum

    return None


# ---------------------------------------------------------------------------
# Denetimler
# ---------------------------------------------------------------------------


def _bolumleri_denetle(
    bolumler: list[dict], beklenen: list[str], dayanak: str
) -> list[Bulgu]:
    """Bölümler var mı, dolu mu ve YÖNERGEDEKİ SIRADA mı?"""
    bulgular: list[Bulgu] = []
    yerler: list[int] = []

    for baslik in beklenen:
        bolum = _bolum_bul(bolumler, baslik)

        if bolum is None:
            bulgular.append(
                Bulgu(ENGEL, "bölüm", f"'{baslik}' bölümü yok.", dayanak)
            )
            continue

        if not bolum_metni(bolum).strip():
            bulgular.append(
                Bulgu(ENGEL, "bölüm", f"'{baslik}' bölümü boş.", dayanak)
            )

        yerler.append(bolumler.index(bolum))

    # Sira denetimi YALNIZCA bulunan bolumler uzerinden: eksik bir bolum zaten
    # ayri bir engel ve onu bir de "sira bozuk" diye saymak, tek kusuru iki
    # kez bildirmek olurdu.
    if yerler != sorted(yerler):
        bulgular.append(
            Bulgu(
                ENGEL,
                "sıra",
                "Bölümler yönergedeki sırada değil. Beklenen sıra: "
                + " → ".join(beklenen),
                dayanak,
            )
        )

    return bulgular


def _ifadeleri_denetle(
    bolumler: list[dict], sartname: Sartname
) -> tuple[list[Bulgu], list[str]]:
    """Kapanış ifadesi ve sonuç bölümündeki kesin ifade.

    Kesin ifade SONUÇ bölümünde aranıyor, raporun tamamında değil: yönerge
    onu sonucun kuralı olarak yazıyor ve tartışma bölümünde geçen bir
    "kamu zararı tespit edilmiştir" cümlesi sonucu yazmış sayılmaz.
    """
    bulgular: list[Bulgu] = []
    denetlenmeyen: list[str] = []

    sonuc = _sonuc_bolumu(bolumler, sartname)

    if sartname.kapanis_ifadesi:
        # Kapanis ifadesi SON BOLUMDE araniyor, raporun herhangi bir yerinde
        # degil. Yonerge "rapor ... ifadesiyle son bulur" diyor; tartisma
        # bolumunde gecen bir kalip raporu bitirmis sayilmaz. Tamaminda
        # aramak, kapanisi hic yazmamis bir raporu "uygun" gosterebilirdi.
        kapsam = kucuk(bolum_metni(sonuc)) if sonuc is not None else ""

        if kucuk(sartname.kapanis_ifadesi) not in kapsam:
            bulgular.append(
                Bulgu(
                    ENGEL,
                    "kapanış",
                    f"Rapor '{sartname.kapanis_ifadesi}' ifadesiyle bitmiyor; "
                    "bu ifade son bölümde geçmeli.",
                    _dayanak(sartname, "kapanis_ifadesi"),
                )
            )
    else:
        denetlenmeyen.append("kapanış ifadesi (şartnamede yok)")

    if not sartname.zorunlu_ifadeler:
        denetlenmeyen.append("sonuç ifadesi (şartnamede yok)")
        return bulgular, denetlenmeyen

    if sonuc is None:
        # Sonuc bolumu yoksa eksik bolum denetimi zaten bagirdi.
        return bulgular, denetlenmeyen

    govde = kucuk(bolum_metni(sonuc))

    if not any(kucuk(i) in govde for i in sartname.zorunlu_ifadeler):
        bulgular.append(
            Bulgu(
                ENGEL,
                "sonuç ifadesi",
                "Sonuç bölümü yönergenin saydığı kesin ifadelerden hiçbirini "
                "taşımıyor. Birini AYNEN yaz: "
                + " | ".join(f"“{i}”" for i in sartname.zorunlu_ifadeler),
                sartname.bolum_dayanagi,
            )
        )

    return bulgular, denetlenmeyen


def _sonuc_bolumu(bolumler: list[dict], sartname: Sartname) -> dict | None:
    """Şartnamedeki SON bölüm -- yönergelerde sonuç her zaman sonuncusu."""
    if not sartname.bolumler:
        return None

    return _bolum_bul(bolumler, sartname.bolumler[-1])


def _dayanak(sartname: Sartname, alan: str) -> str:
    kural = sartname.kural(alan)
    return kural.dayanak if kural else ""


# --- Kapak ---------------------------------------------------------------

#: Şartnamenin yönergeden okuduğu kapak alanı adları -> ``model.Kapak``
#: alanları. Eşleme SÖZCÜK TABANLI: yönerge "Görev emri tarih ve sayısı"
#: diyor, kod ``gorev_emri_tarih`` ve ``gorev_emri_sayi`` tutuyor. Birebir
#: ad beklemek her yönergede eşlemeyi bozardı.
_KAPAK_ESLEME = (
    (("bakanlık",), ("bakanlik",)),
    (("başkanlık", "kurul"), ("baskanlik",)),
    (("raporun adı", "rapor adı", "başlık"), ("baslik",)),
    (("konu",), ("konu",)),
    (("görev emri",), ("gorev_emri_tarih", "gorev_emri_sayi")),
    (("rapor tarih", "rapor sayı"), ("rapor_tarih", "rapor_sayi")),
    (("ek adedi", "ek sayısı"), ("ek_adedi",)),
    (("müfettiş", "düzenleyen"), ("mufettis_ad",)),
)


def _kapagi_denetle(kapak: dict, sartname: Sartname) -> tuple[list[Bulgu], list[str]]:
    """Yönergenin saydığı kapak alanları dolu mu?"""
    if not sartname.kapak_alanlari:
        return [], ["kapak alanları (şartnamede yok)"]

    bulgular: list[Bulgu] = []
    dayanak = _dayanak(sartname, "kapak_alanlari")

    for yazim in sartname.kapak_alanlari:
        sade = kucuk(yazim)
        alanlar = next(
            (kod for isaretler, kod in _KAPAK_ESLEME if any(i in sade for i in isaretler)),
            (),
        )

        if not alanlar:
            # Eslenemeyen alan SESSIZCE gecilmiyor: yonerge onu kapakta
            # istiyor ve kod onu tutmuyor demektir.
            bulgular.append(
                Bulgu(
                    UYARI,
                    "kapak",
                    f"Yönerge kapakta '{yazim}' istiyor; kapak modelinde "
                    "karşılığı yok, elle kontrol et.",
                    dayanak,
                )
            )
            continue

        for alan in alanlar:
            if not str(kapak.get(alan, "")).strip():
                bulgular.append(
                    Bulgu(ENGEL, "kapak", f"'{yazim}' boş ({alan}).", dayanak)
                )

    return bulgular, []


# --- Ek atfı ve izlenebilirlik -------------------------------------------

#: Bir paragrafın MADDİ TESPİT taşıdığını gösteren işaretler.
#:
#: Ölçüt bilerek dar: tarih, resmî sayı ya da tutar. Bunlar bir raporun
#: doğrulanabilir çekirdeği ve uydurulduklarında en pahalı olanlar
#: (``model`` modülünün başında yazılı gerekçe). "Değerlendirilmiştir" gibi
#: yorum cümleleri kapsam dışı: onların eke dayanması gerekmiyor ve her
#: paragrafı işaretlemek uyarıyı gürültüye çevirirdi.
_TESPIT_ISARETLERI = (
    re.compile(r"\b\d{2}\.\d{2}\.\d{4}\b"),
    re.compile(r"\b\d[\d.]*\s*(?:TL|₺|Türk lirası)", re.IGNORECASE),
    re.compile(r"\b[\d/\-]{3,}\s*sayılı", re.IGNORECASE),
)

#: Metnin içine elle yazılmış ek atfı -- "(Ek: 3/1)".
_METINDE_EK = re.compile(r"\(\s*Ek\s*[:.]\s*[^)]{1,24}\)", re.IGNORECASE)


def _tespit_mi(metin: str) -> bool:
    return any(k.search(metin) for k in _TESPIT_ISARETLERI)


def _izlenebilirligi_denetle(bolumler: list[dict], ek_sayisi: int) -> list[Bulgu]:
    """Maddi tespit taşıyan her paragraf bir eke dayanıyor mu?

    Uyarı, engel değil: bir tarih taşıyan her cümle maddi tespit olmayabilir
    (görev emrinin tarihi GİRİŞ bölümünün olağan içeriği ve onun eki yok).
    Kararı müfettiş veriyor; aracın işi listeyi önüne koymak.
    """
    dayanaksiz: list[str] = []

    for bolum in bolumler:
        for oge in bolum.get("ogeler", []):
            if not isinstance(oge, dict):
                continue

            metin = _oge_metni(oge)

            if not _tespit_mi(metin):
                continue

            if str(oge.get("ek", "")).strip() or _METINDE_EK.search(metin):
                continue

            dayanaksiz.append(f"{bolum.get('baslik', '')}: {metin[:70]}…")

    if not dayanaksiz:
        return []

    if ek_sayisi == 0:
        return [
            Bulgu(
                ENGEL,
                "dayanak",
                f"{len(dayanaksiz)} paragraf tarih/sayı/tutar içeriyor ama "
                "rapora HİÇ ek bağlanmamış. Maddi tespitin dayanağı olmadan "
                "rapor imzalanamaz; önce rapor_delil_ekle çağır.",
            )
        ]

    return [
        Bulgu(
            UYARI,
            "dayanak",
            f"{len(dayanaksiz)} paragraf maddi tespit taşıyor ama ek atfı yok. "
            "Her birine (Ek: n/m) ekle ya da tespit değilse geç: "
            + " || ".join(dayanaksiz[:5]),
        )
    ]


# --- Şişirme -------------------------------------------------------------

#: Tekrar sayılmak için bir cümlenin en az uzunluğu.
#:
#: 60 karakter: resmî metinde kısa kalıplar ("Arz olunur.", "Gereği
#: bilgilerinize sunulur.") meşru olarak tekrarlanıyor ve onları şişirme
#: saymak her raporu suçlardı. Bu uzunluğun üstünde birebir tekrar eden bir
#: cümle ise anlatı değil, doldurma.
TEKRAR_ASGARI_UZUNLUK = 60


def _sisirmeyi_denetle(bolumler: list[dict]) -> list[Bulgu]:
    """Aynı cümleyi tekrar ederek sayfa doldurulmuş mu?

    Yönerge bunu açıkça yasaklıyor ve sebebi yalnızca biçim değil: sayfa
    hedefi olan bir üretimde tekrar, modelin en ucuz çıkış yolu. Hedefi
    tutturmanın yolu daha çok TESPİT, aynı tespiti iki kez yazmak değil.
    """
    sayac: dict[str, int] = {}

    for bolum in bolumler:
        for oge in bolum.get("ogeler", []):
            for cumle in re.split(r"(?<=[.!?])\s+", _oge_metni(oge)):
                sade = " ".join(cumle.split()).lower()

                if len(sade) >= TEKRAR_ASGARI_UZUNLUK:
                    sayac[sade] = sayac.get(sade, 0) + 1

    tekrarlar = [c for c, adet in sayac.items() if adet > 1]

    if not tekrarlar:
        return []

    return [
        Bulgu(
            ENGEL,
            "şişirme",
            f"{len(tekrarlar)} cümle birebir tekrar ediyor. Yönerge raporun "
            "tekrarla uzatılmasını yasaklıyor; tekrar eden cümleyi sil ve "
            "yerine kaynaklardan yeni tespit yaz: "
            + " || ".join(t[:70] + "…" for t in tekrarlar[:3]),
        )
    ]


# ---------------------------------------------------------------------------
# Giriş noktası
# ---------------------------------------------------------------------------


def denetle(taslak_sozlugu: dict, sartname: Sartname | None = None) -> Rapor_Denetimi:
    """Bir taslağı şartnameye karşı denetle.

    ``sartname`` verilmezse taslağın türünden ``yonerge.RAPOR_TURLERI``
    tablosuna düşülüyor -- yönerge yüklenmemiş bir oturumda denetimin hiç
    çalışmaması, en azından bölüm ve kapanış denetimini kaybetmek olurdu.
    """
    sartname = sartname or _turden_sartname(str(taslak_sozlugu.get("tur", "")))

    denetim = Rapor_Denetimi()
    bolumler = [b for b in taslak_sozlugu.get("bolumler", []) if isinstance(b, dict)]

    if sartname is None:
        denetim.bulgular.append(
            Bulgu(
                ENGEL,
                "şartname",
                "Ne şartname verildi ne de taslağın türü tanınıyor; neye göre "
                "denetleneceği belli değil. Önce rapor_yonerge_ogren çağır.",
            )
        )
        return denetim

    if sartname.bolumler:
        denetim.bulgular += _bolumleri_denetle(
            bolumler, sartname.bolumler, sartname.bolum_dayanagi
        )
    else:
        denetim.denetlenmeyenler.append("bölüm listesi (şartnamede yok)")

    ifade_bulgulari, ifade_denetlenmeyen = _ifadeleri_denetle(bolumler, sartname)
    denetim.bulgular += ifade_bulgulari
    denetim.denetlenmeyenler += ifade_denetlenmeyen

    kapak_bulgulari, kapak_denetlenmeyen = _kapagi_denetle(
        dict(taslak_sozlugu.get("kapak") or {}), sartname
    )
    denetim.bulgular += kapak_bulgulari
    denetim.denetlenmeyenler += kapak_denetlenmeyen

    denetim.bulgular += _izlenebilirligi_denetle(
        bolumler, len(taslak_sozlugu.get("ekler") or [])
    )
    denetim.bulgular += _sisirmeyi_denetle(bolumler)

    # Sayfa araligi BURADA denetlenmiyor: gercek sayfa sayisi ancak belge
    # basildiktan sonra bilinebiliyor (bkz. ``sayfa_hedefi``). Denetlenmemis
    # bir kurali sessiz birakmak, "uygun" cevabini oldugundan genis
    # gostermek olurdu.
    if sartname.sayfa_araligi_var_mi():
        denetim.denetlenmeyenler.append(
            f"sayfa aralığı {sartname.sayfa_en_az}-{sartname.sayfa_en_cok} "
            "(üretimden sonra rapor_sayfa_denetle ile ölçülür)"
        )

    return denetim


def _turden_sartname(tur: str) -> Sartname | None:
    """``RAPOR_TURLERI`` tablosundaki bir türü şartnameye çevir.

    Geriye dönük yol: şartname kavramı bu depoya sonradan geldi ve dört
    gömülü tür hâlâ geçerli. İki ayrı denetim yolu yazmak yerine eski tablo
    yeni biçime çevriliyor, böylece denetim mantığı TEK yerde duruyor.
    """
    rapor_turu = RAPOR_TURLERI.get(tur)

    if rapor_turu is None:
        return None

    return Sartname(
        kimlik=f"gomulu-{tur}",
        ad=rapor_turu.ad,
        kaynak="yonerge.RAPOR_TURLERI (koda gömülü)",
        bolumler=list(rapor_turu.bolumler),
        bolum_dayanagi="MADDE 17",
        zorunlu_ifadeler=list(rapor_turu.sonuc_ifadeleri),
        kapanis_ifadesi=KAPANIS_IFADESI,
    )
