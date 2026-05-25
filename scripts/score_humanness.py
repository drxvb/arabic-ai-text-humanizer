#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Side-by-side 13-dimension before/after comparison + delta report.

Usage:
    python score_humanness.py --before original.txt --after humanized.txt
    python score_humanness.py --before original.txt --after humanized.txt --json
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).parent))
from analyze_deep import analyze, DIM_NAMES


def render(before: dict, after: dict) -> str:
    lines = []
    lines.append("=" * 80)
    lines.append("Humanness Comparison — Before vs. After")
    lines.append("=" * 80)
    lines.append(f"Before: {before['word_count']} words, "
                 f"{before['sentence_count']} sentences, "
                 f"burstiness {before['burstiness']}")
    lines.append(f"After:  {after['word_count']} words, "
                 f"{after['sentence_count']} sentences, "
                 f"burstiness {after['burstiness']}")
    lines.append("")
    lines.append(f"{'#':>3} {'Dimension':<48} {'Before':>6} {'After':>6} {'Δ':>5}")
    lines.append("-" * 80)
    for n in range(1, 17):
        bs = before["by_dimension"][n]["score"]
        as_ = after["by_dimension"][n]["score"]
        d = as_ - bs
        d_str = f"+{d}" if d > 0 else str(d)
        marker = "↑" if d > 0 else "↓" if d < 0 else " "
        lines.append(f"{n:>3} {DIM_NAMES[n]:<48} {bs:>4}/15 {as_:>4}/15 {d_str:>4}{marker}")
    lines.append("-" * 80)
    bt = before["total_points"]
    at = after["total_points"]
    bh = before["overall_humanness_0_100"]
    ah = after["overall_humanness_0_100"]
    lines.append(f"    {'TOTAL':<48} {bt:>4}/240 {at:>4}/240 {at-bt:+4}")
    lines.append(f"    {'HUMANNESS 0-100':<48} {bh:>6.1f} {ah:>6.1f} {ah-bh:+5.1f}")
    lines.append("")
    # Band
    def band(score):
        if score >= 91: return "indistinguishable"
        if score >= 71: return "excellent"
        if score >= 41: return "good"
        return "mediocre"
    lines.append(f"Before band: {band(bh)}")
    lines.append(f"After band:  {band(ah)}")
    if (band(bh) != band(ah)):
        lines.append(f"  → band promotion!")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--before", required=True, type=Path)
    ap.add_argument("--after", required=True, type=Path)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if not args.before.exists():
        raise SystemExit(f"not found: {args.before}")
    if not args.after.exists():
        raise SystemExit(f"not found: {args.after}")

    before = analyze(args.before.read_text(encoding="utf-8"))
    after = analyze(args.after.read_text(encoding="utf-8"))

    if args.json:
        print(json.dumps({"before": before, "after": after,
                          "delta_humanness": round(
                              after["overall_humanness_0_100"]
                              - before["overall_humanness_0_100"], 1)},
                         ensure_ascii=False, indent=2))
    else:
        print(render(before, after))


if __name__ == "__main__":
    main()
