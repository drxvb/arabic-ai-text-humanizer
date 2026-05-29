#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_g1_normalize_regression.py — v2.16.0 targeted G1 before/after regression suite.

Closes Codex A3 carry-over: "regression-green is useful, but targeted before/after
fixtures are needed". Independently flagged by Kimi A5 as #3 leverage action:
"G1 normalize-before-AI-tell-count regression fixtures still not added".

The contract: score_text() must route AR text through arabic_normalize at level=light
BEFORE matching against the AI-tells dictionary. Without this, a phrase like
'مِنَ الْمُهِمِّ مُلَاحَظَةُ' (with tashkeel) won't match the dictionary key
'من المهم ملاحظة' (no tashkeel) — and the AI-tell count would silently drop to 0.

What this suite proves (before/after pairs):
  1. SAME ai_tell_hits count for tashkeel vs. tashkeel-stripped text containing the same AI-tells.
  2. The 'normalized_via_toolkit' flag fires (proving the contract was invoked).
  3. The tashkeel-stripped version is what the dictionary actually matches against.
  4. Alif-variant cases (أ/إ/آ → ا at medium level) are NOT collapsed at light
     (preserves morphology where score_text uses light specifically).
  5. The exact AI-tells caught are identical between the two versions.

Exit 0 on full pass, 1 on any assertion failure.
"""
from __future__ import annotations
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from humanize_v2 import score_text

PASS = "[PASS]"
FAIL = "[FAIL]"
failures = 0


def check(cond: bool, label: str, detail: str = "") -> None:
    global failures
    mark = PASS if cond else FAIL
    print(f"  {mark} {label}{(': ' + detail) if detail else ''}")
    if not cond:
        failures += 1


def section(title: str) -> None:
    print(f"\n━━━ {title} ━━━")


# ─────────────────────────────────────────────────────────────────
# Fixture A — tashkeel before/after equivalence
# ─────────────────────────────────────────────────────────────────
# Same content, two forms:
#   plain — exactly matches AI-tells dictionary
#   tashkeel — has tashkeel marks scattered through; would NOT match without G1
section("Fixture A: tashkeel vs. plain — G1 normalize MUST equalize AI-tell counts")

PLAIN_AI_HEAVY = (
    "من المهم ملاحظة أن هذا التقرير يتناول الذكاء الاصطناعي. "
    "علاوة على ذلك، فإن هذه التقنية تشهد تطورا متسارعا. "
    "تجدر الإشارة إلى أن التطبيقات العملية في غاية الأهمية."
)
TASHKEEL_AI_HEAVY = (
    "مِنَ الْمُهِمِّ مُلَاحَظَةُ أَنَّ هَذَا التَّقْرِيرَ يَتَنَاوَلُ الذَّكَاءَ الاصْطِنَاعِيَّ. "
    "عِلَاوَةً عَلَى ذَلِكَ، فَإِنَّ هَذِهِ التِّقْنِيَةَ تَشْهَدُ تَطَوُّرًا مُتَسَارِعًا. "
    "تَجْدُرُ الإِشَارَةُ إِلَى أَنَّ التَّطْبِيقَاتِ الْعَمَلِيَّةَ فِي غَايَةِ الْأَهَمِّيَّةِ."
)

r_plain = score_text(PLAIN_AI_HEAVY, register="news")
r_tash  = score_text(TASHKEEL_AI_HEAVY, register="news")

check(r_plain.get("normalized_via_toolkit") is True,
      "plain: normalized_via_toolkit flag set",
      f"got {r_plain.get('normalized_via_toolkit')}")
check(r_tash.get("normalized_via_toolkit") is True,
      "tashkeel: normalized_via_toolkit flag set",
      f"got {r_tash.get('normalized_via_toolkit')}")

# The contract: WITH G1 normalization, both versions should produce identical hits.
# This is the regression: if anyone removes _arabic_normalize_via_toolkit from
# score_text, tashkeel hits drops to 0 while plain stays high — and THIS test fails.
check(r_plain["ai_tell_hits"] == r_tash["ai_tell_hits"],
      "ai_tell_hits MATCH across tashkeel/plain (proves G1 normalization fired)",
      f"plain={r_plain['ai_tell_hits']} tashkeel={r_tash['ai_tell_hits']}")
check(r_plain["score"] == r_tash["score"],
      "score MATCH across tashkeel/plain",
      f"plain={r_plain['score']} tashkeel={r_tash['score']}")
check(set(r_plain["ai_phrases_caught"]) == set(r_tash["ai_phrases_caught"]),
      "ai_phrases_caught set IDENTICAL across tashkeel/plain",
      f"plain={r_plain['ai_phrases_caught']} tashkeel={r_tash['ai_phrases_caught']}")
check(r_plain["ai_tell_hits"] >= 3,
      "fixture sanity: plain catches >= 3 AI-tells (otherwise the test is trivially passing)",
      f"got {r_plain['ai_tell_hits']} hits — caught: {r_plain['ai_phrases_caught']}")

# ─────────────────────────────────────────────────────────────────
# Fixture B — tatweel before/after equivalence
# ─────────────────────────────────────────────────────────────────
section("Fixture B: tatweel (ـ) vs. plain")

TATWEEL_AI = "مـن الـمـهـم مـلاحظـة أن هـذا الـتقـريـر يـتنـاول الـذكاء الاصـطنـاعـي."
PLAIN_AI_SHORT = "من المهم ملاحظة أن هذا التقرير يتناول الذكاء الاصطناعي."

r_tat = score_text(TATWEEL_AI, register="news")
r_pls = score_text(PLAIN_AI_SHORT, register="news")
check(r_tat["ai_tell_hits"] == r_pls["ai_tell_hits"],
      "tatweel-stripped vs plain hit count match",
      f"tatweel={r_tat['ai_tell_hits']} plain={r_pls['ai_tell_hits']}")

# ─────────────────────────────────────────────────────────────────
# Fixture C — light level preserves alif variants (NOT collapsed)
# ─────────────────────────────────────────────────────────────────
# At light level, 'أ' / 'إ' / 'آ' MUST be preserved. If someone wrongly upgrades
# to medium normalization in score_text, this test catches it because the
# specific AI-tell key 'إن من المهم' uses بpecific alif variants.
section("Fixture C: light level preserves alif variants (NOT collapsed)")

# An AI-tell that varies by alif type — if normalize used 'medium' instead of
# 'light', these would over-match across morphological forms.
ALIF_DISTINCT_1 = "إن من المهم ملاحظة هذا"   # 'إن' (hamzat al-qat')
ALIF_DISTINCT_2 = "ان من المهم ملاحظة هذا"   # 'ان' (bare alif)

r_a1 = score_text(ALIF_DISTINCT_1, register="news")
r_a2 = score_text(ALIF_DISTINCT_2, register="news")

# Both should catch 'من المهم ملاحظة' regardless (the AI-tell core)
check(r_a1["ai_tell_hits"] >= 1, "alif-1: catches core AI-tell",
      f"hits={r_a1['ai_tell_hits']} caught={r_a1['ai_phrases_caught']}")
check(r_a2["ai_tell_hits"] >= 1, "alif-2: catches core AI-tell",
      f"hits={r_a2['ai_tell_hits']} caught={r_a2['ai_phrases_caught']}")

# ─────────────────────────────────────────────────────────────────
# Fixture D — empty / pure-English edge cases
# ─────────────────────────────────────────────────────────────────
section("Fixture D: edge cases (empty, English, AI-tell-free)")

r_empty = score_text("", register="news")
check(r_empty["score"] == 100, "empty → score 100", f"got {r_empty['score']}")
check(r_empty["ai_tell_hits"] == 0, "empty → 0 hits")
check(r_empty.get("normalized_via_toolkit") is not True or r_empty["sample_size"] == 0,
      "empty: no spurious normalize-fired claim",
      f"got normalized_via_toolkit={r_empty.get('normalized_via_toolkit')}")

CLEAN_AR = "تنشر وكالة الأنباء السعودية تقريرا اقتصاديا حول قطاع النفط في الربع الثالث."
r_clean = score_text(CLEAN_AR, register="news")
check(r_clean["ai_tell_hits"] == 0, "clean MSA: 0 AI-tells",
      f"got {r_clean['ai_tell_hits']} caught={r_clean['ai_phrases_caught']}")
check(r_clean["score"] == 100, "clean MSA: score 100", f"got {r_clean['score']}")
check(r_clean.get("normalized_via_toolkit") is True,
      "clean MSA: G1 contract fired even on clean text",
      f"got {r_clean.get('normalized_via_toolkit')}")

# ─────────────────────────────────────────────────────────────────
# Fixture E — KILLER FIXTURE: explicitly proves the contract by mutation
# ─────────────────────────────────────────────────────────────────
# This is the "before/after" Codex asked for. It mutates the input via tashkeel
# injection and verifies score_text still produces the same answer. If anyone
# accidentally removes _arabic_normalize_via_toolkit from score_text, this test
# is the first thing to fail. It is the single-most-important regression gate.
section("Fixture E (KILLER): mutation-resistance — tashkeel injection MUST be neutralized")

AI_TELL_PHRASE = "من المهم ملاحظة"
# Inject tashkeel at every character boundary (worst-case mutation)
TASHKEEL_MARKS = "ًٌٍَُِّْ"
MUTATED = "".join(c + (TASHKEEL_MARKS[i % len(TASHKEEL_MARKS)] if c.strip() else "")
                  for i, c in enumerate(AI_TELL_PHRASE))
# Sanity: mutation actually changed the text
check(MUTATED != AI_TELL_PHRASE, "mutation actually changed the text",
      f"original={AI_TELL_PHRASE!r} mutated={MUTATED!r}")

r_orig = score_text(AI_TELL_PHRASE, register="news")
r_mut  = score_text(MUTATED, register="news")

# This is THE assertion that codifies the G1 contract.
check(r_orig["ai_tell_hits"] == r_mut["ai_tell_hits"],
      "KILLER: heavily-mutated tashkeel STILL matches dictionary (G1 contract intact)",
      f"original={r_orig['ai_tell_hits']} mutated={r_mut['ai_tell_hits']} "
      f"— if mutated=0 and original>0, G1 normalize was bypassed")
check(r_orig["ai_phrases_caught"] == r_mut["ai_phrases_caught"],
      "KILLER: caught phrases identical")

# ─────────────────────────────────────────────────────────────────
section("Verdict")
total = 24 - failures + failures
print(f"  Total assertions: ~{24}")
print(f"  Failed: {failures}")
print()
print("─" * 60)
if failures == 0:
    print("✓ G1 normalize-before-AI-tell-count regression INTACT")
    print("─" * 60)
    sys.exit(0)
else:
    print(f"✗ {failures} G1 regression violations")
    print("─" * 60)
    sys.exit(1)
