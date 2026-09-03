"""Nefes: cümleler arasına gerçek sessizlik konuyor.

Akan seslendirme metni cümle cümle sentezliyor ve parçaları arka arkaya
çalıyor. Aradaki tek boşluk motorun bir sonraki parçayı üretme süresi --
yani ölçülen gecikme ne kadar düşerse konuşma o kadar SIKIŞIYOR. Kokoro
0,08 sn'ye indiğinde cümleler neredeyse üst üste biniyor: teknik olarak
hızlı, kulakta nefessiz.

İnsan konuşmasında cümle arası duraklama 300-500 ms, virgülde 150-250 ms
civarı. Burada o boşluk AÇIKÇA üretiliyor -- motorun ne kadar hızlı olduğuna
bağlı bırakılmıyor.

Sessizlik PCM olarak ekleniyor, bekleyerek değil: akış boru hattında
``sleep`` bir sonraki parçanın sentezini de geciktirirdi ve kazanılan
gecikme geri verilirdi.
"""

from __future__ import annotations

import pytest

from fool import prosody


# ---------------------------------------------------------------------------
# Duraklama süresi
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text", ["Tamam.", "Gercekten mi?", "Harika!"])
def test_cumle_sonu_en_uzun_duraklamayi_aliyor(text: str) -> None:
    assert prosody.pause_ms_after(text) == prosody.SENTENCE_PAUSE_MS


@pytest.mark.parametrize("text", ["Bir dakika...", "Sey…", "Yani --"])
def test_asili_biten_cumle_daha_uzun_bekliyor(text: str) -> None:
    """Üç nokta ve tire "devam edeceğim" demek; acele etmek yanlış duyuluyor."""
    assert prosody.pause_ms_after(text) == prosody.TRAILING_PAUSE_MS
    assert prosody.TRAILING_PAUSE_MS > prosody.SENTENCE_PAUSE_MS


@pytest.mark.parametrize("text", ["Once sunu,", "Bekle;", "Sunlar:"])
def test_yan_cumle_kisa_duraklama(text: str) -> None:
    assert prosody.pause_ms_after(text) == prosody.CLAUSE_PAUSE_MS
    assert prosody.CLAUSE_PAUSE_MS < prosody.SENTENCE_PAUSE_MS


def test_paragraf_sonu_en_uzun() -> None:
    assert prosody.pause_ms_after("Bitti.\n\n") == prosody.PARAGRAPH_PAUSE_MS
    assert prosody.PARAGRAPH_PAUSE_MS >= prosody.TRAILING_PAUSE_MS


def test_noktalamasiz_parca_neredeyse_hic_beklemiyor() -> None:
    """Zorla boşaltılan bir parça cümlenin ORTASI; orada durmak kekelemek."""
    assert prosody.pause_ms_after("bir seyler yaparken") == prosody.CONTINUATION_PAUSE_MS
    assert prosody.CONTINUATION_PAUSE_MS < prosody.CLAUSE_PAUSE_MS


def test_sondaki_bosluk_ve_tirnak_kararı_degistirmiyor() -> None:
    """``"Tamam." `` ile ``Tamam.`` aynı şey."""
    for text in ('Tamam. ', '"Tamam."', "Tamam.'", "Tamam.)  "):
        assert prosody.pause_ms_after(text) == prosody.SENTENCE_PAUSE_MS


def test_bos_metin_cokmuyor() -> None:
    for text in ("", "   ", None, 42):
        assert prosody.pause_ms_after(text) == 0


# ---------------------------------------------------------------------------
# Sessizlik üretimi
# ---------------------------------------------------------------------------

def test_sessizlik_dogru_uzunlukta() -> None:
    """24 kHz mono int16'da 100 ms = 2400 örnek = 4800 bayt."""
    data = prosody.silence_pcm(100, sample_rate=24_000)

    assert len(data) == 4800
    assert set(data) == {0}


def test_ornekleme_hizina_gore_olceklendiriliyor() -> None:
    assert len(prosody.silence_pcm(100, sample_rate=48_000)) == 9600


def test_sifir_ve_negatif_sure_bos_donuyor() -> None:
    assert prosody.silence_pcm(0, sample_rate=24_000) == b""
    assert prosody.silence_pcm(-50, sample_rate=24_000) == b""


def test_asiri_uzun_duraklama_kirpiliyor() -> None:
    """Bozuk bir hesap yüzünden saniyelerce sessizlik konuşmayı öldürürdü."""
    data = prosody.silence_pcm(999_999, sample_rate=24_000)

    assert len(data) <= prosody.MAX_PAUSE_MS * 24_000 // 1000 * 2


def test_gecersiz_ornekleme_hizi_bos_donuyor() -> None:
    assert prosody.silence_pcm(100, sample_rate=0) == b""


# ---------------------------------------------------------------------------
# Birleşik yol
# ---------------------------------------------------------------------------

def test_parca_sonrasi_sessizlik_uretiliyor() -> None:
    data = prosody.pause_pcm_after("Tamam.", sample_rate=24_000)
    expected = prosody.SENTENCE_PAUSE_MS * 24_000 // 1000 * 2

    assert len(data) == expected


def test_kapaliyken_hic_sessizlik_eklenmiyor() -> None:
    """Kullanıcı kapatabilmeli: bazı motorlar zaten kendi duraklamasını koyuyor."""
    assert prosody.pause_pcm_after("Tamam.", sample_rate=24_000, enabled=False) == b""


def test_yapilandirmadan_okunuyor() -> None:
    assert prosody.pauses_enabled({}) is True
    assert prosody.pauses_enabled({"tts": {"pauses": False}}) is False
    assert prosody.pauses_enabled({"tts": {"pauses": "off"}}) is False
    assert prosody.pauses_enabled({"tts": {"pauses": "on"}}) is True


def test_bozuk_yapilandirmada_acik_kaliyor() -> None:
    for bad in (None, [], "x", {"tts": 7}):
        assert prosody.pauses_enabled(bad) is True


# ---------------------------------------------------------------------------
# İlk cümle GECİKMESİ ve sınırsız uzun cümle
# ---------------------------------------------------------------------------

def _stream(reply: str, step: int = 7):
    """Token token besle; her parçanın KAÇ karakterde çıktığını döndür."""
    from tools.tts_streaming import SentenceChunker

    chunker = SentenceChunker()
    seen = 0
    out = []
    for index in range(0, len(reply), step):
        delta = reply[index : index + step]
        seen += len(delta)
        for piece in chunker.feed(delta):
            out.append((seen, piece.strip()))
    for piece in chunker.flush():
        out.append((seen, piece.strip()))
    return out


def test_ILK_cumle_hemen_cikiyor() -> None:
    """Ölçüldü: kısa açılışlı bir cevapta ilk parça 204 karakterin 77'sinde
    çıkıyordu, çünkü "Sure." 20 karakterlik alt sınırın altında ve SONRAKİ
    cümleyle birleştiriliyordu. Konuşma, ilk cümle çoktan bitmişken hâlâ
    başlamamış oluyordu.

    Birleştirme kuralı kötü değil ama YALNIZCA ilk parçada pahalı: orada
    beklenen şey sessizlik.
    """
    reply = (
        "Sure. The first thing to know is that the system loads the model once. "
        "After that every sentence is fast, usually under a second."
    )

    pieces = _stream(reply)

    assert pieces, "hic cumle cikmadi"
    at, text = pieces[0]
    assert text == "Sure."
    # Cevabin ONDA BIRINDEN once konusmaya baslamali.
    assert at < len(reply) // 10, f"ilk parca {at}/{len(reply)} karakterde cikti"


def test_cok_kisa_acilis_HALA_birlesiyor() -> None:
    """"Ha!" tek başına bir klip olarak konuşulunca saçma duruyor."""
    pieces = _stream("Ha! That is interesting to hear about.")

    assert len(pieces) == 1
    assert pieces[0][1].startswith("Ha! That is")


def test_SINIRSIZ_uzun_cumle_sessiz_KALMIYOR() -> None:
    """Nokta/soru işareti olmayan uzun bir cümle tampona birikip hiç
    konuşulmuyordu -- kullanıcının bildirdiği "uzun cümlelerde speak aloud
    düzgün çalışmıyor". Sınır aşılınca cümlecik sınırından kesiliyor.
    """
    reply = (
        "Well the way this works is that the model streams tokens and the chunker "
        "watches for a boundary and when it finds one it hands the text to the "
        "engine which turns it into audio and the player queues it so playback "
        "overlaps generation which is the whole point of the design here"
    )

    pieces = _stream(reply)

    assert len(pieces) >= 2, "uzun cumle hic kesilmedi"
    first_at = pieces[0][0]
    assert first_at < len(reply), "ilk parca ancak sonda cikti"


def test_kesme_METNI_kaybetmiyor() -> None:
    """Kesmek bölmek olmalı, yutmak değil."""
    reply = "a" * 100 + ", " + "b" * 100 + ", " + "c" * 100

    pieces = _stream(reply)

    joined = "".join(text for _, text in pieces)
    assert joined.replace(" ", "") == reply.replace(" ", "")


def test_flush_SONRASI_yeni_tur_yine_hizli() -> None:
    """Bayrak tur başına sıfırlanmalı, yoksa ikinci turun ilk cümlesi yine
    gecikirdi."""
    from tools.tts_streaming import SentenceChunker

    chunker = SentenceChunker()
    chunker.feed("Sure. Something longer follows here to pass the limit.")
    chunker.flush()

    assert chunker.feed("Yes. And more text after it that is long enough.")[0].strip() == "Yes."
