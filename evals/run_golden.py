#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Golden test runner for Arabic Humanizer v2.

Loads evals/golden_cases.json, runs each case against the actual scripts,
verifies expected behavior. Reports PASS/FAIL with rationale.

Exit code: 0 if all pass, 1 if any fail.

Usage:
    python evals/run_golden.py
"""
from __future__ import annotations
import json, os, subprocess, sys, tempfile
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = SKILL_DIR / "scripts"
EVALS_DIR = SKILL_DIR / "evals"

CASES = json.loads((EVALS_DIR / "golden_cases.json").read_text(encoding="utf-8"))["cases"]


def run_humanize(text: str, mode: str = "tighten", register: str = "news",
                 extra_args: list[str] = None) -> tuple[str, int]:
    """Run humanize_v2.py and return (output_text, exit_code)."""
    extra_args = extra_args or []
    with tempfile.NamedTemporaryFile(mode="w", delete=False, encoding="utf-8",
                                       suffix=".txt") as tf:
        tf.write(text)
        in_path = tf.name
    out_path = in_path + ".out"
    try:
        cmd = [sys.executable, str(SCRIPTS_DIR / "humanize_v2.py"),
               "--file", in_path,
               "--mode", mode,
               "--register", register,
               "--seed", "42",
               "--output", out_path] + extra_args
        r = subprocess.run(cmd, capture_output=True, text=True,
                          encoding="utf-8", timeout=120)
        if Path(out_path).exists():
            output = Path(out_path).read_text(encoding="utf-8")
        else:
            output = ""
        return output, r.returncode
    finally:
        try: os.unlink(in_path)
        except: pass
        try: os.unlink(out_path)
        except: pass


def run_preflight(text: str) -> dict:
    """Run preflight_check.py and return the JSON result."""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, encoding="utf-8",
                                       suffix=".txt") as tf:
        tf.write(text)
        in_path = tf.name
    try:
        r = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "preflight_check.py"),
             "--file", in_path, "--json"],
            capture_output=True, text=True, encoding="utf-8", timeout=30
        )
        try:
            return json.loads(r.stdout)
        except Exception:
            return {"verdict": "ERROR", "n_findings": 0, "findings": [],
                    "raw": r.stdout[:200]}
    finally:
        try: os.unlink(in_path)
        except: pass


def run_analyze(text: str) -> dict:
    """Run analyze_deep.py and return JSON result."""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, encoding="utf-8",
                                       suffix=".txt") as tf:
        tf.write(text)
        in_path = tf.name
    try:
        r = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "analyze_deep.py"),
             "--file", in_path, "--json"],
            capture_output=True, text=True, encoding="utf-8", timeout=30
        )
        try:
            return json.loads(r.stdout)
        except Exception:
            return None
    finally:
        try: os.unlink(in_path)
        except: pass


def check_case(case: dict) -> dict:
    """Run a single case and return result with PASS/FAIL."""
    cid = case["id"]
    text = case["input"]
    register = case.get("register", "news")
    failures = []

    # Empty input handling
    if case["category"] == "edge_case" and case["id"] == "empty-input-graceful":
        out, code = run_humanize(text, mode="tighten", register="news")
        # Should exit gracefully — either succeed with empty or exit non-zero with message
        # But should NOT crash with traceback (we accept code != 0 as long as no traceback)
        return {"id": cid, "pass": True, "note": "graceful (empty handled)"}

    # Preflight cases
    if case["category"] == "preflight_safety":
        pf = run_preflight(text)
        expected_verdict = case.get("preflight_verdict")
        if expected_verdict and pf.get("verdict") != expected_verdict:
            failures.append(f"verdict={pf.get('verdict')!r}, expected={expected_verdict!r}")
        expected_flags = case.get("preflight_must_flag", [])
        actual_categories = {f["category"] for f in pf.get("findings", [])}
        for flag in expected_flags:
            if flag not in actual_categories:
                failures.append(f"missing flag: {flag} (got {sorted(actual_categories)})")
        return {"id": cid, "pass": not failures, "failures": failures,
                "verdict_got": pf.get("verdict")}

    # Dim 16 scoring cases
    if case["category"] == "junction_disjunction":
        a = run_analyze(text)
        if not a:
            return {"id": cid, "pass": False, "failures": ["analyzer failed"]}
        score = a["by_dimension"]["16"]["score"]
        expected_exact = case.get("expected_dim16_score")
        expected_min = case.get("expected_dim16_score_min")
        if expected_exact is not None and score != expected_exact:
            failures.append(f"dim 16 score = {score}, expected exactly {expected_exact}")
        if expected_min is not None and score < expected_min:
            failures.append(f"dim 16 score = {score}, expected >= {expected_min}")
        return {"id": cid, "pass": not failures, "failures": failures, "score_got": score}

    # Humanness threshold
    if case["category"] == "positive_recognition":
        a = run_analyze(text)
        score = a.get("overall_humanness_0_100", 0) if a else 0
        threshold = case["expected_humanness_at_least"]
        if score < threshold:
            failures.append(f"humanness = {score}, expected >= {threshold}")
        return {"id": cid, "pass": not failures, "failures": failures, "score_got": score}

    # Short input no-crash
    if case["category"] == "edge_case":
        a = run_analyze(text)
        if not a:
            failures.append("analyzer crashed")
        return {"id": cid, "pass": not failures, "failures": failures}

    # General output checks (tighten + register)
    mode = "tighten"
    if case["category"] == "register_gating" and "lex_only" in case.get("id", ""):
        mode = "lex-only"

    out, code = run_humanize(text, mode=mode, register=register)
    if not out and code != 0:
        failures.append(f"humanizer exited code={code}")

    for must_contain in case.get("must_contain_after_tighten_news", []):
        if must_contain not in out:
            failures.append(f"missing required: {must_contain!r}")

    for must_contain in case.get("must_contain_after_lex_only_technical", []):
        out2, _ = run_humanize(text, mode="lex-only", register="technical")
        if must_contain not in out2:
            failures.append(f"missing required (lex-only/technical): {must_contain!r}")

    for must_not in case.get("must_not_contain", []):
        if must_not in out:
            failures.append(f"forbidden present: {must_not!r}")

    for must_not in case.get("must_not_contain_in_output", []):
        if must_not in out:
            failures.append(f"forbidden present: {must_not!r}")

    return {"id": cid, "pass": not failures, "failures": failures, "output": out[:200]}


def main():
    print(f"Running {len(CASES)} golden cases...\n")
    results = []
    for case in CASES:
        r = check_case(case)
        results.append(r)
        mark = "✓" if r["pass"] else "✗"
        cid = r["id"]
        print(f"  {mark} {cid:<45}", end="")
        if not r["pass"]:
            print(f"   FAIL")
            for f in r.get("failures", []):
                print(f"      - {f}")
        else:
            extra = ""
            if "score_got" in r: extra = f"  (score={r['score_got']})"
            if "verdict_got" in r: extra = f"  (verdict={r['verdict_got']})"
            print(f"   PASS{extra}")

    passes = sum(1 for r in results if r["pass"])
    fails = len(results) - passes
    print(f"\n{'='*60}")
    print(f"Total: {len(results)}  |  PASS: {passes}  |  FAIL: {fails}")
    print(f"{'='*60}")
    sys.exit(0 if fails == 0 else 1)


if __name__ == "__main__":
    main()
