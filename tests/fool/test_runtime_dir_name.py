"""Runtime dizini ``fool-agent`` — ve ÜÇ TARAF da aynı sırayı bilmeli.

Neden bu dosya var
------------------
``runtime-dir-name`` dikişi tek bir yerde değil, üç bağımsız yerde yaşıyor:

* ``apps/desktop/electron/runtime-root.ts`` — masaüstü hangi dizini açacak
* ``scripts/install.ps1``                   — Windows kurulumu nereye kuracak
* ``scripts/install.sh``                    — macOS/Linux kurulumu nereye kuracak

Üçü aynı sırayı uygulamak ZORUNDA: **yeni ad varsa yeni, yoksa eski ad varsa
eski, hiçbiri yoksa yeni.** Biri diğerlerinden ayrılırsa sonuç sessiz ve
pahalı: masaüstü klonu ``fool-agent``a taşır, sonra ``curl | bash`` ile
çalıştırılan kurulum -- ``--dir`` almadığı için -- eski adla İKİNCİ bir
gigabaytlarca klon oluşturur. Terminaldeki ``fool`` eski kopyayı, uygulama
yeni kopyayı koşar ve ikisi farklı sürümdedir.

Ölçülen hâl: ``install.ps1`` ve masaüstü yeni ada geçirilmişti, ``install.sh``
geride kalmıştı -- yani macOS ve Linux tam olarak yukarıdaki duruma açıktı.

Zone A: upstream bu dosyayı bilmiyor.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

INSTALL_SH = (REPO_ROOT / "scripts/install.sh").read_text(encoding="utf-8")
INSTALL_PS1 = (REPO_ROOT / "scripts/install.ps1").read_text(encoding="utf-8")
RUNTIME_ROOT_TS = (
    REPO_ROOT / "apps/desktop/electron/runtime-root.ts"
).read_text(encoding="utf-8")


def _code_lines(source: str, comment: str) -> list[str]:
    """Yorum satırlarını atan kaba bir süzgeç.

    İddialar KOD hakkında. Ham metin üzerinde saymak, bir açıklama satırında
    geçen adın testi düşürmesine -- ya da daha kötüsü, silinmiş bir geri
    düşüşün yerine sayılıp testi yeşil tutmasına -- yol açıyor.
    """
    return [
        line
        for line in source.splitlines()
        if not line.lstrip().startswith(comment)
    ]


# ---------------------------------------------------------------------------
# Üç taraf da YENİ adı biliyor
# ---------------------------------------------------------------------------


def test_masaustu_yeni_adi_kullaniyor() -> None:
    assert "export const RUNTIME_DIR_NAME = 'fool-agent'" in RUNTIME_ROOT_TS
    assert "export const LEGACY_RUNTIME_DIR_NAME = 'hermes-agent'" in RUNTIME_ROOT_TS


def test_windows_kurulumu_yeni_adi_kullaniyor() -> None:
    code = _code_lines(INSTALL_PS1, "#")

    # SAYIM DEGIL, COZUMLEME YERLERI.
    #
    # Onceki hali "dosyada tam iki kez gecsin" diyordu ve ilk mesru ucuncu
    # kullanim (eski kurulumu temizleyen yol listesi) testi dusurdu. Sayim,
    # korumak istedigi seyi degil dosyanin o anki halini tutuyordu.
    #
    # Tutulmasi gereken kural su: runtime dizinini HESAPLAYAN her yer once
    # yeni ada bakmali. Iki hesap yeri var -- parametre varsayilani ve
    # yeniden hesaplama blogu -- ve ikisi de ayni desenle yaziliyor.
    resolvers = [
        line for line in code if "= Join-Path" in line and "'fool-agent'" in line
    ]

    assert len(resolvers) == 2, (
        "iki hesap yeri de (parametre varsayilani + yeniden hesaplama blogu) "
        f"yeni adi tercih etmeli; bulunan: {resolvers}"
    )


def test_posix_kurulumu_yeni_adi_kullaniyor() -> None:
    """Ölçülen boşluk buydu: ``install.sh`` göç edilen ada hiç geçmemişti."""
    assert "fool_runtime_dir()" in INSTALL_SH
    assert 'echo "$1/fool-agent"' in INSTALL_SH


# ---------------------------------------------------------------------------
# Üçü de AYNI sırayı uyguluyor
# ---------------------------------------------------------------------------


def test_posix_kurulumu_sirayi_dogru_uyguluyor() -> None:
    """yeni → eski → yeni. Sıra bozulursa göç etmiş bir kurulumda ikinci klon."""
    body = INSTALL_SH[
        INSTALL_SH.index("fool_runtime_dir() {") : INSTALL_SH.index(
            "resolve_install_layout() {"
        )
    ]

    new_first = body.index('-d "$1/fool-agent"')
    legacy_second = body.index('-d "$1/hermes-agent"')

    assert new_first < legacy_second, "yeni ad ONCE denenmeli"
    # Son çare de YENİ ad: taze kurulum eski adı asla oluşturmamalı.
    assert body.rstrip().endswith("}")
    assert body.count('echo "$1/fool-agent"') == 2  # ilk dal + son çare


def test_windows_kurulumu_sirayi_dogru_uyguluyor() -> None:
    for prefix in ("__new", "__inew"):
        legacy = prefix.replace("new", "legacy")
        pattern = re.compile(
            r"if \(Test-Path \$" + prefix + r"\) \{ \$" + prefix + r" \}"
            r" elseif \(Test-Path \$" + legacy + r"\) \{ \$" + legacy + r" \}"
            r" else \{ \$" + prefix + r" \}"
        )

        assert pattern.search(INSTALL_PS1), f"{prefix} sirasi bozuk"


def test_masaustu_sirayi_dogru_uyguluyor() -> None:
    body = RUNTIME_ROOT_TS[RUNTIME_ROOT_TS.index("export function chooseRuntimeRoot") :]

    assert "if (hasNew) {" in body
    assert body.index("if (hasNew) {") < body.index("if (hasLegacy) {")


# ---------------------------------------------------------------------------
# ESKİ ad okunmaya devam ediyor
# ---------------------------------------------------------------------------


def test_eski_ad_her_uc_tarafta_da_GERI_DUSUS_olarak_duruyor() -> None:
    """Göç edememiş (dosya kilitli, izin yok) bir kurulum çalışmayı sürdürmeli.

    Ad bir kolaylık, çalışmanın şartı değil.
    """
    assert 'echo "$1/hermes-agent"' in INSTALL_SH
    assert "'hermes-agent'" in INSTALL_PS1
    assert "LEGACY_RUNTIME_DIR_NAME" in RUNTIME_ROOT_TS


# ---------------------------------------------------------------------------
# Yeniden adlandırmanın DOKUNDUĞU her yer birlikte değişmeli
# ---------------------------------------------------------------------------


def test_veri_sozlesmesi_IKI_adi_da_biliyor() -> None:
    """Yalnızca eski adı bilmek, göç etmiş bir kurulumda klonu "kullanıcı
    verisi" sayardı: ne temizlenir ne yedekten dışlanır."""
    from fool import user_data

    assert user_data.is_owned("fool-agent") is False
    assert user_data.is_owned("hermes-agent") is False


def test_yedek_IKI_adi_da_disliyor() -> None:
    """Göç ettikten sonra klon ``fool-agent``: yalnızca eski adı dışlamak her
    yedeğe gigabaytlarca yeniden klonlanabilir dosya koyardı."""
    from fool_cli import backup

    assert "fool-agent" in backup._EXCLUDED_DIRS
    assert "hermes-agent" in backup._EXCLUDED_DIRS


def test_uzak_baglanti_IKI_adi_da_deniyor() -> None:
    """Uzak bir ana makinede ``fool`` aranırken yeni ad ÖNCE, eski ad hâlâ
    listede -- göç edememiş bir uzak kurulum da bulunabilmeli."""
    source = (
        REPO_ROOT / "apps/desktop/electron/remote-lifecycle.ts"
    ).read_text(encoding="utf-8")

    new_at = source.index("'~/.fool/fool-agent/venv/bin/fool'")
    legacy_at = source.index("'~/.fool/hermes-agent/venv/bin/fool'")

    assert new_at < legacy_at


# ---------------------------------------------------------------------------
# Dağıtım adı: kurulum betikleri pyproject'i DOĞRU okuyor
# ---------------------------------------------------------------------------


def test_kurulum_betikleri_dagitim_adini_SABITLEMIYOR() -> None:
    """``[all]`` ayrıştırması dağıtım adına göre yapılıyor.

    Ölçülen hata: iki betik de adı ``hermes-agent`` olarak gömüyordu, oysa
    proje ``fool-agent`` adını almıştı. Regex hiçbir şeyle eşleşmiyor, her
    kurulum "Could not parse [all] from pyproject.toml" yazıyor ve Tier 2
    Tier 1 ile aynı şeye dönüşüyordu.

    Bu kozmetik değil: Tier 2 bozulma yolunun tamamı. Ölü olduğunda PyPI'de
    çözülemeyen TEK bir extra, kullanıcıyı istediği her şeyi korumak yerine
    doğrudan "core only (no extras)" seviyesine düşürüyor.
    """
    for source, label in ((INSTALL_SH, "install.sh"), (INSTALL_PS1, "install.ps1")):
        assert 'data["project"]["name"]' in source or "data['project']['name']" in source, (
            f"{label}: dagitim adi pyproject'ten OKUNMALI, gomulmemeli"
        )
        assert "hermes-agent\\[" not in source, f"{label}: eski ad regex'te gomulu"


def test_dagitim_adi_gercekten_ayristirilabiliyor() -> None:
    """Betiklerin yaptığı işin aynısı: eşleşme BOŞ dönmemeli."""
    import tomllib

    data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    name = re.escape(data["project"]["name"])
    specs = data["project"]["optional-dependencies"]["all"]

    extras = [m.group(1) for s in specs if (m := re.search(name + r"\[([\w-]+)\]", s))]

    assert extras, "[all] icindeki extra'lar ayristirilamadi -- Tier 2 olu"
    assert len(extras) == len(specs), "bazi spec'ler eslesmedi"
