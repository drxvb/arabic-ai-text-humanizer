# Arabic AI-Text Humanizer

A multi-pass Arabic-text humanizer that reduces AI fingerprints across **16 dimensions** of cognitive structure, rhetorical figures, reader-respect, typography hygiene, and connector-entropy. Built as an [Agent Skills](https://agentskills.io) skill — drop into Claude Code, Codex, Kimi, MiniMax, Gemini, or any compatible host.

The full specification, transformation protocol, dimension definitions, anti-patterns, and worked example all live in **[`SKILL.md`](SKILL.md)**. This README is a one-screen overview.

## What it does

Rewrites AI-generated Arabic prose to be less mechanical at the *style* and *cognitive-structure* layer — adding visible reasoning steps, classical-rhetorical figures (when register allows), graduated explanation, scope markers, and reader-respect restraint. Includes a pre-flight safety check for factual/ethical/sourcing hazards.

Six transformation modes ranging from `lex-only` (deterministic, ~1s, no LLM) to `full` (4-pass cognitive + rhetorical + coherence). Four register policies (`classical / news / opinion / technical`) gate which transformations fire.

**Scope:** humanization, **not** localization. BCP47 locale tags, ICU MessageFormat plurals, and SSML are out of scope by design.

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

## License

[MIT](LICENSE). Copyright © 2026.

## Contributing

The skill is published as a stable artifact. Issues and discussion welcome; behavioural changes need a regression case added to `evals/` first.
