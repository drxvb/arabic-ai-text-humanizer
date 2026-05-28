#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verb_agreement_validator.py — Arabic verb-subject agreement validator.

v2.6.4 ships the MODULE + wires it into humanize_v2.py's lex pass.
Implements Agent A's #2 missing-feature finding from the multi-agent
review:

  > AI consistently writes `الحكومات أعلنت` (fem-pl + sing-fem verb is
  > correct) but also `الحكومات أعلنوا` (with masc-pl). The skill has
  > zero agreement validation.

## The rule (per Arabic grammar)

Sound feminine plural noun (`جمع مؤنث سالم`, ending in `ـات`) followed
by a verb:

- Non-human plural (`غير عاقل`): verb MUST be singular feminine.
  e.g., الشركات أعلنت ✓ — NOT الشركات أعلنوا ✗
- Human feminine plural (`عاقل` مؤنث): verb is feminine plural (`ـن`)
  OR singular feminine (`ـت`). NEVER masculine plural (`ـوا`).
  e.g., الطبيبات أكدن ✓ OR الطبيبات أكدت ✓ — NOT الطبيبات أكدوا ✗

## What this module catches

The single error class: noun-ending-in-`ـات` followed within a small
window by a verb in masculine-plural form (suffix `ـوا`). The correction
is the singular-feminine form (suffix `ـت`).

## Conservative by design

False positives in this domain are costly (changing verb morphology
changes meaning). The detection rules:

1. Verb must be IMMEDIATELY after the noun, OR separated by at most
   ONE short particle (قد, لم, لا, لن, ما, لقد, إنما, سوف).
2. Verb must be in a curated list of ~40 common newsroom/editorial
   verbs in both forms. Novel verbs (rare in corpus) are NOT touched.
3. The noun must be at least 4 characters (avoids partial matches on
   short non-plural words ending in `ات`).
4. The substitution operates outside quoted spans (caller's
   responsibility to wrap via `_apply_outside_quotes` if needed).

Python 3 stdlib only.
"""
from __future__ import annotations

import re
import sys
from typing import List, Tuple

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


# ── Curated verb table: masculine-plural perfective -> singular-feminine ──
# Selected from high-frequency newsroom / editorial corpora. Each pair
# was verified by hand to ensure the transformation is unambiguous.
# Plain form-I and form-IV verbs dominate; some form-VIII and form-X.
VERB_PAIRS = {
    # form-I / form-IV — most common newsroom verbs
    "أعلنوا": "أعلنت",
    "قالوا": "قالت",
    "ذكروا": "ذكرت",
    "أضافوا": "أضافت",
    "كتبوا": "كتبت",
    "أكدوا": "أكدت",
    "وصلوا": "وصلت",
    "أصدروا": "أصدرت",
    "أشاروا": "أشارت",
    "نشروا": "نشرت",
    "أعدوا": "أعدت",
    "بدأوا": "بدأت",
    "اتخذوا": "اتخذت",
    "أكملوا": "أكملت",
    "وقعوا": "وقعت",
    "قرروا": "قررت",
    "نفذوا": "نفذت",
    "حققوا": "حققت",
    "طوروا": "طورت",
    "أطلقوا": "أطلقت",
    "دعموا": "دعمت",
    "رفضوا": "رفضت",
    "وافقوا": "وافقت",
    "اعتمدوا": "اعتمدت",
    "أنتجوا": "أنتجت",
    "أنشأوا": "أنشأت",
    "اتفقوا": "اتفقت",
    "صرحوا": "صرحت",
    "أكسبوا": "أكسبت",
    "أبدوا": "أبدت",
    "أبدعوا": "أبدعت",
    "أسسوا": "أسست",
    "تبنوا": "تبنت",
    "تجاوزوا": "تجاوزت",
    "تمكنوا": "تمكنت",
    "وضعوا": "وضعت",
    "بحثوا": "بحثت",
    "حضروا": "حضرت",
    "حذروا": "حذرت",
    "خاطبوا": "خاطبت",
    "دفعوا": "دفعت",
    "ساهموا": "ساهمت",
    "سعوا": "سعت",
}

# Particles that can legitimately appear between subject and verb without
# breaking the noun-verb relationship.
INTERVENING_PARTICLES = {"قد", "لم", "لا", "لن", "ما", "لقد", "إنما", "سوف", "سَ"}

# Sound feminine plural marker: 4+ char Arabic word ending in ـات
NOUN_AT_RE = re.compile(r"\b[ء-ي]{2,}ات\b")


def _find_verb_after_noun(text: str, noun_end: int,
                          max_window_chars: int = 30) -> Tuple[int, int, str] | None:
    """Find the first masc-plural verb from VERB_PAIRS within `max_window_chars`
    of the noun, allowing at most one intervening particle. Returns
    (start, end, masc_form) or None.
    """
    window_start = noun_end
    window_end = min(len(text), noun_end + max_window_chars)
    window = text[window_start:window_end]

    # Tokenize the window into Arabic tokens (separated by whitespace).
    # We need to know: what's between the noun and any candidate verb?
    tokens = re.findall(r"\S+", window)
    if not tokens:
        return None

    # Allow up to ONE intervening particle. So:
    #   token 0 might be the verb directly
    #   OR token 0 is a particle and token 1 is the verb
    candidate_positions: List[int] = [0]
    if len(tokens) >= 2 and tokens[0] in INTERVENING_PARTICLES:
        candidate_positions.append(1)

    for tok_idx in candidate_positions:
        tok = tokens[tok_idx]
        # Strip trailing punctuation so we can match the bare verb form.
        bare = re.sub(r"[،؛؟!.,:;\(\)\[\]\"«»]+$", "", tok)
        if bare in VERB_PAIRS:
            # Compute absolute position by finding this token in `window`.
            # Use re.finditer with the bare token to locate.
            for tm in re.finditer(re.escape(bare), window):
                # Skip matches that aren't the right token occurrence.
                # Simplest: find the FIRST occurrence after the appropriate
                # number of preceding tokens. For the conservative path
                # (tok_idx <= 1), just use the first match.
                return (window_start + tm.start(),
                        window_start + tm.end(),
                        bare)
    return None


def find_agreement_errors(text: str) -> List[dict]:
    """Return list of (noun, verb_wrong, verb_correct, noun_pos, verb_start, verb_end)
    for every detected fem-pl-noun + masc-pl-verb pair.
    """
    findings: List[dict] = []
    for m in NOUN_AT_RE.finditer(text):
        result = _find_verb_after_noun(text, m.end())
        if result is None:
            continue
        verb_start, verb_end, verb_wrong = result
        verb_correct = VERB_PAIRS[verb_wrong]
        findings.append({
            "noun": m.group(),
            "noun_pos": m.start(),
            "noun_end": m.end(),
            "verb_wrong": verb_wrong,
            "verb_correct": verb_correct,
            "verb_start": verb_start,
            "verb_end": verb_end,
        })
    return findings


def fix_verb_agreement(text: str) -> Tuple[str, List[str]]:
    """Apply verb-subject agreement corrections. Returns (corrected_text, applied).
    Conservative: corrections fire only when noun ending in ـات is within ~30
    chars of a curated masc-pl verb, allowing at most one intervening particle.
    """
    findings = find_agreement_errors(text)
    if not findings:
        return text, []
    # Apply right-to-left so verb-substitution doesn't shift earlier positions.
    findings.sort(key=lambda f: f["verb_start"], reverse=True)
    out = text
    applied: List[str] = []
    for f in findings:
        out = out[:f["verb_start"]] + f["verb_correct"] + out[f["verb_end"]:]
        applied.append(f"{f['noun']} + {f['verb_wrong']} -> {f['verb_correct']}")
    return out, applied


def cli_main() -> int:
    import argparse
    p = argparse.ArgumentParser(description="Arabic verb-subject agreement corrector")
    p.add_argument("--text", "-t", help="Inline text")
    p.add_argument("--input", "-i", help="File")
    p.add_argument("--report", action="store_true", help="Show what changed")
    p.add_argument("--analyze", action="store_true", help="Flag-only, don't transform")
    args = p.parse_args()
    if args.input:
        text = open(args.input, encoding="utf-8").read()
    elif args.text:
        text = args.text
    else:
        p.error("--text or --input required")
        return 2

    if args.analyze:
        findings = find_agreement_errors(text)
        print(f"# Verb-agreement findings: {len(findings)}\n")
        for f in findings:
            print(f"- {f['noun']!r} + {f['verb_wrong']!r} -> {f['verb_correct']!r} (verb at {f['verb_start']})")
        return 0

    fixed, applied = fix_verb_agreement(text)
    if args.report:
        print(f"# Verb-agreement corrections: {len(applied)}\n")
        for op in applied:
            print(f"- {op}")
        print(f"\n## Output\n\n{fixed}")
    else:
        print(fixed)
    return 0


if __name__ == "__main__":
    sys.exit(cli_main())
