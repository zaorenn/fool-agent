"""Konuşulan dil, cevabın dilinden BAĞIMSIZ.

İstenen (kullanıcının kendi ifadesi):

    "girlfriend modunda ona söylediğimde model cevabı ingilizce vermeli ki
     anlayabileyim, sesi japonca olmalı"

Yani ekranda okunan metin ile hoparlörden çıkan dil aynı olmak zorunda değil.

Neden persona ile çözülmedi
---------------------------
Persona tek bir dil söyleyebilir. "Japonca cevap ver" dersen kullanıcı cevabı
okuyamaz; "İngilizce cevap ver" dersen ses de İngilizce çıkar. İkisi aynı
anahtarda kaldığı sürece biri diğerini kaybettirir. Bu yüzden ayrı bir ayar:
``tts.speech_language``.

Neden motor dili de değişmek zorunda
------------------------------------
Ölçüldü: Türkçe bir cümle İngilizce motorla seslendirilince ``Merhaba`` ->
``Mehabal`` çıkıyor. Yalnızca metni çevirmek, Japonca metni İngilizce
fonetiğiyle okuyan bir motor bırakırdı -- ses üretilir, hata yok, kullanıcıya
"yine bozuk" olarak görünür. Sessiz başarısızlık.
"""

from __future__ import annotations

import pytest

from tools import tts_tool


# ---------------------------------------------------------------------------
# Ayarın okunması
# ---------------------------------------------------------------------------


def test_bos_ayar_davranisi_DEGISTIRMIYOR() -> None:
    assert tts_tool._speech_language({}) == ""
    assert tts_tool._speech_language({"speech_language": ""}) == ""
    assert tts_tool._speech_language({"speech_language": "   "}) == ""


def test_gecerli_dil_kodu_kabul_ediliyor() -> None:
    assert tts_tool._speech_language({"speech_language": "ja"}) == "ja"
    assert tts_tool._speech_language({"speech_language": "  JA  "}) == "ja"


def test_VARSAYILAN_deger_uyari_URETMIYOR(caplog: pytest.LogCaptureFixture) -> None:
    """``same`` bir dil kodu değil, "üst üste binme" demek -- ve VARSAYILAN.

    Ölçülen hata: sentinel tanınmıyordu, yani HİÇ AYAR YAPMAMIŞ bir kullanıcıda
    her cümlede şu satır düşüyordu::

        [The Fool] tts.speech_language='same' taninmadi ve yok sayildi.
        Desteklenenler: ar, da, de, el, en, ...

    Davranış doğruydu (çeviri yok), ama günlük kullanıcıya AYARININ
    REDDEDİLDİĞİNİ söylüyordu -- oysa reddedilen bir şey yoktu. Akışta cümle
    başına bir kez tekrarlanan bu satır, gerçek bir uyarıyı da görünmez
    yapıyordu.
    """
    from fool_cli.config_defaults import DEFAULT_CONFIG

    default = DEFAULT_CONFIG["tts"]["speech_language"]

    with caplog.at_level("WARNING"):
        assert tts_tool._speech_language({"speech_language": default}) == ""
        for sentinel in tts_tool.SPEECH_LANGUAGE_SENTINELS:
            assert tts_tool._speech_language({"speech_language": sentinel}) == ""
            assert tts_tool._speech_language({"speech_language": sentinel.upper()}) == ""

    assert caplog.text == "", f"varsayilan ayar uyari uretti: {caplog.text!r}"


def test_VARSAYILAN_deger_sentinel_kumesinde() -> None:
    """İkisi birlikte değişmeli: ``config_defaults`` başka bir sözcüğe geçerse
    ve burası bilmezse, uyarı sessizce geri gelir."""
    from fool_cli.config_defaults import DEFAULT_CONFIG

    assert DEFAULT_CONFIG["tts"]["speech_language"] in tts_tool.SPEECH_LANGUAGE_SENTINELS


def test_gecersiz_kod_SESSIZCE_yutulmuyor(caplog: pytest.LogCaptureFixture) -> None:
    """Sessizce yok saymak, kullanıcının ayarı yazıp hiçbir şey olmadığını
    görmesi demekti -- ve sebebi hiçbir yerde yazmıyordu."""
    with caplog.at_level("WARNING"):
        assert tts_tool._speech_language({"speech_language": "klingon"}) == ""

    assert "klingon" in caplog.text


# ---------------------------------------------------------------------------
# Çeviri + motor dili birlikte
# ---------------------------------------------------------------------------


def test_ayar_yokken_metne_DOKUNULMUYOR(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(*_a: object, **_k: object) -> str:  # pragma: no cover
        raise AssertionError("ayar yokken ceviri cagrilmamali")

    monkeypatch.setattr(tts_tool, "_translate_for_speech", _boom)

    text, cfg = tts_tool._apply_speech_language("hello", {"provider": "chatterbox"})

    assert text == "hello"
    assert cfg == {"provider": "chatterbox"}


def test_ayar_varken_metin_cevriliyor_VE_motor_dili_ayarlaniyor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(tts_tool, "_translate_for_speech", lambda t, target: "こんにちは")

    text, cfg = tts_tool._apply_speech_language(
        "hello", {"provider": "chatterbox", "speech_language": "ja"}
    )

    assert text == "こんにちは"
    # Motor da Japonca olmali -- yoksa Japonca metin Ingilizce fonetigiyle okunur.
    assert cfg["chatterbox"]["language"] == "ja"


def test_ozgun_yapilandirma_MUTASYONA_ugramiyor(monkeypatch: pytest.MonkeyPatch) -> None:
    """``_load_tts_config`` önbellekli; kaynağı değiştirmek sonraki çağrıları
    da sessizce Japoncaya çevirirdi."""
    monkeypatch.setattr(tts_tool, "_translate_for_speech", lambda t, target: "X")
    original = {"provider": "chatterbox", "speech_language": "ja", "chatterbox": {"device": "cuda"}}

    _, cfg = tts_tool._apply_speech_language("hello", original)

    assert original["chatterbox"] == {"device": "cuda"}
    assert cfg["chatterbox"]["language"] == "ja"
    assert cfg["chatterbox"]["device"] == "cuda"


# ---------------------------------------------------------------------------
# Başarısızlık: sessizlik DEĞİL
# ---------------------------------------------------------------------------


def test_ceviri_cokerse_OZGUN_metin_seslendiriliyor(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Yanlış dilde konuşmak, hiç konuşmamaktan iyi: kullanıcı sesi duyar ve
    bir şeyin ters gittiğini anlar. Sessizlik "TTS yine bozuldu" olarak
    okunuyor."""

    def _explode(**_k: object) -> object:
        raise RuntimeError("model kapali")

    monkeypatch.setattr("agent.auxiliary_client.call_llm", _explode, raising=False)

    with caplog.at_level("WARNING"):
        out = tts_tool._translate_for_speech("hello there", "ja")

    assert out == "hello there"


def test_bos_ceviri_OZGUN_metne_dusuyor(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        tts_tool, "_extract_auxiliary_message_content", lambda _r: "   "
    )
    monkeypatch.setattr(
        "agent.auxiliary_client.call_llm", lambda **_k: object(), raising=False
    )

    assert tts_tool._translate_for_speech("hello", "ja") == "hello"


def test_bos_metin_modele_GITMIYOR(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(**_k: object) -> object:  # pragma: no cover
        raise AssertionError("bos metin icin model cagrilmamali")

    monkeypatch.setattr("agent.auxiliary_client.call_llm", _boom, raising=False)

    assert tts_tool._translate_for_speech("   ", "ja") == "   "


# ---------------------------------------------------------------------------
# Motor tarafı
# ---------------------------------------------------------------------------


def test_desteklenen_diller_chatterbox_ile_AYNI() -> None:
    """İki liste ayrışırsa kullanıcı burada kabul edilen bir dili seçer ve
    motor onu reddeder -- ya da tersi."""
    from pathlib import Path

    plugin = Path("plugins/tts/fool-chatterbox/__init__.py").read_text(encoding="utf-8")

    for code in tts_tool.SPEECH_LANGUAGE_NAMES:
        assert f'"{code}"' in plugin, f"{code} chatterbox listesinde yok"


# ---------------------------------------------------------------------------
# Konuşma dili MODELE söylenmiyor
# ---------------------------------------------------------------------------


def test_konusma_dili_ISTEME_girmiyor(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ölçülen hata: kullanıcı İngilizce yazdı, ses dili Japonca'ydı ve model
    cevabı JAPONCA YAZDI --

        [warm] こんにちは。元気ですよ！あなたはいかがですか？

    Kullanıcının bildirdiği: "cevap japonca geldi, ne dediğini anlamıyorum."
    Ekranda okunamayan bir cevap, ayarın tam tersi.

    Küçük bir model için istemde geçen dil adı, etrafındaki olumsuzlamadan
    ("do NOT write Japanese") daha güçlü. Yasak yazmak yetmiyor: kelimenin
    orada OLMAMASI gerekiyor. Modelin bu bilgiye ihtiyacı da yok -- çeviri
    seslendirme katmanında yapılıyor.
    """
    from fool import language_mode

    monkeypatch.setattr(language_mode, "current", lambda: ("en", "ja"))

    block = language_mode.prompt_block()

    assert "Japanese" not in block
    assert "Speech language" not in block
    # Cevap dili kuralı YERİNDE kalmalı -- kaldırılan yalnızca konuşma dili.
    assert "English" in block


def test_yalnizca_konusma_dili_ayarliyken_DIL_ADI_gecmiyor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bu senaryo önce BOŞ blok üretiyordu; artık üretmiyor -- ve sebebi
    ölçüldü: kural yokken model sohbet geçmişinin dilini sürdürdü ve kullanıcı
    okuyamadığı bir cevap aldı (bkz. ``test_match_me_momentumu_KIRAN_bir_kural
    _yaziyor``).

    Değişmeyen kural şu: blok konuşma dilinin ADINI asla taşımaz."""
    from fool import language_mode

    monkeypatch.setattr(language_mode, "current", lambda: ("", "ja"))

    block = language_mode.prompt_block()

    assert "Japanese" not in block
    assert "Speech language" not in block


# ---------------------------------------------------------------------------
# Ön-yükleme: çeviri sentezin ARKASINA saklanıyor
# ---------------------------------------------------------------------------


def test_onbellek_ikinci_cagriyi_MODELE_gondermiyor(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ön-yüklemenin işe yaraması onbelleğe bağlı: onbellek olmasaydı aynı
    çeviri ikinci kez istenir ve önden yapılan iş boşa giderdi."""
    calls = []

    def _fake(**kwargs: object) -> object:
        calls.append(kwargs)
        return object()

    monkeypatch.setattr("agent.auxiliary_client.call_llm", _fake, raising=False)
    monkeypatch.setattr(tts_tool, "_extract_auxiliary_message_content", lambda _r: "こんにちは")
    tts_tool._TRANSLATION_CACHE.clear()

    first = tts_tool._translate_for_speech("hello", "ja")
    second = tts_tool._translate_for_speech("hello", "ja")

    assert first == second == "こんにちは"
    assert len(calls) == 1, "ikinci cagri onbellekten gelmeliydi"


def test_on_yukleme_onbellegi_DOLDURUYOR(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("agent.auxiliary_client.call_llm", lambda **_k: object(), raising=False)
    monkeypatch.setattr(tts_tool, "_extract_auxiliary_message_content", lambda _r: "やあ")
    tts_tool._TRANSLATION_CACHE.clear()

    tts_tool.prefetch_speech_translation("hey", {"speech_language": "ja"})

    assert tts_tool._translation_cached(("hey", "ja")) == "やあ"


def test_on_yukleme_ayar_yokken_HICBIR_SEY_yapmiyor(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(**_k: object) -> object:  # pragma: no cover
        raise AssertionError("ayar yokken model cagrilmamali")

    monkeypatch.setattr("agent.auxiliary_client.call_llm", _boom, raising=False)

    tts_tool.prefetch_speech_translation("hey", {})


def test_on_yukleme_ASLA_yukselmiyor(monkeypatch: pytest.MonkeyPatch) -> None:
    """Bu bir hızlandırma; çökerse gerçek çağrı normal yolundan gitmeli."""

    def _explode(*_a: object, **_k: object) -> str:
        raise RuntimeError("patladi")

    monkeypatch.setattr(tts_tool, "_translate_for_speech", _explode)

    tts_tool.prefetch_speech_translation("hey", {"speech_language": "ja"})


def test_onbellek_SINIRLI(monkeypatch: pytest.MonkeyPatch) -> None:
    """Uzun bir oturumda her cümle burada birikirdi."""
    tts_tool._TRANSLATION_CACHE.clear()

    for i in range(tts_tool.TRANSLATION_CACHE_MAX + 20):
        tts_tool._translation_store((f"c{i}", "ja"), f"x{i}")

    assert len(tts_tool._TRANSLATION_CACHE) == tts_tool.TRANSLATION_CACHE_MAX
    # En ESKI dusmus olmali.
    assert tts_tool._translation_cached(("c0", "ja")) is None


def test_akis_katmani_ON_YUKLEMEYI_cagiriyor() -> None:
    """Bağlantı koparsa çeviri yine sıralı olur ve kimse fark etmez."""
    from pathlib import Path

    server = Path("fool_cli/web_server.py").read_text(encoding="utf-8")

    assert "prefetch_speech_translation" in server
    assert "_sentences_translated" in server
    # İlk cümle geciktirilmemeli: ayrı bir iş parçacığı cümleleri çeker.
    assert 'name="tts-sentences"' in server


def test_araya_girince_BESLEYICI_de_duruyor() -> None:
    """Tüketici gittiğinde üretici de durmalı.

    İlk yazımda böyle bir bayrak yoktu ve ölçülen iki sonucu vardı:

    1. Havuz kapandıktan sonra besleyici bir sonraki cümlede
       ``pool.submit`` çağırıyor ve ``RuntimeError: cannot schedule new
       futures after shutdown`` atıyordu. Kimse yakalamıyor -- yani HER
       araya girmede günlüğe bir iş parçacığı geri izlemesi düşüyordu.
    2. ``_sentences()`` sonuna kadar tüketiliyordu: kullanıcı konuşmayı
       kesmiş olsa bile akış pompalanmaya devam ediyordu.
    """
    from pathlib import Path

    server = Path("fool_cli/web_server.py").read_text(encoding="utf-8")
    block = server[
        server.index("def _sentences_translated()") : server.index(
            "for sentence in _sentences_translated()"
        )
    ]

    assert "done = threading.Event()" in block
    assert "if done.is_set():" in block
    assert "except RuntimeError:" in block

    # SIRA: önce besleyiciye dur denir, sonra havuz kapatılır. Tersi tam da
    # yukarıdaki yarışı açardı.
    assert block.index("done.set()") < block.index("pool.shutdown(wait=False)")


# ---------------------------------------------------------------------------
# Gereksiz çeviri YAPILMIYOR
# ---------------------------------------------------------------------------


def test_ingilizce_metin_ingilizce_sese_CEVRILMIYOR(monkeypatch: pytest.MonkeyPatch) -> None:
    """İstenen: "seslendirme ingilizce olduğunda ... çeviri katmanları
    çalışmamalı ki cevap direkt olarak sesli okunup hızlıca gelsin."

    Önceki hâli koşulsuz çeviriyordu: İngilizce'yi İngilizce'ye "çevirmek" için
    bir LLM turu dönüyor ve kullanıcı 2,4-9,7 sn bekliyordu. Tamamı boşa.
    """

    def _boom(*_a: object, **_k: object) -> str:  # pragma: no cover
        raise AssertionError("ayni yazi sisteminde ceviri cagrilmamali")

    monkeypatch.setattr(tts_tool, "_translate_for_speech", _boom)

    text, cfg = tts_tool._apply_speech_language(
        "Hey, I am right here.", {"speech_language": "en", "provider": "chatterbox"}
    )

    assert text == "Hey, I am right here."
    # Motor dili yine ayarlaniyor -- atlanan yalnizca ceviri.
    assert cfg["chatterbox"]["language"] == "en"


def test_japonca_metin_japonca_sese_CEVRILMIYOR(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(*_a: object, **_k: object) -> str:  # pragma: no cover
        raise AssertionError("zaten japonca, ceviri cagrilmamali")

    monkeypatch.setattr(tts_tool, "_translate_for_speech", _boom)

    text, _cfg = tts_tool._apply_speech_language(
        "こんにちは。", {"speech_language": "ja"}
    )

    assert text == "こんにちは。"


def test_ingilizce_metin_japonca_sese_CEVRILIYOR(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tts_tool, "_translate_for_speech", lambda t, target: "こんにちは")

    text, _cfg = tts_tool._apply_speech_language("hello", {"speech_language": "ja"})

    assert text == "こんにちは"


def test_yazi_sistemi_sinamasi() -> None:
    # Latin hedef: Latin disi varsa ceviri gerekli.
    assert tts_tool._already_in_language("Hello there", "en") is True
    assert tts_tool._already_in_language("Merhaba dünya", "tr") is True
    assert tts_tool._already_in_language("こんにちは", "en") is False

    # Latin disi hedef: o yaziyi iceriyorsa zaten o dilde.
    assert tts_tool._already_in_language("こんにちは", "ja") is True
    assert tts_tool._already_in_language("hello", "ja") is False
    assert tts_tool._already_in_language("Привет", "ru") is True

    # Cevrilecek bir sey yok.
    assert tts_tool._already_in_language("   ", "ja") is True
    assert tts_tool._already_in_language("123 — 456", "ja") is True


def test_on_yukleme_de_gereksiz_ceviriyi_ATLIYOR(monkeypatch: pytest.MonkeyPatch) -> None:
    """Arka planda bile olsa boş bir LLM turu, modeli sohbetin önünden alırdı."""

    def _boom(*_a: object, **_k: object) -> str:  # pragma: no cover
        raise AssertionError("on-yukleme gereksiz ceviri yapmamali")

    monkeypatch.setattr(tts_tool, "_translate_for_speech", _boom)

    tts_tool.prefetch_speech_translation("Hello there", {"speech_language": "en"})


# ---------------------------------------------------------------------------
# "Match me" GERÇEKTEN bir kural
# ---------------------------------------------------------------------------


def test_match_me_momentumu_KIRAN_bir_kural_yaziyor(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ölçülen hâl: kullanıcı İngilizce yazdı, geçmiş Japonca'ydı, model Japonca
    devam etti. Kullanıcının bildirdiği: "yazı dili match me olmadı, japonca
    devam etti."

    Kural yokken model geçmişin dilini sürdürüyor; "kullanıcıya uy" bir
    varsayılan değil, söylenmesi gereken bir talimat.
    """
    from fool import language_mode

    monkeypatch.setattr(language_mode, "current", lambda: ("", "ja"))

    block = language_mode.prompt_block()

    assert "MOST RECENT" in block
    assert "earlier turns" in block
    # Ses dili yine SOYLENMIYOR.
    assert "Japanese" not in block


def test_hicbir_ayar_yokken_istem_hala_BOS(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sıradan bir ajanın istemi sebepsiz büyümemeli."""
    from fool import language_mode

    monkeypatch.setattr(language_mode, "current", lambda: ("", ""))

    assert language_mode.prompt_block() == ""
