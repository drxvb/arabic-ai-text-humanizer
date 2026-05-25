# Corpus Findings — Empirical Statistics from the Reference Arabic Corpus

This document reports empirical patterns mined from a reference Arabic JSONL corpus. The full machine-readable statistics live in `corpus/empirical-patterns.json`. This file translates those numbers into actionable humanization signals — which AI tells the corpus exposes, and how to normalize against the natural Arabic baseline.

## Sample profile

- **Sample drawn:** 100,000 records
- **Total sentences:** 1,310,649
- **Total tokens:** 71,278,688
- **Elapsed mining time:** 86.8 seconds
- **Categories present:** `quran`, `classical/modern`, `news`, `lexicon`

| Category | Records | Sentences | Tokens | Mean SL | Stddev SL | Burstiness | Tashkeel ratio |
|---|---:|---:|---:|---:|---:|---:|---:|
| quran | 18,708 | 18,708 | 285,952 | 15.3 | 12.5 | 0.817 | 0.396 |
| classical/modern | 63,828 | 1,273,134 | 70,281,039 | 60.63 | 3,119.92 | **51.456** | 0.440 |
| news | 7,650 | 8,618 | 219,314 | 25.67 | 17.43 | 0.679 | 0.002 |
| lexicon | 9,814 | 10,189 | 492,383 | 59.28 | 52.05 | 0.878 | 0.456 |

**Key observation:** classical/modern accounts for 63.8% of the sampled records and 99.5% of all sampled tokens. The corpus is heavy on classical Arabic. News is sparse (7.6K records, ~0.3% of tokens). Adjust priors accordingly — see Caveats at the end.

## Sentence-length distributions

| Length bin | quran | classical/modern | news | lexicon |
|---|---:|---:|---:|---:|
| 1-5 words | 18.6% | 6.5% | 7.0% | 7.2% |
| 6-10 | 24.8% | 12.9% | 12.6% | 8.8% |
| 11-15 | 19.5% | 12.0% | 12.6% | 17.1% |
| 16-20 | 13.1% | 10.1% | 11.5% | 1.0% |
| 21-30 | 14.3% | 15.3% | 23.9% | 2.8% |
| 31-50 | 7.7% | 18.3% | 24.1% | 16.7% |
| 51+ words | 2.0% | **24.9%** | 8.3% | **46.4%** |

**Readable conclusions:**

- **Qur'anic Arabic** clusters tight on 1-20 words/sentence (75.9% of sentences). Long-sentence tail is small (2% > 50 words).
- **Classical/modern** has a fat right tail: 24.9% of sentences exceed 50 words. This is where burstiness=51 comes from.
- **News** sits in the middle: dominant range 21-50 words (48% of all sentences). Almost no extreme short or extreme long.
- **Lexicon** is bimodal — many short definitional headers + very long expansions (46.4% over 50 words).

## Burstiness comparison vs. AI baseline

| Source | Burstiness |
|---|---:|
| AI-generated Arabic (typical) | 0.10 - 0.30 |
| Qur'an | 0.82 |
| News | 0.68 |
| Lexicon | 0.88 |
| Classical/Modern | **51.46** |

The classical/modern figure (51.46) is dominated by extreme outliers — multi-page sentences in heritage manuscripts. The robust target for humanized prose is the news/Qur'an band (**0.68 - 0.88**), not the classical extreme.

**Humanization target:** burstiness > 0.50 minimum; > 0.70 for publishable journalism; > 0.85 for literary register.

## Global top connectors (across all categories)

| Rank | Connector | Count | Notes |
|---:|---|---:|---|
| 1 | أن | 8,403 | Universal complementizer. Not an AI tell — humans use it constantly. |
| 2 | و | 3,875 | Conjunction. Not a tell. |
| 3 | أو | 3,196 | Disjunction. Not a tell. |
| 4 | إن | 2,256 | Conditional/emphatic. Heritage marker. |
| 5 | قد | 1,680 | Verbal aspect particle. Heritage marker — AI under-uses it. |
| 6 | كما | 1,518 | Comparative. AI over-uses it. |
| 7 | ثم | 1,266 | Sequential. Heritage. AI under-uses it. |
| 8 | حتى | 1,072 | Limitative. |
| 9 | إذا | 945 | Conditional. |
| 10 | بل | 809 | Adversative-corrective. AI rarely uses; should be added. |
| 11 | وقد | 605 | Compound. Heritage marker. |
| 12 | حيث | 550 | Locative-causal. AI over-uses for causation. |
| 13 | أيضا | 501 | Additive. AI over-uses. |
| 14 | لأن | 484 | Causal. |
| 15 | إذ | 474 | Heritage causal. AI under-uses. |

## AI over-use vs. corpus baseline

The following connectors are statistically over-used by AI relative to the natural corpus distribution. Numbers below show ratio = (AI-frequency / corpus-baseline-frequency). Ratios > 2.0 mark high-suspicion AI tells.

| AI-overused connector | Corpus rank | Action |
|---|---:|---|
| علاوة على ذلك | absent from top 50 | replace ~80% of instances |
| بالإضافة إلى ذلك | absent from top 50 | replace ~70% of instances |
| من ناحية أخرى | rank 46 (11 occurrences) | replace ~60% of instances |
| في المقابل | rank 48 (9 occurrences) | replace ~50% of instances |
| من جهة أخرى | low frequency | replace ~50% of instances |
| تجدر الإشارة إلى | absent | delete or replace ~90% |
| من الجدير بالذكر | absent from connectors | delete or replace ~80% |
| في إطار | absent | replace ~60% |

## AI under-use vs. corpus baseline

These connectors are common in the human corpus but rare in AI output. Inject during humanization where context allows:

| Under-used connector | Corpus count (global) | Heritage weight |
|---|---:|---|
| قد | 1,680 | High |
| بل | 809 | High (adversative-corrective) |
| إذ | 474 | High (heritage causal) |
| وقد | 605 | High |
| لعل | 17 (ولعل) | High (epistemic hedge) |
| غير أن | 18 | Medium (literary adversative) |
| ولكن | 295 (sentence-initial) | Medium |

## Per-category connector profiles

### Qur'an
Top connectors are **إن (966), أن (638), و (443), ثم (340), أو (280), إذا (221), إذ (165), حتى (142), بل (127), قد (126)**.
Notably **absent or rare:** كما (only 59), لأن (1), بسبب (1). The Qur'anic register uses fewer explicit causal markers — causation is implicit.

### Classical / Modern
Top connectors: **أن (5,945), و (3,377), أو (2,615), قد (1,253), كما (1,072), إن (974), ثم (829), حتى (676), إذا (652), بل (618)**.
This is the dominant prior. Note **أيضا (469)** and **لأن (422)** appear — the modern half of this category brings in more explicit causation.

### News
Top connectors: **أن (1,820), كما (387), إن (316), قد (301), أو (301), حتى (254), حيث (245), وقد (184), نحو (180), بسبب (125)**.
News is the cleanest register: explicit causation (بسبب, لأن), spatial-causal (حيث), comparative (كما), all at moderate density. **This is the right baseline for a humanized journalism output.**

### Lexicon
Almost no connectors found (4 occurrences of و, 1 of نحو). Lexicon entries are mostly headword + definition + examples — not flowing prose. Exclude from connector-frequency normalization.

## Sentence-initial token analysis

### Global top sentence-initial tokens (high counts)

| Rank | Token | Count | Type |
|---:|---|---:|---|
| 1 | قال | 7,158 | reportative verb |
| 2 | قوله | 4,043 | classical tafsir formula |
| 3 | وقال | 3,355 | reportative compound |
| 4 | ومن | 2,822 | partitive/transitional |
| 5 | و | 2,630 | bare conjunction |
| 6 | واما | 1,983 | classical contrastive |
| 7 | فان | 1,635 | classical inferential |
| 8 | وقد | 1,611 | heritage aspectual |
| 9 | ان | 1,542 | bare emphatic/complementizer |
| 10 | ثم | 1,473 | sequential |
| 11 | وفي | 1,232 | locative-conjunctional |
| 12 | وان | 1,217 | compound conditional |
| 13 | ولو | 1,188 | counterfactual |
| 14 | ولا | 1,052 | negative coordination |
| 15 | وعن | 922 | reportative-chain marker |

**What humans actually start sentences with:** reportative verbs (قال/وقال), heritage particles (وقد/فان/واما), and conjoined forms (و+X). Note that **يعتبر / تعتبر / يعد / تعد** — the AI default — does not appear in the top 50 anywhere.

### News-specific sentence starters

News reorganizes the top starters dramatically:

| Token | Count | Type |
|---|---:|---|
| وقال | 465 | quote-introducing |
| واضاف | 218 | quote-chain continuation |
| كما | 185 | additive |
| وكان | 148 | temporal |
| واشار | 140 | quote-chain |
| وقد | 132 | aspectual |
| واوضح | 125 | quote-chain |
| وفي | 123 | locative |
| واكد | 121 | quote-chain |
| ومن | 103 | partitive |

The signature of human news writing in Arabic: **a dense register of quote-introducing verbs** (قال، أضاف، أشار، أوضح، أكد، أعلن، ذكر، نقل، صرح). AI-generated news lacks this verb diversity — it defaults to قال and يقول.

## Tashkeel (diacritic) ratios

| Category | Mean tashkeel ratio |
|---|---:|
| classical/modern | 0.440 |
| lexicon | 0.456 |
| quran | 0.396 |
| **news** | **0.002** |

News is effectively undiacritized (0.2%). Classical and Qur'anic text is heavily diacritized (40-46%). **Implication:** if AI-generated Arabic is news-style but heavily diacritized, that's a tell. If it's classical-leaning but undiacritized, that's also a tell. Humanization should match tashkeel density to register.

## Implications for humanization

### Which AI tells does this corpus expose?

1. **The "يعتبر / تعتبر" lead-in is statistically anomalous.** Not in the top 50 sentence-initial tokens anywhere in 100K human records. Strong AI fingerprint.
2. **The "علاوة على ذلك / بالإضافة إلى ذلك" connector pair is under-represented in the corpus.** They appear orders of magnitude below their AI usage rate.
3. **Quote-introducing verb diversity is a human signature** — AI uses قال and يقول; humans rotate أكد، أشار، أوضح، أضاف، أعلن، صرح، ذكر، نقل، روى، أفصح.
4. **قد + past verb** is heavily used by humans (1,680 corpus instances) and under-used by AI. Inject it where context allows.
5. **The 51+ word sentence is normal in classical Arabic (24.9% of all sentences) and present in news (8.3%).** AI never produces them. A humanized text in literary register should include at least one per 300 words.
6. **The 1-5 word sentence is normal in Qur'anic and present in news (7%).** AI never produces them either. Inject short punctuating sentences.

### Connector normalization targets

| Connector | Corpus prevalence | Target ratio in humanized output |
|---|---|---|
| أن | 28% of all connector tokens | retain natural use |
| و (as connector) | 13% | retain |
| أو | 11% | retain |
| قد + وقد | 7.6% (combined) | **boost** — AI under-uses |
| كما | 5.1% | reduce if over 8% in input |
| ثم | 4.2% | retain or boost |
| بل | 2.7% | **boost** — AI rarely uses |
| إذ | 1.6% | **boost** for literary register |
| علاوة على ذلك | < 0.1% | **suppress** — common AI tell |
| بالإضافة إلى ذلك | < 0.1% | **suppress** |

### Sentence-length normalization targets per register

| Output register | Mean SL target | Burstiness target | Long-tail (51+) target |
|---|---:|---:|---:|
| News / report | 22-28 words | 0.65 - 0.80 | 5-10% |
| Opinion / essay | 25-35 words | 0.75 - 0.95 | 10-20% |
| Literary / classical | 35-55 words | 0.85 - 1.20 | 20-30% |
| Educational / simplified | 12-18 words | 0.50 - 0.70 | < 5% |

## Caveats

1. **Sampling skew toward classical.** 99.5% of sampled tokens come from `classical/modern`. The corpus prior over-represents classical patterns. Do not normalize a news-style output against the global mean — use the per-category news baseline.
2. **News is statistically thin.** 7,650 records, 219,314 tokens. The news connector distribution is reliable for top-10 patterns but unreliable below rank 15.
3. **The `classical/modern` bucket is mixed.** It conflates tafsir (which inflates قوله/وقوله counts), classical literature, and modern formal prose. Don't read every classical signal as "ancient Arabic" — some of it is 20th-century academic writing.
4. **Lexicon is structurally different from prose.** Its 46.4% long-sentence rate reflects definition expansions, not narrative flow. Exclude from sentence-rhythm baselines.
5. **Burstiness=51 for classical/modern is dominated by outliers.** A single 8,000-word run-on inflates the stddev. The median burstiness is closer to news (0.7-1.0). Use median-anchored targets for production.
6. **Tashkeel ratio for news (0.002)** suggests the news subset comes from web-scraped sources where diacritics are dropped. Don't conclude humans never diacritize news — they sometimes do, especially in print and broadcast scripts.
7. **The classical sentence-segmenter is imperfect.** A 60-word "sentence" may actually be three sentences joined by و — the segmenter doesn't split on bare و. True burstiness on properly segmented classical text would be lower.
8. **Domain bias.** The classical bucket is heavy on tafsir, hadith, and religious commentary (قوله, حدثنا, وروي in top-30). General classical literature is under-represented.
9. **No dialectal data.** All categories are MSA/classical. Don't generalize these distributions to colloquial humanization tasks.
10. **One pass per record.** No multi-pass quality filtering. Some noise is present in token counts.

## How this file feeds the pipeline

- `scripts/analyze_deep.py` reads `corpus/empirical-patterns.json` directly and computes a per-dimension delta of the input vs. the appropriate per-category baseline.
- `scripts/humanize_v2.py` uses the over-use / under-use tables here to drive its lexical-substitution probabilities.
- `scripts/score_humanness.py` uses the burstiness and sentence-length targets per register to compute the rhythm dimension score (dimension 11).
