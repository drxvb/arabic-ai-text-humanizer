#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
orthographic_validator.py — Arabic orthographic hygiene pass.

v2.6.1 ships the MODULE; v2.6.2 will wire it into humanize_v2.py's
lex pass. Implements Agent A's #1 missing-feature finding:

  > Hamzat al-waṣl vs hamzat al-qaṭʿ — AI translators routinely write
  > `إستخدام`/`إستراتيجية` (wrong qaṭʿ on a waṣl word). The skill claims
  > "anti-translationese" but doesn't fix this; it's the #1 visible
  > AI-Arabic tell after حركة connectors. A regex pass for the common
  > 30 misspellings would land in 50 lines.

This module implements that pass. Form-X verbal nouns (استفعال,
استفعل) take hamzat al-waṣl, which is NOT written with a hamza
marker (no ء above or below the alif). AI consistently writes them
with `إ` (hamzat al-qaṭʿ) — that's the bug.

The fix is a controlled substitution against a curated list of
attested form-X verbal nouns + their derivative forms. We do NOT
do a blanket `إست` → `است` substitution because some words legitimately
start with `إست` (proper nouns, loanwords).

Python 3 stdlib only.
"""
from __future__ import annotations

import re
import sys
from typing import List, Tuple

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


# Form-X verbal nouns and verbs where AI consistently writes the wrong hamza.
# Each entry: the AI-wrong form (with إ) and the corpus-attested correct form
# (with ا — no visible hamza marker because hamzat al-waṣl is silent in writing).
# Curated from native-MSA editorial practice + IPCC/UN/Aljazeera Arabic.
FORM_X_VERBAL_NOUNS = {
    # Tech / Business
    "إستخدام": "استخدام",
    "إستراتيجية": "استراتيجية",
    "إستراتيجي": "استراتيجي",
    "إستراتيجياً": "استراتيجياً",
    "إستثمار": "استثمار",
    "إستثماري": "استثماري",
    "إستقرار": "استقرار",
    "إستيراد": "استيراد",
    "إستيرادات": "استيرادات",
    "إستقبال": "استقبال",
    "إستجابة": "استجابة",
    "إستجابات": "استجابات",
    "إستشارة": "استشارة",
    "إستشاري": "استشاري",
    "إستعداد": "استعداد",
    "إستفسار": "استفسار",
    "إستنتاج": "استنتاج",
    "إستدلال": "استدلال",
    "إستئناف": "استئناف",
    "إسترداد": "استرداد",
    "إسترجاع": "استرجاع",
    "إستكمال": "استكمال",
    "إستكشاف": "استكشاف",
    "إستعراض": "استعراض",
    "إستمرار": "استمرار",
    "إستمرارية": "استمرارية",
    "إستهلاك": "استهلاك",
    "إستبدال": "استبدال",
    "إستبيان": "استبيان",
    "إستخراج": "استخراج",
    "إستدعاء": "استدعاء",
    "إستسلام": "استسلام",
    "إستشهاد": "استشهاد",
    "إستطاعة": "استطاعة",
    "إستعلام": "استعلام",
    "إستعلامات": "استعلامات",
    "إستفادة": "استفادة",
    "إستقالة": "استقالة",
    "إستلهام": "استلهام",
    "إستمتاع": "استمتاع",
    "إستنباط": "استنباط",
    "إستنزاف": "استنزاف",
    "إستهداف": "استهداف",
    "إستهلال": "استهلال",
    "إستياء": "استياء",
    "إستيعاب": "استيعاب",
    "إستيقاظ": "استيقاظ",
    "إستفتاء": "استفتاء",
    "إستحضار": "استحضار",
    "إستحقاق": "استحقاق",
}

# Compiled patterns for speed.
_COMPILED = [
    (re.compile(r"\b" + re.escape(wrong) + r"\b"), correct)
    for wrong, correct in FORM_X_VERBAL_NOUNS.items()
]


def fix_hamzat_alwasl(text: str) -> Tuple[str, List[str]]:
    """
    Apply form-X verbal-noun corrections. Returns (corrected_text, applied_list).
    Each applied entry is `"إستخدام -> استخدام"` for the report.
    """
    out = text
    applied: List[str] = []
    for pat, correct in _COMPILED:
        new = pat.sub(correct, out)
        if new != out:
            wrong = next(w for w, c in FORM_X_VERBAL_NOUNS.items() if c == correct)
            applied.append(f"{wrong} -> {correct}")
        out = new
    return out, applied


def cli_main() -> int:
    import argparse
    p = argparse.ArgumentParser(description="Apply Arabic hamzat al-waṣl/qaṭʿ corrections")
    p.add_argument("--text", "-t", help="Inline text")
    p.add_argument("--input", "-i", help="File")
    p.add_argument("--report", action="store_true", help="Show what changed")
    args = p.parse_args()
    if args.input:
        text = open(args.input, encoding="utf-8").read()
    elif args.text:
        text = args.text
    else:
        p.error("--text or --input required")
        return 2
    fixed, applied = fix_hamzat_alwasl(text)
    if args.report:
        print(f"# Hamzat al-waṣl validator\n")
        print(f"**Corrections applied:** {len(applied)}\n")
        for op in applied:
            print(f"- {op}")
        print(f"\n## Output\n\n{fixed}")
    else:
        print(fixed)
    return 0


if __name__ == "__main__":
    sys.exit(cli_main())
