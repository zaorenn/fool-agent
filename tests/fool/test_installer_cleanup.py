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

    def test_HATA_yolu_da_kendi_kurulumumuza_isaret_ediyor(self):
        """Kurulum düşerse kullanıcı BAŞKA bir ürüne yönlendirilmemeli.

        Ölçülen hata: temiz bir makinede kurulum düştü ve mesaj
        ``hermes-agent.nousresearch.com/install.ps1`` indirmeyi öneriyordu --
        yani The Fool kurulamayan kullanıcıya Hermes kurduruyordu. Markalama
        değil, yanlış ürün.

        ``fool.audit`` bunu görmedi: taradığı yüzeyler arasında kurulum
        betiğinin hata yolu yok.
        """
        for script in (PS1, SH):
            assert "nousresearch.com" not in script


class TestSslPolitikasi_KENDINI_ONARIYOR:
    """Engellenen SSL, kullanıcıya iş çıkarmadan çözülmeli.

    Ölçülen hata (temiz Windows 11 laptop): Akıllı Uygulama Denetimi yeni
    kurulumlarda varsayılan olarak AÇIK ve ``uv``nin taşınabilir Python'ındaki
    imzasız ``_ssl.pyd``i engelliyor. HTTPS gerektiren her şey ölüyor -- ama
    kurulum bunu ALAKASIZ bir paketin (``alibabacloud-tea``) derleme hatası
    olarak bildiriyordu. İki kişi o hatayı okudu, kimse işletim sistemini
    düşünmedi.

    Kullanıcıya "git Python kur" demek bu kurulumun tek vaadini bozardı:
    Python bir ön koşul değil. O yüzden kendi kendini onarıyor.
    """

    def test_SSL_bagimlilik_kurulumundan_ONCE_sinaniyor(self):
        # Sonra sinamak, dakikalarca surup yanlis bir hatayla bitmek demekti.
        assert PS1.index("Test-PythonSsl") < PS1.index("Baseline imports failed")

    def test_politika_engeli_AYIRT_ediliyor(self):
        # Her ssl hatasi politika engeli degil; ayirt etmeden onarim denemek
        # gercek sebebi gizlerdi.
        assert "function Test-SslBlockedByPolicy" in PS1
        assert "DLL load failed|Application Control|Uygulama Denetimi" in PS1

    def test_ONCE_makinedeki_python_deneniyor(self):
        # Indirmeden once bakmak: cogu makinede zaten imzali bir Python var.
        assert "--python-preference only-system" in PS1

    def test_yoksa_IMZALI_python_kuruluyor(self):
        # winget Windows 11'de hazir geliyor ve kullanici kapsaminda kuruyor,
        # yani yukseltme istemiyor.
        assert "winget install --id Python.Python.3.13" in PS1
        assert "--scope user" in PS1

    def test_zaten_kurulu_hatasi_BASARI_sayiliyor(self):
        # winget paket zaten varken ayri bir kod donuyor; onu hata saymak
        # calisan bir makinede onarimi durdururdu.
        assert "-1978335189" in PS1

    def test_winget_KURDUGU_surumu_deniyor(self):
        """winget 3.13 kuruyor; onarım 3.11 istemeye devam ederse boşa düşer.

        Bu tam da işe yarayacağı anda kaybedilen bir onarım olurdu: paket
        kurulur, sonraki adım olmayan bir sürümü ister ve vazgeçilir.
        """
        block = PS1[PS1.index("function Repair-BlockedSslVenv"):]
        block = block[: block.index("function ", 10)] if "function " in block[10:] else block

        assert "$candidates = @('3.13')" in block

    def test_orijinal_surum_TEKRAR_ISTENMIYOR(self):
        # Engellenen venv'i uv indirmisti; ayni surumu ``only-system`` ile
        # istemek tanim geregi hicbir sey bulamaz.
        block = PS1[PS1.index("function Repair-BlockedSslVenv"):]

        assert "--python $PythonVersion --python-preference only-system" not in block

    def test_her_ikisi_de_dusesrse_SEBEP_soyleniyor(self):
        # Son care mesaji gercek sebebi adlandirmali, yaniltici derleme
        # hatasini degil.
        assert "one-way" in PS1
        assert "python.org/downloads" in PS1


class TestMarkaTemasi_KURULUYOR:
    """Marka teması her iki kurulumda da yüklenip seçilmeli.

    Ölçülen hata: ``fool/skins/the-fool.yaml`` depoda vardı ama hiçbir kurulum
    onu kopyalamıyor ve seçmiyordu. Temiz bir makinede TUI upstream'in kehribar
    paletiyle açılıyordu -- altındaki afiş çoktan crimson olmasına rağmen. Tema
    yazılmış, geliştiricinin makinesinde elle seçilmiş ve başka kimseye hiç
    ulaşmamıştı.
    """

    def test_tema_dosyasi_kopyalaniyor(self):
        assert "fool/skins/the-fool.yaml" in SH
        sep = chr(92)
        assert f"fool{sep}skins{sep}the-fool.yaml" in PS1

    def test_tema_SECILIYOR(self):
        for script in (PS1, SH):
            assert "skin: the-fool" in script

    def test_yalnizca_YENI_yapilandirmada(self):
        # Var olan bir config kullanicinin sectigi bir temayi tasiyor olabilir;
        # uzerine yazmak onun tercihini elinden almak olurdu.
        assert "$configIsNew" in PS1
        assert "config_is_new" in SH

    def test_VAR_OLAN_deger_degistiriliyor_eklenmiyor(self):
        """Şablonda zaten ``display:`` ve ``skin: default`` var.

        İlk yazımım "skin satırı varsa dokunma" diyordu -- yani temiz bir
        kurulumda HİÇBİR ŞEY yapmayacaktı: düzeltmenin kendisi sessizce
        işlevsizdi. Blok eklemek ise ikinci bir ``display:`` anahtarı üretip
        YAML'i bozardı. Doğrusu var olan değeri yeniden yazmak.
        """
        assert "skin:\s*default" in PS1
        assert "skin:[[:space:]]*default" in SH

    def test_sablon_hala_default_tasiyor(self):
        # Bu testlerin dayanagi: sablon degisip ``skin: default`` satiri
        # kalkarsa yukaridaki ikame sessizce hicbir sey yapmaz.
        template = (REPO_ROOT / "cli-config.yaml.example").read_text(encoding="utf-8")

        assert re.search(r"(?m)^\s*skin:\s*default\s*$", template)
        assert re.search(r"(?m)^display:", template)


class TestKurulumSihirbazi_YEREL_ONCE:
    """İlk kurulum yerel modelle başlamalı, abonelik girişiyle değil.

    Kullanıcının kararı: "yerel ilk olması lazım; kullanıcı isterse sonradan
    gerçekten Hermes gibi Nous'a bağlanabilsin."

    Ölçüldü: varsayılan doğrudan Nous Portal OAuth'a gidiyordu ve temiz
    makinede uç ``400 Bad Request`` döndü -- yerel çalışsın diye kurulan bir
    uygulama, daha ilk ekranında bir abonelik hatası gösterdi.
    """

    SETUP = (REPO_ROOT / "fool_cli" / "setup.py").read_text(encoding="utf-8")

    def test_ilk_secenek_YEREL(self):
        first = self.SETUP.index("Local model (recommended)")
        portal = self.SETUP.index("Nous Portal - hosted models".replace("-", "—"))

        assert first < portal

    def test_varsayilan_yerel_akisi_cagiriyor(self):
        assert "if setup_mode == 0:\n            _run_first_time_local_setup(" in self.SETUP

    def test_portal_KALDIRILMADI(self):
        # Kullanici acikca istedi: isteyen baglanabilmeli.
        assert "_run_first_time_quick_setup(" in self.SETUP
        assert "setup_mode == 1" in self.SETUP

    def test_ortak_adimlar_TEK_yerde(self):
        # Iki yol yalnizca modeli nasil sectiginde ayriliyor; terminal arka ucu
        # ve varsayilanlar ayri ayri yazilsaydi biri degisip digeri unutulurdu.
        assert self.SETUP.count("def _finish_first_time_setup(") == 1
        assert self.SETUP.count("def _offer_messaging_gateway(") == 1

    def test_yerel_bulunamazsa_HATA_degil(self):
        # Model sunucusu kapaliysa kurulum yine tamamlanmali.
        block = self.SETUP[self.SETUP.index("def _run_first_time_local_setup"):]
        block = block[: block.index("def _run_first_time_quick_setup")]

        assert "No local model server answered yet" in block
        assert "fool portal" in block
