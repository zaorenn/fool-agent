# Upstream'den besleme

The Fool tam yeniden adlandırıldı: `fool_cli` → `fool_cli`, `HERMES_*` →
`FOOL_*`, komut `fool`, veri dizini `~/.fool`. Normalde bu, upstream'den beslenmenin sonu
demektir — ölçtük, bir aylık upstream değişikliği **2.776 dosyada** çakışıyor.

Bu belge o duvarın nasıl aşıldığını anlatır.

## Fikir

Yeniden adlandırma tek seferlik bir olay değil, **yeniden çalıştırılabilir bir
dönüşüm** ([`fool/rename.py`](../../fool/rename.py)).

Upstream'i doğrudan merge etmek yerine, upstream'in bir **kopyasına aynı
dönüşümü uygularız** ve merge'i iki dönüştürülmüş ağaç arasında yaparız.

```
upstream/main  ──[fool.rename]──►  upstream-renamed  ──merge──►  main
     │                                                             │
  dokunulmaz                                          ikisi de ayni duzlemde
```

Sonuç: çatışmalar yalnızca **gerçek içerik farklarında** çıkar — isim
farklarında değil. Ve upstream deposuna hiç dokunulmaz.

## Akış

```bash
# 1. Upstream'in son halini al
git fetch upstream

# 2. Upstream'in anlik goruntusunu ayri bir dalda donustur
git checkout -B upstream-renamed upstream/main
python -m fool.rename --apply
git add -A
git commit -m "chore: upstream anlik goruntusu, yeniden adlandirilmis"

# 3. Kendi dalinda merge et
git checkout main
git merge upstream-renamed

# 4. Dogrula
python -m pytest tests/fool/ -q          # dikis + markalasma korumalari
python -m fool.audit                     # gorunen yuzeylerde kacak var mi
python -m fool.rename --verify           # donusum hala tutarli mi
```

## Neden bu çalışıyor

Dönüşümün iki özelliği bunu mümkün kılıyor; ikisi de `--verify` ile test edilir:

**Deterministik** — aynı girdi her zaman aynı çıktıyı verir. Olmasaydı iki taraf
ayrışır ve merge anlamsızlaşırdı.

**Idempotent** — zaten dönüştürülmüş bir ağaca tekrar uygulanması hiçbir şeyi
değiştirmez. Bu sayede `main` üzerinde tekrar çalıştırmak güvenlidir ve merge
sonrası kalan artıkları temizlemek için kullanılabilir.

## Dikkat edilecekler

**Aracın kendisi dönüşüme tabi değil.** `fool/rename.py`, `fool/audit.py` ve
`fool/branding.py` `SELF_EXCLUDE` listesinde. İlk çalıştırmada bu koruma yoktu
ve araç kendi tablosunu yedi — `("fool_state", "fool_state")` satırı
`("fool_state", "fool_state")` oldu, yani boş bir işleme döndü. Araç
çalışıyor görünmeye devam eder ama artık hiçbir şey yapmaz.

**Korunan değerler var.** `NousResearch/hermes-agent` (upstream deposu — atıf ve
merge yolu için gerekli) ve `hermes-agent` beceri kimliği
(`skill_view(name='hermes-agent')` ile çağrılıyor) dönüşümden muaf. Bunları
değiştirmek dış dünyaya bağlı bir şeyi kırar.

**Yeni bir yeniden adlandırma eklerken** `MODULE_RENAMES` tablosuna uzun adı
kısa addan ÖNCE koy. `fool_state_common`, `fool_state`'ten sonra gelirse
ikinci kural birinciyi bozar.

## Upstream'i seçici almak

Her şeyi almak zorunda değilsin. Tek bir düzeltmeyi almak için:

```bash
git checkout -B upstream-renamed upstream/main
python -m fool.rename --apply && git commit -am "renamed snapshot"
git checkout main
git cherry-pick -x <commit>       # upstream-renamed uzerindeki karsiligi
```

Upstream commit'inin yeniden adlandırılmış karşılığını bulmak için
`git log upstream-renamed --grep=<konu>` kullan.

## Ne zaman merge etmemeli

Backend'de kendi mimarini kurdukça bazı upstream değişiklikleri anlamını
yitirecek. Bunları almamak meşru bir karar — ama **bilinçli** olsun:
`docs/fool/SEAMS.md` gibi bir yerde neyi neden almadığını not et, yoksa altı ay
sonra aynı çatışmayı tekrar tekrar çözersin.
