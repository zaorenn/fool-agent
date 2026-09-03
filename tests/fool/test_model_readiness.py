"""Modelin tool-calling sınavı.

Upstream'in "bu model agentic değil" kararı bir DİZE eşleşmesi: model adında
belirli parçalar aranıyor. Bu yaklaşım iki yönden de yanlış cevap veriyor --
adı tanınmayan yetenekli bir model kısıtlanmıyor, adı tanınan ama ince
ayarlanmış bir model haksız yere işaretleniyor. Yerel modellerde ad zaten
kullanıcının koyduğu bir etiket.

Burada ad değil DAVRANIŞ ölçülüyor: modele gerçek araç şemaları verilip
birkaç somut istek yapılıyor ve doğru aracı doğru argümanlarla çağırıp
çağırmadığına bakılıyor.
"""

from __future__ import annotations

import json

from fool import model_readiness as mr


def test_sinav_bos_degil() -> None:
    assert len(mr.PROBES) >= 3


def test_her_soru_beklenen_araci_ve_alani_soyluyor() -> None:
    for probe in mr.PROBES:
        assert probe.prompt.strip()
        assert probe.expect_tool
        assert probe.expect_args, f"{probe.name}: beklenen arguman yazilmamis"


def test_her_sorunun_araci_sinav_semalarinda_var() -> None:
    """Şemada olmayan bir aracı beklemek, modeli imkânsız bir sınava sokmak."""
    names = {t["function"]["name"] for t in mr.PROBE_TOOLS}

    for probe in mr.PROBES:
        assert probe.expect_tool in names, f"{probe.name}: sema yok"


def test_dogru_arac_ve_argumanlar_geciyor() -> None:
    probe = mr.PROBES[0]
    call = {"name": probe.expect_tool, "arguments": dict(probe.expect_args)}

    assert mr.grade(probe, call) is True


def test_yanlis_arac_kaliyor() -> None:
    probe = mr.PROBES[0]

    assert mr.grade(probe, {"name": "baska_arac", "arguments": {}}) is False


def test_eksik_zorunlu_alan_kaliyor() -> None:
    """En sık görülen kusur: doğru araç, eksik argüman."""
    probe = mr.PROBES[0]

    assert mr.grade(probe, {"name": probe.expect_tool, "arguments": {}}) is False


def test_hic_arac_cagrilmamasi_kaliyor() -> None:
    assert mr.grade(mr.PROBES[0], None) is False


def test_arguman_metin_json_olarak_gelse_de_okunuyor() -> None:
    """Çoğu sağlayıcı ``arguments``ı JSON DİZESİ olarak döndürüyor.

    Bunu okumamak, doğru çalışan bir modeli haksız yere sınıfta bırakırdı.
    """
    probe = mr.PROBES[0]
    call = {"name": probe.expect_tool, "arguments": json.dumps(dict(probe.expect_args))}

    assert mr.grade(probe, call) is True


def test_bozuk_json_kaliyor_ama_cokmuyor() -> None:
    probe = mr.PROBES[0]

    assert mr.grade(probe, {"name": probe.expect_tool, "arguments": "{bozuk"}) is False


def test_sayi_metin_olarak_gelse_de_geciyor() -> None:
    """``"120"`` ile ``120`` aynı şeyi söylüyor; biçim ölçmüyoruz."""
    probe = next(p for p in mr.PROBES if p.name == "birim-cevirme")

    assert mr.grade(probe, {"name": "set_timer", "arguments": {"seconds": "120"}}) is True


def test_fazladan_arguman_gecmeyi_engellemiyor() -> None:
    probe = mr.PROBES[0]
    args = dict(probe.expect_args) | {"extra": "sey"}

    assert mr.grade(probe, {"name": probe.expect_tool, "arguments": args}) is True


def test_sonuc_puani_ve_gecti_bilgisini_veriyor() -> None:
    result = mr.summarize("test-model", [True, True, False, True, True])

    assert result["score"] == 4
    assert result["total"] == 5
    assert result["model"] == "test-model"
    assert isinstance(result["passed"], bool)


def test_gecme_esigi_tam_puan_istemiyor_ama_yuksek() -> None:
    """Tek bir kusur modeli sınıfta bırakmamalı; yarısı yetmemeli."""
    assert 0.5 < mr.PASS_RATIO <= 1.0


def test_dusuk_puan_gecmiyor() -> None:
    assert mr.summarize("m", [True, False, False, False, False])["passed"] is False


def test_tam_puan_geciyor() -> None:
    assert mr.summarize("m", [True] * 5)["passed"] is True


def test_bos_sonuc_gecmiyor() -> None:
    """Hiç ölçüm yapılamadıysa "geçti" demek, ölçmemekle aynı şey."""
    assert mr.summarize("m", [])["passed"] is False


# ---------------------------------------------------------------------------
# Kararın saklanması
# ---------------------------------------------------------------------------

def test_karar_yazilip_okunuyor(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(mr, "verdict_path", lambda: tmp_path / "v.json")

    mr.save_verdict({"model": "m1", "score": 5, "total": 5, "passed": True})

    assert mr.load_verdict("m1")["passed"] is True


def test_baska_model_icin_karar_YOK(tmp_path, monkeypatch) -> None:
    """Karar modele bağlı: bir modelin geçmesi diğerini geçirmez.

    Model değiştirmek yetkinin de değişmesi demek; eski kararı taşımak
    kullanıcının hiç sınamadığı bir modele yetki vermekti.
    """
    monkeypatch.setattr(mr, "verdict_path", lambda: tmp_path / "v.json")
    mr.save_verdict({"model": "m1", "score": 5, "total": 5, "passed": True})

    assert mr.load_verdict("m2") is None


def test_dosya_yoksa_none(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(mr, "verdict_path", lambda: tmp_path / "yok.json")

    assert mr.load_verdict("m1") is None


def test_bozuk_dosya_cokmuyor(tmp_path, monkeypatch) -> None:
    path = tmp_path / "v.json"
    path.write_text("{bozuk", encoding="utf-8")
    monkeypatch.setattr(mr, "verdict_path", lambda: path)

    assert mr.load_verdict("m1") is None


def test_gecti_mi_olculmemis_modeli_gecirmiyor(tmp_path, monkeypatch) -> None:
    """Hiç sınanmamış model "geçti" sayılmaz.

    Kapıyı açan kullanıcı ölçüm istiyor; ölçmeden geçirmek kapıyı hiç
    açmamakla aynı şey olurdu.
    """
    monkeypatch.setattr(mr, "verdict_path", lambda: tmp_path / "v.json")

    assert mr.has_passed("hic-sinanmamis") is False


def test_gecti_mi_kaydedilmis_sonucu_okuyor(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(mr, "verdict_path", lambda: tmp_path / "v.json")
    mr.save_verdict({"model": "m1", "score": 5, "total": 5, "passed": True})
    mr.save_verdict({"model": "m2", "score": 1, "total": 5, "passed": False})

    assert mr.has_passed("m1") is True
    assert mr.has_passed("m2") is False
