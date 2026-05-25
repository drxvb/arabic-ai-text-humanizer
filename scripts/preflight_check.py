#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pre-flight factual / ethical / sourcing-hygiene check for Arabic AI text.

Per cross-LLM strategic critique: the 16-dimension humanizer optimizes for
prose QUALITY, not TRUTH. A beautifully-humanized falsehood is more dangerous
than the AI-flat original. This script flags suspect content BEFORE the
humanizer runs — it does NOT transform; it FLAGS.

Detection categories:
  1. Unsourced statistics (numeric claims without "حسب" / "وفق" / "بحسب" attribution)
  2. Named people with specific quotes (verify quote attribution)
  3. Loaded adjective-stacks on groups (bias indicator)
  4. Sweeping generalizations ("كل العرب"، "جميع المسلمين"، "دائماً ما يَفعل X")
  5. Anonymous-source chains without verification ("مصادر مطلعة لم تَكشف عن هويتها")
  6. Pseudo-precision quantifiers ("نحو 73%"، "تَقريباً ثلاثة أرباع")
  7. Stance verbs in quote attribution (already flagged in Gap-D; cross-listed)

Usage:
    python preflight_check.py --input "نص" --report
    python preflight_check.py --file in.txt --json [--strict]

Exit codes:
    0 — clean (no flags)
    1 — flags found (review before transformation)
    2 — hard-fail (blocking issue: --strict and HIGH-severity finding)
"""
from __future__ import annotations
import argparse, json, re, sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


# ── Detection patterns ──────────────────────────────────────────────────────

# 1. Unsourced statistics — number followed by % / unit, but no attribution
UNSOURCED_STAT = re.compile(
    r'(?<!حسب\s)(?<!وفق\s)(?<!بحسب\s)'
    r'\b\d+(?:[.,]\d+)?\s*(?:%|٪|بالمئة|في\s+المئة|مليون|مليار|ألف)\b',
    re.UNICODE
)

# 2. Named-person + specific quote (Arabic quotation marks « » or " ")
NAMED_QUOTE = re.compile(
    r'(?:قال|قالت|أكّد|أكدت|صرّح|صرّحت|أعلن|أعلنت)\s+'
    r'(?:الرئيس|الوزير|المدير|الدكتور|السيد|الأستاذ|البروفيسور|الشيخ)\s+'
    r'[ء-ي]+(?:\s+[ء-ي]+){0,3}'
    r'\s*[:،,]?\s*[«"]'
)

# 3. Loaded adjective triplets on group nouns
LOADED_GROUP_ADJ = re.compile(
    r'(?:كل|جميع|عامة|أغلب)\s+'
    r'(?:العرب|المسلمين|الغرب|الأوروبيين|الأمريكيين|اليهود|الصينيين|الروس|الإيرانيين|السعوديين)'
)

# 4. Sweeping generalizations — "دائماً X" / "أبداً Y" / "في كل مرة"
SWEEPING = [
    re.compile(r'\b(?:دائماً|أبداً|قط)\s+[ء-ي]+\s+ما\s+'),
    re.compile(r'\bفي\s+كلّ?\s+مرة\b'),
    re.compile(r'\bكل\s+(?:عربي|مسلم|يهودي|مسيحي|غربي)\b'),
    re.compile(r'\bجميع(?:هم|هن|نا|كم)\b'),
]

# 5. Anonymous-source chains
ANON_SOURCE = re.compile(
    r'(?:مصادر|مصدر)\s+(?:مطلعة|مطلع|مسؤولة|مسؤول|دبلوماسية|أمنية)'
    r'(?:\s+لم\s+تَ?كشف\s+عن\s+هويت(?:ها|ه)|\s+فضّلت?\s+عدم\s+ذكر\s+الاسم)?'
)

# 6. Pseudo-precision quantifiers
PSEUDO_PRECISION = re.compile(
    r'(?:نحو|تقريباً|تَقريباً|قرابة|حوالي|ما\s+يقارب)\s+\d+(?:[.,]\d+)?'
)

# 7. Hostile/stance verbs in attribution (cross-listed with Gap D safety)
HOSTILE_QUOTE = re.compile(
    r'(?:زعم|ادّعى|تَفاخر|تَبجّح|اعترف|أَقرّ)\s+(?:بأنّ?|أنّ?|أن)'
)


def check(text: str) -> dict:
    findings = []

    for m in UNSOURCED_STAT.finditer(text):
        findings.append({
            "category": "unsourced_statistic",
            "severity": "HIGH" if "%" in m.group(0) or "٪" in m.group(0) else "MEDIUM",
            "text": m.group(0),
            "position": m.start(),
            "advice": "Add attribution: 'حسب X' / 'وفق دراسة Y' / 'بحسب تقرير Z'",
        })

    for m in NAMED_QUOTE.finditer(text):
        findings.append({
            "category": "named_quote_attribution",
            "severity": "HIGH",
            "text": m.group(0)[:80],
            "position": m.start(),
            "advice": "Verify the quote with the cited person before publication. AI may have fabricated attribution.",
        })

    for m in LOADED_GROUP_ADJ.finditer(text):
        findings.append({
            "category": "loaded_group_generalization",
            "severity": "HIGH",
            "text": m.group(0),
            "position": m.start(),
            "advice": "Sweeping generalization about a group. Replace with specific subgroup or named instances.",
        })

    for pat in SWEEPING:
        for m in pat.finditer(text):
            findings.append({
                "category": "sweeping_generalization",
                "severity": "MEDIUM",
                "text": m.group(0),
                "position": m.start(),
                "advice": "Sweeping claim ('دائماً' / 'كل' / 'جميع'). Soften or qualify.",
            })

    for m in ANON_SOURCE.finditer(text):
        findings.append({
            "category": "anonymous_source_chain",
            "severity": "MEDIUM",
            "text": m.group(0)[:80],
            "position": m.start(),
            "advice": "Anonymous sourcing. Verify with named editorial chain; do not let humanizer beautify into more credible-seeming prose without verification.",
        })

    for m in PSEUDO_PRECISION.finditer(text):
        findings.append({
            "category": "pseudo_precision",
            "severity": "LOW",
            "text": m.group(0),
            "position": m.start(),
            "advice": "Pseudo-precise quantifier ('نحو 73%'). Either commit to exact figure with source, or use plain qualitative description.",
        })

    for m in HOSTILE_QUOTE.finditer(text):
        findings.append({
            "category": "hostile_attribution_verb",
            "severity": "MEDIUM",
            "text": m.group(0)[:80],
            "position": m.start(),
            "advice": "Hostile attribution verb (زعم/ادّعى). Verify the editorial stance was intended; AI may have inserted bias.",
        })

    severities = [f["severity"] for f in findings]
    return {
        "n_findings": len(findings),
        "n_high": severities.count("HIGH"),
        "n_medium": severities.count("MEDIUM"),
        "n_low": severities.count("LOW"),
        "findings": findings,
        "verdict": ("BLOCK" if "HIGH" in severities
                    else "FLAG" if findings else "CLEAN"),
    }


def render_report(result: dict, text: str) -> str:
    lines = []
    lines.append("=" * 70)
    lines.append("Pre-flight factual / ethical / sourcing-hygiene check")
    lines.append("=" * 70)
    lines.append(f"Verdict: {result['verdict']}")
    lines.append(f"Findings: {result['n_findings']} total  "
                 f"({result['n_high']} HIGH, {result['n_medium']} MEDIUM, "
                 f"{result['n_low']} LOW)")
    if not result["findings"]:
        lines.append("\n✓ No flags. Safe to proceed with humanization.")
        return "\n".join(lines)
    lines.append("")
    for i, f in enumerate(result["findings"], 1):
        lines.append(f"\n[{i}] {f['severity']:<6} {f['category']}")
        lines.append(f"    Found: \"{f['text']}\"")
        lines.append(f"    Advice: {f['advice']}")
    lines.append("")
    if result["verdict"] == "BLOCK":
        lines.append("⚠ HIGH-severity findings present. Use --strict to BLOCK humanization.")
        lines.append("  Otherwise: flags are advisory only; humanization will proceed.")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", "-i", help="Inline text")
    ap.add_argument("--file", "-f", type=Path, help="Read from file")
    ap.add_argument("--strict", action="store_true",
                    help="Exit code 2 if HIGH-severity findings present")
    ap.add_argument("--json", action="store_true", help="JSON output")
    ap.add_argument("--report", action="store_true", help="Human-readable report")
    args = ap.parse_args()

    if args.file:
        text = args.file.read_text(encoding="utf-8")
    elif args.input:
        text = args.input
    else:
        text = sys.stdin.read()
    if not text.strip():
        raise SystemExit("empty input")

    result = check(text)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(render_report(result, text))

    if args.strict and result["verdict"] == "BLOCK":
        sys.exit(2)
    sys.exit(1 if result["findings"] else 0)


if __name__ == "__main__":
    main()
