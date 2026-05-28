# 20 — Context-Keywords Gate (v2.6.3+)

A two-layer defense for dictionary entries that fire on **bare-stem Arabic forms** which can mean different things in different domains. The classic disaster: `view → مشاهدة` corrupted `رؤية 2030` in v2.4.0–v2.5.x. v2.6.0 deleted the entry. v2.6.3 brings it back, safely.

## The two layers

### Layer 1 — Positive context gate (`context_keywords_*`)

For each topic-guarded entry, at least N keywords (default 1) from `context_keywords_arabic` or `context_keywords_english` must appear within a ±100-character window of the candidate match. If the count threshold isn't met, **the substitution is skipped**.

Example for `view → عرض`:

```json
"context_keywords_arabic": [
  "قاعدة البيانات", "جدول", "استعلام", "فهرس", "صفوف", "أعمدة",
  "مخطط", "البيانات الجدولية", "SQL"
],
"context_keywords_english": [
  "SQL", "SELECT", "JOIN", "WHERE", "FROM", "TABLE", "DATABASE",
  "INDEX", "schema", "query", "MySQL", "PostgreSQL", "SQLite", "Oracle"
],
"context_keywords_required_count": 1
```

The 23 keywords cover the high-density vocabulary of database / SQL contexts. If ANY of them is within ±100 chars of `رؤية` in the input, the substitution becomes eligible.

### Layer 2 — Negative exclusion patterns (`exclude_if_pattern`)

Even when the positive gate passes, certain patterns force-preserve the source text. For `view → عرض`:

```json
"exclude_if_pattern": [
  "رؤية\\s+\\d{4}",
  "الرؤية\\s+\\d{4}",
  "رؤية\\s+المملكة"
]
```

Each pattern is evaluated against the candidate match's ±20-character trailing context. If ANY pattern matches, **the substitution is force-blocked** regardless of the positive gate.

This is the load-bearing safety belt for the Saudi `رؤية 2030` / `رؤية المملكة` patterns — they remain preserved even when surrounded by database vocabulary.

## The 6 v2.6.3 topic-guarded entries

| Entry | Natural | Positive gate (sample) | Negative exclusion |
|---|---|---|---|
| **`view` (database)** | `عرض` | `قاعدة البيانات`, `SQL`, `جدول`, `SELECT`, `JOIN` | `رؤية\s+\d{4}` (Vision XXXX), `رؤية\s+المملكة` |
| **`partition` (database)** | `قسم` | `SQL`, `partition`, `sharding`, `MySQL` | `تقسيم\s+العمل` (division of labor) |
| **`trigger` (database)** | `مُطلِق` | `SQL`, `TRIGGER`, `AFTER INSERT`, `PL/SQL` | `مشغل\s+الصدمة` (psychological trigger) |
| **`process` (OS / system)** | `العملية` | `OS`, `kernel`, `thread`, `PID`, `Linux`, `daemon` | `العملية\s+التشريعية` (legislative process), `العملية\s+السياسية` (political process), `العملية\s+التعليمية` (educational process) |
| **`task` (scheduler / threading)** | `المهمّة` | `async`, `scheduler`, `cron`, `Celery`, `queue` | — |
| **`worker` (background process)** | `العامِل البرمجي` | `async`, `Celery`, `Kubernetes`, `pod`, `RQ`, `Sidekiq` | `حقوق\s+العمال` (labor rights), `العامِل\s+الإنشائي` (construction worker), `عامل\s+النظافة` (cleaning worker) |

## Per-entry safety analysis

### `view → عرض`

- **Without the gate**: would corrupt `رؤية 2030` into `عرض 2030` — politically catastrophic.
- **With Layer 1 only**: vulnerable to mixed-context docs (a Vision 2030 paragraph that happens to mention `قاعدة البيانات` would trigger the substitution).
- **With Layer 2**: `رؤية\s+\d{4}` matches the year suffix regardless of surrounding context. Two-layer defense is mandatory for this entry.

### `process → العملية`

- **Without the gate**: would corrupt `العملية السياسية` (the political process) into `العملية` — meaning loss.
- **With Layer 2 only**: would catch the three legislative/political/educational variants explicitly listed but miss novel `العملية + adjective` phrases.
- **With Layer 1 + 2**: requires OS/kernel/threading vocabulary nearby AND blocks the three known political/educational patterns. Defense in depth.

### `worker → العامِل البرمجي`

- **Without the gate**: would corrupt `حقوق العمال` (labor rights) — politically loaded in MENA labor reporting.
- **With Layer 1 only**: vulnerable to articles that discuss both labor rights AND technology (e.g., gig-economy reporting). The `حقوق\s+العمال` exclusion is mandatory.
- **With Layer 1 + 2**: requires async/Celery/Kubernetes context AND blocks the three labor-context patterns.

## Architectural notes

- `_load_calque_dictionary()` extracts the 4 new optional fields. Entries without them preserve v2.3.0+ unconditional-substitution behavior (zero regression risk).
- `lex_apply_calque_dictionary()` walks topic-guarded matches **right-to-left** so deletions/substitutions don't shift earlier offsets.
- `_matches_topic(segment, match, entry)` is a per-match helper that returns True iff (a) no topic guard configured, OR (b) positive gate passes AND no exclusion patterns match. Pure function; testable.
- Substitution proceeds per-match for topic-guarded entries (vs whole-segment `re.sub` for unguarded entries). Slightly more expensive but unguarded entries dominate the dictionary, so per-call overhead is minimal.

## What this DOESN'T address (v2.6.4+ candidates)

- **Curated keyword lists are static.** A new database product name (e.g., a future "DuckDB 2.0") won't be in the list. Mitigation: extend the lists as new vocabulary emerges.
- **Topic detection is keyword-based, not semantic.** A satirical political article that mentions `قاعدة البيانات الانتخابية` could trigger the technical gate on `رؤية 2030` if not for the year-suffix exclusion. The exclusion catches that case but only by luck — a non-year Vision pattern (e.g., `رؤية الإصلاح`) would be vulnerable.
- **No machine learning.** The current implementation is rule-based by design — multi-LLM consensus was found unreliable for fine-grained Arabic disambiguation in the v2.6.0 review. Future LLM-based topic detection should be additive to (not a replacement for) the keyword + exclusion gates.

## Provenance

Designed and shipped in v2.6.3 after the v2.6.0 multi-agent review documented the `رؤية 2030` failure mode. The two-layer architecture (positive gate + negative exclusion) is a defensive measure against any single-layer gate failure mode.
