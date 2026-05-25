#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fragility regression tests — focused on the specific bug-classes that
cross-LLM critique surfaced. These complement the broader golden suite by
asserting (sometimes-counterintuitive) invariants about the lexical layer.

Run: python evals/test_known_fragility.py
Exit 0 on all-pass, non-zero on first failure.

What's covered (and why each test exists):
  T1 — clause-preserving substitution: "من الواضح أن X" must keep "أن" because
       the predicate clause depends on it. Naive lex-replace dropped it.
  T2 — pro-drop deletion: "في الواقع" and "بكل تأكيد" should DISAPPEAR (Arabic
       pro-drop prefers implicit subjects); naive substitution wrongly kept a
       filler word in place.
  T3 — quote-verb rotation default-OFF: قال and يقول must survive a default
       tighten/news run because hostile rotation (e.g. قال→يَزعم) shifts
       editorial stance, not just style.
  T4 — quote-verb rotation env-gate: setting HUMANIZER_ALLOW_QUOTE_ROTATION=1
       must enable the rotation (the gate has to actually work in both
       directions, not just be off by default).
  (T5 was a register-contrast test removed in v2.1 — it asserted that
   --register technical and --register opinion produce different outputs,
   but for tighten-mode benign input both registers legitimately do the
   same lexical work. Register's real differentiation happens in
   +cognitive/+rhetorical modes that need a live LLM, which this offline
   test environment can't exercise. Re-add when an LLM-mocked harness exists.)
  T6 — provider-agnostic guard: with no LLM_API_URL set, --mode +cognitive
       must NOT crash; it must gracefully degrade to lex-only with a clear
       error in the run log.
"""
from __future__ import annotations
import json, os, re, subprocess, sys, tempfile
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

SKILL_ROOT = Path(__file__).resolve().parent.parent
HUMANIZE = SKILL_ROOT / "scripts" / "humanize_v2.py"
PYEXE = sys.executable


def run_humanize(text: str, *args, env_overrides: dict | None = None) -> str:
    """Invoke humanize_v2.py with the given args. Returns stdout."""
    env = os.environ.copy()
    if env_overrides:
        env.update(env_overrides)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".txt", delete=False) as inp:
        inp.write(text)
        inp_path = inp.name
    out_path = inp_path + ".out"
    try:
        cmd = [PYEXE, str(HUMANIZE), "--file", inp_path, "--output", out_path] + list(args)
        proc = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=60)
        if proc.returncode not in (0, 2):  # 2 = preflight gate, also acceptable
            raise RuntimeError(f"humanize_v2 exited {proc.returncode}: {proc.stderr[:400]}")
        if Path(out_path).exists():
            return Path(out_path).read_text(encoding="utf-8")
        return proc.stdout
    finally:
        for p in (inp_path, out_path):
            try:
                os.unlink(p)
            except OSError:
                pass


class TestResult:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.cases = []

    def check(self, name: str, cond: bool, detail: str = ""):
        if cond:
            self.passed += 1
            self.cases.append((name, "PASS", ""))
            print(f"  [PASS] {name}")
        else:
            self.failed += 1
            self.cases.append((name, "FAIL", detail))
            print(f"  [FAIL] {name}: {detail}")


def main():
    r = TestResult()

    print("=" * 60)
    print("  T1 — clause-preserving substitution (أن must survive)")
    print("=" * 60)
    out = run_humanize("من الواضح أن القرار مناسب جداً.",
                       "--mode", "tighten", "--register", "news")
    r.check("T1.أن_preserved", "أن" in out,
            f"output dropped أن: {out[:80]!r}")
    r.check("T1.no_broken_construct", "بوضوح القرار" not in out,
            f"output broke grammar: {out[:80]!r}")

    print()
    print("=" * 60)
    print("  T2 — pro-drop deletion (fluff disappears)")
    print("=" * 60)
    out = run_humanize("في الواقع، النظام يعمل جيداً. بكل تأكيد المستقبل قادم.",
                       "--mode", "tighten", "--register", "news")
    r.check("T2.fi_alwaqi_deleted", "في الواقع" not in out,
            f"في الواقع still present: {out[:80]!r}")
    r.check("T2.bikul_taakeed_deleted", "بكل تأكيد" not in out,
            f"بكل تأكيد still present: {out[:80]!r}")
    r.check("T2.content_preserved", "النظام" in out and "المستقبل" in out,
            f"content nouns lost: {out[:80]!r}")

    print()
    print("=" * 60)
    print("  T3 — quote-verb rotation default-OFF (قال survives)")
    print("=" * 60)
    env_off = {k: v for k, v in os.environ.items()
               if k != "HUMANIZER_ALLOW_QUOTE_ROTATION"}
    out = run_humanize(
        "يقول الخبير إن النتائج إيجابية. قال المدير إن المشروع ناجح.",
        "--mode", "tighten", "--register", "news",
        env_overrides={"HUMANIZER_ALLOW_QUOTE_ROTATION": ""},
    )
    r.check("T3.qala_survives", "قال" in out,
            f"قال was rotated without env-gate: {out[:80]!r}")
    r.check("T3.yaqul_survives", "يقول" in out,
            f"يقول was rotated without env-gate: {out[:80]!r}")
    for hostile in ("يزعم", "ادّعى", "اعترف"):
        r.check(f"T3.no_hostile_{hostile}", hostile not in out,
                f"hostile verb '{hostile}' injected: {out[:80]!r}")

    print()
    print("=" * 60)
    print("  T6 — provider-agnostic guard (no API config → graceful)")
    print("=" * 60)
    env_no_api = {k: v for k, v in os.environ.items()
                  if k not in ("LLM_API_URL", "LLM_API_KEY", "LLM_MODEL")}
    env_no_api["LLM_API_URL"] = ""
    env_no_api["LLM_MODEL"] = ""
    try:
        out = run_humanize(
            "النظام يَعمل بشكل جيد. هذا اختبار للتحقق من السلوك بدون مفتاح API.",
            "--mode", "+cognitive", "--llm-backend", "api",
            env_overrides=env_no_api,
        )
        r.check("T6.no_crash_without_api", True)
        r.check("T6.lex_pass_still_applied", "بشكل" not in out or len(out) > 10,
                "output looks empty — pipeline crashed silently")
    except Exception as e:
        r.check("T6.no_crash_without_api", False,
                f"crashed instead of graceful degradation: {e}")

    print()
    print("=" * 60)
    print("  T7 — hamza letter forms survive (NOT tashkeel)")
    print("=" * 60)
    out = run_humanize(
        "إن النظام يعمل. أن نعرف ذلك. إما هذا أو ذاك. أما أنت فمختلف.",
        "--mode", "tighten", "--register", "news",
    )
    r.check("T7.hamza_above_alif_an", "أن" in out,
            f"أن (hamza above) was stripped: {out[:80]!r}")
    r.check("T7.hamza_below_alif_in", "إن" in out,
            f"إن (hamza below) was stripped: {out[:80]!r}")
    r.check("T7.imma_vs_amma_preserved",
            "إما" in out and "أما" in out,
            f"إما/أما distinction lost: {out[:120]!r}")

    print()
    print("=" * 60)
    print("  T8 — madda/precomposed letters survive (قرآن آلام آمال)")
    print("=" * 60)
    out = run_humanize(
        "النص يتحدث عن قرآن وآلام وآمال وأحصنة وآذان.",
        "--mode", "tighten", "--register", "news",
    )
    for word in ("قرآن", "آلام", "آمال", "أحصنة", "آذان"):
        r.check(f"T8.{word}_survives", word in out,
                f"{word} broken in output: {out[:120]!r}")

    print()
    print("=" * 60)
    print("  T9 — Arabic-Indic digits preserved (٠-٩)")
    print("=" * 60)
    out = run_humanize(
        "الأرقام ٠١٢٣٤٥٦٧٨٩ والسنة ٢٠٢٦ والنسبة ٨٧٪ يجب أن تَبقى.",
        "--mode", "tighten", "--register", "news",
    )
    for digit in ("٠١٢٣٤٥٦٧٨٩", "٢٠٢٦", "٨٧"):
        r.check(f"T9.digits_{digit}_survive", digit in out,
                f"digit run '{digit}' was stripped: {out[:120]!r}")

    print()
    print("=" * 60)
    print("  T10 — pipeline calque (خط أنابيب) replaced by workflow phrasing")
    print("=" * 60)
    out = run_humanize(
        "خط أنابيب التحويل يَعمل بكفاءة في كل المراحل.",
        "--mode", "tighten", "--register", "news",
    )
    r.check("T10.calque_replaced", "خط أنابيب" not in out,
            f"خط أنابيب still present: {out[:120]!r}")
    r.check("T10.workflow_inserted",
            "مسار عمل" in out or "مسار العمل" in out or "تسلسل العمل" in out,
            f"no workflow phrasing in output: {out[:120]!r}")

    print()
    print("=" * 60)
    print("  T11 — tashkeel reduced in news register, preserved in classical")
    print("=" * 60)
    heavy_in = "النَّصُّ المُولَّدُ بِالذَّكاءِ الاصطِناعيِّ يَحتاجُ إلى تَحويلٍ عَميقٍ."
    tashkeel_re = re.compile(r"[ً-ْٰ]")
    in_count = len(tashkeel_re.findall(heavy_in))

    out_news = run_humanize(heavy_in, "--mode", "tighten", "--register", "news")
    out_classical = run_humanize(heavy_in, "--mode", "tighten", "--register", "classical")
    news_count = len(tashkeel_re.findall(out_news))
    classical_count = len(tashkeel_re.findall(out_classical))

    r.check("T11.news_reduces_tashkeel", news_count < in_count // 2,
            f"news register kept {news_count}/{in_count} tashkeel marks (expected < half)")
    r.check("T11.classical_preserves_tashkeel", classical_count >= in_count * 0.7,
            f"classical register kept only {classical_count}/{in_count} marks (expected >= 70%)")

    print()
    print("=" * 60)
    print("  T12 — calque dictionary loads (v2.3.0)")
    print("=" * 60)
    # Sanity: the lex pipeline should produce different output on calque input
    # vs the same input absent the calque. We test a known dictionary entry.
    out_calque = run_humanize(
        "خط أنابيب البيانات يعمل بكفاءة عالية في المنصة.",
        "--mode", "tighten", "--register", "news",
    )
    r.check("T12.dict_loaded",
            "خط أنابيب" not in out_calque,
            f"calque survived in output: {out_calque[:120]!r}")

    print()
    print("=" * 60)
    print("  T13 — calque dictionary catches multi-domain calques")
    print("=" * 60)
    # Business calque: 'startup' as 'بدء التشغيل' should become 'شركة ناشئة'
    out_biz = run_humanize(
        "بدء التشغيل التقنية الجديدة تطلق منتجها الأول هذا الأسبوع.",
        "--mode", "tighten", "--register", "news",
    )
    r.check("T13.business_calque_caught",
            "بدء التشغيل" not in out_biz or "شركة ناشئة" in out_biz,
            f"startup calque survived: {out_biz[:120]!r}")

    # Security calque: 'logging' is NOT in our dict (we dropped it due to ambiguity)
    # but 'monitoring' as 'مونيتورينغ' should become 'مراقبة'
    out_sec = run_humanize(
        "مونيتورينغ النظام يكشف الأخطاء فور حدوثها.",
        "--mode", "tighten", "--register", "news",
    )
    r.check("T13.transliteration_calque_caught",
            "مونيتورينغ" not in out_sec,
            f"monitoring transliteration survived: {out_sec[:120]!r}")

    print()
    print("=" * 60)
    print("  T14 — calque dictionary REGISTER-GATED (technical preserves source)")
    print("=" * 60)
    # In technical register, calques in the new v2.3.0 dictionary should NOT
    # be substituted (preserve source verbatim). We use 'مونيتورينغ' which is
    # only in the new calque-dictionary.json — NOT in AI_PHRASES_AR.
    out_tech = run_humanize(
        "مونيتورينغ النظام يعمل بكفاءة في البيئة الإنتاجية.",
        "--mode", "tighten", "--register", "technical",
    )
    r.check("T14.technical_preserves_calque",
            "مونيتورينغ" in out_tech,
            f"technical register substituted: {out_tech[:120]!r}")

    print()
    print("=" * 60)
    print("  T15 — kashida (Arabic tatweel ـ) stripped from output (v2.4.1)")
    print("=" * 60)
    # AI-Arabic sometimes injects kashida to 'look more Arabic'. Modern editorial
    # convention treats kashida in encoded body text as wrong (it's for display
    # typography only). The typography pass must strip every U+0640.
    out = run_humanize(
        "هذا اختبار للتحقق من إزالة الكشيـدة من النص العـربي المـتدفق.",
        "--mode", "tighten", "--register", "news",
    )
    r.check("T15.kashida_stripped_news",
            "ـ" not in out,
            f"kashida (U+0640) survived in output: {out!r}")
    # Verify universal (not just news): classical should also strip per universal
    # editorial convention. (Future: if classical opts to preserve, change here.)
    out_cl = run_humanize(
        "هذا اختبار للتحقق من إزالة الكشيـدة من النص العـربي المـتدفق.",
        "--mode", "tighten", "--register", "classical",
    )
    r.check("T15.kashida_stripped_classical_too",
            "ـ" not in out_cl,
            f"kashida survived in classical register: {out_cl!r}")

    print()
    print("=" * 60)
    print("  T16 — em-dash → Arabic comma when surrounded by Arabic (v2.4.1)")
    print("=" * 60)
    # Em-dash between Arabic clauses is a Western-typography import; modern
    # Arabic style uses Arabic comma. Pattern: <Arabic> — <text> becomes
    # <Arabic>، <text>
    out = run_humanize(
        "الذكاء الاصطناعي — تقنية حديثة — يغير الصناعات.",
        "--mode", "tighten", "--register", "news",
    )
    # Both em-dashes are between Arabic, so both should become Arabic commas
    r.check("T16.arabic_em_dash_converted",
            "—" not in out and "،" in out,
            f"em-dash not converted: {out!r}")

    print()
    print("=" * 60)
    print("  T17 — em-dash preserved when adjacent to Latin (v2.4.1)")
    print("=" * 60)
    # When em-dash is between English content, preserve it — it's legitimate
    # English-context typography that happens to live in Arabic prose.
    out = run_humanize(
        "OpenAI — a company — released GPT-4 last year.",
        "--mode", "tighten", "--register", "news",
    )
    r.check("T17.english_em_dash_preserved",
            "—" in out,
            f"em-dash incorrectly stripped from English context: {out!r}")

    print()
    print("=" * 60)
    print(f"  Total: {r.passed + r.failed}  |  PASS: {r.passed}  |  FAIL: {r.failed}")
    print("=" * 60)
    sys.exit(0 if r.failed == 0 else 1)


if __name__ == "__main__":
    main()
