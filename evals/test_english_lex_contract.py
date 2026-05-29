#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_english_lex_contract.py — contract test for the DETERMINISTIC English
lex/slop pass in scripts/humanize_english.py.

Sibling of test_english_fragility.py. Where that file exercises the CLI and the
edge-case bug-fixes (T1/T2/T3/T6/T7/T8), this file pins the *contract* of the
pure, no-LLM deterministic pass: the 5-axis rubric and the deterministic
lexical substitution layer (he.transform / he.score_5_axis / he.analyze).

NO network, NO LLM, NO subprocess — all calls go through the pure functions
loaded from the script module, against the bundled corpus/english-patterns.json.

Contract under test:
  C1  A known-sloppy string surfaces findings across catalogue categories.
  C2  Catalogued AI-tells (throat-clearing, business jargon, em-dash) actually
      transform deterministically (delete / substitute).
  C3  The sloppy string scores WORSE than a clean string on the 5-axis rubric.
  C4  The sloppy string lands below the revise threshold; clean lands at/above.
  C5  Determinism: same input -> identical output across two calls, for both
      transform() and score_5_axis().
"""
from __future__ import annotations

import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT / "scripts"))
import humanize_english as he  # noqa: E402

passed = 0
failed: list[tuple[str, str]] = []


def assert_true(name: str, cond: bool, why: str = "") -> None:
    global passed
    if cond:
        passed += 1
        print(f"  PASS {name}")
    else:
        failed.append((name, why))
        print(f"  FAIL {name} -- {why}")


def assert_eq(name: str, got, expected) -> None:
    assert_true(name, got == expected, f"expected {expected!r}, got {got!r}")


PATTERNS = he.load_patterns()

# A deliberately sloppy English string with catalogued AI-tells:
#   - throat-clearing opener: "Here's the thing:"
#   - business jargon: "lean into", "navigate"
#   - emphasis crutch / meta-commentary: "Let that sink in."
#   - filler adverbs: "actually", "literally"
#   - em-dash AI-tell
SLOP = (
    "Here's the thing: we actually need to lean into discomfort and navigate "
    "uncertainty — literally. Let that sink in."
)

# A clean control string: plain declaratives, no catalogue tells, varied length.
CLEAN = (
    "We shipped the release on Friday. The team fixed three bugs before lunch. "
    "Sales rose nine percent after launch."
)


# ---- C1 — findings detected on the sloppy string ----
slop_report = he.analyze(SLOP)
assert_true("C1a: analyze returns a Report with findings on sloppy input",
            len(slop_report.findings) >= 3,
            f"got {len(slop_report.findings)} findings")
slop_categories = {f.category for f in slop_report.findings}
assert_true("C1b: throat_clearing_openers detected",
            "throat_clearing_openers" in slop_categories,
            f"categories: {sorted(slop_categories)}")
assert_true("C1c: business_jargon detected",
            "business_jargon" in slop_categories,
            f"categories: {sorted(slop_categories)}")
assert_true("C1d: em_dashes detected at sentence level",
            "em_dashes" in slop_categories,
            f"categories: {sorted(slop_categories)}")
# Clean control surfaces strictly fewer findings.
clean_report = he.analyze(CLEAN)
assert_true("C1e: clean string surfaces fewer findings than sloppy",
            len(clean_report.findings) < len(slop_report.findings),
            f"clean={len(clean_report.findings)} slop={len(slop_report.findings)}")


# ---- C2 — deterministic lexical transformation applies catalogued ops ----
transformed, applied, skipped = he.transform(SLOP, PATTERNS)
assert_true("C2a: throat-clearing opener deleted",
            "Here's the thing:" not in transformed,
            f"got: {transformed!r}")
assert_true("C2b: business jargon 'lean into' substituted away",
            "lean into" not in transformed.lower(),
            f"got: {transformed!r}")
assert_true("C2c: business jargon 'navigate' substituted to 'handle'",
            "navigate" not in transformed.lower() and "handle" in transformed.lower(),
            f"got: {transformed!r}")
assert_true("C2d: em-dash removed by substitution",
            "—" not in transformed,
            f"got: {transformed!r}")
assert_true("C2e: at least one transformation was recorded as applied",
            len(applied) >= 1,
            f"applied: {applied}")


# ---- C3 — score reflects slop: sloppy scores worse than clean ----
slop_score = he.score_5_axis(SLOP, PATTERNS)
clean_score = he.score_5_axis(CLEAN, PATTERNS)
assert_true("C3a: every axis is within [1,10] for both inputs",
            all(1 <= slop_score[a] <= 10 and 1 <= clean_score[a] <= 10
                for a in ("directness", "rhythm", "trust", "authenticity", "density")),
            f"slop={slop_score} clean={clean_score}")
assert_true("C3b: clean total strictly exceeds sloppy total",
            clean_score["total"] > slop_score["total"],
            f"clean={clean_score['total']} slop={slop_score['total']}")
assert_true("C3c: transforming the slop improves its score",
            he.score_5_axis(transformed, PATTERNS)["total"] > slop_score["total"],
            f"before={slop_score['total']} after={he.score_5_axis(transformed, PATTERNS)['total']}")


# ---- C4 — rubric verdict honours the revise threshold ----
threshold = PATTERNS["scoring_rubric_5_axis"]["threshold_revise_below"]
assert_eq("C4a: threshold echoed in score payload",
          slop_score["threshold_revise_below"], threshold)
assert_true("C4b: sloppy verdict is 'revise' (below threshold)",
            slop_score["verdict"] == "revise" and slop_score["total"] < threshold,
            f"slop total={slop_score['total']} threshold={threshold} verdict={slop_score['verdict']}")
assert_true("C4c: clean verdict is 'ship' (at/above threshold)",
            clean_score["verdict"] == "ship" and clean_score["total"] >= threshold,
            f"clean total={clean_score['total']} threshold={threshold} verdict={clean_score['verdict']}")


# ---- C5 — determinism: identical output across repeated calls ----
t_a, applied_a, _ = he.transform(SLOP, PATTERNS)
t_b, applied_b, _ = he.transform(SLOP, PATTERNS)
assert_eq("C5a: transform() is deterministic (same text)", t_a, t_b)
assert_eq("C5b: transform() is deterministic (same applied ops)", applied_a, applied_b)
assert_eq("C5c: score_5_axis() is deterministic",
          he.score_5_axis(SLOP, PATTERNS), he.score_5_axis(SLOP, PATTERNS))


# Summary
total = passed + len(failed)
print(f"\nEnglish lex contract: {passed}/{total} passed")
if failed:
    print("Failures:")
    for name, msg in failed:
        print(f"  - {name}: {msg}")
sys.exit(0 if not failed else 1)
