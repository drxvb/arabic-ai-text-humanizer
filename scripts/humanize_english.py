#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
humanize_english.py — English AI-tell removal + 5-axis scoring.

Sibling of humanize_v2.py (which is Arabic-only). This script handles
English text using the catalogue at corpus/english-patterns.json, which
adapts hardikpandya/stop-slop (MIT) into a machine-readable form plus
the 5-axis scoring rubric (Directness / Rhythm / Trust / Authenticity /
Density, max 50, revise below 35).

Two operating modes:
  --mode analyze     — flag patterns + emit 5-axis score; do NOT transform
  --mode lex         — apply safe deletions + substitutions (deletes
                       throat-clearing, emphasis crutches, meta-commentary;
                       substitutes business jargon and em-dashes); flag
                       unsafe patterns (binary contrasts, false agency)
  --mode both        — flag + transform + score before AND after (default)

Architecture mirrors humanize_v2.py: deterministic with --seed, no LLM call,
~1s runtime. The cognitive/rhetorical layers from the Arabic pipeline are
out of scope here — English already has stop-slop as a prompt-based skill
for that work; this script complements it with deterministic ops + scoring.

Python 3 stdlib only.

Usage:
    python humanize_english.py --input draft.md --mode both --report
    python humanize_english.py --text "Here's the thing: ..." --mode analyze --json
    python humanize_english.py --input draft.md --mode lex --output cleaned.md
"""
from __future__ import annotations

import argparse
import io
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from statistics import stdev
from typing import Any, Dict, List, Optional, Tuple

# Force UTF-8 on Windows (cp1252 default chokes on em-dashes and any
# non-ASCII glyphs we substitute).
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


REPO_ROOT = Path(__file__).parent.parent
PATTERNS_PATH = REPO_ROOT / "corpus" / "english-patterns.json"


# Language gate: bail early if input is Arabic so users don't accidentally
# run the English pass on Arabic text. (humanize_v2.py is the Arabic path.)
def detect_language(text: str) -> str:
    if not text:
        return "unknown"
    arabic = sum(1 for ch in text if "؀" <= ch <= "ۿ" or "ݐ" <= ch <= "ݿ")
    latin = sum(1 for ch in text if ch.isascii() and ch.isalpha())
    if arabic > latin:
        return "ar"
    if latin > arabic:
        return "en"
    return "unknown"


@dataclass
class Finding:
    layer: str  # lexical | structural | sentence_level
    category: str
    action: str  # delete | substitute | flag
    match: str
    position: int


@dataclass
class Report:
    language: str
    sentence_count: int
    word_count: int
    findings: List[Finding] = field(default_factory=list)
    transformations_applied: List[str] = field(default_factory=list)
    score: Dict[str, int] = field(default_factory=dict)


def load_patterns() -> Dict[str, Any]:
    with PATTERNS_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


def split_sentences(text: str) -> List[str]:
    # Naive but sufficient for scoring; treats ., !, ? as sentence terminators.
    # Keeps abbreviations imperfect; we accept ~5% error for a deterministic heuristic.
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z])", text.strip())
    return [p for p in parts if p.strip()]


def word_count(text: str) -> int:
    return len(re.findall(r"\b[A-Za-z][A-Za-z'-]*\b", text))


def scan_lexical(text: str, patterns: Dict[str, Any]) -> List[Finding]:
    findings: List[Finding] = []
    lex = patterns["lexical"]
    for category, spec in lex.items():
        action = spec["action"]
        if "patterns" in spec:
            for pat in spec["patterns"]:
                for m in re.finditer(re.escape(pat), text, flags=re.IGNORECASE):
                    findings.append(Finding("lexical", category, action, m.group(0), m.start()))
        elif "substitutions" in spec:
            for needle in spec["substitutions"]:
                # Substitutions match as whole words for verbs/nouns, but multi-word
                # phrases pass through as plain regex with word boundaries on both sides.
                pat = r"\b" + re.escape(needle) + r"\b"
                for m in re.finditer(pat, text, flags=re.IGNORECASE):
                    findings.append(Finding("lexical", category, action, m.group(0), m.start()))
    return findings


def scan_structural(text: str, patterns: Dict[str, Any]) -> List[Finding]:
    findings: List[Finding] = []
    struct = patterns["structural"]
    for category, spec in struct.items():
        action = spec.get("action", "flag")
        if "patterns" in spec:
            for pat in spec["patterns"]:
                for m in re.finditer(re.escape(pat), text, flags=re.IGNORECASE):
                    findings.append(Finding("structural", category, action, m.group(0), m.start()))
        if "regex_patterns" in spec:
            for pat in spec["regex_patterns"]:
                try:
                    for m in re.finditer(pat, text, flags=re.IGNORECASE):
                        findings.append(Finding("structural", category, action, m.group(0), m.start()))
                except re.error:
                    continue
    return findings


def scan_sentence_level(text: str, patterns: Dict[str, Any]) -> List[Finding]:
    findings: List[Finding] = []
    sl = patterns["sentence_level"]

    # Wh- sentence starters
    wh = sl.get("wh_starters", {})
    starter_words = wh.get("starter_words", [])
    for m in re.finditer(r"(?:^|(?<=[.!?]\s))(" + "|".join(re.escape(w) for w in starter_words) + r")\b", text):
        findings.append(Finding("sentence_level", "wh_starters", wh["action"], m.group(0), m.start()))

    # Paragraph starter blacklist
    pb = sl.get("paragraph_starter_blacklist", {})
    for word in pb.get("starter_words", []):
        for m in re.finditer(r"(?:^|\n)\s*" + re.escape(word), text, flags=re.IGNORECASE):
            findings.append(Finding("sentence_level", "paragraph_starter_blacklist", pb["action"], m.group(0).strip(), m.start()))

    # Lazy extremes (whole words, case-insensitive)
    le = sl.get("lazy_extremes", {})
    for pat in le.get("patterns", []):
        for m in re.finditer(r"\b" + re.escape(pat) + r"\b", text, flags=re.IGNORECASE):
            findings.append(Finding("sentence_level", "lazy_extremes", le["action"], m.group(0), m.start()))

    # Em-dashes
    em = sl.get("em_dashes", {})
    for needle in em.get("substitutions", {}):
        for m in re.finditer(re.escape(needle), text):
            findings.append(Finding("sentence_level", "em_dashes", em["action"], m.group(0), m.start()))

    return findings


def transform(text: str, patterns: Dict[str, Any]) -> Tuple[str, List[str]]:
    """Apply safe deletions + substitutions; return (transformed_text, applied_ops)."""
    out = text
    applied: List[str] = []

    # 1. Delete throat-clearing openers, emphasis crutches, meta-commentary, filler phrases.
    for category in ("throat_clearing_openers", "emphasis_crutches", "meta_commentary", "filler_phrases"):
        spec = patterns["lexical"].get(category, {})
        if spec.get("action") != "delete":
            continue
        for pat in spec.get("patterns", []):
            # Delete the pattern; collapse residual leading/trailing whitespace.
            new = re.sub(re.escape(pat) + r"\s*", "", out, flags=re.IGNORECASE)
            if new != out:
                applied.append(f"delete[{category}]: {pat!r}")
            out = new

    # 2. Substitute business jargon (word-boundary).
    jargon = patterns["lexical"].get("business_jargon", {})
    if jargon.get("action") == "substitute":
        for src, dst in jargon.get("substitutions", {}).items():
            pat = r"\b" + re.escape(src) + r"\b"
            new = re.sub(pat, dst, out, flags=re.IGNORECASE)
            if new != out:
                applied.append(f"substitute[business_jargon]: {src!r} -> {dst!r}")
            out = new

    # 3. Strip filler adverbs (whole-word, case-insensitive).
    fillers = patterns["lexical"].get("filler_adverbs", {})
    if fillers.get("action") == "delete":
        skip_ctx = [c.lower() for c in fillers.get("skip_when_context", [])]
        for adv in fillers.get("patterns", []):
            # Skip when the adverb is part of a load-bearing context phrase.
            if any(adv.lower() in s for s in skip_ctx):
                continue
            pat = r"\b" + re.escape(adv) + r"\s+"
            new = re.sub(pat, "", out, flags=re.IGNORECASE)
            if new != out:
                applied.append(f"delete[filler_adverbs]: {adv!r}")
            out = new

    # 4. Em-dash substitution.
    em = patterns["sentence_level"].get("em_dashes", {})
    if em.get("action") == "substitute":
        for src, dst in em.get("substitutions", {}).items():
            new = out.replace(src, dst)
            if new != out:
                applied.append(f"substitute[em_dashes]: {src!r} -> {dst!r}")
            out = new

    # Collapse leftover double-spaces and stray comma-comma artifacts from deletions.
    out = re.sub(r"  +", " ", out)
    out = re.sub(r",\s*,", ",", out)
    out = re.sub(r"\.\s*\.", ".", out)
    out = out.strip()
    return out, applied


def score_5_axis(text: str, patterns: Dict[str, Any]) -> Dict[str, int]:
    """Compute Directness / Rhythm / Trust / Authenticity / Density on a 1-10 scale."""
    sentences = split_sentences(text)
    n_sent = max(1, len(sentences))

    # Re-scan to count findings by category. (Cheaper than passing them in.)
    lex_findings = scan_lexical(text, patterns)
    struct_findings = scan_structural(text, patterns)
    sl_findings = scan_sentence_level(text, patterns)

    def count(layer: str, category: str) -> int:
        all_findings = {"lexical": lex_findings, "structural": struct_findings, "sentence_level": sl_findings}[layer]
        return sum(1 for f in all_findings if f.category == category)

    # Sentence length stats for rhythm.
    lengths = [word_count(s) for s in sentences]
    runs_same = 0
    if len(lengths) >= 3:
        i = 0
        while i < len(lengths) - 2:
            if abs(lengths[i] - lengths[i + 1]) <= 1 and abs(lengths[i + 1] - lengths[i + 2]) <= 1:
                runs_same += 1
                i += 3
            else:
                i += 1
    length_stdev = stdev(lengths) if len(lengths) >= 2 else 0.0

    # Per-axis scores (1-10, where 10 = best).
    # Each axis starts at 10 and deducts based on offending findings, normalized
    # to per-100-words density so short and long texts score comparably.
    word_total = max(1, sum(lengths))
    norm = 100.0 / word_total

    directness = 10 - min(9, int(
        (count("lexical", "throat_clearing_openers") +
         count("lexical", "emphasis_crutches") +
         count("lexical", "vague_declaratives") +
         count("lexical", "meta_commentary")) * norm
    ))

    rhythm = 10
    if length_stdev < 4 and len(lengths) >= 3:
        rhythm -= 3
    rhythm -= min(6, runs_same * 2)
    rhythm -= min(2, count("structural", "dramatic_fragmentation") * 2)
    rhythm = max(1, rhythm)

    trust = 10 - min(9, int(
        (count("lexical", "meta_commentary") * 2 +
         count("structural", "rhetorical_setups") +
         count("structural", "negative_listings") * 2 +
         count("lexical", "filler_phrases")) * norm
    ))

    authenticity = 10 - min(9, int(
        (count("lexical", "business_jargon") +
         count("structural", "false_agency") * 2 +
         count("structural", "narrator_from_a_distance")) * norm
    ))

    # Density penalty grows faster — filler is the easiest to detect and cut.
    density = 10 - min(9, int(
        (count("lexical", "filler_adverbs") +
         count("lexical", "filler_phrases") +
         count("sentence_level", "lazy_extremes") +
         count("sentence_level", "em_dashes")) * norm
    ))

    total = directness + rhythm + trust + authenticity + density
    return {
        "directness": max(1, directness),
        "rhythm": max(1, rhythm),
        "trust": max(1, trust),
        "authenticity": max(1, authenticity),
        "density": max(1, density),
        "total": total,
        "threshold_revise_below": patterns["scoring_rubric_5_axis"]["threshold_revise_below"],
        "verdict": "revise" if total < patterns["scoring_rubric_5_axis"]["threshold_revise_below"] else "ship",
    }


def analyze(text: str) -> Report:
    patterns = load_patterns()
    sents = split_sentences(text)
    findings: List[Finding] = []
    findings.extend(scan_lexical(text, patterns))
    findings.extend(scan_structural(text, patterns))
    findings.extend(scan_sentence_level(text, patterns))
    score = score_5_axis(text, patterns)
    return Report(
        language=detect_language(text),
        sentence_count=len(sents),
        word_count=word_count(text),
        findings=findings,
        score=score,
    )


def run(text: str, mode: str) -> Tuple[str, Report, Optional[Dict[str, int]]]:
    """Returns (final_text, report_before, score_after_if_transformed)."""
    patterns = load_patterns()
    report = analyze(text)
    if mode == "analyze":
        return text, report, None
    transformed, ops = transform(text, patterns)
    report.transformations_applied = ops
    if mode == "lex":
        return transformed, report, None
    # mode == "both"
    score_after = score_5_axis(transformed, patterns)
    return transformed, report, score_after


def format_report(text_before: str, text_after: str, report: Report,
                  score_after: Optional[Dict[str, int]], mode: str) -> str:
    out = ["# English Humanizer Report\n"]
    out.append(f"**Language detected:** {report.language}")
    out.append(f"**Sentences:** {report.sentence_count} · **Words:** {report.word_count}")
    out.append(f"**Mode:** {mode}\n")

    out.append("## 5-Axis Score (max 50; revise below 35)\n")
    s = report.score
    out.append(f"| Axis | Score | Out of |")
    out.append(f"|---|---|---|")
    out.append(f"| Directness | {s['directness']} | 10 |")
    out.append(f"| Rhythm | {s['rhythm']} | 10 |")
    out.append(f"| Trust | {s['trust']} | 10 |")
    out.append(f"| Authenticity | {s['authenticity']} | 10 |")
    out.append(f"| Density | {s['density']} | 10 |")
    out.append(f"| **TOTAL** | **{s['total']}** | **50** |")
    out.append(f"\n**Verdict:** {s['verdict']}")

    if score_after:
        out.append("\n## After Transformation\n")
        out.append(f"| Axis | Before | After | Delta |")
        out.append(f"|---|---|---|---|")
        for axis in ("directness", "rhythm", "trust", "authenticity", "density"):
            before = s[axis]
            after = score_after[axis]
            delta = after - before
            sign = "+" if delta > 0 else ""
            out.append(f"| {axis.title()} | {before} | {after} | {sign}{delta} |")
        out.append(f"| **TOTAL** | **{s['total']}** | **{score_after['total']}** | **{'+' if score_after['total']-s['total']>0 else ''}{score_after['total']-s['total']}** |")
        out.append(f"\n**Verdict after:** {score_after['verdict']}")

    if report.findings:
        out.append(f"\n## Findings ({len(report.findings)})\n")
        # Group by category.
        from collections import defaultdict
        by_cat = defaultdict(list)
        for f in report.findings:
            by_cat[(f.layer, f.category, f.action)].append(f.match)
        for (layer, category, action), matches in sorted(by_cat.items()):
            unique = sorted(set(matches))
            out.append(f"- **[{action}] {layer}/{category}** ({len(matches)} matches): {', '.join(repr(m) for m in unique[:5])}{'...' if len(unique) > 5 else ''}")

    if report.transformations_applied:
        out.append(f"\n## Transformations Applied ({len(report.transformations_applied)})\n")
        for op in report.transformations_applied[:30]:
            out.append(f"- {op}")
        if len(report.transformations_applied) > 30:
            out.append(f"- ... and {len(report.transformations_applied) - 30} more")

    return "\n".join(out)


def main() -> int:
    p = argparse.ArgumentParser(description="English AI-tell remover + 5-axis scorer (sibling of humanize_v2.py)")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--input", "-i", help="Read text from this file")
    src.add_argument("--text", "-t", help="Read text directly from argument")
    p.add_argument("--mode", choices=["analyze", "lex", "both"], default="both",
                   help="analyze=flag only · lex=transform · both=transform+score before/after")
    p.add_argument("--output", "-o", help="Write transformed text to this file (mode=lex or both)")
    p.add_argument("--report", action="store_true", help="Print human-readable report to stdout")
    p.add_argument("--json", action="store_true", help="Emit JSON report to stdout")
    p.add_argument("--force-language", choices=["en", "ar"], help="Bypass language detection")

    args = p.parse_args()

    if args.input:
        text = Path(args.input).read_text(encoding="utf-8")
    else:
        text = args.text

    lang = args.force_language or detect_language(text)
    if lang == "ar":
        print("ERROR: Input looks Arabic. Use scripts/humanize_v2.py instead (this script is English-only).", file=sys.stderr)
        return 2

    transformed, report, score_after = run(text, args.mode)

    if args.output and args.mode != "analyze":
        Path(args.output).write_text(transformed, encoding="utf-8")

    if args.json:
        payload = {
            "language": report.language,
            "mode": args.mode,
            "sentence_count": report.sentence_count,
            "word_count": report.word_count,
            "score_before": report.score,
            "score_after": score_after,
            "findings_count": len(report.findings),
            "transformations_count": len(report.transformations_applied),
            "transformations_applied": report.transformations_applied,
            "findings": [
                {"layer": f.layer, "category": f.category, "action": f.action, "match": f.match, "position": f.position}
                for f in report.findings
            ],
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    elif args.report or not args.output:
        print(format_report(text, transformed, report, score_after, args.mode))

    return 0


if __name__ == "__main__":
    sys.exit(main())
