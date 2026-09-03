"""Windows bildirimi UYGULAMAYA bağlanmalı.

Kullanıcının bildirdiği: "Windows bildirimine tıklayınca uygulama değil,
Electron + dosya yolu içeren bir arayüz açılıyor."

Sebep ÖLÇÜLDÜ: ``main.ts`` ``setAppUserModelId('com.nousresearch.fool')``
diyordu, build ``appId`` ise ``com.fool.desktop``. NSIS kurulumu Başlat menüsü
kısayolunu ``appId`` ile damgalıyor -- yani uygulamanın bildirdiği kimlikle
kayıtlı kısayolun kimliği FARKLIYDI. Windows toast'ı çalışan sürece
bağlayamıyor ve tıklama, uygulamayı öne getirmek yerine kayıtlı yolu açan
genel bir geri dönüşe düşüyor.

``main.ts``teki yorum zaten "keep this string in sync with package.json
``build.appId``" diyordu. Yorum yetmedi: iki kopya ayrıştı ve hangisinin canlı
olduğu hiçbir yerde görünmüyordu. Bu dosya o yorumun yerini alıyor.

``appId`` KAZANIYOR çünkü tek değiştiremediğimiz taraf o: NSIS'in kısayola
yazdığı damga uygulama kodundan değiştirilemiyor.

NOT -- ``fool_cli`` neden burada yok
------------------------------------
``fool_cli.main._ensure_windows_desktop_shortcut`` yalnızca MASAÜSTÜ kısayolu
üretiyor. Bildirim kimliği Başlat menüsü kısayolundan çözülüyor; masaüstü
kısayolları o kayda hiç katılmıyor, yani orada damgalamanın karşılığı yok.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PACKAGE_JSON = ROOT / "apps" / "desktop" / "package.json"
MAIN_TS = ROOT / "apps" / "desktop" / "electron" / "main.ts"
INSTALL_PS1 = ROOT / "scripts" / "install.ps1"


@pytest.fixture(scope="module")
def app_id() -> str:
    build = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))["build"]
    value = build.get("appId", "")

    assert value, "build.appId bos -- kimlik zincirinin kaynagi bu"

    return value


def _single(pattern: str, text: str, what: str) -> str:
    found = re.findall(pattern, text)

    # BIRDEN FAZLA eslesme de hata: ikinci bir kopya tam olarak bu testin
    # onlemeye calistigi sey.
    assert len(found) == 1, f"{what}: beklenen tek tanim, bulunan {len(found)}"

    return found[0]


def test_uygulamanin_bildirdigi_kimlik_appId_ile_AYNI(app_id: str) -> None:
    declared = _single(
        r"const WINDOWS_APP_USER_MODEL_ID = '([^']+)'",
        MAIN_TS.read_text(encoding="utf-8"),
        "main.ts AUMID",
    )

    assert declared == app_id


def test_installer_kisayolu_AYNI_kimlikle_damgaliyor(app_id: str) -> None:
    """Kısayolun damgası uygulamanınkinden farklıysa toast hiçbir şeye bağlanmaz."""
    stamped = _single(
        r"\$script:FoolAumid = '([^']+)'",
        INSTALL_PS1.read_text(encoding="utf-8"),
        "install.ps1 AUMID",
    )

    assert stamped == app_id


def _code_only(path: Path, comment_prefixes: tuple[str, ...]) -> str:
    """Yorum satırlarını at.

    Ayrışmış eski değer BİLEREK yorumlarda anlatılıyor -- ölçülen hatanın ne
    olduğunu kaynağın kendisinde bırakmak deponun üslubu. Aranan şey o
    anlatım değil, dizenin CANLI koda geri sızması.
    """
    lines = path.read_text(encoding="utf-8").splitlines()

    return "\n".join(
        line for line in lines if not line.lstrip().startswith(comment_prefixes)
    )


def test_AYRISMIS_eski_deger_CANLI_kodda_kalmadi() -> None:
    """Regresyonun kendisi. Eski dize geri sızarsa hata sessizce döner."""
    assert "com.nousresearch.fool" not in _code_only(MAIN_TS, ("//", "*", "/*"))
    assert "com.nousresearch.fool" not in _code_only(INSTALL_PS1, ("#",))


def test_installer_kisayolu_GERCEKTEN_damgaliyor() -> None:
    """``WScript.Shell`` AUMID yazamıyor -- damga ayrı bir adım.

    Kısayol oluşturulup damgalanmazsa Windows kimliği kendi sezgisiyle
    eşleştirmeye çalışır; o sezgiye güvenmek, kurulumun bazen çalışıp bazen
    çalışmaması demek.
    """
    source = INSTALL_PS1.read_text(encoding="utf-8")

    assert "function Set-ShortcutAumid" in source
    assert "Set-ShortcutAumid -Lnk $lnkPath -Aumid $script:FoolAumid" in source
    # System.AppUserModel.ID ozellik anahtari.
    assert "9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3" in source


def test_kimlik_YALNIZCA_Windowsta_bildiriliyor() -> None:
    """macOS/Linux'ta gereksiz ve zararlı olabilir; kapı yerinde kalmalı."""
    source = MAIN_TS.read_text(encoding="utf-8")
    call = source[source.index("app.setAppUserModelId") - 200 : source.index("app.setAppUserModelId")]

    assert "IS_WINDOWS" in call
