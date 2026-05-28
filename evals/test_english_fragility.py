#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_english_fragility.py — fragility tests for the English path.

Keeps Arabic fragility (test_known_fragility.py) independent. This file
exercises scripts/humanize_english.py + corpus/english-patterns.json.

v2.5.1 — rewritten after multi-agent review found 5 critical bugs that
v2.5.0's tests passed BECAUSE of the bugs (not despite them). E4c and
E8 now actually test the documented behavior.

Categories:
  E1   stop-slop Example 1 reproduces (throat-clearing + binary contrast)
  E2   stop-slop Example 3 reproduces (business jargon stack)
  E3   em-dash + en-dash normalization
  E4   language gate: Arabic refused (even with --force-language en — T2 fix)
  E5   score axes always in [1, 10], total in [5, 50]
  E6   deterministic transformation
  E7   empty input doesn't crash; scores 50/50
  E8   skip_when_context works ON ACTUAL CONTEXT (T1 fix):
        - 'literally' deleted in filler use
        - 'literally' preserved in 'literally on fire'
  E9   JSON output validity + score_before has all 5 axes
  E10  T3 code-block protection: `def navigate()` survives lex pass
  E11  T8 case preservation: 'Navigate' -> 'Handle' (not 'handle')
  E12  T7 finding de-duplication by span
  E13  T6 --seed flag accepted without error
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

SKILL_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = SKILL_ROOT / "scripts" / "humanize_english.py"
PYEXE = sys.executable

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


# ---- E1 — stop-slop Example 1 ----
e1_text = "Here's the thing: building products is hard. Not because the technology is complex. Because people are complex. Let that sink in."
transformed, _, _ = he.transform(e1_text, he.load_patterns())
assert_true("E1a: throat-clearing 'Here's the thing:' deleted",
            "Here's the thing:" not in transformed, f"got: {transformed!r}")
assert_true("E1b: emphasis crutch 'Let that sink in.' deleted",
            "Let that sink in" not in transformed, f"got: {transformed!r}")
e1_report = he.analyze(e1_text)
flagged_binary = [f for f in e1_report.findings if f.category == "binary_contrasts"]
assert_true("E1c: binary contrast flagged", len(flagged_binary) >= 1,
            f"findings: {[f.category for f in e1_report.findings]}")


# ---- E2 — stop-slop Example 3 (business jargon) ----
e2_text = "In today's fast-paced landscape, we need to lean into discomfort and navigate uncertainty with clarity."
e2_transformed, _, _ = he.transform(e2_text, he.load_patterns())
assert_true("E2a: 'lean into' substituted to 'accept'",
            "accept discomfort" in e2_transformed.lower(), f"got: {e2_transformed!r}")
assert_true("E2b: 'navigate' substituted to 'handle'",
            "handle uncertainty" in e2_transformed.lower(), f"got: {e2_transformed!r}")


# ---- E3 — em-dash / en-dash ----
e3_text = "She wrote a book — a long one — and then another – shorter one."
e3_transformed, _, _ = he.transform(e3_text, he.load_patterns())
assert_true("E3a: em-dash removed", "—" not in e3_transformed, f"got: {e3_transformed!r}")
assert_true("E3b: en-dash removed", "–" not in e3_transformed, f"got: {e3_transformed!r}")


# ---- E4 — language gate (T2 fix) ----
arabic_text = "هذا نص بالعربية الفصحى لاختبار البوابة اللغوية."
code, _, stderr = run_cli(arabic_text, "--mode", "lex")
assert_eq("E4a: Arabic input exits code 2", code, 2)
assert_true("E4b: stderr names the Arabic detection",
            "Arabic" in stderr or "ar" in stderr.lower(), f"stderr was: {stderr!r}")
# T2 fix: --force-language en should ALSO refuse Arabic, not silently no-op.
code_force, _, stderr_force = run_cli(arabic_text, "--mode", "analyze", "--force-language", "en")
assert_eq("E4c: --force-language en on Arabic still exits 2 (T2 fix)", code_force, 2)
assert_true("E4d: stderr explains why force-language en doesn't bypass Arabic gate",
            "Arabic" in stderr_force or "silently no-op" in stderr_force,
            f"stderr was: {stderr_force!r}")


# ---- E5 — score ranges ----
for sample in [
    "",
    "Single sentence.",
    "Here's the thing: actually, literally, the data tells us that the implications are significant. Let that sink in.",
    "A clean sentence. Another varied one with more words to differ in length. Short.",
]:
    s = he.score_5_axis(sample, he.load_patterns())
    in_range = all(1 <= s[a] <= 10 for a in ("directness", "rhythm", "trust", "authenticity", "density"))
    assert_true(f"E5: axes in [1,10] ({len(sample)} chars)",
                in_range and 5 <= s["total"] <= 50, f"score: {s}")


# ---- E6 — deterministic ----
sample6 = "Here's the thing: we need to lean into this. Let that sink in. The decision emerges from the team."
out1, _, _ = he.transform(sample6, he.load_patterns())
out2, _, _ = he.transform(sample6, he.load_patterns())
assert_eq("E6: deterministic transformation", out1, out2)


# ---- E7 — empty input ----
empty_score = he.score_5_axis("", he.load_patterns())
assert_true("E7a: empty input doesn't crash", "total" in empty_score, f"empty_score: {empty_score}")
assert_eq("E7b: empty scores 50/50", empty_score["total"], 50)


# ---- E8 — T1 fix: skip_when_context actually examines input context ----
# Sub-test E8a: filler 'actually' DOES get deleted in filler use.
e8a_text = "Actually, the data tells us we should reconsider."
e8a_transformed, e8a_applied, e8a_skipped = he.transform(e8a_text, he.load_patterns())
assert_true("E8a: 'Actually' deleted in filler use (T1 fix)",
            "actually" not in e8a_transformed.lower(),
            f"got: {e8a_transformed!r} applied={e8a_applied} skipped={e8a_skipped}")

# Sub-test E8b: 'literally' DOES preserve in 'literally on fire'.
e8b_text = "The building is literally on fire."
e8b_transformed, _, e8b_skipped = he.transform(e8b_text, he.load_patterns())
assert_true("E8b: 'literally on fire' preserved (skip_when_context match)",
            "literally on fire" in e8b_transformed,
            f"got: {e8b_transformed!r} skipped={e8b_skipped}")
assert_true("E8c: skip is reported, not silent",
            any("literally" in s for s in e8b_skipped),
            f"skipped: {e8b_skipped}")

# Sub-test E8d: when SAME WORD appears in both contexts, only filler use gets deleted.
e8d_text = "The building is literally on fire, and the meeting was literally boring."
e8d_transformed, _, e8d_skipped = he.transform(e8d_text, he.load_patterns())
assert_true("E8d: 'literally on fire' kept; 'literally boring' deleted",
            "literally on fire" in e8d_transformed and "literally boring" not in e8d_transformed,
            f"got: {e8d_transformed!r}")


# ---- E9 — JSON output ----
code, stdout, _ = run_cli("Here's the thing: hello.", "--mode", "both", "--json")
try:
    payload = json.loads(stdout)
    assert_true("E9a: JSON mode emits valid JSON", True)
    assert_true("E9b: score_before has all 5 axes",
                all(a in payload["score_before"] for a in ("directness", "rhythm", "trust", "authenticity", "density")),
                f"keys: {list(payload['score_before'].keys())}")
except json.JSONDecodeError as e:
    assert_true("E9: JSON mode emits valid JSON", False, f"{e} — stdout: {stdout[:200]!r}")


# ---- E10 — T3 fix: code-block protection ----
# Fenced code block.
e10a = "Here is code:\n```python\ndef navigate(): pass\n```\nAlso navigate this carefully."
e10a_transformed, _, _ = he.transform(e10a, he.load_patterns())
assert_true("E10a: code-fence content NOT rewritten (T3 fix)",
            "def navigate(): pass" in e10a_transformed,
            f"got: {e10a_transformed!r}")
assert_true("E10b: code-fence prose context IS rewritten",
            "handle this carefully" in e10a_transformed.lower(),
            f"got: {e10a_transformed!r}")

# Inline backtick.
e10c = "The function `navigate()` does X. We should navigate to that conclusion."
e10c_transformed, _, _ = he.transform(e10c, he.load_patterns())
assert_true("E10c: inline `code` NOT rewritten",
            "`navigate()`" in e10c_transformed,
            f"got: {e10c_transformed!r}")
assert_true("E10d: prose surrounding inline code IS rewritten",
            "handle to" in e10c_transformed.lower(),
            f"got: {e10c_transformed!r}")


# ---- E11 — T8 fix: case-preserving substitution ----
e11a = "Navigate this challenge."
e11a_transformed, _, _ = he.transform(e11a, he.load_patterns())
assert_true("E11a: 'Navigate' -> 'Handle' (Title case preserved)",
            "Handle" in e11a_transformed,
            f"got: {e11a_transformed!r}")

e11b = "NAVIGATE THIS CHALLENGE."
e11b_transformed, _, _ = he.transform(e11b, he.load_patterns())
assert_true("E11b: 'NAVIGATE' -> 'HANDLE' (ALL CAPS preserved)",
            "HANDLE" in e11b_transformed,
            f"got: {e11b_transformed!r}")

e11c = "we should navigate this."
e11c_transformed, _, _ = he.transform(e11c, he.load_patterns())
assert_true("E11c: 'navigate' -> 'handle' (lowercase preserved)",
            "handle" in e11c_transformed,
            f"got: {e11c_transformed!r}")


# ---- E12 — T7 fix: finding de-duplication by span ----
# 'Look,' is in both throat_clearing_openers AND paragraph_starter_blacklist.
# Pre-fix: 2 findings for same span. Post-fix: 1 (highest-severity action).
e12_text = "Look, this is the point."
e12_report = he.analyze(e12_text)
look_findings = [f for f in e12_report.findings if "look" in f.match.lower()]
assert_true("E12: 'Look,' span de-duplicated (T7 fix)",
            len(look_findings) <= 1,
            f"got {len(look_findings)} findings for 'Look,': {[(f.category, f.action) for f in look_findings]}")


# ---- E13 — T6 fix: --seed flag accepted ----
code, _, stderr = run_cli("Hello world.", "--mode", "analyze", "--seed", "42")
assert_eq("E13: --seed flag accepted without error", code, 0)


# Summary
total = passed + len(failed)
print(f"\nEnglish fragility: {passed}/{total} passed")
if failed:
    print("Failures:")
    for name, msg in failed:
        print(f"  - {name}: {msg}")
sys.exit(0 if not failed else 1)
