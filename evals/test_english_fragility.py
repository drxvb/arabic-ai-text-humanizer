#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_english_fragility.py — fragility tests for the v2.5.0 English path.

Keeps Arabic fragility (test_known_fragility.py) independent. This file
only exercises scripts/humanize_english.py + corpus/english-patterns.json.

Why each test exists:
  E1 — stop-slop Example 1 reproduces: throat-clearing opener + binary
       contrast + emphasis crutch should all be detected; the opener and
       crutch get auto-deleted, the binary contrast gets flagged (it
       needs human rewrite, not deletion).
  E2 — stop-slop Example 3 reproduces: business jargon stack ("lean
       into", "navigate") substitutes correctly; "This matters because"
       deletes.
  E3 — em-dash normalization: " — " becomes ", " across all variants
       (em, en, padded, unpadded).
  E4 — language gate: Arabic input refused by detect_language() (the
       script exits 2 unless --force-language en is set, which is the
       intentional escape hatch).
  E5 — score axes stay in [1, 10] and total in [5, 50] for any input.
  E6 — deterministic: same input → same output, byte-for-byte.
  E7 — empty input doesn't crash; produces a baseline score.
  E8 — load-bearing literal not stripped: "literally on fire" must keep
       "literally" (it's in the skip_when_context list).

Run: python evals/test_english_fragility.py
Exit 0 on all-pass, non-zero on first failure.
"""
from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

SKILL_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = SKILL_ROOT / "scripts" / "humanize_english.py"
PYEXE = sys.executable

# Also import the script's module directly for unit-style assertions.
sys.path.insert(0, str(SKILL_ROOT / "scripts"))
import humanize_english as he

passed = 0
failed: list[tuple[str, str]] = []


def assert_true(name: str, cond: bool, why: str = "") -> None:
    global passed
    if cond:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed.append((name, why))
        print(f"  ❌ {name} — {why}")


def assert_eq(name: str, got, expected) -> None:
    global passed
    if got == expected:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed.append((name, f"expected {expected!r}, got {got!r}"))
        print(f"  ❌ {name} — expected {expected!r}, got {got!r}")


def run_cli(text: str, *args) -> tuple[int, str, str]:
    proc = subprocess.run(
        [PYEXE, str(SCRIPT), "--text", text] + list(args),
        capture_output=True, text=True, encoding="utf-8", timeout=30,
    )
    return proc.returncode, proc.stdout, proc.stderr


# E1 — stop-slop Example 1
e1_text = "Here's the thing: building products is hard. Not because the technology is complex. Because people are complex. Let that sink in."
transformed, ops = he.transform(e1_text, he.load_patterns())
assert_true(
    "E1a: throat-clearing 'Here's the thing:' deleted",
    "Here's the thing:" not in transformed,
    f"got: {transformed!r}",
)
assert_true(
    "E1b: emphasis crutch 'Let that sink in.' deleted",
    "Let that sink in" not in transformed,
    f"got: {transformed!r}",
)
e1_report = he.analyze(e1_text)
flagged_binary = [f for f in e1_report.findings if f.category == "binary_contrasts"]
assert_true(
    "E1c: binary contrast 'Not because... Because' flagged",
    len(flagged_binary) >= 1,
    f"findings: {[f.category for f in e1_report.findings]}",
)


# E2 — stop-slop Example 3 (business jargon)
e2_text = "In today's fast-paced landscape, we need to lean into discomfort and navigate uncertainty with clarity. This matters because your competition isn't waiting."
e2_transformed, e2_ops = he.transform(e2_text, he.load_patterns())
assert_true(
    "E2a: 'lean into' substituted to 'accept'",
    "accept discomfort" in e2_transformed.lower(),
    f"got: {e2_transformed!r}",
)
assert_true(
    "E2b: 'navigate' substituted to 'handle'",
    "handle uncertainty" in e2_transformed.lower(),
    f"got: {e2_transformed!r}",
)
assert_true(
    "E2c: 'This matters because' deleted",
    "this matters because" not in e2_transformed.lower(),
    f"got: {e2_transformed!r}",
)


# E3 — em-dash normalization
e3_text = "She wrote a book — a long one — and then another – shorter one."
e3_transformed, _ = he.transform(e3_text, he.load_patterns())
assert_true(
    "E3a: em-dash removed",
    "—" not in e3_transformed,
    f"got: {e3_transformed!r}",
)
assert_true(
    "E3b: en-dash removed",
    "–" not in e3_transformed,
    f"got: {e3_transformed!r}",
)


# E4 — language gate refuses Arabic
arabic_text = "هذا نص بالعربية الفصحى لاختبار البوابة اللغوية."
code, _, stderr = run_cli(arabic_text, "--mode", "lex")
assert_eq("E4a: Arabic input exits with code 2", code, 2)
assert_true(
    "E4b: stderr names the Arabic detection",
    "Arabic" in stderr or "ar" in stderr.lower(),
    f"stderr was: {stderr!r}",
)
# Force-language escape hatch works:
code_force, _, _ = run_cli(arabic_text, "--mode", "analyze", "--force-language", "en")
assert_eq("E4c: --force-language en bypasses the gate", code_force, 0)


# E5 — score axes always in valid ranges
for sample in [
    "",
    "Single sentence.",
    "Here's the thing: actually, literally, the data tells us that the implications are significant. Let that sink in.",
    "A clean sentence. Another varied one with more words to differ in length. Short.",
]:
    s = he.score_5_axis(sample, he.load_patterns())
    in_range = all(1 <= s[a] <= 10 for a in ("directness", "rhythm", "trust", "authenticity", "density"))
    assert_true(
        f"E5: score axes in [1,10] for sample ({len(sample)} chars)",
        in_range and 5 <= s["total"] <= 50,
        f"score: {s}",
    )


# E6 — deterministic transformation
sample6 = "Here's the thing: we need to lean into this. Let that sink in. The decision emerges from the team."
out1, _ = he.transform(sample6, he.load_patterns())
out2, _ = he.transform(sample6, he.load_patterns())
assert_eq("E6: transformation is deterministic", out1, out2)


# E7 — empty input
empty_score = he.score_5_axis("", he.load_patterns())
assert_true(
    "E7a: empty input doesn't crash",
    "total" in empty_score,
    f"empty_score: {empty_score}",
)
assert_true(
    "E7b: empty input scores all 10s (no AI tells detectable)",
    empty_score["total"] == 50,
    f"empty_score: {empty_score}",
)


# E8 — load-bearing 'literally' kept (in skip_when_context)
e8 = "The building is literally on fire — call 911."
e8_transformed, _ = he.transform(e8, he.load_patterns())
assert_true(
    "E8: 'literally on fire' preserved (skip_when_context)",
    "literally on fire" in e8_transformed,
    f"got: {e8_transformed!r}",
)


# E9 — JSON output mode works (smoke test for CLI integration)
code, stdout, _ = run_cli("Here's the thing: hello.", "--mode", "both", "--json")
try:
    payload = json.loads(stdout)
    assert_true("E9a: JSON mode emits valid JSON", True)
    assert_true(
        "E9b: JSON has score_before with all 5 axes",
        all(a in payload["score_before"] for a in ("directness", "rhythm", "trust", "authenticity", "density")),
        f"keys: {list(payload['score_before'].keys())}",
    )
except json.JSONDecodeError as e:
    assert_true("E9: JSON mode emits valid JSON", False, f"{e} — stdout was: {stdout[:200]!r}")


# Summary
total = passed + len(failed)
print(f"\nEnglish fragility: {passed}/{total} passed")
if failed:
    print("Failures:")
    for name, msg in failed:
        print(f"  - {name}: {msg}")
sys.exit(0 if not failed else 1)
