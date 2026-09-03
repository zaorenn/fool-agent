"""İki sesli kip: arkadaş ve Jarvis.

Aynı sesli yüzeyden iki farklı şey isteniyor ve gereksinimleri çelişiyor:
arkadaş kipinde çoğu tur bir görev değil (kısa, sıcak, araçsız), Jarvis
kipinde gerçekten iş yapılıyor (terminal, dosya, kod). Tek kipte
birleştirmek ikisini de bozuyordu.

Bu testlerin ağırlığı SINIRDA: hangi kipin neye dokunabildiği ve tanınmayan
bir değerin nereye düştüğü. Bir yazım hatası yüzünden sesli yüzeyin
terminale açılması kabul edilemez.
"""

from __future__ import annotations

import pytest

from fool import voice_modes as vm
from toolsets import resolve_toolset


DANGEROUS = {
    "computer_use",
    "cronjob",
    "delegate_task",
    "execute_code",
    "read_file",
    "terminal_run",
    "write_file",
}


# ---------------------------------------------------------------------------
# Kip kaydı
# ---------------------------------------------------------------------------

def test_uc_kip_tanimli() -> None:
    """Notch'un iki kipi + Friend penceresi.

    ``friend`` sonradan eklendi: pencere KENDI sesini secebilsin diye
    (``voice.modes.friend.provider``). Notch'un kipleri degismedi.
    """
    assert set(vm.modes()) == {vm.COMPANION, vm.FRIEND, vm.JARVIS}


def test_friend_kipi_makineye_dokunmuyor_ama_hafizasi_var() -> None:
    friend = vm.get(vm.FRIEND)

    assert friend.touches_machine is False
    assert "memory" in (friend.toolsets or ())
    assert vm.requires_benchmark(vm.FRIEND) is False


def test_varsayilan_kip_ARKADAS() -> None:
    """Sesli yüzey varsayılan olarak makineye dokunamamalı."""
    assert vm.DEFAULT_MODE == vm.COMPANION
    assert vm.get(vm.DEFAULT_MODE).touches_machine is False


@pytest.mark.parametrize("mode_id", [vm.COMPANION, vm.JARVIS])
def test_her_kipin_etiketi_ozeti_ve_personasi_var(mode_id: str) -> None:
    mode = vm.get(mode_id)

    assert mode.label.strip()
    assert mode.summary.strip()
    assert mode.guidance.strip()


def test_kip_etiketleri_ingilizce() -> None:
    """Depo kuralı: kullanıcıya görünen metin İngilizce."""
    assert vm.get(vm.COMPANION).label == "Friend"
    assert vm.get(vm.JARVIS).label == "Jarvis"


# ---------------------------------------------------------------------------
# Yetki sınırı
# ---------------------------------------------------------------------------

def test_arkadas_kipi_makineye_dokunamiyor() -> None:
    tools: set[str] = set()
    for name in vm.get(vm.COMPANION).toolsets or ():
        tools |= set(resolve_toolset(name))

    assert tools, "arkadas kipi hicbir araca cozulmuyor"
    assert not (DANGEROUS & tools)


def test_jarvis_normal_cozumlemeye_birakiliyor() -> None:
    """``None`` = kısıtlama yok: Jarvis sahibinin tam yüzeyini alır."""
    assert vm.get(vm.JARVIS).toolsets is None


def test_jarvis_sinav_sart_kosuyor_arkadas_kosmuyor() -> None:
    """Sesle "şunu sil" demek ile modelin çağrıyı DOĞRU üretmesi ayrı şeyler.

    Arkadaş kipinde gereksiz -- orada dokunacak bir şey yok.
    """
    assert vm.requires_benchmark(vm.JARVIS) is True
    assert vm.requires_benchmark(vm.COMPANION) is False


# ---------------------------------------------------------------------------
# Tanınmayan değerler
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bad", ["", "  ", "JARVİS", "agent", None, 42, "companion "])
def test_taninmayan_kip_ARKADASA_dusuyor(bad) -> None:
    """Kapalı taraf güvenli taraf.

    Bir yazım hatasının sesli yüzeyi terminale açması kabul edilemez.
    ``"companion "`` (bosluklu) ve ``"JARVİS"`` (Türkçe İ) gibi yakın-kaçırma
    durumları bilerek sınanıyor.
    """
    mode = vm.get(bad)

    if str(bad).strip().lower() == "companion":
        assert mode.id == vm.COMPANION
    else:
        assert mode.touches_machine is False


def test_buyuk_harf_ve_bosluk_JARVIS_i_buluyor() -> None:
    assert vm.get("  JARVIS ").id == vm.JARVIS


# ---------------------------------------------------------------------------
# Yapılandırma
# ---------------------------------------------------------------------------

def test_aktif_kip_varsayilani_arkadas() -> None:
    assert vm.active_mode({}) == vm.COMPANION


def test_aktif_kip_okunuyor() -> None:
    assert vm.active_mode({"voice": {"mode": "jarvis"}}) == vm.JARVIS


def test_bozuk_aktif_kip_arkadasa_dusuyor() -> None:
    for bad in (None, [], "x", {"voice": 7}, {"voice": {"mode": "yok-boyle"}}):
        assert vm.active_mode(bad) == vm.COMPANION


def test_kip_basina_ses_OKUYAN_HICBIR_SEY_YOK() -> None:
    """Kipler araç kümesiyle ayrışıyor, SESLE değil.

    ``mode_provider`` silindi: yazan ama okunmayan bir ayar, hatanın geri
    büyümesi için hazır bir yoldu -- bir sonraki yüzey onu bulup "kip sesi"
    diye kullanmaya başlardı. Bu sınav o dönüşü yakalar.
    """
    assert not hasattr(vm, "mode_provider")


def test_hicbir_kip_kendi_sesini_TASIMIYOR() -> None:
    """Kip tanımında ses alanı yok -- olsaydı ikinci bir hakikat olurdu."""
    for mode in vm.modes().values():
        assert not hasattr(mode, "provider")
        assert not hasattr(mode, "voice")


# ---------------------------------------------------------------------------
# Jarvis personası -- sesle iş yapmanın kuralları
# ---------------------------------------------------------------------------

def test_jarvis_yikici_islemden_once_ONAY_istiyor() -> None:
    """Sesle yanlış anlaşılma kolay; bedeli gerçek bir eylem olabilir."""
    flat = " ".join(vm.JARVIS_GUIDANCE.split())

    assert "WAIT for a yes" in flat
    assert "destructive" in flat


def test_jarvis_belirsizlikte_TAHMIN_ETMIYOR() -> None:
    flat = " ".join(vm.JARVIS_GUIDANCE.split())

    assert "ask instead of guessing" in flat


def test_jarvis_sessizce_yeniden_denemiyor() -> None:
    """Kullanıcı ekrana bakmıyor; başarısız denemeleri göremez."""
    flat = " ".join(vm.JARVIS_GUIDANCE.split())

    assert "Do not retry variations silently" in flat


def test_jarvis_yaptigini_gecmis_zamanda_soyluyor() -> None:
    """"Yapacağım" değil "yaptım": kullanıcı sonucu duymak istiyor."""
    flat = " ".join(vm.JARVIS_GUIDANCE.split())

    assert "past tense" in flat


def test_iki_persona_da_kisa() -> None:
    """Sistem promptu bedava değil."""
    for mode_id in (vm.COMPANION, vm.JARVIS):
        assert len(vm.get(mode_id).guidance) < 1_800


# ---------------------------------------------------------------------------
# Gerçek seslendirme yolu
# ---------------------------------------------------------------------------

def test_kip_sesi_genel_ayari_ARTIK_EZMIYOR(monkeypatch) -> None:
    """Tek hakikat ``tts.provider`` -- kip başına ses KALDIRILDI.

    Ölçülen hata (kullanıcının kurulumundan, birebir):

        tts.provider                = styletts2   <- panelin gösterdiği
        voice.modes.friend.provider = kyutai      <- gerçekten koşan

    Panel "StyleTTS 2" yazıyor (cümle başına 0,56 sn), motor kyutai koşuyor
    (11 sn). Kullanıcı panelde bir şey seçip bambaşka bir sesi duyuyordu ve
    gecikmenin sebebini hiçbir yerden göremiyordu. Üstüne tek-motor kuralı
    yüzünden iki yüzey iki farklı motor isteyince her tur yükle-boşalt
    döngüsüne giriyordu.
    """
    from tools import tts_tool

    import fool_cli.config as cfg

    # Eski ezme anahtari bilerek yaziliyor: okunmamali.
    monkeypatch.setattr(
        cfg,
        "load_config",
        lambda *a, **k: {
            "tts": {"provider": "kokoro"},
            "voice": {"mode": "friend", "modes": {"friend": {"provider": "styletts2"}}},
        },
    )

    assert tts_tool._get_provider({"provider": "kokoro"}) == "kokoro"
    # Okuyan islev de artik YOK -- geri gelirse bu satir kirilir.
    assert not hasattr(tts_tool, "_voice_mode_provider")


def test_kip_sesi_yoksa_genel_ayar_gecerli() -> None:
    from tools import tts_tool

    assert tts_tool._get_provider({"provider": "kokoro"}) == "kokoro"


def test_kip_sesi_okuma_hatasi_seslendirmeyi_SUSTURMUYOR(monkeypatch) -> None:
    """Bir yapılandırma hatası yüzünden sesin tamamen kesilmesi kabul edilemez."""
    import fool.voice_modes as _vm
    from tools import tts_tool

    def _boom(*a, **k):
        raise RuntimeError("config unreadable")

    monkeypatch.setattr(_vm, "active_mode", _boom)

    assert tts_tool._get_provider({"provider": "kokoro"}) == "kokoro"


def test_ESKI_kip_ayari_yapilandirmada_kalsa_bile_YOK_SAYILIYOR(monkeypatch) -> None:
    """Eski kurulumlarda ``voice.modes.<kip>.provider`` yazılı kalmış olabilir.

    Silmek yerine YOK SAYMAK bilinçli: kararı geri almak isteyen bir
    kullanıcının değeri kaybolmuyor, ama sessizce sesi ezmiyor da.
    """
    import fool_cli.config as cfg
    from tools import tts_tool

    monkeypatch.setattr(
        cfg,
        "load_config",
        lambda *a, **k: {
            "voice": {"mode": "jarvis", "modes": {"jarvis": {"provider": "orpheus"}}}
        },
    )

    assert tts_tool._get_provider({"provider": "kokoro"}) == "kokoro"


# ---------------------------------------------------------------------------
# Yüzey başına ses -- İSTEK katmanındaki son kaynak
# ---------------------------------------------------------------------------
#
# Kip başına ses (``voice.modes.<kip>.provider``) kaldırıldıktan sonra bile
# ikinci bir ezme yolu AYAKTA kalmıştı: masaüstü ``POST /api/audio/speak``
# gövdesinde bir ``provider`` gönderebiliyordu ve Friend penceresi bunu
# gönderiyordu. Neden hata olduğu ölçüldü:
#
#   * Tek seferlik yol (``/api/audio/speak``) istekteki adı OKUYORDU.
#   * Cümle-cümle akış yolu (``speak_stream_ws``) hiç okumuyordu, her zaman
#     genel ``tts.provider``ı çözüyordu.
#
# Yani AYNI pencere, AYNI cevap: akış çalışırsa X motoruyla, geri düşüşte Y
# motoruyla konuşuyordu. Üstelik gönderilen ad yalnızca pencere açılırken bir
# kez okunan bir React state'iydi -- kullanıcı motoru Ayarlar'dan
# değiştirdiğinde Friend eski adı tutuyordu.


def test_speak_istegi_yuzeye_ozel_ses_TASIMIYOR() -> None:
    """Gövdedeki ``provider`` sessizce DÜŞÜYOR -- alan artık yok.

    Eski masaüstü paketleri (güncellenmemiş bir pencere) hâlâ alanı
    gönderiyor olabilir; düşürülmesi doğru davranış: tek hakikat sunucuda.
    """
    from fool_cli.web_models import TTSSpeakRequest

    request = TTSSpeakRequest(text="merhaba", provider="kyutai")

    assert not hasattr(request, "provider")
    assert request.model_dump() == {"text": "merhaba"}


def test_speak_ucu_saglayiciyi_SENTEZ_ARACINA_GECIRMIYOR(monkeypatch) -> None:
    """Uç, sentez aracını saglayıcı vermeden çağırıyor.

    Doğrudan davranış: aracın aldığı argümanlar kaydediliyor. Bir ``provider``
    anahtar argümanı geçilseydi yüzey yine kendi sesini seçebiliyor olurdu.
    """
    import asyncio

    from fool_cli.web_models import TTSSpeakRequest
    from tools import tts_tool

    seen: dict[str, object] = {}

    def _record(text, **kwargs):
        seen["text"] = text
        seen["kwargs"] = kwargs
        # Sentezi gerçekten yapmadan çık: ölçtüğümüz şey ARGÜMANLAR.
        return '{"success": false, "error": "test"}'

    monkeypatch.setattr(tts_tool, "text_to_speech_tool", _record)

    from fastapi import HTTPException

    import fool_cli.web_server as web_server

    with pytest.raises(HTTPException):
        asyncio.run(web_server.speak_text(TTSSpeakRequest(text="merhaba"), None))

    assert seen["text"] == "merhaba"
    assert seen["kwargs"] == {}, (
        f"Uc sentez aracina fazladan argüman geçiyor: {seen['kwargs']}. "
        "Yüzey başına ses geri gelmiş olabilir."
    )


def test_akis_ve_tek_seferlik_yollar_AYNI_saglayiciyi_cozuyor(monkeypatch) -> None:
    """İki yolun çözümlemesi tek işlevden geliyor: ``_get_provider``.

    Ayrıştıkları an kullanıcı aynı pencerede iki farklı ses duyuyor. Burada
    ölçülen şey, ikisinin de aynı yapılandırma anahtarına bakması.
    """
    from tools.tts_tool import _get_provider

    config = {"provider": "styletts2"}

    # Akış yolu (``speak_stream_ws::_resolve``) ve tek seferlik yol
    # (``text_to_speech_tool``) ikisi de bunu çağırıyor.
    assert _get_provider(config) == "styletts2"

    # Eski ezme anahtarları yazılı olsa BİLE sonuç değişmiyor.
    import fool_cli.config as cfg

    monkeypatch.setattr(
        cfg,
        "load_config",
        lambda *a, **k: {
            "tts": {"provider": "styletts2"},
            "voice": {"mode": "friend", "modes": {"friend": {"provider": "kyutai"}}},
        },
    )

    assert _get_provider(config) == "styletts2"
