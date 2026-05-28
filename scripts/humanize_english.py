#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
humanize_english.py — English AI-tell removal + 5-axis scoring.

Sibling of humanize_v2.py (which is Arabic-only). This script handles
English text using the catalogue at corpus/english-patterns.json, which
adapts hardikpandya/stop-slop (MIT) into a machine-readable form plus
the 5-axis scoring rubric (Directness / Rhythm / Trust / Authenticity /
Density, max 50, revise below 35).

Three operating modes:
  --mode analyze     — flag patterns + emit 5-axis score; do NOT transform
  --mode lex         — apply safe deletions + substitutions; flag unsafe ones
  --mode both        — flag + transform + score before AND after (default)

v2.5.1 hotfix (over v2.5.0) — fixes 5 critical bugs found by multi-agent review:
  T1  skip_when_context now compares input ±N-word window to skip phrases
      (was comparing pattern to skip list — globally suppressed deletion).
  T2  --force-language en still refuses Arabic input (sanity check on top
      of the flag).
  T3  Markdown code-block protection: fenced ```...``` and inline `code`
      are extracted before transformation and restored verbatim afterward.
  T7  Findings de-duplicated by (start, end) span before scoring so a
      single match in two catalogue categories doesn't double-penalize.
  T8  Case-preserving substitution: "Navigate" -> "Handle" (Title case
      preserved); "NAVIGATE" -> "HANDLE"; "navigate" -> "handle".
  T6  --seed flag added (script is already deterministic; flag is
      reserved for future stochastic ops and resolves the doc/code drift).

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
import json
import random
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

# Sentinel used internally to mask code blocks before transformation.
# Chosen so the sentinel itself can never be a catalogue match.
_CODE_BLOCK_SENTINEL = "\x00STOPSLOP_CODEBLOCK_{i}\x00"


# ---------------------------------------------------------------------------
# Language detection
# ---------------------------------------------------------------------------

def detect_language(text: str) -> str:
    """Return 'ar' if Arabic chars dominate, 'en' for ASCII letters, else 'unknown'."""
    if not text:
        return "unknown"
    arabic = sum(1 for ch in text if "؀" <= ch <= "ۿ" or "ݐ" <= ch <= "ݿ")
    latin = sum(1 for ch in text if ch.isascii() and ch.isalpha())
    if arabic > latin:
        return "ar"
    if latin > arabic:
        return "en"
    return "unknown"


# ---------------------------------------------------------------------------
# Code-block protection (T3 fix)
# ---------------------------------------------------------------------------

_FENCED_BLOCK_RE = re.compile(r"```[\s\S]*?```", re.MULTILINE)
_INLINE_CODE_RE = re.compile(r"`[^`\n]+`")


def _extract_code_blocks(text: str) -> Tuple[str, List[str]]:
    """
    Replace fenced ```...``` and inline `code` with sentinels.
    Returns (masked_text, list_of_originals_in_order).
    Fenced first (so they're matched before inline backticks inside them
    can be picked up).
    """
    blocks: List[str] = []

    def take(match):
        blocks.append(match.group(0))
        return _CODE_BLOCK_SENTINEL.format(i=len(blocks) - 1)

    masked = _FENCED_BLOCK_RE.sub(take, text)
    masked = _INLINE_CODE_RE.sub(take, masked)
    return masked, blocks


def _restore_code_blocks(masked: str, blocks: List[str]) -> str:
    """Inverse of _extract_code_blocks."""
    out = masked
    for i, original in enumerate(blocks):
        out = out.replace(_CODE_BLOCK_SENTINEL.format(i=i), original)
    return out


# ---------------------------------------------------------------------------
# Case preservation (T8 fix)
# ---------------------------------------------------------------------------

def _preserve_case(matched: str, replacement: str) -> str:
    """
    Return `replacement` cased like `matched`.
    - matched all UPPER -> replacement UPPER
    - matched Title Case (first letter upper) -> replacement Title Case
    - otherwise -> replacement as-is (assumed lowercase in catalogue)
    """
    if not matched or not replacement:
        return replacement
    if matched.isupper():
        return replacement.upper()
    if matched[0].isupper() and (len(matched) == 1 or matched[1:].islower()):
        # Title Case for single-word matched; for multi-word phrases we
        # only title-case the first letter.
        return replacement[0].upper() + replacement[1:]
    return replacement


def _case_preserving_sub(pattern: str, replacement: str, text: str, flags=re.IGNORECASE) -> str:
    """re.sub that preserves the matched span's casing in the replacement."""
    def _repl(m: re.Match) -> str:
        return _preserve_case(m.group(0), replacement)
    return re.sub(pattern, _repl, text, flags=flags)


# ---------------------------------------------------------------------------
# Skip-context check (T1 fix)
# ---------------------------------------------------------------------------

def _should_skip_filler(text: str, span_start: int, span_end: int,
                        skip_phrases: List[str], window_words: int = 2) -> bool:
    """
    True if the input text around [span_start:span_end] matches any
    `skip_phrases` entry (looking at a ±window_words context).
    """
    if not skip_phrases:
        return False
    # Expand window by tokenizing on whitespace; cheap and good enough for English.
    left_tail = text[:span_start]
    right_tail = text[span_end:]
    left_words = re.findall(r"\S+", left_tail)[-window_words:]
    right_words = re.findall(r"\S+", right_tail)[:window_words]
    matched = text[span_start:span_end]
    context = " ".join(left_words + [matched] + right_words).lower()
    return any(skip.lower() in context for skip in skip_phrases)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class Finding:
    layer: str  # lexical | structural | sentence_level
    category: str
    action: str  # delete | substitute | flag
    match: str
    position: int
    span_end: int = 0  # T7: track span end for dedup


@dataclass
class Report:
    language: str
    sentence_count: int
    word_count: int
    findings: List[Finding] = field(default_factory=list)
    transformations_applied: List[str] = field(default_factory=list)
    transformations_skipped: List[str] = field(default_factory=list)
    score: Dict[str, int] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Pattern loading
# ---------------------------------------------------------------------------

def load_patterns() -> Dict[str, Any]:
    with PATTERNS_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# Tokenization
# ---------------------------------------------------------------------------

def split_sentences(text: str) -> List[str]:
    """Naive: split on ., !, ? followed by whitespace + capital letter."""
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z])", text.strip())
    return [p for p in parts if p.strip()]


def word_count(text: str) -> int:
    return len(re.findall(r"\b[A-Za-z][A-Za-z'-]*\b", text))


# ---------------------------------------------------------------------------
# Scanners
# ---------------------------------------------------------------------------

def scan_lexical(text: str, patterns: Dict[str, Any]) -> List[Finding]:
    findings: List[Finding] = []
    lex = patterns["lexical"]
    for category, spec in lex.items():
        action = spec["action"]
        if "patterns" in spec:
            for pat in spec["patterns"]:
                for m in re.finditer(re.escape(pat), text, flags=re.IGNORECASE):
                    findings.append(Finding("lexical", category, action, m.group(0), m.start(), m.end()))
        elif "substitutions" in spec:
            for needle in spec["substitutions"]:
                pat = r"\b" + re.escape(needle) + r"\b"
                for m in re.finditer(pat, text, flags=re.IGNORECASE):
                    findings.append(Finding("lexical", category, action, m.group(0), m.start(), m.end()))
    return findings


def scan_structural(text: str, patterns: Dict[str, Any]) -> List[Finding]:
    findings: List[Finding] = []
    struct = patterns["structural"]
    for category, spec in struct.items():
        action = spec.get("action", "flag")
        if "patterns" in spec:
            for pat in spec["patterns"]:
                for m in re.finditer(re.escape(pat), text, flags=re.IGNORECASE):
                    findings.append(Finding("structural", category, action, m.group(0), m.start(), m.end()))
        if "regex_patterns" in spec:
            for pat in spec["regex_patterns"]:
                try:
                    for m in re.finditer(pat, text, flags=re.IGNORECASE):
                        findings.append(Finding("structural", category, action, m.group(0), m.start(), m.end()))
                except re.error:
                    continue
    return findings


def scan_sentence_level(text: str, patterns: Dict[str, Any]) -> List[Finding]:
    findings: List[Finding] = []
    sl = patterns["sentence_level"]

    wh = sl.get("wh_starters", {})
    starter_words = wh.get("starter_words", [])
    if starter_words:
        # T12 partial: keep wh case-sensitive (capitalized sentence start) but
        # explicit comment so future maintainers know it's intentional.
        for m in re.finditer(r"(?:^|(?<=[.!?]\s))(" + "|".join(re.escape(w) for w in starter_words) + r")\b", text):
            findings.append(Finding("sentence_level", "wh_starters", wh["action"], m.group(0), m.start(), m.end()))

    pb = sl.get("paragraph_starter_blacklist", {})
    for word in pb.get("starter_words", []):
        for m in re.finditer(r"(?:^|\n)\s*" + re.escape(word), text, flags=re.IGNORECASE):
            findings.append(Finding("sentence_level", "paragraph_starter_blacklist", pb["action"], m.group(0).strip(), m.start(), m.end()))

    le = sl.get("lazy_extremes", {})
    for pat in le.get("patterns", []):
        for m in re.finditer(r"\b" + re.escape(pat) + r"\b", text, flags=re.IGNORECASE):
            findings.append(Finding("sentence_level", "lazy_extremes", le["action"], m.group(0), m.start(), m.end()))

    em = sl.get("em_dashes", {})
    for needle in em.get("substitutions", {}):
        for m in re.finditer(re.escape(needle), text):
            findings.append(Finding("sentence_level", "em_dashes", em["action"], m.group(0), m.start(), m.end()))

    return findings


# ---------------------------------------------------------------------------
# T7 fix: de-duplicate findings by (start, end) span
# ---------------------------------------------------------------------------

def _dedupe_findings(findings: List[Finding]) -> List[Finding]:
    """
    Collapse findings that share the SAME (start, end) span — they're the
    same literal text, just classified into multiple catalogue categories.
    Keep the highest-severity action (delete > substitute > flag).
    """
    action_rank = {"delete": 3, "substitute": 2, "flag": 1}
    by_span: Dict[Tuple[int, int], Finding] = {}
    for f in findings:
        key = (f.position, f.span_end)
        existing = by_span.get(key)
        if existing is None or action_rank.get(f.action, 0) > action_rank.get(existing.action, 0):
            by_span[key] = f
    return list(by_span.values())


# ---------------------------------------------------------------------------
# Transformation pipeline (with T1, T3, T8 fixes)
# ---------------------------------------------------------------------------

def transform(text: str, patterns: Dict[str, Any]) -> Tuple[str, List[str], List[str]]:
    """
    Apply safe deletions + substitutions; return (transformed, applied, skipped).
    Skipped entries surface to the user when skip_when_context bailed.
    """
    # T3: mask code blocks so we don't rewrite identifiers inside them.
    masked, code_blocks = _extract_code_blocks(text)
    out = masked
    applied: List[str] = []
    skipped: List[str] = []

    # 1. Delete throat-clearing, emphasis crutches, meta-commentary, filler phrases.
    for category in ("throat_clearing_openers", "emphasis_crutches", "meta_commentary", "filler_phrases"):
        spec = patterns["lexical"].get(category, {})
        if spec.get("action") != "delete":
            continue
        # Sort by length descending so longer patterns are matched first,
        # avoiding e.g. "Here's the thing:" being eaten as "Here's" + leftover.
        for pat in sorted(spec.get("patterns", []), key=len, reverse=True):
            new = re.sub(re.escape(pat) + r"\s*", "", out, flags=re.IGNORECASE)
            if new != out:
                applied.append(f"delete[{category}]: {pat!r}")
            out = new

    # 2. Substitute business jargon with case preservation (T8).
    jargon = patterns["lexical"].get("business_jargon", {})
    if jargon.get("action") == "substitute":
        # Sort by length descending so "double down" is matched before "double".
        items = sorted(jargon.get("substitutions", {}).items(), key=lambda x: -len(x[0]))
        for src, dst in items:
            pat = r"\b" + re.escape(src) + r"\b"
            before = out
            out = _case_preserving_sub(pat, dst, out)
            if out != before:
                applied.append(f"substitute[business_jargon]: {src!r} -> {dst!r}")

    # 3. Strip filler adverbs with CORRECT skip-context check (T1 fix).
    fillers = patterns["lexical"].get("filler_adverbs", {})
    if fillers.get("action") == "delete":
        skip_ctx = fillers.get("skip_when_context", [])
        for adv in fillers.get("patterns", []):
            pat = re.compile(r"\b" + re.escape(adv) + r"\b\s*", flags=re.IGNORECASE)
            new_parts: List[str] = []
            last = 0
            any_change = False
            for m in pat.finditer(out):
                start, end = m.start(), m.end()
                # End-of-adverb token (without trailing whitespace) for context check.
                token_end = start + len(adv)
                if _should_skip_filler(out, start, token_end, skip_ctx):
                    skipped.append(f"skip[filler_adverbs]: {adv!r} preserved (in skip_when_context)")
                    new_parts.append(out[last:end])
                else:
                    new_parts.append(out[last:start])
                    any_change = True
                last = end
            new_parts.append(out[last:])
            if any_change:
                applied.append(f"delete[filler_adverbs]: {adv!r}")
                out = "".join(new_parts)

    # 4. Em-dash substitution (sort by length descending — T14 fix-by-implementation).
    em = patterns["sentence_level"].get("em_dashes", {})
    if em.get("action") == "substitute":
        items = sorted(em.get("substitutions", {}).items(), key=lambda x: -len(x[0]))
        for src, dst in items:
            new = out.replace(src, dst)
            if new != out:
                applied.append(f"substitute[em_dashes]: {src!r} -> {dst!r}")
            out = new

    # Collapse leftover whitespace and punctuation artifacts from deletions.
    out = re.sub(r"  +", " ", out)
    out = re.sub(r",\s*,", ",", out)
    out = re.sub(r"\.\s*\.", ".", out)
    out = re.sub(r"^\s*[,;]\s*", "", out, flags=re.MULTILINE)  # leading punct after deletion
    out = out.strip()

    # T3: restore code blocks.
    out = _restore_code_blocks(out, code_blocks)
    return out, applied, skipped


# ---------------------------------------------------------------------------
# Scoring (with T7 dedup applied before counts)
# ---------------------------------------------------------------------------

def score_5_axis(text: str, patterns: Dict[str, Any]) -> Dict[str, int]:
    sentences = split_sentences(text)

    # Mask code blocks so they don't inflate findings.
    masked, _ = _extract_code_blocks(text)

    lex_findings = scan_lexical(masked, patterns)
    struct_findings = scan_structural(masked, patterns)
    sl_findings = scan_sentence_level(masked, patterns)

    # T7: dedup before counting.
    all_findings = _dedupe_findings(lex_findings + struct_findings + sl_findings)

    def count(layer: str, category: str) -> int:
        return sum(1 for f in all_findings if f.layer == layer and f.category == category)

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


# ---------------------------------------------------------------------------
# Top-level workflow
# ---------------------------------------------------------------------------

def analyze(text: str) -> Report:
    patterns = load_patterns()
    sents = split_sentences(text)
    masked, _ = _extract_code_blocks(text)
    findings: List[Finding] = []
    findings.extend(scan_lexical(masked, patterns))
    findings.extend(scan_structural(masked, patterns))
    findings.extend(scan_sentence_level(masked, patterns))
    findings = _dedupe_findings(findings)  # T7
    score = score_5_axis(text, patterns)
    return Report(
        language=detect_language(text),
        sentence_count=len(sents),
        word_count=word_count(text),
        findings=findings,
        score=score,
    )


def run(text: str, mode: str) -> Tuple[str, Report, Optional[Dict[str, int]]]:
    patterns = load_patterns()
    report = analyze(text)
    if mode == "analyze":
        return text, report, None
    transformed, ops, skipped = transform(text, patterns)
    report.transformations_applied = ops
    report.transformations_skipped = skipped
    if mode == "lex":
        return transformed, report, None
    score_after = score_5_axis(transformed, patterns)
    return transformed, report, score_after


# ---------------------------------------------------------------------------
# Formatter
# ---------------------------------------------------------------------------

def format_report(text_before: str, text_after: str, report: Report,
                  score_after: Optional[Dict[str, int]], mode: str) -> str:
    out = ["# English Humanizer Report\n"]
    out.append(f"**Language detected:** {report.language}")
    out.append(f"**Sentences:** {report.sentence_count} · **Words:** {report.word_count}")
    out.append(f"**Mode:** {mode}\n")

    out.append("## 5-Axis Score (max 50; revise below 35)\n")
    s = report.score
    out.append("| Axis | Score | Out of |")
    out.append("|---|---|---|")
    out.append(f"| Directness | {s['directness']} | 10 |")
    out.append(f"| Rhythm | {s['rhythm']} | 10 |")
    out.append(f"| Trust | {s['trust']} | 10 |")
    out.append(f"| Authenticity | {s['authenticity']} | 10 |")
    out.append(f"| Density | {s['density']} | 10 |")
    out.append(f"| **TOTAL** | **{s['total']}** | **50** |")
    out.append(f"\n**Verdict:** {s['verdict']}")

    if score_after:
        out.append("\n## After Transformation\n")
        out.append("| Axis | Before | After | Delta |")
        out.append("|---|---|---|---|")
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

    if report.transformations_skipped:
        out.append(f"\n## Transformations Skipped ({len(report.transformations_skipped)})\n")
        for op in report.transformations_skipped[:15]:
            out.append(f"- {op}")

    return "\n".join(out)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

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
    # T6 fix: --seed is a no-op today (no stochastic ops), reserved for future use.
    # Documented as deterministic so the flag's presence resolves doc/code drift.
    p.add_argument("--seed", type=int, default=None,
                   help="Random seed (currently no stochastic ops; reserved for future use)")

    args = p.parse_args()

    if args.seed is not None:
        random.seed(args.seed)

    if args.input:
        text = Path(args.input).read_text(encoding="utf-8")
    else:
        text = args.text

    detected = detect_language(text)
    # T2 fix: Arabic input refused, even with --force-language en. The user
    # almost certainly didn't mean to run the English pass on Arabic prose;
    # they probably typed --force-language en habitually.
    if detected == "ar":
        print(
            "ERROR: Input looks Arabic. Use scripts/humanize_v2.py instead (this script is English-only).\n"
            "       If you genuinely want to test English regexes against Arabic text, the script\n"
            "       still refuses because the English regexes (\\b[A-Za-z]+) match zero Arabic chars\n"
            "       and the run would silently no-op.",
            file=sys.stderr,
        )
        return 2

    lang = args.force_language or detected
    if lang == "ar":
        # Should be unreachable given the gate above; kept for safety.
        print("ERROR: Arabic routing path reached unexpectedly.", file=sys.stderr)
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
            "transformations_skipped": report.transformations_skipped,
            "findings": [
                {"layer": f.layer, "category": f.category, "action": f.action,
                 "match": f.match, "position": f.position, "span_end": f.span_end}
                for f in report.findings
            ],
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    elif args.report or not args.output:
        print(format_report(text, transformed, report, score_after, args.mode))

    return 0


if __name__ == "__main__":
    sys.exit(main())
