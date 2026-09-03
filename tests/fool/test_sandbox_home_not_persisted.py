"""Geçici bir ev KALICI olamaz.

Ölçülen hasar, tahmin değil
---------------------------
``npm run test:desktop:fresh`` ``install.ps1``i ``%TEMP%`` altındaki bir sandbox
eviyle çalıştırıyor (``hermes-desktop-fresh-install-*\\hermes-home``).
``install.ps1`` kurulumun sonunda ``FOOL_HOME``u KULLANICI kapsamına yazıyordu
ve test bittiğinde bu değeri kimse geri almıyordu.

Masaüstü uygulaması (``apps/desktop/electron/main.ts::resolveFoolHome``)
kullanıcı kapsamlı ``FOOL_HOME``u ``%LOCALAPPDATA%\\fool``dan **önce** okuyor --
Explorer'dan açılan bir GUI, login'den sonra ``setx`` ile ayarlanmış bir
değişkeni ``process.env``de göremediği için bilerek böyle yazılmıştı.

İkisi birleşince: test bir kere koştuktan sonra uygulama her açılışta BOŞ bir
test kutusuna giriyordu. Oturum geçmişi yok, profil yok, ses klonu yok,
``sidecars`` yok. Kullanıcının bildirdiği belirtiler tam olarak bunlar:
"girlfriend gitmiş, ses klonlarım gitmiş, sohbetlerim gitmiş, hiçbir TTS ve
STT çalışmıyor, modeller %70'te takılıyor" -- hiçbiri silinmemişti, uygulama
sadece başka bir yere bakıyordu.

Bu yüzden buradaki testler bir KULLANICI VERİSİ koruması: kapı kalkarsa hata
sessiz olur ve veri kaybı gibi görünür.
"""

from __future__ import annotations

from pathlib import Path

INSTALL = Path("scripts/install.ps1").read_text(encoding="utf-8")

#: Kalıcı yazmanın yapıldığı satır.
PERSIST = '[Environment]::SetEnvironmentVariable("FOOL_HOME", $FoolHome, "User")'


def test_sandbox_kapisi_DURUYOR() -> None:
    assert "$isSandboxHome" in INSTALL


def test_kapi_kalici_yazmanin_ONUNDE() -> None:
    """Kapı sonra gelirse hiçbir şey korunmaz."""
    gate = INSTALL.index("$isSandboxHome = $false")
    persist = INSTALL.index(PERSIST)

    assert gate < persist


def test_kalici_yazma_kapinin_ICINDE() -> None:
    """Yazma koşulsuz kalırsa kapı yalnızca bir log satırı olur."""
    gate = INSTALL.index("if ($isSandboxHome)")
    persist = INSTALL.index(PERSIST)
    tail = INSTALL[gate:persist]

    # Kalıcı yazma, sandbox DEĞİLKEN çalışan dala düşmeli.
    assert "} else {" in tail


def test_TEMP_altindaki_ev_sandbox_sayiliyor() -> None:
    """Sandbox'ın tanımı geçici dizin -- test betiğinin adı değil.

    Ada bakmak kırılgan olurdu: ``test-desktop.mjs`` yarın başka bir önek
    seçerse koruma sessizce düşerdi.
    """
    assert "$env:TEMP" in INSTALL
    assert "GetTempPath()" in INSTALL


def test_oturum_degiskeni_YINE_ayarlaniyor() -> None:
    """Sandbox kurulumu çalışmaya devam etmeli -- kalıcı olmayan tek şey yazma."""
    persist = INSTALL.index(PERSIST)
    after = INSTALL[persist : persist + 2000]

    assert "$env:FOOL_HOME = $FoolHome" in after


def test_masaustu_kullanici_kapsamini_OKUMAYA_devam_ediyor() -> None:
    """Okuma tarafı kaldırılarak "çözülmemeli".

    ``setx FOOL_HOME`` yapmış gerçek bir kullanıcı var ve GUI onu
    ``process.env``de göremiyor; okuma bu yüzden orada. Doğru düzeltme yazma
    tarafında ve öyle kalmalı.
    """
    main = Path("apps/desktop/electron/main.ts").read_text(encoding="utf-8")

    assert "readWindowsUserEnvVar('FOOL_HOME')" in main


# ---------------------------------------------------------------------------
# PATH da aynı kapının altında
# ---------------------------------------------------------------------------


def test_PATH_yazmasi_da_kapinin_ICINDE() -> None:
    r"""İkinci, sessiz kalan ihlal.

    ``FOOL_HOME`` korunurken ``PATH`` korunmuyordu: sandbox kurulumu
    kullanıcının KALICI PATH'ine, test bittiğinde hiç var olmayacak bir dizin
    ekliyordu (``%TEMP%\...\hermes-agent\bin``). Aynı sınıf hata, fark
    edilmesi daha zor olanı.
    """
    gate = INSTALL.index("$isSandboxHome = $false")
    path_write = INSTALL.index('[Environment]::SetEnvironmentVariable(\n                "Path",')

    assert gate < path_write, "kapi PATH yazmasindan ONCE gelmeli"

    # PATH yazmasi sandbox DEGILKEN calisan dala dusmeli.
    between = INSTALL[gate:path_write]
    assert "if ($isSandboxHome)" in between
    assert "} else {" in between


def test_tespit_BIR_KEZ_yapiliyor() -> None:
    """İki ayrı kopya ayrışabilir ve biri sessizce eski davranışa dönerdi."""
    assert INSTALL.count("$isSandboxHome = $false") == 1


def test_uv_kurucusu_PATHe_dokunmuyor() -> None:
    r"""Üçüncü PATH yazarı: uv'nin KENDİ kurucusu.

    Ölçülen sızıntı: sandbox eviyle yapılan bir kurulumdan sonra kullanıcının
    KALICI PATH'inde şu satır kaldı::

        C:\...\Temp\hermes-desktop-fresh-install-fNWZmX\hermes-home\bin

    yani test bittiğinde hiç var olmayacak bir dizin. ``install.ps1``in kendi
    PATH yazması ``$isSandboxHome`` ile korunuyordu, ama uv'nin kurucusu ayrı
    bir yazardı ve o kapının dışındaydı.

    The Fool uv'yi kendi ``bin`` dizininde tutup MUTLAK yolla çağırıyor --
    kullanıcının PATH'inde bulunmasına hiç ihtiyaç yok.
    """
    assert "UV_NO_MODIFY_PATH" in INSTALL

    # Kurucu ÇAĞRILMADAN önce ayarlanmalı, yoksa hiçbir etkisi olmaz.
    flag = INSTALL.index("UV_NO_MODIFY_PATH")
    installer = INSTALL.index("astral.sh/uv/install.ps1")

    assert flag < installer


# ---------------------------------------------------------------------------
# Runtime dizini adı: iki hesap yeri BİRLİKTE değişmeli
# ---------------------------------------------------------------------------


def test_runtime_dizini_ADI_iki_yerde_de_yeni() -> None:
    """Ölçülen hata: aynı değer İKİ yerde hesaplanıyor.

    Parametre varsayılanı ``fool-agent``a çevrilmişti, ama parametre
    bağlanmadığında değeri YENİDEN hesaplayan blok eski adı sabitliyordu --
    düzeltme sessizce eziliyordu.

    Sonuç: masaüstünün onarımı ``fool-agent`` dururken ``hermes-agent``a
    klonladı ve iki dizin birden oluştu.
    """
    # Iki hesap yeri de yeni adi tercih etmeli.
    assert INSTALL.count("Join-Path $__foolHome 'fool-agent'") == 1
    assert INSTALL.count("Join-Path $__ih 'fool-agent'") == 1

    # Eski ad yalnizca GERI DUSUS olarak gecmeli -- sabitlenmis olarak degil.
    assert '"$env:FOOL_HOME\\hermes-agent"' not in INSTALL


def test_eski_ad_hala_OKUNUYOR() -> None:
    """Göç edememiş bir kurulum çalışmayı sürdürmeli.

    Sayım YORUM SATIRLARINI dışlıyor: iddia KOD hakkında. Ham metin üzerinde
    sayarken bir açıklama satırında geçen ``'hermes-agent'`` testi düşürüyordu
    -- yani yorum yazmak, sınavı kırabiliyordu. Tersi daha kötü: bir yorum,
    silinmiş bir geri düşüşün yerine sayılıp testi yeşil tutabilirdi.
    """
    code = [
        line for line in INSTALL.splitlines() if not line.lstrip().startswith("#")
    ]

    # SAYIM DEGIL, GERI DUSUS YERLERI.
    #
    # Sayim, korumak istedigi kurali degil dosyanin o anki halini tutuyordu:
    # ilk mesru ucuncu kullanim (eski kurulumu temizleyen yol listesi) testi
    # dusurdu. Tutulmasi gereken kural, GOC EDEMEMIS bir kurulumun calismaya
    # devam etmesi -- yani her cozumleme yerinde eski ada bir geri dusus.
    fallbacks = [
        line for line in code if "= Join-Path" in line and "'hermes-agent'" in line
    ]

    assert len(fallbacks) == 2, (
        "iki cozumleme yerinde de eski ad geri dusus olarak okunmali; "
        f"bulunan: {fallbacks}"
    )
