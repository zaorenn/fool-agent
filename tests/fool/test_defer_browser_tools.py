"""İlk açılış tarayıcı araçlarını beklememeli.

Ölçüldü (kullanıcının ikinci makinesi): ``node-deps`` aşaması TEK BAŞINA 10
dakika sürdü ve toplam kurulumu 20 dakikanın üzerine çıkardı. Yaptığı iş depo
kökünde ``npm install`` -- yani bütün monorepo'nun devDependencies'i
(electron, electron-builder, vite, playwright) -- üstüne Playwright Chromium
indirmesi.

Masaüstü uygulaması bunların hiçbirine ihtiyaç duymuyor: kendi derlenmiş hâlini
paketin içinde taşıyor.
"""

from __future__ import annotations

from pathlib import Path

INSTALL = Path("scripts/install.ps1").read_text(encoding="utf-8")
RUNNER = Path("apps/desktop/electron/bootstrap-runner.ts").read_text(encoding="utf-8")


def test_kurulum_betigi_ATLAMAYI_biliyor() -> None:
    assert "FOOL_INSTALL_DEFER_BROWSER_TOOLS" in INSTALL


def test_atlama_npm_install_ONUNDE() -> None:
    """Kapı geç gelirse hiçbir şey kazanılmaz."""
    gate = INSTALL.index("FOOL_INSTALL_DEFER_BROWSER_TOOLS")
    npm = INSTALL.index('_Run-NpmInstall "Browser tools"')

    assert gate < npm


def test_kullaniciya_NASIL_alacagini_soyluyor() -> None:
    """Atlanan bir yeteneğin geri gelme yolu görünür olmalı."""
    block = INSTALL[INSTALL.index("FOOL_INSTALL_DEFER_BROWSER_TOOLS") :][:400]

    assert "fool setup tools" in block


def test_masaustu_bootstrap_bayragi_GECIYOR() -> None:
    assert RUNNER.count("FOOL_INSTALL_DEFER_BROWSER_TOOLS: '1'") == 2


def test_CLI_kurulumu_etkilenmiyor() -> None:
    """Bayrak yalnızca masaüstünün sürdüğü kurulumda set ediliyor; terminalden
    ``install.ps1`` çalıştıran kullanıcı her şeyi almaya devam ediyor."""
    assert "FOOL_INSTALL_DEFER_BROWSER_TOOLS=1" not in INSTALL
    assert 'if ($env:FOOL_INSTALL_DEFER_BROWSER_TOOLS' in INSTALL
