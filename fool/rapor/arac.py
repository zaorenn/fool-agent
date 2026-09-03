"""
Ajan araçları: resmî rapor okuma, öğrenme, tamamlama ve yazma.

Neden araç, neden bilgi istemi değil
------------------------------------
Bu işlerin hiçbiri modele anlatılarak yaptırılmıyor. Kenar boşluğunu, Türkçe
büyük harfi, ek numaralandırmasını, bozuk PDF tespitini kod yapıyor; model
yalnızca İÇERİK üretiyor. 70 sayfalık resmî bir evrakta biçim tutarlılığını
bir dil modelinin dikkatine bırakmak, kullanıcının "hata payı yok" şartıyla
bağdaşmıyor.

Araçlar bilerek dar
-------------------
Her araç tek bir soruya cevap veriyor ve JSON döndürüyor. Modelin bağlamı
64-128 bin token; araçlar bu yüzden metin YIĞMIYOR: büyük belgelerden sorguya
uyan kesitleri, örnek rapordan iskeleti, yarım rapordan eksik listesini
döndürüyorlar.

Zone A: upstream bu dosyayı bilmiyor.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .bicim_devral import devral, yonergeye_uygunluk
from .cozumle import bolumlere_ayir, eksik_bolumler, iskelet_cikar, tur_tahmin
from .docx_yazici import yaz
from .kaynak import oku, token_tahmini
from .pdf_cikti import pdf_uret
from .sayfa_toplami import sabitle as _toplami_sabitle
from .model import EKSIK, Alinti, AltBaslik, Bolum, Ek, Kapak, Paragraf, Rapor, Tablo
from . import sartname as _sartname
from . import sayfa_hedefi, taslak, uygunluk, yonerge_ogren
from .secici import ilgili_kesitler
from .yonerge import RAPOR_TURLERI


def _hata(mesaj: str, **ek: Any) -> str:
    return json.dumps({"error": mesaj, **ek}, ensure_ascii=False)


def _sonuc(veri: dict) -> str:
    return json.dumps(veri, ensure_ascii=False)


# ---------------------------------------------------------------------------
# 1. Kaynak okuma -- tamamı ya da yalnızca sorguya uyan kısmı
# ---------------------------------------------------------------------------


def kaynak_oku(
    yol: str,
    sorgu: str | None = None,
    token_butcesi: int = 8000,
) -> str:
    """Belgeyi oku. ``sorgu`` verilirse yalnızca ilgili kesitler döner.

    Kalite denetimi HER ZAMAN çalışıyor: bozuk çıkarılmış bir metin modele
    gitmeden önce işaretleniyor (bkz. ``kaynak.kalite_olc``).
    """
    hedef = Path(yol)

    if not hedef.exists():
        return _hata(f"belge bulunamadı: {yol}")

    try:
        belge = oku(hedef)
    except Exception as sebep:  # noqa: BLE001 -- sebep kullaniciya gosteriliyor
        return _hata(f"belge okunamadı: {sebep}")

    kalite = belge.kalite

    if not kalite.guvenilir:
        # Metin DONDURULMUYOR. Bozuk metni "yine de al" diye vermek, raporun
        # icine bozuk yazimin girmesi demek -- kullanicinin en acik sarti buna
        # aykiri.
        return _sonuc(
            {
                "belge": belge.ad,
                "sayfa_sayisi": belge.sayfa_sayisi,
                "guvenilir": False,
                "gerekce": kalite.gerekce,
                "oneri": (
                    "Bu belgenin metin katmanı bozuk. İçeriği rapora "
                    "kullanmadan önce OCR'lı bir kopya gerekiyor; bozuk metin "
                    "bilerek döndürülmedi."
                ),
            }
        )

    if sorgu:
        kesitler = ilgili_kesitler(belge, sorgu, token_butcesi=token_butcesi)

        return _sonuc(
            {
                "belge": belge.ad,
                "guvenilir": True,
                "sayfa_sayisi": belge.sayfa_sayisi,
                "toplam_token": token_tahmini(belge.metin),
                "secilen_token": sum(token_tahmini(k.metin) for k in kesitler),
                "kesitler": [
                    {"baslik": k.baslik, "atif": k.atif, "metin": k.metin}
                    for k in kesitler
                ],
            }
        )

    toplam = token_tahmini(belge.metin)

    if toplam > token_butcesi:
        return _sonuc(
            {
                "belge": belge.ad,
                "guvenilir": True,
                "sayfa_sayisi": belge.sayfa_sayisi,
                "toplam_token": toplam,
                "uyari": (
                    f"Belge {toplam} token, bütçe {token_butcesi}. Tamamını "
                    "okumak yerine `sorgu` vererek ilgili kısmı iste."
                ),
            }
        )

    return _sonuc(
        {
            "belge": belge.ad,
            "guvenilir": True,
            "sayfa_sayisi": belge.sayfa_sayisi,
            "toplam_token": toplam,
            "metin": belge.metin,
        }
    )


# ---------------------------------------------------------------------------
# 1b. Yönergeden öğrenme -- örnek rapordan DEĞİL, kuralları anlatan metinden
# ---------------------------------------------------------------------------


def yonerge_ogren_arac(
    yol: str,
    kimlik: str,
    bolum_secimi: str = "",
    sayfa_en_az: int = 0,
    sayfa_en_cok: int = 0,
) -> str:
    """Yönergeyi oku, şartname çıkar ve diske kaydet.

    Yönergenin METNİ dönmüyor -- 70 sayfa zaten bağlama sığmıyor ve amaç
    onu bağlamda tutmak değil, KURALA çevirmek. Dönen şey gözden geçirilecek
    özet: her kural yanında yönergenin kendi maddesiyle.
    """
    try:
        ogrenme = yonerge_ogren.ogren(
            yol, kimlik, bolum_secimi, sayfa_en_az, sayfa_en_cok
        )
    except (FileNotFoundError, ValueError) as sebep:
        return _hata(str(sebep))
    except _sartname.SartnameHatasi as sebep:
        return _hata(str(sebep))

    try:
        kayit = _sartname.kaydet(ogrenme.sartname)
    except _sartname.SartnameHatasi as sebep:
        return _hata(str(sebep))

    secilen = ogrenme.sartname

    return _sonuc(
        {
            "sartname": secilen.kimlik,
            "kaydedildi": str(kayit),
            "yonerge": secilen.kaynak,
            "birim_sayisi": ogrenme.birim_sayisi,
            "ozet": secilen.ozet_metni(),
            "bolum_sayisi": len(secilen.bolumler),
            "secilen_iskelet": secilen.bolum_dayanagi,
            # Yonergede birden cok rapor turu tanimliysa SECIM gizlenmiyor:
            # arac en uzun listeyi sectiyse bile digerleri burada duruyor ve
            # tek cagriyla degistirilebiliyor.
            "diger_iskeletler": [
                {
                    "dayanak": a.dayanak,
                    "baslik": a.baslik,
                    "bolum_sayisi": len(a.bolumler),
                    "bolumler": list(a.bolumler),
                }
                for a in ogrenme.bolum_adaylari
                if a.dayanak != secilen.bolum_dayanagi
            ],
            "eksik_kurallar": list(secilen.eksik_kurallar),
            "uyari": (
                "Bu şartnameyi kullanıcıya GÖSTER ve onaylat. Çıkarım kurallı "
                "yapıldı ve yanılabilir; yanlış bir kural 20 sayfalık belgeyi "
                "sessizce bozar."
            ),
        }
    )


def sartname_goster(kimlik: str = "") -> str:
    """Kayıtlı şartnameyi göster; kimlik verilmezse hepsini listele."""
    if not kimlik:
        return _sonuc({"sartnameler": _sartname.listele()})

    try:
        kayitli = _sartname.yukle(kimlik)
    except _sartname.SartnameHatasi as sebep:
        return _hata(str(sebep), sartnameler=_sartname.listele())

    return _sonuc(
        {
            "sartname": kayitli.kimlik,
            "ad": kayitli.ad,
            "yonerge": kayitli.kaynak,
            "ozet": kayitli.ozet_metni(),
            "bolumler": list(kayitli.bolumler),
            "sayfa_en_az": kayitli.sayfa_en_az,
            "sayfa_en_cok": kayitli.sayfa_en_cok,
            "zorunlu_ifadeler": list(kayitli.zorunlu_ifadeler),
            "kapanis_ifadesi": kayitli.kapanis_ifadesi,
            "eksik_kurallar": list(kayitli.eksik_kurallar),
        }
    )


# ---------------------------------------------------------------------------
# 2. Örnek rapordan öğrenme
# ---------------------------------------------------------------------------


def ornek_ogren(yol: str) -> str:
    """Örnek rapordan yazım iskeletini çıkar.

    Örneğin METNİ dönmüyor: başka bir soruşturmanın isim ve tarihlerinin yeni
    rapora sızmaması için yalnızca biçim bilgisi veriliyor.
    """
    hedef = Path(yol)

    if not hedef.exists():
        return _hata(f"örnek rapor bulunamadı: {yol}")

    try:
        belge = oku(hedef)
    except Exception as sebep:  # noqa: BLE001
        return _hata(f"örnek okunamadı: {sebep}")

    if not belge.kalite.guvenilir:
        return _hata(
            "örnek raporun metni güvenilir değil", gerekce=belge.kalite.gerekce
        )

    iskelet = iskelet_cikar(belge)

    try:
        devralinan = devral(hedef)
        bicim = {
            "yazi_tipi": devralinan.bicim.yazi_tipi,
            "punto": devralinan.bicim.yazi_boyut / 2,
            "hizalama": devralinan.bicim.hizalama,
            "okunamayan": devralinan.okunamayan,
        }
    except Exception:  # noqa: BLE001 -- bicim okunamazsa iskelet yine degerli
        bicim = {}

    return _sonuc(
        {
            "ornek": belge.ad,
            "iskelet": iskelet.metin(),
            "bolumler": iskelet.bolumler,
            "ek_atif_bicimi": iskelet.ek_atif_bicimi,
            "sonuc_alt_basliklari": iskelet.alt_basliklar,
            "bicim": bicim,
            "iskelet_token": token_tahmini(iskelet.metin()),
            "ornek_token": token_tahmini(belge.metin),
        }
    )


# ---------------------------------------------------------------------------
# 3. Yarım raporu çözümle
# ---------------------------------------------------------------------------


def yarim_cozumle(yol: str) -> str:
    """Yarım raporun neyi var, neyi eksik ve hangi biçimde yazılmış?

    Yarım rapor HER ZAMAN eksiksiz okunuyor: atlanan bir paragraf, zaten
    yazılmış olanla çelişen bir tamamlama demek.
    """
    hedef = Path(yol)

    if not hedef.exists():
        return _hata(f"rapor bulunamadı: {yol}")

    try:
        belge = oku(hedef)
    except Exception as sebep:  # noqa: BLE001
        return _hata(f"rapor okunamadı: {sebep}")

    if not belge.kalite.guvenilir:
        return _hata(
            "tamamlanacak raporun metni güvenilir değil",
            gerekce=belge.kalite.gerekce,
        )

    cozumlenmis = bolumlere_ayir(belge)
    tur = tur_tahmin(cozumlenmis)
    eksikler = eksik_bolumler(cozumlenmis, tur)

    try:
        devralinan = devral(hedef)
        farklar = [str(f) for f in yonergeye_uygunluk(devralinan.bicim)]
        bicim = {
            "yazi_tipi": devralinan.bicim.yazi_tipi,
            "punto": devralinan.bicim.yazi_boyut / 2,
            "satir_araligi": devralinan.bicim.satir_araligi,
            "hizalama": devralinan.bicim.hizalama,
            "kenar_sol": devralinan.bicim.kenar_sol,
            "kenar_ust": devralinan.bicim.kenar_ust,
            "okunamayan": devralinan.okunamayan,
            "yonergeden_farklar": farklar,
        }
    except Exception as sebep:  # noqa: BLE001
        bicim = {"hata": f"biçim okunamadı: {sebep}"}

    return _sonuc(
        {
            "rapor": belge.ad,
            "tur": tur.kimlik if tur else None,
            "tur_adi": tur.ad if tur else None,
            "mevcut_bolumler": [
                {"baslik": b.baslik, "karakter": b.karakter, "bos": b.bos}
                for b in cozumlenmis.bolumler
            ],
            "eksik_bolumler": [
                {"baslik": e.baslik, "durum": e.durum} for e in eksikler
            ],
            "bicim": bicim,
            "tam_metin": belge.metin,
            "not": (
                "Tamamlarken bu biçimi kullan: aynı yazı tipi, punto ve "
                "hizalama. Yönergeden farklar bildirildi ama DÜZELTİLMEDİ; "
                "belgeyi ortasından değiştirmek müfettişin kararı."
            ),
        }
    )


# ---------------------------------------------------------------------------
# 4. Raporu yaz
# ---------------------------------------------------------------------------


def _oge_kur(ham: dict) -> Any:
    tur = (ham.get("tur") or "paragraf").lower()

    if tur == "alt_baslik":
        return AltBaslik(ham.get("metin", ""))

    if tur == "alinti":
        return Alinti(
            ham.get("metin", ""), ham.get("kaynak", ""), ham.get("ek", "")
        )

    if tur == "tablo":
        return Tablo(
            ham.get("baslik", ""),
            list(ham.get("basliklar", [])),
            [list(s) for s in ham.get("satirlar", [])],
        )

    return Paragraf(
        ham.get("metin", ""),
        kalin=bool(ham.get("kalin", False)),
        ek=ham.get("ek", ""),
    )


def rapor_yaz(
    rapor_json: str | dict,
    hedef: str,
    bicim_kaynagi: str | None = None,
    sartname_kimligi: str | None = None,
    zorla: bool = False,
) -> str:
    """Yapılandırılmış rapordan ``.docx`` üret.

    ``bicim_kaynagi`` verilirse biçim O BELGEDEN devralınıyor -- yarım bir
    raporu aynı fontla tamamlamanın yolu bu.

    ``sartname_kimligi`` verilirse biçim YÖNERGEDEN geliyor ve rapor
    üretilmeden önce şartnameye karşı denetleniyor; engel varsa belge
    YAZILMIYOR. Bu katılık yalnızca şartnameli yola ait: kullanıcı yönergeyi
    bilerek verdiyse "hata payı yok" şartı devrededir. Şartnamesiz çağrılar
    eskisi gibi davranıyor, yoksa koda gömülü dört türle çalışan mevcut akış
    bir anda üretmeyi bırakırdı.
    """
    try:
        veri = json.loads(rapor_json) if isinstance(rapor_json, str) else rapor_json
    except json.JSONDecodeError as sebep:
        return _hata(f"rapor JSON çözümlenemedi: {sebep}")

    if not isinstance(veri, dict):
        return _hata("rapor JSON bir nesne olmalı")

    tur = veri.get("tur", "inceleme")

    # Sartname, sozlukte tasiniyorsa oradan da alinabiliyor: ``taslak_uret``
    # taslagi cevirirken kimligi icine koyuyor ve arada elden ele gecmesi
    # gerekmiyor.
    kayitli = _sartname.varsa_yukle(sartname_kimligi or veri.get("sartname"))

    if kayitli is None and tur not in RAPOR_TURLERI:
        return _hata(
            f"bilinmeyen rapor türü: {tur}",
            gecerli=sorted(RAPOR_TURLERI),
            oneri=(
                "Kendi yönergen varsa önce rapor_yonerge_ogren ile şartname "
                "çıkar ve sartname_kimligi ver."
            ),
        )

    if kayitli is not None and not zorla:
        denetim = uygunluk.denetle(veri, kayitli)

        if not denetim.uygun:
            # Belge YAZILMIYOR. Yonergeye aykiri bir resmi evrak uretmek,
            # uretmemekten kotu: dosyaya dusen sey imzalaniyor.
            return _hata(
                "rapor şartnameye uygun değil; belge yazılmadı",
                sartname=kayitli.kimlik,
                engeller=[b.sozluk() for b in denetim.engeller],
                uyarilar=[b.sozluk() for b in denetim.uyarilar],
                oneri=(
                    "Engelleri gider ve tekrar dene. Gerçekten böyle "
                    "üretilmesi gerekiyorsa zorla=true gönder."
                ),
            )

    kapak_ham = veri.get("kapak", {})
    kapak = Kapak(
        **{
            alan: kapak_ham[alan]
            for alan in (
                "bakanlik", "baskanlik", "baslik", "konu",
                "gorev_emri_tarih", "gorev_emri_sayi", "rapor_tarih",
                "rapor_sayi", "ek_adedi", "mufettis_ad", "mufettis_unvan",
            )
            if alan in kapak_ham
        },
        gizli=bool(kapak_ham.get("gizli", False)),
    )

    # Bolumler YONERGEDEKI siraya diziliyor: model istedigi sirada
    # gonderebiliyor ve sirasi karismis bir resmi rapor yonergeye aykiri.
    bolumler = []
    for ham in taslak.sirala(
        list(veri.get("bolumler", [])),
        tur,
        list(kayitli.bolumler) if kayitli else None,
    ):
        bolum = Bolum(ham.get("baslik", ""))
        ogeler = list(ham.get("ogeler", []))

        # Sekli ANLASILMAYAN oge sessizce bos paragrafa donusmuyor: modelin
        # bozuk yapisi bes bolumu de bos birakmisti ve arac "basarili"
        # demisti (bkz. taslak.ogeleri_dogrula).
        try:
            taslak.ogeleri_dogrula(ogeler, bolum.baslik)
            bolum.ogeler = [_oge_kur(o) for o in ogeler]
        except (taslak.TaslakHatasi, ValueError) as sebep:
            return _hata(str(sebep))

        bolumler.append(bolum)

    ekler = [
        Ek(
            no=int(e.get("no", i + 1)),
            icerik=e.get("icerik", ""),
            sayfa_sayisi=int(e.get("sayfa_sayisi", 1)),
        )
        for i, e in enumerate(veri.get("ekler", []))
    ]

    rapor = Rapor(
        tur=tur,
        kapak=kapak,
        bolumler=bolumler,
        ozet=list(veri.get("ozet", [])),
        ekler=ekler,
        # Verilmeyen imza alani UYDURULMUYOR: EKSIK olarak belgede kaliyor
        # ve ``eksikler()`` bunu imzadan once listeliyor.
        imza_yer=veri.get("imza_yer") or EKSIK,
        imza_tarih=veri.get("imza_tarih") or EKSIK,
    )

    # Bicim onceligi: YARIM RAPOR > SARTNAME > gomulu varsayilan.
    #
    # Yarim rapor once geliyor cunku onu tamamlamanin sarti "ayni font, ayni
    # punto" (bkz. ``bicim_devral``): elindeki belgenin ikinci yarisini
    # yonergeye uydurmak, ortaya yarisi farkli gorunen tek bir evrak cikarir.
    # Yonergeye aykiriysa fark ``yonergeye_uygunluk`` ile bildiriliyor, karar
    # mufettisin.
    bicim = kayitli.bicim() if kayitli else None
    devralindi = None

    if bicim_kaynagi:
        kaynak_yolu = Path(bicim_kaynagi)

        if not kaynak_yolu.exists():
            return _hata(f"biçim kaynağı bulunamadı: {bicim_kaynagi}")

        try:
            devralinan = devral(kaynak_yolu)
            bicim = devralinan.bicim
            devralindi = {
                "kaynak": devralinan.kaynak,
                "yazi_tipi": bicim.yazi_tipi,
                "punto": bicim.yazi_boyut / 2,
                "okunamayan": devralinan.okunamayan,
            }
        except Exception as sebep:  # noqa: BLE001
            return _hata(f"biçim devralınamadı: {sebep}")

    try:
        yazilan = yaz(rapor, hedef, bicim)
    except Exception as sebep:  # noqa: BLE001
        return _hata(f"docx yazılamadı: {sebep}")

    eksikler = rapor.eksikler()

    # Sayfa toplamini SABITLE.
    #
    # ``SECTIONPAGES`` alanini Word hesapliyor, LibreOffice hesaplamiyor:
    # olculdu, uc sayfalik metin "1/1, 2/1, 3/1" cikti. Yonergenin istedigi
    # "1/3". Belgeyi bir kez bastirip metin sayfalarini sayiyor ve toplami
    # duz sayi olarak yaziyoruz; boylece hangi programla acildigina bagli
    # olmuyor.
    sabitleme = _toplami_sabitle(yazilan)

    # Sayfa araligi denetimi BURADAN besleniyor, ikinci bir donusturmeden
    # degil: ``sabitle`` belgeyi zaten bir kez bastirip metin sayfalarini
    # saydi. Ayni sayiyi yeniden uretmek icin LibreOffice'i tekrar cagirmak
    # olculu olarak saniyeler suruyor ve ayni cevabi verirdi.
    sayfa_notu = None

    if kayitli is not None and kayitli.sayfa_araligi_var_mi():
        sayfa_notu = sayfa_hedefi.degerlendir(
            sabitleme.metin_sayfasi,
            kayitli.sayfa_en_az,
            kayitli.sayfa_en_cok,
            veri,
            olculdu=bool(sabitleme.metin_sayfasi),
            gerekce=sabitleme.gerekce,
        ).sozluk()

    return _sonuc(
        {
            "yazildi": str(yazilan),
            "metin_sayfasi": sabitleme.metin_sayfasi or None,
            "sayfa_denetimi": sayfa_notu,
            "sayfa_toplami_notu": None if sabitleme.yapildi else sabitleme.gerekce,
            "bayt": yazilan.stat().st_size,
            "tur": tur,
            "bolum_sayisi": len(bolumler),
            "ek_sayisi": len(ekler),
            "bicim_devralindi": devralindi,
            "eksik_alanlar": eksikler,
            "uyari": (
                "Doldurulmamış alanlar var; belgede [EKSİK] olarak duruyor. "
                "İmzadan önce tamamlanmalı."
            )
            if eksikler
            else None,
        }
    )


# ---------------------------------------------------------------------------
# 5. Parça parça rapor kurma
# ---------------------------------------------------------------------------
#
# Tek dev JSON yerine biriken taslak. Gerekçe ``taslak.py`` başında ölçümle
# yazılı: yerel model uzun bir yapıyı yeniden kurarken alan düşürüyor, ve 70
# sayfalık bir rapor zaten tek çağrıya sığmıyor.


def taslak_baslat(
    kimlik: str,
    tur: str = "inceleme",
    kapak: dict | None = None,
    ozet: list | None = None,
    imza_yer: str = "",
    imza_tarih: str = "",
    sifirla: bool = False,
    ornek_rapor: str | None = None,
    sartname_kimligi: str = "",
) -> str:
    """Yeni bir rapor taslağı aç.

    ``ornek_rapor`` verilirse bölüm uzunlukları oradan HEDEF olarak alınıyor:
    kullanıcının şartı "örnek rapordan kısa olamaz" ve bunu güvence altına
    almanın yolu örneği ÖLÇMEK, modelin uzun yazacağını ummak değil.

    ``sartname_kimligi`` verilirse bölüm listesi, biçim ve sayfa aralığı
    kullanıcının KENDİ yönergesinden geliyor; koda gömülü dört tür devre
    dışı kalıyor.
    """
    if sartname_kimligi and _sartname.varsa_yukle(sartname_kimligi) is None:
        # Kayitli olmayan bir sartname kimligi SESSIZCE gecilmiyor: taslak
        # acilir, bolum listesi bos gelir ve "eksik bolum yok" diye okunurdu
        # -- yani hicbir denetimi olmayan bir rapor uretilirdi.
        return _hata(
            f"şartname bulunamadı: {sartname_kimligi}",
            kayitli=_sartname.listele(),
            oneri="Önce rapor_yonerge_ogren ile yönergeden şartname çıkar.",
        )

    hedef: dict[str, int] = {}

    if ornek_rapor:
        try:
            belge = oku(Path(ornek_rapor))
            hedef = {
                b: int(u) for b, u in iskelet_cikar(belge).bolum_uzunluklari.items()
            }
        except Exception as sebep:  # noqa: BLE001
            return _hata(f"örnek rapor okunamadı: {sebep}")

    try:
        taslak.baslat(
            kimlik,
            tur,
            kapak=kapak,
            ozet=list(ozet or []),
            imza_yer=imza_yer,
            imza_tarih=imza_tarih,
            sifirla=sifirla,
            hedef_uzunluk=hedef,
            sartname_kimligi=sartname_kimligi,
        )
    except taslak.TaslakHatasi as sebep:
        return _hata(str(sebep))

    return _sonuc(taslak.durum(kimlik))


def taslak_bolum(kimlik: str, baslik: str, ogeler: list | None = None) -> str:
    """Taslağa tek bir bölüm yaz (aynı başlık gelirse üzerine yazar)."""
    try:
        taslak.bolum_ekle(kimlik, baslik, list(ogeler or []))
    except taslak.TaslakHatasi as sebep:
        return _hata(str(sebep))

    return _sonuc(taslak.durum(kimlik))


def taslak_ek(kimlik: str, icerik: str, sayfa_sayisi: int = 1) -> str:
    """Ek dizinine bir kayıt ekle."""
    try:
        taslak.ek_ekle(kimlik, icerik, sayfa_sayisi)
    except taslak.TaslakHatasi as sebep:
        return _hata(str(sebep))

    return _sonuc(taslak.durum(kimlik))


def taslak_kapak(kimlik: str, alanlar: dict | None = None) -> str:
    """Kapağın YALNIZCA verilen alanlarını güncelle."""
    try:
        taslak.kapak_guncelle(kimlik, dict(alanlar or {}))
    except taslak.TaslakHatasi as sebep:
        return _hata(str(sebep))

    return _sonuc(taslak.durum(kimlik))


def taslak_ozet(kimlik: str, satirlar: list | None = None) -> str:
    """Raporun özetini yaz (MADDE 7)."""
    try:
        taslak.ozet_yaz(kimlik, list(satirlar or []))
    except taslak.TaslakHatasi as sebep:
        return _hata(str(sebep))

    return _sonuc(taslak.durum(kimlik))


def taslak_durum(kimlik: str) -> str:
    """Taslakta ne var, yönergeye göre ne eksik?"""
    try:
        return _sonuc(taslak.durum(kimlik))
    except taslak.TaslakHatasi as sebep:
        return _hata(str(sebep))


def taslak_uret(kimlik: str, hedef: str, bicim_kaynagi: str | None = None) -> str:
    """Biriken taslaktan ``.docx`` üret."""
    try:
        sozluk = taslak.rapor_sozlugu(kimlik)
    except taslak.TaslakHatasi as sebep:
        return _hata(str(sebep))

    cevap = json.loads(rapor_yaz(sozluk, hedef, bicim_kaynagi))

    if "error" not in cevap:
        cevap["taslak_durumu"] = taslak.durum(kimlik)

    return _sonuc(cevap)


# ---------------------------------------------------------------------------
# 5b. Üretimden ÖNCE uygunluk, üretimden SONRA sayfa denetimi
# ---------------------------------------------------------------------------


def uygunluk_denetle(kimlik: str, sartname_kimligi: str = "") -> str:
    """Taslak şartnameye uyuyor mu? Uymuyorsa NEYİN eksik olduğunu söyle.

    Belge üretilmeden çağrılıyor: yanlış bir resmî evrakı üretip sonra
    bildirmek, onu hiç üretmemekten kötü -- üretilen belge imzalanıyor.
    """
    try:
        veri = taslak.yukle(kimlik)
    except taslak.TaslakHatasi as sebep:
        return _hata(str(sebep))

    kayitli = _sartname.varsa_yukle(sartname_kimligi or veri.sartname)
    denetim = uygunluk.denetle(veri.sozluk(), kayitli)
    cevap = denetim.sozluk()

    cevap["kimlik"] = kimlik
    cevap["sartname"] = kayitli.kimlik if kayitli else None
    cevap["siradaki_adim"] = (
        "Engel yok. rapor_taslak_uret ile .docx üret, sonra "
        "rapor_sayfa_denetle ile sayfa aralığını ölç."
        if denetim.uygun
        else "Engelleri gider: her biri için ilgili bölümü "
        "rapor_taslak_bolum ile yeniden yaz ya da rapor_taslak_kapak ile "
        "eksik alanı doldur, sonra bu aracı tekrar çağır."
    )

    return _sonuc(cevap)


def sayfa_denetle(
    docx: str, kimlik: str = "", en_az: int = 0, en_cok: int = 0
) -> str:
    """Üretilmiş raporun GERÇEK sayfa sayısını ölç ve hedefle karşılaştır.

    Hedef aralık öncelikle şartnameden geliyor (yönerge ne diyorsa), yoksa
    çağrıda verilen sayılardan. Sayfa sayısı hesaplanmıyor, belge bastırılıp
    SAYILIYOR -- gerekçe ``sayfa_hedefi`` modül başlığında.
    """
    sozluk: dict = {}
    kayitli = None

    if kimlik:
        try:
            veri = taslak.yukle(kimlik)
        except taslak.TaslakHatasi as sebep:
            return _hata(str(sebep))

        sozluk = veri.sozluk()
        kayitli = _sartname.varsa_yukle(veri.sartname)

    if kayitli is not None and kayitli.sayfa_araligi_var_mi():
        en_az = en_az or kayitli.sayfa_en_az
        en_cok = en_cok or kayitli.sayfa_en_cok

    if not en_az and not en_cok:
        return _hata(
            "hedef sayfa aralığı yok: şartnamede yazmıyor ve çağrıda da "
            "verilmedi (en_az / en_cok)"
        )

    denetim = sayfa_hedefi.denetle(docx, en_az, en_cok, sozluk)
    cevap = denetim.sozluk()
    cevap["belge"] = docx

    return _sonuc(cevap)


def rapor_pdf(docx: str, hedef_klasor: str | None = None) -> str:
    """Üretilmiş bir ``.docx`` raporu PDF'e çevir."""
    sonuc = pdf_uret(docx, hedef_klasor)

    if not sonuc.basarili:
        return _hata(sonuc.gerekce, donusturucu=sonuc.donusturucu or None)

    return _sonuc(
        {
            "pdf": str(sonuc.yol),
            "bayt": sonuc.yol.stat().st_size,
            "donusturucu": sonuc.donusturucu,
        }
    )


# ---------------------------------------------------------------------------
# 6. Deliller -- ifade tutanakları, şikâyet dilekçeleri
# ---------------------------------------------------------------------------
#
# İş bölümü: ÖRNEK rapor üslubu öğretiyor, DELİLLER içeriği veriyor. Şirket
# adı, kişi, tarih ve sayı buradan geliyor -- örnekten değil. Örneğin
# içeriğinin yeni rapora sızmaması bilerek engelleniyor (bkz. ``cozumle``).


def delil_ekle(kimlik: str, yol: str, icerik: str | None = None) -> str:
    """Bir ifade/şikâyet belgesini rapora dayanak yap.

    Belge okunuyor, kalitesi ölçülüyor, künyesi çıkarılıyor ve ek dizinine
    yazılıyor. TAM METİN taslağa kopyalanmıyor: diskte duruyor ve
    ``rapor_delil_oku`` ile parça parça okunuyor -- on dilekçenin tamamı
    bağlama sığmıyor.
    """
    hedef = Path(yol)

    if not hedef.exists():
        return _hata(f"delil bulunamadı: {yol}")

    try:
        belge = oku(hedef)
    except Exception as sebep:  # noqa: BLE001
        return _hata(f"delil okunamadı: {sebep}")

    if not belge.kalite.guvenilir:
        return _hata(
            f"'{belge.ad}' metni güvenilir değil; rapora dayanak yapılmadı",
            gerekce=belge.kalite.gerekce,
        )

    from .kaynak import kart_cikar

    kart = kart_cikar(belge, ek_no=0)
    kunye = {
        "ad": kart.ad,
        "tur": kart.tur,
        "tarih": kart.tarih,
        "sayi": kart.sayi,
        "kisiler": kart.kisiler,
        "sayfa_sayisi": kart.sayfa_sayisi,
        "icerik": icerik or f"{kart.tur or 'Belge'} - {kart.ad}",
    }

    try:
        taslak.delil_ekle(kimlik, kunye, str(hedef))
    except taslak.TaslakHatasi as sebep:
        return _hata(str(sebep))

    durum = taslak.durum(kimlik)
    eklenen = taslak.yukle(kimlik).deliller[-1]

    return _sonuc(
        {
            "ek_no": eklenen["ek_no"],
            "kunye": kunye,
            "kurtarma": belge.kurtarma_aciklamasi or None,
            "atif_ornegi": f"(Ek: {eklenen['ek_no']}/1)",
            "ek_sayisi": durum["ek_sayisi"],
            "siradaki_adim": durum["siradaki_adim"],
        }
    )


def delil_listesi(kimlik: str) -> str:
    """Rapora dayanak yapılmış belgelerin künyeleri.

    Yalnızca künye dönüyor: on belgenin tam metni bağlama sığmaz, künyeleri
    sığar. Model önce buraya bakıyor, sonra gerekeni açıyor.
    """
    try:
        veri = taslak.yukle(kimlik)
    except taslak.TaslakHatasi as sebep:
        return _hata(str(sebep))

    return _sonuc(
        {
            "kimlik": kimlik,
            "deliller": [
                {
                    "ek_no": d.get("ek_no"),
                    "ad": d.get("ad"),
                    "tur": d.get("tur"),
                    "tarih": d.get("tarih"),
                    "sayi": d.get("sayi"),
                    "kisiler": d.get("kisiler", []),
                    "sayfa_sayisi": d.get("sayfa_sayisi"),
                    "atif": f"(Ek: {d.get('ek_no')}/1)",
                }
                for d in veri.deliller
            ],
        }
    )


def delil_oku(kimlik: str, ek_no: int, sorgu: str | None = None,
              token_butcesi: int = 4000) -> str:
    """Bir delilin ilgili kısımlarını oku.

    ``sorgu`` verilirse yalnızca ona uyan kesitler dönüyor; uzun bir ifade
    tutanağının tamamını bağlama koymak gereksiz ve çoğu zaman imkânsız.
    """
    try:
        yol = taslak.delil_yolu(kimlik, int(ek_no))
    except taslak.TaslakHatasi as sebep:
        return _hata(str(sebep))

    cevap = json.loads(kaynak_oku(yol, sorgu=sorgu, token_butcesi=token_butcesi))

    if "error" not in cevap:
        cevap["ek_no"] = int(ek_no)
        cevap["atif"] = f"(Ek: {int(ek_no)}/1)"

    return _sonuc(cevap)
