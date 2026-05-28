---
name: arabic-ai-text-humanizer
description: Bilingual AI-text humanizer. Arabic primary (16 dimensions, classical-rhetoric + cognitive-structure + typography hygiene + connector entropy; 4 register policies; 6 modes; pre-flight safety). English secondary (5-axis Directness/Rhythm/Trust/Authenticity/Density rubric + deterministic lex pass; lexical/structural/sentence-level pattern catalogue adapted from hardikpandya/stop-slop MIT). Scope is humanization, NOT localization — BCP47, ICU, SSML are out of scope. Provider-agnostic; works with any OpenAI-compatible LLM. Triggers on "humanize deep", "humanize cognitively", "humanizer v2", "تحويل النص إلى أسلوب بشري عميق", "stop slop", "remove AI slop", "detect AI tells", "humanize English", "humanize prose". Do NOT use for technical specs, code documentation, legal text, dialect-heavy/colloquial Arabic content, already-human text (run analyze-only instead), or languages outside Arabic/English.
---

# Arabic AI-Text Humanizer — Cognitive + Rhetorical + Reader-Respect Layer

## Languages supported

| Language | Status |
|---|---|
| **Modern Standard Arabic (MSA), classical-leaning** | ✅ Primary target — all 16 dimensions calibrated for this register; use `scripts/humanize_v2.py` |
| **English (modern, direct register)** | ✅ Secondary (v2.5.0+) — 5-axis rubric, deterministic lex pass; use `scripts/humanize_english.py`. See `references/17-english-ai-tells.md` |
| Arabic dialects (Egyptian, Levantine, Khaleeji, Maghrebi, etc.) | ❌ Not supported — lexical tables and dimensions assume MSA |
| Code-switched Arabic + English | ⚠️ Pick the path that matches the dominant script; mixed spans may be misprocessed |
| Right-to-left + left-to-right Bidi-mixed text | ⚠️ Plain text only; Bidi marks not preserved |
| Quranic recitation marks (U+06D6–U+06ED) | ⚠️ Preserved verbatim but not generated |
| Other languages (French, Spanish, Mandarin, Hindi, …) | ❌ Out of scope — use a language-specific humanizer |

## Scope: Humanizer ≠ Localizer (per cross-LLM critique)

**This skill is a `Humanizer`, not a `Localizer`.** Load-bearing distinction:

- **Humanizer (this skill)** — takes AI-generated Arabic text, makes it less mechanical at the *style* and *cognitive-structure* layer. Outputs **Arabic prose**.
- **Localizer (out of scope)** — produces locale-specific product strings with BCP47 tags, ICU MessageFormat plurals, SSML, locale numerics, `<bdi>`/dir attributes, gender-aware UI. Outputs **product strings with metadata**.

External deep-research (May 2026) recommended adopting BCP47/ICU/SSML. Multiple LLM critiques independently flagged this as **scope conflation**: those tools build a different product. We DECLINED those recommendations and documented why.

## What "humanness" means here (per cross-LLM critique — gap that the framework had)

The skill optimizes a **ranked priority list**, not a single metric:

1. **Meaning preservation** — never let humanization rewrite a claim into a different claim
2. **Syntactic naturalness** — sentences must parse as native Arabic, not English-syntax transfer
3. **Register fit** — match the target policy (news/opinion/classical/technical)
4. **Economy** — prefer deletion over substitution when both yield grammatical output (the pro-drop heuristic)
5. **Anti-translationese** — reduce AI-tells (clichés, mechanical connectors, hyper-formal MSA)

When these conflict, earlier rules win. The 16-dimension analyzer measures (3-5) but trusts the lex pass to preserve (1-2). The pre-flight check (`preflight_check.py`) gates against violating (1) via factual/ethical guards.

## Summary

Reduces AI fingerprints in Arabic text along **16 dimensions** (was 14 prior to Dim 16 الفصل والوصل + Dim 15 typography). Dimensions 14 and 15 are *inverse-scored* (the score measures absence of bad patterns; high score = more restraint / cleaner typography). Combines a deterministic rule-based pass (clause-preserving substitutions + pro-drop deletion, both informed by cross-LLM critique) with an LLM-augmented cognitive pass that works against **any OpenAI-compatible chat-completions endpoint** (configure via `LLM_API_URL` / `LLM_API_KEY` / `LLM_MODEL`). Produces three artifacts per run: transformed text, dimension-by-dimension diagnostic report, and a humanness score (0-100 across 16 dimensions, max 240 points).

## Register taxonomy: it's a POLICY knob, not a linguistic genre

The 4 register options (`classical/news/opinion/technical`) are **product-policy categories** for gating which transformations fire — they are NOT recognized Arabic linguistic genres. An alternative proposed in deep-research (`msa-neutral/msa-helpful/msa-formal/msa-editorial`) is equally engineered-not-linguistic. Both are pragmatic; both are useful; neither maps cleanly to traditional Arabic register theory (فصحى التراث / فصحى المعاصرة / لغة الصحافة / لغة قانونية).

What the 4 register options actually gate (in `humanize_v2.py`):

- `classical` — enables ALL transformations including stylistic variation, rhetorical figures, sentence-length variance
- `opinion` — enables most transformations; allows quote-verb rotation (still env-gated)
- `news` (DEFAULT, SAFE) — skips stylistic risks: no jinas/saj, no quote-verb rotation, no aggressive sentence-length variance
- `technical` — most conservative: no structural-opener rewrites, no sentence-length variance, only typography + dim 14 deletions

Built from research synthesized across **4 LLM critiques** (cognitive-structure, rhetorical decomposition, transitions/literary-art, and historical/coherence perspectives) plus **empirical patterns mined from a reference Arabic corpus** — 100,000 records sampled, **1.31 million sentences and 71.28 million tokens** across four register categories (Qur'an, classical-and-modern prose, news, lexicon). The mining pass tracks 50 connector types and 50 sentence-initial-token types and completes in **≈87 seconds** for the 100K sample.

## Protocol

### Stage 0 — Detect and classify

```bash
python scripts/analyze_deep.py --input <file-or-text> --report
```

Outputs a 13-dimension diagnostic:
- For each dimension, a score 0-15 (judge-like) + diagnostic signals detected
- Overall humanness 0-100
- Recommended `--mode` based on what's weak

### Stage 1 — Lexical/structural pass (deterministic, no LLM)

```bash
python scripts/humanize_v2.py --input <file> --mode lex-only [--intensity 0.5]
```

Applies the deterministic lexical pipeline:
- Phrase substitution from `references/13-inherited-lexical-tables.md`, including:
  - AI-formulaic hedge deletion (`في الواقع`, `بكل تأكيد`, etc. — pro-drop where possible)
  - Clause-preserving formulaic-opener substitution (`أن`-bearing patterns)
  - **English-calque → native Arabic** (v2.2.0) — `خط أنابيب` → `مسار عمل` / `مسار العمل`
- **Calque dictionary** (v2.3.0, news/opinion only) — `corpus/calque-dictionary.json` holds 93 corpus-validated English-calque → natural-Arabic pairs across 9 domains (tech-software, tech-ai-ml, tech-data, tech-security, tech-infra, tech-consumer, business, news-journalism, politics). Built via multi-LLM swarm (Claude Sonnet) + frequency validation against an 8,850-article Arabic tech-news corpus (AITNews). Examples: `بدء التشغيل` → `شركة ناشئة`, `مونيتورينغ` → `مراقبة`, `الإعلام الاجتماعي` → `وسائل التواصل الاجتماعي`, `قطع الأشجار` → `تسجيل` (logging), `الرئيس التنفيذي` (high-confidence: 428 corpus hits).
- Connector swap (breaks the و-monoculture flagged by Dim 16 الفصل والوصل)
- Quote-verb rotation (env-gated only: `HUMANIZER_ALLOW_QUOTE_ROTATION=1`)
- Intensifier de-stacking
- Dim 14 anti-redundancy passes
- Pronoun diversification (register-gated: opinion/classical only)
- Sentence-length variance (register-gated: classical/opinion when intensity > 0.3)
- **Tashkeel reduction** (v2.2.0, register-gated: news/opinion strip; classical/technical preserve)
- Dim 15 typography hygiene (always last)

Deterministic with `--seed`. Reproducible. No LLM call. ~1s runtime.

#### Register × lex-pass gating

| Pass | classical | news | opinion | technical |
|---|:-:|:-:|:-:|:-:|
| Phrase substitution + connector swap | ✓ | ✓ | ✓ | ✓ |
| Pipeline-calque → workflow (v2.2.0) | ✓ | ✓ | ✓ | ✓ |
| Structural opener rewrites | ✓ | ✓ | ✓ | — |
| Quote-verb rotation (env-gated `=1`) | ✓ | — | ✓ | — |
| Pronoun diversification | ✓ | — | ✓ | — |
| Sentence-length variance | ✓ | — | ✓ | — |
| **Tashkeel reduction (v2.2.0)** | — | ✓ | ✓ | — |
| Dim 14 anti-redundancy | ✓ | ✓ | ✓ | ✓ |
| Dim 15 typography hygiene | ✓ | ✓ | ✓ | ✓ |

### Stage 2 — Cognitive pass (LLM-augmented)

```bash
# Set provider env vars once (any OpenAI-compatible endpoint):
export LLM_API_URL=https://api.openai.com/v1/chat/completions
export LLM_API_KEY=sk-...
export LLM_MODEL=gpt-4o-mini

python scripts/humanize_v2.py --input <file> --mode +cognitive --llm-backend api
```

Adds cognitive sophistication along dimensions 1-8:
- **Deduction** (الاستنتاج): inject visible reasoning steps — see `references/01-cognitive-structure.md`
- **Inference** (الاستدلال): argumentation chains using ladder structure
- **Induction** (الاستنباط): from-general-to-specific reframing
- **Human analysis methods** (التحليل البشري): comparison/classification reframing
- **Graduated explanation** (التدرج في الشرح): simple → complex scaffolding
- **Scope definition** (تحديد النطاق): explicit boundary markers
- **Idea transitions** (التنقل في الأفكار): spiral / linear / dialectic flows
- **Axes & data partitioning** (التقسيم للمحاور): orthogonal-axis reframing

Two backend slots are wired in `scripts/llm_transform.py`:

- `api` — any OpenAI-compatible cloud endpoint (no defaults, **must** be configured)
- `local` — defaults to Ollama on `127.0.0.1:11434`

Per-invocation overrides: `--backend-url`, `--auth-token`, `--model`. See `config.example.json` for provider configuration examples (OpenAI, Moonshot, MiniMax, Together, Groq, DeepSeek, etc.).

### Stage 3 — Rhetorical + coherence pass (LLM-augmented)

```bash
python scripts/humanize_v2.py --input <file> --mode +rhetorical --llm-backend api
```

Adds dimensions 9-13:
- **Literary art** (الفن الأدبي): rhythm, imagery, allusion
- **Historical anchoring** (الاستدلال التاريخي): event/historical evidence injection
- **Imagination/concretization** (التخيل): abstract → metaphor
- **Rhetorical figures** (البلاغة): جناس / طباق / سجع / كناية / استعارة used judiciously
- **Non-repetition + intra-text citation** (عدم التكرار + الاستدلال بما تم مناقشته)

### Stage 4 — Score and report

```bash
python scripts/score_humanness.py --before <orig> --after <transformed>
```

Outputs a side-by-side 13-dimension comparison with per-dimension delta. Score promotion bands: 0-40 mediocre, 41-70 good, 71-90 excellent, 91-100 indistinguishable.

### Full pipeline (one command)

```bash
python scripts/humanize_v2.py --input text.md --mode full --llm-backend api --analyze --output humanized.md
```

## Cost and latency

| Mode | LLM calls | Wall-clock per 1000-word input | Cost (depends on provider) |
|---|---|---|---|
| `lex-only` | 0 | ~1s | free (no API) |
| `+cognitive` | 1–2 | ~10–30s | ~1–2K input tokens + ~2–4K output tokens per call |
| `+rhetorical` | 2–3 | ~30–90s | ~3–7K total tokens across passes |
| `full` | 3–5 | ~45–120s | ~5–12K total tokens across passes |

Pick a model that fits your budget. For privacy, route via `--llm-backend local` (Ollama). For absolute reproducibility (no API at all), use `--mode lex-only` or `--mode tighten`.

## Example invocation

```bash
# Diagnose only — find out what's weak
python scripts/analyze_deep.py \
  --input "النص المولد بالذكاء الاصطناعي هنا..." \
  --report

# Light humanize (lexical only — deterministic, no API)
python scripts/humanize_v2.py \
  --input ai-generated.txt \
  --mode lex-only \
  --output light.txt

# Deep humanize (cognitive + rhetorical)
python scripts/humanize_v2.py \
  --input ai-generated.txt \
  --mode full \
  --llm-backend api \
  --output deep.txt \
  --analyze

# Score before/after
python scripts/score_humanness.py \
  --before ai-generated.txt \
  --after deep.txt \
  --json
```

## Worked example (Arabic input → humanized output)

**Input** (AI-generated, register: news, mode: tighten):

```
من المهم ملاحظة أن الاقتصاد السعودي يشهد نموا ملحوظا في القطاعات غير النفطية.
في الواقع، أكدت التقارير أن نسبة المشاركة في سوق العمل ارتفعت بشكل كبير.
علاوة على ذلك، فإن هذا النمو يعكس تنوعا متزايدا في مصادر الدخل.
```

**Command:**

```bash
python scripts/humanize_v2.py \
  --input above.txt --mode tighten --register news \
  --analyze --output cleaned.txt
```

**Output** (lex-only pass; pro-drop deletions removed `من المهم ملاحظة أن`, `في الواقع`, and the connector `علاوة على ذلك` is swapped to `كما أن`):

```
يشهد الاقتصاد السعودي نموا ملحوظا في القطاعات غير النفطية.
أكدت التقارير أن نسبة المشاركة في سوق العمل ارتفعت بشكل كبير.
كما أن هذا النمو يعكس تنوعا متزايدا في مصادر الدخل.
```

**Dimensions that fired:** Dim 14 (reader-respect, +3 from removing 2 hedges), Dim 16 (الفصل والوصل, +2 from connector diversification), Dim 15 (typography unchanged — input already clean). Net humanness delta: ~+5/240, runs in <1s, no API call.

## Pairing (optional, if available in your environment)

- **A lexical-only sibling humanizer** — If you have a faster, lexical-only Arabic humanizer (or this skill's `--mode lex-only`), use it when only surface-level changes are wanted.
- **An Arabic morphology/syntax engine** (e.g., camel_tools, or any ishtiqaq/nahw/sarf rule engine) — The rhetorical pass benefits from grammatical validation but does not require it.
- **The mined corpus** — `corpus/empirical-patterns.json` ships pre-computed (100K records / 1.31M sentences / 71.28M tokens / ≈87s mining time across 4 register categories); runtime needs no corpus access. To re-mine against your own JSONL, set `ARABIC_CORPUS_PATH` and run `scripts/mine_corpus.py`.
- **An "inversion" or "adversarial review" skill**, if you have one — useful for pre-analysis ("what would the AI-shape failure look like?") and post-pass cross-LLM challenge before publication.

## References

Each dimension has its own deep-dive file. The synthesis pulled from 4 LLM critiques + 100K-record corpus mining.

- `references/01-cognitive-structure.md` — Deduction, inference, induction (dims 1-3, 4) + scope (dim 6)
- `references/02-graduated-explanation.md` — Simple → complex scaffolding (dim 5)
- `references/03-idea-transitions.md` — Spiral / linear / dialectic flows (dim 7)
- `references/04-axes-and-data-partitioning.md` — Orthogonal-axis decomposition (dim 8)
- `references/05-literary-art.md` — Aesthetic / الفن الأدبي (dim 9)
- `references/06-historical-anchoring.md` — Event-based & historical evidence (dim 10)
- `references/07-imagination-concretization.md` — Abstract → metaphor (dim 11)
- `references/08-rhetorical-figures.md` — جناس / طباق / سجع / كناية / استعارة (dim 12)
- `references/09-coherence-non-repetition.md` — Non-repetition + intra-text citation (dim 13)
- `references/10-register-modulation.md` — MSA layer modulation (elevate vs. ground)
- `references/11-sentence-rhythm.md` — Length variance, parallelism breaks
- `references/12-corpus-findings.md` — Empirical statistics from the reference-corpus mining
- `references/13-inherited-lexical-tables.md` — Deterministic lexical-substitution tables
- `references/14-reader-respect.md` — Reader-respect / احترام عقل القارئ (INVERSE-scored: anti-tautology, anti-re-explanation, surprise, leave-deduction-to-reader, productive ambiguity)
- `references/15-typography-hygiene.md` — Typography hygiene / نظافة الصياغة (INVERSE-scored, mechanical: Arabic-English spacing, Arabic punctuation, paren spacing, numbering, tables)
- `references/16-fasl-wa-wasl.md` — الفصل والوصل (DISTRIBUTIONAL — Shannon entropy of connector diversity; monoculture of `و` flagged as 2/15, classical-rich connector distribution scores 13-15/15)
- `scripts/preflight_check.py` — Factual / ethical / sourcing-hygiene pre-flight check (flags unsourced statistics, named-quote attributions, loaded group generalizations, anonymous-source chains, sweeping claims, hostile attribution verbs). FLAGS only — does NOT transform.

## Composing with a lexical-only sibling

If you also have access to a lighter lexical-only Arabic humanizer (or use this skill's `--mode lex-only`), the run-order matters:

| Order | Result | Recommended? |
|---|---|---|
| **This skill alone** | Full 16-dim transformation with register-aware gating | ✅ Recommended for sophisticated text |
| **Lex-only sibling alone** | Lexical-only humanization, ~1s | ✅ Use when speed > sophistication |
| **Sibling → this skill** | This skill receives lex-cleaned input, adds cognitive layer | ✅ Acceptable but redundant (this skill already runs the lex pass) |
| **This skill → sibling** | Sibling's lex pass flattens cognitive/rhetorical structure | ❌ DO NOT — undoes the cognitive work |
| **`--mode tighten`** | Inverse-scored dims 14+15 only — newsroom subediting | ✅ Recommended for news copy |

For English text, route to `scripts/humanize_english.py` (5-axis rubric, deterministic lex pass — see `references/17-english-ai-tells.md`). For other languages, use a language-specific humanizer.

## Pipeline composition

Within this skill, run-order matters. The DEFAULT pipeline is:

```
[Input Text]
    ↓
[Pre-flight check (--preflight)]  → flags factual/ethical issues; does NOT transform
    ↓
[Lex pass (register-aware)]  → safe normalization
    ↓
[Cognitive pass (--mode +cognitive/+rhetorical/full)]  → LLM-augmented (needs proxies)
    ↓
[Typography hygiene (always last)]  → normalize Arabic-English spacing + punctuation
    ↓
[Diagnostic report]
```

**Recommended mode for unknown content**: `--mode tighten --register news --preflight` — runs the pre-flight check, then tightens only (deletions + typography), no risky additions.

**Known future work** (raised by cross-LLM critique, not yet addressed):
- Factual/ethical guardrail integration (currently a separate script; could be wired as pre-flight stage)
- إيحاء/كناية framing as deeper sub-dimension of dim 14 (editorial finding)
- Stratified corpus mining (genre-weighted sampling instead of 100K sequential)
- Positive-polarity score reframing (dim 14 → "Cognitive Restraint Score", dim 15 → "Typographic Precision Score")
- `corpus/empirical-patterns.json` — Machine-readable corpus statistics (consumed by scripts)
- `scripts/analyze_deep.py` — 13-dimension diagnostic analyzer (replaces v1's lexical-only `analyze_text`)
- `scripts/humanize_v2.py` — Multi-pass transformation pipeline (replaces v1's single-pass `humanize`)
- `scripts/mine_corpus.py` — One-time corpus miner (produces empirical-patterns.json)
- `scripts/score_humanness.py` — 13-dimension scoring rubric
- `scripts/llm_transform.py` — LLM-call wrapper with OpenAI-compatible-API + local-Ollama routing

## Version history

| Version | What changed |
|---|---|
| **v2.7.2** | **`ARABIC_CORPUS_TOOLKIT_DISABLE=1` env var added.** Closes the operational-tooling gap noted in v2.7.1: previously there was no way to force the inline-fallback code paths even by pointing `ARABIC_CORPUS_TOOLKIT_ROOT` at a nonexistent directory (the loader still fell through to the default sibling-path). The new flag is the explicit kill-switch: set to the literal string `"1"` (not `"true"`, not `"yes"`, not truthy — strict literal match, DEBUG=1 convention) and both Asset A (calque dictionary) and Asset C (lexical tables) skip toolkit loading entirely, using the in-code literals/vendored copy. Centralized in `_toolkit_disabled()` helper — both loaders call it. This was a prerequisite for the v2.8.0 vendored-literal removal: that release needs to test the in-code fallback in isolation to prove behavioral equivalence with the toolkit-backed path; before v2.7.2 there was no clean way to do that. **Eval evidence: four quadrants — toolkit-enabled × {Arabic 74/74, English 33/33} + toolkit-disabled × {Arabic 74/74, English 33/33} = 428/428 assertions across the matrix.** Plus flag-semantics test: `DISABLE=true` (non-literal-1) correctly keeps toolkit active, confirming strict flag matching. No content changes, no projection changes — only an opt-in escape hatch. |
| **v2.7.1** | **Asset C cutover: lexical tables now read from `arabic-corpus-toolkit` by default.** Second cutover in the Asset-A pattern established by v2.7.0. When `arabic-corpus-toolkit/corpus/lexical-tables.json` is present (sibling path, overridable via `ARABIC_CORPUS_TOOLKIT_ROOT` env var), the six tables defined at the top of `humanize_v2.py` (AI_PHRASES_AR, CONNECTORS_AR, REPETITIVE_STARTERS_AR, STRUCTURAL_OPENERS_AR, QUOTE_VERBS_ROTATION, INTENSIFIER_DESTACK) are overridden with the toolkit's canonical values via `_project_toolkit_lexical_tables()` — a 6-line projection from the toolkit's list-of-objects shape to the humanizer's dict / list-of-tuples / list-of-strings shapes. The in-code literals (lines 51-209) remain as the fallback. Major-version refuse: if the toolkit asset is `$schema_version` 2.x or higher, the loader refuses to use it (consumer needs update). Cutover was gated on toolkit v0.7.1's parity-audit work (`arabic-corpus-toolkit/references/05-asset-c-migration-audit.md`) which reconciled the toolkit asset to the v2.7.0 humanizer code after v0.7 was found to be migrated from stale documentation. **Eval evidence: 74/74 Arabic + 33/33 English with toolkit backing, 74/74 + 33/33 with toolkit env-var override path** — behaviorally identical to v2.7.0 across both code paths. The cutover commits Asset C to the same removal trajectory as Asset A: vendored literals removed in v2.8.0 once toolkit is a hard dependency. |
| **v2.7.0** | **Toolkit integration: humanizer now reads from `arabic-corpus-toolkit` by default.** Per the v2.6.0 multi-agent review's architectural recommendation (Agent C: scope critic), the calque dictionary becomes shared infrastructure. `_load_calque_dictionary()` rewritten with a two-tier resolution: (1) Preferred — load from `arabic-corpus-toolkit/corpus/calque-dictionary.json` (sibling path; overridable via `ARABIC_CORPUS_TOOLKIT_ROOT` env var). (2) Fallback — load from the local vendored copy (v2.5.x and earlier behavior). The internal lookup shape unchanged from v2.6.4, so `lex_apply_calque_dictionary()` and `_matches_topic()` are untouched. The vendored `corpus/calque-dictionary.json` remains in this repo through v2.7.x as a compat-shim source; it will be removed in v2.8.0 once the toolkit is a hard dependency. Eval evidence: Arabic fragility 74/74, English fragility 33/33 — same numbers as v2.6.4, no regression. End-to-end test shows the full v2.6.x pipeline (verb-agreement + pro-drop + topic-guards) working identically through the toolkit-backed loader. Refactored helper `_build_lookup_from_entries()` shared by both code paths — single source of truth for the schema-to-internal-shape conversion. The vendored copy and the toolkit copy are byte-identical at v2.7.0 ship (both are humanizer v2.6.4 state); divergence will only start once toolkit v0.4+ ships new schema additions ahead of the humanizer's adoption. |
| **v2.6.4** | **Verb-subject agreement validator + formal eval coverage for v2.6.3 topic-guards.** Two-part shipment: (1) New `scripts/verb_agreement_validator.py` implements Agent A's #2 missing-feature finding from the v2.6.0 review. Detects sound-feminine-plural nouns (ending in `ـات`) followed within ~30 chars (allowing one intervening particle `قد`/`لم`/`لا`/`لن`/`ما`/`لقد`/`سوف`) by a verb in masculine-plural form (`ـوا` suffix), and corrects to the singular-feminine form (`ـت`). 42 curated verb pairs covering high-frequency newsroom verbs (`أعلنوا→أعلنت`, `قالوا→قالت`, `ذكروا→ذكرت`, `أكدوا→أكدت`, `وافقوا→وافقت`, …). Wired into `humanize_v2.py::lex_pass()` right after the orthographic validator — runs in ALL registers because the rule (`جمع مؤنث سالم` takes singular-feminine verb for non-human plurals, never masculine-plural) is invariant across registers. (2) Eval suite expanded from 66 to **74 assertions** with T29 (v2.6.3 topic-guard behavior — 4 sub-checks including the critical `رؤية 2030`-with-tech-keywords mixed-context case) and T30 (v2.6.4 verb-agreement — 4 sub-checks including direct error, intervening particle, distant-subject negative, and correct-usage-unchanged). Conservative scoping: distant subjects (separated by comma + new noun phrase) correctly preserved. End-to-end verified: input `الحكومات أعلنوا عن خطة جديدة. في الواقع، الشركات اتفقوا أيضاً.` → output `الحكومات أعلنت عن خطة جديدة. حقيقة، الشركات اتفقت أيضا.` — both verb-agreement corrections fire, AI-tell `في الواقع` deleted. New `references/21-verb-agreement-validator.md`. English fragility 33/33 (no regression). |
| **v2.6.3** | **Topic-guarded re-add of the 6 bare-stem entries deleted in v2.6.0.** Restores translation coverage for the database/OS/scheduling/threading senses of `view`, `partition`, `trigger`, `process`, `task`, `worker` — but each entry now carries a mandatory two-layer defense: (a) **positive context gate** — at least 1 of `context_keywords_arabic` + `context_keywords_english` must appear within ±100 chars of the candidate match (e.g., `view` only fires when surrounding context contains `قاعدة البيانات` / `جدول` / `SELECT` / `MySQL` / etc.); (b) **negative exclusion patterns** — `رؤية\s+\d{4}` blocks the substitution even when tech context surrounds the Vision XXXX pattern (load-bearing for `رؤية 2030` Saudi national vision use cases). New JSON fields: `context_keywords_arabic`, `context_keywords_english`, `context_keywords_required_count`, `exclude_if_pattern`. **`lex_apply_calque_dictionary` refactored** to walk per-match (right-to-left for offset stability) when an entry is topic-guarded; unguarded entries preserve v2.3.0 unconditional-substitution behavior. Verified end-to-end with three behavioral tests: pure-political context (preserves `رؤية 2030`), pure-tech context (fires `رؤية → عرض`), mixed context with year suffix (still preserves `رؤية 2030` — exclude_if_pattern wins). 6 new dictionary entries; 4 new optional schema fields. Arabic fragility 66/66, English fragility 33/33 — no regression. New `references/20-context-keywords-gate.md`. |
| **v2.6.2** | **Orthographic validator wired into the lex pass; proclitic-boundary fix landed.** Two-part shipment: (1) `scripts/orthographic_validator.py::fix_hamzat_alwasl()` rewritten from regex-with-`\b` to direct `str.replace`. Form-X verbal nouns are unique enough strings that substring substitution is safe AND automatically handles four classes of compound forms that the regex approach missed: **proclitics** (`لإستقرار → لاستقرار`, `بإستراتيجية → باستراتيجية`), **multi-proclitic combinations** (`وبإستثمار → وباستثمار`), **definite article** (`الإستخدام → الاستخدام`), and **inflections** (`إستخداماته → استخداماته`). (2) `humanize_v2.py::lex_pass()` now calls `fix_hamzat_alwasl()` at the START of every mode (enrich / tighten / standard), in ALL registers (form-X verbal nouns take hamzat al-waṣl regardless of register — the AI-tell is universal). End-to-end verified: a 6-error sample input including all 4 compound-form classes round-trips correctly through `lex-only` mode. Both eval suites remain green: Arabic 66/66, English 33/33. References/19-orthographic-validator.md updated to mark the v2.6.1 proclitic limitation as **resolved in v2.6.2 via the str.replace approach** instead of the originally-planned lookbehind-aware regex (simpler, correct, and provably handles all four compound-form classes). |
| **v2.6.1** | **Sacred-text guard wired into the pipeline + orthographic validator module.** Two of the deferred items from the v2.6.0 multi-agent review landed: (1) `scripts/humanize_v2.py::run_pipeline()` now masks Quranic verses / hadith citations / basmala via `sacred_text_guard.mask_sacred_spans()` BEFORE the lex pass and restores via `restore_sacred_spans()` at every return point. Pipeline log includes a new `sacred_guard` stage entry with `spans_locked` count and reasons. The v2.6.0 module is now actually used by default — religious-publication deployments no longer require manual mask/restore calls. (2) New `scripts/orthographic_validator.py` ships the hamzat al-waṣl/qaṭʿ corrector that Agent A flagged as "#1 visible AI-Arabic tell after connector mismatches." 50 form-X verbal-noun corrections (`إستخدام → استخدام`, `إستراتيجية → استراتيجية`, `إستثمار → استثمار`, …), curated from native-MSA editorial practice + UN/IPCC/Aljazeera Arabic. Module ships standalone in v2.6.1; wiring into `humanize_v2.py`'s lex pass is v2.6.2. Known limitation: proclitic-prefixed forms (`لإستقرار`, `بإستراتيجية`) miss the `\b` word boundary — addressed in v2.6.2. New `references/19-orthographic-validator.md`. Both eval suites still green: Arabic 66/66, English 33/33. End-to-end pipeline test verified `قال رسول الله ﷺ: «إنما الأعمال بالنيات»` is preserved bytes-identical when the surrounding prose is humanized. |
| **v2.6.0** | **Linguistic emergency triage + sacred-text guard.** Acting on a native-MSA-tier multi-agent review of v2.5.1, the calque dictionary received surgical fixes for 14 entries: **6 deleted** (`view`, `partition`, `trigger`, `process`, `task`, `worker` — bare-stem entries with no topic guards that would corrupt across domains, including `view → مشاهدة` rewriting `رؤية 2030` into `مشاهدة 2030`); **6 fixed** (`personalization` had the direction REVERSED: `الشخصنة` is the attested modern term, `التخصيص` reads as "privatization" in Saudi context; `fundraising` conflated charity-donations with VC-fundraising — now maps to `جمع التمويل`; `venture capital` corrected to corpus-attested `رأس المال المخاطر`; `fake news` sign-flip resolved to `الأخبار الكاذبة`/`المفبركة`; `global warming` no longer collapses with greenhouse effect; `grassroots` neutral pan-Arab `حركة قاعدية` over politically-loaded `حركة شعبية`); **2 annotated** (`refugee` and `displaced person` paired with `disambiguation_pair_id: refugee-vs-displaced-person` and high political_sensitivity to prevent silent swaps in Gaza/Sudan/Syria reporting). New dictionary schema fields: `regional_sensitivity` (gulf/levant/maghreb/pan-arab), `political_sensitivity` (none/low/medium/high/critical), `disambiguation_pair_id`, `disambiguation_warning`, `applies_only_in_domain`. **New `scripts/sacred_text_guard.py`** — detects Quranic verses (U+06D6-U+06ED tajweed-mark clustering), citation framing (`قال تعالى:`, `يقول تعالى`), hadith chains (`قال رسول الله ﷺ`, `روى البخاري عن`), and the basmala; returns `(start, end, reason)` spans that downstream transformations MUST preserve verbatim. Conservative by design — high precision over recall. Exposes `mask_sacred_spans()` / `restore_sacred_spans()` helpers mirroring the code-block protection pattern from humanize_english.py T3. New `references/18-sacred-text-guard.md`. Arabic 16-dim pipeline still untouched (humanize_v2.py unchanged); fragility still 66/66. English fragility 33/33. Multi-agent review evidence preserved at `M:\Main\AI\Corpus\humanizer-v2.6-multi-agent-synthesis.md`. |
| **v2.5.1** | **Critical hotfix from multi-agent review.** Five bugs in the v2.5.0 English path fixed: (T1) `skip_when_context` rewritten to compare *input* ±2-word window to skip phrases instead of pattern-to-skip-list — `actually`/`literally`/`really` now actually get deleted in filler use while `literally on fire` is preserved as designed; (T2) `--force-language en` no longer silently no-ops on Arabic input — it refuses with explanatory stderr; (T3) Markdown code-block protection: fenced ` ``` ` and inline `code` are extracted before transformation and restored verbatim afterward, so `def navigate()` inside a code fence isn't rewritten to `def handle()`; (T7) findings de-duplicated by `(start, end)` span before scoring — `Look,` no longer counts twice for the same character span; (T8) case-preserving substitution helper added — `Navigate` → `Handle` (was `handle`); `NAVIGATE` → `HANDLE`. Also: (T5) LICENSE adds Hardik Pandya copyright line for MIT redistribution compliance; (T6) `--seed` flag added as documented (was vapor-doc'd in v2.5.0). Eval suite **rewritten from 21 to 33 assertions** — the v2.5.0 suite passed only because the tests exercised the bugs as features (E8 passed because `literally` was never deleted globally; E4c only checked exit code 0). Multi-agent review credited in `M:\Main\AI\Corpus\humanizer-v2.6-multi-agent-synthesis.md`. Arabic 16-dim pipeline unchanged; 66/66 fragility holds. |
| **v2.5.0** | **English support added (secondary language).** New `scripts/humanize_english.py` — deterministic lex pass + 5-axis Directness/Rhythm/Trust/Authenticity/Density rubric (max 50; revise below 35). New `corpus/english-patterns.json` machine-readable pattern catalogue (throat-clearing openers, emphasis crutches, business jargon substitutions, filler adverbs, filler phrases, meta-commentary, binary contrasts, negative listings, dramatic fragmentation, rhetorical setups, false agency, narrator-from-distance, Wh- starters, lazy extremes, em-dash normalization). New `references/17-english-ai-tells.md` narrative reference. Lexical/structural/sentence-level catalogue and the 5-axis rubric adapted from [`hardikpandya/stop-slop`](https://github.com/hardikpandya/stop-slop) (MIT) with attribution preserved in both the JSON catalogue and the reference doc. Three operating modes (`analyze`, `lex`, `both`). Language gate: `detect_language()` counts Arabic-block vs ASCII letters; refuses to process Arabic input. Arabic 16-dimension pipeline (`humanize_v2.py`) unchanged. No regression — Arabic fragility suite still 66/66. |
| v2.4.5 | **User-reviewed corrections + word-boundary fix.** Native-speaker review caught two dictionary issues: (1) `swarm intelligence` natural form `ذكاء الأسراب` (biological swarms) → `ذكاء المجموعة` (group — neutral CS term); plural form `ذكاء الأسراب` added as separate calque key. (2) New entry `سلوكا` → `أسلوبا` (mansoob accusative form only) for AI-translated 'approach' / 'method' where the LLM picked behavior-sense; conservative key avoids false positives on bare سلوك in psychology contexts. **Critical underlying fix:** `lex_apply_calque_dictionary` substitution engine now uses word-boundary lookahead `(?![؀-ۿ])` to prevent the calque key from matching INSIDE a longer Arabic word. Example: `ذكاء السرب` no longer falsely matches inside `الذكاء السربي` (adjectival form). This protects every dictionary entry from substring-substitution bugs. T27+T28 added (5 sub-checks). Fragility now **66/66**. |
| v2.4.4 | **List-`و` insertion + register-gated guillemets.** Itwadi rule: insert `و` before list items 2..n when 3+ single-word Arabic tokens are comma-separated. Short-clause commas not treated as lists. Register-gated quotation: ASCII `"..."` → `«...»` ONLY in classical register. T25+T26 added (5 sub-checks). Fragility now **61/61**. |
| v2.4.3 | **Parenthesis interior-spacing normalization.** Researched 4 more Arabic style guides (Albuthi, Alukah academic, proof-reading-service, Kaplan International — 13 total now). The new rule from Kaplan + proof-reading-service: "no spacing between brackets and content". `typography_paren_interior_spacing()` (1) strips space immediately after `(` when followed by Arabic letter, (2) strips space before `)` when preceded by Arabic letter, (3) strips space between `)` and following punctuation. Example: `هذه جملة ( مع تعليق ) ، ثم آخر` → `هذه جملة (مع تعليق)، ثم آخر`. Preserves existing Latin-content paren padding (for English-in-Arabic Bidi clarity). 5 new fragility sub-checks (T23–T24). Fragility now **56/56**. |
| v2.4.2 | **Authoritative-source-based punctuation rules.** Researched 9 Arabic style guides (Al Jazeera Learning, Drasah, Loghate ×2, Mawdoo3, Mobt3ath, KSU College of Humanities, Itwadi, Shoair School). Implemented: (1) **No space before Arabic punctuation** (`،`، `؛`، `؟`، `:`، `!`، `.`) — the universal rule from all sources ("ملاصقة للكلمة التي قبلها"). (2) **Comma → semicolon before unambiguous causal connectors** (`لأن`، `لأنّ`، `لذلك`، `لذا`، `ومن ثَمَّ`) — semicolon is the correct mark before causal clauses per multiple sources; ambiguous connectors (`إذ`، `حيث`) skipped to avoid false conversions ("when"/"where" vs "because"). (3) Made existing Latin→Arabic punctuation rules explicit via T19-T21 tests (formerly inherited from v1, now fragility-guarded). Deferred to v2.4.3: list-conjunction `و` between Arabic list items (requires multi-pass context detection), LRM-Bidi handling (render-time concern). Fragility suite now **51/51**. |
| v2.4.1 | **Typography fixes** — two AI-Arabic tells that v2.2.0–v2.4.0 didn't catch: (1) **Kashida (Arabic tatweel `ـ`, U+0640) stripped** from output per modern editorial convention — kashida is for display typography (logos, posters, justified-text rendering at typeset time), NEVER for encoded body text; AI translators sometimes inject it to "look more Arabic" which is the exact opposite of professional Arabic typography. Stripping is UNIVERSAL (all registers), not register-gated. (2) **Em-dash `—` converted to Arabic comma `،`** when surrounded by Arabic letters (e.g., `النص — التعليق` → `النص، التعليق`); preserved in English-context (e.g., `OpenAI — مؤسسة` keeps em-dash because `I` is Latin). 4 new fragility test sub-checks (T15–T17). Fragility suite now **35/35**. |
| v2.4.0 | **Dictionary expansion — 93 → 338 entries (3.6×).** Adds process/workflow, agents/swarm/multi-agent (modern AI vocabulary not in v2.3.0), expanded database, DevOps/cloud-native, crypto/Web3, healthcare, climate, geopolitics. New domains: `tech-ai-agents` (35), `tech-crypto` (15), `climate` (15), `healthcare` (11). Expanded domains: `tech-software` (44, +35), `tech-infra` (36, +26), `news-journalism` (44, +28), `business` (43, +27), `tech-security` (31, +20). Built via Claude+Codex multi-LLM swarm on 361 seed terms (300 yielded responses; partial promoted to final because of CLI rate-limit stall on the tail batch); 151 `medium_consensus` entries reflect multi-LLM agreement strength. **Lex pass unchanged** — same `lex_apply_calque_dictionary()`, just more data. Fragility still 31/31. |
| v2.3.0 | **Calque-translation dictionary** — initial release. `corpus/calque-dictionary.json` (93 entries, 9 domains, 27 high-confidence + 66 medium). Built via multi-LLM swarm (Claude Sonnet) on 181 seed English terms, validated against an 8,850-article Arabic tech-news corpus (AITNews; 2.88M tokens). New `lex_apply_calque_dictionary()` runs in news/opinion registers (classical/technical preserve source). Double-ال handling for substitutions where input has definite article but key/natural don't agree on prefix. 3 new fragility test classes (T12–T14): dictionary-load verification, multi-domain calque catches, register-gating. Fragility suite now 31/31. |
| v2.2.0 | `lex_reduce_tashkeel()` added — strips 9 canonical combining diacritics in news/opinion (classical/technical preserve). Hamza-safe (preserves أ إ آ ء ؤ ئ ى) and digit-safe (preserves ٠–٩). Pipeline-calque `خط أنابيب` → `مسار عمل` / `مسار العمل` / `تسلسل العمل` added to `AI_PHRASES_AR`. Five new fragility test classes (T7–T11): hamza preservation, madda preservation, digit preservation, calque substitution, register-gated tashkeel policy. |
| v2.1.3 | Arabic editorial pass on documentation: replaced English-calque "pipeline" with "مسار عمل" in README.ar.md; reduced ~96% of tashkeel marks in prose; preserved classical-Arabic quotations within `«»` / `""` brackets. |
| v2.1.2 | `examples/` directory added — 6 byte-deterministic worked examples covering register × mode combinations. README + README.ar.md gained source-size + effort disclosure. |
| v2.1.1 | Corpus-stats refactor: replaced `8.5 GB classical-Arabic dataset` wording with lexicon-level statistics (1.31M sentences / 71.28M tokens / 4 register categories / ~87s mining time). Multi-LLM CLI security audit (regex + Claude Sonnet + Codex). Hardcoded path leak in `corpus/empirical-patterns.json` redacted. |
| v2.1.0 | Provider-agnostic refactor. `BACKENDS` dict collapsed from `kimi`/`minimax`/`local` to `api`/`local`. Universal env vars `LLM_API_URL` / `LLM_API_KEY` / `LLM_MODEL`. CLI overrides `--backend-url`/`--auth-token`/`--model`. `INSTALL-FOR-KIMI.md` added (markdown installer for Kimi CLI which doesn't import .skill ZIPs). |
| v2.0.0 | Initial public release. 16-dimension humanness framework, 6 modes, 4 register policies, cross-LLM-critique-informed lexical layer, pre-flight safety check, 20 golden tests + 12 fragility assertions. |

## Anti-Patterns (NEVER do)

- NEVER apply `+rhetorical` to technical specifications, legal text, or code documentation — embellishment is harmful here
- NEVER apply ALL 13 dimensions at maximum intensity to the same text — produces parody, not human-like prose; pick the 2-3 weakest per the analyzer
- NEVER skip stage 0 (diagnostic) — random transformation degrades text that's already mostly human
- NEVER bypass `--seed` reproducibility when running in production — same input must produce same output
- NEVER feed dialect/colloquial Arabic into this skill — it targets MSA / classical-leaning register only
- NEVER use the rhetorical-figure injector without consulting `references/08-rhetorical-figures.md` for the "when NOT to use جناس/طباق" warnings
- NEVER call `humanize_v2.py` (the Arabic pipeline) on English text — it will produce garbage; route English through `humanize_english.py` instead
- NEVER call `humanize_english.py` on Arabic text — the language-detection gate will refuse, but explicit `--force-language en` would corrupt Arabic prose
- NEVER trust the humanness score as ground truth — it's a heuristic that approximates a human reader, not a perfect detector
- NEVER overwrite the input file without `--inplace --confirm` — default is write to `--output` path
- NEVER include PII in test runs — the LLM-augmented modes send content to whichever cloud endpoint `LLM_API_URL` points at; route sensitive content through `--llm-backend local` (or stay in `--mode lex-only`/`tighten`) instead
