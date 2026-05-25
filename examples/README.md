# Worked examples

All examples here are **byte-deterministic** — they use `--mode lex-only` or `--mode tighten` (or the read-only `analyze_deep` / `preflight_check` scripts), none of which call an LLM. Running the reproduction command shown in each example produces the exact output committed here.

| # | Example | Mode | Register | What it shows |
|---|---|---|---|---|
| 01 | [News × tighten — pro-drop deletion](01-news-tighten-pro-drop.md) | tighten | news | Formulaic AI hedges (`من المهم ملاحظة أن`, `في الواقع`) get deleted; content is preserved |
| 02 | [Opinion × tighten — de-stacking intensifiers](02-opinion-tighten-intensifier-destack.md) | tighten | opinion | Stacked intensifiers (`في غاية الأهمية البالغة جدا`) collapse to one |
| 03 | [Technical × tighten — register restraint](03-technical-tighten-conservative.md) | tighten | technical | Technical terms (`Raft`, `Write-Ahead Logging`) preserved verbatim — register protects the substance |
| 04 | [Classical × lex-only — connector diversification](04-classical-lex-only-connector-diversification.md) | lex-only | classical | و-monoculture broken with alternating classical connectors |
| 05 | [Diagnostic — 16-dim scorecard](05-diagnostic-only-analyze.md) | — | — | `analyze_deep` produces a dimension-by-dimension report without transforming |
| 06 | [Pre-flight — flagging hazards](06-preflight-flagging-unsourced-stat.md) | — | — | `preflight_check` flags unsourced stats, anonymous sources, hostile attribution verbs |
| 07 | [v2.2.0 — tashkeel + calque](07-v2.2.0-tashkeel-and-calque.md) | tighten | news | **New in v2.2.0:** `خط أنابيب` → `مسار العمل`, tashkeel reduction (news/opinion only), hamza/digit preservation |

## LLM-augmented modes — why they're NOT in the canonical examples

Modes `+cognitive`, `+rhetorical`, and `full` depend on a live LLM call. Their outputs vary by provider, model, temperature, and the model's specific behavior on the day you call it — so we can't ship a byte-identical canonical example. Try them yourself once you've set `LLM_API_URL`/`LLM_API_KEY`/`LLM_MODEL`.

A reasonable demo prompt to try:

```bash
export LLM_API_URL=https://api.openai.com/v1/chat/completions
export LLM_API_KEY=sk-...
export LLM_MODEL=gpt-4o-mini

python scripts/humanize_v2.py   --file examples/01-news-tighten-pro-drop.input.txt   --mode +cognitive --register news   --output /tmp/news-with-cognitive.txt --analyze
```

## Reproducibility note

Each `.input.txt` and its matching `.output.txt` / `.report.txt` is committed. If you change anything in `scripts/humanize_v2.py` or the lexical tables in `scripts/`, re-run the relevant `.input.txt` through the pipeline and commit the new `.output.txt`. The fragility tests in `evals/test_known_fragility.py` will catch most lex-pass regressions, but the worked examples here are the human-readable evidence.
