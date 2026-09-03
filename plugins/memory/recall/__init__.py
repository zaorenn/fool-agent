"""Recall: ölçeklenen, anlamsal, zamanın farkında hafıza.

Ne yapıyor
----------
Yerleşik hafıza (``tools/memory_tool.py``) küçük ve bilinçli öyle: 2200 + 1375
karakter, sistem promptuna donmuş bir anlık görüntü olarak giriyor ve önek
önbelleğini koruyor. Bu sağlayıcı ONUN YERİNE GEÇMİYOR -- altına bir katman
koyuyor:

- **Depo büyür, bağlam küçük kalır.** Anılar SQLite'ta birikiyor; her turda
  yalnızca o an ilgili olan birkaçı, karakter bütçesi altında enjekte ediliyor.
- **Geri getirme anlamsal.** Sözlüksel arama tek başına ölçülebilir biçimde
  yetmiyor (gerekçe ``fool/recall_store.py``).
- **Zamanın farkında.** Günün saati, aradan geçen süre ve önceki oturumun
  vedasız bitip bitmediği modele hazır bir cümle olarak gidiyor
  (``fool/time_context.py``).

Neden yerleşik hafızayla ÇAKIŞMIYOR
-----------------------------------
İkisi farklı sorulara cevap veriyor. ``MEMORY.md``/``USER.md`` KÜRE EDİLMİŞ ve
kalıcı: "bu kullanıcı kısa cevap sever". Burası OLAYSAL: "salı günü sesin
çalışmamasına sinirlenmişti". Birincisi her turda gerekli, ikincisi yalnızca
konu açıldığında.

İki BAĞIMSIZ hafıza
-------------------
Depo ``FOOL_HOME/memories/recall.db``. Profil arka ucu kendi FOOL_HOME'uyla
koşuyor, yani ``persona`` profilinin hafızası normal ajanınkinden fiziksel
olarak ayrı. Ek mekanizma yok.

Zone A: upstream bu dosyayı bilmiyor.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any, Dict, List, Optional

from agent.memory_provider import MemoryProvider, RecallStatus

logger = logging.getLogger(__name__)

#: Bir turdan sonra kaç anı geri getirilsin.
DEFAULT_RECALL_LIMIT = 6

#: Gömme ucu için zaman aşımı. Kısa: hafıza bir İYİLEŞTİRME ve turu
#: bekletmemeli. Süre dolarsa sözlüksel aramaya düşülüyor.
EMBED_TIMEOUT_SECONDS = 8.0

#: nomic-embed-text görev önekleri. Öneksiz benzerlikler birbirine yapışıyor --
#: ölçüldü, ilgili ve ilgisiz çiftler 0,39-0,52 aralığına sıkışıyor.
_PREFIX = {"query": "search_query: ", "document": "search_document: "}


def _config() -> Dict[str, Any]:
    try:
        from fool_cli.config import load_config

        return (load_config() or {}).get("memory") or {}
    except Exception:
        return {}


def _recall_config() -> Dict[str, Any]:
    section = _config().get("recall")

    return section if isinstance(section, dict) else {}


def _voice_in_use() -> bool:
    """Bu profilde gerçekten seslendirme yapılıyor mu?

    Sentez yolunun kendi çözücüsüne soruyor (``tools/tts_tool.py``): seçim
    yokken kurulu yerel bir motora düşüyor ve hiçbiri yoksa ``none`` dönüyor.
    Yapılandırmaya doğrudan bakmak, motoru kurulu olmayan bir kullanıcıya
    etiket sözlüğü vermek olurdu.

    Okunamazsa ``False``: ipucu bir iyileştirme, ve emin olmadan prompta
    satır eklemek onu her kullanıcı için pahalı yapardı.
    """
    try:
        from tools.tts_tool import _get_provider

        section = _config().get("tts")
        resolved = _get_provider(section if isinstance(section, dict) else {})

        return bool(resolved) and str(resolved).strip().lower() != "none"
    except Exception:  # noqa: BLE001
        return False


def _db_path() -> str:
    from pathlib import Path

    from fool_constants import get_hermes_home

    return str(Path(get_hermes_home()) / "memories" / "recall.db")


def _make_embedder():
    """LM Studio (ya da uyumlu) gömme ucu. Yoksa ``None``.

    Yeni bir model indirmiyor: kullanıcının zaten çalıştırdığı uca soruyor.
    Uç yoksa sağlayıcı sözlüksel aramayla çalışmaya devam ediyor.
    """
    cfg = _recall_config()
    model = str(cfg.get("embed_model") or "text-embedding-nomic-embed-text-v1.5").strip()

    if not model or model.lower() == "none":
        return None

    base = str(cfg.get("embed_base_url") or "").strip()

    if not base:
        try:
            from fool_cli.config import load_config

            model_cfg = (load_config() or {}).get("model") or {}
            base = str(model_cfg.get("base_url") or "http://localhost:1234/v1").strip()
        except Exception:
            base = "http://localhost:1234/v1"

    url = base.rstrip("/") + "/embeddings"

    def embed(texts, kind: str = "document"):
        import urllib.request

        prefix = _PREFIX.get(kind, _PREFIX["document"])
        body = json.dumps(
            {"model": model, "input": [prefix + str(t) for t in texts]}
        ).encode("utf-8")
        request = urllib.request.Request(
            url, data=body, headers={"Content-Type": "application/json"}
        )

        with urllib.request.urlopen(request, timeout=EMBED_TIMEOUT_SECONDS) as response:
            payload = json.load(response)

        return [item["embedding"] for item in payload["data"]]

    return embed


class RecallMemoryProvider(MemoryProvider):
    """Olaysal hafıza sağlayıcısı."""

    def __init__(self) -> None:
        self._store = None
        self._session_id = ""
        self._last_count = 0
        self._lock = threading.Lock()
        self._pending: List[tuple] = []
        self._relationship = None

    # -- ilişki durumu ------------------------------------------------------

    def _relationship_enabled(self) -> bool:
        """``memory.recall.relationship`` -- varsayılan KAPALI.

        Normal ajanın bir "ilişki durumu" yok: kod yazarken kırılmıyor,
        soğumuyor, gönlü alınmıyor. Bu, bir persona özelliği ve yalnızca onu
        isteyen profilde açılıyor.
        """
        return bool(_recall_config().get("relationship"))

    def _load_relationship(self):
        if self._relationship is not None or self._store is None:
            return self._relationship

        from fool import relationship as relationship_module

        self._relationship = relationship_module.from_dict(self._store.load_relationship())

        return self._relationship

    def _save_relationship(self) -> None:
        if self._store is None or self._relationship is None:
            return

        from fool import relationship as relationship_module

        self._store.save_relationship(relationship_module.to_dict(self._relationship))

    def relationship_snapshot(self) -> Dict[str, Any]:
        """Arayüzün göstereceği hâl -- neye kırgın, ne kadar yakın.

        Kullanıcının istediği "ilişki barı" bunu okuyor. Modelden bağımsız:
        ekranda görünen şey, modelin o an ne söylediğine değil defterin
        kendisine bakıyor.
        """
        state = self._load_relationship()

        if state is None:
            return {}

        state.decay(time.time())
        name, _description = state.stance()

        return {
            "warmth": round(state.warmth, 1),
            "stance": name,
            "grievances": [
                {"text": g.text, "since": g.created_at} for g in state.open_grievances()
            ],
        }

    # -- kimlik -------------------------------------------------------------

    @property
    def name(self) -> str:
        return "recall"

    def is_available(self) -> bool:
        # Yerel ve bağımlılıksız: sqlite her zaman var. Gömme ucu yoksa
        # sözlüksel aramayla çalışıyor, yani "kullanılamaz" değil.
        return True

    def unavailable_reason(self) -> str:
        return ""

    def initialize(self, session_id: str, **kwargs) -> None:
        self._session_id = session_id or ""

        if self._store is not None:
            return

        try:
            from fool.recall_store import RecallStore

            self._store = RecallStore(_db_path(), embedder=_make_embedder())
        except Exception as exc:  # pragma: no cover -- kurulum hatası
            logger.warning("[recall] store unavailable: %s", exc)
            self._store = None

    # -- sistem promptu -----------------------------------------------------

    def system_prompt_block(self) -> str:
        """Zaman bağlamı + hafızanın nasıl kullanılacağı.

        Zaman bağlamı BURADA, ``prefetch``te değil: her turda değişmiyor ve
        oturum boyunca sabit kalması önek önbelleğini koruyor.
        """
        if self._store is None:
            return ""

        try:
            from fool import time_context

            now = time.time()
            context = time_context.build(
                now=now,
                last_seen=self._store.last_seen(),
                last_farewell=self._store.last_farewell(),
            )
            # Bu turdan itibaren "görüldü" -- bir sonraki oturum aradaki boşluğu
            # buradan hesaplayacak.
            self._store.touch_seen(now=now)
        except Exception:
            return ""

        lines = [context.render()]

        if self._store.count():
            lines.append(
                "You remember earlier conversations. Relevant memories are supplied "
                "each turn; use them naturally rather than announcing them."
            )

        lines.append(
            "Use remember() for anything worth carrying into future conversations, "
            "and recall() to look something up you were not given."
        )

        curiosity = self._curiosity_line()

        if curiosity:
            lines.append("")
            lines.append(curiosity)

        # Teslimat etiketleri SESE bağlı, personaya değil.
        #
        # Önce bu ipucu ilişki bloğunun içindeydi ve gerekçesi "sıradan ajanın
        # cevabı okunuyor, seslendirilmiyor" idi. Yanlıştı: sesli sohbet ve
        # çentik sıradan ajanla da kullanılıyor, yani orada da her cevap
        # seslendiriliyor -- ve o ajan tonunu hiç değiştiremiyordu.
        #
        # Doğru koşul "bu bir persona mı" değil, "ses gerçekten kullanılıyor
        # mu". Motor yoksa ipucu promptu bedelsiz şişirirdi; varsa ton kontrolü
        # kimin konuştuğundan bağımsız olarak işe yarıyor.
        if _voice_in_use():
            try:
                from fool.voice_emotion import prompt_hint

                lines.append("")
                lines.append(prompt_hint())
            except Exception:  # noqa: BLE001
                pass

        if self._relationship_enabled():
            state = self._load_relationship()

            if state is not None:
                state.decay(now)
                self._save_relationship()

                # Duruş yalnızca ARANIZDA BİR ŞEY GEÇTİYSE gösteriliyor.
                #
                # Hiçbir olay kaydedilmemişken sıcaklık başlangıç değerinde
                # duruyor ve o değerin tarifi ("civil but not especially warm")
                # persona ile ÇELİŞİYOR: sevgi dolu diye tanımlanmış bir
                # karaktere ilk karşılaşmada mesafeli olmasını söylüyordu.
                #
                # "Nerede durduğun" aranızda bir şey geçmeden anlamsız. Geçtiği
                # anda anlamlı hâle geliyor ve o zaman personayı EZMESİ de
                # doğru -- kırgınlık karakterin üstünde.
                if state.updated_at or state.grievances:
                    lines.append("")
                    lines.append("Where you stand with them right now:")
                    lines.append(state.render())
                    lines.append(
                        "Report how they treated you with relationship() so this keeps "
                        "meaning something. Do not narrate the mechanism."
                    )
                else:
                    lines.append("")
                    lines.append(
                        "Nothing has happened between you yet. Report how they treat "
                        "you with relationship() as it does."
                    )


        return "\n".join(line for line in lines if line is not None)

    def _curiosity_line(self) -> str:
        """Bu oturumda sorulacak TEK konu (yoksa boş).

        Sorulan konu HEMEN işaretleniyor, cevap beklenmeden. Cevabı beklemek
        için turu izlemek gerekirdi ve o izleme yanlış cevap verdiğinde sonuç,
        aynı soruyu tekrar tekrar sormak olurdu -- yardımcının dinlemediğini
        gösteren tek şey. Cevap gelirse zaten ``remember()`` ile yazılıyor ve
        konu kapsanmış oluyor; gelmezse soru bir kez sorulmuş ve bırakılmış
        oluyor. İkisi de doğru.
        """
        if self._store is None or not bool(_recall_config().get("curiosity", True)):
            return ""

        try:
            from fool import curiosity

            asked = set(self._store.asked_topics())
            topic = curiosity.next_topic(
                self._store.all_texts(),
                companion=self._relationship_enabled(),
                asked=asked,
            )

            if topic is None:
                return ""

            self._store.mark_topic_asked(topic.id)

            return curiosity.prompt_line(topic)
        except Exception as exc:  # noqa: BLE001
            logger.debug("[recall] curiosity unavailable: %s", exc)

            return ""

    # -- tur başına geri getirme -------------------------------------------

    def prefetch(self, query: str, *, session_id: str = "") -> str:
        if self._store is None or not query.strip():
            self._last_count = 0

            return ""

        try:
            budget = int(_recall_config().get("char_budget") or 0) or None
            limit = int(_recall_config().get("recall_limit") or DEFAULT_RECALL_LIMIT)
            kwargs: Dict[str, Any] = {"limit": limit}

            if budget:
                kwargs["budget"] = budget

            block, ids = self._store.context_block(query, **kwargs)
        except Exception as exc:
            logger.debug("[recall] prefetch failed: %s", exc)
            self._last_count = 0

            return ""

        self._last_count = len(ids)

        if not block:
            return ""

        self._store.mark_recalled(ids)

        return "What you remember about them:\n" + block

    def recall_status(self) -> Optional[RecallStatus]:
        if not self._last_count:
            return None

        return RecallStatus(provider_label="recall", count=self._last_count)

    # -- kayıt --------------------------------------------------------------

    def sync_turn(
        self,
        user_content: str,
        assistant_content: str,
        *,
        session_id: str = "",
        messages: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """Turu KAYDETMİYOR -- ham konuşmayı biriktirmek hafıza değil, kütük.

        Anı yazmak bir YARGI: neyin taşınmaya değer olduğunu model biliyor,
        kod bilmiyor. O yüzden yazma yolu ``remember()`` aracı. Burada yalnızca
        vedanın kaydı tutuluyor, çünkü onu turun metninden anlamak mümkün.
        """
        if self._store is None:
            return

        if _looks_like_farewell(user_content):
            self._store.mark_farewell()

    def on_session_end(self, messages: List[Dict[str, Any]]) -> None:
        if self._store is None:
            return

        try:
            # Oturum bitti: gömmesi olmayan anılar varsa (LM Studio o sırada
            # kapalıydı) burada yakalanıyor -- yoksa anlamsal aramaya sonsuza
            # kadar görünmez kalırlardı.
            self._store.backfill_embeddings()
        except Exception:
            pass

    # -- araçlar ------------------------------------------------------------

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        schemas = self._memory_tool_schemas()

        if self._relationship_enabled():
            schemas.append(
                {
                    "name": "relationship",
                    "description": (
                        "Record how they just treated you, so it carries past this "
                        "turn. Judge it yourself -- tone, context, whether it was a "
                        "joke. Use 'apology' when they genuinely make something right; "
                        "it clears the heaviest thing between you, not all of it. Give "
                        "a note for anything negative: an unnamed grievance cannot be "
                        "brought up later. Do not call this every turn -- only when "
                        "something actually happened."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "event": {
                                "type": "string",
                                "enum": [
                                    "affectionate",
                                    "warm",
                                    "attentive",
                                    "promise_kept",
                                    "apology",
                                    "neutral",
                                    "dismissive",
                                    "rude",
                                    "cruel",
                                    "promise_broken",
                                    "ignored",
                                ],
                            },
                            "note": {
                                "type": "string",
                                "description": (
                                    "For negative events: what happened, in one short "
                                    "line you would be willing to say out loud later."
                                ),
                            },
                            "weight": {
                                "type": "number",
                                "description": "0.1-3.0, how much it mattered. Default 1.",
                            },
                        },
                        "required": ["event"],
                    },
                }
            )

        return schemas

    def _memory_tool_schemas(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "remember",
                "description": (
                    "Store something worth carrying into future conversations: a fact "
                    "about them, a preference, a promise you made, something that "
                    "happened between you, or a correction when they tell you that you "
                    "had something wrong. Write it as a complete sentence that will "
                    "still make sense months from now, with no pronouns whose referent "
                    "is only in this conversation. Do not store passing chatter, and do "
                    "not store the same thing twice -- near-duplicates are rejected."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "text": {
                            "type": "string",
                            "description": "The memory, self-contained and in the third person.",
                        },
                        "importance": {
                            "type": "number",
                            "description": (
                                "0.0-1.0. Above 0.7 for things that shape how you treat "
                                "them; below 0.3 for small colour."
                            ),
                        },
                        "kind": {
                            "type": "string",
                            "enum": ["fact", "preference", "event", "promise", "correction"],
                            "description": (
                                "Use 'correction' when they told you that something you "
                                "said or assumed was wrong. Write it so the mistake "
                                "cannot recur: what is actually true, and what you had "
                                "wrong. These outrank other memories when they are "
                                "relevant."
                            ),
                        },
                    },
                    "required": ["text"],
                },
            },
            {
                "name": "recall",
                "description": (
                    "Search your memory of them. Use this when they refer to something "
                    "you were not given this turn, or when you want to check what you "
                    "already know before asking."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "What to look for."},
                        "limit": {"type": "integer", "description": "How many (default 6)."},
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "forget",
                "description": (
                    "Delete a memory by its id, shown in recall() results. Use when they "
                    "ask you to forget something, or when a memory turned out to be wrong."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {"id": {"type": "integer"}},
                    "required": ["id"],
                },
            },
        ]

    def handle_tool_call(self, tool_name: str, args: Dict[str, Any], **kwargs) -> str:
        if self._store is None:
            return json.dumps({"ok": False, "error": "memory store unavailable"})

        try:
            if tool_name == "remember":
                return self._do_remember(args)

            if tool_name == "recall":
                return self._do_recall(args)

            if tool_name == "forget":
                removed = self._store.forget(int(args.get("id") or 0))

                return json.dumps({"ok": bool(removed)})

            if tool_name == "relationship":
                return self._do_relationship(args)
        except Exception as exc:
            return json.dumps({"ok": False, "error": str(exc)})

        return json.dumps({"ok": False, "error": "unknown tool " + str(tool_name)})

    def _do_remember(self, args: Dict[str, Any]) -> str:
        text = str(args.get("text") or "").strip()

        if not text:
            return json.dumps({"ok": False, "error": "text is required"})

        memory_id = self._store.remember(
            text,
            kind=str(args.get("kind") or "fact"),
            importance=float(args.get("importance", 0.5)),
            session_id=self._session_id,
        )

        if memory_id is None:
            # Sessizce basarili demek yaniltici olurdu: model ayni seyi tekrar
            # tekrar yazmayi surdurur.
            return json.dumps({"ok": True, "stored": False, "reason": "already known"})

        return json.dumps({"ok": True, "stored": True, "id": memory_id})

    def _do_relationship(self, args: Dict[str, Any]) -> str:
        if not self._relationship_enabled():
            return json.dumps({"ok": False, "error": "relationship tracking is off"})

        state = self._load_relationship()

        if state is None:
            return json.dumps({"ok": False, "error": "relationship unavailable"})

        from fool.relationship import EVENT_WARMTH

        event = str(args.get("event") or "").strip()

        if event not in EVENT_WARMTH:
            return json.dumps({"ok": False, "error": "unknown event " + event})

        state.record(
            event,
            note=str(args.get("note") or ""),
            weight=float(args.get("weight", 1.0)),
        )
        self._save_relationship()

        name, _description = state.stance()

        return json.dumps(
            {
                "ok": True,
                "stance": name,
                "warmth": round(state.warmth, 1),
                "open_grievances": len(state.open_grievances()),
            }
        )

    def _do_recall(self, args: Dict[str, Any]) -> str:
        query = str(args.get("query") or "").strip()
        limit = int(args.get("limit") or DEFAULT_RECALL_LIMIT)
        hits = self._store.search(query, limit=limit)

        if not hits:
            return json.dumps({"ok": True, "memories": []})

        self._store.mark_recalled([m.id for m, _ in hits])
        now = time.time()

        return json.dumps(
            {
                "ok": True,
                "memories": [
                    {
                        "id": memory.id,
                        "text": memory.text,
                        "kind": memory.kind,
                        "days_ago": round(memory.age_days(now), 1),
                    }
                    for memory, _score in hits
                ],
            }
        )

    # -- yapılandırma -------------------------------------------------------

    def get_config_schema(self) -> List[Dict[str, Any]]:
        return [
            {
                "key": "embed_model",
                "description": (
                    "Embedding model for semantic recall, served by your local endpoint. "
                    "Set to 'none' to use keyword search only."
                ),
                "default": "text-embedding-nomic-embed-text-v1.5",
            },
            {
                "key": "embed_base_url",
                "description": "OpenAI-compatible base URL. Blank follows model.base_url.",
                "default": "",
            },
            {
                "key": "char_budget",
                "description": (
                    "Characters of recalled memory injected per turn. 1500 suits a 32k "
                    "context; 3000 is comfortable at 64k."
                ),
                "type": "integer",
                "default": 1500,
                "minimum": 200,
                "maximum": 8000,
            },
            {
                "key": "recall_limit",
                "description": "How many memories to consider per turn.",
                "type": "integer",
                "default": DEFAULT_RECALL_LIMIT,
                "minimum": 1,
                "maximum": 30,
            },
        ]

    def save_config(self, values: Dict[str, Any], hermes_home: str) -> None:
        from fool_cli.config import set_config_value

        for key, value in (values or {}).items():
            set_config_value("memory.recall." + str(key), str(value), force=True)

    def shutdown(self) -> None:
        store, self._store = self._store, None

        if store is not None:
            try:
                store.close()
            except Exception:
                pass


#: Veda sayılan kapanışlar. Liste DAR tutuluyor: "night" tek başına ("last
#: night", "night shift") veda değil, ve yanlış pozitif bir veda, ertesi sabah
#: hak edilmiş bir sitemi yutardı.
_FAREWELLS = (
    "good night",
    "goodnight",
    "gute nacht",
    "iyi geceler",
    "goodbye",
    "good bye",
    "bye for now",
    "talk to you tomorrow",
    "talk tomorrow",
    "see you tomorrow",
    "going to bed",
    "off to bed",
    "heading to bed",
    "gorusuruz",
    "hosca kal",
    "kendine iyi bak",
)


def _looks_like_farewell(text: str) -> bool:
    lowered = " " + " ".join(str(text or "").lower().split()) + " "

    return any(phrase in lowered for phrase in _FAREWELLS)
