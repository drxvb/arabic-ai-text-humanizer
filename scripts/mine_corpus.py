#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stream-process a JSONL Arabic corpus for empirical patterns.

Input format: one JSON record per line with {"text": "...", "metadata":
{"category": "..."}} fields. Use any classical-Arabic-leaning JSONL.

Default sample: 100,000 records (≈87 seconds for the reference corpus,
producing ≈1.31M sentences, ≈71.3M tokens across the categories the
input declares).

Computes per-category aggregates: sentence-length distribution, connector
frequency, sentence-initial token distribution, character-level statistics.

Output: corpus/empirical-patterns.json (relative to this skill's root).
"""
from __future__ import annotations
import argparse, json, re, sys, time
from collections import Counter, defaultdict
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# Arabic sentence terminators
SENT_END = re.compile(r'[.!?؟…]+\s+')
# Arabic punctuation for tokenization
PUNCT = re.compile(r'[،؛؟٪٬٫!?,.;:()\[\]{}\'"<>«»\-—–_…]')
# Arabic letter range
AR_LETTER = re.compile(r'[؀-ۿ]')
# Common connector candidates to track frequency
CONNECTORS = [
    "و", "ف", "ثم", "أو", "لكن", "بل", "غير أن", "بيد أن", "إذ", "إذا", "إذن",
    "حتى", "كما", "كذلك", "أيضاً", "أيضا", "مع ذلك", "مع أن", "علاوة على ذلك",
    "بالإضافة إلى ذلك", "من ناحية أخرى", "في المقابل", "بالمقابل",
    "وعلى الرغم من", "رغم أن", "على أن", "لذلك", "لذا", "وبالتالي",
    "ولا غرو", "وقد", "قد", "إن", "أن", "بأن",
    "من جهة", "من جهة أخرى", "أولاً", "ثانياً", "ثالثاً", "أخيراً",
    "في البداية", "في النهاية", "في الختام",
    "على سبيل المثال", "مثلاً", "كمثال", "نحو", "كقولنا",
    "لأن", "بسبب", "نظراً ل", "بناءً على",
    "إلى جانب", "فضلاً عن", "ناهيك عن",
    "خلاصة القول", "وفي النهاية", "وفي الختام",
    "وذلك", "حيث", "بحيث", "كأن", "كأنما",
    "ولعل", "ربما", "قد يكون", "يبدو أن",
]
# Sort by length DESC so longer patterns match first
CONNECTORS_SORTED = sorted(CONNECTORS, key=lambda x: -len(x))


def normalize_ar(s: str) -> str:
    """Strip tatweel, diacritics, normalize hamza/ya."""
    s = re.sub(r'ـ+', '', s)
    s = re.sub(r'[ً-ٰٟ]', '', s)  # diacritics
    s = s.translate(str.maketrans("أإآ", "ااا")).replace("ى", "ي")
    return s


def split_sentences(text: str) -> list[str]:
    parts = SENT_END.split(text)
    return [p.strip() for p in parts if p.strip()]


def tokenize(text: str) -> list[str]:
    text = PUNCT.sub(' ', text)
    return [t for t in text.split() if len(t) >= 1]


def count_connectors(sentence: str) -> dict:
    """Count connector occurrences in a sentence (longer-first match)."""
    out = Counter()
    s_norm = " " + sentence + " "
    for c in CONNECTORS_SORTED:
        c_norm = " " + c + " "
        n = s_norm.count(c_norm)
        if n: out[c] += n
    return out


def main():
    import os as _os
    ap = argparse.ArgumentParser()
    # Default input: ARABIC_CORPUS_PATH env var if set, else "./corpus.jsonl"
    # in the current working directory. The CLI flag overrides both. The skill
    # ships with corpus/empirical-patterns.json already computed, so most users
    # won't need to run this script.
    default_input = _os.environ.get("ARABIC_CORPUS_PATH", "./corpus.jsonl")
    # Default output: write to corpus/empirical-patterns.json relative to this
    # script's parent skill directory — portable across installs.
    default_out = Path(__file__).resolve().parent.parent / "corpus" / "empirical-patterns.json"
    ap.add_argument("--input", type=Path, default=Path(default_input),
                    help=("Path to a JSONL with {text, metadata.category} "
                          "records. Defaults to $ARABIC_CORPUS_PATH or "
                          "./corpus.jsonl. The skill ships with a pre-mined "
                          "corpus/empirical-patterns.json — this script is "
                          "rarely needed for end users."))
    ap.add_argument("--sample", type=int, default=100000,
                    help="Max records to sample (default 100K). Use 0 for full file.")
    ap.add_argument("--out", type=Path, default=default_out,
                    help="Output path for empirical-patterns.json.")
    args = ap.parse_args()

    if not args.input.exists():
        raise SystemExit(f"Corpus not found: {args.input}")

    print(f"[mine] streaming {args.input} (sample={args.sample or 'full'})", flush=True)
    start = time.time()

    # Per-category aggregates
    cat_stats = defaultdict(lambda: {
        "n_records": 0,
        "n_sentences": 0,
        "n_tokens": 0,
        "sentence_lengths": [],
        "connector_counts": Counter(),
        "sent_initial_tokens": Counter(),
        "tashkeel_ratio_sum": 0.0,
        "tashkeel_ratio_n": 0,
    })
    overall = {"n_records": 0, "n_skipped": 0}

    with args.input.open("rb") as f:
        for line_no, raw in enumerate(f, 1):
            if args.sample and overall["n_records"] >= args.sample:
                break
            try:
                obj = json.loads(raw.decode("utf-8", errors="replace"))
            except Exception:
                overall["n_skipped"] += 1
                continue
            text = obj.get("text", "")
            if not isinstance(text, str) or not text.strip():
                overall["n_skipped"] += 1
                continue
            md = obj.get("metadata") or {}
            cat = md.get("category") or "unknown"

            sentences = split_sentences(text)
            tokens = tokenize(text)

            stats = cat_stats[cat]
            stats["n_records"] += 1
            stats["n_sentences"] += len(sentences)
            stats["n_tokens"] += len(tokens)
            for s in sentences[:50]:  # cap per record
                sl = len(s.split())
                if sl >= 2: stats["sentence_lengths"].append(sl)
                stats["connector_counts"].update(count_connectors(s))
                first = s.split()[0] if s.split() else ""
                first_norm = normalize_ar(first)
                if first_norm and AR_LETTER.search(first_norm):
                    stats["sent_initial_tokens"][first_norm] += 1

            # Tashkeel ratio (diacritics / arabic letters)
            ar_letters = len(AR_LETTER.findall(text))
            diacs = len(re.findall(r'[ً-ٟ]', text))
            if ar_letters > 100:
                stats["tashkeel_ratio_sum"] += diacs / ar_letters
                stats["tashkeel_ratio_n"] += 1

            overall["n_records"] += 1
            if overall["n_records"] % 10000 == 0:
                elapsed = int(time.time() - start)
                print(f"  [{overall['n_records']:>7}] {elapsed}s — cats={len(cat_stats)}", flush=True)

    # Summarize
    print(f"\n[mine] summarizing {overall['n_records']} records across {len(cat_stats)} categories", flush=True)
    summary = {
        "input": str(args.input),
        "sample_size": overall["n_records"],
        "skipped": overall["n_skipped"],
        "elapsed_s": round(time.time() - start, 1),
        "categories": {},
        "global_top_connectors": Counter(),
        "global_top_sent_initial": Counter(),
    }
    for cat, st in cat_stats.items():
        if not st["sentence_lengths"]: continue
        sls = st["sentence_lengths"]
        mean_sl = sum(sls) / len(sls)
        var = sum((l - mean_sl) ** 2 for l in sls) / len(sls)
        stddev = var ** 0.5
        burstiness = stddev / mean_sl if mean_sl else 0
        # Histogram bins
        bins = {"1-5": 0, "6-10": 0, "11-15": 0, "16-20": 0, "21-30": 0, "31-50": 0, "51+": 0}
        for l in sls:
            if l <= 5: bins["1-5"] += 1
            elif l <= 10: bins["6-10"] += 1
            elif l <= 15: bins["11-15"] += 1
            elif l <= 20: bins["16-20"] += 1
            elif l <= 30: bins["21-30"] += 1
            elif l <= 50: bins["31-50"] += 1
            else: bins["51+"] += 1
        total = sum(bins.values()) or 1
        bins_pct = {k: round(v * 100 / total, 1) for k, v in bins.items()}

        summary["categories"][cat] = {
            "n_records": st["n_records"],
            "n_sentences": st["n_sentences"],
            "n_tokens": st["n_tokens"],
            "mean_sentence_length": round(mean_sl, 2),
            "stddev_sentence_length": round(stddev, 2),
            "burstiness": round(burstiness, 3),
            "sentence_length_histogram_pct": bins_pct,
            "top_connectors": st["connector_counts"].most_common(30),
            "top_sent_initial_tokens": st["sent_initial_tokens"].most_common(30),
            "mean_tashkeel_ratio": round(st["tashkeel_ratio_sum"] / max(1, st["tashkeel_ratio_n"]), 4),
        }
        summary["global_top_connectors"].update(st["connector_counts"])
        summary["global_top_sent_initial"].update(st["sent_initial_tokens"])

    summary["global_top_connectors"] = summary["global_top_connectors"].most_common(50)
    summary["global_top_sent_initial"] = summary["global_top_sent_initial"].most_common(50)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[mine] DONE — {args.out}", flush=True)
    print(f"[mine] categories: {list(summary['categories'].keys())}", flush=True)


if __name__ == "__main__":
    main()
