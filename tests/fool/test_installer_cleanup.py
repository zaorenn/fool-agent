"""Kurulum betiği: eski kurulumu siler, kullanıcı verisini SİLMEZ.

Kullanıcının kararı: "bu yeni repodan kuracaklar şuanki repodan kurulmuş
versiyonu 0 kalıntı bırakarak öncelikle silmeli; daha önce bu repoyu kurmamış
olanlar için bu adım atlanmalı ve yeni repoda temiz kurulmalı."

Neden "0 kalıntı" TÜM KÖK demek değil
-------------------------------------
Program ve kullanıcı verisi AYNI kökte duruyor. Ölçüldü::

    program : fool-agent/ (depo kopyası)  bin/ 50M  cache/ 197M  bootstrap-cache/
    veri    : state.db (oturumlar + hafıza)  config.yaml  auth.json  SOUL.md
              voices/ (klonlanmış sesler)  skins/  whatsapp/

Kökü toptan silmek, bir YÜKSELTMEDE kullanıcının bütün geçmişini ve klonladığı
sesleri yok etmek olurdu. Asıl kalıntı sorunu program tarafında: eski klonun
``origin``i artık var olmayan bir depoyu gösteriyor ve güncellemeler ağ hatası
gibi görünen biçimlerde düşüyor.

Tam silmek isteyen için açık bir bayrak var.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PS1 = (REPO_ROOT / "scripts" / "install.ps1").read_text(encoding="utf-8")
SH = (REPO_ROOT / "scripts" / "install.sh").read_text(encoding="utf-8")

#: Silinmesi gereken program yolları -- her ikisinde de aynı liste.
PROGRAM_PATHS = ("fool-agent", "hermes-agent", "bin", "cache", "bootstrap-cache")

#: ASLA silinmemesi gereken kullanıcı verisi.
USER_DATA = ("state.db", "config.yaml", "auth.json", "SOUL.md", "voices", "skins")


class TestProgramSiliniyor:
    def test_her_iki_betik_de_ayni_program_yollarini_siliyor(self):
        # Ayrışırlarsa bir platformda kalıntı kalır ve bunu ancak kullanıcı
        # fark eder.
        for name in PROGRAM_PATHS:
            assert name in PS1, f"install.ps1 {name} yolunu bilmiyor"
            assert name in SH, f"install.sh {name} yolunu bilmiyor"

    def test_eski_klon_adi_da_siliniyor(self):
        # Yeniden adlandırmadan ÖNCE kurulmuş bir makinede dizin
        # ``hermes-agent`` adını taşıyor; onu bırakmak tam da temizlenmek
        # istenen kalıntı olurdu.
        assert "hermes-agent" in PS1
        assert "hermes-agent" in SH

    def test_PATH_girdileri_de_temizleniyor(self):
        # Kaldırılan ağaca işaret eden bir PATH girdisi, sonraki kurulumda
        # olmayan bir ikiliyi çağırır.
        assert "Remove-FoolPathEntries" in PS1
        assert "FOOL_GIT_BASH_PATH" in PS1


class TestKullaniciVerisiKORUNUYOR:
    def test_kok_varsayilan_olarak_silinmiyor(self):
        # Silme, kökün KENDİSİNİ değil altındaki program yollarını hedefliyor.
        # Bu testin düşmesi, birinin oturum geçmişini kaybetmesi demek.
        for script, purge_flag in ((PS1, "PurgeUserData"), (SH, "PURGE_USER_DATA")):
            assert purge_flag in script

    def test_veri_dosyalari_silme_listesinde_DEGIL(self):
        program_block_ps1 = PS1[PS1.index("function Get-FoolProgramPaths"):]
        program_block_ps1 = program_block_ps1[: program_block_ps1.index("function Test-PreviousFoolInstall")]

        program_block_sh = SH[SH.index("fool_program_paths()"):]
        program_block_sh = program_block_sh[: program_block_sh.index("has_previous_install()")]

        for data in USER_DATA:
            assert data not in program_block_ps1, f"{data} program listesinde -- veri kaybı"
            assert data not in program_block_sh, f"{data} program listesinde -- veri kaybı"

    def test_kullaniciya_NE_KALDIGI_soyleniyor(self):
        # Sessizce silmek ya da sessizce bırakmak, ikisi de kullanıcıyı
        # tahmin etmeye bırakır.
        assert "Kept your data" in PS1
        assert "Kept your data" in SH


class TestTemizMakinede_ATLANIYOR:
    def test_onceki_kurulum_yoksa_hicbir_sey_yapilmiyor(self):
        # Kullanıcının şartı: "daha önce bu repoyu kurmamış olanlar için bu
        # adım atlanmalı." İlk kez kuran birine temizlik mesajı göstermek,
        # olmayan bir sorunu varmış gibi anlatmak olurdu.
        assert "if (-not (Test-PreviousFoolInstall -Root $Root)) { return }" in PS1
        assert 'has_previous_install "$_root" || return 0' in SH


class TestHermesKurulumuna_DOKUNULMUYOR:
    def test_ayri_veri_dizini_hedeflenmiyor(self):
        # README açıkça "mevcut bir Hermes kurulumuna dokunmaz" diye söz
        # veriyor ve makinede gerçekten ayrı bir tane olabiliyor.
        for script in (PS1, SH):
            assert "LOCALAPPDATA\\hermes" not in script
            assert "$HOME/.hermes" not in script


class TestPowerShellBetigi_SAF_ASCII:
    """``install.ps1`` ASCII kalmalı.

    Ölçülen hata: temizlik bloğunu eklerken içine bir uzun tire (U+2014)
    girdi. Dosyada BOM yok ve PowerShell 5.1 BOM'suz UTF-8'i ANSI sanıyor;
    çok baytlı karakter çözülünce DİZGENİN ORTASINA bir tırnak düşüyor ve
    ayrıştırıcı ``Unexpected token '}'`` diyerek betiği komple reddediyor.

    Dosya bu değişiklikten önce zaten tamamen ASCII'ydi -- yani kural
    yazılmamış ama gerçekti. Artık yazılı.
    """

    def test_hic_ascii_disi_karakter_yok(self):
        offenders = [
            (i + 1, line)
            for i, line in enumerate(PS1.split("\n"))
            if any(ord(ch) > 127 for ch in line)
        ]

        assert not offenders, "install.ps1 ASCII disi: " + repr(offenders[:3])

    def test_bom_yok(self):
        # BOM eklemek de cozum olurdu, ama betik ``irm | iex`` ile de
        # calisiyor ve orada BOM govdeye sizabiliyor. ASCII kalmak ikisini
        # birden guvenli tutuyor.
        raw = (REPO_ROOT / "scripts" / "install.ps1").read_bytes()

        assert not raw.startswith(b"\xef\xbb\xbf")


class TestDepoAdresi_YENI:
    def test_eski_depo_adresi_kalmadi(self):
        # Eski adrese giden bir kurulum, ilk adımda olmayan bir depoyu
        # klonlamaya calisir.
        for script in (PS1, SH):
            assert "thefool-desktop" not in script

    def test_yeni_depo_adresi_kullaniliyor(self):
        for script in (PS1, SH):
            assert re.search(r"zaorenn/fool-agent", script)
