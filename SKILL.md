---
name: ai-text-humanizer
description: Arabic-text humanizer scoring along 16 dimensions — cognitive structure, rhetorical figures, reader-respect, typography hygiene, and connector entropy. Six modes and four register policies gate which transformations fire; a pre-flight safety check flags factual/ethical/sourcing hazards. Scope is humanization, NOT localization — BCP47, ICU, SSML are out of scope. Provider-agnostic; works with any OpenAI-compatible LLM. Use when the user wants Arabic AI text rewritten with cognitive depth and classical-rhetoric awareness; also triggers on "humanize deep", "humanize cognitively", "humanizer v2", or "تحويل النص إلى أسلوب بشري عميق". Do NOT use for technical specs, code documentation, legal text, dialect-heavy/colloquial content, already-human text (run analyze-only instead), or English (Arabic-only).
---

# Arabic AI-Text Humanizer — Cognitive + Rhetorical + Reader-Respect Layer

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
- Phrase substitution from `references/13-inherited-lexical-tables.md`
- Connector swap
- Sentence-starter diversification
- Structural pattern breaking
- Rhythm variance (sentence-length variation)

Deterministic with `--seed`. Reproducible. No LLM call. ~1s runtime.

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
من المهم ملاحظة أن الاقتصاد السعودي يشهد نمواً ملحوظاً في القطاعات غير النفطية.
في الواقع، أكدت التقارير أن نسبة المشاركة في سوق العمل ارتفعت بشكل كبير.
علاوة على ذلك، فإن هذا النمو يعكس تنوعاً متزايداً في مصادر الدخل.
```

**Command:**

```bash
python scripts/humanize_v2.py \
  --input above.txt --mode tighten --register news \
  --analyze --output cleaned.txt
```

**Output** (lex-only pass; pro-drop deletions removed `من المهم ملاحظة أن`, `في الواقع`, and the connector `علاوة على ذلك` is swapped to `كما أن`):

```
يشهد الاقتصاد السعودي نمواً ملحوظاً في القطاعات غير النفطية.
أكدت التقارير أن نسبة المشاركة في سوق العمل ارتفعت بشكل كبير.
كما أن هذا النمو يعكس تنوعاً متزايداً في مصادر الدخل.
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

Arabic only — for English text use a separate English-targeted humanizer.

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

## Anti-Patterns (NEVER do)

- NEVER apply `+rhetorical` to technical specifications, legal text, or code documentation — embellishment is harmful here
- NEVER apply ALL 13 dimensions at maximum intensity to the same text — produces parody, not human-like prose; pick the 2-3 weakest per the analyzer
- NEVER skip stage 0 (diagnostic) — random transformation degrades text that's already mostly human
- NEVER bypass `--seed` reproducibility when running in production — same input must produce same output
- NEVER feed dialect/colloquial Arabic into this skill — it targets MSA / classical-leaning register only
- NEVER use the rhetorical-figure injector without consulting `references/08-rhetorical-figures.md` for the "when NOT to use جناس/طباق" warnings
- NEVER call this skill for English text — this skill is Arabic-only; use an English-targeted humanizer for English
- NEVER trust the humanness score as ground truth — it's a heuristic that approximates a human reader, not a perfect detector
- NEVER overwrite the input file without `--inplace --confirm` — default is write to `--output` path
- NEVER include PII in test runs — the LLM-augmented modes send content to whichever cloud endpoint `LLM_API_URL` points at; route sensitive content through `--llm-backend local` (or stay in `--mode lex-only`/`tighten`) instead
