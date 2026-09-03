"""Terminalden kuran kullanıcı da masaüstünde kısayol görmeli.

İstenen: "``fool desktop`` ilk çalıştığında ... masaüstünde exesi olmalı,
kullanıcı isterse hâlâ terminalden çalıştırabilmeli ya da masaüstü
kısayolundan açabilmeli."

İki ölçülmüş tuzak burada sabitleniyor:

1. Kısayolu üreten kod ``scripts/install.ps1``de vardı ama yalnızca installer
   yolunda koşuyordu.
2. Masaüstü klasörü ``~/Desktop`` DEĞİL: bu makinede OneDrive'a yönlendirilmiş
   (``~/OneDrive/Masaüstü``) ve ``~/Desktop`` hiç yok. Sabit ad yazmak,
   kısayolun görünmediği ama hata da vermediği bir sınıf yaratıyor -- üstelik
   klasör adı dile de bağlı.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from fool_cli.main import _ensure_windows_desktop_shortcut


@pytest.fixture
def calls(monkeypatch):
    seen: list = []

    class _Done:
        stdout = ""

    def _run(argv, **_kwargs):
        seen.append(argv)

        return _Done()

    monkeypatch.setattr("fool_cli.main.subprocess.run", _run)

    return seen


def test_exe_YOKKEN_hicbir_sey_yapmiyor(tmp_path, calls) -> None:
    _ensure_windows_desktop_shortcut(None)
    _ensure_windows_desktop_shortcut(tmp_path / "yok.exe")

    assert calls == []


@pytest.mark.skipif(sys.platform != "win32", reason="kisayol Windows'a ozgu")
def test_masaustu_klasoru_WINDOWS_A_soruluyor(tmp_path, calls) -> None:
    """``~/Desktop`` varsayılmıyor: yönlendirilmiş ve dile bağlı olabiliyor."""
    exe = tmp_path / "TheFool.exe"
    exe.write_text("x", encoding="utf-8")

    _ensure_windows_desktop_shortcut(exe)

    assert len(calls) == 1
    script = calls[0][-1]
    assert "GetFolderPath('Desktop')" in script
    assert "Desktop'" not in script.replace("GetFolderPath('Desktop')", "")


@pytest.mark.skipif(sys.platform != "win32", reason="kisayol Windows'a ozgu")
def test_VAR_OLANI_ezmiyor(tmp_path, calls) -> None:
    """Kullanıcının taşıdığı/yeniden adlandırdığı kısayolu geri getirmek onun
    kararını geri almak olurdu -- betik önce varlığını sınıyor."""
    exe = tmp_path / "TheFool.exe"
    exe.write_text("x", encoding="utf-8")

    _ensure_windows_desktop_shortcut(exe)

    script = calls[0][-1]
    assert "if(Test-Path $p){" in script
    assert script.index("Test-Path $p") < script.index("CreateShortcut")


@pytest.mark.skipif(sys.platform != "win32", reason="kisayol Windows'a ozgu")
def test_hedef_ve_calisma_dizini_GECIYOR(tmp_path, calls) -> None:
    exe = tmp_path / "TheFool.exe"
    exe.write_text("x", encoding="utf-8")

    _ensure_windows_desktop_shortcut(exe)

    script = calls[0][-1]
    assert str(exe) in script
    assert str(tmp_path) in script


@pytest.mark.skipif(sys.platform != "win32", reason="kisayol Windows'a ozgu")
def test_powershell_DUSERSE_patlamiyor(tmp_path, monkeypatch) -> None:
    """Kısayol bir kolaylık; oluşturulamaması uygulamayı açtırmamalı."""
    exe = tmp_path / "TheFool.exe"
    exe.write_text("x", encoding="utf-8")

    def _boom(*_a, **_k):
        raise OSError("powershell yok")

    monkeypatch.setattr("fool_cli.main.subprocess.run", _boom)

    _ensure_windows_desktop_shortcut(exe)  # yükselmemeli
