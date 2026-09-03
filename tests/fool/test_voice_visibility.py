"""Panelde hangi motorun görüneceği: kural YAZILI ve sınanıyor.

Ölçülen sorun
-------------
``VoiceEntry.hidden`` elle konan bir boolean'dı ve alanın belgesi tek bir
ölçüt söylüyordu: yavaş olan gizlenir. Gerçek kural o değildi.

Ölçülen süreler (sıcak, cümle başına)::

    piper       120 ms      görünür
    kokoro      200 ms      görünür
    styletts2   556 ms      görünür
    chatterbox 1894 ms      görünür      <- eşiğin ALTINDA
    kyutai     2517 ms      gizli
    qwen3-tts  9423 ms      gizli

Yalnızca hıza bakan biri chatterbox ile kyutai arasındaki 0,6 saniyeyi görüp
"tutarsız" der ve chatterbox'ı da gizlerdi. Bedeli somut: chatterbox
kullanıcının klonladığı sesi (Ultron) taşıyan motor ve tek klonlama yolu --
gizlemek o sesi seçiciden sessizce silmek olurdu.

Ölçümler neden BURAYA yazılı
----------------------------
İlk yazımda süreler ``voice_bench.load_results()`` ile çalışma anında
okunuyordu. Sınav yeşil yanıyordu ama HİÇBİR ŞEY sınamıyordu: pytest altında o
kayıt boş dönüyor ve her satır "ölçüm kaydı yok" diye atlanıyordu. Yani tam da
bu dosyada eleştirilen şeyin kendisiydi -- yeşil yanan, korumayan bir muhafız.

Sayılar artık sabit: kural onlara karşı sınanıyor. Yeniden ölçüm yapılırsa
tablo BİLEREK güncellenir; aşağıdaki tutarlılık sınavı, makinede bir kayıt
varsa tablonun ondan sapmadığını da kontrol ediyor.
"""

from __future__ import annotations

import pytest

from fool import voice_bench, voice_models

#: Cümle başına ölçülen süreler (sıcak). Kaynak: ``fool/voice_bench.py``
#: sonuçları, kullanıcının makinesinde (RTX 4070 Ti SUPER).
MEASURED_MS: dict[str, int] = {
    "chatterbox": 1894,
    "kokoro": 200,
    "kyutai": 2517,
    "piper": 120,
    "qwen3-tts": 9423,
    "styletts2": 556,
}


def _tts_entries() -> list:
    return [e for e in voice_models.CATALOG if e.kind == "tts"]


def _clone_capable(entry) -> bool:
    return (entry.provider_id or entry.id) in voice_models.CLONE_CAPABLE


# ---------------------------------------------------------------------------
# Kural
# ---------------------------------------------------------------------------

def test_esik_olculen_degerlerin_ARASINDA() -> None:
    """Eşik iki komşu ölçümün arasına düşmeli; ucuna dayanmış bir eşik
    ölçümdeki küçük bir dalgalanmayla motorları yerinden oynatır."""
    assert MEASURED_MS["styletts2"] < voice_models.SLOW_ENGINE_MS < MEASURED_MS["kyutai"]


@pytest.mark.parametrize("entry_id", sorted(MEASURED_MS))
def test_gorunur_motor_ya_HIZLI_ya_KLONLANABILIR(entry_id: str) -> None:
    entry = voice_models.entry(entry_id)

    assert entry is not None, f"{entry_id} katalogda yok -- tablo bayatlamis"

    if entry.hidden:
        return

    measured = MEASURED_MS[entry_id]

    assert measured <= voice_models.SLOW_ENGINE_MS or _clone_capable(entry), (
        f"{entry_id} panelde gorunuyor ama cumle basina {measured} ms "
        f"(esik {voice_models.SLOW_ENGINE_MS}) ve klonlama da yapamiyor."
    )


@pytest.mark.parametrize("entry_id", sorted(MEASURED_MS))
def test_esigin_USTUNDEKI_klonsuz_motor_GIZLI(entry_id: str) -> None:
    """Kuralın diğer yönü: yavaş ve klonsuzsa görünmemeli."""
    entry = voice_models.entry(entry_id)

    assert entry is not None

    if MEASURED_MS[entry_id] <= voice_models.SLOW_ENGINE_MS or _clone_capable(entry):
        return

    assert entry.hidden, (
        f"{entry_id} cumle basina {MEASURED_MS[entry_id]} ms ve klonlayamiyor -- "
        "panelde gorunmemeli."
    )


# ---------------------------------------------------------------------------
# Somut sonuç
# ---------------------------------------------------------------------------

def test_CHATTERBOX_gorunur_kaliyor() -> None:
    """Kullanıcının klonu burada yaşıyor. Hız gerekçesiyle gizlenirse Ultron
    seçiciden kaybolur."""
    entry = voice_models.entry("chatterbox")

    assert entry is not None
    assert entry.hidden is False
    assert _clone_capable(entry)
    # Esigin ALTINDA oldugu da yazili kalsin: "klon istisnasi" sanilip
    # gereginden genis bir kapi acilmasin.
    assert MEASURED_MS["chatterbox"] < voice_models.SLOW_ENGINE_MS


def test_gizlenen_motor_katalogdan_SILINMIYOR() -> None:
    """Kurulu bir motoru katalogdan çıkarmak diskteki gigabaytları görünmez
    yapardı; gizlemek geri alınabilir, silmek değil."""
    ids = {e.id for e in voice_models.CATALOG}

    for hidden_id in ("kyutai", "f5-tts", "qwen3-tts"):
        assert hidden_id in ids


def test_secili_gizli_motor_YINE_gosteriliyor() -> None:
    """Aksi halde kullanıcı ayarlarda hiçbir şey seçili görmez ve sesin
    nereden geldiğini anlayamaz."""
    import inspect

    assert "active.get(" in inspect.getsource(voice_models.visible_catalog)


def test_her_TTS_motoru_tabloda() -> None:
    """Yeni bir motor eklenip ölçülmeden bırakılırsa kural onu hiç görmez."""
    missing = {e.id for e in _tts_entries()} - set(MEASURED_MS) - {"f5-tts"}

    assert not missing, f"Olcumu olmayan motor(lar): {sorted(missing)}"


# ---------------------------------------------------------------------------
# Tablo bayatladı mı
# ---------------------------------------------------------------------------

def test_tablo_makinedeki_kayitla_TUTARLI() -> None:
    """Makinede bir ölçüm kaydı varsa tablo ondan sapmamalı.

    Bu sınav ATLANABILIR: kayıt makineye özel ve CI'da yok. Kuralın kendisi
    yukarıda sabit sayılarla sınanıyor -- burası yalnızca tablonun sessizce
    bayatlamasını yakalamak için.
    """
    results = voice_bench.load_results() or {}

    if not results:
        pytest.skip("bu makinede olcum kaydi yok")

    for entry_id, expected in MEASURED_MS.items():
        row = results.get(entry_id)

        if not isinstance(row, dict) or not isinstance(row.get("elapsed_ms"), (int, float)):
            continue

        actual = int(row["elapsed_ms"])

        # Genis bant: amac dalgalanmayi degil, TABLONUN yanlis olmasini
        # yakalamak (orn. motor degisti ve sure iki katina cikti).
        assert abs(actual - expected) <= max(200, expected * 0.5), (
            f"{entry_id}: tabloda {expected} ms, makinede {actual} ms."
        )


# ---------------------------------------------------------------------------
# Boşta bırakma süresi
# ---------------------------------------------------------------------------

def test_secili_motor_BES_DAKIKA_yasiyor() -> None:
    """Kullanıcının açık isteği: "bir kere kullanıldığında 5 dakika kadar
    aktif kalsın, her kullanıldığında tekrar 5 dk beklesin."

    Sayaç her kullanımda sıfırlanıyor, yani sürekli konuşulan bir oturumda
    motor hiç boşalmıyor; beş dakika SESSİZLİKTEN sonra bırakılıyor.
    """
    from fool import engine_host

    assert engine_host.SELECTED_IDLE_UNLOAD_SECONDS == 300.0


def test_iki_sabit_AYRI_duruyor() -> None:
    """Bugün ikisi de 300 sn ve bu bilinçli -- ama ayrı kalmaları da bilinçli.

    Biri genel boşta politikası, diğeri kullanıcının açık isteği. Tek sabite
    indirmek, genel politikayı ayarlayan birinin kullanıcının istediği
    davranışı sessizce değiştirmesi demek olurdu.
    """
    from fool import engine_host

    assert hasattr(engine_host, "IDLE_UNLOAD_SECONDS")
    assert hasattr(engine_host, "SELECTED_IDLE_UNLOAD_SECONDS")
