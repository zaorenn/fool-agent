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
    def test_eski_adres_YALNIZCA_tasima_kaynagi_olarak_geciyor(self):
        """Eski adres klonlanmamali -- ama TANINMALI.

        Ilk yazim "betikte hic gecmesin" diyordu. O kural, eski depodan
        kurulmus makinelerin sonsuza dek oradan cekmeye calismasi
        sorununu gorunmez kildi: origin'i hicbir sey yeniden yazmiyordu.

        Dogru sozlesme: eski adres SADECE tasima fonksiyonunda, "bu
        kurulumu guncel depoya tasi" kaynagi olarak gecebilir. Klonlama,
        fetch hedefi ya da indirme adresi olarak asla.
        """
        for script, fn in ((PS1, "function Repair-OriginRemote"),
                           (SH, "remote-migration")):
            if fn == "remote-migration":
                tasima = script.split("repair_origin_remote() {")[1].split(chr(10) + "}")[0]
                gerisi = (script.split("repair_origin_remote() {")[0]
                          + script.split("repair_origin_remote() {")[1].split(chr(10) + "}", 1)[1])
            else:
                tasima = script.split(fn)[1].split(chr(10) + "function ")[0]
                gerisi = script.split(fn)[0] + script.split(fn)[1].split(chr(10) + "function ", 1)[1]

            assert "thefool-desktop" in tasima, "eski adres taninmiyor; tasima olmaz"
            assert "thefool-desktop" not in gerisi, (
                "eski adres tasima disinda geciyor -- klonlama/fetch hedefi olabilir"
            )

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

    def test_VAR_OLAN_deger_degistiriliyor_eklenmiyor(self):
        """Şablonda zaten ``display:`` ve ``skin: default`` var.

        İlk yazımım "skin satırı varsa dokunma" diyordu -- yani temiz bir
        kurulumda HİÇBİR ŞEY yapmayacaktı: düzeltmenin kendisi sessizce
        işlevsizdi. Blok eklemek ise ikinci bir ``display:`` anahtarı üretip
        YAML'i bozardı. Doğrusu var olan değeri yeniden yazmak.
        """
        assert "skin:" + chr(92) + "s*default" in PS1
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


class TestKurulumBetikleri_KONTROL_KARAKTERI_YOK:
    """Her iki kurulum betiginde de C0 kontrol karakteri bulunmamali.

    Olculen hata, UC KEZ: duzenleme sirasinda yazilan bir kacis dizisi
    dosyaya COZULMUS halde dustu.

    1. install.ps1 -- "ters bolu + t", SEKME'ye donustu ve
       "$skinDir + ters bolu + the-fool.yaml" yolunun ortasina gomuldu.
       Kurulum "Yolda gecersiz karakterler var" diyerek oldu; kullanici
       hicbir sey kuramadi.
    2. install.ps1 -- ayni satirin ilk onariminda ikinci bir kopya
       gozden kacti, cunku dogrulama taramasi sekmeyi HARIC TUTUYORDU.
    3. install.sh -- "ters bolu + 1", U+0001'e donustu. sed'in geri
       basvurusu yerine kullanicinin config.yaml'ina gorunmez bir
       kontrol karakteri yazacakti.

    Ustteki ASCII muhafizi bunlarin hicbirini yakalamadi: yalnizca
    ord > 127 bakiyor, sekme (9) ve SOH (1) o esigin altinda kaliyor.
    """

    def test_c0_kontrol_karakteri_yok(self):
        # Iki betik de girintide bosluk kullaniyor, yani SEKME dahil
        # her C0 karakteri suphelidir.
        izinli = {chr(10), chr(13)}

        for ad, metin in (("install.ps1", PS1), ("install.sh", SH)):
            suclular = [
                (i + 1, hex(ord(ch)))
                for i, satir in enumerate(metin.split(chr(10)))
                for ch in satir
                if ord(ch) < 32 and ch not in izinli
            ]

            assert not suclular, ad + " C0 kontrol karakteri: " + repr(suclular[:5])

    def test_sed_geri_basvurusu_girintiyi_koruyor(self):
        # Yakalanan girinti degistirmede KULLANILMALI. Kullanilmazsa
        # "  skin: default" sifirinci sutuna duser, display: altindaki
        # yuvalanma bozulur ve YAML'in anlami degisir.
        satirlar = [l for l in SH.split(chr(10)) if "skin: the-fool/" in l]

        assert len(satirlar) == 1, satirlar
        assert chr(92) + "1skin: the-fool" in satirlar[0], satirlar[0]

    def test_skin_mevcut_config_uzerinde_de_calisiyor(self):
        # Kapi "bu kosu config'i olusturduysa" idi; hicbir sey korumuyordu
        # cunku yeniden yazilan tek deger upstream'in secilmemis
        # varsayilani. Kapi yuzunden daha once kurmus HER makine
        # upstream paletinde kaliyordu.
        assert "$configIsNew" not in PS1
        assert "config_is_new" not in SH


class TestCalisanUygulamaDURDURULUYOR:
    """Kaldirma adimi, uygulamanin GERCEK surec adini durdurmali.

    Olculen hata: ``productName`` "The Fool" -- BOSLUKLU -- oldugu icin
    kurulan calistirilabilir "The Fool.exe" ve Windows sureci
    "The Fool" olarak bildiriyor. Betik ise 'TheFool' ve 'Fool'
    ariyordu; ikisi de hicbir seye uymadi.

    Sonuc kullanicinin log'unda gorundu: uygulama acikken yeniden
    kurulum "These paths could not be removed" dedi, ardindan klonlama
    adimi agacin tamamini ".broken-<zaman>" olarak yeniden adlandirdi
    ve o kopya diskte kaldi -- bu adimin sozu verdigi "sifir kalinti"
    yeniden kurulumun tam tersi.

    Test, listeyi package.json'daki ada BAGLIYOR: urun adi degisirse
    ve liste guncellenmezse burasi kirilir.
    """

    def test_urun_adi_durdurma_listesinde(self):
        import json

        pkg = json.loads(
            (REPO_ROOT / "apps" / "desktop" / "package.json").read_text(encoding="utf-8")
        )
        urun = pkg["build"]["productName"]

        blok = PS1.split("function Stop-FoolProcesses")[1].split("function ")[0]

        assert "'" + urun + "'" in blok, (
            "Stop-FoolProcesses '" + urun + "' surecini aramiyor; "
            "calisan uygulama durdurulmuyor"
        )

    def test_node_ve_electron_da_kapsamda(self):
        # Kurulum dizini masaustu uygulamasinin node_modules'unu ve
        # Electron calisma zamanini barindiriyor; buradan baslamis bir
        # node ya da electron agaci uygulamanin kendisi kadar kilitler.
        blok = PS1.split("function Stop-FoolProcesses")[1].split("function ")[0]

        assert "'node'" in blok
        assert "'electron'" in blok

    def test_isim_disi_surecler_YOL_ile_sinirli(self):
        # Ada gore oldurmek kullanicinin alakasiz python/node surecini
        # kapatirdi. Kurulum kokunden calisiyor olmasi sarti guvenligi
        # saglayan sey.
        blok = PS1.split("function Stop-FoolProcesses")[1].split("function ")[0]

        assert "StartsWith($Root" in blok


class TestEskiKOKLER_TEMIZLENIYOR:
    """Yeniden adlandirma oncesi kalan veri kokleri de kaldirilmali.

    Olculen durum: yeniden adlandirma FOOL_HOME'u
    %LOCALAPPDATA%/hermes'ten %LOCALAPPDATA%/fool'a tasidi, aradaki bir
    yapi da %LOCALAPPDATA%/thefool kullandi. Kaldirma adimi YALNIZCA
    guncel koke bakiyordu, dolayisiyla eski kokler her yeniden kurulumdan
    sag cikti: diskte ikinci bir tam program kopyasi.

    Bu makinede olculdu: eski hermes koku 358 MB klon + 49 MB calisma
    zamani tasiyordu ve sessions/memories/skills/cron dizinlerinin HEPSI
    bostu -- saf program kalintisi.

    Ama bu herkes icin varsayilamaz. Hermes doneminde aylarca kullanmis
    birinin orada gercek oturumlari var. Bu yuzden sozlesme su: PROGRAM
    dizinleri kaldirilir, kok ise ANCAK icinde hicbir dosya kalmadiysa
    kaldirilir.
    """

    def _blok(self, metin, ad):
        return metin.split(ad)[1].split(chr(10) + "function ")[0]

    def test_ps1_kendi_eski_kokumuzu_tariyor(self):
        blok = self._blok(PS1, "function Remove-LegacyRoots")

        assert "LOCALAPPDATA" + chr(92) + "thefool" in blok

    def test_UPSTREAM_hermes_koku_HEDEFLENMIYOR(self):
        # README acikca "will not touch an existing Hermes config" diyor ve
        # %LOCALAPPDATA%/hermes upstream Hermes Agent'in KENDI kurulum yeri.
        # Yazarin makinesinde bakildi: oradaki klonun origin'i tanimsiz ve
        # gecmisi upstream'inki gibi okunuyor -- yani sahipligi kanitlanamaz
        # ve yanlis tahmin baska bir urunun kurulumunu yok eder.
        blok = self._blok(PS1, "function Remove-LegacyRoots")
        sh_blok = SH.split("remove_legacy_roots() {")[1].split(chr(10) + "}")[0]

        assert 'LOCALAPPDATA' + chr(92) + 'hermes"' not in blok
        assert '"$HOME/.hermes"' not in sh_blok

    def test_ps1_veri_varsa_kok_KORUNUYOR(self):
        blok = self._blok(PS1, "function Remove-LegacyRoots")

        # Kokun silinmesi, geriye dosya kalmamis olmasina bagli olmali.
        assert "-Recurse -File" in blok
        assert "$left.Count -eq 0" in blok

    def test_ps1_aktif_koke_dokunmuyor(self):
        # Guncel FOOL_HOME eski adlardan biriyse silmek felaket olurdu.
        blok = self._blok(PS1, "function Remove-LegacyRoots")

        assert "$full -eq $current" in blok

    def test_ps1_kaldirma_akisina_BAGLI(self):
        # Yazilip cagrilmamasi sessiz bir no-op olurdu.
        assert "Remove-LegacyRoots -CurrentRoot" in PS1

    def test_sh_ayni_sozlesmeyi_tasiyor(self):
        # Bu depoda tekrar eden hata: ders kardes betige tasinmiyor.
        blok = SH.split("remove_legacy_roots() {")[1].split(chr(10) + "}")[0]

        assert "$HOME/.thefool" in blok
        assert "-type f" in blok
        assert '"$_left" -eq 0' in blok
        assert "remove_legacy_roots " in SH.split("remove_legacy_roots() {")[2 - 1]


class TestOluPATHGirdileri_TEMIZLENIYOR:
    """Baska koklerden kalan OLU PATH girdileri kaldirilmali.

    Olculen durum: yazarin kendi makinesinde kullanici PATH'i bu program
    icin SEKIZ girdi tasiyordu, ALTISI artik var olmayan bir dizini
    gosteriyordu -- eski %LOCALAPPDATA%/hermes koku, ara
    %LOCALAPPDATA%/thefool koku, adi degistirilmis bir hermes-agent
    klonu, ve bir atilabilir test kurulumunun %TEMP% altinda biraktigi
    iki girdi.

    Bu kozmetik degil: ONDEKI canli girdi kaldirilir kaldirilmaz
    terminaldeki ``fool`` komutu, hala binary'si duran hangi eski
    kopyaya rastlarsa ona cozulmeye baslar -- "ayni makinede iki
    kurulum" sorununun en sinsi hali.

    Guvenligi saglayan sey VAR OLMA kontrolu: bir girdi YALNIZCA kendi
    dizini gercekten yok oldugunda dusuyor. Hala var olan bir ucuncu
    taraf Hermes kurulumu (README'nin dokunmama sozu verdigi) yerinde
    kalir. Regex'in davranisi PowerShell'in kendisiyle elle dogrulandi:
    yazarin gercek PATH'inde 4 olu girdiyi atti, 3 canli/var-olan girdiyi
    (biri ucuncu taraf hermes olabilecek) birakti.
    """

    def _blok(self):
        return PS1.split("function Remove-FoolPathEntries")[1].split(chr(10) + "function ")[0]

    def test_ikinci_geciste_VAR_OLMA_kontrolu_var(self):
        blok = self._blok()

        assert "Test-Path -LiteralPath $entry" in blok

    def test_bilinen_ADLARIN_hepsi_tariniyor(self):
        blok = self._blok()

        for ad in ("fool", "thefool", "hermes", "fool-agent", "hermes-agent"):
            assert ad in blok, ad

    def test_kaldirma_akisina_BAGLI(self):
        # Yazilip cagrilmamasi sessiz bir no-op olurdu.
        assert "Remove-FoolPathEntries -Root $Root" in PS1

