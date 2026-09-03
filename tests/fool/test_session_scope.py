"""Sesli arkadaş, sahibinin terminalini almamalı.

Ölçüldü (``tui_gateway.server._load_enabled_toolsets``, FOOL_DESKTOP=1):
masaüstü oturumu 21 takım alıyor ve içinde ``terminal``, ``computer_use``,
``code_execution``, ``delegation``, ``cronjob`` var. Notch'un sesli turu O
OTURUMU paylaşıyor (``$activeSessionId``), yani "hava nasıl?" diyen arkadaş
makinenin tamamına sahip.
"""

from __future__ import annotations

import pytest

from fool import session_scope as ss
from toolsets import resolve_toolset


DANGEROUS = {
    "computer_use",
    "cronjob",
    "delegate_task",
    "execute_code",
    "patch",
    "read_file",
    "search_files",
    "terminal_run",
    "write_file",
}


# ---------------------------------------------------------------------------
# Kapsam araçları
# ---------------------------------------------------------------------------

def test_arkadas_kapsami_makineye_dokunmuyor() -> None:
    tools: set[str] = set()
    for name in ss.COMPANION_TOOLSETS:
        tools |= set(resolve_toolset(name))

    assert tools, "arkadas kapsami hicbir araca cozulmuyor"
    assert not (DANGEROUS & tools)


def test_arkadas_kapsaminda_tarayici_ve_hafiza_yok() -> None:
    """Tarayıcı oturum açılmış hesaplar, hafıza sahibinin geçmiş sohbetleri."""
    tools: set[str] = set()
    for name in ss.COMPANION_TOOLSETS:
        tools |= set(resolve_toolset(name))

    assert not [t for t in tools if t.startswith("browser")]
    assert "memory" not in ss.COMPANION_TOOLSETS
    assert "session_search" not in ss.COMPANION_TOOLSETS


def test_arkadas_kapsami_SOHBET_EDEBILIYOR() -> None:
    """Kısıtlamak sakatlamak değil: soru sorabilmeli, bakabilmeli."""
    assert "clarify" in ss.COMPANION_TOOLSETS
    assert "web" in ss.COMPANION_TOOLSETS


def test_arkadas_kapsaminda_KENDI_SES_ARACI_YOK() -> None:
    """Masaüstü zaten HER cevabı kendi hattından seslendiriyor.

    Ajana ayrıca ``text_to_speech`` verilirse kendi kendine de sentez
    çağırmaya başlıyor -- gerçekte gözlemlendi: tek bir turda ajan üç kez
    "Thought → Text To Speech" döngüsüne girdi, final metin bir öncekiyle
    yinelenerek göründü, ve masaüstünün kendi sentezi aynı motoru paylaştığı
    için "model uyandırılıyor" durumunda takılı kaldı. WhatsApp/Telegram gibi
    istemci tarafı sesi olmayan yüzeylerde bu araç hâlâ doğru -- yalnızca
    buradaki kapsamlarda yok.
    """
    assert "tts" not in ss.COMPANION_TOOLSETS
    assert "tts" not in ss.FRIEND_TOOLSETS


def test_arkadas_kapsami_DOSYA_URETEBILIYOR() -> None:
    """"Bunun PDF'ini çıkar" çalışmalı -- ama okuma yetkisi olmadan."""
    assert "output_file" in ss.COMPANION_TOOLSETS
    assert set(resolve_toolset("output_file")) == {"write_output"}


# ---------------------------------------------------------------------------
# Kapsam çözümlemesi
# ---------------------------------------------------------------------------

def test_arkadas_kapsami_kendi_listesini_veriyor() -> None:
    assert ss.scope_toolsets("companion") == list(ss.COMPANION_TOOLSETS)


@pytest.mark.parametrize("scope", ["cli", "desktop", "tui"])
def test_sahibinin_kapsamlari_kisitlanmiyor(scope: str) -> None:
    """``None`` = "normal çözümlemeye devam et"."""
    assert ss.scope_toolsets(scope) is None


def test_bilinmeyen_kapsam_kisitlanmiyor() -> None:
    """Tanımadığımız bir yüzeyi sessizce kırmak yanlış olurdu."""
    assert ss.scope_toolsets("yarin-eklenecek-yuzey") is None
    assert ss.scope_toolsets(None) is None
    assert ss.scope_toolsets(42) is None


def test_buyuk_harf_ve_bosluk_sorun_degil() -> None:
    assert ss.scope_toolsets("  COMPANION ") == list(ss.COMPANION_TOOLSETS)


# ---------------------------------------------------------------------------
# Yüzey tanıma
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("surface", ["hud", "notch", "companion", "HUD", " hud "])
def test_notch_yuzeyleri_taniniyor(surface: str) -> None:
    """Notch bugün ``surface: 'hud'`` gonderiyor ve sunucuda kimse okumuyor."""
    assert ss.is_companion_surface(surface) is True


@pytest.mark.parametrize("surface", ["chat", "cli", "", None, 42, "desktop"])
def test_diger_yuzeyler_arkadas_sayilmiyor(surface) -> None:
    assert ss.is_companion_surface(surface) is False


# ---------------------------------------------------------------------------
# Gerçek çözümleyici
# ---------------------------------------------------------------------------

def test_gateway_arkadas_kapsamini_uyguluyor() -> None:
    """``_load_enabled_toolsets("companion")`` kısıtlı listeyi vermeli."""
    from tui_gateway.server import _load_enabled_toolsets

    result = _load_enabled_toolsets("companion")

    assert result is not None
    assert set(result) == set(ss.COMPANION_TOOLSETS)


def test_gateway_arkadas_kapsaminda_terminal_VERMIYOR() -> None:
    from tui_gateway.server import _load_enabled_toolsets

    result = set(_load_enabled_toolsets("companion") or [])

    for forbidden in ("terminal", "file", "code_execution", "computer_use", "delegation"):
        assert forbidden not in result


def test_gateway_masaustu_kapsamini_DEGISTIRMIYOR(monkeypatch) -> None:
    """Sahibinin çalıştığı oturum aynen kalmalı."""
    monkeypatch.setenv("FOOL_DESKTOP", "1")
    monkeypatch.delenv("FOOL_DESKTOP_TERMINAL", raising=False)

    from tui_gateway.server import _load_enabled_toolsets

    result = set(_load_enabled_toolsets("desktop") or [])

    assert "terminal" in result
    assert "file" in result


# ---------------------------------------------------------------------------
# Friend penceresi: arkadaş kapsamı + ORTAK HAFIZA
# ---------------------------------------------------------------------------
#
# Uzak bir kullanıcıya sahibinin geçmiş sohbetlerini açmak sızıntı; kendi
# makinesinde kendi penceresinde AÇMAMAK ise arkadaşı hafızasız bırakmak --
# her seferinde kendini yeniden anlatmak zorunda kalıyorsun. İkisi farklı
# sorular ve farklı cevapları var.

def test_friend_kapsami_hafizayi_PAYLASIYOR() -> None:
    assert "memory" in ss.FRIEND_TOOLSETS
    assert "memory" not in ss.COMPANION_TOOLSETS


def test_friend_kapsami_yine_de_makineye_dokunmuyor() -> None:
    tools: set[str] = set()
    for name in ss.FRIEND_TOOLSETS:
        tools |= set(resolve_toolset(name))

    assert tools
    assert not (DANGEROUS & tools)
    assert not [t for t in tools if t.startswith("browser")]


def test_friend_gecmis_sohbetleri_TARAYAMIYOR() -> None:
    """Hatırlamak ile geçmişi taramak farklı şeyler; sohbet için gerekmiyor."""
    assert "session_search" not in ss.FRIEND_TOOLSETS


def test_friend_kapsami_cozumleniyor() -> None:
    assert ss.scope_toolsets("friend") == list(ss.FRIEND_TOOLSETS)


def test_gateway_friend_kapsamini_uyguluyor() -> None:
    from tui_gateway.server import _load_enabled_toolsets

    result = set(_load_enabled_toolsets("friend") or [])

    assert result == set(ss.FRIEND_TOOLSETS)
    for forbidden in ("terminal", "file", "code_execution", "computer_use", "delegation"):
        assert forbidden not in result


def test_uc_kapsam_da_BIRBIRINDEN_farkli() -> None:
    """companion < friend, ve desktop ikisinden de YETKILI.

    Ilk yazimda ``friend < desktop`` diye yazmistim ve YANLISTI: friend'de
    ``output_file`` var (yalnizca yazan, kilitli klasor), desktop'ta onun
    yerine TAM ``file`` var -- yani desktop daha yetkili ama kume olarak
    friend'i kapsamiyor. Kume iliskisi burada yanlis olcut; olcut YETKI.
    """
    from tui_gateway.server import _load_enabled_toolsets

    companion = set(_load_enabled_toolsets("companion") or [])
    friend = set(_load_enabled_toolsets("friend") or [])
    desktop = set(_load_enabled_toolsets("desktop") or [])

    # friend, companion'in her seyini yapabiliyor + hafiza.
    assert companion < friend
    assert friend - companion == {"memory"}

    # desktop makineye dokunuyor, digerleri dokunmuyor.
    machine = {"terminal", "file", "code_execution", "computer_use", "delegation"}
    assert machine <= desktop
    assert not (machine & friend)
    assert not (machine & companion)

    # friend'in dosya uretme yetkisi desktop'ta TAM dosya erisimiyle
    # karsilaniyor -- ayni isin daha genis hali.
    assert "output_file" in friend
    assert "file" in desktop


# ---------------------------------------------------------------------------
# Takım ADI değil, ajanın GERÇEKTEN aldığı araçlar
# ---------------------------------------------------------------------------
#
# Yukarıdaki sınavlar takım adlarını doğruluyor. Asıl soru bir katman aşağıda:
# o adlar hangi ARAÇLARA açılıyor? Bir takım sonradan makineye dokunan bir
# araç kazanabilir ve ad listesi hiç değişmeden arkadaş kipi terminale
# kavuşabilir. Ölçüldü (FOOL_DESKTOP=1, ağ geçidinin kendi çözümlemesi):
#
#     friend      6 takım ->  7 araç   makineye dokunan: YOK
#     companion   5 takım ->  6 araç   makineye dokunan: YOK
#     desktop    21 takım -> 73 araç   terminal, write_file, execute_code,
#                                      computer_use, delegate_task, cronjob
#
# Sınav sayıları DEĞİL, ilişkiyi donduruyor.

#: Yanlış çağrıldığında makineye ya da kullanıcının verisine dokunan araçlar.
_MACHINE_TOOL_MARKERS = (
    "computer",
    "cronjob",
    "delegate",
    "delete",
    "execute_code",
    "terminal",
    "write_file",
)


def _tools_for(scope: str) -> set[str]:
    """Bu kapsamın araç adları -- gerçek çözümleme, taklit yok."""
    from toolsets import resolve_toolset

    names = ss.scope_toolsets(scope)
    assert names is not None, f"{scope} kapsami kisitlanmiyor"

    tools: set[str] = set()
    for toolset in names:
        for tool in resolve_toolset(toolset) or []:
            tools.add(tool if isinstance(tool, str) else getattr(tool, "name", str(tool)))
    return tools


def _machine_tools(tools: set[str]) -> list[str]:
    return sorted(t for t in tools if any(m in t for m in _MACHINE_TOOL_MARKERS))


def test_arkadas_kapsami_MAKINEYE_DOKUNAN_hicbir_arac_ALMIYOR() -> None:
    """Ad listesi değil, araçların kendisi sınanıyor.

    Bir takımın sonradan ``terminal_run`` kazanması, ad listesi hiç
    değişmeden sesli arkadaşa terminal vermek olurdu.
    """
    for scope in (ss.COMPANION, ss.FRIEND):
        leaked = _machine_tools(_tools_for(scope))
        assert not leaked, f"{scope} kapsamina makineye dokunan arac sizdi: {leaked}"


def test_arkadas_kapsami_BOS_da_degil() -> None:
    """Kısıtlamak susturmak değil: konuşacak araçları var."""
    for scope in (ss.COMPANION, ss.FRIEND):
        assert _tools_for(scope), f"{scope} kapsami hic arac almiyor"


def test_JARVIS_kapsami_makineye_GERCEKTEN_dokunuyor() -> None:
    """Jarvis'in var olma sebebi bu.

    ``scope_toolsets('desktop')`` ``None`` döner (kısıtlama yok) -- yani
    kısıt kapsamda değil, tool-calling sınavında. Burada sınanan şey Jarvis
    kipinin GERÇEKTEN iş yapabildiği: aksi hâlde kip sadece bir etiket olurdu.
    """
    import os

    from tui_gateway import server as srv

    os.environ.setdefault("FOOL_DESKTOP", "1")

    assert ss.scope_toolsets("desktop") is None

    names = srv._load_enabled_toolsets("desktop") or []
    assert "terminal" in names
    assert "file" in names
    assert "code_execution" in names


def test_arkadas_ile_JARVIS_arasindaki_fark_MAKINEYE_ERISIM() -> None:
    """İki kip ayrışmazsa ayrı kip olmalarının anlamı kalmıyor.

    KESİN alt küme DEĞİL, ölçüldü: ``output_file`` arkadaşta var, Jarvis'in
    listesinde yok. Kayıp değil -- Jarvis'in ``file`` takımı zaten dosya
    yazıyor, arkadaşın ise SADECE yazan bu araç dışında hiç dosya erişimi
    yok. Sınanacak şey bu asimetri değil, farkın YÖNÜ: Jarvis'in fazladan
    aldığı her şey makineye dokunan takımlar.
    """
    import os

    from fool.agent_authority import EARNED_TOOLSETS
    from tui_gateway import server as srv

    os.environ.setdefault("FOOL_DESKTOP", "1")

    jarvis = set(srv._load_enabled_toolsets("desktop") or [])
    friend = set(ss.FRIEND_TOOLSETS)

    # Jarvis'in fazladan aldiklari KAZANILMASI gerekenleri iceriyor.
    assert EARNED_TOOLSETS & (jarvis - friend), "Jarvis makineye dokunan hicbir sey almiyor"

    # Arkadasin fazladan aldigi ne varsa ZARARSIZ olmali.
    for extra in friend - jarvis:
        assert extra not in EARNED_TOOLSETS, (
            f"arkadas kapsami kazanilmasi gereken bir takim aliyor: {extra}"
        )


# ---------------------------------------------------------------------------
# Chat kipi: sahibinin klavyesi, ama OKUYAN eller
# ---------------------------------------------------------------------------
#
# Masaüstündeki Chat/Cowork anahtarının "Chat" tarafı. ``companion``dan farkı
# kimin konuştuğu: orada uzak bir kullanıcı, burada makinenin sahibi. Sahibi
# dosyasını okutabilmeli ve geçmişini aratabilmeli; ama Chat'te "şunu düzelt"
# demek düzeltilmiş bir dosya getirmemeli -- o Cowork'ün işi.


def test_chat_kapsami_cozumleniyor() -> None:
    assert ss.scope_toolsets("chat") == list(ss.CHAT_TOOLSETS)


def test_chat_kapsami_MAKINEYE_dokunmuyor() -> None:
    tools: set[str] = set()
    for name in ss.CHAT_TOOLSETS:
        tools |= set(resolve_toolset(name))

    for forbidden in ("terminal", "process", "execute_code", "write_file", "patch", "computer_use"):
        assert forbidden not in tools, f"Chat kapsamina yazan arac sizmis: {forbidden}"


def test_chat_kapsami_OKUYABILIYOR() -> None:
    """Read-only, "araçsız" demek değil.

    Sahibi kendi makinesinde: dosyasını okutabilmeli ve geçmişini
    aratabilmeli. Boş bir kümenin de yukarıdaki testten geçeceğini unutma.
    """
    tools: set[str] = set()
    for name in ss.CHAT_TOOLSETS:
        tools |= set(resolve_toolset(name))

    for needed in ("read_file", "search_files", "web_search", "session_search"):
        assert needed in tools, f"Chat kapsaminda okuma araci eksik: {needed}"


def test_chat_ARKADAS_kapsamlarindan_farkli() -> None:
    """Üçü de ayrı sorular.

    ``companion`` uzak ve tanınmayan kullanıcı; ``friend`` sahibinin sesli
    penceresi; ``chat`` sahibinin klavyesi. Aynı sabite çıkarmak, birini
    değiştirip diğerini unutmanın kapısı olurdu.
    """
    def resolved(names):
        out: set[str] = set()
        for name in names:
            out |= set(resolve_toolset(name))
        return out

    chat = resolved(ss.CHAT_TOOLSETS)

    assert chat != resolved(ss.COMPANION_TOOLSETS)
    assert chat != resolved(ss.FRIEND_TOOLSETS)
    # Sahibinin klavyesi geçmişini görebilir; uzak kullanıcı göremez.
    assert "session_search" in chat
    assert "session_search" not in resolved(ss.COMPANION_TOOLSETS)


def test_gateway_chat_kapsamini_UYGULUYOR() -> None:
    """Asıl bağlantı. Oturumun ``source``u ``chat`` ise ağ geçidi bu kümeyi
    veriyor -- yeni bir tesisat değil, var olan ``_session_source`` ->
    ``platform_override`` -> ``scope_toolsets`` zinciri."""
    from tui_gateway.server import _load_enabled_toolsets

    assert _load_enabled_toolsets("chat") == list(ss.CHAT_TOOLSETS)


def test_gateway_chat_kapsaminda_TERMINAL_vermiyor() -> None:
    from tui_gateway.server import _load_enabled_toolsets

    tools: set[str] = set()
    for name in _load_enabled_toolsets("chat") or []:
        tools |= set(resolve_toolset(name))

    assert "terminal" not in tools
    assert "write_file" not in tools
