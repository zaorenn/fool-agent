#!/usr/bin/env python3
"""
FOOL-SEAM: resmi-rapor

Resmî rapor araçlarının kayıt yeri.

Neden bu dosya ``tools/`` altında
---------------------------------
Kayıt defteri yalnızca ``tools/*.py`` dosyalarını tarıyor
(``tools/registry.py::discover_builtin_tools``): bir modül orada değilse ve
kimse onu elle ithal etmiyorsa araçları HİÇ kaydolmuyor.

Bu sessiz bir tuzak ve depoda bir örneği zaten var: ``fool/output_file.py``
kendini kaydediyor ama ``tools/`` altında olmadığı için yalnızca test onu
ithal ediyor -- yani ``output_file`` takımı takım listesinde görünüyor,
``write_output`` aracı ise çalışan üründe hiç var olmuyor. Ölçüldü:
``discover_builtin_tools()`` sonrası kayıtlı 88 araç içinde ``write_output``
yok; ``import fool.output_file`` yapılınca beliriyor.

Aynı hataya düşmemek için mantık Zone A'da (``fool/rapor/``), kayıt burada.
Bu dosya bilerek ince: yalnızca şema ve bağlama.
"""

from __future__ import annotations

from fool.rapor import arac
from tools.registry import registry

KAYNAK_OKU_SCHEMA = {
    "name": "rapor_kaynak_oku",
    "description": (
        "Read a source document (.pdf/.docx/.txt) for official report work, "
        "with an automatic text-quality check.\n\n"
        "Pass `sorgu` to retrieve ONLY the parts relevant to a question — "
        "required for large references (a 73-page guide is ~44k tokens, the "
        "directive ~135k). Without `sorgu` the whole text is returned, but "
        "only if it fits `token_butcesi`.\n\n"
        "If the document's text layer is broken (e.g. a PDF whose font drops "
        "a letter), the text is NOT returned — you get the reason instead. "
        "Do not work around this; ask the user for an OCR'd copy."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "yol": {"type": "string", "description": "Path to the document."},
            "sorgu": {
                "type": "string",
                "description": (
                    "What you need from it, in Turkish or English. Only the "
                    "matching sections are returned, in document order."
                ),
            },
            "token_butcesi": {
                "type": "integer",
                "description": "Max tokens to return (default 8000).",
            },
        },
        "required": ["yol"],
    },
}

YONERGE_OGREN_SCHEMA = {
    "name": "rapor_yonerge_ogren",
    "description": (
        "Read a long directive (yönerge) that DESCRIBES how a report must be "
        "written, and distil it into a saved, machine-checkable "
        "specification: required sections and their order, page setup "
        "(margins, font, size, spacing, alignment), page range, annex "
        "citation shape, cover fields, and the exact closing/conclusion "
        "phrases the directive mandates.\n\n"
        "This is NOT rapor_ornek_ogren. That one learns from a filled-in "
        "example REPORT; this one learns from the rules text. A 70-page "
        "directive never enters your context — you get a ~30 line summary "
        "where every rule cites the article it came from.\n\n"
        "SHOW that summary to the user and get it confirmed before writing: "
        "extraction is rule-based and can misread. Everything the directive "
        "did not state is listed in `eksik_kurallar` rather than silently "
        "defaulted.\n\n"
        "If the directive defines several report types, all of them come "
        "back in `diger_iskeletler`; re-run with `bolum_secimi` to pick one."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "yol": {"type": "string", "description": "Path to the directive (.pdf/.docx/.txt)."},
            "kimlik": {
                "type": "string",
                "description": (
                    "Short id to save the spec under, e.g. 'teftis-2026'. "
                    "Reuse it when starting drafts."
                ),
            },
            "bolum_secimi": {
                "type": "string",
                "description": (
                    "Which section list to adopt when the directive defines "
                    "several — an article ('MADDE 11') or part of its title."
                ),
            },
            "sayfa_en_az": {
                "type": "integer",
                "description": (
                    "Minimum pages, used ONLY if the directive states no page "
                    "range of its own."
                ),
            },
            "sayfa_en_cok": {"type": "integer", "description": "Maximum pages, same rule."},
        },
        "required": ["yol", "kimlik"],
    },
}

SARTNAME_GOSTER_SCHEMA = {
    "name": "rapor_sartname_goster",
    "description": (
        "Show a saved report specification, or list them all when no id is "
        "given. Use it to re-read the rules in a later session — the "
        "directive itself never has to be read again."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "kimlik": {"type": "string", "description": "Spec id; omit to list all."}
        },
    },
}

UYGUNLUK_SCHEMA = {
    "name": "rapor_uygunluk_denetle",
    "description": (
        "Check a draft against its specification BEFORE producing the "
        "document, and report concretely what is wrong: missing or empty "
        "sections, sections out of the directive's order, empty mandatory "
        "cover fields, a missing closing formula, a conclusion that carries "
        "none of the directive's mandated phrases, factual claims (dates, "
        "amounts, file numbers) with no annex reference, and sentences "
        "repeated verbatim to pad length.\n\n"
        "`engel` findings block production; `uyari` findings are for you to "
        "judge. Call this before rapor_taslak_uret — a non-conforming "
        "official document that has been produced is worse than one that "
        "was refused, because produced documents get signed."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "kimlik": {"type": "string", "description": "Draft id."},
            "sartname_kimligi": {
                "type": "string",
                "description": "Spec to check against; defaults to the draft's own.",
            },
        },
        "required": ["kimlik"],
    },
}

SAYFA_DENETLE_SCHEMA = {
    "name": "rapor_sayfa_denetle",
    "description": (
        "Measure the produced report's REAL page count and compare it to the "
        "target range. The document is rendered and its numbered pages are "
        "counted — not estimated — because the same character count fills a "
        "different number of pages at a different font or spacing.\n\n"
        "If it is short you get how many characters are missing, calibrated "
        "from this document's own measured characters-per-page, plus which "
        "sections are thinnest. Close that gap with NEW findings from the "
        "sources (rapor_delil_oku), never by widening spacing or repeating "
        "text — repetition is itself a blocking finding in "
        "rapor_uygunluk_denetle."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "docx": {"type": "string", "description": "Path to the produced .docx."},
            "kimlik": {
                "type": "string",
                "description": (
                    "Draft id — supplies the target range from its spec and "
                    "lets the tool name the thin sections."
                ),
            },
            "en_az": {"type": "integer", "description": "Minimum pages, if no spec."},
            "en_cok": {"type": "integer", "description": "Maximum pages, if no spec."},
        },
        "required": ["docx"],
    },
}

ORNEK_OGREN_SCHEMA = {
    "name": "rapor_ornek_ogren",
    "description": (
        "Learn HOW an example official report is written: section order, "
        "annex-reference shape, closing formulas, sub-headings, and its "
        "font/size.\n\n"
        "Returns a compact skeleton, not the example's text — measured 6,384 "
        "tokens down to 226. The example's sentences are deliberately "
        "withheld so another investigation's names and dates cannot leak "
        "into the new report."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "yol": {"type": "string", "description": "Path to the example .docx."}
        },
        "required": ["yol"],
    },
}

YARIM_COZUMLE_SCHEMA = {
    "name": "rapor_yarim_cozumle",
    "description": (
        "Analyse a half-finished report: which sections exist, which are "
        "missing or empty, and the exact formatting it uses (font, size, "
        "line spacing, alignment, margins).\n\n"
        "Reads the report IN FULL — a skipped paragraph means completed text "
        "that contradicts what is already written. Use the returned `bicim` "
        "as `bicim_kaynagi` when writing, so the completion matches the "
        "existing half exactly."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "yol": {"type": "string", "description": "Path to the half report .docx."}
        },
        "required": ["yol"],
    },
}

RAPOR_YAZ_SCHEMA = {
    "name": "rapor_yaz",
    "description": (
        "Write a structured report to .docx with the directive's layout "
        "applied by code (A4, margins, Times New Roman 12, justified, 1cm "
        "indent, 'n/N' page numbers on the body section only, Turkish "
        "uppercase). You supply CONTENT; formatting is not yours to get "
        "right.\n\n"
        "Report types: inceleme, disiplin, adli, on_inceleme.\n\n"
        "Any field you leave out stays [EKSİK] in the document and is listed "
        "back to you — never invent a date, file number or article reference."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "rapor_json": {
                "type": "string",
                "description": (
                    "JSON object: {tur, kapak:{bakanlik,baskanlik,baslik,konu,"
                    "gorev_emri_tarih,gorev_emri_sayi,rapor_tarih,rapor_sayi,"
                    "ek_adedi,mufettis_ad,gizli}, ozet:[...], bolumler:["
                    "{baslik, ogeler:[{tur:'paragraf'|'alt_baslik'|'alinti'|"
                    "'tablo', metin, ek, kaynak, baslik, basliklar, satirlar}]}"
                    "], ekler:[{no,icerik,sayfa_sayisi}], imza_yer, imza_tarih}"
                ),
            },
            "hedef": {"type": "string", "description": "Output .docx path."},
            "bicim_kaynagi": {
                "type": "string",
                "description": (
                    "Optional .docx to inherit formatting from — use the half "
                    "report being completed so both halves look identical."
                ),
            },
        },
        "required": ["rapor_json", "hedef"],
    },
}


# --- Parca parca kurma ---------------------------------------------------
#
# Tek dev JSON yerine diskte biriken taslak. Olculdu: yerel model (gemma-4-e4b)
# tek seferde uzun bir rapor JSON'unu yeniden kurarken kapak alanlarini
# dusuruyor; ayrica 70 sayfalik bir rapor tek cagriya zaten sigmiyor.

TASLAK_BASLAT_SCHEMA = {
    "name": "rapor_taslak_baslat",
    "description": (
        "Start a new report draft that accumulates on disk. Use this for any "
        "real report instead of building one giant JSON: each later call adds "
        "ONE section, so nothing large is ever held in context and a 70-page "
        "report is possible. "
        "Pick a short `kimlik` (draft id) and reuse it for every later call."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "kimlik": {"type": "string", "description": "Draft id, e.g. 'fazla-mesai-2026'."},
            "tur": {
                "type": "string",
                "description": (
                    "inceleme | disiplin | adli | on_inceleme — or any name "
                    "you like when `sartname_kimligi` is given, since the "
                    "sections then come from the user's own directive."
                ),
            },
            "sartname_kimligi": {
                "type": "string",
                "description": (
                    "Spec id from rapor_yonerge_ogren. Strongly preferred "
                    "when the user supplied a directive: the section list, "
                    "page setup and page range all come from it, and "
                    "production is refused while the draft breaks it."
                ),
            },
            "kapak": {"type": "object", "description": "Cover fields; can also be filled in later."},
            "ozet": {"type": "array", "items": {"type": "string"}},
            "imza_yer": {"type": "string"},
            "imza_tarih": {"type": "string"},
            "ornek_rapor": {
                "type": "string",
                "description": (
                    "Path to an example report. Its per-section lengths become "
                    "TARGETS, so the new report cannot come out far shorter "
                    "than the example it imitates. Strongly recommended."
                ),
            },
            "sifirla": {
                "type": "boolean",
                "description": (
                    "Only if you truly want to discard an existing draft. "
                    "Without it, starting an existing draft is refused so "
                    "already-written sections are not lost."
                ),
            },
        },
        "required": ["kimlik", "tur"],
    },
}

TASLAK_BOLUM_SCHEMA = {
    "name": "rapor_taslak_bolum",
    "description": (
        "Write ONE section into the draft. Sending the same `baslik` again "
        "replaces that section rather than duplicating it, so you can revise. "
        "`ogeler` items: {tur:'paragraf', metin, ek?, kalin?} | "
        "{tur:'alt_baslik', metin} | {tur:'alinti', metin, kaynak?, ek?} | "
        "{tur:'tablo', baslik, basliklar:[...], satirlar:[[...]]}"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "kimlik": {"type": "string"},
            "baslik": {"type": "string", "description": "e.g. 'III. INCELEME VE ARASTIRMA'"},
            "ogeler": {"type": "array", "items": {"type": "object"}},
        },
        "required": ["kimlik", "baslik", "ogeler"],
    },
}

TASLAK_EK_SCHEMA = {
    "name": "rapor_taslak_ek",
    "description": (
        "Add one entry to the annex index. Numbering follows the order added, "
        "which is what the directive asks for (first mention in the report)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "kimlik": {"type": "string"},
            "icerik": {"type": "string", "description": "What the annex is."},
            "sayfa_sayisi": {"type": "integer"},
        },
        "required": ["kimlik", "icerik"],
    },
}

TASLAK_KAPAK_SCHEMA = {
    "name": "rapor_taslak_kapak",
    "description": (
        "Update ONLY the given cover fields, leaving the rest untouched. "
        "Use this rather than resending the whole cover - resending a long "
        "object is exactly where fields get dropped."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "kimlik": {"type": "string"},
            "alanlar": {
                "type": "object",
                "description": (
                    "Any of: bakanlik, baskanlik, baslik, konu, "
                    "gorev_emri_tarih, gorev_emri_sayi, rapor_tarih, "
                    "rapor_sayi, ek_adedi, mufettis_ad, mufettis_unvan, gizli"
                ),
            },
        },
        "required": ["kimlik", "alanlar"],
    },
}

TASLAK_OZET_SCHEMA = {
    "name": "rapor_taslak_ozet",
    "description": (
        "Write the report's summary page (MADDE 7: it sits between the cover "
        "and the report text). Do this AFTER the sections exist - the "
        "directive sizes the summary against the report's length, so it "
        "cannot be written before there is a report to summarise."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "kimlik": {"type": "string"},
            "satirlar": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Summary paragraphs, in order.",
            },
        },
        "required": ["kimlik", "satirlar"],
    },
}

TASLAK_DURUM_SCHEMA = {
    "name": "rapor_taslak_durum",
    "description": (
        "What the draft contains and which required sections are still "
        "missing. Check this before producing the document."
    ),
    "parameters": {
        "type": "object",
        "properties": {"kimlik": {"type": "string"}},
        "required": ["kimlik"],
    },
}

TASLAK_URET_SCHEMA = {
    "name": "rapor_taslak_uret",
    "description": (
        "Produce the .docx from the accumulated draft. Pass `bicim_kaynagi` "
        "when completing a half-finished report so both halves match."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "kimlik": {"type": "string"},
            "hedef": {"type": "string", "description": "Output .docx path."},
            "bicim_kaynagi": {"type": "string"},
        },
        "required": ["kimlik", "hedef"],
    },
}


RAPOR_PDF_SCHEMA = {
    "name": "rapor_pdf",
    "description": (
        "Convert a produced .docx report to PDF using an installed converter "
        "(LibreOffice). The .docx stays the authoritative document - the "
        "inspector edits and signs that; PDF is a derived output. "
        "If no converter is installed this reports that plainly instead of "
        "pretending to produce one."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "docx": {"type": "string", "description": "Path to the .docx."},
            "hedef_klasor": {"type": "string", "description": "Output folder (default: next to the .docx)."},
        },
        "required": ["docx"],
    },
}

def check_rapor_requirements() -> bool:
    """Check if official report generation tools should be exposed.

    Gated so 14+ specialized report tools (~3000 tokens) do not bloat normal
    conversations unless FOOL_RAPOR_ENABLED=1 is set or explicitly in toolsets.
    """
    import os
    from utils import env_var_enabled
    if env_var_enabled("FOOL_RAPOR_ENABLED"):
        return True
    try:
        from fool_cli.config import load_config
        cfg = load_config()
        if cfg.get("rapor", {}).get("enabled", False):
            return True
        toolsets = cfg.get("toolsets", [])
        if isinstance(toolsets, list) and "rapor" in toolsets:
            return True
        platform = os.environ.get("FOOL_PLATFORM") or "cli"
        plat_ts = (cfg.get("platform_toolsets") or {}).get(platform, [])
        if isinstance(plat_ts, list) and "rapor" in plat_ts:
            return True
    except Exception:
        pass
    return False


# Kayitlar EN UST SEVIYEDE, ``try`` icinde DEGIL.
#
# ``tools/registry.py::_module_registers_tools`` yalnizca modul govdesindeki
# en ust seviye ifadelere bakiyor (``ast.parse(...).body``). Kayitlari bir
# ``try`` blogunun icine koydugumda tarayici bu dosyayi "arac kaydetmiyor"
# diye isaretledi ve modul hic ithal edilmedi -- olculdu: kesif sonrasi
# kayitli rapor araci 0, dogrudan ithal edince 4.
registry.register(
    name="rapor_kaynak_oku",
    toolset="rapor",
    schema=KAYNAK_OKU_SCHEMA,
    handler=lambda args, **kw: arac.kaynak_oku(
        yol=args.get("yol", ""),
        sorgu=args.get("sorgu"),
        token_butcesi=int(args.get("token_butcesi", 8000)),
    ),
    check_fn=check_rapor_requirements,
    emoji="📑",
)

registry.register(
    name="rapor_yonerge_ogren",
    toolset="rapor",
    schema=YONERGE_OGREN_SCHEMA,
    handler=lambda args, **kw: arac.yonerge_ogren_arac(
        yol=args.get("yol", ""),
        kimlik=args.get("kimlik", ""),
        bolum_secimi=args.get("bolum_secimi", ""),
        sayfa_en_az=int(args.get("sayfa_en_az", 0) or 0),
        sayfa_en_cok=int(args.get("sayfa_en_cok", 0) or 0),
    ),
    check_fn=check_rapor_requirements,
    emoji="📜",
)

registry.register(
    name="rapor_sartname_goster",
    toolset="rapor",
    schema=SARTNAME_GOSTER_SCHEMA,
    handler=lambda args, **kw: arac.sartname_goster(kimlik=args.get("kimlik", "")),
    check_fn=check_rapor_requirements,
    emoji="📐",
)

registry.register(
    name="rapor_uygunluk_denetle",
    toolset="rapor",
    schema=UYGUNLUK_SCHEMA,
    handler=lambda args, **kw: arac.uygunluk_denetle(
        kimlik=args.get("kimlik", ""),
        sartname_kimligi=args.get("sartname_kimligi", ""),
    ),
    check_fn=check_rapor_requirements,
    emoji="🔎",
)

registry.register(
    name="rapor_sayfa_denetle",
    toolset="rapor",
    schema=SAYFA_DENETLE_SCHEMA,
    handler=lambda args, **kw: arac.sayfa_denetle(
        docx=args.get("docx", ""),
        kimlik=args.get("kimlik", ""),
        en_az=int(args.get("en_az", 0) or 0),
        en_cok=int(args.get("en_cok", 0) or 0),
    ),
    check_fn=check_rapor_requirements,
    emoji="📏",
)

registry.register(
    name="rapor_ornek_ogren",
    toolset="rapor",
    schema=ORNEK_OGREN_SCHEMA,
    handler=lambda args, **kw: arac.ornek_ogren(yol=args.get("yol", "")),
    check_fn=check_rapor_requirements,
    emoji="🧭",
)

registry.register(
    name="rapor_yarim_cozumle",
    toolset="rapor",
    schema=YARIM_COZUMLE_SCHEMA,
    handler=lambda args, **kw: arac.yarim_cozumle(yol=args.get("yol", "")),
    check_fn=check_rapor_requirements,
    emoji="🧩",
)

registry.register(
    name="rapor_yaz",
    toolset="rapor",
    schema=RAPOR_YAZ_SCHEMA,
    handler=lambda args, **kw: arac.rapor_yaz(
        rapor_json=args.get("rapor_json", "{}"),
        hedef=args.get("hedef", ""),
        bicim_kaynagi=args.get("bicim_kaynagi"),
    ),
    check_fn=check_rapor_requirements,
    emoji="📄",
)

registry.register(
    name="rapor_taslak_baslat",
    toolset="rapor",
    schema=TASLAK_BASLAT_SCHEMA,
    handler=lambda args, **kw: arac.taslak_baslat(
        kimlik=args.get("kimlik", ""),
        tur=args.get("tur", "inceleme"),
        kapak=args.get("kapak"),
        ozet=args.get("ozet"),
        imza_yer=args.get("imza_yer", ""),
        imza_tarih=args.get("imza_tarih", ""),
        sifirla=bool(args.get("sifirla", False)),
        ornek_rapor=args.get("ornek_rapor"),
        sartname_kimligi=args.get("sartname_kimligi", ""),
    ),
    check_fn=check_rapor_requirements,
    emoji="🗂️",
)

registry.register(
    name="rapor_taslak_bolum",
    toolset="rapor",
    schema=TASLAK_BOLUM_SCHEMA,
    handler=lambda args, **kw: arac.taslak_bolum(
        kimlik=args.get("kimlik", ""),
        baslik=args.get("baslik", ""),
        ogeler=args.get("ogeler"),
    ),
    check_fn=check_rapor_requirements,
    emoji="✍️",
)

registry.register(
    name="rapor_taslak_ek",
    toolset="rapor",
    schema=TASLAK_EK_SCHEMA,
    handler=lambda args, **kw: arac.taslak_ek(
        kimlik=args.get("kimlik", ""),
        icerik=args.get("icerik", ""),
        sayfa_sayisi=int(args.get("sayfa_sayisi", 1)),
    ),
    check_fn=check_rapor_requirements,
    emoji="📎",
)

registry.register(
    name="rapor_taslak_kapak",
    toolset="rapor",
    schema=TASLAK_KAPAK_SCHEMA,
    handler=lambda args, **kw: arac.taslak_kapak(
        kimlik=args.get("kimlik", ""),
        alanlar=args.get("alanlar"),
    ),
    check_fn=check_rapor_requirements,
    emoji="🏷️",
)

registry.register(
    name="rapor_taslak_durum",
    toolset="rapor",
    schema=TASLAK_DURUM_SCHEMA,
    handler=lambda args, **kw: arac.taslak_durum(kimlik=args.get("kimlik", "")),
    check_fn=check_rapor_requirements,
    emoji="📋",
)

registry.register(
    name="rapor_taslak_uret",
    toolset="rapor",
    schema=TASLAK_URET_SCHEMA,
    handler=lambda args, **kw: arac.taslak_uret(
        kimlik=args.get("kimlik", ""),
        hedef=args.get("hedef", ""),
        bicim_kaynagi=args.get("bicim_kaynagi"),
    ),
    check_fn=check_rapor_requirements,
    emoji="📘",
)

registry.register(
    name="rapor_pdf",
    toolset="rapor",
    schema=RAPOR_PDF_SCHEMA,
    handler=lambda args, **kw: arac.rapor_pdf(
        docx=args.get("docx", ""),
        hedef_klasor=args.get("hedef_klasor"),
    ),
    check_fn=check_rapor_requirements,
    emoji="🖨️",
)

registry.register(
    name="rapor_taslak_ozet",
    toolset="rapor",
    schema=TASLAK_OZET_SCHEMA,
    handler=lambda args, **kw: arac.taslak_ozet(
        kimlik=args.get("kimlik", ""),
        satirlar=args.get("satirlar"),
    ),
    check_fn=check_rapor_requirements,
    emoji="📝",
)
