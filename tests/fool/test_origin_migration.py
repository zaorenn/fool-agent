"""Kurulumun ve ``fool update``in HANGI depoyu takip ettigi.

Olculen hata: hicbir sey ``origin``i yeniden yazmiyordu. Eski depodan
kurulmus bir makine sonsuza dek oradan cekmeye calisiyordu -- guncelleme
calisiyor, "basarili" diyor, hicbir yenilik getirmiyordu. Yazarin kendi
makinesindeki calisan klon tam bu durumda bulundu: origin
``zaorenn/thefool-desktop``, HEAD birkac commit geride.

Ustune: guncel depo TEK COMMIT'lik temiz bir gecmis olarak yayinlandi,
yani eskisiyle ortak atasi yok. Duz ``git pull`` orada
"refusing to merge unrelated histories" ile durur. Cozum ``fetch`` +
``reset --hard``.

``reset``in guvenli olmasinin sebebi olculdu: klonun ICINDE hicbir
kullanici verisi yok. ``.env``, ``config.yaml``, ``sessions``,
``profiles`` (kisisel agent'lar), ``voices`` (klonlanmis sesler),
``sidecars`` (indirilmis modeller), ``memories`` ve ``SOUL.md`` --
hepsi klonun YANINDA, FOOL_HOME icinde. Ayrica ``reset --hard`` yalnizca
TAKIPLI dosyalari geri yazar, yani takipsiz ``venv`` ve ``node_modules``
ondan sag cikar (sentetik depoyla dogrulandi).
"""

import pytest

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PS1 = (REPO_ROOT / "scripts" / "install.ps1").read_text(encoding="utf-8")
SH = (REPO_ROOT / "scripts" / "install.sh").read_text(encoding="utf-8")


class TestKurulumBetikleri_ORIGIN_TASIYOR:
    def _ps(self):
        return PS1.split("function Repair-OriginRemote")[1].split(chr(10) + "function ")[0]

    def _sh(self):
        return SH.split("repair_origin_remote() {")[1].split(chr(10) + "}")[0]

    def test_ps1_eski_ADI_taniyor(self):
        assert "zaorenn/thefool-desktop" in self._ps()

    def test_sh_eski_ADI_taniyor(self):
        assert "zaorenn/thefool-desktop" in self._sh()

    def test_CATAL_korunuyor(self):
        # ``_is_fork`` catala bakan kurulumu bilerek destekliyor. Rastgele bir
        # uzak adresi resmi depoya cevirmek, birinin kendi calismasini
        # sessizce atmak olurdu -- bu yuzden yalnizca BILINEN eski ad tasinir.
        for blok in (self._ps(), self._sh()):
            assert "zaorenn/thefool-desktop" in blok

        assert "$superseded -notcontains $norm" in self._ps()
        assert 'return 1' in self._sh()

    @staticmethod
    def _yalnizca_kod(blok, block_comment):
        """Yorumlari at; iddia KODA bakmali.

        Ilk yazimimda ``"pull" not in blok`` dedim ve test kendi
        aciklamamdaki "git pull stops at..." cumlesine takildi -- yani
        kodu degil, metni sinamis oluyordu.
        """
        satirlar, icerde = [], False
        for l in blok.split(chr(10)):
            t = l.strip()
            if block_comment:
                if icerde:
                    if "#>" in t:
                        icerde = False
                    continue
                if t.startswith("<#"):
                    icerde = "#>" not in t
                    continue
            if t.startswith("#"):
                continue
            satirlar.append(l)
        return chr(10).join(satirlar)

    def test_pull_DEGIL_fetch_reset(self):
        # Gecmisler ilgisiz; ``pull`` burada calismaz.
        for blok, bc in ((self._ps(), True), (self._sh(), False)):
            kod = self._yalnizca_kod(blok, bc)
            assert "reset --hard FETCH_HEAD" in kod
            assert "fetch" in kod
            assert "pull" not in kod

    def test_guncelleme_akisina_BAGLI(self):
        # Yazilip cagrilmamasi sessiz bir no-op olurdu.
        assert "Repair-OriginRemote -RepoDir $InstallDir" in PS1
        assert 'repair_origin_remote "$INSTALL_DIR"' in SH

    def test_resmi_adrese_DOKUNULMUYOR(self):
        # Zaten dogru olan bir kurulumu her koşuda "tasimak" gurultu olurdu.
        assert 'github.com/zaorenn/fool-agent' in self._ps()
        assert 'zaorenn/fool-agent' in self._sh()


class TestFoolUpdate_ORIGIN_TASIYOR:
    def test_eski_ad_catal_degil_olarak_ayirt_ediliyor(self):
        from fool_cli.update_cmd import _is_fork, _is_superseded_origin

        eski = "https://github.com/zaorenn/thefool-desktop.git"
        catal = "https://github.com/birisi/kendi-catalim.git"
        resmi = "https://github.com/zaorenn/fool-agent.git"

        assert _is_superseded_origin(eski) is True
        assert _is_superseded_origin(catal) is False
        assert _is_superseded_origin(resmi) is False

        # Eski ad ``_is_fork`` icin de True doner; ayrimi yapan sey
        # _is_superseded_origin. Once o calismazsa eski kurulumlar
        # "catal" diye etiketlenip guncelleme hic gelmez.
        assert _is_fork(eski) is True
        assert _is_fork(resmi) is False

    def test_ssh_ve_https_bicimleri_ayni_sayiliyor(self):
        from fool_cli.update_cmd import _is_superseded_origin

        for u in (
            "https://github.com/zaorenn/thefool-desktop",
            "https://github.com/zaorenn/thefool-desktop.git",
            "git@github.com:zaorenn/thefool-desktop",
            "git@github.com:zaorenn/thefool-desktop.git",
        ):
            assert _is_superseded_origin(u) is True, u

    def test_tasima_catal_uyarisindan_ONCE_calisiyor(self):
        kaynak = (REPO_ROOT / "fool_cli" / "update_cmd.py").read_text(encoding="utf-8")
        tasima = kaynak.index("_migrate_superseded_origin(git_cmd, _m().PROJECT_ROOT, origin_url)")
        catal = kaynak.index("is_fork = _is_fork(origin_url)")

        assert tasima < catal


class TestOriginNormalizasyonu_GERCEK_DAVRANIS:
    r"""Regex'in METNINI degil, GERCEK ESLESME DAVRANISINI sinar.

    Olculen hata: yazarken ``\.git$`` yazildi -- CIFT ters bolu, yani
    .NET regex'i "ters bolu + herhangi bir karakter, sonra git" ariyordu,
    "\.git$" (kacisli nokta) DEGIL. Sonuc: ".git" hic kirpilmiyordu,
    normallestirme hicbir zaman superseded listesiyle eslesmiyordu, ve
    Repair-OriginRemote SESSIZCE $false donuyordu -- push edilmis olsaydi
    origin migrasyonunun TAMAMI hicbir hata vermeden calismayacakti.

    Statik metin kontrolu (`"\.git" in blok`) bunu YAKALAMAZDI --
    metin dogru GORUNUYORDU, davranis yanlisti. Bu yuzden gercek
    PowerShell'i calistirip GERCEK sonucu olculur.
    """

    def test_git_uzantisi_dogru_kirpiliyor(self):
        import shutil
        import subprocess

        pwsh = shutil.which("powershell") or shutil.which("pwsh")
        if not pwsh:
            pytest.skip("PowerShell bu makinede yok")

        blok = PS1.split("function Repair-OriginRemote")[1].split(chr(10) + "function ")[0]
        norm_satirlari = chr(10).join(
            l for l in blok.split(chr(10)) if "-replace" in l or "$norm =" in l
        )

        script = (
            "$current = 'https://github.com/zaorenn/thefool-desktop.git'; " +
            norm_satirlari.replace(chr(10), " ") +
            "; Write-Output $norm"
        )
        out = subprocess.run(
            [pwsh, "-NoProfile", "-Command", script],
            capture_output=True, text=True, timeout=30,
        ).stdout.strip()

        assert out == "github.com/zaorenn/thefool-desktop", (
            f"normallestirme yanlis sonuc verdi: {out!r} "
            "(.git kirpilmemis olabilir -- cift ters bolu regresyonu)"
        )
