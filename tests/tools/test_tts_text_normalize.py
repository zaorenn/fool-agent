from gateway.config import Platform, PlatformConfig
from gateway.platforms.base import BasePlatformAdapter
from tools.tts_text_normalize import prepare_spoken_text


class _DummyAdapter(BasePlatformAdapter):
    def __init__(self):
        super().__init__(PlatformConfig(enabled=True, token="test"), Platform.TELEGRAM)

    async def connect(self):
        return True

    async def disconnect(self):
        pass

    async def send(self, chat_id, content, **kwargs):
        raise AssertionError("not used")

    async def get_chat_info(self, chat_id):
        return {"id": chat_id, "type": "dm"}


def test_prepare_spoken_text_expands_celsius_and_weather_units():
    raw = """## Christchurch today\n\n- **Now:** about **14°C**, feels like **14°C**\n- **Wind:** 9 km/h\n- **Rain:** 1.3 mm\n- **Range:** 11\u201317°C\n"""

    spoken = prepare_spoken_text(raw)

    assert "##" not in spoken
    assert "**" not in spoken
    assert "14 degrees Celsius" in spoken
    assert "11 to 17 degrees Celsius" in spoken
    assert "9 kilometres per hour" in spoken
    assert "1.3 millimetres" in spoken
    assert "°C" not in spoken
    assert "km/h" not in spoken


def test_prepare_spoken_text_polish_edge_cases():
    # Heading folds into the next sentence as a lead-in, not a bare label.
    assert prepare_spoken_text("## Weather\nIt will be sunny") == "Weather, It will be sunny."
    # Bare degree unit (no leading number) still expands.
    assert "degrees Celsius" in prepare_spoken_text("measured in °C")
    # Trailing comma is not swallowed into the amount.
    assert "300 US dollars" in prepare_spoken_text("US$300, next")
    # Real numeric rates expand, but and/or, N/A, IDs and dates are left intact.
    assert "5 dollars per month" in prepare_spoken_text("$5/month")
    assert "and/or" in prepare_spoken_text("choose and/or option")
    assert "N/A" in prepare_spoken_text("status N/A here")
    assert "2026/06/02" in prepare_spoken_text("due 2026/06/02 ok")


# ---------------------------------------------------------------------------
# BAĞIRMA — motor harf harf okumasın
# ---------------------------------------------------------------------------


class TestSoftenShoutedCaps:
    """Tamamen büyük harfli cevap HARF HARF okunuyordu.

    Ölçülen hata: model bir kişilik/kip gereği tamamen büyük harfle cevap
    verdiğinde Chatterbox cümleyi sözcük olarak değil harf harf okuyordu --
    "THE LIGHT OF HOPE" -> "ti eyç i, el ay ci ...". Genel bir seslendirme
    davranışı: motorlar büyük harf öbeklerini kısaltma sanıp heceliyor.
    """

    def test_bagirilan_cumle_kucultuluyor(self) -> None:
        from tools.tts_text_normalize import soften_shouted_caps

        assert (
            soften_shouted_caps("THE LIGHT OF HOPE BURNS FOREVER!")
            == "The light of hope burns forever!"
        )

    def test_noktalama_diziyi_bolmuyor(self) -> None:
        from tools.tts_text_normalize import soften_shouted_caps

        assert soften_shouted_caps("ULTRAMAN... PROTECTS THE WORLD!") == (
            "Ultraman... protects the world!"
        )

    def test_her_cumle_kendi_basina_buyuyor(self) -> None:
        from tools.tts_text_normalize import soften_shouted_caps

        assert soften_shouted_caps("WE WILL NOT LOSE! WE WILL NEVER LOSE!") == (
            "We will not lose! We will never lose!"
        )

    def test_tek_harfli_sozcuk_diziyi_bozmuyor(self) -> None:
        from tools.tts_text_normalize import soften_shouted_caps

        # "I" buyuk harf olmasi normal: ne diziyi baslatir ne bozar.
        assert soften_shouted_caps("SUGOI! I AM THE GUARDIAN!") == "Sugoi! I am the guardian!"

    def test_KISALTMALAR_korunuyor(self) -> None:
        """Bunlar gerçekten harf harf okunmalı -- kural onlara dokunmamalı."""
        from tools.tts_text_normalize import soften_shouted_caps

        assert soften_shouted_caps("Use the CPU for that") == "Use the CPU for that"
        assert soften_shouted_caps("The HTTP API is slow") == "The HTTP API is slow"
        assert soften_shouted_caps("Check the JSON payload") == "Check the JSON payload"
        assert soften_shouted_caps("I said NO.") == "I said NO."

    def test_cumle_ortasindaki_vurgu_buyutulmuyor(self) -> None:
        from tools.tts_text_normalize import soften_shouted_caps

        assert soften_shouted_caps("That was AMAZING.") == "That was amazing."

    def test_prepare_spoken_text_uzerinden_de_gecerli(self) -> None:
        """Tek dikiş: her TTS yolu ``prepare_spoken_text``ten geçiyor."""
        from tools.tts_text_normalize import prepare_spoken_text

        spoken = prepare_spoken_text("**THE FUTURE IS NOW! THE PRESENT IS HERE!**")

        assert "THE FUTURE" not in spoken
        assert "The future is now" in spoken

    def test_bos_metin_sorun_cikarmiyor(self) -> None:
        from tools.tts_text_normalize import soften_shouted_caps

        assert soften_shouted_caps("") == ""
        assert soften_shouted_caps("   ") == "   "
