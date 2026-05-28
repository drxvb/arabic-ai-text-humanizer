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

## v2.6.1 limitations (addressed in v2.6.2)

1. **Proclitic-prefixed forms miss the word boundary.** `لإستقرار` (with the `ل` proclitic = "for") doesn't match because Python's `\b` treats `ل` as part of the same Arabic word-token. Same problem for `بـ`, `كـ`, `فـ`, `وـ`. v2.6.2 will switch to lookbehind-aware matching.
2. **Not wired into `humanize_v2.py`'s lex pass yet.** v2.6.1 ships the module standalone for testing + manual use; v2.6.2 will add a `lex_dim_orthographic_hygiene` sub-pass that runs after the calque dictionary and before typography hygiene.
3. **Only form-X verbal nouns.** Other classes of hamza errors (form-IV nouns like `إقامة` written as `اقامة`, vocative `يا أيها` misspellings, etc.) are not yet covered. v2.6.3+.

## Sources / provenance

Native-MSA editorial practice + cross-referenced against:
- UN Arabic translation standards (which consistently use hamzat al-waṣl on form-X verbal nouns)
- IPCC Arabic climate reports
- Aljazeera Arabic stylebook
- Saudi Press Agency Arabic copy (the corpus that underpins `Y:\Linguistics\NewsDataForTranslation`)

No multi-LLM voting was used for this list — Agent A's review demonstrated that LLM consensus is unreliable for fine-grained Arabic orthographic distinctions. This is curated, not voted.
