"""Tests for config.get() null-coalescing in tool configuration.

YAML ``null`` values (or ``~``) for a present key make ``dict.get(key, default)``
return ``None`` instead of the default — calling ``.lower()`` on that raises
``AttributeError``.  These tests verify the ``or`` coalescing guards.
"""

from unittest.mock import patch


# ── TTS tool ──────────────────────────────────────────────────────────────

class TestTTSProviderNullGuard:
    """tools/tts_tool.py — _get_provider()

    FOOL-SEAM: local-only-tts

    Upstream'in secim-yokken varsayilani ``edge``di ve bu sinif onu
    savunuyordu. Edge TTS Microsoft'un cevrimici "Read Aloud" servisi: ajanin
    soyledigi HER cumlenin metni websocket uzerinden Microsoft'a gidiyor.
    Yerel-once bir uruntte bu, bir hata yolu degil VARSAYILAN yol oldugu icin
    daha da kabul edilemez.

    Bu sinifin ASIL korudugu iki sey degismedi ve hala dogrulaniyor:

      1. ``provider: null`` cokmemeli (AttributeError yok).
      2. Bir sohbet saglayicisi anahtari, kullaniciyi sessizce PARALI bir
         seslendirmeye gecirmemeli.

    Degisen tek sey: secim yokken varsayilan artik KURULU BIR YEREL motor;
    hicbiri yoksa acik tercih olmadan buluta cikilmiyor.
    """

    def test_explicit_null_provider_does_not_crash(self):
        """YAML ``tts: {provider: null}`` bir istisna uretmemeli."""
        from tools.tts_tool import _get_provider

        assert isinstance(_get_provider({"provider": None}), str)

    def test_null_and_missing_resolve_identically(self, monkeypatch):
        """``provider: null`` ile hic anahtar olmamasi ayni sey."""
        from tools import tts_tool

        monkeypatch.setattr(tts_tool, "_installed_local_tts", lambda: {"kokoro"})

        assert tts_tool._get_provider({"provider": None}) == tts_tool._get_provider({})

    def test_missing_provider_prefers_installed_local_engine(self, monkeypatch):
        """Bir sohbet anahtari kullaniciyi parali TTS'e gecirmemeli.

        Upstream bunu "edge'de kal" diye dogruluyordu; The Fool bir adim ileri
        gidiyor ve KURULU YEREL motoru seciyor -- ne parali ne de bulut.
        """
        from tools import tts_tool

        monkeypatch.setattr(tts_tool, "_installed_local_tts", lambda: {"kokoro", "chatterbox"})

        provider = tts_tool._get_provider({})

        assert provider == "kokoro"
        assert provider not in {"openai", "elevenlabs", "deepinfra", "gemini"}

    def test_no_local_engine_does_not_silently_reach_the_cloud(self, monkeypatch):
        """Yerel motor yoksa sessizce Edge'e dusmuyor; acik tercih sart."""
        from tools import tts_tool

        monkeypatch.setattr(tts_tool, "_installed_local_tts", lambda: set())

        assert tts_tool._get_provider({}) == "none"
        assert tts_tool._get_provider({"allow_cloud_fallback": True}) == tts_tool.DEFAULT_PROVIDER

    def test_explicit_provider_wins_over_active(self):
        """An explicit tts.provider always overrides the active-provider fallback."""
        from tools.tts_tool import _get_provider

        assert _get_provider({"provider": "edge"}) == "edge"



# ── Web tools ─────────────────────────────────────────────────────────────

class TestWebBackendNullGuard:
    """tools/web_tools.py — _get_backend()"""

    @patch("tools.web_tools._load_web_config", return_value={"backend": None})
    def test_explicit_null_backend_does_not_crash(self, _cfg):
        """YAML ``web: {backend: null}`` should not raise AttributeError."""
        from tools.web_tools import _get_backend

        # Should not raise — the exact return depends on env key fallback
        result = _get_backend()
        assert isinstance(result, str)

    @patch("tools.web_tools._load_web_config", return_value={})
    def test_missing_backend_does_not_crash(self, _cfg):
        from tools.web_tools import _get_backend

        result = _get_backend()
        assert isinstance(result, str)


# ── MCP tool ──────────────────────────────────────────────────────────────

class TestMCPAuthNullGuard:
    """tools/mcp_tool.py — MCPServerTask.__init__() auth config line"""

    def test_explicit_null_auth_does_not_crash(self):
        """YAML ``auth: null`` in MCP server config should not raise."""
        # Test the expression directly — MCPServerTask.__init__ has many deps
        config = {"auth": None, "timeout": 30}
        auth_type = (config.get("auth") or "").lower().strip()
        assert auth_type == ""


    def test_valid_auth_passed_through(self):
        config = {"auth": "OAUTH", "timeout": 30}
        auth_type = (config.get("auth") or "").lower().strip()
        assert auth_type == "oauth"


# ── Trajectory compressor ─────────────────────────────────────────────────

class TestTrajectoryCompressorNullGuard:
    """trajectory_compressor.py — _detect_provider() and config loading"""

    def test_null_base_url_does_not_crash(self):
        """base_url=None should not crash _detect_provider()."""
        from trajectory_compressor import CompressionConfig, TrajectoryCompressor

        config = CompressionConfig()
        config.base_url = None

        compressor = TrajectoryCompressor.__new__(TrajectoryCompressor)
        compressor.config = config

        # Should not raise AttributeError; returns empty string (no match)
        result = compressor._detect_provider()
        assert result == ""

    def test_config_loading_null_base_url_keeps_default(self):
        """YAML ``summarization: {base_url: null}`` should keep default."""
        from trajectory_compressor import CompressionConfig
        from fool_constants import OPENROUTER_BASE_URL

        config = CompressionConfig()
        data = {"summarization": {"base_url": None}}

        config.base_url = data["summarization"].get("base_url") or config.base_url
        assert config.base_url == OPENROUTER_BASE_URL
