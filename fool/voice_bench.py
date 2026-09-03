"""Hangi seslendirme motoru GERÇEKTEN ne kadar sürüyor.

Neden ölçüldü
-------------
CODEX görev tanımı Chatterbox'ı "28 sn, difüzyon tabanlı, hızlandırılabilir
mi araştır" diye işaretliyor. Araştırmanın cevabı ölçümde çıktı ve beklenen
yerde değildi (bu makine, RTX 4070 Ti SUPER, kısa cümle, saniye):

    motor            ilk      2.       3.
    piper           3,10    0,11    0,11
    kokoro          7,69    0,14    0,14
    chatterbox     14,64    1,94    1,74
    qwen3-tts      36,75   15,38    9,26

Belgelenen tabloyla karşılaştırma:

    Chatterbox   58 / 28   ->  14,64 / 1,74    ~16x daha hızlı
    Kokoro      7,6 / 0,08 ->   7,69 / 0,14    aynı
    Qwen3-TTS  18,4 / 6,0  ->  36,75 / 9,26    DAHA YAVAŞ

Yani Chatterbox sorunu kalıcı-süreç değişikliğiyle zaten çözülmüş; belgedeki
28 saniye eskimiş. Asıl sorun başka yerde: kullanıcının SEÇİLİ motoru
(qwen3) kurulu en hızlısından ~70 kat yavaş. Sesli sohbette her cümle için
9-15 saniye demek -- yaptığım bütün gecikme düzeltmelerinin toplamından daha
büyük bir maliyet ve hiçbir yerde görünmüyor.

Bu modül ölçümü kalıcı hale getiriyor ve ``fool doctor``ın "seçtiğin motor
kurulu bir alternatiften çok daha yavaş" diyebilmesini sağlıyor.
"""

from __future__ import annotations

import json
from typing import Any

#: Seçili motor, kurulu en hızlısından bu kat daha yavaşsa uyarılıyor.
#:
#: 3x bilinçli olarak yüksek: kullanıcı ses kalitesi için gecikmeyi göze almış
#: olabilir ve her küçük farkta uyarmak gürültü olurdu. 0,14 sn'ye karşı
#: 9,26 sn gibi bir fark (66x) bilinçli tercih değil, fark edilmemiş bir
#: durumdur.
SLOW_FACTOR = 3.0

#: Bu sürenin altındaki motorlar arasında karşılaştırma yapılmıyor: 0,11 ile
#: 0,14 arasındaki fark kulakla duyulmuyor ve ölçüm gürültüsü içinde.
FAST_ENOUGH_MS = 500


def results_path():
    from pathlib import Path

    from fool_cli.config import get_hermes_home

    return Path(get_hermes_home()) / "voice-bench.json"


def load_results() -> dict:
    try:
        with open(results_path(), encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def save_result(entry_id: str, elapsed_ms: int) -> None:
    """Bir motorun ölçülen gecikmesini sakla.

    ISINMIS ölçüm saklanıyor, ilk çağrı değil: ilk çağrı model yüklemesi ve
    kullanıcı onu oturum başına bir kez ödüyor. Karşılaştırmayı ilk çağrıya
    dayandırmak, her seferinde yanlış motoru "hızlı" gösterirdi.
    """
    data = load_results()
    data[str(entry_id)] = {"elapsed_ms": int(elapsed_ms)}

    path = results_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)


def is_measured(selected: str, results: Any) -> bool:
    """Seçili motorun ölçümü VAR mı?

    Ayrı bir soru olması gerekiyor: ölçüm yokken ``faster_alternative``
    ``None`` döner ve çağıran taraf bunu "sorun yok" sanıyordu. "Ölçülmedi"
    ile "ölçüldü, iyi" farklı şeyler ve kullanıcıya farklı gösterilmeli.
    """
    if not isinstance(results, dict):
        return False
    row = results.get(str(selected))
    if not isinstance(row, dict):
        return False
    try:
        return int(row.get("elapsed_ms") or 0) > 0
    except (TypeError, ValueError):
        return False


#: Anlaşılır ama YAPAY duyulan motorlar.
#:
#: Ayrım gerekli, çünkü öneri yalnızca hıza bakınca saçmalıyor: ölçümde
#: piper 120 ms, kyutai 2517 ms. Yani "piper'a geç" en hızlı cevap -- ama
#: kyutai'yi seçen kullanıcı onu GERÇEKÇİLİĞİ için seçti ve piper o işi
#: yapmıyor. Hızlı ama kulağa robot gibi gelen bir motoru önermek,
#: kullanıcının çözdüğü sorunu geri getirmek olurdu.
#:
#: Doğal duyulan bir motordan doğal duyulan bir motora öneri serbest
#: (kyutai 2517 ms -> styletts2 556 ms gibi); tersi değil.
BASIC_QUALITY: frozenset[str] = frozenset({"piper"})


def _is_downgrade(selected: str, candidate: str) -> bool:
    """*candidate*, *selected*'a göre bir KALİTE düşüşü mü?"""
    return candidate in BASIC_QUALITY and selected not in BASIC_QUALITY


def faster_alternative(
    selected: str, results: dict, *, factor: float = SLOW_FACTOR
) -> tuple[str, int, int] | None:
    """Seçili motordan belirgin şekilde hızlı, ölçülmüş bir motor var mı?

    Yalnızca KALİTE DÜŞÜŞÜ OLMAYAN adaylar değerlendiriliyor
    (bkz. ``BASIC_QUALITY``).

    Döner: ``(motor, o_motorun_ms, secilinin_ms)`` ya da ``None``.
    """
    if not isinstance(results, dict):
        return None

    current = results.get(str(selected))
    if not isinstance(current, dict):
        return None
    try:
        current_ms = int(current.get("elapsed_ms") or 0)
    except (TypeError, ValueError):
        return None
    if current_ms <= FAST_ENOUGH_MS:
        return None

    best_id, best_ms = None, current_ms
    for entry_id, row in results.items():
        if entry_id == str(selected) or not isinstance(row, dict):
            continue
        if _is_downgrade(str(selected), entry_id):
            continue
        try:
            ms = int(row.get("elapsed_ms") or 0)
        except (TypeError, ValueError):
            continue
        if ms <= 0:
            continue
        if ms < best_ms:
            best_id, best_ms = entry_id, ms

    if best_id is None or best_ms <= 0:
        return None
    if current_ms < best_ms * factor:
        return None
    return best_id, best_ms, current_ms


def slow_engine_message(selected: str, alternative: str, alt_ms: int, current_ms: int) -> str:
    """Ne olduğunu VE ne yapacağını birlikte söyle.

    Sayı GEÇİYOR: "daha hızlı bir seçenek var" tek başına inandırıcı değil ve
    kullanıcı zaten bir motoru bilerek seçmiş. Ölçülen fark ise bir karar
    verdirir.

    Metin bir KABUK KOMUTU önermiyor artık. Bunu okuyan kişi masaüstü
    panelinde duruyor ve seçim orada tek tık; terminale göndermek, aynı işi
    daha zor bir yerde yaptırmaktı.
    """
    return (
        f"{selected} takes {current_ms / 1000:.2f}s per sentence; "
        f"{alternative} takes {alt_ms / 1000:.2f}s "
        f"({current_ms / max(alt_ms, 1):.0f}x faster) and is already installed. "
        "Both are here — press Listen to compare."
    )


def run_bench(*, rounds: int = 3) -> list[dict[str, Any]]:
    """Kurulu her TTS motorunu ölç ve sonucu sakla.

    Her motor ``rounds`` kez çağrılıyor; SON ölçüm saklanıyor çünkü ilk çağrı
    model yüklemesini içeriyor ve kullanıcı onu oturum başına bir kez ödüyor.
    """
    import time

    from fool import voice_models as vm
    from fool.voice_preview import preview

    out: list[dict[str, Any]] = []
    for entry in vm.CATALOG:
        if entry.kind != "tts":
            continue
        if not vm.status(entry.id).get("installed"):
            continue

        times: list[float] = []
        error = ""
        for _ in range(max(1, rounds)):
            try:
                started = time.monotonic()
                preview(entry.id)
                times.append(time.monotonic() - started)
            except Exception as exc:
                error = str(exc)
                break

        # Anahtar SAGLAYICI ADI, katalog kimligi degil: ``tts.provider``
        # yapilandirmaya ``qwen3`` yaziyor ama katalog kimligi ``qwen3-tts``.
        # Kimlikle saklamak, secili motorun olcumu HIC bulunamamasi demekti --
        # ve "bulunamadi" sessizce "sorun yok" diye gorunuyordu.
        provider = entry.provider_id or entry.id
        row: dict[str, Any] = {
            "entry_id": entry.id,
            "provider": provider,
            "label": entry.label,
            "error": error,
        }
        if times:
            row["first_ms"] = int(times[0] * 1000)
            row["warm_ms"] = int(times[-1] * 1000)
            save_result(provider, row["warm_ms"])
        out.append(row)

    return out


def _main() -> int:  # pragma: no cover - elle calistirilan komut
    rows = run_bench()
    if not rows:
        print("kurulu seslendirme motoru yok")
        return 2

    print(f"{'motor':16} {'ilk':>9} {'isinmis':>9}")
    for row in rows:
        if row.get("error"):
            print(f"{row['entry_id']:16} HATA: {row['error'][:50]}")
            continue
        print(f"{row['entry_id']:16} {row['first_ms'] / 1000:8.2f}s {row['warm_ms'] / 1000:8.2f}s")

    try:
        from fool_cli.config import load_config

        selected = str(((load_config() or {}).get("tts") or {}).get("provider") or "").strip()
    except Exception:
        selected = ""

    if selected:
        hit = faster_alternative(selected, load_results())
        if hit:
            print()
            print(slow_engine_message(selected, *hit))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())
