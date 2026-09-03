"""Seçili seslendirme motoru kurulu bir alternatiften çok yavaşsa söylenmeli.

CODEX görev tanımı Chatterbox'ı "28 sn, hızlandırılabilir mi araştır" diye
işaretliyor. Ölçtüm (bu makine, kısa cümle, saniye):

    motor            ilk      2.       3.
    piper           3,10    0,11    0,11
    kokoro          7,69    0,14    0,14
    chatterbox     14,64    1,94    1,74
    qwen3-tts      36,75   15,38    9,26

Belgelenen tabloyla:

    Chatterbox   58 / 28   ->  14,64 / 1,74    ~16x daha hizli (belge eskimis)
    Kokoro      7,6 / 0,08 ->   7,69 / 0,14    ayni
    Qwen3-TTS  18,4 / 6,0  ->  36,75 /  9,26   DAHA YAVAS

Yani Chatterbox sorunu kalıcı-süreç değişikliğiyle zaten çözülmüş. Asıl sorun
kullanıcının SEÇİLİ motoru: qwen3, kurulu en hızlısından ~66 kat yavaş ve bu
hiçbir yerde görünmüyor.
"""

from __future__ import annotations

import pytest

from fool import voice_bench as vb


RESULTS = {
    "kokoro": {"elapsed_ms": 140},
    "piper": {"elapsed_ms": 110},
    "chatterbox": {"elapsed_ms": 1_740},
    "qwen3-tts": {"elapsed_ms": 9_260},
}


# ---------------------------------------------------------------------------
# Karşılaştırma
# ---------------------------------------------------------------------------

def test_cok_yavas_secim_yakalaniyor() -> None:
    hit = vb.faster_alternative("qwen3-tts", RESULTS)

    assert hit is not None
    alternative, alt_ms, current_ms = hit
    # ``piper`` DEGIL (110 ms ile en hizlisi o): bkz. asagidaki kalite testi.
    assert alternative == "kokoro"
    assert alt_ms == 140
    assert current_ms == 9_260


def test_HIZLI_ama_YAPAY_motor_onerilmiyor() -> None:
    """Öneri yalnızca hıza bakınca saçmalıyordu.

    Ölçümde piper 110 ms ile en hızlısı, ama qwen3-tts'i seçen kullanıcı onu
    GERÇEKÇİLİĞİ için seçti. "piper'a geç" demek, kullanıcının çözdüğü
    sorunu geri getirmek olurdu -- hızlı ama kulağa robot gibi gelen bir ses.
    """
    alternative, _, _ = vb.faster_alternative("qwen3-tts", RESULTS)

    assert alternative not in vb.BASIC_QUALITY


def test_YAPAY_motordan_yapay_motora_oneri_serbest() -> None:
    """Ters yön: kısıt kalite DÜŞÜŞÜNE karşı, kalite artışına değil.

    Zaten piper kullanan biri için daha iyi bir seçenek gizlenmemeli.
    """
    results = {"piper": {"elapsed_ms": 9_000}, "kokoro": {"elapsed_ms": 140}}

    hit = vb.faster_alternative("piper", results)

    assert hit is not None
    assert hit[0] == "kokoro"


def test_tek_secenek_YAPAY_ise_oneri_YOK() -> None:
    """Elde yalnızca bir kalite düşüşü varsa susmak doğru cevap."""
    results = {"kyutai": {"elapsed_ms": 9_000}, "piper": {"elapsed_ms": 110}}

    assert vb.faster_alternative("kyutai", results) is None


def test_zaten_hizli_secim_uyarilmiyor() -> None:
    """0,11 ile 0,14 arasındaki fark kulakla duyulmuyor."""
    assert vb.faster_alternative("kokoro", RESULTS) is None


def test_kucuk_fark_uyarilmiyor() -> None:
    """Kullanıcı ses kalitesi için biraz gecikmeyi göze almış olabilir.

    Her küçük farkta uyarmak gürültü olurdu; eşik bilerek yüksek.
    """
    results = {"a": {"elapsed_ms": 2_000}, "b": {"elapsed_ms": 1_000}}

    assert vb.faster_alternative("a", results) is None


def test_esigi_gecen_fark_uyariliyor() -> None:
    results = {"a": {"elapsed_ms": 3_000}, "b": {"elapsed_ms": 1_000}}

    assert vb.faster_alternative("a", results) is not None


def test_olculmemis_motor_icin_karar_YOK() -> None:
    """Ölçülmemiş bir motoru "yavaş" ilan etmek uydurmak olurdu."""
    assert vb.faster_alternative("hic-olculmemis", RESULTS) is None


def test_tek_motor_varsa_karsilastirma_yok() -> None:
    assert vb.faster_alternative("a", {"a": {"elapsed_ms": 9_000}}) is None


def test_bozuk_kayitlar_cokmuyor() -> None:
    for bad in (None, [], "x", {"a": "bozuk"}, {"a": {"elapsed_ms": "x"}}):
        assert vb.faster_alternative("a", bad) is None


def test_sifir_olcum_yok_sayiliyor() -> None:
    results = {"a": {"elapsed_ms": 9_000}, "b": {"elapsed_ms": 0}}

    assert vb.faster_alternative("a", results) is None


# ---------------------------------------------------------------------------
# Mesaj
# ---------------------------------------------------------------------------

def test_mesaj_olcumu_ve_cozumu_birlikte_veriyor() -> None:
    message = vb.slow_engine_message("qwen3-tts", "kokoro", 140, 9_260)

    assert "9.26s" in message
    assert "0.14s" in message
    # KABUK KOMUTU YOK: bunu okuyan kisi masaustu panelinde duruyor ve secim
    # orada tek tik. Terminale gondermek ayni isi daha zor bir yerde
    # yaptirmakti.
    assert "fool config set" not in message
    assert "Listen" in message


def test_mesaj_kat_farkini_soyluyor() -> None:
    assert "66x faster" in vb.slow_engine_message("qwen3-tts", "kokoro", 140, 9_260)


# ---------------------------------------------------------------------------
# Saklama
# ---------------------------------------------------------------------------

def test_sonuc_yazilip_okunuyor(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(vb, "results_path", lambda: tmp_path / "b.json")

    vb.save_result("kokoro", 140)

    assert vb.load_results()["kokoro"]["elapsed_ms"] == 140


def test_sonuclar_birikiyor(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(vb, "results_path", lambda: tmp_path / "b.json")

    vb.save_result("kokoro", 140)
    vb.save_result("piper", 110)

    assert set(vb.load_results()) == {"kokoro", "piper"}


def test_dosya_yoksa_bos(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(vb, "results_path", lambda: tmp_path / "yok.json")

    assert vb.load_results() == {}


def test_bozuk_dosya_cokmuyor(tmp_path, monkeypatch) -> None:
    path = tmp_path / "b.json"
    path.write_text("{bozuk", encoding="utf-8")
    monkeypatch.setattr(vb, "results_path", lambda: path)

    assert vb.load_results() == {}


# ---------------------------------------------------------------------------
# Ölçüm koşusu
# ---------------------------------------------------------------------------

def test_bench_ISINMIS_olcumu_sakliyor(tmp_path, monkeypatch) -> None:
    """İlk çağrı model yüklemesini içerir ve oturum başına bir kez ödenir.

    Karşılaştırmayı ilk çağrıya dayandırmak her seferinde yanlış motoru
    "hızlı" gösterirdi.
    """
    monkeypatch.setattr(vb, "results_path", lambda: tmp_path / "b.json")

    from fool import voice_models as vm

    entry = next(e for e in vm.CATALOG if e.kind == "tts")
    monkeypatch.setattr(vm, "CATALOG", (entry,))
    monkeypatch.setattr(vm, "status", lambda entry_id: {"installed": True})

    calls = {"n": 0}
    clock = {"t": 0.0}

    def _fake_preview(entry_id):
        calls["n"] += 1
        # Ilk cagri yavas, sonrakiler hizli -- gercek davranis.
        clock["t"] += 5.0 if calls["n"] == 1 else 0.1
        return {"ok": True}

    import fool.voice_preview as vp
    import time as _time

    monkeypatch.setattr(vp, "preview", _fake_preview)
    monkeypatch.setattr(_time, "monotonic", lambda: clock["t"])

    rows = vb.run_bench(rounds=3)

    assert len(rows) == 1
    assert rows[0]["warm_ms"] < rows[0]["first_ms"]
    assert vb.load_results()[entry.id]["elapsed_ms"] == rows[0]["warm_ms"]


def test_bench_patlayan_motoru_atlıyor(tmp_path, monkeypatch) -> None:
    """Bir motorun çökmesi ölçümün tamamını düşürmemeli."""
    monkeypatch.setattr(vb, "results_path", lambda: tmp_path / "b.json")

    from fool import voice_models as vm

    entry = next(e for e in vm.CATALOG if e.kind == "tts")
    monkeypatch.setattr(vm, "CATALOG", (entry,))
    monkeypatch.setattr(vm, "status", lambda entry_id: {"installed": True})

    import fool.voice_preview as vp

    def _boom(entry_id):
        raise RuntimeError("engine died")

    monkeypatch.setattr(vp, "preview", _boom)

    rows = vb.run_bench(rounds=2)

    assert rows[0]["error"] == "engine died"
    assert "warm_ms" not in rows[0]


# ---------------------------------------------------------------------------
# "Ölçülmedi" ile "ölçüldü, iyi" ayrı sorular
# ---------------------------------------------------------------------------
#
# Bu bölüm bir hatanın ardından yazıldı. Ölçüm sonuçları KATALOG KİMLİĞİYLE
# saklanıyordu (``qwen3-tts``) ama ``tts.provider`` yapılandırmaya SAĞLAYICI
# ADINI yazıyor (``qwen3``). Anahtarlar tutmayınca ``faster_alternative``
# ``None`` dönüyordu ve doctor bunu "sorun yok" diye gösteriyordu -- yani
# ölçülen 66 kat fark ekranda "latency looks fine" olarak çıktı.

def test_olculmus_mu_sorusu_ayri_cevap_veriyor() -> None:
    assert vb.is_measured("kokoro", RESULTS) is True
    assert vb.is_measured("hic-yok", RESULTS) is False


def test_olculmus_mu_bozuk_kayitlarda_false() -> None:
    for bad in (None, [], "x", {"a": "bozuk"}, {"a": {"elapsed_ms": "x"}}, {"a": {"elapsed_ms": 0}}):
        assert vb.is_measured("a", bad) is False


def test_bench_SAGLAYICI_adiyla_sakliyor(tmp_path, monkeypatch) -> None:
    """``tts.provider`` sağlayıcı adını yazıyor; kayıt onunla eşleşmeli."""
    monkeypatch.setattr(vb, "results_path", lambda: tmp_path / "b.json")

    from fool import voice_models as vm

    # ``provider_id`` ile ``id``nin GERCEKTEN farkli oldugu bir girdi gerekiyor
    # (qwen3-tts -> qwen3). StyleTTS 2 eklendiginde bu test yanlisi seciyordu:
    # onun provider_id'si id'siyle ayni ve test kendini dogrulayamiyordu.
    entry = next(
        e for e in vm.CATALOG
        if e.kind == "tts" and e.provider_id and e.provider_id != e.id
    )
    monkeypatch.setattr(vm, "CATALOG", (entry,))
    monkeypatch.setattr(vm, "status", lambda entry_id: {"installed": True})

    import fool.voice_preview as vp

    monkeypatch.setattr(vp, "preview", lambda entry_id: {"ok": True})

    vb.run_bench(rounds=1)

    assert entry.provider_id in vb.load_results()
    assert entry.provider_id != entry.id, "bu test provider_id != id olan bir girdi gerektiriyor"
