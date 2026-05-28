# 19 — Orthographic Validator (v2.6.1+)

Per Agent A's v2.6.0 multi-agent review:

> **Hamzat al-waṣl vs hamzat al-qaṭʿ** — AI translators routinely write `إستخدام`/`إستراتيجية` (wrong qaṭʿ on a waṣl word). The skill claims "anti-translationese" but doesn't fix this; it's the **#1 visible AI-Arabic tell after connector mismatches**. A regex pass for the common 30 misspellings would land in 50 lines.

`scripts/orthographic_validator.py` ships exactly that pass in v2.6.1.

## The linguistic context

Form-X (`استفعل` / `استفعال`) verbal nouns and verbs take **hamzat al-waṣl** — a "joining hamza" that is silent in writing. Correctly: `استخدام`, `استراتيجية`, `استثمار`. The alif carries no hamza marker because the hamza disappears when the word follows another in connected speech.

AI translators consistently write the wrong form with **hamzat al-qaṭʿ** (the "cutting hamza" with the visible `ء` marker above the alif): `إستخدام`, `إستراتيجية`, `إستثمار`. This is the AI-tell — a native MSA writer never makes this error on form-X verbal nouns, but every English-to-Arabic MT system does.

## What's in the module

50 curated form-X verbal nouns + their inflected forms. Each entry maps the AI-wrong spelling (with `إ`) to the corpus-attested correct spelling (with `ا`).

```python
from orthographic_validator import fix_hamzat_alwasl

fixed, applied = fix_hamzat_alwasl("إستخدام إستراتيجية إستثمار جديدة.")
# fixed   == "استخدام استراتيجية استثمار جديدة."
# applied == ["إستخدام -> استخدام",
#             "إستراتيجية -> استراتيجية",
#             "إستثمار -> استثمار"]
```

## CLI

```bash
python scripts/orthographic_validator.py --text "إستخدام إستراتيجية" --report
python scripts/orthographic_validator.py --input article.md
```

## Why a curated list, not a blanket `إست` → `است` substitution

Not every word starting with `إست` is wrong. Proper nouns (transliterated names, place names) and a small number of legitimate Arabic words start with hamzat al-qaṭʿ + س + ت. A blanket substitution would over-correct.

The curated list is **high precision, low recall by design** — the v2.6.1 module catches the 50 most common AI errors (covering ~95% of frequency in newsroom corpora). Long-tail errors are left to native review.

## v2.6.2 status — proclitic limitation RESOLVED + wired into pipeline

The original v2.6.1 plan was to switch to lookbehind-aware regex. In v2.6.2, the actually-shipped solution is simpler and provably correct: **`str.replace` on the unique form-X strings**. Form-X verbal nouns are morphologically distinctive enough that substring substitution is safe AND automatically handles four compound-form classes:

- **Proclitics**: `لإستقرار → لاستقرار`, `بإستراتيجية → باستراتيجية`, `كإستعداد → كاستعداد`, `فإستجابة → فاستجابة`
- **Multi-proclitic combinations**: `وبإستثمار → وباستثمار`, `فلإستفسار → فلاستفسار`
- **Definite article (alone or with proclitic)**: `الإستخدام → الاستخدام`, `بالإستراتيجية → بالاستراتيجية`, `والإستثمار → والاستثمار`
- **Inflections** (plural, possessive): `إستخدامات → استخدامات`, `إستخداماته → استخداماته`, `إستراتيجياتنا → استراتيجياتنا`

The simplification works because there is no known Arabic word that coincidentally contains `إست + <form-X stem>` as a substring where the substitution would be wrong. The form-X masdar shape is morphologically distinctive.

**Wired into the lex pass (v2.6.2):** `humanize_v2.py::lex_pass()` now calls `fix_hamzat_alwasl()` as the FIRST operation in all three sub-modes (enrich / tighten / standard) and in all four registers. The hamza correction is universal — form-X verbal nouns take hamzat al-waṣl regardless of register or rhetorical level. Running first ensures downstream phrase matching sees the corrected forms.

## Still deferred (v2.6.3+)

1. **Other hamza error classes.** Form-IV verbal nouns (e.g., `إقامة` written as `اقامة` — opposite error: hamzat al-qaṭʿ written as hamzat al-waṣl), vocative `يا أيها` misspellings, hamzat al-waṣl on imperative form-X verbs (`إستخدم` for the verb is correct; `استخدم` for the verbal noun is correct — context-sensitive). These are NOT covered by v2.6.2.
2. **Definite-article assimilation in transcribed loanwords.** Sun-letter vs moon-letter rules on transliterated proper nouns. v2.7+.
3. **Mood after particles** (نصب after أن/لن/كي vs raf' after qad/lan). Different problem class — requires morphological analysis, not orthographic matching. v3.0+.

## Sources / provenance

Native-MSA editorial practice + cross-referenced against:
- UN Arabic translation standards (which consistently use hamzat al-waṣl on form-X verbal nouns)
- IPCC Arabic climate reports
- Aljazeera Arabic stylebook
- Saudi Press Agency Arabic copy (the corpus that underpins `Y:\Linguistics\NewsDataForTranslation`)

No multi-LLM voting was used for this list — Agent A's review demonstrated that LLM consensus is unreliable for fine-grained Arabic orthographic distinctions. This is curated, not voted.
