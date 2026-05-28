#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sacred_text_guard.py — detect Quranic verses + hadith citations and return
locked spans that downstream transformation passes MUST preserve verbatim.

Per multi-agent linguistic review (Agent A, v2.6.0): the humanizer
previously had no protection for sacred-text content. Running the
cognitive pass or quote-verb rotation on a hadith citation
(`قال رسول الله ﷺ`) producing `أكد رسول الله` is theologically wrong
and editorially catastrophic for any religious-publication deployment.

This module provides:

  detect_locked_spans(text) -> List[Tuple[start, end, reason]]

Callers (humanize_v2.py, humanize_english.py if applied) should subtract
these spans from the transformation surface or chunk-and-restore them
(same pattern as code-block protection in humanize_english.py T3).

Heuristics (high-precision, low-recall is intentional — we'd rather miss
some sacred content than produce false positives that lock legitimate prose):

1. **Quranic-verse marks** (U+06D6 - U+06ED, U+06DD): if 3+ such marks
   appear in a 200-char window, lock the surrounding paragraph.
2. **Hadith attribution chains**: regex match on:
   - `قال رسول الله ﷺ`
   - `قال رسول الله صلى الله عليه وسلم`
   - `قال النبي ﷺ`
   - `روى البخاري عن` / `روى مسلم عن` / `روى الترمذي`
   - `حدثنا X عن Y عن Z`
3. **Quranic citation framing**:
   - `قال تعالى:` (followed by either ASCII quotes or Arabic guillemets)
   - `قال الله تعالى:`
   - `في قوله تعالى`
4. **Basmala**: `بسم الله الرحمن الرحيم` (full or partial).

Locked span extends to the end of the quoted/cited passage (closing
guillemet `»`, ASCII close-quote `"`, or end of sentence terminated
by `۔ .` if no quote frame is present).

Conservative by design — when in doubt, lock more rather than less.

Python 3 stdlib only.
"""
from __future__ import annotations

import re
import sys
from typing import List, Tuple

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


# Unicode ranges:
#  U+06D6 .. U+06DC: Quranic small high marks (sajda, etc.)
#  U+06DD: Quranic end-of-ayah marker (followed by digit ayah number)
#  U+06DE .. U+06E4, U+06E7 .. U+06E8, U+06EA .. U+06ED: various tajweed marks
QURANIC_MARK_RE = re.compile(r"[ۖ-ۭ]")

# Hadith attribution patterns. ﷺ is U+FDFA (Arabic ligature sallallahou alayhe wasallam).
HADITH_FRAMES = [
    r"قال\s+رسول\s+الله\s*ﷺ",
    r"قال\s+رسول\s+الله\s+صلى\s+الله\s+عليه\s+وسلم",
    r"قال\s+النبي\s*ﷺ",
    r"قال\s+النبي\s+صلى\s+الله\s+عليه\s+وسلم",
    r"عن\s+النبي\s*ﷺ",
    r"عن\s+النبي\s+صلى\s+الله\s+عليه\s+وسلم",
    r"روى\s+(البخاري|مسلم|الترمذي|أبو\s+داود|النسائي|ابن\s+ماجه|أحمد)\s+عن",
    r"حدثنا\s+\S+\s+عن\s+\S+\s+عن",
    r"أخرجه\s+(البخاري|مسلم|الترمذي|أبو\s+داود|النسائي|ابن\s+ماجه|أحمد)",
]
HADITH_RE = re.compile("|".join(HADITH_FRAMES))

# Quranic citation framing.
QURAN_FRAMES = [
    r"قال\s+تعالى\s*[:؛]?",
    r"قال\s+الله\s+تعالى\s*[:؛]?",
    r"يقول\s+تعالى\s*[:؛]?",
    r"في\s+قوله\s+تعالى",
    r"كما\s+قال\s+تعالى",
]
QURAN_FRAME_RE = re.compile("|".join(QURAN_FRAMES))

# Basmala.
BASMALA_RE = re.compile(r"بسم\s+الله\s+الرحمن\s+الرحيم")

# Span end markers — Arabic guillemets, ASCII quotes, end-of-sentence Arabic punct.
SPAN_END_PATTERNS = [
    r"»",
    r'"',
    r"”",
    r"›",
    r"۔",  # Urdu / Arabic full stop variant
    r"\.\s",
    r"\.$",
    r"؟",
    r"!",
]
SPAN_END_RE = re.compile("|".join(SPAN_END_PATTERNS))


def _find_span_end(text: str, start: int, max_window: int = 400) -> int:
    """
    Given a citation-frame start position, find the end of the quoted/cited
    passage. Look ahead up to max_window chars for a close-quote / sentence
    terminator. Fall back to start + max_window if nothing found.
    """
    window = text[start:start + max_window]
    m = SPAN_END_RE.search(window)
    if m:
        return start + m.end()
    return min(start + max_window, len(text))


def _quranic_mark_clusters(text: str, window_size: int = 200,
                           min_marks: int = 3) -> List[Tuple[int, int]]:
    """
    Find regions where Quranic tajweed marks cluster (≥min_marks in window_size chars).
    Returns merged (start, end) spans covering those regions.
    """
    positions = [m.start() for m in QURANIC_MARK_RE.finditer(text)]
    if len(positions) < min_marks:
        return []
    spans: List[Tuple[int, int]] = []
    i = 0
    while i < len(positions) - (min_marks - 1):
        first = positions[i]
        last_in_window = positions[i + min_marks - 1]
        if last_in_window - first <= window_size:
            # Extend right: as long as more marks fall within window_size of the last.
            j = i + min_marks - 1
            while j + 1 < len(positions) and positions[j + 1] - positions[j] <= window_size:
                j += 1
            # Snap to surrounding paragraph (find blank line before first / after last).
            para_start = text.rfind("\n\n", 0, first)
            para_start = 0 if para_start == -1 else para_start + 2
            para_end = text.find("\n\n", positions[j])
            para_end = len(text) if para_end == -1 else para_end
            spans.append((para_start, para_end))
            i = j + 1
        else:
            i += 1
    return _merge_spans(spans)


def _merge_spans(spans: List[Tuple[int, int]]) -> List[Tuple[int, int]]:
    """Merge overlapping (start, end) spans."""
    if not spans:
        return []
    spans = sorted(spans)
    merged = [spans[0]]
    for start, end in spans[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    return merged


def detect_locked_spans(text: str) -> List[Tuple[int, int, str]]:
    """
    Public API. Return a list of (start, end, reason) spans that downstream
    transformation passes MUST NOT modify.
    """
    spans: List[Tuple[int, int, str]] = []

    # 1. Hadith attribution chains.
    for m in HADITH_RE.finditer(text):
        end = _find_span_end(text, m.end())
        spans.append((m.start(), end, "hadith citation"))

    # 2. Quranic citation framing.
    for m in QURAN_FRAME_RE.finditer(text):
        end = _find_span_end(text, m.end())
        spans.append((m.start(), end, "Quranic citation framing"))

    # 3. Basmala.
    for m in BASMALA_RE.finditer(text):
        # Basmala is short — lock just the phrase plus any following sentence.
        end = _find_span_end(text, m.end(), max_window=80)
        spans.append((m.start(), end, "basmala"))

    # 4. Quranic-mark clusters (high tajweed-mark density).
    for start, end in _quranic_mark_clusters(text):
        spans.append((start, end, "Quranic verse cluster (tajweed marks)"))

    # Merge overlapping spans, preserving reasons.
    if not spans:
        return []
    spans.sort()
    merged: List[Tuple[int, int, str]] = []
    for start, end, reason in spans:
        if merged and start <= merged[-1][1]:
            ls, le, lr = merged[-1]
            new_reason = lr if reason in lr else lr + "; " + reason
            merged[-1] = (ls, max(le, end), new_reason)
        else:
            merged.append((start, end, reason))
    return merged


def mask_sacred_spans(text: str) -> Tuple[str, List[Tuple[int, int, str, str]]]:
    """
    Return (masked_text, list_of_(orig_start, orig_end, reason, original_text)).
    Sentinel format mirrors humanize_english.py's code-block sentinel.
    """
    spans = detect_locked_spans(text)
    if not spans:
        return text, []
    sentinel = "\x00SACRED_{i}\x00"
    out_parts: List[str] = []
    masks: List[Tuple[int, int, str, str]] = []
    cursor = 0
    for i, (start, end, reason) in enumerate(spans):
        out_parts.append(text[cursor:start])
        out_parts.append(sentinel.format(i=i))
        masks.append((start, end, reason, text[start:end]))
        cursor = end
    out_parts.append(text[cursor:])
    return "".join(out_parts), masks


def restore_sacred_spans(masked: str, masks: List[Tuple[int, int, str, str]]) -> str:
    """Inverse of mask_sacred_spans."""
    out = masked
    for i, (_, _, _, original) in enumerate(masks):
        out = out.replace(f"\x00SACRED_{i}\x00", original)
    return out


def cli_main() -> int:
    import argparse
    p = argparse.ArgumentParser(description="Detect sacred-text spans in Arabic text")
    p.add_argument("--text", "-t", help="Text to scan")
    p.add_argument("--input", "-i", help="File to scan")
    p.add_argument("--json", action="store_true", help="JSON output")
    args = p.parse_args()
    if args.input:
        text = open(args.input, encoding="utf-8").read()
    elif args.text:
        text = args.text
    else:
        p.error("--text or --input required")
        return 2
    spans = detect_locked_spans(text)
    if args.json:
        import json
        print(json.dumps(
            [{"start": s, "end": e, "reason": r, "preview": text[s:min(e, s+80)]}
             for s, e, r in spans],
            indent=2, ensure_ascii=False,
        ))
    else:
        print(f"Detected {len(spans)} locked span(s):\n")
        for s, e, r in spans:
            preview = text[s:min(e, s+80)].replace("\n", " ")
            print(f"  [{s}:{e}] ({r}) {preview!r}")
    return 0


if __name__ == "__main__":
    sys.exit(cli_main())
