# Arabic AI-Text Humanizer

> 🇸🇦 [اقرأ بِالعَرَبية](README.ar.md) — Arabic README in native MSA phrasing, not literal translation.

A multi-pass Arabic-text humanizer that reduces AI fingerprints across **16 dimensions** of cognitive structure, rhetorical figures, reader-respect, typography hygiene, and connector-entropy. Built as an [Agent Skills](https://agentskills.io) skill — drop into Claude Code, Codex, Kimi, MiniMax, Gemini, or any compatible host.

The full specification, transformation protocol, dimension definitions, anti-patterns, and worked example all live in **[`SKILL.md`](SKILL.md)**. This README is a one-screen overview.

## What it does

Rewrites AI-generated Arabic prose to be less mechanical at the *style* and *cognitive-structure* layer — adding visible reasoning steps, classical-rhetorical figures (when register allows), graduated explanation, scope markers, and reader-respect restraint. Includes a pre-flight safety check for factual/ethical/sourcing hazards.

Six transformation modes ranging from `lex-only` (deterministic, ~1s, no LLM) to `full` (4-pass cognitive + rhetorical + coherence). Four register policies (`classical / news / opinion / technical`) gate which transformations fire.

**Scope:** humanization, **not** localization. BCP47 locale tags, ICU MessageFormat plurals, and SSML are out of scope by design.

## Installation

| Your environment | How to install |
|---|---|
| **Claude Code, Codex CLI, MiniMax CLI, or any agent CLI that imports `.skill` ZIPs** | Download the matching `.skill` bundle from [Releases](../../releases) and unpack into your CLI's skills directory. Provider-tuned variants are available for Moonshot/Kimi, MiniMax, and Anthropic Claude (via OpenAI-compatible proxy). |
| **Kimi CLI** (does not import `.skill` archives) | Use **[`INSTALL-FOR-KIMI.md`](INSTALL-FOR-KIMI.md)** — a self-contained markdown installer. Hand the file to Kimi and ask it to recreate the skill tree. 30 file blocks embedded; 100% lossless round-trip verified. |
| **Manual install / forking** | `git clone` this repo and drop the directory wherever your CLI expects skills. The repo content IS the skill. |

## Quickstart

The skill is **provider-agnostic**. Configure any OpenAI-compatible chat-completions endpoint:

```bash
# Pick a provider:
export LLM_API_URL=https://api.openai.com/v1/chat/completions
export LLM_API_KEY=sk-...
export LLM_MODEL=gpt-4o-mini

# Run a deep humanization with diagnostic report:
python scripts/humanize_v2.py \
  --input input.txt --mode +cognitive --register news \
  --output humanized.txt --analyze
```

Deterministic mode needs no API:

```bash
python scripts/humanize_v2.py --input input.txt --mode tighten --register news --output cleaned.txt
```

`config.example.json` carries ready-made provider configurations (Moonshot, MiniMax, OpenAI, Together, Groq, DeepSeek, local Ollama).

## What's in the box

| Path | What |
|---|---|
| `SKILL.md` | The full skill specification — load this first |
| `scripts/humanize_v2.py` | Main multi-pass pipeline (lex / cognitive / rhetorical / coherence) |
| `scripts/analyze_deep.py` | 16-dimension diagnostic analyzer (no LLM; deterministic) |
| `scripts/preflight_check.py` | Factual / ethical / sourcing-hygiene flagger |
| `scripts/llm_transform.py` | Provider-agnostic LLM-call wrapper |
| `scripts/score_humanness.py` | Before/after humanness scorer |
| `scripts/mine_corpus.py` | Empirical-pattern miner (run against your own JSONL if you want to extend the corpus baseline) |
| `references/*.md` | 16 deep-dive files — one per humanness dimension |
| `corpus/empirical-patterns.json` | Pre-mined statistics (100K records / 1.31M sentences / 71.28M tokens across Qur'an, classical/modern, news, lexicon registers; mining took ≈87 seconds) |
| `examples/` | Six worked examples — actual input + actual output + analysis, all reproducible byte-deterministically (`lex-only` / `tighten` modes + `analyze_deep` + `preflight_check` — no API key needed) |
| `evals/run_golden.py` | 20 golden regression cases |
| `evals/test_known_fragility.py` | 12 fragility-class assertions (clause-preservation, pro-drop, env-gates) |
| `config.example.json` | Provider configuration reference |

## Verify on your machine

```bash
python evals/run_golden.py             # expect: 20/20 PASS
python evals/test_known_fragility.py   # expect: 12/12 PASS
```

Both suites are dependency-free Python 3 stdlib — no `pip install` required.

## Design notes (short)

- **Provider-agnostic.** No backend name lives in source code. Configure `LLM_API_URL` / `LLM_API_KEY` / `LLM_MODEL` for whichever OpenAI-compatible endpoint you want. CLI flags `--backend-url`, `--auth-token`, `--model` override per invocation.
- **Cross-LLM-critique-informed.** Lexical-pass behaviors (clause-preserving substitution, pro-drop deletion, quote-verb-rotation env-gate) come from a multi-LLM review of an earlier framework. See `evals/test_known_fragility.py` for the bug-class regression checks.
- **Arabic-only.** Targets MSA / classical-leaning register. Not for dialectal / colloquial / English text.

## Source-size + effort behind this release

| Metric | Value |
|---|---|
| Total source lines | **6,728** (2,806 Python + 2,340 Markdown + 1,582 JSON) |
| Files in the skill | **31** (16 references + 6 scripts + 2 evals + 1 corpus stats + LICENSE + SKILL.md + .gitignore + config.example.json + README + INSTALL-FOR-KIMI + 1 examples README) |
| 16-dimension framework documentation | 16 deep-dive reference files, ~2,000 lines of Arabic+English explanatory text |
| Empirical corpus mining | **100,000 records sampled** → **1,310,649 sentences**, **71,278,688 tokens** across 4 register categories (Qur'an, classical/modern, news, lexicon). Mining time: **≈87 seconds**. Tracked: 50 connector types + 50 sentence-initial-token types. |
| Regression coverage | 20 golden cases + 12 fragility assertions = **32 deterministic tests**, all passing, dependency-free (Python 3 stdlib only) |
| Cross-LLM critique iterations | **4 independent perspectives** (cognitive-structure, rhetorical decomposition, transitions/literary-art, historical/coherence) folded into the 16-dimension framework |
| Worked examples shipped | **6 byte-deterministic examples** covering `news/tighten`, `opinion/tighten`, `technical/tighten`, `classical/lex-only`, plus diagnostic-only and pre-flight-only |
| Distributable variants | **5 release assets** — 1 universal `.skill` bundle + 3 provider-tuned `.skill` bundles (Moonshot/Kimi, MiniMax, Anthropic-via-proxy) + 1 markdown installer for Kimi CLI |
| Provider-agnostic | Any OpenAI-compatible chat-completions endpoint (OpenAI, Moonshot, MiniMax, Together, Groq, DeepSeek, local Ollama, …) |

This is what shipped publicly at v2.1.1. Effort across multiple iterations spanning the v1 → v2.0 → v2.1 → v2.1.1 lineage (cognitive-framework design, cross-LLM critique synthesis, portability refactor, security audit, public-release packaging).

## License

[MIT](LICENSE). Copyright © 2026.

## Contributing

The skill is published as a stable artifact. Issues and discussion welcome; behavioural changes need a regression case added to `evals/` first.
