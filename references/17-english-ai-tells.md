# 17 — English AI-Tells (5-axis rubric + pattern catalogue)

Loaded when the user wants the English path (`scripts/humanize_english.py`). For Arabic, the 16-dimension framework in references/01-16 is canonical; this file does NOT apply to Arabic input.

## Provenance

The lexical / structural / sentence-level pattern catalogue and the 5-axis scoring rubric (Directness · Rhythm · Trust · Authenticity · Density) are adapted from [`hardikpandya/stop-slop`](https://github.com/hardikpandya/stop-slop) (MIT). The upstream skill is a markdown-only LLM editing skill — patterns expressed as rules the LLM applies during writing. This humanizer ports that catalogue to:

1. **`corpus/english-patterns.json`** — machine-readable form with per-pattern `action` (delete / substitute / flag) annotations
2. **`scripts/humanize_english.py`** — deterministic CLI runner with the 5-axis scorer; no LLM required for the lex pass

Both projects are MIT-licensed; redistribution preserves stop-slop's attribution.

## Why a separate path (English ≠ Arabic 16-dim)

The 16-dimension Arabic framework is built around features that don't transfer to English: classical-rhetorical figures (جناس / طباق / سجع), connector entropy specific to Arabic's coordinator-heavy syntax (Dim 16 الفصل والوصل), tashkeel normalization, kashida stripping, Arabic-specific typography hygiene (Dim 15). A 16-dim English path would be ⅔ inapplicable.

Stop-slop's 5-axis rubric is tuned for English: Directness · Rhythm · Trust · Authenticity · Density. These DO transfer cleanly and are orthogonal enough to score without over-counting. The deterministic implementation here treats them as inverse-weighted: high score = absence of the corresponding AI tells.

## The 5 axes

| Axis | What it measures | Drops when |
|---|---|---|
| **Directness** | Statements vs announcements | Throat-clearing openers, emphasis crutches, vague declaratives, meta-commentary |
| **Rhythm** | Varied vs metronomic | 3+ consecutive same-length sentences, sentence-length stdev < 4 words, staccato fragmentation |
| **Trust** | Respects reader intelligence | Meta-commentary, rhetorical setups, negative listings, filler phrases |
| **Authenticity** | Sounds human | Business jargon, false agency (inanimate verbs), narrator-from-distance voice |
| **Density** | Anything cuttable | Filler adverbs, filler phrases, lazy extremes, em-dashes |

Each axis scored 1-10; total max 50. **Below 35 = revise** per upstream's threshold.

## The three detection layers

### Lexical (catalogue-based)

Action per category in `corpus/english-patterns.json`:

| Category | Default action | Auto-safe? |
|---|---|---|
| `throat_clearing_openers` | delete | ✅ — opener removal is safe |
| `emphasis_crutches` | delete | ✅ — "Let that sink in." removable |
| `business_jargon` | substitute | ✅ — table-mapped to plain language |
| `filler_adverbs` | delete | ⚠️ — strips most adverbs; load-bearing contexts in skip-list |
| `filler_phrases` | delete | ✅ — "At its core,", "In today's X" removable |
| `meta_commentary` | delete | ✅ — self-referential asides are noise |
| `vague_declaratives` | flag | ❌ — needs human to fill specifics |

### Structural (regex + multi-sentence)

These require **context** to fix correctly. The script flags but does NOT auto-transform:

- `binary_contrasts` — "Not X. It's Y." — needs human to choose which half to keep
- `negative_listings` — "Not A... Not B... It was C." — pick C and rewrite
- `dramatic_fragmentation` — "X. That's it. That's the Y." — collapse to one sentence
- `rhetorical_setups` — "What if I told you..." — make the point directly
- `false_agency` — "the decision emerges" — name the actor
- `narrator_from_a_distance` — "Nobody designed this." — put the reader in the room

### Sentence-level (positional)

- `wh_starters` — Wh-words at sentence start (flagged; restructure manually)
- `paragraph_starter_blacklist` — paragraphs that open with "So," / "Look," (flagged)
- `lazy_extremes` — "every / always / never / everyone / nobody" (flagged; replace with specifics)
- `em_dashes` — substituted with comma (stop-slop's "No em dashes at all" rule)

## When the deterministic pass is enough

For most English AI prose, the lex pass alone produces a meaningful improvement:
- Score uplift typically **+5 to +15** points on stop-slop's example texts
- Runtime ~1s, no LLM call, deterministic with `--seed`
- Safe to run in CI

When it's not enough:
- Binary contrasts and false-agency patterns need rewriting, not deletion
- Vague declaratives need the specific content filled in
- Sentence-length variance can't be auto-introduced without changing meaning
- For these, run stop-slop directly with an LLM or hand the report to a human editor

## Operating modes

```bash
# Analyze only (flag, don't transform)
python scripts/humanize_english.py --input draft.md --mode analyze --report

# Lex pass (safe deletions + substitutions; flag the rest)
python scripts/humanize_english.py --input draft.md --mode lex --output cleaned.md

# Both — score before AND after the lex pass
python scripts/humanize_english.py --input draft.md --mode both --report
```

Output formats: `--report` (markdown), `--json` (structured), or default (markdown to stdout when no `--output` set).

## Language gate

`detect_language()` counts Arabic-block code points vs ASCII letters. If Arabic dominates, the script exits with an error and points to `humanize_v2.py`. Mixed-content (e.g., English prose with quoted Arabic) routes to English when Latin chars dominate. `--force-language en|ar` overrides detection if needed.

## Worked example

**Input** (stop-slop Example 1, throat-clearing + emphasis crutches):

> "Here's the thing: building products is hard. Not because the technology is complex. Because people are complex. Let that sink in."

**Output of `--mode lex`** (v2.5.1):

> "building products is hard. Not because the technology is complex. Because people are complex."

The throat-clearing opener (`Here's the thing:`) and emphasis crutch (`Let that sink in.`) are auto-deleted; the binary contrast (`Not because… Because`) is **flagged but NOT auto-deleted** because the correct rewrite ("Technology is manageable. People aren't.") requires human judgment.

**Score delta:** Directness 1 → 10 (+9), Total 38 → 47.

### Why some patterns delete while others only flag

| Pattern type | Action | Reason |
|---|---|---|
| Throat-clearing opener (`Here's the thing:`) | delete | Always removable; sentence stands without it. |
| Emphasis crutch (`Let that sink in.`) | delete | Adds zero meaning. |
| Business jargon (`navigate` → `handle`) | substitute (case-preserved) | One-for-one lookup, register-safe. |
| Em-dash | substitute (→ comma) | Mechanical typography. |
| Binary contrast (`Not because X. Because Y.`) | **flag** | Auto-rewriting changes argument structure. |
| False agency (`the decision emerges`) | **flag** | Needs the actor named, can't guess. |
| Vague declarative (`The implications are significant`) | **flag** | Needs the specific implication filled in. |

### v2.5.1 behavior notes (read before relying on output)

- **Code blocks are protected.** Fenced ` ``` ` and inline `code` are extracted before transformation and restored verbatim. `def navigate()` inside a code fence stays as `def navigate()`; the prose around it gets normal treatment.
- **Filler adverbs preserve load-bearing context.** `literally on fire` keeps `literally`; `Actually, the data...` deletes `Actually`. The skip-list (`literally on fire`, `literally true`, `actually false`) is matched against the actual ±2-word input window, not against the pattern itself (v2.5.0 had the latter and was effectively a no-op on adverbs).
- **Case is preserved.** `Navigate` → `Handle`, `NAVIGATE` → `HANDLE`, `navigate` → `handle`.
- **Arabic input is refused.** Even with `--force-language en`, the script exits 2 if `detect_language()` reports `ar` — to prevent silent no-ops on Arabic prose (v2.5.0 silently produced unchanged output, which was arguably worse than the documented "corruption" warning).

## Composing with stop-slop directly

If you have stop-slop loaded as an LLM-side skill:

| Order | Result | Recommended? |
|---|---|---|
| This script's `--mode lex` only | Deterministic deletions + substitutions, ~1s, no LLM | ✅ Fastest |
| stop-slop only (LLM rewrite) | Full rewrite including structural fixes | ✅ Most polished |
| `humanize_english.py --mode lex` → stop-slop | Deterministic baseline + LLM polish on top | ✅ Best of both |
| stop-slop → `humanize_english.py --mode analyze` | LLM rewrites, then deterministic scorer verifies | ✅ Useful for CI / regression |
| `humanize_english.py --mode lex` → human editor | Deterministic baseline + human edits the flagged items | ✅ For high-stakes prose |

The deterministic pass and the LLM-side skill are complementary, not competitive. The script handles the cuttable garbage; stop-slop handles the judgment calls.

## What this English path is NOT

- Not a localization tool (no i18n / ICU / BCP47 — same scope discipline as Arabic)
- Not a grammar checker (use a separate tool)
- Not a style guide for ALL English — opinionated toward direct, modern, conversational prose; legal / technical / academic English may legitimately use what this skill flags
- Not a replacement for human editing — the 5-axis score is a heuristic, not a verdict

## Score → action ladder

| Score | What it means | Action |
|---|---|---|
| 45-50 | Reads like sharp human prose | Ship |
| 35-44 | Some AI tells but not bad | Optional: run `--mode lex` |
| 25-34 | Clearly AI-flavored | Run `--mode lex` + review flags |
| 15-24 | Heavy AI tells throughout | Run `--mode lex`, then LLM rewrite (stop-slop), then re-score |
| 1-14 | Almost pure AI slop | Throw out and rewrite from scratch |
