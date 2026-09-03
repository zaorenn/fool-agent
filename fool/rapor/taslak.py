"""
Raporu PARÇA PARÇA kur -- tek bir dev JSON ile değil.

Ölçülen sebep
-------------
İlk tasarımda ``rapor_yaz`` raporun tamamını tek bir JSON olarak alıyordu.
Yerel modelle (google/gemma-4-e4b, LM Studio) denendi: araç çağrıldı, belge
yazıldı, ama model JSON'u yeniden kurarken kapak alanlarını düşürdü --
``gorev_emri_tarih``, ``gorev_emri_sayi``, ``rapor_tarih``, ``rapor_sayi``,
``ek_adedi`` ve ``imza_tarih`` kayboldu. Aynı JSON doğrudan araca verildiğinde
``eksik_alanlar`` boş dönüyor, yani hata araçta değil: küçük bir yerel model
uzun ve birebir bir yapıyı tek seferde üretemiyor.

Bu, tek başına bile düzeltilmesi gereken bir kusur. Ama asıl sorun daha
temelde: kullanıcının raporu 70 sayfaya kadar çıkıyor. 70 sayfalık bir raporun
tamamı tek bir JSON olarak ~100 bin token eder ve zaten 64 binlik pencereye
sığmaz. Yani "tek çağrıda tüm rapor" yaklaşımı modelden bağımsız olarak
ölçekleyemiyor.

Çözüm: taslak diskte birikiyor. Model her seferinde TEK bölüm gönderiyor,
her çağrı küçük ve doğrulanabilir, bağlamda hiçbir zaman raporun tamamı
durmuyor.

Neden diskte
------------
Oturum uzun; model bağlamı doluyor ve eski turlar özetleniyor. Taslak bağlamda
tutulsaydı, 40. bölüm yazılırken 3. bölüm çoktan unutulmuş olurdu. Diskte
duran taslak bundan etkilenmiyor ve iş yarıda kalırsa kaldığı yerden devam
ediyor.

Zone A: upstream bu dosyayı bilmiyor.
"""

from __future__ import annotations

import json
import re
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import sartname
from .turkce import sade_baslik
from .yonerge import RAPOR_TURLERI

#: Taslak kimliğinde yalnızca bunlar: taslak adı dosya yolu oluyor ve
#: ``../`` gibi bir ad başka klasöre yazmaya çalışırdı.
_GECERLI_KIMLIK = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


class TaslakHatasi(Exception):
    """Taslak işlemi yapılamadı."""


def taslak_klasoru() -> Path:
    """Taslakların durduğu yer.

    ``FOOL_RAPOR_TASLAK_DIR`` ile değiştirilebiliyor; testler kendi geçici
    klasörünü veriyor, böylece kullanıcının gerçek taslakları test koşusundan
    etkilenmiyor.
    """
    import os

    ham = os.environ.get("FOOL_RAPOR_TASLAK_DIR")

    if ham:
        yol = Path(ham)
    else:
        yol = Path(tempfile.gettempdir()) / "fool-rapor-taslak"

    yol.mkdir(parents=True, exist_ok=True)

    return yol


def _taslak_yolu(kimlik: str) -> Path:
    if not _GECERLI_KIMLIK.match(kimlik):
        raise TaslakHatasi(
            f"geçersiz taslak kimliği: {kimlik!r} "
            "(yalnızca harf, rakam, nokta, tire, alt çizgi; en çok 64)"
        )

    return taslak_klasoru() / f"{kimlik}.json"


@dataclass
class Taslak:
    """Diskte biriken rapor."""

    kimlik: str
    tur: str
    kapak: dict = field(default_factory=dict)
    ozet: list[str] = field(default_factory=list)
    bolumler: list[dict] = field(default_factory=list)
    ekler: list[dict] = field(default_factory=list)
    imza_yer: str = ""
    imza_tarih: str = ""
    #: Bölüm başlığı -> örnek rapordaki karakter sayısı. Hedef, dilek değil:
    #: örnekten belirgin kısa bir rapor, örneği taklit etmiyor demektir.
    hedef_uzunluk: dict = field(default_factory=dict)
    #: Rapora dayanak yapılan belgeler (ifade tutanakları, şikâyet
    #: dilekçeleri...). Künyeleri burada; TAM METİNLERİ diskte kalıyor ve
    #: yalnızca sorulduğunda parça parça okunuyor.
    deliller: list = field(default_factory=list)
    #: Bu taslağın uyacağı şartnamenin kimliği (``sartname`` modülü).
    #:
    #: Şartnamenin KENDİSİ değil kimliği tutuluyor: kullanıcı yönergedeki bir
    #: çıkarım hatasını düzeltip şartnameyi yeniden öğrenebiliyor ve o zaman
    #: yarım kalmış taslakların eski kurallarla devam etmesi istenmez. Kimlik
    #: tutulduğunda düzeltme bütün taslaklara aynı anda geçiyor.
    sartname: str = ""

    def sozluk(self) -> dict:
        return asdict(self)


def baslat(
    kimlik: str,
    tur: str,
    kapak: dict | None = None,
    ozet: list[str] | None = None,
    imza_yer: str = "",
    imza_tarih: str = "",
    sifirla: bool = False,
    hedef_uzunluk: dict | None = None,
    sartname_kimligi: str = "",
) -> Taslak:
    """Yeni taslak aç. Var olanın ÜZERİNE YAZMAZ.

    Önce yazıyordu ve ölçüldü: uygulama sürülürken model, bölümleri yazdıktan
    SONRA ``baslat``ı bir kez daha çağırdı ve o ana kadar yazılmış beş bölümün
    tamamı silindi -- taslakta 5 ek ve 10 kapak alanı kalmış, bölümler boştu.
    Bir dil modelinin turu yeniden başlatması olağan; 70 sayfalık bir işi
    sessizce sıfırlamak değil.

    Gerçekten baştan başlanacaksa ``sifirla=True`` açıkça isteniyor.
    """
    # Sartname verildiyse tur ADI SERBEST.
    #
    # ``RAPOR_TURLERI`` dort turu koda gomuyor ve kullanicinin yonergesi
    # bambaska bir rapor tanimlayabiliyor -- iş akışının başlangıç noktası
    # zaten "bu yönergeyi öğren" olduğu için, öğrenilen türü tanımayan bir
    # tablo yolun tam ortasında duruyordu. Sartname yoksa eski kural
    # aynen geçerli: tanınmayan tür reddediliyor.
    if not sartname_kimligi and tur not in RAPOR_TURLERI:
        raise TaslakHatasi(
            f"bilinmeyen rapor türü: {tur} (geçerli: {', '.join(sorted(RAPOR_TURLERI))}). "
            "Kendi yönergen varsa önce rapor_yonerge_ogren ile şartname çıkar "
            "ve sartname kimliğini ver."
        )

    if not sifirla and _taslak_yolu(kimlik).exists():
        mevcut = yukle(kimlik)

        if mevcut.bolumler or mevcut.ekler:
            raise TaslakHatasi(
                f"'{kimlik}' taslağı zaten var: "
                f"{len(mevcut.bolumler)} bölüm, {len(mevcut.ekler)} ek. "
                "Kaldığın yerden devam et (rapor_taslak_bolum / "
                "rapor_taslak_durum). Gerçekten baştan başlamak istiyorsan "
                "sifirla=true gönder."
            )

    taslak = Taslak(
        kimlik=kimlik,
        tur=tur,
        kapak=dict(kapak or {}),
        ozet=list(ozet or []),
        imza_yer=imza_yer,
        imza_tarih=imza_tarih,
        hedef_uzunluk=dict(hedef_uzunluk or {}),
        sartname=sartname_kimligi,
    )
    _yaz(taslak)

    return taslak


def _yaz(taslak: Taslak) -> None:
    yol = _taslak_yolu(taslak.kimlik)
    gecici = yol.with_suffix(".json.tmp")

    # Once gecici dosyaya, sonra yerine koy: 40. bolumu yazarken kesilen bir
    # islem, o ana kadar birikmis 39 bolumu bozmasin.
    gecici.write_text(
        json.dumps(taslak.sozluk(), ensure_ascii=False, indent=1), encoding="utf-8"
    )
    gecici.replace(yol)


def yukle(kimlik: str) -> Taslak:
    yol = _taslak_yolu(kimlik)

    if not yol.exists():
        raise TaslakHatasi(f"taslak bulunamadı: {kimlik}")

    try:
        ham = json.loads(yol.read_text(encoding="utf-8"))
    except json.JSONDecodeError as sebep:
        raise TaslakHatasi(f"taslak bozuk: {sebep}") from sebep

    return Taslak(**ham)


def bolum_ekle(kimlik: str, baslik: str, ogeler: list[dict]) -> Taslak:
    """Taslağa bir bölüm ekle.

    Aynı başlık ikinci kez gelirse ÜZERİNE YAZILIYOR, ikinci kopya
    eklenmiyor: model bir bölümü düzeltmek isteyince aynı başlıkla tekrar
    gönderiyor ve iki "III. İNCELEME VE ARAŞTIRMA" bölümü olan bir rapor,
    tamamlanmamış bir rapordan daha kötü.
    """
    ogeleri_dogrula(list(ogeler), baslik)

    taslak = yukle(kimlik)
    yeni = {"baslik": baslik, "ogeler": list(ogeler)}

    for sira, mevcut in enumerate(taslak.bolumler):
        if mevcut.get("baslik") == baslik:
            taslak.bolumler[sira] = yeni
            break
    else:
        taslak.bolumler.append(yeni)

    _yaz(taslak)

    return taslak


def ek_ekle(kimlik: str, icerik: str, sayfa_sayisi: int = 1, no: int | None = None) -> Taslak:
    """Ek dizinine bir kayıt ekle.

    Numara verilmezse sıradaki veriliyor: yönerge eklerin rapordaki ilk
    anılma sırasına göre numaralanmasını istiyor (MADDE 10(4)), o da doğal
    olarak ekleme sırası.
    """
    taslak = yukle(kimlik)
    sonraki = no if no is not None else len(taslak.ekler) + 1

    taslak.ekler.append(
        {"no": int(sonraki), "icerik": icerik, "sayfa_sayisi": int(sayfa_sayisi)}
    )
    _yaz(taslak)

    return taslak


def kapak_guncelle(kimlik: str, alanlar: dict) -> Taslak:
    """Kapağın yalnızca verilen alanlarını değiştir.

    Tümünü birden göndermek zorunda kalmamak önemli: ölçülen hata tam olarak
    modelin uzun bir kapak nesnesini yeniden kurarken alan düşürmesiydi.
    """
    kapak_alanlarini_dogrula(alanlar)

    taslak = yukle(kimlik)
    taslak.kapak.update({k: v for k, v in alanlar.items() if v not in (None, "")})
    _yaz(taslak)

    return taslak


def beklenen_bolumler(taslak: "Taslak") -> tuple[list[str], str]:
    """Bu taslağın uyması gereken bölüm listesi ve rapor türünün adı.

    Sıra: önce ŞARTNAME (kullanıcının kendi yönergesi), sonra koda gömülü
    tablo. Şartname kayıtlıysa o kazanıyor -- kullanıcı yönergeyi bilerek
    verdi ve gömülü tablo başka bir kurumun yönergesinden geliyor.

    Şartname kimliği yazılı ama dosyası silinmişse bölüm listesi BOŞ
    dönüyor ve bu bilerek: sessizce gömülü tabloya düşmek, taslağın hangi
    kurallarla denetlendiğini kullanıcıya yanlış söylerdi.
    """
    if taslak.sartname:
        kayitli = sartname.varsa_yukle(taslak.sartname)

        if kayitli is not None:
            return list(kayitli.bolumler), kayitli.ad

        return [], f"şartname bulunamadı: {taslak.sartname}"

    tur = RAPOR_TURLERI.get(taslak.tur)

    return (list(tur.bolumler), tur.ad) if tur else ([], taslak.tur)


def durum(kimlik: str) -> dict:
    """Taslakta ne var, yönergeye göre ne eksik?"""
    taslak = yukle(kimlik)
    beklenen, tur_adi = beklenen_bolumler(taslak)

    mevcut = [b.get("baslik", "") for b in taslak.bolumler]
    sade = {_sade(b) for b in mevcut}

    eksik = [b for b in beklenen if not _var_mi(_sade(b), sade)]

    return {
        "kimlik": taslak.kimlik,
        "tur": taslak.tur,
        "tur_adi": tur_adi,
        "sartname": taslak.sartname or None,
        "beklenen_bolumler": list(beklenen),
        "yazilan_bolumler": mevcut,
        "eksik_bolumler": eksik,
        "oge_sayisi": {b.get("baslik", ""): len(b.get("ogeler", [])) for b in taslak.bolumler},
        "ek_sayisi": len(taslak.ekler),
        "kapak_alanlari": sorted(taslak.kapak),
        "uzunluk": {b.get("baslik", ""): bolum_uzunlugu(b) for b in taslak.bolumler},
        "hedef_uzunluk": dict(taslak.hedef_uzunluk),
        "kisa_bolumler": [
            {"baslik": b, "mevcut": m, "hedef": h} for b, m, h in _kisa_kalanlar(taslak)
        ],
        "tamam_mi": not eksik and not _kisa_kalanlar(taslak),
        "siradaki_adim": _siradaki_adim(taslak, eksik),
    }


#: MADDE 6(1)'in saydigi, kapakta BULUNMASI ZORUNLU alanlar.
_ZORUNLU_KAPAK = (
    "bakanlik", "baskanlik", "baslik", "konu", "gorev_emri_tarih",
    "gorev_emri_sayi", "rapor_tarih", "rapor_sayi", "ek_adedi", "mufettis_ad",
)


def _siradaki_adim(taslak: "Taslak", eksik: list[str]) -> str:
    """Sırada ne yapılacağını AÇIKÇA söyle.

    Ölçüldü: yerel model (gemma-4-e4b) on bir adımlık bir planın ikinci
    bölümünden sonra durdu ve "rapor tamamlandı" dedi -- oysa üç bölüm ve
    kapağın yarısı eksikti. Araç cevabının içinde sıradaki adımı adıyla
    söylemek, planı modelin hafızasında tutmaya çalışmaktan çok daha
    dayanıklı: her turda yeniden hatırlatılıyor.
    """
    if eksik:
        hedef = ""
        for ornek_baslik, uzunluk in taslak.hedef_uzunluk.items():
            if _sade(ornek_baslik) == _sade(eksik[0]):
                hedef = (
                    f" Bu bölüm örnek raporda ~{int(uzunluk)} karakter; "
                    f"en az {int(int(uzunluk) * HEDEF_ORANI)} karakter yaz."
                )
                break

        return (
            f"HENÜZ BİTMEDİ. Sıradaki bölüm: '{eksik[0]}'.{hedef} "
            f"rapor_taslak_bolum aracını kimlik='{taslak.kimlik}', "
            f"baslik='{eksik[0]}' ile çağır. "
            f"Kalan bölümler: {', '.join(eksik)}."
        )

    kisa = _kisa_kalanlar(taslak)

    if kisa:
        baslik, mevcut, hedef = kisa[0]
        return (
            f"'{baslik}' bölümü ÇOK KISA: {mevcut} karakter, örnekte "
            f"~{hedef}. En az {int(hedef * HEDEF_ORANI)} karakter olmalı. "
            f"rapor_taslak_bolum ile aynı başlığı DAHA DOLU yazarak gönder "
            f"(aynı başlık üzerine yazar). Kalan kısa bölümler: "
            f"{', '.join(b for b, _, _ in kisa)}."
        )

    kapak_eksik = [a for a in _ZORUNLU_KAPAK if not str(taslak.kapak.get(a, "")).strip()]

    if kapak_eksik:
        return (
            f"Bölümler tamam. Kapakta eksik alan var: {', '.join(kapak_eksik)}. "
            f"rapor_taslak_kapak aracını kimlik='{taslak.kimlik}' ile çağır."
        )

    if not taslak.ekler:
        return (
            f"Bölümler ve kapak tamam. Şimdi ekleri gir: rapor_taslak_ek, "
            f"kimlik='{taslak.kimlik}'."
        )

    if not taslak.ozet:
        # MADDE 7: kapak ile rapor metni arasinda ozet sayfasi bulunur.
        return (
            f"Bölümler, kapak ve ekler tamam. Şimdi özeti yaz: "
            f"rapor_taslak_ozet, kimlik='{taslak.kimlik}'."
        )

    # Uretimden ONCE denetim. Sirali soylenmesinin sebebi olculdu: model
    # "siradaki adim" ne diyorsa onu yapiyor ve son adim dogrudan uretim
    # oldugunda denetim hic cagrilmiyordu -- yani yonergeye aykiri bir belge
    # uretilip imzaya gidebiliyordu (bkz. ``uygunluk`` modul basligi).
    return (
        f"Taslak hazır. ÖNCE rapor_uygunluk_denetle aracını "
        f"kimlik='{taslak.kimlik}' ile çağır; engel yoksa "
        f"rapor_taslak_uret ile .docx üret."
    )


#: Yazilan bir bolum, ornekteki karsiliginin bu kadarina ulasmali.
#:
#: Kullanicinin sozu: "ne sana attigim ornek rapordan kisa olamaz". Birebir
#: esitlik istenmiyor -- konu farkli, dava sayisi farkli -- ama ucte birinde
#: kalan bir bolum ornegi taklit etmiyor. %60 hem gercekci hem olculebilir.
HEDEF_ORANI = 0.6


def bolum_uzunlugu(bolum: dict) -> int:
    """Bir bölümdeki gerçek metin uzunluğu (karakter)."""
    toplam = 0

    for oge in bolum.get("ogeler", []):
        if not isinstance(oge, dict):
            continue

        toplam += len(str(oge.get("metin", "")))
        toplam += len(str(oge.get("baslik", "")))

        for satir in oge.get("satirlar", []) or []:
            toplam += sum(len(str(h)) for h in satir)

    return toplam


def _kisa_kalanlar(taslak: "Taslak") -> list[tuple[str, int, int]]:
    """Örnekteki karşılığının belirgin altında kalan bölümler."""
    kisa = []

    for bolum in taslak.bolumler:
        baslik = bolum.get("baslik", "")
        hedef = 0

        for ornek_baslik, uzunluk in taslak.hedef_uzunluk.items():
            sade = _sade(ornek_baslik)
            if sade == _sade(baslik) or sade.startswith(_sade(baslik)) or _sade(baslik).startswith(sade):
                hedef = int(uzunluk)
                break

        if hedef <= 0:
            continue

        mevcut = bolum_uzunlugu(bolum)

        if mevcut < hedef * HEDEF_ORANI:
            kisa.append((baslik, mevcut, hedef))

    return kisa


#: Başlık sadeleştirmesi ``turkce``de duruyor: aynı kuralı çözümleyici ve
#: uygunluk denetimi de kullanıyor ve üçü ayrışırsa "bölüm var mı" sorusuna
#: üç farklı cevap çıkar.
_sade = sade_baslik


def _var_mi(hedef: str, mevcut: set[str]) -> bool:
    # "V. SONUC" ile "V. SONUC VE ONERILER" ayni bolum (bkz. cozumle.bul).
    return any(m == hedef or m.startswith(hedef) or hedef.startswith(m) for m in mevcut)


def sil(kimlik: str) -> None:
    _taslak_yolu(kimlik).unlink(missing_ok=True)


def rapor_sozlugu(kimlik: str) -> dict:
    """Taslağı ``arac.rapor_yaz``ın beklediği yapıya çevir."""
    taslak = yukle(kimlik)
    beklenen, _ = beklenen_bolumler(taslak)

    return {
        "tur": taslak.tur,
        "kapak": taslak.kapak,
        "ozet": taslak.ozet,
        "bolumler": sirala(taslak.bolumler, taslak.tur, beklenen),
        "ekler": taslak.ekler,
        "imza_yer": taslak.imza_yer,
        "imza_tarih": taslak.imza_tarih,
        "sartname": taslak.sartname,
        "deliller": taslak.deliller,
    }


def sirala(
    bolumler: list[dict], tur_kimligi: str, beklenen_sira: list[str] | None = None
) -> list[dict]:
    """Bölümleri YÖNERGEDEKİ sıraya diz.

    Model bölümleri istediği sırada yazıyor -- ölçüldü: yerel model
    "IV. TARTIŞMA VE DEĞERLENDİRME"i "III. İNCELEME VE ARAŞTIRMA"dan önce
    gönderdi. Geliş sırasına göre yazınca ortaya bölümleri karışmış bir resmî
    rapor çıkıyor; yönerge (MADDE 17) sırayı sayıyor ve o sıra bağlayıcı.

    Yönergede olmayan bir başlık ATILMIYOR, sona ekleniyor: müfettiş kendi alt
    bölümünü açabiliyor (MADDE 8(7)) ve sessizce silmek veri kaybı olurdu.

    ``beklenen_sira`` şartnameden gelen sıra; verilmezse koda gömülü tabloya
    düşülüyor. Sıralama tek yerde kalsın diye iki kaynak burada birleşiyor --
    ikisi ayrı yazılsaydı şartnameli bir rapor gömülü sıraya göre dizilirdi.
    """
    if beklenen_sira is None:
        tur = RAPOR_TURLERI.get(tur_kimligi)
        beklenen_sira = list(tur.bolumler) if tur else []

    if not beklenen_sira:
        return list(bolumler)

    beklenen = [_sade(b) for b in beklenen_sira]

    def anahtar(veri: tuple[int, dict]) -> tuple[int, int]:
        sira, bolum = veri
        sade = _sade(bolum.get("baslik", ""))

        for yer, hedef in enumerate(beklenen):
            if sade == hedef or sade.startswith(hedef) or hedef.startswith(sade):
                return (yer, sira)

        # Taninmayan baslik sona, kendi arasinda geldigi sirayla.
        return (len(beklenen), sira)

    return [b for _, b in sorted(enumerate(bolumler), key=anahtar)]


# ---------------------------------------------------------------------------
# Doğrulama -- modelin gönderdiği şekli SESSİZCE kabul etmemek
# ---------------------------------------------------------------------------
#
# Ölçülen olay: yerel model bölüm öğeleri yerine şunu gönderdi::
#
#     {"\"icerik\"": [{"\"metin\"": [{"\"aciklama\"": 1, "\"tur\"": 0}]}]}
#
# Kod bunu kabul etti: ``tur`` yoktu -> "paragraf" varsayıldı, ``metin`` yoktu
# -> boş dizi. Sonuçta beş bölümü de BOŞ olan bir rapor üretildi ve araç
# "başarılı" dedi. Kapakta da model ``rapor_tarih`` yerine ``rapor_date``
# yazdı; bilinmeyen alan sessizce yutuldu ve tarih [EKSİK] kaldı.
#
# İkisi de aynı kusur: anlaşılmayanı sessizce düşürmek. Resmî evrakta en kötü
# sonuç bu -- hata görünmüyor, belge boş çıkıyor. Artık anlaşılmayan şey
# REDDEDİLİYOR ve doğru şeklin ne olduğu söyleniyor, böylece model düzeltip
# tekrar gönderebiliyor.

#: Bir bölüm öğesinin alabileceği türler ve o türde ZORUNLU alanlar.
_OGE_ALANLARI = {
    "paragraf": ("metin",),
    "alt_baslik": ("metin",),
    "alinti": ("metin",),
    "tablo": ("basliklar", "satirlar"),
}

#: Kapakta tanınan alanlar. MADDE 6(1) + imza/gizlilik.
_KAPAK_ALANLARI = frozenset(
    (
        "bakanlik", "baskanlik", "baslik", "konu", "gorev_emri_tarih",
        "gorev_emri_sayi", "rapor_tarih", "rapor_sayi", "ek_adedi",
        "mufettis_ad", "mufettis_unvan", "gizli",
    )
)


def ogeleri_dogrula(ogeler: list[dict], baslik: str) -> None:
    """Bölüm öğeleri gerçekten yazılabilir mi? Değilse NEDEN olmadığını söyle."""
    if not ogeler:
        raise TaslakHatasi(
            f"'{baslik}' bölümü boş gönderildi. En az bir öğe gerekiyor: "
            '{"tur": "paragraf", "metin": "..."}'
        )

    for sira, oge in enumerate(ogeler, start=1):
        yer = f"'{baslik}' bölümü, {sira}. öğe"

        if not isinstance(oge, dict):
            raise TaslakHatasi(f"{yer}: nesne olmalı, {type(oge).__name__} geldi.")

        tur = oge.get("tur", "paragraf")

        if tur not in _OGE_ALANLARI:
            raise TaslakHatasi(
                f"{yer}: bilinmeyen tür {tur!r}. "
                f"Geçerli türler: {', '.join(sorted(_OGE_ALANLARI))}."
            )

        for alan in _OGE_ALANLARI[tur]:
            deger = oge.get(alan)

            if alan == "metin":
                if not isinstance(deger, str) or not deger.strip():
                    raise TaslakHatasi(
                        f"{yer} ({tur}): 'metin' dolu bir yazı olmalı. "
                        'Doğru şekli: {"tur": "%s", "metin": "..."}' % tur
                    )
            elif not isinstance(deger, list) or not deger:
                raise TaslakHatasi(
                    f"{yer} (tablo): '{alan}' dolu bir dizi olmalı. "
                    'Doğru şekli: {"tur": "tablo", "baslik": "Tablo 1: ...", '
                    '"basliklar": ["A","B"], "satirlar": [["1","2"]]}'
                )


def kapak_alanlarini_dogrula(alanlar: dict) -> None:
    """Kapakta tanınmayan alan varsa reddet.

    Sessizce yutmak, modelin ``rapor_date`` yazıp tarihin boş kalmasına yol
    açıyordu -- belge [EKSİK] ile basıldı ve kimse fark etmedi.
    """
    bilinmeyen = sorted(set(alanlar) - _KAPAK_ALANLARI)

    if bilinmeyen:
        raise TaslakHatasi(
            f"Kapakta tanınmayan alan: {', '.join(bilinmeyen)}. "
            f"Geçerli alanlar: {', '.join(sorted(_KAPAK_ALANLARI))}."
        )


def ozet_yaz(kimlik: str, satirlar: list[str]) -> Taslak:
    """Özeti yaz -- ÜZERİNE yazar.

    Ayrı bir işlem, çünkü özet doğal olarak EN SON yazılıyor: MADDE 7 özeti
    "raporun her 30 sayfası için en fazla 1 sayfa" diye tanımlıyor, yani
    metnin ne kadar olduğu bilinmeden yazılamıyor. ``baslat`` sırasında
    istemek, modeli daha hiçbir bölüm yokken özet uydurmaya zorlardı.
    """
    temiz = [str(s).strip() for s in satirlar if str(s).strip()]

    if not temiz:
        raise TaslakHatasi(
            "Özet boş gönderildi. En az bir cümle gerekiyor "
            "(MADDE 7: kapak ile rapor metni arasında özet sayfası bulunur)."
        )

    taslak = yukle(kimlik)
    taslak.ozet = temiz
    _yaz(taslak)

    return taslak


def delil_ekle(kimlik: str, kart: dict, yol: str) -> Taslak:
    """Bir delil belgesini taslağa bağla ve ek dizinine yaz.

    Ek numarası ekleme sırasından geliyor (MADDE 10(4): rapora ilk konu
    edilen eke ilk numara). Aynı belge iki kez eklenmiyor -- MADDE 10(8)
    "bir belge rapora birden fazla ek yapılmaz" diyor.
    """
    taslak = yukle(kimlik)

    for mevcut in taslak.deliller:
        if mevcut.get("yol") == yol:
            raise TaslakHatasi(
                f"bu belge zaten Ek:{mevcut.get('ek_no')} olarak ekli "
                "(MADDE 10(8): bir belge rapora birden fazla ek yapılmaz). "
                f"Atıf için (Ek: {mevcut.get('ek_no')}/1) kullan."
            )

    ek_no = len(taslak.ekler) + 1
    kayit = {**kart, "ek_no": ek_no, "yol": yol}

    taslak.deliller.append(kayit)
    taslak.ekler.append(
        {
            "no": ek_no,
            "icerik": kart.get("icerik") or kart.get("ad", ""),
            "sayfa_sayisi": int(kart.get("sayfa_sayisi", 1)),
        }
    )
    _yaz(taslak)

    return taslak


def delil_yolu(kimlik: str, ek_no: int) -> str:
    """Bir ekin dosya yolu."""
    taslak = yukle(kimlik)

    for delil in taslak.deliller:
        if int(delil.get("ek_no", 0)) == int(ek_no):
            return str(delil.get("yol", ""))

    raise TaslakHatasi(f"Ek:{ek_no} bu taslakta yok")
