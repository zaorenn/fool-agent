"""Kendi cevabını seslendiren yüzey, ajana SESLENDİRME aracı vermemeli.

Ölçülen hata
------------
Kullanıcının bildirdiği: "bazen aynı cümleleri 2 kere speak aloud yapıyor."

``COMPANION_TOOLSETS`` başlığındaki not bu hatayı zaten anlatıyordu ve dersi
iki komşuya (companion, friend) uygulamıştı. ``desktop`` ATLANMIŞTI: kapsam
``scope_toolsets``ten ``None`` dönüyor, platformun tam bileşiğine düşüyor ve
bileşikte ``tts`` var. Ölçüldü -- masaüstü oturumunun son araç listesinde
``text_to_speech`` duruyordu.

Bu depoda tekrar eden kalıp: bir kolda öğrenilen ders kardeşine taşınmıyor.
Bu yüzden kural artık yorum değil VERİ (``SELF_VOICED_SCOPES``) ve TEK bir
boğaz noktasında uygulanıyor.
"""

from fool.session_scope import (
    SELF_VOICED_DROP,
    SELF_VOICED_KEEP,
    SELF_VOICED_SCOPES,
    strip_self_voiced,
)


class TestKural:
    def test_masaustu_kapsami_listede(self):
        # Atlanan kapsam TAM OLARAK buydu.
        assert "desktop" in SELF_VOICED_SCOPES

    def test_butun_masaustu_yuzeyleri_listede(self):
        # Hepsi aynı hattan seslendiriyor; biri unutulursa hata geri gelir.
        for scope in ("chat", "companion", "desktop", "friend", "hud", "notch"):
            assert scope in SELF_VOICED_SCOPES, scope

    def test_sentez_dusuyor_dil_ayari_kaliyor(self):
        # Takımı TOPTAN düşürmek ``set_language_mode``u da götürürdü -- "ses
        # dilini japonca yap" isteğini gerçekten uygulayan araç o.
        result = strip_self_voiced("desktop", ["file", "tts", "web"])

        assert SELF_VOICED_DROP not in result
        assert SELF_VOICED_KEEP in result
        assert "file" in result and "web" in result

    def test_seslendirmeyen_yuzey_DOKUNULMADAN_geciyor(self):
        # WhatsApp/Telegram'da istemci tarafı ses YOK: orada "konuşmak" = ses
        # dosyası üretmek ve ``text_to_speech`` tek yol.
        original = ["file", "tts", "web"]

        assert strip_self_voiced("telegram", original) == original
        assert strip_self_voiced("tui", original) == original

    def test_None_aynen_geciyor(self):
        # ``None`` = "kapsama özel kısıtlama yok". Burada liste uydurmak
        # çözümlemenin geri kalanını atlamak olurdu.
        assert strip_self_voiced("desktop", None) is None

    def test_tts_zaten_yoksa_KEEP_eklenmiyor(self):
        # Companion/friend beyaz listesinde ``tts`` hiç yok; oraya sessizce
        # yeni bir takım sokmak kapsamı genişletmek olurdu.
        assert strip_self_voiced("companion", ["clarify", "web"]) == ["clarify", "web"]

    def test_kapsam_metni_olmayan_deger_cokmuyor(self):
        assert strip_self_voiced(None, ["tts"]) == ["tts"]
        assert strip_self_voiced(123, ["tts"]) == ["tts"]

    def test_bosluk_ve_buyuk_harf(self):
        assert SELF_VOICED_DROP not in strip_self_voiced("  DESKTOP  ", ["tts"])


class TestCanliKapsam:
    """Ağ geçidinin GERÇEK çözümlemesi -- kuralın bağlandığı yer.

    Takım listesi SABİTLENİYOR (``FOOL_TUI_TOOLSETS``). İlk yazımda ortamın
    kendi çözümlemesine bırakmıştım ve test pytest altında düştü: orada
    "kodlama duruşu" yolu devreye giriyor, ``tts`` zaten hiç gelmiyor ve test
    kuralı değil ortamı ölçüyordu. Pin, boğaz noktasının gerçekten
    uygulandığını ortamdan bağımsız gösteriyor.
    """

    @staticmethod
    def _pin(monkeypatch):
        monkeypatch.setenv("FOOL_TUI_TOOLSETS", "tts,web")

        from tui_gateway.server import _load_enabled_toolsets

        return _load_enabled_toolsets

    def test_masaustu_artik_sentez_ALMIYOR(self, monkeypatch):
        load = self._pin(monkeypatch)

        assert load("desktop") == ["speech_settings", "web"]

    def test_masaustu_dil_ayarini_HALA_aliyor(self, monkeypatch):
        # Düzeltilmiş bir hatayı sessizce geri kırmamanın muhafızı: "ses
        # dilini japonca yap" isteğini uygulayan araç kalmalı.
        load = self._pin(monkeypatch)

        from model_tools import get_tool_definitions

        names = {
            (d.get("name") or (d.get("function") or {}).get("name", ""))
            for d in get_tool_definitions(
                enabled_toolsets=load("desktop"),
                quiet_mode=True,
                skip_tool_search_assembly=True,
            )
        }

        assert "set_language_mode" in names
        assert "text_to_speech" not in names

    def test_tui_ETKILENMEDI(self, monkeypatch):
        # Kural yalnızca seslendiren yüzeylere; TUI'de istemci tarafı ses yok.
        load = self._pin(monkeypatch)

        assert load("tui") == ["tts", "web"]
