"""Kullanıcıya görünen yüzeylerde kalan upstream markasını bulur.

Neden bu var
------------
Markalaşma kaçakları teker teker bulunuyordu: güncelleme penceresi, bootstrap'in
klonladığı depo, ajanın kendi kimliği, hata mesajlarındaki komut adları… Her biri
kullanıcı tarafından fark edildi, denetimle değil. Bu tarayıcı o döngüyü kırar.

Neden `git grep -i hermes` işe yaramaz
--------------------------------------
Repoda ~3.270 dosya "hermes" içeriyor. Ham arama 3.248 "bulgu" veriyor ve
neredeyse tamamı gürültü. Üç ayrı gürültü kaynağı var ve üçü de elenmeli:

1. **İç sözleşme** — ``hermes_cli``, ``HERMES_HOME``, ``hermes-agent`` beceri
   kimliği. Bunlar kod; değiştirilirse uygulama bozulur.
2. **Yorum satırları** — kullanıcı kodun yorumlarını görmez.
3. **Çalışma anında dönüştürülen yüzeyler** — ``i18n/en.ts`` içindeki 141
   "Hermes" geçişi ``applyFoolBrand()``'den geçiyor; komut açıklamaları
   ``CommandDef.__post_init__``'ten; ``--help`` metni argparse yamasından.
   Kaynakta "Hermes" yazması bir kaçak DEĞİL — kullanıcıya "The Fool" olarak
   ulaşıyor.

Geriye kalan şey gerçek sinyal: kullanıcıya olduğu gibi giden, hiçbir dönüşümün
dokunmadığı metin.

Kullanım::

    python -m fool.audit
    python -m fool.audit --verbose
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

#: Çalışma anında marka dönüşümünden GEÇEN yüzeyler. Kaynakta "Hermes" yazması
#: beklenen ve doğru olan durumdur — dönüşüm zaten hallediyor. Bunları taramak
#: yüzlerce yanlış pozitif üretir ve aracı kullanılamaz hale getirir.
#: NOT: bu dosya ``fool/rename.py``'daki ``SELF_EXCLUDE`` listesinde olduğu için
#: yeniden adlandırmadan ETKİLENMEZ. Bedeli: aşağıdaki yolları elle güncel
#: tutmak gerekir. Bir modül yeniden adlandırıldığında burada da düzelt, yoksa
#: tarayıcı var olmayan dizinleri tarar ve sessizce "temiz" der.
TRANSFORM_COVERED: tuple[str, ...] = (
    "apps/desktop/src/i18n/",   # applyFoolBrand  (FOOL-SEAM: i18n-brand)
    "web/src/i18n/",            # applyFoolBrand  (FOOL-SEAM: web-i18n-brand)
    "locales/",                 # brand_value     (FOOL-SEAM: locale-brand)
    "fool_cli/commands.py",     # CommandDef.__post_init__
    "fool_cli/_parser.py",      # argparse_brand
    "fool_cli/console_engine.py",
    "skills/",                  # brand_skill_body (FOOL-SEAM: skill-body-brand)
)

#: Taranan yüzeyler: kullanıcıya DÖNÜŞÜMSÜZ giden metin.
SURFACES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Masaüstü bileşenleri (sabit metin)", ("apps/desktop/src/**/*.tsx",)),
    ("Masaüstü ana süreç (diyalog/menü)", ("apps/desktop/electron/*.ts",)),
    ("Masaüstü HTML", ("apps/desktop/index.html",)),
    ("Kurulum sihirbazı", ("apps/bootstrap-installer/src/**/*.tsx",)),
    ("Güncelleme penceresi", ("scripts/desktop-update/*",)),
    ("Kurulum betikleri", ("scripts/install.sh", "scripts/install.ps1")),
    ("Ajan kimliği ve promptlar", ("agent/prompt_builder.py", "agent/system_prompt.py")),
    ("CLI banner ve sürüm", ("fool_cli/banner.py", "fool_cli/_startup_fast.py")),
    # CLI'nin KULLANICIYA YAZDIRDIGI komutlar. Burada "hermes update" yazmasi
    # kozmetik degil: kullanici (ya da ajan) o komutu gercekten calistirip
    # "command not found" aliyor -- 433 gecis tam buradan kacmisti.
    ("CLI komut metinleri", ("fool_cli/**/*.py", "tools/**/*.py", "agent/**/*.py")),
    # Web panosu BILESENLERI. i18n katalogu donusumden geciyor ama bilesen
    # icindeki sabit metinler gecmiyor -- dashboard basligi ve logotype tam
    # buradan kacmisti.
    ("Web panosu (sabit metin)", ("web/src/**/*.tsx", "web/index.html")),
    # NOT: ``skills/`` bilerek TARANMIYOR. Beceri govdeleri artik okuma
    # aninda ``brand_skill_body()`` ile donusturuluyor; kaynakta "Hermes"
    # yazmasi kacak degil. Bu tarayici 156 yanlis pozitif uretiyordu.
)

#: Marka — YALNIZCA serbest metinde. Kelime sınırları kritik: tanımlayıcıda
#: "Hermes" harflere yapışıktır (``waitForHermesReady``,
#: ``HERMES_DESKTOP_APP_NAME``), metinde ise boşluk/tırnakla çevrilidir
#: (``'Hermes update'``). Sınır olmadan tarayıcı yüzlerce sembol adını
#: metin sanıyordu.
_BRAND = re.compile(r"\b(Hermes|HERMES|Nous Research)\b")

#: Kullaniciya YAZDIRILAN komut: ``hermes`` ardindan bir alt komut.
#: Tanimlayicilardan ayirt eden sey BOSLUK -- ``hermes_cli`` ve
#: ``hermes-agent`` bu desene uymaz.
_COMMAND = re.compile(r"\bhermes (?=[a-z][a-z0-9-]*)")

#: İÇ SÖZLEŞME — değişmemeli, bulgu sayılmaz.
_CONTRACT: tuple[re.Pattern[str], ...] = (
    re.compile(r"HERMES_[A-Z0-9_]+"),
    re.compile(r"hermes_[a-z0-9_]+"),
    re.compile(r"hermes-agent(-[a-z-]+)?"),
    re.compile(r"hermes-(bots|frames|sprite|fade-in|achievements|home|runtime|bootstrap)"),
    re.compile(r"@hermes/"),
    re.compile(r"\.hermes\b"),
    re.compile(r"hermes\.(py|ts|tsx|mjs|json|exe|md)"),
    re.compile(r"(launch|build|is|get|set|resolve|active)Hermes\w*"),
    re.compile(r"Hermes(Skin|Plugin|Config|Home|Cli|State|Error|Window)\w*"),
    re.compile(r"NousResearch/hermes-agent"),   # upstream depoya atıf meşru
    re.compile(r"github\.com/nousresearch"),
    re.compile(r"nousresearch\.com"),           # upstream doküman bağlantısı
)

#: Yorum satırı başlangıçları — kullanıcı bunları görmez.
_COMMENT = re.compile(r"^\s*(//|#|\*|/\*|<!--|--)")


@dataclass(frozen=True)
class Finding:
    surface: str
    path: str
    line_no: int
    line: str


def _tracked(patterns: tuple[str, ...]) -> list[Path]:
    out: list[Path] = []
    for pattern in patterns:
        proc = subprocess.run(
            ["git", "ls-files", pattern], cwd=REPO_ROOT, capture_output=True, text=True
        )
        out.extend(REPO_ROOT / ln for ln in proc.stdout.splitlines() if ln.strip())
    return out


def _covered_by_transform(rel: str) -> bool:
    norm = rel.replace("\\", "/")
    return any(norm.startswith(c) or norm == c for c in TRANSFORM_COVERED)


def scan() -> list[Finding]:
    findings: list[Finding] = []
    seen: set[tuple[str, int]] = set()

    for surface, patterns in SURFACES:
        for path in _tracked(patterns):
            rel = str(path.relative_to(REPO_ROOT)).replace("\\", "/")
            if _covered_by_transform(rel):
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            # Docstring'ler KULLANICIYA GITMEZ; gelistirici notudur. Yorum
            # satirlariyla ayni gerekce, ama uc tirnak birden cok satira
            # yayildigi icin durum takibi gerekiyor. Bu olmadan tarayici 226
            # yanlis pozitif uretiyor ve gercek bulgular arasinda kayboluyordu.
            in_docstring = False

            for i, raw in enumerate(text.splitlines(), 1):
                fences = raw.count('\"\"\"') + raw.count("'''")

                if in_docstring:
                    if fences:
                        in_docstring = False
                    continue

                if fences == 1:
                    in_docstring = True
                    continue

                if fences >= 2:
                    # Tek satirlik docstring -- basi ve sonu ayni satirda.
                    continue

                if _COMMENT.match(raw):
                    continue

                # Komut metni markadan BAGIMSIZ bir bulgu turu: ``hermes push``
                # icinde "Hermes" gecmiyor ama calistirildiginda hata veriyor.
                if _COMMAND.search(raw):
                    key = (rel, i)
                    if key not in seen:
                        seen.add(key)
                        findings.append(Finding(surface, rel, i, raw.strip()[:150]))
                    continue

                if not _BRAND.search(raw):
                    continue
                # Sözleşme parçalarını sil, kalanda marka ara.
                residue = raw
                for pat in _CONTRACT:
                    residue = pat.sub("", residue)
                if not _BRAND.search(residue):
                    continue
                key = (rel, i)
                if key in seen:
                    continue
                seen.add(key)
                findings.append(Finding(surface, rel, i, raw.strip()[:150]))
    return findings


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="thefool-audit",
        description="Kullanıcıya dönüşümsüz giden metinde kalan upstream markasını bulur.",
    )
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    # Windows konsolu cp1254 gibi dar bir kod sayfasında olabilir ve bulunan
    # satırlar kutu-çizimi/emoji taşıyabiliyor. Değiştirilemeyen karakterler
    # aracı çökertmesin — bulgu göstermek, güzel göstermekten önemli.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")

    findings = scan()
    if not findings:
        print("Temiz — dönüşümsüz yüzeylerde markalanmamış metin yok.")
        return 0

    grouped: dict[str, list[Finding]] = {}
    for f in findings:
        grouped.setdefault(f.surface, []).append(f)

    print(f"{len(findings)} bulgu, {len(grouped)} yuzeyde:\n")
    for surface, items in sorted(grouped.items(), key=lambda kv: -len(kv[1])):
        print(f"  {len(items):4d}  {surface}")
        if args.verbose:
            for f in items:
                print(f"          {f.path}:{f.line_no}: {f.line}")
    if not args.verbose:
        print("\n  (satirlari gormek icin: --verbose)")
    return 1


if __name__ == "__main__":
    sys.exit(main())
