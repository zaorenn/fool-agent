"""Chat kipi OKUR, hiçbir şeyi değiştirmez.

Masaüstündeki Chat/Cowork anahtarının "Chat" tarafı bu kümeye bağlanıyor.
Kullanıcının isteği iki cümleydi ve ikisi de burada tutuluyor:

    "chat kısmında agentic özellikler yerine aşırı hızlı sohbet edilebilecek
     bir yer olsun"
    "sadece chat modu read only olsun"

Hız istemin kendisinden geliyor: araç şemaları her turda modele gidiyor ve
``coding`` kümesi bunun iki katından fazlasını taşıyor. Ama asıl tutulması
gereken şey hız değil, YAZAN bir aracın buraya sessizce sızmaması -- Chat'te
"bir dosyayı düzelt" diyen bir kullanıcı, düzeltilmiş bir dosya beklemiyor.
"""

from __future__ import annotations

import pytest

from toolsets import get_toolset_info

#: Bir şeyi DEĞİŞTİREN araçlar. Chat'te hiçbiri bulunmamalı.
#:
#: Liste araç ADIYLA yazılıyor, kümeyle değil: ``file`` kümesinin yarısı
#: (``read_file``, ``search_files``) Chat'te BİLEREK var, diğer yarısı
#: olmamalı. Küme adına bakan bir muhafız bu ayrımı göremezdi.
FORBIDDEN = frozenset(
    {
        "write_file",
        "patch",
        "terminal",
        "process",
        "execute_code",
        "delegate_task",
        "skill_manage",
        "computer_use",
        "output_file",
    }
)

#: Tarayıcıyı SÜREN araçlar. ``web_search``/``web_extract`` okumaktır ve
#: kalıyor; tıklayan, yazan, gezinen her şey çıkıyor.
FORBIDDEN_PREFIXES = ("browser_",)


@pytest.fixture(scope="module")
def chat() -> dict:
    info = get_toolset_info("chat")

    assert info is not None, "chat kumesi tanimli degil"

    return info


def test_chat_kumesi_VAR(chat: dict) -> None:
    assert chat["description"]
    assert chat["resolved_tools"], "chat kumesi bos"


def test_chat_hicbir_YAZAN_araci_TASIMIYOR(chat: dict) -> None:
    """Kuralın kendisi.

    Yeni bir araç ``web`` ya da ``vision`` kümesine eklenirse buraya
    kendiliğinden sızar -- bu test o sızıntının farkedildiği yer.
    """
    tools = set(chat["resolved_tools"])
    leaked = tools & FORBIDDEN

    assert not leaked, f"Chat'e yazan arac sizmis: {sorted(leaked)}"

    driving = [t for t in tools if t.startswith(FORBIDDEN_PREFIXES)]

    assert not driving, f"Chat'e tarayici surme araci sizmis: {sorted(driving)}"


def test_dosya_kumesinin_YALNIZCA_okuyan_yarisi_alinmis(chat: dict) -> None:
    """``file`` kümesi karışık: okuyan ve yazan araçları bir arada tutuyor.

    Bütün olarak ``includes`` etmek ``write_file`` ve ``patch``i de getirirdi;
    tek tek listelemek kümenin yarısını almanın tek yolu.
    """
    tools = set(chat["resolved_tools"])

    assert "read_file" in tools
    assert "search_files" in tools
    assert "write_file" not in tools
    assert "patch" not in tools


def test_HAFIZA_bilerek_iceride(chat: dict) -> None:
    """Tek istisna, ve kullanıcının kararı.

    Teknik olarak yazıyor ama sisteme değil kendi not defterine. Hafızasız bir
    sohbet her seferinde sıfırdan başlar; "hızlı sohbet" tam da tekrar
    anlatmak zorunda kalmamak demek.
    """
    assert "memory" in chat["resolved_tools"]


def test_okuma_araclari_GERCEKTEN_var(chat: dict) -> None:
    """Read-only, "araçsız" demek değil.

    Kullanıcı "sadece okuma araçları kalsın" dedi -- yani web araması ve dosya
    okuma ÇALIŞMALI. Boş bir küme de bu testlerin hepsinden geçerdi.
    """
    tools = set(chat["resolved_tools"])

    for needed in ("web_search", "web_extract", "session_search"):
        assert needed in tools, f"okuma araci eksik: {needed}"


def test_chat_coding_kumesinden_BELIRGIN_kucuk() -> None:
    """Hız iddiasının ölçüsü.

    Araç şemaları her turda modele gidiyor. Chat, Cowork'ün taşıdığının
    yarısından azını taşımıyorsa "aşırı hızlı" iddiası boştur.
    """
    chat_info = get_toolset_info("chat")
    coding_info = get_toolset_info("coding")

    assert chat_info is not None and coding_info is not None
    assert chat_info["tool_count"] * 2 < coding_info["tool_count"], (
        f"chat={chat_info['tool_count']} coding={coding_info['tool_count']} -- "
        "hiz kazanci iddia edilecek kadar buyuk degil"
    )


def test_safe_kumesi_KOPYALANMAMIS() -> None:
    """``safe`` adı güven veriyor ama Chat için yanlış küme.

    İçinde ``image_generate`` var (üretiyor, okumuyor) ve dosya okuma ile
    geçmiş araması hiç yok -- hem fazlası hem eksiği. Birinin "zaten safe var"
    deyip Chat'i ona bağlamasını engelleyen not burada.
    """
    safe = get_toolset_info("safe")
    chat_info = get_toolset_info("chat")

    assert safe is not None and chat_info is not None
    assert set(safe["resolved_tools"]) != set(chat_info["resolved_tools"])
    assert "image_generate" not in chat_info["resolved_tools"]
