#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_input_validation_contract.py — v2.17.0 input-validation guard contract.

The v2.17.0 guards in humanize_v2.score_text() validate the input BEFORE any
LLM / vendor round-trip, so this suite is fully deterministic and makes NO
network calls. It exercises _validate_input_text via the public score_text API:

  1. score_text(None)         -> {ok:False, input_validation.error_class == "null_input"}
  2. score_text(12345)        -> {ok:False, input_validation.error_class == "wrong_type"}
  3. score_text("x"*250000)   -> {ok:False, input_validation.error_class == "input_too_long"}
     (250000 > MAX_INPUT_CHARS_HEURISTIC == 200_000)
  4. score_text(<valid short arabic string>) -> success-shaped result
     (int score, no ok:False, no input_validation failure envelope)

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

from humanize_v2 import score_text, MAX_INPUT_CHARS_HEURISTIC

PASS = "[PASS]"
FAIL = "[FAIL]"

failures = []


def check(cond, msg):
    if cond:
        print(f"{PASS} {msg}")
    else:
        print(f"{FAIL} {msg}")
        failures.append(msg)


# --- Case 1: None input -> null_input -------------------------------------
r_none = score_text(None)
assert isinstance(r_none, dict), "None case must return a dict envelope"
check(r_none.get("ok") is False, "score_text(None) -> ok is False")
iv_none = r_none.get("input_validation", {})
check(iv_none.get("error_class") == "null_input",
      "score_text(None) -> input_validation.error_class == 'null_input'")

# --- Case 2: wrong type (int) -> wrong_type --------------------------------
r_int = score_text(12345)
assert isinstance(r_int, dict), "int case must return a dict envelope"
check(r_int.get("ok") is False, "score_text(12345) -> ok is False")
iv_int = r_int.get("input_validation", {})
check(iv_int.get("error_class") == "wrong_type",
      "score_text(12345) -> input_validation.error_class == 'wrong_type'")

# --- Case 3: pathologically long string -> input_too_long ------------------
long_text = "x" * 250000
assert len(long_text) > MAX_INPUT_CHARS_HEURISTIC, "fixture must exceed heuristic cap"
r_long = score_text(long_text)
assert isinstance(r_long, dict), "long case must return a dict envelope"
check(r_long.get("ok") is False, "score_text('x'*250000) -> ok is False")
iv_long = r_long.get("input_validation", {})
check(iv_long.get("error_class") == "input_too_long",
      "score_text('x'*250000) -> input_validation.error_class == 'input_too_long'")

# --- Case 4: valid short arabic string -> success-shaped -------------------
# Plain local heuristic scoring; no network. Short, clean text.
valid_text = "هذا نص عربي قصير وبسيط للاختبار."
r_ok = score_text(valid_text)
assert isinstance(r_ok, dict), "valid case must return a dict result"
check(r_ok.get("ok") is not False,
      "score_text(valid) -> not a failure envelope (ok is not False)")
check("input_validation" not in r_ok,
      "score_text(valid) -> no input_validation failure envelope present")
check(isinstance(r_ok.get("score"), int),
      "score_text(valid) -> 'score' is an int")

# --- Summary ---------------------------------------------------------------
total = 11
print(f"\n{len(failures)} failure(s) of {total} checks "
      f"in test_input_validation_contract.py")
if failures:
    sys.exit(1)
print("ALL PASS: v2.17.0 input-validation guards are deterministic (no LLM).")
sys.exit(0)
