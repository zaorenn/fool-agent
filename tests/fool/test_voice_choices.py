"""Ses tipleri panelde GORUNMUYORDU.

Kullanicinin bildirdigi: "kyutainin sadece 1 ses tipi mi var, modellerin
diger seslerini niye secemiyoruz".

Sebep: panel ``catalog_status()`` okuyor, eklentiyi degil. Kyutai
eklentisinin ``_VOICES`` demeti UC ses tasiyor ama katalog girdisinde
``voices`` alani hic tanimli degildi -- yani ``available_voices`` bos liste
donuyordu ve acilir listede secilecek bir sey olmuyordu. styletts2,
chatterbox ve f5-tts'te de ayni durum.

Bu dosya iki seyi tutuyor: (1) her kurulu TTS motorunun EN AZ bir secilebilir
sesi var, (2) kyutai'nin katalog listesi eklentinin listesiyle AYNI --
ikisinin ayri yerlerde yasamasi tam da bu hatayi uretmisti.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from fool import voice_models as vm

_TTS = [e for e in vm.CATALOG if e.kind == "tts"]


# ---------------------------------------------------------------------------
# Her motorun bir sesi var
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("entry", _TTS, ids=lambda e: e.id)
def test_her_TTS_motorunun_secilebilir_sesi_var(entry) -> None:
    """Bos liste = kullanici acilir listede hicbir sey goremiyor.

    Piper HARIC: onun sesleri ayri ayri inen ``.onnx`` dosyalari ve liste
    diskten uretiliyor -- hic ses inmemisse bos olmasi DOGRU cevap.
    """
    if entry.id == "piper":
        pytest.skip("piper'in sesleri diskten geliyor, katalogdan degil")

    assert vm.available_voices(entry), f"{entry.id}: secilebilir ses yok"


@pytest.mark.parametrize("entry", _TTS, ids=lambda e: e.id)
def test_ses_kimlikleri_ve_etiketleri_bos_DEGIL(entry) -> None:
    """Bos etiket, acilir listede bos bir satir demek."""
    for voice in vm.available_voices(entry):
        assert voice["id"].strip(), f"{entry.id}: kimliksiz ses"
        assert voice["label"].strip(), f"{entry.id}: etiketsiz ses"


@pytest.mark.parametrize("entry", _TTS, ids=lambda e: e.id)
def test_ses_kimlikleri_TEKIL(entry) -> None:
    """Ayni kimlikten iki tane, secimin hangisini kaydettigini belirsiz kilar."""
    ids = [v["id"] for v in vm.available_voices(entry)]

    assert len(ids) == len(set(ids)), f"{entry.id}: yinelenen ses kimligi"


# ---------------------------------------------------------------------------
# Katalog ile eklenti AYNI seyi soyluyor mu
# ---------------------------------------------------------------------------

def _plugin_voice_ids(path: pathlib.Path, name: str) -> list[str]:
    """Eklenti kaynagindaki demeti ITHAL ETMEDEN oku.

    Ithal etmek eklentinin bagimliliklarini (torch, moshi) ana ortama
    sokmayi gerektirirdi; onlar bilerek izole ortamlarda yasiyor.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if not isinstance(node, ast.AnnAssign | ast.Assign):
            continue
        targets = [node.target] if isinstance(node, ast.AnnAssign) else node.targets
        if not any(isinstance(t, ast.Name) and t.id == name for t in targets):
            continue
        value = node.value
        assert value is not None
        return [ast.literal_eval(item)[0] for item in value.elts]  # type: ignore[attr-defined]
    raise AssertionError(f"{path}: {name} bulunamadi")


def test_kyutai_katalogu_eklentiyle_AYNI() -> None:
    """Iki liste ayrisirsa panel var olmayan bir sesi sunar.

    Sonuc calisma aninda hata degil, SESSIZ yanlislik: motor tanimadigi
    kimlikte kendi varsayilanina dusuyor ve kullanici sectigi sesi hic
    duymuyor.
    """
    plugin = pathlib.Path("plugins/tts/fool-kyutai/__init__.py")
    if not plugin.exists():
        pytest.skip("kyutai eklentisi bu agacta yok")

    entry = vm.entry("kyutai")
    assert entry is not None

    assert [v["id"] for v in vm.available_voices(entry)] == _plugin_voice_ids(plugin, "_VOICES")


def test_kyutai_BIRDEN_COK_ses_veriyor() -> None:
    """Bildirilen hatanin dogrudan karsiligi."""
    entry = vm.entry("kyutai")
    assert entry is not None

    assert len(vm.available_voices(entry)) >= 3


# ---------------------------------------------------------------------------
# Secim gercekten kaydediliyor mu
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("entry", _TTS, ids=lambda e: e.id)
def test_sunulan_her_ses_KABUL_ediliyor(entry, monkeypatch) -> None:
    """Panelde gorunen ama ``set_voice``in reddettigi bir ses, kullaniciya
    "Could not save the speaker" olarak gorunurdu."""
    saved: dict[str, str] = {}
    monkeypatch.setattr(
        "fool_cli.config.set_config_value",
        lambda key, value: saved.__setitem__(key, value),
    )

    for voice in vm.available_voices(entry):
        vm.set_voice(entry.id, voice["id"])

    assert not vm.available_voices(entry) or saved


def test_bilinmeyen_ses_REDDEDILIYOR(monkeypatch) -> None:
    """Ters yon: dogrulama tumden kaldirilirsa yazim hatasi sessizce kaydolur."""
    monkeypatch.setattr("fool_cli.config.set_config_value", lambda key, value: None)

    with pytest.raises(ValueError):
        vm.set_voice("kokoro", "boyle-bir-ses-yok")


# ---------------------------------------------------------------------------
# Chatterbox TURBO
# ---------------------------------------------------------------------------

def test_chatterbox_TURBO_kullaniyor() -> None:
    """Ölçüldü (RTX 4070 Ti SUPER, aynı metin):

        chatterbox.tts        1,89 sn / cümle
        chatterbox.tts_turbo  1,60 sn sentez -> 6,40 sn ses = 4x gerçek zaman

    Klonlu ürün yolunda sıcak: 0,78 sn / cümle.

    Turbo aynı pakette (``chatterbox-tts==0.1.7``) zaten geliyordu; eklenti
    onu kullanmıyordu.
    """
    import pathlib

    plugin = pathlib.Path("plugins/tts/fool-chatterbox/__init__.py")
    source = plugin.read_text(encoding="utf-8")

    assert "chatterbox.tts_turbo" in source
    assert "ChatterboxTurboTTS" in source


def test_TURBO_yoksa_klasige_dusuyor() -> None:
    """Eski bir kurulumda ``tts_turbo`` yok ve oradaki kullanıcıyı sessizce
    sessizliğe düşürmek kabul edilemez."""
    import pathlib

    source = pathlib.Path("plugins/tts/fool-chatterbox/__init__.py").read_text(encoding="utf-8")

    assert "from chatterbox.tts import ChatterboxTTS as _Engine" in source


def test_bilinmeyen_arguman_SENTEZI_dusurmuyor() -> None:
    """Turbo'nun imzası klasikten dar.

    Bilinmeyen bir anahtar argümanı ``TypeError`` ile düşüyor -- yani
    kullanıcı hiçbir ses duymuyor. İmza bir kez okunup süzülüyor.
    """
    import pathlib

    source = pathlib.Path("plugins/tts/fool-chatterbox/__init__.py").read_text(encoding="utf-8")

    assert "inspect.signature" in source
    assert '"exaggeration" in _accepts' in source
    assert '"cfg_weight" in _accepts' in source
