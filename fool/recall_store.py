"""Olay hafızası: zaman damgalı, aranabilir, bütçeli.

Neden var
---------
Bugünkü hafıza (``tools/memory_tool.py``) İYİ ama küçük: ``MEMORY.md`` 2200,
``USER.md`` 1375 karakter -- toplam ~3,5k karakter, yani ~900 token. İkisi de
sistem promptuna DONMUŞ bir anlık görüntü olarak giriyor ve bu bilinçli bir
karar: önek önbelleği korunuyor.

O tasarımın taşıyamadığı tek şey ÖLÇEK. "Birkaç gün önce şunu demiştin" için
gereken şey 3,5k karakterlik bir tahtaya sığmıyor, ve sığdırmaya çalışmak
eskiyi silmek demek. İstenen tam tersi: eskinin durması ve gerektiğinde geri
gelmesi.

Çözüm, ÖLÇEĞİ bağlamdan ayırmak: depo büyür, bağlama giren küçük kalır. Her
turda yalnızca o an ilgili birkaç kayıt enjekte ediliyor.

Neden SQLite, neden dış bir uygulama değil
------------------------------------------
- SQLite zaten geliyor (``state.db``, ``projects.db``) -- yeni kurulum yok.
- FTS5 tam metin aramayı sıfır bağımlılıkla veriyor (sqlite 3.50, doğrulandı).
- Çevrimdışı; başka bir programın açık olmasına bağlı değil.
- Zaman damgası, çürüme ve puanlama tek sorguda çözülüyor.

Bir markdown kasası insan için okunaklı, geri getirme için yanlış araç.
Okunaklılık zaten korunuyor: ``MEMORY.md``/``USER.md`` duruyor; burası onların
ALTINDAKİ katman.

İki BAĞIMSIZ hafıza -- bedavaya
-------------------------------
Depo ``FOOL_HOME/memories/recall.db``. Masaüstü bir profili çalıştırırken
``FOOL_HOME`` o profilin dizini, yani ``persona`` profilinin hafızası ile
normal ajanınki fiziksel olarak ayrı dosyalar. Ek bir mekanizmaya gerek yok.

(Motorlar ve ses varlıkları için kural TERSİ -- onlar makine düzeyinde
paylaşılıyor, bkz. ``fool/machine_assets.py``. Ayrım şu: motor kurulumu makine
varlığı, hafıza kullanıcı durumu.)

Zone A: upstream bu dosyayı bilmiyor.
"""

from __future__ import annotations

import re
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Sequence

#: Bir anının yarı ömrü -- bu kadar gün sonra tazelik puanı yarıya iner.
#:
#: 10 gün: bir hafta öncesi hâlâ güçlü, bir ay öncesi zayıf ama silinmiş
#: değil. Çürüme SİLME değil SIRALAMA: eski bir anı yeterince ilgiliyse yine
#: geri geliyor.
RECENCY_HALF_LIFE_DAYS = 10.0

#: Hiç hatırlanmamış anılara verilen küçük artı.
#:
#: Olmadan geri getirme kendini besliyor: bir kez seçilen sürekli seçiliyor,
#: hiç seçilmeyen hiç görünmüyor. Küçük tutuluyor -- ilgiyi ezmemeli, yalnızca
#: beraberliği bozmalı.
UNSEEN_BONUS = 0.15

#: Enjekte edilen bloğun karakter bütçesi.
#:
#: 32k bağlamda ~1500 karakter (~375 token) hafızaya ayrılabilir bir paydır;
#: 64k'da iki katı rahat. Varsayılan küçük taraftan: bağlamı hafızayla
#: doldurmak, hatırlananla düşünecek yeri kaybetmek olurdu.
DEFAULT_CHAR_BUDGET = 1500

#: Bir DÜZELTMENİN sıralamadaki ek ağırlığı.
#:
#: "Kullanıcının sevdiği şeyleri VE kendi hatalarını öğrensin" istendi. İkisi
#: aynı ağırlıkta değil: unutulmuş bir tercih küçük bir kayıp, unutulmuş bir
#: düzeltme AYNI HATANIN TEKRARI -- ve bir kez düzeltilmiş bir şeyde ikinci kez
#: yanılmak, hiç bilmemekten daha kötü karşılanıyor.
#:
#: Değer, tazelik teriminin (en fazla 0,5) üstünde ve ilgi teriminin (3,0)
#: çok altında bilinçli olarak: bir düzeltme, konuyla ilgisi olmadığında yine
#: de geri gelmemeli. Yaptığı tek şey, EŞİT ilgideki bir yarışı kazanmak.
CORRECTION_BONUS = 0.6

#: Aynı anının tekrar YAZILMASINI engelleyen benzerlik eşiği.
#:
#: Yüksek tutuluyor çünkü buradaki hata GERİ ALINAMAZ: eşiğin altına düşen bir
#: anı hiç kaydedilmiyor, yani gerçekten yeni bir şey sessizce kaybolabilir.
DUPLICATE_RATIO = 0.92

#: Aynı şeyi TEKRAR SÖYLEYEN bir anının o turda ATLANMA eşiği.
#:
#: Yazma eşiğinden belirgin biçimde düşük, çünkü buradaki hata UCUZ: yalnızca
#: bir turun bağlamından bir satır düşüyor, anı yerinde duruyor ve bir sonraki
#: soruda geri geliyor.
#:
#: Neden gerekli: yazma eşiği yalnızca SON 200 anıya bakıyor ve yalnızca
#: neredeyse birebir tekrarı yakalıyor. Aylar içinde aynı şey farklı
#: sözcüklerle üç kez söylendiğinde üçü de kaydediliyor, üçü de aynı sorguda
#: yüksek puan alıyor ve sabit bütçe tek bir olguyu üç kez anlatmaya gidiyor.
#: Yani "her şeyi hatırlasın" isteği tam da burada, sessizce yarıya iniyor.
#:
#: Sayı ÖLÇÜLDÜ, seçilmedi. Aynı olgunun iki anlatımı ile ayrı iki olgunun
#: bu ölçüde nereye düştüğü (Jaccard):
#:
#:   0,667  "his cat is called Pamuk" / "the cat Pamuk is his"   <- aynı şey
#:   0,667  "his cat is called Pamuk" / "his cat is named Pamuk" <- aynı şey
#:   0,500  "he likes coffee"         / "he likes tea"           <- AYRI
#:   0,429  "his cat is called Pamuk" / "his dog is called Boncuk" <- AYRI
#:
#: Eşik ikisinin arasında. Yanlış tarafa düşerse tercih SAKLAMAK yönünde:
#: fazladan bir satır bütçe israfı, eksik bir satır unutmak.
REDUNDANT_RATIO = 0.6

_WORD_RE = re.compile(r"[^\W\d_]+", re.UNICODE)


#: Metinleri vektöre çeviren işlev. ``None`` dönerse gömme YOK sayılıyor.
#:
#: Enjekte edilebilir olması sınav içindir: ağa bağlı bir geri getirme sınavı,
#: sınadığı şeyi değil ağı sınar.
#: ``kind`` ``"query"`` ya da ``"document"``.
#:
#: Model ayrımı önemsiz DEĞİL: nomic-embed-text görev öneki bekliyor
#: (``search_query:`` / ``search_document:``) ve öneksiz benzerlikler
#: birbirine yapışıyor -- ölçüldü, ilgili ve ilgisiz çiftler 0,39-0,52
#: aralığına sıkışıp sıralamayı taşıyamıyordu. Ayrımı burada YAPMIYORUZ,
#: yalnızca çağırana bildiriyoruz: hangi önekin gerektiği modele özgü ve o
#: bilgi sağlayıcıda duruyor.
Embedder = Callable[[Sequence[str], str], "list[list[float]] | None"]


@dataclass(frozen=True)
class Memory:
    """Tek bir anı."""

    id: int
    text: str
    kind: str
    created_at: float
    importance: float
    recall_count: int

    def age_days(self, now: float | None = None) -> float:
        return max(0.0, ((now or time.time()) - self.created_at) / 86400.0)


def _normalize(text: str) -> str:
    return " ".join(_WORD_RE.findall(text.lower()))


def _similarity(a: str, b: str) -> float:
    """Sözcük kümesi örtüşmesi (Jaccard) -- yakın tekrarları yakalamak için."""
    wa, wb = set(_normalize(a).split()), set(_normalize(b).split())

    if not wa or not wb:
        return 0.0

    return len(wa & wb) / len(wa | wb)


def _fts_query(text: str) -> str:
    """Kullanıcı metnini GÜVENLİ bir FTS5 sorgusuna çevir.

    Ham metni FTS5'e vermek sözdizimi hatası üretiyor (tırnak, yıldız, ``NEAR``
    gibi belirteçler yüzünden). Sözcükler çıkarılıp OR ile bağlanıyor: geri
    getirme kesişim değil SIRALAMA işi, tek eşleşen sözcük de aday olmalı.
    """
    words = [w for w in _WORD_RE.findall(text.lower()) if len(w) > 2]

    return " OR ".join('"' + w + '"' for w in words[:32])


class RecallStore:
    """Zaman damgalı anıların deposu ve geri getiricisi."""

    def __init__(self, db_path: str | Path, *, embedder: Embedder | None = None) -> None:
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(self.path), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._embedder = embedder
        self._migrate()

    def _embed(self, texts: Sequence[str], kind: str = "document") -> list[list[float]] | None:
        """Gömme -- ve HER hatada ``None``.

        Gömme bir İYİLEŞTİRME. LM Studio kapalıysa, model boşaltılmışsa ya da
        uç zaman aşımına uğrarsa hafıza ÇALIŞMAYA DEVAM etmeli: sözlüksel
        aramaya düşülüyor. Hatırlamanın, başka bir programın açık olmasına
        bağlı olması kabul edilemez.
        """
        if not self._embedder or not texts:
            return None

        try:
            vectors = self._embedder(texts, kind)
        except Exception:
            return None

        if not vectors or len(vectors) != len(texts):
            return None

        return vectors

    # -- şema ---------------------------------------------------------------

    def _migrate(self) -> None:
        self._db.executescript(
            """
            PRAGMA journal_mode=WAL;

            CREATE TABLE IF NOT EXISTS memories (
                id           INTEGER PRIMARY KEY,
                text         TEXT    NOT NULL,
                kind         TEXT    NOT NULL DEFAULT 'fact',
                created_at   REAL    NOT NULL,
                importance   REAL    NOT NULL DEFAULT 0.5,
                last_recall  REAL    NOT NULL DEFAULT 0,
                recall_count INTEGER NOT NULL DEFAULT 0,
                session_id   TEXT    NOT NULL DEFAULT ''
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts
                USING fts5(text, content='memories', content_rowid='id');

            CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
                INSERT INTO memories_fts(rowid, text) VALUES (new.id, new.text);
            END;
            CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
                INSERT INTO memories_fts(memories_fts, rowid, text)
                VALUES ('delete', old.id, old.text);
            END;
            CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE OF text ON memories BEGIN
                INSERT INTO memories_fts(memories_fts, rowid, text)
                VALUES ('delete', old.id, old.text);
                INSERT INTO memories_fts(rowid, text) VALUES (new.id, new.text);
            END;

            CREATE TABLE IF NOT EXISTS meta (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            -- Gömmeler AYRI tabloda: anılar gömme olmadan da yazılabilmeli
            -- (LM Studio kapalıyken) ve sonradan doldurulabilmeli.
            CREATE TABLE IF NOT EXISTS embeddings (
                memory_id INTEGER PRIMARY KEY REFERENCES memories(id) ON DELETE CASCADE,
                dim       INTEGER NOT NULL,
                vec       BLOB    NOT NULL
            );
            """
        )
        self._db.commit()

    # -- yazma --------------------------------------------------------------

    def remember(
        self,
        text: str,
        *,
        kind: str = "fact",
        importance: float = 0.5,
        session_id: str = "",
        now: float | None = None,
    ) -> int | None:
        """Bir anı yaz. Yakın tekrar ise ``None`` döner (yeni kayıt açılmaz).

        Tekrarı engellemek şart: aynı olgu her oturumda yeniden yazılırsa depo
        aynı cümlenin kopyalarıyla dolar ve geri getirme onları üst üste
        enjekte eder -- bağlam dolar, bilgi artmaz.
        """
        clean = " ".join(text.split())

        if len(clean) < 3:
            return None

        for existing in self._recent(limit=200):
            if _similarity(existing.text, clean) >= DUPLICATE_RATIO:
                # Tekrar görülmesi ÖNEMİ artırıyor: iki kez söylenen şey daha
                # önemlidir. Metnin kendisi değişmiyor.
                self._db.execute(
                    "UPDATE memories SET importance = MIN(1.0, importance + 0.1) WHERE id = ?",
                    (existing.id,),
                )
                self._db.commit()

                return None

        cursor = self._db.execute(
            "INSERT INTO memories (text, kind, created_at, importance, session_id)"
            " VALUES (?, ?, ?, ?, ?)",
            (clean, kind, now or time.time(), max(0.0, min(1.0, importance)), session_id),
        )
        self._db.commit()

        memory_id = int(cursor.lastrowid or 0)
        vectors = self._embed([clean])

        if vectors:
            self._store_vector(memory_id, vectors[0])

        return memory_id

    def _store_vector(self, memory_id: int, vector: Sequence[float]) -> None:
        import array

        buf = array.array("f", [float(v) for v in vector])
        self._db.execute(
            "INSERT INTO embeddings (memory_id, dim, vec) VALUES (?, ?, ?)"
            " ON CONFLICT(memory_id) DO UPDATE SET dim = excluded.dim, vec = excluded.vec",
            (memory_id, len(buf), buf.tobytes()),
        )
        self._db.commit()

    def backfill_embeddings(self, limit: int = 200) -> int:
        """Gömmesi olmayan anıları doldur; kaç tanesinin dolduğunu döndür.

        LM Studio kapalıyken yazılan anılar gömmesiz kalıyor. Bu, onları
        sonradan yakalayan yol -- yoksa o anılar anlamsal aramaya sonsuza
        kadar görünmez olurdu.
        """
        rows = self._db.execute(
            "SELECT m.id, m.text FROM memories m"
            " LEFT JOIN embeddings e ON e.memory_id = m.id"
            " WHERE e.memory_id IS NULL ORDER BY m.created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()

        if not rows:
            return 0

        vectors = self._embed([str(r["text"]) for r in rows])

        if not vectors:
            return 0

        for row, vector in zip(rows, vectors):
            self._store_vector(int(row["id"]), vector)

        return len(rows)

    def _all_vectors(self, cap: int = 5000) -> tuple[list[int], object]:
        """``(kimlikler, matris)``. Matris ``None`` ise gömme yok.

        Kaba kuvvet kosinüs YETERLİ: birkaç bin anı x 768 boyut, numpy'de
        milisaniyeler. Bir vektör veritabanı burada çözdüğünden fazla sorun
        getirirdi -- yeni bir bağımlılık, yeni bir süreç, eşitlenmesi gereken
        ikinci bir hakikat.
        """
        try:
            import numpy as np
        except Exception:
            return [], None

        rows = self._db.execute(
            "SELECT e.memory_id AS id, e.dim AS dim, e.vec AS vec FROM embeddings e"
            " JOIN memories m ON m.id = e.memory_id"
            " ORDER BY m.created_at DESC LIMIT ?",
            (cap,),
        ).fetchall()

        if not rows:
            return [], None

        dim = int(rows[0]["dim"])
        ids: list[int] = []
        flat: list[float] = []

        for row in rows:
            if int(row["dim"]) != dim:
                continue

            ids.append(int(row["id"]))
            flat.extend(np.frombuffer(row["vec"], dtype="float32").tolist())

        if not ids:
            return [], None

        matrix = np.asarray(flat, dtype="float32").reshape(len(ids), dim)
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1.0

        return ids, matrix / norms

    def forget(self, memory_id: int) -> bool:
        cursor = self._db.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
        self._db.commit()

        return cursor.rowcount > 0

    # -- okuma --------------------------------------------------------------

    def _recent(self, limit: int = 50) -> list[Memory]:
        rows = self._db.execute(
            "SELECT * FROM memories ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()

        return [_row_to_memory(r) for r in rows]

    def count(self) -> int:
        row = self._db.execute("SELECT COUNT(*) AS n FROM memories").fetchone()

        return int(row["n"]) if row else 0

    def all_texts(self, limit: int = 400) -> list[str]:
        """Bilinenlerin METNİ -- "neyi bilmiyorum" sorusu için.

        Arama DEĞİL, kapsam sorusu: geri getirme "bu turda ne gerekiyor" diye
        sorarken burası "bu konu hiç geçti mi" diye soruyor ve ikisinin doğru
        cevabı farklı. Bir sorgu yok, çünkü aranan şey de yok.

        Sınır var çünkü bu her oturum açılışında bir kez okunuyor ve binlerce
        anıyı belleğe almanın karşılığı yok: kapsanmamış bir konu, ilk birkaç
        yüz anıda da kapsanmamış olacak.
        """
        rows = self._db.execute(
            "SELECT text FROM memories ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()

        return [str(r["text"]) for r in rows]

    def search(
        self,
        query: str,
        *,
        limit: int = 8,
        now: float | None = None,
    ) -> list[tuple[Memory, float]]:
        """İlgili anılar, puanlarıyla; en iyisi başta.

        Puan üç bileşenin ÇARPIMI değil TOPLAMI: çarpımda bir bileşen sıfıra
        yaklaşınca diğerlerini yok sayardı -- çok eski ama tam isabet bir anı
        böyle kaybolurdu, ki hatırlamanın en değerli hâli tam olarak odur.
        """
        now = now or time.time()
        relevance: dict[int, float] = {}

        # -- ANLAMSAL: sözcükler tutmasa da anlam tutar.
        #
        # Sözlüksel arama tek başına bu iş için yetmiyor ve sebebi ölçüldü:
        # "what music does he like" sorgusu "User loves the band Radiohead"
        # kaydıyla TEK BİR sözcük paylaşmıyor, yani FTS boş dönüyor ve sıralama
        # saf tazeliğe düşüyordu -- kullanıcının sorduğu şey üçüncü sırada
        # kalıyordu. Gömmeyle aynı çift 0,52 benzerlik veriyor; alakasız çift
        # 0,39.
        for memory_id, score in self._semantic_scores(query).items():
            relevance[memory_id] = score

        # -- SÖZLÜKSEL: özel adlar, kodlar, tam alıntılar.
        #
        # Gömme bunlarda zayıf: "Radiohead" ile "Coldplay" anlamca yakın ama
        # kullanıcı BİRİNİ söyledi. İkisi birbirini tamamlıyor.
        for memory_id, score in self._lexical_scores(query, limit * 6).items():
            relevance[memory_id] = max(relevance.get(memory_id, 0.0), score * 0.9)

        pool = self._by_ids(list(relevance)) if relevance else []

        if not pool:
            # Hiçbir şey eşleşmedi: en taze ve önemli olanları ver. Bir şey
            # göstermek hiçbir şey göstermemekten iyi.
            pool = self._recent(limit=limit * 3)

        scored = [(m, self._score(m, relevance.get(m.id, 0.0), now)) for m in pool]
        scored.sort(key=lambda pair: pair[1], reverse=True)

        return scored[:limit]

    def _semantic_scores(self, query: str) -> dict[int, float]:
        vectors = self._embed([query], "query")

        if not vectors:
            return {}

        ids, matrix = self._all_vectors()

        if matrix is None or not ids:
            return {}

        import numpy as np

        q = np.asarray(vectors[0], dtype="float32")
        norm = float(np.linalg.norm(q)) or 1.0
        sims = matrix @ (q / norm)

        # Kosinüs değerleri dar bir bantta toplanıyor (0,3-0,7): ham hâlde
        # aralarındaki fark sıralamayı taşımıyor. Aday kümesi içinde
        # gerilerek en iyi eşleşme 1,0 oluyor -- sözlüksel puanda da aynı
        # gerekçeyle aynı şey yapılıyor.
        raw = {mid: float(max(0.0, value)) for mid, value in zip(ids, sims)}

        if not raw:
            return {}

        top = max(raw.values())
        floor = min(raw.values())
        span = top - floor

        if span <= 1e-6:
            return {mid: 0.0 for mid in raw}

        return {mid: (value - floor) / span for mid, value in raw.items()}

    def _lexical_scores(self, query: str, cap: int) -> dict[int, float]:
        clause = _fts_query(query)

        if not clause:
            return {}

        try:
            rows = self._db.execute(
                "SELECT memories_fts.rowid AS id, bm25(memories_fts) AS rank FROM memories_fts"
                " WHERE memories_fts MATCH ? ORDER BY rank LIMIT ?",
                (clause, cap),
            ).fetchall()
        except sqlite3.OperationalError:
            return {}

        if not rows:
            return {}

        # bm25 negatif ve daha DÜŞÜKSE daha iyi. En iyisi 1.0 olacak şekilde
        # ölçekleniyor -- ham değeri kullanmak, ilgiyi tazeliğin altında
        # bırakıyordu.
        raw = {int(r["id"]): -float(r["rank"]) for r in rows}
        best = max(raw.values()) or 1.0

        return {mid: max(0.0, value) / best for mid, value in raw.items()}

    def _by_ids(self, ids: list[int]) -> list[Memory]:
        if not ids:
            return []

        marks = ",".join("?" for _ in ids)
        rows = self._db.execute(
            "SELECT * FROM memories WHERE id IN (" + marks + ")", ids
        ).fetchall()

        return [_row_to_memory(r) for r in rows]

    def _score(self, memory: Memory, relevance: float, now: float) -> float:
        """İLGİ baskın, tazelik ve önem ayarlayıcı.

        Ağırlıklar ölçümle düzeltildi: ilk hâlde ilgi 1,0 / tazelik 0,6 /
        önem 0,5 idi ve tam isabet bir anı, alakasız ama taze bir anının
        arkasında kalıyordu. Hatırlamanın değeri tam olarak o durumda --
        eskiyi doğru anda geri getirmekte.

        Düzeltmeler AYRI tutuluyor (bkz. ``CORRECTION_BONUS``): bir düzeltme,
        aynı ilgideki sıradan bir anıyla yer değiştirdiğinde sonuç yalnızca
        "bir şey hatırlamamak" değil, AYNI HATAYI TEKRARLAMAK oluyor.
        """
        recency = 0.5 ** (memory.age_days(now) / RECENCY_HALF_LIFE_DAYS)
        unseen = UNSEEN_BONUS if memory.recall_count == 0 else 0.0
        corrected = CORRECTION_BONUS if memory.kind == "correction" else 0.0

        return relevance * 3.0 + recency * 0.5 + memory.importance * 0.4 + unseen + corrected

    def mark_recalled(self, ids: Iterable[int], *, now: float | None = None) -> None:
        listed = list(ids)

        if not listed:
            return

        self._db.executemany(
            "UPDATE memories SET recall_count = recall_count + 1, last_recall = ? WHERE id = ?",
            [(now or time.time(), i) for i in listed],
        )
        self._db.commit()

    # -- bağlama giren blok -------------------------------------------------

    def context_block(
        self,
        query: str,
        *,
        budget: int = DEFAULT_CHAR_BUDGET,
        limit: int = 8,
        now: float | None = None,
    ) -> tuple[str, list[int]]:
        """Enjekte edilecek metin ve kullanılan anıların kimlikleri.

        Bütçe KARAKTER cinsinden: token sayısı modele göre değişir, karakter
        değişmez -- ``memory_tool`` da aynı gerekçeyle karakter kullanıyor.
        """
        now = now or time.time()
        hits = self.search(query, limit=limit, now=now)

        if not hits:
            return "", []

        lines: list[str] = []
        used: list[int] = []
        chosen: list[str] = []
        spent = 0

        for memory, _score in hits:
            # Zaten seçilmiş bir satırın AYNISINI söylüyorsa atlanıyor.
            #
            # Puanı yüksek olması onu yeni yapmıyor: "kedisinin adı Pamuk" üç
            # kez farklı sözcüklerle söylenmişse üçü de aynı sorguda üste
            # çıkıyor ve bütçenin tamamı tek olguya gidiyor.
            if any(_similarity(existing, memory.text) >= REDUNDANT_RATIO for existing in chosen):
                continue

            line = "- (" + _ago(memory.created_at, now) + ") " + memory.text

            if spent + len(line) + 1 > budget:
                # ``break`` DEĞİL: uzun bir anı sırada öndeyse, arkasındaki
                # kısa ve sığacak olanları da birlikte götürürdü. Sıra
                # korunuyor, yalnızca sığmayan atlanıyor -- aynı bütçeye daha
                # çok anı giriyor.
                continue

            lines.append(line)
            used.append(memory.id)
            chosen.append(memory.text)
            spent += len(line) + 1

        if not lines:
            return "", []

        return "\n".join(lines), used

    # -- zaman farkındalığı -------------------------------------------------

    def touch_seen(self, *, now: float | None = None) -> None:
        """Kullanıcıyı ŞİMDİ gördük."""
        self._set_meta("last_seen", repr(now or time.time()))

    def last_seen(self) -> float | None:
        return self._get_float("last_seen")

    def mark_farewell(self, *, now: float | None = None) -> None:
        """VEDALAŞILDI.

        Ayrı bir damga, çünkü aradan geçen süre bunu taşımıyor: sekiz saatlik
        bir boşluk, "iyi geceler deyip yattı" ile "ortadan kayboldu" arasında
        hiçbir fark görmüyor (gerekçe ``fool/time_context.py``de).
        """
        self._set_meta("last_farewell", repr(now or time.time()))

    def last_farewell(self) -> float | None:
        return self._get_float("last_farewell")

    # -- sorulmuş konular ---------------------------------------------------

    def asked_topics(self) -> list[str]:
        """Bu profilde daha önce sorulmuş tanışma konuları."""
        import json

        raw = self._get_meta("asked_topics")

        if not raw:
            return []

        try:
            payload = json.loads(raw)
        except ValueError:
            return []

        return [str(item) for item in payload] if isinstance(payload, list) else []

    def mark_topic_asked(self, topic_id: str) -> None:
        """Konu SORULDU -- cevap gelse de gelmese de.

        Cevabı beklemek yerine sorulmayı kaydetmenin sebebi: cevap vermemek de
        bir cevap. Aynı soruyu üçüncü kez sormak, dinlemediğini göstermenin en
        hızlı yolu.
        """
        import json

        asked = self.asked_topics()

        if topic_id in asked:
            return

        asked.append(topic_id)
        self._set_meta("asked_topics", json.dumps(asked, ensure_ascii=False))

    # -- ilişki durumu ------------------------------------------------------

    def load_relationship(self) -> dict | None:
        """Kayıtlı ilişki durumu (``None`` = hiç yok)."""
        import json

        raw = self._get_meta("relationship")

        if not raw:
            return None

        try:
            payload = json.loads(raw)
        except ValueError:
            return None

        return payload if isinstance(payload, dict) else None

    def save_relationship(self, payload: dict) -> None:
        import json

        self._set_meta("relationship", json.dumps(payload, ensure_ascii=False))

    def _get_float(self, key: str) -> float | None:
        raw = self._get_meta(key)

        try:
            return float(raw) if raw else None
        except ValueError:
            return None

    def _get_meta(self, key: str) -> str | None:
        row = self._db.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()

        return row["value"] if row else None

    def _set_meta(self, key: str, value: str) -> None:
        self._db.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?)"
            " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        self._db.commit()

    def close(self) -> None:
        self._db.close()


def _row_to_memory(row: sqlite3.Row) -> Memory:
    return Memory(
        id=int(row["id"]),
        text=str(row["text"]),
        kind=str(row["kind"]),
        created_at=float(row["created_at"]),
        importance=float(row["importance"]),
        recall_count=int(row["recall_count"]),
    )


def _ago(then: float, now: float) -> str:
    """İnsan ölçeğinde "ne kadar önce"."""
    seconds = max(0.0, now - then)

    if seconds < 300:
        return "just now"

    if seconds < 3600:
        return str(int(seconds // 60)) + "m ago"

    hours = seconds / 3600

    if hours < 24:
        return str(int(hours)) + "h ago"

    days = hours / 24

    if days < 2:
        return "yesterday"

    if days < 7:
        return str(int(days)) + "d ago"

    if days < 30:
        return str(int(days // 7)) + "w ago"

    return str(int(days // 30)) + "mo ago"
