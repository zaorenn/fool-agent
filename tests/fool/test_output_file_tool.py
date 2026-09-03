"""Uzak platformlarda dosya üretimi — diski okutmadan.

WhatsApp'tan "bana bir PDF çıkar" demek bugün imkânsız: dosya yazmak ``file``
takımını gerektiriyor, o takım da ``read_file`` getiriyor. Yani bir dosya
üretebilmek için bota mesaj yazabilen herkese TÜM DİSKİ okutmak gerekiyordu.

Bu modül o düğümü çözüyor: yalnızca yazan, okuma yetkisi olmayan, tek bir
çıktı klasörüne kilitli bir araç.

Testlerin ağırlığı yol doğrulamasında, çünkü sınır orada. Bir kaçış açığı,
uzak bir kullanıcının makinede istediği yere yazması demek.
"""

from __future__ import annotations

import base64

import pytest

from fool import output_file as of


# ---------------------------------------------------------------------------
# Dosya adı doğrulaması — güvenlik sınırı
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", [
    "rapor.pdf",
    "notlar.txt",
    "veri-2026.csv",
    "ozet_v2.md",
    "a.png",
])
def test_makul_adlar_kabul(name: str) -> None:
    assert of.safe_filename(name) == name


@pytest.mark.parametrize("name", [
    "../gizli.txt",
    r"..\gizli.txt",
    "alt/klasor.txt",
    r"alt\klasor.txt",
    "/etc/passwd",
    r"C:\Windows\System32\evil.dll",
    r"\\sunucu\pay\x.txt",
])
def test_yol_kacislari_reddediliyor(name: str) -> None:
    """Kaçış açığı = uzak kullanıcının makinede istediği yere yazması."""
    with pytest.raises(ValueError):
        of.safe_filename(name)


@pytest.mark.parametrize("name", ["", "   ", ".", "..", "..."])
def test_bos_ve_nokta_adlari_reddediliyor(name: str) -> None:
    with pytest.raises(ValueError):
        of.safe_filename(name)


def test_ntfs_alternatif_veri_akisi_reddediliyor() -> None:
    """``rapor.txt:gizli`` Windows'ta AYRI bir akışa yazar ve listede görünmez."""
    with pytest.raises(ValueError):
        of.safe_filename("rapor.txt:gizli")


@pytest.mark.parametrize("name", ["CON", "PRN", "AUX", "NUL", "COM1", "LPT9", "con.txt", "nul.pdf"])
def test_windows_aygit_adlari_reddediliyor(name: str) -> None:
    """Bu adlar dosya değil AYGIT açar; yazma işlemi sessizce hiçbir yere gider."""
    with pytest.raises(ValueError):
        of.safe_filename(name)


def test_gomulu_null_bayti_reddediliyor() -> None:
    with pytest.raises(ValueError):
        of.safe_filename("rapor\x00.txt")


def test_asiri_uzun_ad_reddediliyor() -> None:
    with pytest.raises(ValueError):
        of.safe_filename("a" * 300 + ".txt")


def test_yurutulebilir_uzantilar_reddediliyor() -> None:
    """Uzak biri makineye çalıştırılabilir bırakamaz.

    Aracın işi belge üretmek; ``.exe`` / ``.ps1`` / ``.bat`` üretmek değil.
    """
    for name in ("kur.exe", "betik.ps1", "calistir.bat", "x.cmd", "y.scr", "z.dll"):
        with pytest.raises(ValueError):
            of.safe_filename(name)


# ---------------------------------------------------------------------------
# Yazma
# ---------------------------------------------------------------------------

def test_metin_yaziliyor_ve_yol_donuyor(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(of, "output_dir", lambda session_id=None: tmp_path)

    result = of.write_output("ozet.txt", text="merhaba")

    assert result["ok"] is True
    assert (tmp_path / "ozet.txt").read_text(encoding="utf-8") == "merhaba"
    assert result["path"].endswith("ozet.txt")


def test_ikili_icerik_base64_ile_yaziliyor(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(of, "output_dir", lambda session_id=None: tmp_path)
    payload = b"%PDF-1.4 sahte"

    of.write_output("rapor.pdf", base64_content=base64.b64encode(payload).decode())

    assert (tmp_path / "rapor.pdf").read_bytes() == payload


def test_ayni_ad_UZERINE_YAZMIYOR(tmp_path, monkeypatch) -> None:
    """Üzerine yazmak, önceki turda üretilen dosyayı sessizce yok etmekti."""
    monkeypatch.setattr(of, "output_dir", lambda session_id=None: tmp_path)

    first = of.write_output("rapor.txt", text="bir")
    second = of.write_output("rapor.txt", text="iki")

    assert first["path"] != second["path"]
    assert (tmp_path / "rapor.txt").read_text(encoding="utf-8") == "bir"


def test_boyut_siniri(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(of, "output_dir", lambda session_id=None: tmp_path)

    with pytest.raises(ValueError):
        of.write_output("buyuk.txt", text="x" * (of.MAX_OUTPUT_BYTES + 1))


def test_icerik_verilmezse_hata(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(of, "output_dir", lambda session_id=None: tmp_path)

    with pytest.raises(ValueError):
        of.write_output("bos.txt")


def test_bozuk_base64_hata(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(of, "output_dir", lambda session_id=None: tmp_path)

    with pytest.raises(ValueError):
        of.write_output("x.bin", base64_content="bu base64 degil!!!")


def test_yazilan_dosya_cikti_klasorunden_cikmiyor(tmp_path, monkeypatch) -> None:
    """Son savunma: yazılan yol gerçekten çıktı klasörünün İÇİNDE mi?

    Ad doğrulaması ilk hat; bu ikinci hat. Tek hatta güvenmek, o hattaki bir
    boşluğun doğrudan disk erişimine dönüşmesi demek.
    """
    monkeypatch.setattr(of, "output_dir", lambda session_id=None: tmp_path)

    result = of.write_output("rapor.txt", text="x")
    written = of.Path(result["path"]).resolve()

    assert written.is_relative_to(tmp_path.resolve())


# ---------------------------------------------------------------------------
# Araç yüzeyi
# ---------------------------------------------------------------------------

def test_arac_okuma_yetkisi_getirmiyor() -> None:
    """Takımın TAMAMI bu tek araçtan ibaret olmalı."""
    from toolsets import resolve_toolset

    assert resolve_toolset("output_file") == ["write_output"]


def test_uzak_platformlar_bu_takimi_aliyor() -> None:
    """Amaç buydu: WhatsApp'tan dosya üretilebilsin, disk okunmasin."""
    from fool.platform_toolsets import SAFE_REMOTE_TOOLSETS

    assert "output_file" in SAFE_REMOTE_TOOLSETS


def test_uzak_platformda_hala_okuma_araci_yok() -> None:
    from fool_cli.tools_config import _get_platform_tools
    from toolsets import resolve_toolset

    tools = set()
    for name in _get_platform_tools({}, "whatsapp"):
        tools |= set(resolve_toolset(name))

    assert "write_output" in tools
    assert not ({"read_file", "search_files", "write_file", "patch"} & tools)
