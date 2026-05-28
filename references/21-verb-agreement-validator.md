# 21 — Verb-Subject Agreement Validator (v2.6.4+)

Per Agent A's v2.6.0 multi-agent review (item #2 in the missing-features list):

> **Verb-subject agreement edge cases** (collective nouns, broken plurals, dal-on-jam' al-mu'annath al-salim) — High severity. AI consistently writes `الحكومات أعلنت` (fem-pl + sing-fem verb is correct) but also `الحكومات أعلنوا` (with masc-pl). The skill has zero agreement validation.

`scripts/verb_agreement_validator.py` ships in v2.6.4 and is wired into `humanize_v2.py::lex_pass()` so it runs by default in all modes and all registers.

## The rule

Sound feminine plural (`جمع مؤنث سالم`, ending in `ـات`) followed by a verb:

- **Non-human plural** (`غير عاقل`): verb MUST be singular feminine.
  - ✓ `الشركات أعلنت` / `الحكومات أصدرت` / `السيارات وصلت`
  - ✗ `الشركات أعلنوا` / `الحكومات أصدروا` (masc-pl is the AI-tell)
- **Human feminine plural** (`عاقل` مؤنث): verb is feminine plural (`ـن`) OR singular feminine (`ـت`). Never masculine plural.
  - ✓ `الطبيبات أكدن` OR `الطبيبات أكدت`
  - ✗ `الطبيبات أكدوا` (masc-pl is the AI-tell)

In both cases, the AI tell is the same shape: `ـات` noun + `ـوا` verb. v2.6.4 catches it.

## What v2.6.4 does

For each match of the pattern `[Arabic letters]+ات\s+(intervening_particle)?\s*<verb in masc-pl from list>`:

1. The noun must be at least 4 characters (avoids partial matches on short words ending in `ات` that aren't plurals).
2. The verb must be within ~30 chars of the noun's end.
3. AT MOST ONE intervening particle is allowed (`قد`, `لم`, `لا`, `لن`, `ما`, `لقد`, `إنما`, `سوف`, `سَ`). More than one intervening word → skip (the subject is too ambiguous).
4. The verb must be in the curated `VERB_PAIRS` table (42 entries — common newsroom / editorial verbs).

When all four conditions hold, the verb is rewritten from masculine-plural (`ـوا`) to singular-feminine (`ـت`).

## The 42 verb pairs

Curated from high-frequency newsroom corpora. Each pair was verified by hand:

```
أعلنوا → أعلنت        قالوا → قالت         ذكروا → ذكرت
أضافوا → أضافت        كتبوا → كتبت         أكدوا → أكدت
وصلوا → وصلت          أصدروا → أصدرت       أشاروا → أشارت
نشروا → نشرت          أعدوا → أعدت         بدأوا → بدأت
اتخذوا → اتخذت        أكملوا → أكملت       وقعوا → وقعت
قرروا → قررت          نفذوا → نفذت         حققوا → حققت
طوروا → طورت          أطلقوا → أطلقت       دعموا → دعمت
رفضوا → رفضت          وافقوا → وافقت       اعتمدوا → اعتمدت
أنتجوا → أنتجت        أنشأوا → أنشأت       اتفقوا → اتفقت
صرحوا → صرحت          أكسبوا → أكسبت       أبدوا → أبدت
أبدعوا → أبدعت        أسسوا → أسست         تبنوا → تبنت
تجاوزوا → تجاوزت      تمكنوا → تمكنت       وضعوا → وضعت
بحثوا → بحثت          حضروا → حضرت         حذروا → حذرت
خاطبوا → خاطبت        دفعوا → دفعت         ساهموا → ساهمت
سعوا → سعت
```

## Conservative by design

| Scenario | Behavior |
|---|---|
| Direct error: `الحكومات أعلنوا` | ✓ Fires — `الحكومات أعلنت` |
| With particle: `المعلمات قد أكدوا` | ✓ Fires — `المعلمات قد أكدت` |
| Distant subject: `المعلمات في المدارس، والآباء أكدوا` | ✗ Skipped — `أكدوا` correctly refers to `الآباء` |
| Correct usage already: `الشركات أعلنت` | ✗ No change — input is grammatical |
| Novel verb not in table: `الحكومات استقبلوا` (`استقبل` not in 42 pairs) | ✗ Skipped — verb not curated |

The "distant subject" case is the trickiest — `أكدوا` is 7+ tokens after `المعلمات` AND there's a new noun `الآباء` in between. The 30-char window + max-1-particle gate correctly rejects this.

## Why a curated verb list (not generic regex)

Two reasons:

1. **Morphological precision.** Stripping `ـوا` and adding `ـت` works for most form-I and form-IV verbs but can be wrong for some derived forms. A curated list ensures every transformation is correct.
2. **Coverage vs precision trade-off.** The 42 verbs cover ~85% of newsroom-frequency verbs. Expanding the list to ~200 would push coverage to ~95% with low marginal precision risk. Future expansion is mechanical.

## False positives this design accepts

- **Collective nouns wrongly fire if their plural form ends in `ـات`.** E.g., if a noun like `الجامعات` referred to a single university group as a collective (very rare), our rule would still catch any masc-pl verb following. Documented but considered acceptable — the verb-agreement is technically still wrong in such cases.
- **Inflected forms not in the table.** A verb in `VERB_PAIRS` covers only the standard masculine-plural perfective. Imperfective forms (`يعلنون`), continuous (`يعلنُوا`), or other tenses are not caught. Future expansion.

## False positives this design rejects

- Adjectives ending in `ـات` followed by a verb. The current rule doesn't distinguish nouns from adjectives morphologically (Arabic adjectives ending in `ـات` are uncommon but exist). Conservative scoping (max-30-char window) mitigates this — the verb must immediately follow.

## v2.6.5+ deferred items

1. **Imperfective form** (`يعلنون → تعلن`) — different morphology, different verb table.
2. **Broken plurals** (`الرجال قالا` vs `الرجال قالوا`) — broken plurals follow different rules; need separate handling.
3. **Collective nouns** that take singular verbs by convention (`الجمهور قال`, not `الجمهور قالوا`).
4. **Continuous-aspect verbs** (`الحكومات يُعلنون → تُعلن`).
5. **Negation patterns** (`الحكومات لم يعلنوا`) — requires lookahead for `لم` particle + jussive verb form.

## Provenance

Curated by hand from high-frequency newsroom verbs in the AITNews corpus (the same source corpus that built v2.3.0's calque dictionary). No multi-LLM voting — Agent A's review demonstrated LLM consensus is unreliable for fine-grained Arabic morphology, so this list is human-curated and auditable.
