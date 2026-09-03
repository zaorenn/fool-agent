"""Konuşma dili ayarlı değilken yabancı dil seslendirilirse uyarı çıkmalı.

Ölçülen bozulma: ``tts.speech_language`` ayarlanmazsa Chatterbox tek dilli
modeli yüklüyor ve Türkçeyi İngilizce fonetiğiyle okuyor (``Merhaba`` ->
``Mehabal``). Ses çıkıyor, hata yok; kullanıcı yalnızca bozuk telaffuz duyuyor.

Kullanıcının kararı: ilk kurulumda SORMA, ama uyar. Bu yüzden uyarı kurulum
akışında değil, sorun gerçekten ortaya çıktığı anda ve tam çözüldüğü yerde
(ses paneli) beliriyor.
"""

from __future__ import annotations

import json

import pytest

from fool import speech_language_hint as hint


# ---------------------------------------------------------------------------
# Isaret: TAHMIN degil, yuksek kesinlikli gozlem
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Merhaba, nasılsın?", "turkish"),
        ("Bugün hava çok güzel değil mi", "turkish"),
        ("Привет", "cyrillic"),
        ("こんにちは", "hiragana"),
        ("你好", "cjk"),
        ("Γειά σου", "greek"),
        ("مرحبا", "arabic"),
        ("안녕하세요", "hangul"),
    ],
)
def test_yabanci_dil_ISARETI_yakalaniyor(text: str, expected: str) -> None:
    assert hint.detect_signal(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "Hello, how are you?",
        "The quick brown fox jumps over the lazy dog.",
        "",
        "1234 !@#$ ok",
    ],
)
def test_INGILIZCE_metin_isaret_uretmiyor(text: str) -> None:
    assert hint.detect_signal(text) is None


def test_PAYLASILAN_aksanli_harfler_isaret_SAYILMIYOR() -> None:
    """``ç ö ü`` bilerek dışarıda.

    Almanca, Fransızca ve İsveççe de kullanıyor -- işaret olarak kesinlikleri
    düşük ve yanlış pozitif, İngilizce konuşan kullanıcıya sebepsiz bir uyarı
    göstermek olurdu. Tahmin etmiyoruz; yalnızca kesin olanı söylüyoruz.
    """
    assert hint.detect_signal("Über den Fluß, garçon, smörgås") is None


def test_TURKCEYE_OZEL_harfler_tek_basina_yetiyor() -> None:
    """``ı`` ve ``ğ`` pratikte Türkçeye özel; biri bile yeter."""
    assert hint.detect_signal("sığınak") == "turkish"
    assert hint.detect_signal("ışık") == "turkish"


# ---------------------------------------------------------------------------
# Isaretin yasam dongusu
# ---------------------------------------------------------------------------


@pytest.fixture
def marker(tmp_path, monkeypatch):
    """İşaret dosyasını geçici bir yere al ve konuşma dilini AYARSIZ say."""
    path = tmp_path / "speech-language-hint.json"
    monkeypatch.setattr(hint, "_marker_path", lambda: path)
    monkeypatch.setattr(hint, "_speech_language_set", lambda: False)

    return path


def test_YABANCI_dil_seslendirilince_uyari_beliriyor(marker) -> None:
    assert hint.pending() is None

    hint.note("Merhaba, bugün nasılsın?")

    found = hint.pending()

    assert found is not None
    assert found["signal"] == "turkish"


def test_INGILIZCE_konusma_uyari_URETMIYOR(marker) -> None:
    hint.note("Hello there, this is a test.")

    assert hint.pending() is None
    assert not marker.exists()


def test_KAPATILAN_uyari_geri_GELMIYOR(marker) -> None:
    """En sinsi hâli bu olurdu: kullanıcı kapatır, bir sonraki Türkçe cümlede
    uyarı yeniden belirir ve panel kullanılamaz hâle gelir."""
    hint.note("Merhaba")
    hint.dismiss()

    assert hint.pending() is None

    hint.note("Işık ve gölge")

    assert hint.pending() is None


def test_dil_SECILINCE_uyari_kendiliginden_kayboluyor(tmp_path, monkeypatch) -> None:
    """Çözülmüş bir sorunun ekranda durması, kullanıcıya kapatma işi bırakmak
    olurdu."""
    path = tmp_path / "speech-language-hint.json"
    path.write_text(json.dumps({"signal": "turkish"}), encoding="utf-8")
    monkeypatch.setattr(hint, "_marker_path", lambda: path)

    monkeypatch.setattr(hint, "_speech_language_set", lambda: False)
    assert hint.pending() is not None

    monkeypatch.setattr(hint, "_speech_language_set", lambda: True)
    assert hint.pending() is None


def test_dil_ZATEN_secilmisse_isaret_hic_yazilmiyor(tmp_path, monkeypatch) -> None:
    path = tmp_path / "speech-language-hint.json"
    monkeypatch.setattr(hint, "_marker_path", lambda: path)
    monkeypatch.setattr(hint, "_speech_language_set", lambda: True)

    hint.note("Merhaba")

    assert not path.exists()


def test_BOZUK_isaret_dosyasi_paneli_dusurmuyor(marker) -> None:
    """Katalog bu ipucunu taşıyor; bir uyarı uğruna ses panelini tümden
    kaybettirmek kabul edilemez."""
    marker.write_text("{ bozuk json", encoding="utf-8")

    assert hint.pending() is None


def test_YAZILAMAYAN_isaret_sesi_DUSURMUYOR(monkeypatch) -> None:
    """``note`` konuşma yolunun ortasında duruyor."""
    def _boom():
        raise OSError("disk dolu")

    monkeypatch.setattr(hint, "_marker_path", _boom)
    monkeypatch.setattr(hint, "_speech_language_set", lambda: False)

    hint.note("Merhaba")  # patlamamali


def test_SAF_ASCII_Turkce_ayirt_EDILEMIYOR(marker) -> None:
    """Bilinen sınır, bilerek yazılıyor.

    ``Merhaba`` -- bu sorunun kanonik örneği -- İngilizce'den ayrılamaz;
    ayrılabildiğini iddia eden her yöntem tahmindir ve yanlış tahmin
    kullanıcıyı hiç istemediği bir dile geçirirdi.

    Pratikte gecikme, kayıp değil: ``note`` HER cümlede çalışıyor ve
    ``ı``/``ğ``/``ş`` içermeyen bir Türkçe konuşmanın sürmesi beklenmiyor --
    aşağıdaki ikinci cümle uyarıyı getiriyor.
    """
    hint.note("Merhaba")

    assert hint.pending() is None, "ASCII metinden dil tahmin edilmemeli"

    hint.note("Bugün ışık çok güzel")

    assert hint.pending() is not None


def test_metin_SAKLANMIYOR(marker) -> None:
    """Kullanıcının konuştuğu cümle diske yazılmamalı.

    İşaret dosyası yalnızca "hangi işaret görüldü" bilgisini taşıyor; konuşulan
    metni saklamak, uyarı uğruna kullanıcı içeriğini kalıcılaştırmak olurdu.
    """
    hint.note("Merhaba, bu cümle gizli kalmalı — ışık")

    assert "gizli" not in marker.read_text(encoding="utf-8")
    assert json.loads(marker.read_text(encoding="utf-8")) == {"signal": "turkish"}


# ---------------------------------------------------------------------------
# Mesaj: nerede duzeltilecegini SOYLEMEK zorunda
# ---------------------------------------------------------------------------


def test_mesaj_denetimin_YERINI_soyluyor() -> None:
    """"Voice" seçici ses panelinde DEĞİL, başlık çubuğundaki küre ikonunun
    altında.

    Uyarıyı okuyan kişi ses panelinde duruyor. Yeri söylemeden "bir dil ayarı
    var" demek, onu aramaya göndermek olurdu -- ve arayacağı yerde o ayar yok.
    """
    text = hint.message("turkish")

    assert "Voice" in text
    assert "title bar" in text


def test_mesaj_kullanicinin_DUYDUGU_seyi_ornekliyor() -> None:
    """"Yanlış telaffuz" soyut; ``Merhaba -> Mehabal`` kullanıcının zaten
    duyduğu şey ve uyarıyı tanınır kılıyor."""
    text = hint.message("turkish")

    assert "Merhaba" in text and "Mehabal" in text


def test_mesaj_isaret_TAHMIN_gibi_sunulmuyor() -> None:
    """Latin dışı bir yazı için "Turkish" demek, yapmadığımız bir tahmini
    yapmış gibi görünmek olurdu."""
    assert "Turkish" not in hint.message("cyrillic")


# ---------------------------------------------------------------------------
# Dikisler: uyari GERCEKTEN panele ulasiyor mu?
# ---------------------------------------------------------------------------


def test_konusma_yolu_uyariyi_BESLIYOR() -> None:
    """``_apply_speech_language`` tek huni: akışta cümle cümle gelen çağrılar
    da tek seferlik çağrılar da oradan geçiyor.

    Uyarı oraya bağlanmazsa hiç görünmez -- ve bağlandığı yer ``target``ın BOŞ
    olduğu dal olmak zorunda: dil zaten ayarlıysa uyarının konusu yok.
    """
    from pathlib import Path

    import tools.tts_tool as tts_tool

    source = Path(tts_tool.__file__).read_text(encoding="utf-8")
    branch = source[source.index("def _apply_speech_language") :]
    branch = branch[: branch.index("def ", 10)]

    assert "speech_language_hint.note(text)" in branch
    # AYARSIZ dalda olmali: ``if not target:`` bloğunun içinde.
    head = branch[: branch.index("speech_language_hint.note(text)")]
    assert "if not target:" in head


def test_katalog_uyariyi_TASIYOR() -> None:
    """Panel katalogdan okuyor; alan orada değilse uyarı hiç çizilmez."""
    from pathlib import Path

    from fool import voice_routes

    source = Path(voice_routes.__file__).read_text(encoding="utf-8")

    assert '"speech_language_hint": _speech_language_hint()' in source
    assert '@router.post("/api/fool/voice/speech-language-hint/dismiss")' in source


def test_uyari_katalogu_DUSUREMIYOR(monkeypatch) -> None:
    """Bir uyarı uğruna ses panelini tümden kaybettirmek kabul edilemez --
    ``_slow_engine_hint`` ile aynı gerekçe."""
    from fool import voice_routes

    def _boom() -> None:
        raise RuntimeError("patladi")

    monkeypatch.setattr(hint, "pending", _boom)

    assert voice_routes._speech_language_hint() is None


def test_panel_uyariyi_KAPATILABILIR_ciziyor() -> None:
    """Kapatılamayan bir uyarı, sorunu bilerek görmezden gelen kullanıcıya
    kalıcı bir gürültü olurdu."""
    from pathlib import Path

    ROOT = Path(__file__).resolve().parents[2]
    panel = (ROOT / "apps" / "desktop" / "src" / "fool" / "voice-settings.tsx").read_text(
        encoding="utf-8"
    )

    assert "catalog?.speech_language_hint" in panel
    assert "dismissSpeechHint" in panel
