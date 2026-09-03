"""Olay hafızası: ölçek bağlamdan ayrı, geri getirme anlamsal.

Bugünkü hafıza (``tools/memory_tool.py``) 2200 + 1375 karakterle sınırlı ve
sistem promptuna donmuş bir anlık görüntü olarak giriyor. O tasarım önek
önbelleğini koruyor ama ÖLÇEĞİ taşıyamıyor: "birkaç gün önce şunu demiştin"
3,5k karakterlik bir tahtaya sığmıyor.

Bu depo ikisini ayırıyor -- depo büyür, bağlama giren küçük kalır.

Gömücü ENJEKTE EDİLİYOR: ağa bağlı bir geri getirme sınavı, sınadığı şeyi
değil ağı sınar.
"""

from __future__ import annotations

import time

import pytest

from fool.recall_store import DEFAULT_CHAR_BUDGET, RecallStore


@pytest.fixture
def store(tmp_path):
    return RecallStore(tmp_path / "recall.db")


def _fake_embedder(vocabulary: dict[str, list[float]]):
    """Sözcük bazlı sahte gömücü: bilinen sözcüklerin vektörlerini toplar.

    Gerçek bir modeli taklit etmiyor -- yalnızca "anlamca yakın metinler yakın
    vektörler alır" kuralını deterministik hâle getiriyor.
    """

    def embed(texts, kind="document"):
        out = []
        for text in texts:
            vector = [0.0, 0.0, 0.0]
            for word in text.lower().split():
                hit = vocabulary.get(word.strip(".,!?"))
                if hit:
                    vector = [a + b for a, b in zip(vector, hit)]
            # Sifir vektor kosinusu tanimsiz birakir.
            if not any(vector):
                vector = [0.01, 0.01, 0.01]
            out.append(vector)
        return out

    return embed


# ---------------------------------------------------------------------------
# Yazma
# ---------------------------------------------------------------------------


def test_ani_yaziliyor_ve_sayiliyor(store) -> None:
    assert store.count() == 0
    assert store.remember("User has a cat named Pamuk")
    assert store.count() == 1


def test_cok_kisa_metin_YAZILMIYOR(store) -> None:
    assert store.remember("ok") is None
    assert store.count() == 0


def test_YAKIN_TEKRAR_yeni_kayit_acmiyor(store) -> None:
    """Aynı olgu her oturumda yeniden yazılırsa depo kopyalarla dolar.

    Geri getirme onları üst üste enjekte eder: bağlam dolar, bilgi artmaz.
    """
    store.remember("User has a cat named Pamuk")
    store.remember("User has a cat named Pamuk")

    assert store.count() == 1


def test_tekrar_gormek_ONEMI_artiriyor(store) -> None:
    """İki kez söylenen şey daha önemlidir -- metin değişmeden."""
    store.remember("User hates being interrupted", importance=0.4)
    store.remember("User hates being interrupted", importance=0.4)

    memory, _score = store.search("interrupted")[0]

    assert memory.importance > 0.4


def test_unutma_kaydi_siliyor(store) -> None:
    memory_id = store.remember("A passing detail")

    assert store.forget(memory_id) is True
    assert store.count() == 0


# ---------------------------------------------------------------------------
# Geri getirme
# ---------------------------------------------------------------------------


def test_SOZCUK_esleismesi_calisiyor(store) -> None:
    store.remember("User loves the band Radiohead")
    store.remember("User is building a desktop app")

    top, _score = store.search("Radiohead")[0]

    assert "Radiohead" in top.text


def test_ANLAMSAL_esleme_sozcuk_tutmasa_da_calisiyor(tmp_path) -> None:
    """Sözlüksel arama tek başına yetmiyor -- ölçülen hata buydu.

    "what music does he like" ile "User loves the band Radiohead" TEK BİR
    sözcük paylaşmıyor. FTS boş dönüyor ve sıralama saf tazeliğe düşüyordu:
    kullanıcının sorduğu şey üçüncü sırada kalıyordu.
    """
    embed = _fake_embedder(
        {
            "music": [1.0, 0.0, 0.0],
            "band": [0.9, 0.0, 0.0],
            "radiohead": [0.9, 0.0, 0.0],
            "app": [0.0, 1.0, 0.0],
            "desktop": [0.0, 0.9, 0.0],
            "cat": [0.0, 0.0, 1.0],
        }
    )
    store = RecallStore(tmp_path / "r.db", embedder=embed)

    store.remember("User loves the band Radiohead")
    store.remember("User is building a desktop app")
    store.remember("User has a cat")

    top, _score = store.search("what music does he like")[0]

    assert "Radiohead" in top.text


def test_gomme_YOKSA_yine_calisiyor(store) -> None:
    """LM Studio kapalı olabilir. Hafıza ona bağlı olmamalı."""
    store.remember("User loves the band Radiohead")

    hits = store.search("Radiohead")

    assert hits and "Radiohead" in hits[0][0].text


def test_gomucu_PATLARSA_yutuluyor(tmp_path) -> None:
    def boom(texts, kind="document"):
        raise RuntimeError("LM Studio kapali")

    store = RecallStore(tmp_path / "r.db", embedder=boom)

    assert store.remember("User loves the band Radiohead")
    assert store.search("Radiohead")


def test_hicbir_sey_eslesmezse_EN_TAZE_olanlar_geliyor(store) -> None:
    """Bir şey göstermek hiçbir şey göstermemekten iyi."""
    store.remember("User has a cat named Pamuk")

    hits = store.search("quantum chromodynamics")

    assert hits


def test_TAM_ISABET_eski_olsa_da_taze_alakasizi_geciyor(store) -> None:
    """Hatırlamanın değeri tam olarak burada: eskiyi doğru anda geri getirmek.

    İlk ağırlıklandırmada ilgi tazeliğin altında kalıyordu ve 20 gün önceki
    tam isabet, bugünkü alakasız kaydın arkasına düşüyordu.
    """
    now = time.time()
    store.remember("User's mother is named Ayse", now=now - 86400 * 20)
    store.remember("User asked about the weather", now=now - 60)

    top, _score = store.search("what is his mother called", now=now)[0]

    assert "Ayse" in top.text


# ---------------------------------------------------------------------------
# Bağlam bloğu
# ---------------------------------------------------------------------------


def test_blok_BUTCEYI_asmiyor(store) -> None:
    for index in range(60):
        store.remember(f"Fact number {index} about the user and their many interests")

    block, ids = store.context_block("user interests", budget=300, limit=50)

    assert len(block) <= 300
    assert ids


def test_blok_NE_KADAR_ONCE_yaziyor(store) -> None:
    """Zaman farkındalığı bloğun kendisinde: "3d ago" model için sinyal."""
    now = time.time()
    store.remember("User adopted a cat", now=now - 86400 * 3)

    block, _ids = store.context_block("cat", now=now)

    assert "3d ago" in block


def test_bos_depo_bos_blok(store) -> None:
    block, ids = store.context_block("anything")

    assert block == ""
    assert ids == []


def test_varsayilan_butce_32k_baglam_icin_makul() -> None:
    """Bağlamı hafızayla doldurmak, düşünecek yeri kaybetmek olurdu."""
    assert 500 <= DEFAULT_CHAR_BUDGET <= 3000


# ---------------------------------------------------------------------------
# Hatırlama sayacı ve yeniden yüzeye çıkma
# ---------------------------------------------------------------------------


def test_hatirlanan_ani_ISARETLENIYOR(store) -> None:
    memory_id = store.remember("User likes strong coffee")
    store.mark_recalled([memory_id])

    memory, _score = store.search("coffee")[0]

    assert memory.recall_count == 1


def test_HIC_hatirlanmamis_ani_kucuk_bir_artis_aliyor(store) -> None:
    """Olmadan geri getirme kendini besler: seçilen sürekli seçilir.

    Artı BİLİNÇLİ olarak küçük -- ilgiyi ezmemeli, yalnızca beraberliği
    bozmalı. Bu yüzden sınav gerçek bir beraberlik kuruyor: iki kayıt aynı
    yapıda, aynı yaşta, aynı önemde. Aralarındaki tek fark birinin daha önce
    hatırlanmış olması.
    """
    now = time.time()
    seen = store.remember("User drinks coffee", now=now - 3600)
    store.remember("User drinks tea", now=now - 3600)
    store.mark_recalled([seen])

    order = [m.text for m, _ in store.search("drinks", now=now)]

    assert "tea" in order[0], order


def test_hic_hatirlanmamis_artisi_ILGIYI_EZMIYOR(store) -> None:
    """Ters yön de doğru olmalı: tam isabet, tazeliğine bakılmaksızın kazanır."""
    now = time.time()
    seen = store.remember("User's password manager is Bitwarden", now=now - 3600)
    store.remember("User went for a walk", now=now - 3600)
    store.mark_recalled([seen])

    top, _score = store.search("which password manager", now=now)[0]

    assert "Bitwarden" in top.text


# ---------------------------------------------------------------------------
# Zaman farkındalığı
# ---------------------------------------------------------------------------


def test_son_gorulme_yaziliyor_ve_okunuyor(store) -> None:
    assert store.last_seen() is None

    now = time.time()
    store.touch_seen(now=now)

    assert store.last_seen() == pytest.approx(now, abs=1.0)


def test_gomme_sonradan_DOLDURULABILIYOR(tmp_path) -> None:
    """LM Studio kapalıyken yazılan anılar anlamsal aramaya görünmez kalırdı."""
    store = RecallStore(tmp_path / "r.db")
    store.remember("User has a dog named Karabas")

    embed = _fake_embedder({"dog": [1.0, 0.0, 0.0], "karabas": [1.0, 0.0, 0.0]})
    warm = RecallStore(tmp_path / "r.db", embedder=embed)

    assert warm.backfill_embeddings() == 1
    # Ikinci cagri doldurulacak bir sey bulmuyor.
    assert warm.backfill_embeddings() == 0


# ---------------------------------------------------------------------------
# Bütçe TEK bir olguya harcanmasın
# ---------------------------------------------------------------------------


def test_ayni_seyi_soyleyen_anilar_bir_kez_giriyor(store) -> None:
    """Yazma eşiği yalnızca son 200 anıya ve neredeyse birebir tekrara bakıyor.
    Aylar içinde aynı şey farklı sözcüklerle söylendiğinde ikisi de kaydediliyor,
    ikisi de aynı sorguda üste çıkıyor ve sabit bütçe tek olguya gidiyor."""
    store.remember("his cat is called Pamuk")
    store.remember("the cat Pamuk is his")

    _block, ids = store.context_block("cat Pamuk", budget=4000)

    assert len(ids) == 1


def test_SIGMAYAN_uzun_ani_arkasindakileri_goturmuyor(store) -> None:
    """``break`` uzun bir anı sırada öndeyken arkasındaki kısa ve sığacak
    olanları da birlikte götürüyordu."""
    store.remember("cats " + ("x" * 400))
    store.remember("cats are his whole life")

    block, ids = store.context_block("cats", budget=120)

    assert len(ids) == 1
    assert "whole life" in block


def test_farkli_seyler_ikisi_de_giriyor(store) -> None:
    """Sözcük paylaşmak aynı şey olmak değil: eşik ikisinin arasına konuldu."""
    store.remember("his cat is called Pamuk")
    store.remember("his dog is called Boncuk")

    _block, ids = store.context_block("his cat is called", budget=4000)

    assert len(ids) == 2
