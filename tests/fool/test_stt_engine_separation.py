"""İki STT motoru AYRI AYRI kurulu sayılmalı.

Kullanıcının bildirdiği: "STT'de iki motor da 'use' gösteriyor, indirme
düğmesi çıkmıyor."

Sebep: ``whisper-turbo`` ile ``faster-whisper`` aynı ``probe_module``ü
paylaşıyor -- ikisi de ``faster_whisper`` paketiyle çalışıyor. ``status()``
ağırlıkları YALNIZCA ``warmup`` VE ``model_id`` birlikte tanımlıysa
soruyordu; ``faster-whisper``ın ikisi de yoktu, yani durumu sadece pakete
bakıyordu. Turbo kurulunca paket geliyor ve bu satır da "kurulu" görünüyordu.

Zararı görünmez değil: seçilince ``stt.local.model`` ``base`` oluyor ve o
ağırlıklar hiç inmemişse İLK CÜMLEDE 150 MB sessizce inmeye başlıyor --
kullanıcı yalnızca "çok yavaş" görüyor. Kullanıcının kuralı da net: "kurulu
olmayan bir motor seçilebilir olmamalı."
"""

from __future__ import annotations

import pytest

from fool import voice_models as vm


def _entry(entry_id: str) -> vm.VoiceEntry:
    e = vm.entry(entry_id)
    assert e is not None, f"katalogda yok: {entry_id}"
    return e


def test_iki_motor_ayni_paketi_paylasiyor() -> None:
    """Hatanın ön koşulu. Bu ayrışırsa aşağıdaki testlerin sebebi kalmaz."""
    assert _entry("whisper-turbo").probe_module == _entry("faster-whisper").probe_module


def test_her_STT_motorunun_KENDI_model_kimligi_var() -> None:
    """``model_id`` yoksa ağırlıklar hiç sorulmuyor.

    ``select()`` bu alanı ``stt.local.model``e yazıyor (``e.model_id or
    "base"``), yani girdinin gerçekten indirdiği model bu. Yazılmamış
    bırakmak, durumun başka bir modelin ağırlıklarına bakması demek.
    """
    for entry_id in ("whisper-turbo", "faster-whisper"):
        assert _entry(entry_id).model_id, f"{entry_id}: model_id bos"

    assert _entry("whisper-turbo").model_id != _entry("faster-whisper").model_id


def test_model_kimligi_olan_her_giris_AGIRLIK_da_soruyor() -> None:
    """Sınıfın kendisini tutan muhafız.

    Eski koşul ``e.warmup and e.model_id`` idi: ``warmup``ı olmayan bir
    ``model_id`` sessizce kontrolsuz kalıyordu. Yeni bir motor eklenirken aynı
    boşluğa düşülmesin diye koşul kaynakta tutuluyor.
    """
    from pathlib import Path

    source = Path(vm.__file__).read_text(encoding="utf-8")

    assert "if e.model_id and not _weights_present(e.model_id):" in source
    assert "if e.warmup and e.model_id and not _weights_present" not in source


def test_agirliklari_INMEMIS_motor_kurulu_sayilmiyor(monkeypatch) -> None:
    """Kullanıcının makinesinin birebir hâli: yalnızca turbo inmiş.

    Ağ İSTENMİYOR -- hangi ağırlığın diskte olduğu tek yerden
    (``_weights_present``) okunuyor ve burada o taklit ediliyor.
    """
    monkeypatch.setattr(vm, "_weights_present", lambda model_id: "turbo" in model_id)
    monkeypatch.setattr(vm, "_module_available", lambda name: True)

    assert vm.status("whisper-turbo")["installed"] is True
    assert vm.status("faster-whisper")["installed"] is False


def test_kurulu_olmayan_motor_SECILEMIYOR(monkeypatch) -> None:
    """Kullanıcının açık kuralı. ``select()`` durumu sormasaydı, panel
    indirme düğmesi göstermediği için kullanıcı hiç inmemiş bir modeli aktif
    yapardı."""
    monkeypatch.setattr(vm, "_weights_present", lambda model_id: "turbo" in model_id)
    monkeypatch.setattr(vm, "_module_available", lambda name: True)

    with pytest.raises(ValueError, match="kurulu degil"):
        vm.select("faster-whisper")


def test_kurulum_agirliklari_GERCEKTEN_indiriyor() -> None:
    """``warmup`` olmadan "Install" yalnızca paketi kurar.

    Paket zaten kuruluysa (turbo yüzünden) düğme hiçbir şey değiştirmez ve
    durum ``base`` inmediği için "kurulu değil" demeye devam ederdi: kullanıcı
    basar, hiçbir şey olmaz.
    """
    e = _entry("faster-whisper")

    assert e.warmup, "faster-whisper: warmup yok, agirliklar hic inmez"
    assert e.model_id in e.warmup, "warmup BASKA bir modeli isitiyor"
