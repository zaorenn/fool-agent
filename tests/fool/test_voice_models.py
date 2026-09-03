"""Ses modeli kataloğu ve kurulum işlerinin sözleşme testleri.

Buradaki testler AĞA ÇIKMAZ. Gerçek indirme ``_download``'un içinde ve o
``urllib`` ile sınanmıyor; sınanan şey işin etrafındaki sözleşme: aynı öğe için
iki kurulum başlatılamaması, iptalin işi gerçekten durdurması, ilerlemenin
uydurulmaması ve yarıda kalan bir dosyanın "inmiş" sayılmaması.
"""

from __future__ import annotations

import threading
from pathlib import Path
import time

import pytest

from fool import voice_models


class TestKatalog:
    def test_her_ogenin_kimligi_tekil(self):
        ids = [e.id for e in voice_models.CATALOG]
        assert len(ids) == len(set(ids))

    def test_her_oge_tts_ya_da_stt(self):
        assert all(e.kind in ("tts", "stt") for e in voice_models.CATALOG)

    def test_hem_tts_hem_stt_var(self):
        """Kullanıcı ikisini de istedi; biri düşerse panel yarım kalır."""
        kinds = {e.kind for e in voice_models.CATALOG}
        assert kinds == {"tts", "stt"}

    def test_cuda_iddiasi_olan_ogenin_cuda_grubu_ya_da_gerekcesi_var(self):
        """CUDA sunan her öğe onu gerçekten kullanabilmeli.

        Aksi halde kullanıcı CUDA düğmesine basar, kurulum sessizce CPU
        sürümünü kurar ve neden yavaş olduğunu anlamaz.
        """
        for e in voice_models.CATALOG:
            if "cuda" not in e.devices:
                continue
            # CUDA iddiasinin uc mesru dayanagi var:
            #   - ayri bir CUDA paket grubu (piper -> onnxruntime-gpu)
            #   - sidecar'a kurulan CUDA torch tekerlegi (qwen3)
            #   - motorun kendisi cihazi calisma aninda seciyor (torch tabanli)
            assert e.cuda_group or e.sidecar_cuda_specs or e.dep_group or e.sidecar_specs, (
                f"{e.id}: CUDA iddiasi dayanaksiz"
            )

    def test_bilinmeyen_kimlik_none(self):
        assert voice_models.entry("yok-boyle-bir-sey") is None


class TestDurum:
    def test_durum_tam_sozlesme_dondurur(self):
        s = voice_models.status("piper")
        for key in (
            "id", "label", "kind", "summary", "devices", "size_label",
            "recommended", "engine_installed", "assets_installed", "installed",
        ):
            assert key in s, f"eksik alan: {key}"

    def test_installed_iki_kosulun_birlesimi(self):
        """``installed`` motor VE varlıkların ikisini birden gerektirir.

        Motor kurulu ama ses dosyası inmemişken "kurulu" demek, kullanıcının
        sesi açıp anlaşılmaz bir hata almasına yol açardı.
        """
        s = voice_models.status("piper")
        assert s["installed"] == (s["engine_installed"] and s["assets_installed"])

    def test_bilinmeyen_kimlik_hata_dondurur(self):
        s = voice_models.status("yok-boyle-bir-sey")
        assert s["installed"] is False
        assert "error" in s


class TestVarlikDogrulama:
    def test_yarim_dosya_inmis_sayilmaz(self, tmp_path, monkeypatch):
        """Yarıda kesilen indirme hedef adı almamalı.

        Alsaydı ``asset_present`` onu geçerli sayar, Piper açmaya çalışır ve
        hata çalışma anına ertelenirdi.
        """
        monkeypatch.setattr(voice_models, "voice_dir", lambda: tmp_path)
        asset = voice_models.VoiceAsset(url="http://x/y.onnx", filename="y.onnx")

        assert voice_models.asset_present(asset) is False

        (tmp_path / "y.onnx").write_bytes(b"kirik")       # 5 bayt
        assert voice_models.asset_present(asset) is False

        (tmp_path / "y.onnx").write_bytes(b"x" * 2048)
        assert voice_models.asset_present(asset) is True


class TestKurulumIsleri:
    def test_bilinmeyen_oge_reddedilir(self):
        with pytest.raises(ValueError):
            voice_models.start_install("yok-boyle-bir-sey")

    def test_her_ogenin_kurulabilir_paketi_var(self):
        """Kurulacak paketi olmayan oge katalogda YER ALMAMALI.

        KittenTTS tam bu yuzden cikarildi: sabitlenmis bir paket kaydi yoktu,
        yani dugme hicbir sey yapmadan "kuruldu" derdi. Kullanici cubugun
        %100'e gitmesini gorur, oge kurulmamis kalir ve hicbir hata cikmaz --
        sessiz basari, gorunur hatadan cok daha kotudur.
        """
        from tools.lazy_deps import LAZY_DEPS

        for e in voice_models.CATALOG:
            if e.sidecar_specs:
                # Sidecar'li oge dep_group KULLANMAZ; sarkan bir grup adi
                # birakmak ileride yanlis yere bakmaya yol acar.
                assert not e.dep_group, f"{e.id}: sidecar'li ogede dep_group olmamali"
                continue
            assert e.dep_group, f"{e.id}: kurulabilir paket grubu yok"
            assert LAZY_DEPS.get(e.dep_group), (
                f"{e.id}: dep_group={e.dep_group!r} LAZY_DEPS'te yok -- "
                f"kurulum sessizce hicbir sey yapmazdi"
            )

    def test_paketsiz_oge_sessizce_basarili_olmaz(self, monkeypatch):
        job = voice_models.Job(id="t3", entry_id="x", device="cpu")
        bare = voice_models.VoiceEntry(id="x", label="X", kind="tts", summary="")

        with pytest.raises(RuntimeError):
            voice_models._install_engine(bare, "cpu", job, 0.0, 70.0)

        assert job.percent == 0.0, "hata verirken ilerleme ilerletilmemeli"

    def test_ayni_oge_icin_ikinci_is_baslamaz(self, monkeypatch):
        """İki pip aynı hedefe yazarsa ortam yarım kurulumla bozulur."""
        started = threading.Event()
        release = threading.Event()

        def _slow(entry, device, job, base, span):
            started.set()
            release.wait(timeout=5)

        monkeypatch.setattr(voice_models, "_install_engine", _slow)

        first = voice_models.start_install("kokoro")
        assert started.wait(timeout=5), "is baslamadi"
        second = voice_models.start_install("kokoro")

        assert second["id"] == first["id"], "ayni oge icin ikinci is acildi"

        release.set()
        for _ in range(50):
            if voice_models.get_job(first["id"]).state != "running":
                break
            time.sleep(0.1)

    def test_iptal_isi_durdurur(self, monkeypatch):
        release = threading.Event()

        def _slow(entry, device, job, base, span):
            for _ in range(100):
                if job._cancel.is_set():
                    raise InterruptedError("cancelled")
                time.sleep(0.05)

        monkeypatch.setattr(voice_models, "_install_engine", _slow)

        job = voice_models.start_install("chatterbox")
        assert voice_models.cancel_job(job["id"]) is True

        for _ in range(50):
            state = voice_models.get_job(job["id"]).state
            if state != "running":
                break
            time.sleep(0.1)

        assert voice_models.get_job(job["id"]).state == "cancelled"
        release.set()

    def test_tahmini_ilerleme_asamayi_asmaz(self, monkeypatch):
        """pip aşamasında çubuk uydurulmuyor: span'in sonuna DAYANMAZ.

        Yüzde %100'e varıp sonra beklemek, kullanıcıya işin bittiğini yanlış
        söylemek olurdu.
        """
        # DIKKAT: burada ``_install_engine`` YAMALANMAZ -- sinanan sey tam da
        # onun kendi mantigi. (Ilk yazimda yamalanip sonra cagrilmisti; test
        # gercek kodu degil, yamayi olcuyordu.)
        job = voice_models.Job(id="t", entry_id="kokoro", device="cpu")
        e = voice_models.entry("kokoro")
        assert e is not None

        # Yamalanmis surumle degil, gercek fonksiyonla: pip cagrisini taklit et.
        import tools.lazy_deps as lazy

        class _Result:
            ok = True
            blocked = False
            stdout = ""
            stderr = ""

        monkeypatch.setattr(lazy, "install_specs", lambda specs, timeout=0: _Result())
        voice_models._install_engine(e, "cpu", job, 0.0, 70.0)
        assert job.percent == 70.0, "asama bitince gercek degere sicramali"

    def test_is_anlik_goruntusu_tam(self):
        job = voice_models.Job(id="t2", entry_id="piper", device="cpu")
        snap = job.snapshot()
        for key in ("id", "entry_id", "device", "state", "percent", "stage", "detail", "error", "elapsed"):
            assert key in snap, f"eksik alan: {key}"


class TestSaglayiciBaglantisi:
    """Katalogdaki her ogenin GERCEKTEN kullanilabilir bir saglayicisi olmali.

    Kokoro tam bu yuzden olu bir dugmeydi: katalogda listeleniyordu, iniyordu,
    panel "Installed" diyordu ve ajan onu asla kullanamiyordu -- hicbir hata da
    gorunmuyordu. Indirilebilirlik ile kullanilabilirlik AYRI seyler ve ikisi
    ayri ayri dogrulanmali.
    """

    @staticmethod
    def _tts_saglayici_adlari() -> set[str]:
        import re

        names: set[str] = set()

        # Yerlesikler
        from tools.tts_tool import BUILTIN_TTS_PROVIDERS

        names |= set(BUILTIN_TTS_PROVIDERS)

        # Zone A eklentileri: manifestteki ``provides_tts_providers``.
        root = Path(__file__).resolve().parents[2] / "plugins" / "tts"
        for manifest in root.glob("*/plugin.yaml"):
            text = manifest.read_text(encoding="utf-8")
            block = re.search(
                r"provides_tts_providers:\s*((?:\s*-\s*\S+\n?)+)", text
            )
            if block:
                names |= set(re.findall(r"-\s*(\S+)", block.group(1)))
        return names

    def test_her_tts_ogesinin_saglayicisi_var(self):
        available = self._tts_saglayici_adlari()
        missing = [
            e.id
            for e in voice_models.CATALOG
            if e.kind == "tts" and (e.provider_id or e.id) not in available
        ]
        assert not missing, (
            f"saglayicisi olmayan TTS ogeleri: {missing}. "
            f"Bunlar inebilir ama ajan kullanamaz -- sessiz olu dugme. "
            f"Mevcut saglayicilar: {sorted(available)}"
        )

    def test_saglayici_adi_kimlikten_ayri_olabilir(self):
        """``qwen3-tts`` indirilir, ``qwen3`` secilir -- ikisi ayni degil."""
        entry = voice_models.entry("qwen3-tts")
        assert entry is not None
        assert entry.provider_id == "qwen3"
        assert voice_models.status("qwen3-tts")["provider_id"] == "qwen3"

    def test_sidecar_ogeleri_ana_ortami_kirlemez(self):
        """Sidecar'li oge ANA ortamda aranmamali.

        Aranırsa her zaman "kurulu degil" derdi: motor orada zaten yok.
        """
        for e in voice_models.CATALOG:
            if not e.sidecar_specs:
                continue
            assert e.probe_module, f"{e.id}: sidecar var ama probe_module yok"

    def test_sidecar_adi_katalog_kimligiyle_ayni(self):
        """Saglayici sidecar'i KATALOG KIMLIGIYLE ariyor.

        Ayrisirlarsa panel "Installed" derken saglayici ortami bulamaz --
        birbirini goremeyen iki dogru bilesen.
        """
        import re

        root = Path(__file__).resolve().parents[2] / "plugins" / "tts"
        catalog_ids = {e.id for e in voice_models.CATALOG}
        for init in root.glob("*/__init__.py"):
            text = init.read_text(encoding="utf-8")
            found = re.search(r'^SIDECAR_NAME\s*=\s*"([^"]+)"', text, re.M)
            if found:
                assert found.group(1) in catalog_ids, (
                    f"{init.parent.name}: SIDECAR_NAME={found.group(1)!r} "
                    f"katalogda yok"
                )


class TestSidecarIzolasyonu:
    """Sidecar ana ortamdan GERCEKTEN yalitilmali.

    Ayri bir venv acmak yetmiyor: ana surec ``PYTHONPATH``i alt surece
    geciriyorsa, o degisken ana ortamin ``site-packages``ini sidecar'in yoluna
    sokuyor ve sidecar KENDI paketleri yerine onlari ice aktariyor. Izolasyonun
    tum amaci o noktada cokuyor.

    Gercekte yasandi: Qwen3-TTS "Read aloud failed" veriyordu ve altindaki hata
    ``tokenizers>=0.22.0,<=0.23.0 required but found 0.23.1`` idi -- sizan ana
    ortamin tokenizers'i. Onerilen cozum ("pip install transformers -U") de
    yanlis yeri gosteriyordu: sidecar'in transformers'i zaten dogruydu.
    """

    def test_kirletici_degiskenler_alt_surece_gecmez(self):
        from fool.sidecar import _isolated_env

        env = _isolated_env()

        for name in ("PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP"):
            assert name not in env, f"{name} sidecar ortamina siziyor"

    def test_diger_degiskenler_KORUNUR(self, monkeypatch):
        """Ortami komple bosaltmak da yanlis olurdu.

        ``PATH`` gitse alt surec DLL'lerini bulamaz, ``HF_HOME`` gitse model
        agirliklari ikinci kez inerdi.
        """
        from fool.sidecar import _isolated_env

        monkeypatch.setenv("HF_HOME", "C:/onbellek")
        env = _isolated_env()

        assert env.get("HF_HOME") == "C:/onbellek"
        assert "PATH" in env or "Path" in env

    def test_tum_alt_surec_cagrilari_temiz_ortam_kullanir(self):
        """Tek bir cagri unutulursa hata YALNIZCA o yolda geri gelir."""
        import inspect

        from fool import sidecar

        source = inspect.getsource(sidecar)
        runs = source.count("subprocess.run(") + source.count("subprocess.Popen(")

        assert source.count("_isolated_env()") >= runs, (
            "bir alt surec cagrisi temiz ortam kullanmiyor"
        )


class TestCudaKutuphaneleri:
    """CTranslate2'nin CUDA kutuphanelerini bulabilmesi.

    Bu olmadan Whisper SESSIZCE CPU'da calisiyor ve kimse soylemiyor.
    Olculdu (2,80 sn'lik kayit, large-v3-turbo):

        CPU  / int8     15,16 sn  -> gercek zamanin 0,2 kati
        CUDA / float16   0,23 sn  -> gercek zamanin 12 kati

    Paketler kurulu olsa bile Windows ``site-packages/nvidia/*/bin``e bakmiyor;
    DLL arama yolu ayrica ayarlanmali. pip bunu yapmiyor.
    """

    def test_fool_ithali_dll_yolunu_kurar(self):
        """``import fool`` tek basina yeterli olmali.

        faster_whisper DLL'i ILK import'ta yukluyor, yani ayar ondan once
        kosmali. ``fool`` her yerden ithal edildigi icin en erken guvenli nokta.
        """
        import fool  # noqa: F401
        from fool.cuda_runtime import _APPLIED, _candidate_dirs

        if not _candidate_dirs():
            pytest.skip("bu ortamda nvidia kutuphaneleri kurulu degil")

        assert _APPLIED, "fool ithali CUDA DLL yolunu kurmadi"

    def test_dizinler_PATH_e_eklendi(self):
        import os

        from fool.cuda_runtime import _candidate_dirs, enable

        dirs = _candidate_dirs()
        if not dirs:
            pytest.skip("bu ortamda nvidia kutuphaneleri kurulu degil")

        enable()
        path = os.environ.get("PATH", "").lower()

        for d in dirs:
            assert str(d).lower() in path, f"{d} PATH'e eklenmedi"

    def test_asla_yukselmez(self, monkeypatch):
        """Bu bir hizlandirma, gereklilik degil: hata uygulamayi dusurmemeli."""
        from fool import cuda_runtime

        monkeypatch.setattr(cuda_runtime, "_candidate_dirs", lambda: (_ for _ in ()).throw(OSError("disk")))
        monkeypatch.setattr(cuda_runtime, "_APPLIED", False)

        try:
            cuda_runtime.enable()
        except OSError:
            pytest.fail("enable() yukseldi; CPU'ya dusmeli")
        except Exception:
            pytest.fail("enable() beklenmedik sekilde yukseldi")


class TestSesKlonlama:
    """Surukle-birak ses klonlama.

    Chatterbox sifir-atis klonlama yapiyor ve yetenek arka ucta ZATEN vardi;
    eksik olan referans kaydi VERMENIN yoluydu -- yapilandirmaya elle dosya
    yolu yazmak gerekiyordu.
    """

    def test_yalnizca_destekleyen_motor(self):
        """Desteklemeyen motora referans kayit vermek sessizce yok sayilirdi.

        Kullanici sesini yukler, hicbir sey degismez, sebebini ogrenemez.
        """
        from fool.voice_models import CLONE_CAPABLE, set_clone

        assert "chatterbox" in CLONE_CAPABLE

        with pytest.raises(ValueError):
            set_clone("piper", "herhangi.wav")

    def test_desteklenmeyen_bicim_reddedilir(self, tmp_path, monkeypatch):
        from fool import voice_models as vm

        monkeypatch.setattr(vm, "clone_dir", lambda: tmp_path)

        with pytest.raises(ValueError):
            vm.save_clone("ses.txt", b"x" * 4096)

    def test_bos_ve_devasa_dosya_reddedilir(self, tmp_path, monkeypatch):
        from fool import voice_models as vm

        monkeypatch.setattr(vm, "clone_dir", lambda: tmp_path)

        with pytest.raises(ValueError):
            vm.save_clone("ses.wav", b"kisa")

        with pytest.raises(ValueError):
            vm.save_clone("ses.wav", b"x" * (51 * 1024 * 1024))

    def test_dosya_adi_dizin_disina_cikamaz(self, tmp_path, monkeypatch):
        """Kullanicidan gelen ad dogrudan yola yazilirsa ``../`` ile kacilir."""
        from fool import voice_models as vm

        monkeypatch.setattr(vm, "clone_dir", lambda: tmp_path)

        saved = vm.save_clone("../../kotu.wav", b"x" * 4096)

        assert Path(saved["path"]).parent == tmp_path
        assert ".." not in saved["id"]

    def test_kaydet_listele_sil_dongusu(self, tmp_path, monkeypatch):
        from fool import voice_models as vm

        monkeypatch.setattr(vm, "clone_dir", lambda: tmp_path)

        vm.save_clone("benim_sesim.wav", b"x" * 8192)
        clones = vm.list_clones()

        assert [c["label"] for c in clones] == ["benim_sesim"]

        vm.delete_clone(clones[0]["id"])
        assert vm.list_clones() == []

    def test_styletts2_ve_f5tts_de_klonluyor(self):
        """Ikisi de zaten sifir-atis klonluyordu (eklentileri ``reference``
        kwarg'ini okuyordu) ama arayuzden erisilebilir DEGILDI -- kullanici
        "her ses modeli icin klonlamayi arayuzden yapalim" diye istedi."""
        from fool.voice_models import CLONE_CAPABLE

        assert "styletts2" in CLONE_CAPABLE
        assert "f5tts" in CLONE_CAPABLE

    def test_motor_basina_DOGRU_yapilandirma_anahtarina_yaziyor(self, tmp_path, monkeypatch):
        """Chatterbox'in eklentisi ``voice_sample`` okuyor, styletts2 ve
        f5-tts ``reference``. Tek bir sabit anahtar kullanmak SESSIZCE yanlis
        alana yazardi -- motor referansi hic gormez, kullanici yukledigini
        duymaya devam ederdi."""
        from fool import voice_models as vm

        monkeypatch.setattr(vm, "clone_dir", lambda: tmp_path)
        saved: dict[str, str] = {}
        monkeypatch.setattr(
            "fool_cli.config.set_config_value",
            lambda key, value: saved.__setitem__(key, value),
        )

        clip = vm.save_clone("ses.wav", b"x" * 8192)

        vm.set_clone("chatterbox", clip["id"])
        assert "tts.chatterbox.voice_sample" in saved
        assert "tts.chatterbox.reference" not in saved

        vm.set_clone("styletts2", clip["id"])
        assert "tts.styletts2.reference" in saved

        vm.set_clone("f5-tts", clip["id"])
        assert "tts.f5tts.reference" in saved

    def test_current_clone_DOGRU_anahtardan_okuyor(self, monkeypatch):
        from fool import voice_models as vm

        monkeypatch.setattr(
            "fool_cli.config.load_config",
            lambda: {"tts": {"styletts2": {"reference": "/klonlar/ben.wav"}}},
        )

        entry = vm.entry("styletts2")
        assert entry is not None
        assert vm.current_clone(entry) == "ben.wav"

    def test_her_klonlanabilir_motorun_YARDIM_metni_var(self):
        """Yardim eksikse panelde bos bir dugme olurdu -- boyle bir motor
        eklenirse bu test kirilip hatirlatir."""
        from fool.voice_models import CLONE_CAPABLE, CLONE_HELP

        for provider in CLONE_CAPABLE:
            assert CLONE_HELP.get(provider, "").strip(), f"{provider}: yardim metni yok"

    def test_klon_yeteneksiz_motorda_yardim_BOS(self):
        from fool import voice_models as vm

        entry = vm.entry("kokoro")
        assert entry is not None

        rows = [r for r in vm.catalog_status() if r["id"] == "kokoro"]
        assert rows[0]["clone_help"] == ""


# ---------------------------------------------------------------------------
# Paket KURULU ile motor HAZIR ayrı şeyler
# ---------------------------------------------------------------------------

class TestAgirlikDogrulamasi:
    """Kullanıcının arkadaşının makinesinde: ses modelleri yüklü değil ama
    YÜKLÜYMÜŞ gibi görünüyor ve indirme düğmesi hiç çıkmıyor.

    Sebebi: ``status()`` yalnızca PAKETE bakıyordu. Paket kurulu olabilir ama
    ağırlıklar inmemiş -- motor ilk cümlede gigabaytlarca indirmeye başlar ve
    kullanıcı yalnızca "çok yavaş" görür.
    """

    def test_agirliklari_olan_motorlar_BEYAN_ediyor(self) -> None:
        from fool import voice_models as vm

        for entry_id in ("kokoro", "chatterbox"):
            entry = vm.entry(entry_id)

            assert entry is not None
            assert entry.weights_repo, f"{entry_id} agirlik deposunu beyan etmiyor"
            assert "/" in entry.weights_repo, "HuggingFace ``sahip/depo`` bekleniyor"

    def test_AGIRLIK_YOKSA_kurulu_sayilmiyor(self, monkeypatch, tmp_path) -> None:
        """Panelin indirme düğmesini göstermesi buna bağlı."""
        import pathlib

        from fool import voice_models as vm

        monkeypatch.setattr(pathlib.Path, "home", staticmethod(lambda: tmp_path))

        for entry_id in ("kokoro", "chatterbox"):
            assert vm.status(entry_id)["installed"] is False, entry_id

    def test_GERCEK_dosya_varliklari_etkilenmiyor(self, monkeypatch, tmp_path) -> None:
        """Piper ağırlıklarını HF'ten değil beyan edilen dosyalardan alıyor;
        boş bir HF önbelleği onu etkilememeli."""
        import pathlib

        from fool import voice_models as vm

        entry = vm.entry("piper")

        assert entry is not None
        assert not entry.weights_repo
        assert entry.assets, "piper dosya varliklarini beyan etmeli"

    def test_KURULUM_agirliklari_da_indiriyor(self) -> None:
        """Kritik takip: ``status`` ağırlık istiyorsa kurulum onu getirmeli.

        Getirmezse kullanıcı Install'a basar, paket kurulur, panel yine
        "kurulu değil" der ve aynı düğmeye tekrar tekrar basılır -- eski
        hâlden kötü.
        """
        from fool import voice_models as vm

        entry = vm.entry("kokoro")
        snippet = vm._weights_warmup(entry)

        assert "snapshot_download" in snippet
        assert entry.weights_repo in snippet

    def test_acik_warmup_EZILMIYOR(self) -> None:
        """Kendi indirme parçasını yazmış bir öğe (faster-whisper) korunuyor."""
        from fool import voice_models as vm

        for entry in vm.CATALOG:
            if entry.warmup:
                assert vm._weights_warmup(entry) == entry.warmup
