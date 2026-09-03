"""Ayarlarda görünen ifade, motorun GERÇEKTEN dinlediği ifade olmalı.

Ölçülen hata
------------
Kullanıcının bildirdiği: "wake word ayarlarda hey fool olarak geçiyor... o
ayarlardaki neyse o sözcük wake wordümüz olmalı."

Sebep, kodun kendi itirafında duruyordu::

    "phrase": "hey fool",                                  # ayarlarda görünen
    _BUNDLED_MODEL_ALIASES = {"", "hey_hermes", "hey fool", "fool"}
    def wake_phrase(...): '''...purely cosmetic; engine keys detection.'''

Varsayılan sağlayıcı ``openwakeword`` ve o, paketlenmiş ``hey_hermes``
modelini yüklüyor. Ekrandaki yazı ile kulağın duyduğu şey birbirinden
bağımsızdı -- kullanıcı yazana bakıp konuşuyor ve hiçbir şey olmuyordu.

Üç motorun üçü de anahtarını FARKLI yerden alıyor, o yüzden tek bir alanı
okumak yetmiyor. Bu dosya o üç yolu ayrı ayrı tutuyor.
"""

from tools.wake_word import (
    BUNDLED_MODEL_PHRASE,
    effective_wake_phrase,
    openwakeword_phrases,
    wake_phrase,
)


class TestGercekIfade:
    def test_openwakeword_VARSAYILANI_gomulu_modeli_soyluyor(self):
        # Tam olarak bildirilen hata: alan "hey fool", kulak "hey hermes".
        cfg = {"provider": "openwakeword", "phrase": "hey fool"}

        assert wake_phrase(cfg) == "hey fool"
        assert effective_wake_phrase(cfg) == BUNDLED_MODEL_PHRASE

    def test_gomulu_model_ADIYLA_verilse_de_ayni(self):
        cfg = {"provider": "openwakeword", "openwakeword": {"model": "hey_hermes"}}

        assert effective_wake_phrase(cfg) == BUNDLED_MODEL_PHRASE

    def test_yerlesik_model_INSAN_okunusuna_ceviriliyor(self):
        cfg = {"provider": "openwakeword", "openwakeword": {"model": "hey_jarvis"}}

        assert effective_wake_phrase(cfg) == "hey jarvis"

    def test_ozel_model_DOSYA_adindan_okunuyor(self):
        cfg = {"provider": "openwakeword", "openwakeword": {"model": "/tmp/hey_ada.onnx"}}

        assert effective_wake_phrase(cfg) == "hey ada"

    def test_sherpa_YAZILAN_ifadeyi_dinliyor(self):
        # Tek gerçek özel yol: açık sözcük dağarcığı.
        cfg = {"provider": "sherpa", "phrase": "merhaba dostum"}

        assert effective_wake_phrase(cfg) == "merhaba dostum"

    def test_porcupine_KENDI_anahtar_sozcugunu_dinliyor(self):
        # ``phrase`` burada da kozmetik -- motor ``porcupine.keyword`` okuyor.
        cfg = {"provider": "porcupine", "phrase": "hey fool", "porcupine": {"keyword": "computer"}}

        assert effective_wake_phrase(cfg) == "computer"

    def test_porcupine_anahtar_sozcugu_YOKSA_motorun_varsayilani(self):
        cfg = {"provider": "porcupine", "phrase": "hey fool"}

        assert effective_wake_phrase(cfg) == "jarvis"


class TestHazirIfadeler:
    def test_gomulu_model_HER_ZAMAN_listede(self):
        # Paket kurulu olmasa bile gömülü model çalışıyor (yol ile yükleniyor),
        # o yüzden listeden hiçbir zaman düşmemeli.
        models = {item["model"] for item in openwakeword_phrases()}

        assert "hey_hermes" in models

    def test_gomulu_modelin_ifadesi_DOGRU(self):
        bundled = next(
            item for item in openwakeword_phrases() if item["model"] == "hey_hermes"
        )

        assert bundled["phrase"] == BUNDLED_MODEL_PHRASE

    def test_liste_SABIT_YAZILMIYOR(self):
        # Paket kendi kataloğunu taşıyor ve sürümle değişiyor. Uydurulmuş bir
        # liste, kullanıcının seçip hiçbir zaman tetiklenmeyen bir ifadeye
        # geçmesi demekti.
        import inspect

        import tools.wake_word as module

        source = inspect.getsource(module.openwakeword_phrases)

        assert "from openwakeword import MODELS" in source


class TestMotorKatalogu:
    def test_kurulu_olmayan_motor_KULLANILAMAZ(self):
        # Kullanıcının kalıcı kuralı: "kurulu olmayan bir motor seçilebilir
        # olmamalı."
        from fool.wake_engines import catalog

        for engine in catalog():
            if not engine["installed"]:
                assert not engine["usable"]
                assert engine["blocked_reason"]

    def test_uc_motor_da_listeleniyor(self):
        from fool.wake_engines import catalog

        assert {engine["id"] for engine in catalog()} == {
            "openwakeword",
            "porcupine",
            "sherpa",
        }

    def test_YALNIZCA_sherpa_serbest_ifade(self):
        # Sabit dağarcıklı bir motorda serbest metin sunmak, yazılanın hiçbir
        # zaman tanınmaması demekti -- düzeltilen hatanın kaynağı.
        from fool.wake_engines import catalog

        custom = {engine["id"] for engine in catalog() if engine["custom_phrase"]}

        assert custom == {"sherpa"}

    def test_sabit_dagarcikli_motor_ifadelerini_SUNUYOR(self):
        from fool.wake_engines import catalog

        built_in = next(engine for engine in catalog() if engine["id"] == "openwakeword")

        assert built_in["phrases"], "hazır ifade listesi boş olmamalı"

    def test_serbest_ifadeli_motor_LISTE_sunmuyor(self):
        from fool.wake_engines import catalog

        sherpa = next(engine for engine in catalog() if engine["id"] == "sherpa")

        assert sherpa["phrases"] == []

    def test_anahtar_isteyen_motor_ANAHTARINI_soyluyor(self):
        from fool.wake_engines import catalog

        porcupine = next(engine for engine in catalog() if engine["id"] == "porcupine")

        assert porcupine["env_key"] == "PORCUPINE_ACCESS_KEY"


class TestKurulum:
    """"Uygulamadan indirilebilir olmalı" -- kullanıcının kuralı."""

    def test_her_motorun_bir_paket_tanimi_VAR(self):
        # Tanım yoksa kurulum düğmesi çalışmayan bir düğme olurdu.
        from tools.lazy_deps import LAZY_DEPS

        from fool.wake_engines import ENGINES

        for spec in ENGINES:
            assert spec.feature in LAZY_DEPS, spec.id

    def test_bilinmeyen_motor_REDDEDILIYOR(self):
        import pytest

        from fool.wake_engines import start_install

        with pytest.raises(ValueError):
            start_install("yok-boyle-bir-motor")

    def test_sherpa_kurulumu_MODELI_de_indiriyor(self):
        # İlk uyandırma denemesinde indirmek, kullanıcının "kurdum ama
        # çalışmıyor" diye göreceği sessiz bir bekleme olurdu.
        import inspect

        import fool.wake_engines as module

        source = inspect.getsource(module._run)

        assert "_ensure_sherpa_model" in source


class TestDinleyiciYenidenKuruluyor:
    """Yapılandırma değişince KULAK da değişmeli.

    Ölçülen hata
    ------------
    Kullanıcının bildirdiği: "hey hermes dışındaki hiçbiri çalışmıyor."
    Günlükte motor ve ifade değişimleri görünüyordu ama ardından TEK BİR
    ``wake.start`` yoktu -- kulak ilk kurulduğu modelde kalmıştı.

    Sebep sessizce yutulan bir istisnaydı: ``stop_listening`` imzası
    ``def stop_listening(*, owner)`` ve üç çağıran da onu ``stop_listening()``
    diye çağırıyordu. Her çağrı ``TypeError`` atıyor, çevresindeki
    ``except Exception`` onu yutuyor ve dinleyici hiç durmuyordu.
    """

    def test_owner_ZORUNLU_ve_anahtar_kelimeli(self):
        # Muhafızın dayanağı: imza gevşerse aşağıdaki tarama anlamını yitirir.
        import inspect

        from tools.wake_word import stop_listening

        owner = inspect.signature(stop_listening).parameters["owner"]

        assert owner.kind is inspect.Parameter.KEYWORD_ONLY
        assert owner.default is inspect.Parameter.empty

    def test_HICBIR_cagri_sahipsiz_degil(self):
        """Hatanin kendisi: sahipsiz bir ``stop_listening`` cagrisi.

        METIN taramasi DEGIL, AST: ilk yazimda metin tariyordum ve testin
        kendi aciklamasindaki ornege takildi. Ayni tuzaga bu depoda daha once
        de dusuldu -- yorumu ya da docstring'i tarayan bir muhafiz kendi
        anlatimini hata sanar. AST yalnizca GERCEK cagrilari goruyor.
        """
        import ast
        from pathlib import Path

        tree = ast.parse(Path("tui_gateway/server.py").read_text(encoding="utf-8"))
        ownerless = [
            node.lineno
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "stop_listening"
            and not node.args
            and not node.keywords
        ]

        assert not ownerless, "sahipsiz stop_listening cagrilari: %s" % ownerless

    def test_durdurma_hatasi_YUTULMUYOR(self):
        # Hatayi 90 dakika gizleyen sey buydu: ``logger.debug`` ve devam.
        import inspect

        import tui_gateway.server as server

        source = inspect.getsource(server._stop_wake_listener)

        assert "logger.warning" in source
        assert "logger.debug" not in source

    def test_uc_mutasyon_da_ORTAK_yoldan_geciyor(self):
        # Ayri ayri yazilmis uc durdurma, dersin birinde ogrenilip
        # digerlerine tasinmamasi icin hazir bir zemindi.
        from pathlib import Path

        source = Path("tui_gateway/server.py").read_text(encoding="utf-8")

        for caller in ("wake.phrase", "wake.engine", "wake.model"):
            assert f'_stop_wake_listener("{caller}")' in source, caller
