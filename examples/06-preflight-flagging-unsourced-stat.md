# Example 06: Pre-flight safety check — flagging hazardous claims

## Reproduction command

```bash
python scripts/preflight_check.py   --file examples/06-preflight-flagging-unsourced-stat.input.txt
```

Exit code: `0` = no high-severity findings; `2` = at least one high-severity finding (the gate to abort when running with `--strict-preflight`). `preflight_check` is fully deterministic and never calls the LLM.

## Input

```
يُقدِّر الخبراء أن 87% من الموظفين سيعملون عن بُعد بحلول عام 2030. وقد قال مصدر مطلع إن الشركات الكبرى تعمل بالفعل على إعادة هيكلة مكاتبها. تَزعم الدراسات أن هذا التحول سيُوفِّر 40 مليار دولار سنوياً.
```

The input contains three classic hazards:
1. **Unsourced statistic** (`87%`) — a specific number without a `حسب` / `وفق` / `بحسب` attribution
2. **Anonymous source** (`مصدر مطلع`) — a quote attribution that can't be verified
3. **Hostile attribution verb** (`تزعم`) — `زعم` carries a built-in editorial stance that pure reporting doesn't

## Output: pre-flight findings

```
======================================================================
Pre-flight factual / ethical / sourcing-hygiene check
======================================================================
Verdict: FLAG
Findings: 2 total  (0 HIGH, 2 MEDIUM, 0 LOW)


[1] MEDIUM unsourced_statistic
    Found: "40 مليار"
    Advice: Add attribution: 'حسب X' / 'وفق دراسة Y' / 'بحسب تقرير Z'

[2] MEDIUM anonymous_source_chain
    Found: "مصدر مطلع"
    Advice: Anonymous sourcing. Verify with named editorial chain; do not let humanizer beautify into more credible-seeming prose without verification.


[stderr]
```

## What this means for the pipeline

`preflight_check` **flags only — it does not transform**. The humanizer optimizes for prose *quality*, not *truth*; the pre-flight check is the safety net that ensures we don't turn a flat falsehood into a beautiful one. If you pass `--preflight --strict-preflight` to `humanize_v2.py`, the pipeline aborts on any HIGH-severity finding (exit code 2) so you can review before publishing.
