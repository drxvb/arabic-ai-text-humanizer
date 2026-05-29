# Changelog

Bilingual AI-text humanizer (Arabic primary, English secondary). Versions track the SKILL.md status banner;
this file is the auditable per-version history.
Hard dependency: `arabic-corpus-toolkit` ≥ v2.8.0-era contracts (G1-G4 adopted at runtime call sites;
`safe_llm_call` adopted in `score_text_deep` as of v2.17.0).

## v2.17.0 — Input validation + LLM failure resilience (3-of-4 A7 convergent must-have)
**Released:** 2026-05-29
(1) `score_text()` runs `_validate_input_text()` before processing — returns `{ok:False, input_validation:
{error_class,error_detail}}` for `None` (`null_input`), non-string (`wrong_type`), and oversized inputs
(`input_too_long`, MAX_INPUT_CHARS_HEURISTIC=200K). (2) `score_text_deep()` routes through toolkit v1.13.0
`safe_llm_call` (retries + circuit breaker); heuristic fallback enriched with `error_class`/`circuit_open`/
`attempts`. Closes codex+minimax+deepseek "no production-grade error handling; None crashes it."

## v2.16.1 — English G1-equivalent regression suite (2-of-2 A6 convergent gap)
**Released:** 2026-05-29
`evals/test_english_normalize_regression.py` — 16 assertions: case-insensitive scan, whitespace tolerance,
case-preserving substitution, KILLER mutation-resistance (heavily-mutated input → identical findings count +
score). Documents that period/semicolon variants are NOT normalized to comma-form (distinct rhetorical
moves). 16/16 PASS.

## v2.16.0 — Arabic G1 normalize-before-AI-tell regression suite
`evals/test_g1_normalize_regression.py` — 16 before/after assertions across 5 fixtures including the KILLER
mutation-resistance fixture proving `score_text("مًنٌ اَلُمِهّمْ مٌلٍاَحُظِةّ")` still matches "من المهم
ملاحظة" because `_arabic_normalize_via_toolkit` fires before lookup. 16/16 PASS.

## v2.15.1 — Top-level current-status banner (Codex+Gemini A4 #2)
Surfaces current state at a glance. Toolkit hard dependency (v2.8.0+); all four foundational contracts
(G1 arabic_normalize / G2 asset_registry / G3 influence_telemetry / G4 install_family) adopted at runtime.
`score_text(emit_trace=True)` returns Asset C influence records; `score_text_deep(emit_trace=True)` returns
`humanizer_gate_decision` records with `fallback_used`. Vendor rotation {gemini, minimax, codex} for
`score_text_deep`. 107/107 regression green.

### Earlier history (summary — see SKILL.md version table for detail)
- **v2.13.0** toolkit hard-dependency cutover (reads Assets C/D/E) · **v2.8.0** four-contract adoption begins ·
  **v2.7.x** `ARABIC_CORPUS_TOOLKIT_DISABLE` kill-switch + Asset C parity · **v2.6.0** multi-agent review that
  spawned the translator + authoring siblings · **v2.5.0** English secondary path (5-axis rubric +
  stop-slop catalogue).

> **A8 note (2026-05-29):** the "107/107 regression green" and the 16-vs-13 dimension count are scheduled for
> reconciliation with reproducible CI execution evidence (A8 roadmap ranks 4, 14). This CHANGELOG records the
> banner history as-shipped; claims are being substantiated, not retroactively edited.
