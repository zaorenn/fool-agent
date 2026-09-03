"""Sunucu, seslendirdiği cümleyi İSTEMCİYE söylemeli.

İstenen: "notch hem söylediğimiz cümleyi, sonra model cevap verdiğinde o an
sesli okunan cümleyi transcript gibi sırayla ve ses ile eşzamanlı vermeli --
böylece kocaman cümleleri tek seferde yazmak yerine sesli okunan cümleden
cümleye değişir."

Sunucu hangi cümleyi sentezlediğini zaten biliyor; istemcinin bilmesinin tek
yolu bunu söylemek. İki kural burada sabitleniyor ve ikisi de sessizce
bozulabilir.
"""

from __future__ import annotations

import re
from pathlib import Path

SOURCE = Path("fool_cli/web_server.py").read_text(encoding="utf-8")


def test_cumle_karesi_GONDERILIYOR() -> None:
    assert '{"type": "sentence", "text": piece}' in SOURCE


def test_cumle_karesi_AYNI_kuyruktan_geciyor() -> None:
    """Ayrı bir ``send_json`` sesin ÖNÜNE geçerdi: sentez iş parçacığında
    koşuyor ve sesi kuyruğa koyuyor, doğrudan gönderilen bir kare henüz
    kuyrukta bekleyen sesi aşardı. İstemci o zaman daha duyulmamış bir cümleyi
    yazardı -- yani tam da eşzamanlılığı bozardı."""
    block = SOURCE[SOURCE.index('{"type": "sentence"') - 400 : SOURCE.index('{"type": "sentence"') + 120]

    assert "chunks.put_nowait" in block
    assert "send_json" not in block


def test_tuketici_SOZLUK_kareyi_JSON_olarak_gonderiyor() -> None:
    consumer = SOURCE[SOURCE.index("chunk = await chunks.get()") :][:900]

    assert "isinstance(chunk, dict)" in consumer
    assert "send_json(chunk)" in consumer
    # Sozluk kare ses SAYILMAMALI: ``sent_bytes`` yalnizca gercek sesi sayiyor,
    # yoksa hic ses uretmemis bir oturum "calindi" diye raporlanirdi.
    assert consumer.index("isinstance(chunk, dict)") < consumer.index("sent_bytes +=")


def test_parca_basina_TEK_isaret() -> None:
    """Motor bir parça için birden çok ses karesi döndürebiliyor; her karede
    yeniden duyurmak aynı cümleyi tekrar tekrar yazdırırdı."""
    assert re.search(r"piece_announced = False", SOURCE)
    assert re.search(r"if not piece_announced:", SOURCE)
    assert re.search(r"piece_announced = True", SOURCE)
