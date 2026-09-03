"""
Yönergeden çıkarılmış ŞARTNAME: raporun uyması gereken kuralların makine
tarafından denetlenebilir hâli.

Neden ``yonerge.py`` yetmiyor
-----------------------------
``yonerge.py`` bir tabloya dört rapor türünü gömüyor ve bu tablo DSİ Teftiş
Kurulu yönergesinden elle okunmuş. Kullanıcının iş akışı bunu taşımıyor:
elinde 70 sayfalık bir yönerge var ve raporun nasıl yazılacağını O anlatıyor.
Yönerge değişince tablonun elle güncellenmesi gerekiyor -- yani "kod
değişmeden yönerge değişebilir" sözü tutulmuyor.

Şartname bu boşluğu kapatıyor: yönerge OKUNUYOR (``yonerge_ogren``), kurallar
çıkarılıyor ve buraya, tek bir JSON'a yazılıyor. Yazıcı da denetçi de aynı
şartnameyi okuyor, yani "yazılan" ile "denetlenen" aynı kaynaktan geliyor.
İkisi ayrı tablolardan beslenseydi biri güncellenip diğeri unutulduğunda
denetim yanlış "uygun" derdi -- ve resmî evrakta yanlış "uygun", hiç denetim
yapmamaktan kötü.

Neden her kural DAYANAĞIYLA duruyor
-----------------------------------
Kullanıcının şartı "hata payı yok". Bir çıkarım hatası (yönergede 2,5 cm
yazarken 2 cm okumak) sessizce 20 sayfalık bir belgeyi bozar. ``Kural.dayanak``
her değerin hangi maddeden ve hangi cümleden geldiğini taşıyor, ``ozet_metni``
bunu insan gözüyle bakılacak hâlde basıyor: müfettiş şartnameyi bir kez
onaylıyor, sonra yüzlerce sayfa ona göre üretiliyor.

Bulunamayan kural UYDURULMUYOR
------------------------------
``eksik_kurallar`` yönergede karşılığı bulunamayan alanları sayıyor. Bu liste
``model.EKSIK`` ile aynı fikirde: doldurulmamış bir alan görünür kalmalı.
Sessizce ``Bicim`` varsayılanına düşmek, "yönergene uydum" demenin yanlış
olduğu tek durumu gizlerdi -- yönergenin o konuda ne dediğini hiç okumamışken.

Zone A: upstream bu dosyayı bilmiyor.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .yonerge import Bicim

#: Şartname kimliğinde yalnızca bunlar: kimlik dosya adı oluyor ve ``../``
#: gibi bir ad başka klasöre yazmaya çalışırdı (``taslak`` ile aynı gerekçe).
_GECERLI_KIMLIK = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


class SartnameHatasi(Exception):
    """Şartname işlemi yapılamadı."""


# ---------------------------------------------------------------------------
# Tek kural
# ---------------------------------------------------------------------------


@dataclass
class Kural:
    """Yönergeden çıkarılmış tek bir kural -- ve nereden geldiği.

    ``dayanak`` ve ``alinti`` denetim için değil GÖZDEN GEÇİRME için var:
    çıkarım kurallı ve dolayısıyla yanılabilir, o yüzden her değerin yanında
    yönergenin kendi cümlesi duruyor. Kullanıcı 70 sayfayı değil bu listeyi
    okuyor.
    """

    alan: str
    deger: Any
    dayanak: str = ""
    alinti: str = ""

    def __str__(self) -> str:
        yer = f" [{self.dayanak}]" if self.dayanak else ""
        return f"{self.alan} = {self.deger}{yer}"


# ---------------------------------------------------------------------------
# Şartname
# ---------------------------------------------------------------------------

#: ``Bicim`` alanlarından şartnamenin doldurabildikleri. Buradaki adlar
#: ``yonerge.Bicim`` alan adlarıyla BİREBİR: ara bir eşleme tablosu, iki
#: taraftan biri değiştiğinde sessizce kayardı.
BICIM_ALANLARI = (
    "sayfa_genislik",
    "sayfa_yukseklik",
    "kenar_sol",
    "kenar_sag",
    "kenar_ust",
    "kenar_alt",
    "yazi_tipi",
    "yazi_boyut",
    "satir_araligi",
    "hizalama",
    "paragraf_girinti",
    "paragraf_bosluk",
    "sayfa_no_hizalama",
)

#: Yönergede karşılığı ARANAN, bulunamazsa açıkça bildirilen alanlar.
#:
#: Hepsi değil: ``sayfa_no_hizalama`` gibi alanlar çoğu yönergede geçmiyor ve
#: her belgede "eksik" diye bağırmak listeyi işe yaramaz hâle getirirdi.
#: Burada yalnızca resmî bir rapor yönergesinin SÖYLEMEK ZORUNDA olduğu
#: şeyler var.
BEKLENEN_ALANLAR = (
    "yazi_tipi",
    "yazi_boyut",
    "kenar_sol",
    "kenar_sag",
    "kenar_ust",
    "kenar_alt",
)


@dataclass
class Sartname:
    """Bir yönergenin, rapor üretimini yönetecek kadarı."""

    kimlik: str
    ad: str = ""
    #: Şartnamenin çıkarıldığı yönerge dosyası.
    kaynak: str = ""
    #: Zorunlu bölümler, YÖNERGEDEKİ SIRAYLA. Sıra bağlayıcı.
    bolumler: list[str] = field(default_factory=list)
    #: Bölüm listesinin hangi maddeden geldiği.
    bolum_dayanagi: str = ""
    #: ``Bicim`` alan adı -> değer. Yalnızca yönergede YAZAN alanlar.
    bicim_degerleri: dict[str, Any] = field(default_factory=dict)
    #: Rapor metninin sayfa aralığı. 0 = yönerge bir şey söylememiş.
    sayfa_en_az: int = 0
    sayfa_en_cok: int = 0
    #: Sonuç bölümünde geçmesi gereken kesin ifadelerden EN AZ BİRİ.
    zorunlu_ifadeler: list[str] = field(default_factory=list)
    #: Raporun bittiği kalıp. Boşsa yönerge dayatmıyor.
    kapanis_ifadesi: str = ""
    #: Ek atıflarının şekli, örn. "(Ek: 5/3)".
    ek_atif_bicimi: str = ""
    #: Kapakta bulunması zorunlu alanların yönergedeki yazımı.
    kapak_alanlari: list[str] = field(default_factory=list)
    #: Çıkarılan her kural, dayanağıyla. Gözden geçirme buradan yapılıyor.
    kurallar: list[dict] = field(default_factory=list)
    #: Yönergede aranıp BULUNAMAYAN alanlar. Sessizce varsayılana düşülmedi;
    #: düşüldüğü burada yazıyor.
    eksik_kurallar: list[str] = field(default_factory=list)

    # -- kullanım ----------------------------------------------------------

    def bicim(self) -> Bicim:
        """Yazıcının kullanacağı biçim.

        Yönergede yazmayan alan ``Bicim`` varsayılanında kalıyor. Bu bir
        tahmin ve öyle olduğu ``eksik_kurallar``da yazıyor -- iki yer aynı
        gerçeği söylüyor, biri belgeyi üretiyor diğeri kullanıcıyı uyarıyor.
        """
        gecerli = {
            alan: deger
            for alan, deger in self.bicim_degerleri.items()
            if alan in BICIM_ALANLARI
        }

        return Bicim().ile(**gecerli)

    def kural(self, alan: str) -> Kural | None:
        for ham in self.kurallar:
            if ham.get("alan") == alan:
                return Kural(**ham)
        return None

    def sayfa_araligi_var_mi(self) -> bool:
        return self.sayfa_en_az > 0 or self.sayfa_en_cok > 0

    def sozluk(self) -> dict:
        return asdict(self)

    # -- gözden geçirme ----------------------------------------------------

    def ozet_metni(self) -> str:
        """Kullanıcının ONAYLAYACAĞI özet.

        70 sayfa okunmuyor, bu okunuyor. O yüzden her satır tek bir kural ve
        yanında yönergenin kendi maddesi: bir çıkarım yanlışsa burada
        görülüyor, 20 sayfalık bir belge üretildikten sonra değil.
        """
        satirlar = [f"ŞARTNAME: {self.ad or self.kimlik}"]

        if self.kaynak:
            satirlar.append(f"Kaynak yönerge: {self.kaynak}")

        satirlar += ["", "BÖLÜMLER (bu sırayla zorunlu):"]

        if self.bolumler:
            for sira, baslik in enumerate(self.bolumler, start=1):
                satirlar.append(f"  {sira}. {baslik}")
            if self.bolum_dayanagi:
                satirlar.append(f"  (dayanak: {self.bolum_dayanagi})")
        else:
            satirlar.append("  -- yönergede bölüm listesi bulunamadı --")

        satirlar += ["", "BİÇİM:"]

        for alan in BICIM_ALANLARI:
            if alan not in self.bicim_degerleri:
                continue
            kural = self.kural(alan)
            dayanak = f"  [{kural.dayanak}]" if kural and kural.dayanak else ""
            satirlar.append(f"  {alan} = {self.bicim_degerleri[alan]}{dayanak}")

        if self.sayfa_araligi_var_mi():
            satirlar += [
                "",
                f"SAYFA ARALIĞI: {self.sayfa_en_az or '?'}-{self.sayfa_en_cok or '?'} sayfa",
            ]

        if self.kapanis_ifadesi:
            satirlar += ["", f"KAPANIŞ İFADESİ: “{self.kapanis_ifadesi}”"]

        if self.zorunlu_ifadeler:
            satirlar += ["", "SONUÇTA GEÇMESİ GEREKEN İFADELERDEN BİRİ:"]
            satirlar += [f"  “{i}”" for i in self.zorunlu_ifadeler]

        if self.ek_atif_bicimi:
            satirlar += ["", f"EK ATIF BİÇİMİ: {self.ek_atif_bicimi}"]

        if self.kapak_alanlari:
            satirlar += ["", "KAPAK ALANLARI:"]
            satirlar += [f"  {a}" for a in self.kapak_alanlari]

        if self.eksik_kurallar:
            satirlar += [
                "",
                "YÖNERGEDE BULUNAMADI (varsayılan kullanılacak, gözden geçir):",
            ]
            satirlar += [f"  {a}" for a in self.eksik_kurallar]

        return "\n".join(satirlar)


# ---------------------------------------------------------------------------
# Diskte saklama
# ---------------------------------------------------------------------------
#
# Şartname oturumdan uzun yaşıyor: kullanıcı yönergeyi bir kez veriyor, sonra
# aylarca o yönergeye göre rapor yazılıyor. Bağlamda tutulsaydı her yeni
# oturumda 70 sayfa yeniden okunurdu.


def sartname_klasoru() -> Path:
    """Şartnamelerin durduğu yer.

    ``FOOL_RAPOR_SARTNAME_DIR`` ile değiştirilebiliyor; testler kendi geçici
    klasörünü veriyor, böylece kullanıcının gerçek şartnameleri test
    koşusundan etkilenmiyor (``taslak.taslak_klasoru`` ile aynı gerekçe).
    """
    ham = os.environ.get("FOOL_RAPOR_SARTNAME_DIR")
    yol = Path(ham) if ham else Path(tempfile.gettempdir()) / "fool-rapor-sartname"
    yol.mkdir(parents=True, exist_ok=True)

    return yol


def _sartname_yolu(kimlik: str) -> Path:
    if not _GECERLI_KIMLIK.match(kimlik):
        raise SartnameHatasi(
            f"geçersiz şartname kimliği: {kimlik!r} "
            "(yalnızca harf, rakam, nokta, tire, alt çizgi; en çok 64)"
        )

    return sartname_klasoru() / f"{kimlik}.json"


def kaydet(sartname: Sartname) -> Path:
    """Şartnameyi diske yaz."""
    yol = _sartname_yolu(sartname.kimlik)
    gecici = yol.with_suffix(".json.tmp")

    # Once gecici dosyaya, sonra yerine koy -- ``taslak._yaz`` ile ayni
    # gerekce: yarim yazilmis bir sartname, uzerine rapor uretilecek bir
    # kural kumesinin sessizce eksilmesi demek.
    gecici.write_text(
        json.dumps(sartname.sozluk(), ensure_ascii=False, indent=1), encoding="utf-8"
    )
    gecici.replace(yol)

    return yol


def yukle(kimlik: str) -> Sartname:
    yol = _sartname_yolu(kimlik)

    if not yol.exists():
        raise SartnameHatasi(f"şartname bulunamadı: {kimlik}")

    try:
        ham = json.loads(yol.read_text(encoding="utf-8"))
    except json.JSONDecodeError as sebep:
        raise SartnameHatasi(f"şartname bozuk: {sebep}") from sebep

    tanimli = {a.name for a in Sartname.__dataclass_fields__.values()}

    return Sartname(**{k: v for k, v in ham.items() if k in tanimli})


def listele() -> list[str]:
    """Kayıtlı şartname kimlikleri."""
    return sorted(y.stem for y in sartname_klasoru().glob("*.json"))


def sil(kimlik: str) -> None:
    _sartname_yolu(kimlik).unlink(missing_ok=True)


def varsa_yukle(kimlik: str | None) -> Sartname | None:
    """Kimlik verilmişse yükle, yoksa ``None``.

    Çağıranların çoğu "şartname varsa ona göre, yoksa yönerge tablosuna göre"
    diye çalışıyor; bu yardımcı o dalı tek yerde tutuyor.
    """
    if not kimlik:
        return None

    try:
        return yukle(kimlik)
    except SartnameHatasi:
        return None
