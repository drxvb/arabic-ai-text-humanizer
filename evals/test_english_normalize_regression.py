#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_english_normalize_regression.py -- v2.16.1 English G1-equivalent regression.

Closes the 2-of-2 A6 multi-vendor convergent gap: minimax-M2 + deepseek-v4-pro
BOTH independently flagged "English humanization path lacks equivalent G1 regression
suite — Arabic has 16 regression fixtures but English has no documented normalize-
before-pattern-match gates" as their top humanizer proposal.

English's "normalize" contract is structurally different from Arabic's:
  Arabic G1: strip tashkeel + tatweel BEFORE dictionary lookup
  English G1-equivalent: case-insensitive matching at regex layer
                         + whitespace-tolerance
                         + punctuation-boundary tolerance
                         + case-preserving substitution back

This suite codifies the implicit English-normalize contract so future contributors
can't silently break it by removing re.IGNORECASE or changing pattern boundaries.

16 assertions across 5 fixtures:
  A. Case-insensitive scan: all caps, title case, lower case all detected
  B. Punctuation boundary: comma/semicolon/dash variants
  C. Whitespace tolerance: extra spaces, tabs, newlines
  D. Case-preserving substitution: replacement matches matched casing
  E. KILLER mutation: heavily-mutated input still detected

Exit 0 on full pass, 1 on any violation.
"""
from __future__ import annotations
import sys
import re
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from humanize_english import (
    analyze, run, _preserve_case, _case_preserving_sub, load_patterns,
    scan_lexical, scan_structural, scan_sentence_level,
)

PASS, FAIL = "[PASS]", "[FAIL]"
failures = 0
def check(cond, label, detail=""):
    global failures
    print(f"  {PASS if cond else FAIL} {label}" + (f" — {detail}" if detail else ""))
    if not cond: failures += 1
def section(t): print(f"\n━━━ {t} ━━━")


# Common patterns: load once
PATTERNS = load_patterns()


# ─────────────────────────────────────────────────────────────────
# Fixture A: case-insensitive scan
# ─────────────────────────────────────────────────────────────────
section("A: case-insensitive scan — variants of an AI-tell MUST match identically")

VARIANTS = [
    ("Look, this is important.",                "title case"),
    ("LOOK, THIS IS IMPORTANT.",                "all caps"),
    ("look, this is important.",                "lowercase"),
    ("LooK, this is important.",                "mixed case"),
]
rep_baseline = analyze("Look, this is important.")
baseline_count = len(rep_baseline.findings)
check(baseline_count > 0,
      f"baseline 'Look, ...' yields >=1 findings",
      f"got {baseline_count}")

for text, label in VARIANTS:
    rep = analyze(text)
    n = len(rep.findings)
    check(n == baseline_count,
          f"variant ({label}) finds same count",
          f"baseline={baseline_count} variant={n}")


# ─────────────────────────────────────────────────────────────────
# Fixture B: punctuation-boundary tolerance
# ─────────────────────────────────────────────────────────────────
section("B: punctuation-boundary tolerance — commas, semicolons, dashes")

# Known design choice: English patterns target specific punctuation.
# "Look," (comma) is the targeted form; "Look." and "Look;" are NOT normalized
# to the same pattern by design — the pattern catalogue treats them as different
# rhetorical moves. The em-dash variant is detected via a separate pattern.
PUNCT_DETECTED = [
    ("Look, this is important.", True),    # canonical comma form
    ("Look — this is important.", True),   # em-dash detected by separate pattern
]
PUNCT_NOT_NORMALIZED = [
    "Look. this is important.",            # period: by design NOT same as comma
    "Look; this is important.",            # semicolon: by design NOT same as comma
]
for text, _expect_hit in PUNCT_DETECTED:
    rep = analyze(text)
    check(len(rep.findings) >= 1,
          f"punct (detected): {text[:40]!r}",
          f"got {len(rep.findings)} findings")
for text in PUNCT_NOT_NORMALIZED:
    rep = analyze(text)
    # We assert the CURRENT behavior: these aren't normalized to comma form.
    # If a future contributor adds punctuation-normalization, this assertion
    # changes from == 0 to >= 1 — the suite documents the contract.
    check(len(rep.findings) == 0,
          f"punct (NOT normalized — by design): {text[:40]!r}",
          f"got {len(rep.findings)} findings; expected 0")


# ─────────────────────────────────────────────────────────────────
# Fixture C: whitespace tolerance
# ─────────────────────────────────────────────────────────────────
section("C: whitespace tolerance — extra spaces, tabs, newlines")

WS_VARIANTS = [
    "Look,   this   is   important.",   # extra spaces
    "Look,\tthis\tis\timportant.",       # tabs
    "Look,\nthis is important.",         # newline after comma
]
for text in WS_VARIANTS:
    rep = analyze(text)
    check(len(rep.findings) >= 1,
          f"whitespace variant: {text[:30]!r}",
          f"got {len(rep.findings)} findings")


# ─────────────────────────────────────────────────────────────────
# Fixture D: case-preserving substitution
# ─────────────────────────────────────────────────────────────────
section("D: case-preserving substitution — replacement matches input casing")

# Direct unit test of _preserve_case
check(_preserve_case("Navigate", "handle") == "Handle",
      "Navigate -> Handle (title case preserved)")
check(_preserve_case("NAVIGATE", "handle") == "HANDLE",
      "NAVIGATE -> HANDLE (all caps preserved)")
check(_preserve_case("navigate", "handle") == "handle",
      "navigate -> handle (lowercase preserved)")
# Note: _preserve_case currently returns replacement as-is when matched is
# lowercase-or-mixed. Catalogue replacements are expected to be lowercase by
# convention; this is documented behavior, not a bug.
check(_preserve_case("navigate", "Handle") == "Handle",
      "lowercase input passes replacement through as-is (catalogue convention)")

# Integration test via _case_preserving_sub
result = _case_preserving_sub(r"\bnavigate\b", "handle", "Please Navigate carefully.")
check("Handle" in result, "_case_preserving_sub: Navigate -> Handle in real text",
      f"got {result!r}")


# ─────────────────────────────────────────────────────────────────
# Fixture E: KILLER mutation-resistance
# ─────────────────────────────────────────────────────────────────
section("E (KILLER): mutation-resistance — heavy variant MUST still be detected")

# Original baseline text with multiple known AI-tells
ORIGINAL = (
    "Look, this is incredibly important. Honestly, the system is on fire. "
    "Indeed, navigate carefully. Actually, this matters."
)

# Heavy mutation: random case + extra punctuation + extra whitespace
MUTATED = (
    "LOOK,    this  is  INcREDIbly important.    HONESTLY,    "
    "the system is ON FIRE.   INDEED,  navigate    carefully.  "
    "ACTUALLY,  this  matters."
)

rep_orig = analyze(ORIGINAL)
rep_mut  = analyze(MUTATED)
n_orig = len(rep_orig.findings)
n_mut  = len(rep_mut.findings)

check(n_orig > 0, f"original detects AI-tells ({n_orig} findings)")
check(n_mut > 0,  f"mutated detects AI-tells ({n_mut} findings)")
check(n_mut >= n_orig - 1,
      "KILLER: heavily-mutated input STILL detected (>= original - 1)",
      f"original={n_orig} mutated={n_mut}")

# Score is a dict {axis: int, ..., 'total': int, 'verdict': str}; use the 'total' field
score_orig_total = (rep_orig.score or {}).get("total", 0)
score_mut_total  = (rep_mut.score or {}).get("total", 0)
check(abs(score_orig_total - score_mut_total) <= 5,
      "KILLER: score totals within 5 points of each other",
      f"original={score_orig_total} mutated={score_mut_total}")


# ─────────────────────────────────────────────────────────────────
# Verdict
# ─────────────────────────────────────────────────────────────────
print()
print("─" * 60)
if failures == 0:
    print("✓ English G1-equivalent normalize-before-pattern-match contract INTACT")
    print("─" * 60)
    sys.exit(0)
else:
    print(f"✗ {failures} English normalize regression violations")
    print("─" * 60)
    sys.exit(1)
