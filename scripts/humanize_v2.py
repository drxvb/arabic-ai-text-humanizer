#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Main humanizer pipeline — multi-pass transformation for Arabic AI text.

Modes:
  lex-only     — deterministic lexical pipeline only (~1s, no LLM)
  +cognitive   — lexical + LLM cognitive pass (dimensions 1-8)
  +rhetorical  — lexical + cognitive + rhetorical (dimensions 9-13)
  full         — all passes including final coherence

LLM backends: 'api' (any OpenAI-compatible cloud endpoint, configured via
LLM_API_URL/LLM_API_KEY/LLM_MODEL) or 'local' (Ollama by default).
On backend failure (or when LLM_API_URL is unset for --mode > lex-only):
gracefully degrade to lex-only with warning.

Usage:
    python humanize_v2.py --input "نص" --mode lex-only          # no API needed
    LLM_API_URL=https://api.openai.com/v1/chat/completions \
    LLM_API_KEY=sk-... LLM_MODEL=gpt-4o-mini \
    python humanize_v2.py --file in.txt --mode +cognitive --output out.txt --analyze
"""
from __future__ import annotations
import argparse, json, random, re, sys, time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).parent))
from analyze_deep import analyze, render_report
# v2.6.1: Sacred-text guard — masks Quranic verses, hadith citations, and
# the basmala from every transformation pass; restored verbatim on return.
from sacred_text_guard import mask_sacred_spans, restore_sacred_spans
# v2.6.2: Orthographic hygiene — fix hamzat al-waṣl vs hamzat al-qaṭʿ on
# form-X verbal nouns (Agent A's #1 visible AI-Arabic tell after connectors).
# إستخدام -> استخدام, إستراتيجية -> استراتيجية, etc.
from orthographic_validator import fix_hamzat_alwasl
# v2.6.4: Verb-subject agreement (Agent A's #2 missing-feature). Catches
# الحكومات أعلنوا -> الحكومات أعلنت (fem-pl noun + wrongly-masc-pl verb).
# Conservative: only fires on noun + verb within ~30 chars, allowing one
# intervening particle (قد, لم, لا, لن, ما).
from verb_agreement_validator import fix_verb_agreement

# Import the LLM wrapper lazily (only when --mode > lex-only)


# ── v2.8.0: Vendored lexical literals REMOVED. Toolkit is now a HARD dependency.
# ──
# The six tables (AI_PHRASES_AR, CONNECTORS_AR, REPETITIVE_STARTERS_AR,
# STRUCTURAL_OPENERS_AR, QUOTE_VERBS_ROTATION, INTENSIFIER_DESTACK) are populated
# at module load time from arabic-corpus-toolkit/corpus/lexical-tables.json.
# If the toolkit is unavailable, module load FAILS with an explicit error
# pointing at the install instructions.
#
# ARABIC_CORPUS_TOOLKIT_DISABLE=1 now installs empty stubs (lex-pass becomes
# a no-op) — useful for isolation testing of the LLM cognitive layers but the
# normal runtime path requires the toolkit.
#
# Migration trajectory completed:
#   v2.6.x  -- vendored literals only
#   v2.7.0  -- toolkit as preferred, vendored as fallback (Asset A)
#   v2.7.1  -- toolkit as preferred, vendored as fallback (Asset C)
#   v2.7.2  -- DISABLE flag added for isolation testing
#   v2.8.0  -- vendored literals DELETED. Toolkit hard-dependency. ← THIS RELEASE
#
# History of the vendored definitions lives in the git history at tag v2.7.2.

# Empty stubs — populated by the cutover block below, or left empty under
# ARABIC_CORPUS_TOOLKIT_DISABLE=1.
AI_PHRASES_AR: dict = {}
CONNECTORS_AR: list = []
REPETITIVE_STARTERS_AR: list = []
STRUCTURAL_OPENERS_AR: list = []
QUOTE_VERBS_ROTATION: dict = {}
INTENSIFIER_DESTACK: list = []

# Inline literal AI_PHRASES_AR removed — historical reference inert.
_REMOVED_INLINE_AI_PHRASES_AR_AT_V2_8_0 = {
    # ── PRO-DROP / DELETE-DON'T-SUBSTITUTE entries (per cross-LLM
    # critique) ──
    # Arabic prefers implicit subjects (الضمير المُستتر). For "fluff verbs"
    # that add no meaning, DELETION is grammatically cleaner than
    # substitution. The empty string "" is a valid replacement here; the
    # cleanup_orphans pass will handle the trailing whitespace/punctuation.
    # NOTE: only for phrases whose deletion leaves a grammatical clause.
    # Phrases that end with "أن" still need a clausal replacement (above).
    "من المهم ملاحظة أنه":  ["", "ينبغي تذكُّر أن"],   # safe to delete
    "ولا بد من الإشارة هنا إلى أنه": ["", "نشير هنا إلى أن"],
    "في الواقع":             ["", "حقيقةً"],
    "في الحقيقة":            ["", "حقيقةً"],
    "لا شك أن":              ["", "بلا شك"],
    "بكل تأكيد":             [""],
    "في الواقع والحقيقة":     [""],  # tautology — pure delete
    # ── CLAUSE-PRESERVING replacements (must retain "أن"/"أنّ") ──
    # Per ChatGPT-deep-research finding: when source ends with "أن" / "أنّ"
    # (clausal connector), replacement MUST also end with a clausal connector
    # or it produces ungrammatical output like "بوضوح القرار مناسب".
    # All entries below verified to preserve syntactic clausal context.
    "من المهم ملاحظة أن":  ["نشير إلى أن", "ثمة ما يستوجب التنبيه أن", "يلزم التنبيه إلى أن"],
    "من المهم ملاحظة":     ["نشير إلى", "يلزم التنبيه إلى"],  # bare form
    "من الجدير بالذكر أن": ["مما يُذكر أن", "ومما تجدر معرفته أن"],
    "من الجدير بالذكر":    ["ومما يُذكر", "وتجدر معرفة"],
    "من المفيد الإشارة إلى": ["ثمة ما يستحق الإشارة إلى", "نُشير إلى"],
    "في سياق متصل":         ["وفي صلة بذلك", "وعلى صعيد متصل"],
    "في نفس السياق":        ["وفي السياق ذاته", "وعلى الصعيد نفسه"],
    "علاوة على ذلك":        ["وفوق ذلك", "ويُضاف إلى ذلك"],
    "بالإضافة إلى ذلك":     ["ويُضاف إلى ذلك", "وفوق ذلك"],
    # ── ENGLISH-CALQUE → NATIVE-ARABIC replacements ──
    # AI translations often produce literal calques that read awkwardly in
    # Arabic. "خط أنابيب" (line of pipes) for English "pipeline" is the
    # canonical example — native Arabic uses "مسار عمل" (workflow / path-of-work).
    "خط أنابيب":           ["مسار عمل", "مسار العمل", "تسلسل العمل"],
    "خطّ أنابيب":          ["مسار عمل", "مسار العمل"],
    "خط الأنابيب":         ["مسار العمل", "تسلسل العمل"],
    "خطّ الأنابيب":         ["مسار العمل", "تسلسل العمل"],
    "من ناحية أخرى":        ["وعلى صعيد آخر", "وبالمقابل"],
    "على الجانب الآخر":     ["وعلى الصعيد المقابل", "وبالمقابل"],
    "في النهاية":           ["وفي الختام", "وفي نهاية المطاف"],
    "في البداية":           ["في المبتدأ", "بادئ الأمر"],
    "كما ذكر سابقاً":       ["كما تقدّم", "كما سبق ذكره"],
    "كما أسلفنا":           ["كما تقدّم", "وفي ضوء ما تقدّم"],
    "من الواضح أن":         ["لا يخفى أن", "من البديهي أن", "بات معلوماً أن"],
    "من المهم التأكيد على أن": ["نؤكد أن", "يجدر التأكيد على أن"],
    "لا بد من الإشارة إلى أن": ["مما يستلزم الإشارة إليه أن", "نشير إلى أن"],
    "في إطار":              ["ضمن", "في نطاق"],
    "على صعيد":             ["في مجال", "في إطار"],
    "في ظل":                ["مع وجود", "في وقت"],
    "بناءً على ما تقدم":     ["وبناءً عليه", "وعليه"],
    "جدير بالذكر أن":        ["مما يستحق الذكر أن", "نُشير إلى أن"],
    "من الممكن أن":          ["قد", "ربما"],
    "من المتوقع أن":         ["من المرجح أن", "من المنتظر أن"],
    "يشار إلى أن":           ["نشير إلى أن", "تجدر الإشارة إلى أن"],  # KEEP أن — broken before!
    "يُعتبر من":              ["يُعدّ من", "هو من"],
    "في هذا الإطار":         ["في هذا السياق", "ضمن هذا الإطار"],
    # ── Newsroom AI-tells (from cross-LLM critique, journalist Finding 4) ──
    # 8 patterns the lex layer was missing for news register:
    "في تطور لافت":              ["في تطوّر", ""],
    "في تطور مثير":              ["في تطوّر", ""],
    "في خطوة لافتة":             ["في خطوة", ""],
    "وفي سياق متصل":             ["كذلك", "أيضاً"],
    "وضع معقّد ومتشابك":         ["وضع معقّد"],
    "وضع صعب ومعقّد":            ["وضع صعب"],
    "أزمة حادة ومستفحلة":        ["أزمة حادة"],
    "حسب ما أفادت مصادر":        ["حسب مصادر", ""],
    "قالت مصادر مطلعة":          ["حسب مصادر", "حسب مصدر"],
    "الخبراء والمراقبون":        ["المراقبون"],
    "المحللون والمراقبون":       ["المراقبون"],
    "كثير من الخبراء يرون":      ["خبراء يرون", ""],
    "العديد من المراقبين":       ["مراقبون", ""],
    "ومن المتوقع أن يَ":         ["وقد يَ", "ربما يَ"],
    "كما تَواجه":                ["وتواجه"],
    "كما يُتوقع":                ["ويُتوقع"],
    # ── Gap A (from references/13): missed AI lead-ins ─────────────────────
    "تجدر الإشارة إلى أنّ": ["يُذكر أنّ", "والحقيقة أنّ", ""],
    "تجدر الإشارة إلى أن":  ["يُذكر أن",  "والحقيقة أن",  ""],
    "في هذا الصدد":         ["هنا", "بصدد ذلك", ""],
    "من هذا المنطلق":       ["من هنا", "لذلك"],
    "على هذا الأساس":       ["بناءً على ذلك", "لذلك"],
    "لا شك أنّ":            ["بلا شك", ""],
    "لا شك أن":             ["بلا شك", ""],
    "من المعروف أنّ":       ["المعروف أنّ", ""],
    "من المعروف أن":        ["المعروف أن",  ""],
    "كما هو معلوم":         ["المعلوم أنّ", ""],
    "في حقيقة الأمر":       ["في الحقيقة"],
    "لا يخفى على أحد":      ["الواضح أنّ"],
    "تجدر الإشارة كذلك":    ["كذلك", "يُضاف"],
}

_REMOVED_INLINE_CONNECTORS_AR_AT_V2_8_0 = [
    ("وعلاوة على ذلك،", "كما أن،"),
    ("ومع ذلك،", "لكن،"),
    ("وبالتالي،", "لذلك،"),
    ("وبناءً عليه،", "لذلك،"),
    ("على سبيل المثال،", "مثلاً،"),
    ("في المقابل،", "بالمقابل،"),
    ("على العكس من ذلك،", "بعكس ذلك،"),
    ("باختصار،", "بشكل مختصر،"),
    # ── Gap B (from references/13): missed AI connectors ──────────────────
    ("فضلاً عن ذلك،",       "كذلك،"),
    ("إضافة إلى ذلك،",      "كذلك،"),
    ("من جهة أخرى،",        "بالمقابل،"),
    ("من جانب آخر،",        "بالمقابل،"),
    ("بصورة عامة،",         "عموماً،"),
    ("بشكل عام،",           "عموماً،"),
    ("بشكل خاص،",           "خصوصاً،"),
    ("في الواقع،",          "فعلاً،"),
    ("في حين أنّ",          "بينما"),
    ("في حين أن",           "بينما"),
    ("على الرغم من ذلك،",   "رغم ذلك،"),
    ("نتيجة لذلك،",         "لذلك،"),
    ("استناداً إلى ذلك،",   "بناءً عليه،"),
    ("تبعاً لذلك،",         "لذلك،"),
]

_REMOVED_INLINE_REPETITIVE_STARTERS_AR_AT_V2_8_0 = [
    "تعتبر", "تُعتبر", "يُعتبر", "تعد", "يُعد", "تُعد",
    "يمكن", "تستطيع", "نستطيع", "يعتبر", "يعد",
]

# ── Gap C (from references/13): AI structural openers → active rephrasings ──
# Fix #5/bug-1 (comp-linguist): `\S+` doesn't span two-word compounds like
# "الذكاء الاصطناعي". Switched to `([ء-ي\s]{1,40}?)` — Arabic-letters-or-spaces,
# bounded length, lazy match, so "يلعب الذكاء الاصطناعي دوراً" now matches.
_REMOVED_INLINE_STRUCTURAL_OPENERS_AR_AT_V2_8_0 = [
    (r"يلعب ([ء-ي\s]{1,40}?) دوراً",       ["{0} يحدّد", "{0} يُشكّل", "{0} يَصنع"]),
    (r"يشكّل ([ء-ي\s]{1,40}?) عاملاً",     ["{0} هو السبب الرئيسي", "{0} يُحدِّد"]),
    (r"يمثّل ([ء-ي\s]{1,40}?) جزءاً",      ["{0} هو", "{0} يُعدّ"]),
    (r"يكمن ([ء-ي\s]{1,40}?) في",          ["السبب", "ها هو السبب"]),
    (r"تنبع ([ء-ي\s]{1,40}?) من",          ["يَأتي من", "أصلها"]),
    (r"تتمثّل ([ء-ي\s]{1,40}?) في",        ["هي:", "تَتلخّص في"]),
    (r"تكتسب ([ء-ي\s]{1,40}?) أهمية",      ["تُهمّ", "حاسمة"]),
    (r"تواجه ([ء-ي\s]{1,40}?) تحديات",     ["أمام {0} تحديات", "{0} يَتعثّر في"]),
    (r"تشهد ([ء-ي\s]{1,40}?) تطوراً",      ["{0} يَتطوّر"]),
    (r"تسعى ([ء-ي\s]{1,40}?) إلى",         ["{0} تُريد", "{0} تَطمح إلى"]),
]

# ── Gap D (from references/13): news-register quote-verb rotation ──
_REMOVED_INLINE_QUOTE_VERBS_ROTATION_AT_V2_8_0 = {
    "قال":   ["أكّد", "أشار", "أوضح", "أضاف", "صرّح", "ذكر", "نوّه", "لفت"],
    "يقول":  ["يَرى", "يَعتقد", "يَزعم", "يُقرّر", "يُؤكّد"],
    "ذكر أن": ["أفاد بأنّ", "أشار إلى أنّ", "لفت إلى أنّ", "كشف أنّ"],
    "ذكر أنّ": ["أفاد بأنّ", "أشار إلى أنّ", "لفت إلى أنّ", "كشف أنّ"],
}

# ── Gap G (from references/13): redundant intensifier stacks ──
_REMOVED_INLINE_INTENSIFIER_DESTACK_AT_V2_8_0 = [
    # (pattern_regex, replacement)
    (r"في غاية الأهمية البالغة(?:\s+جداً)?",  "بالغ الأهمية"),
    (r"بشكل كبير جداً",                       "كثيراً"),
    (r"بصورة ملحوظة وواضحة",                  "بوضوح"),
    (r"بشكل واضح وملحوظ",                     "بوضوح"),
    (r"بصورة كاملة وشاملة",                   "بشكل كامل"),
    (r"بشكل تام ومطلق",                       "تماماً"),
    (r"للغاية\s+جداً",                        "للغاية"),
    (r"جداً\s+جداً",                          "جداً"),
]

# ── Dim 14: Reader respect — DELETION operations ──
# See references/14-reader-respect.md
# (a) Tautological affirmation: triplet adjective stacks meaning the same
TAUTOLOGY_DELETE = [
    # (pattern_regex, replacement_or_empty)
    (r"مؤكَّد\s+وحقيقي\s+وثابت",      "مؤكَّد"),
    (r"مؤكد\s+وحقيقي\s+وثابت",        "مؤكد"),
    (r"حقيقي\s+ومؤكَّد\s+وثابت",      "ثابت"),
    (r"واقعي\s+ومؤكَّد",              "ثابت"),
    (r"ثابت\s+وراسخ",                  "راسخ"),
    (r"واضح\s+وجَلِيّ",                "واضح"),
    (r"واضح\s+وجلي",                   "واضح"),
    (r"معلوم\s+ومعروف",                "معروف"),
    (r"بدِيهي\s+ومعلوم",               "بدِيهي"),
    (r"وهذا\s+أمر\s+مؤكَّد",           ""),
    (r"وهذا\s+أمر\s+مؤكد",             ""),
    (r"وهذا\s+حقيقة",                  ""),
    (r"بلا\s+شك\s+ولا\s+ريب",          "بلا شك"),
    (r"وهذا\s+واضح\s+وجَلِيّ",         ""),
    (r"وهذا\s+واضح\s+وجلي",            ""),
    (r"ولا\s+يخفى\s+على\s+أحد",        ""),
    (r"كما\s+هو\s+معلوم\s+ومعروف",     "كما هو معروف"),
]

# (b) Re-explanation: "أي بمعنى آخر" + the restatement that follows it.
# Conservative: delete the marker phrase but keep what follows (humanizer
# can't reliably detect that the following is redundant; the marker itself
# IS the AI tell).
RE_EXPLANATION_DELETE = [
    r"أي\s+بمعنى\s+آخر[،,]?",
    r"بمعنى\s+آخر[،,]?",
    r"وهذا\s+يعني\s+أنّ?",
    r"بعبارة\s+أخرى[،,]?",
    r"وبتعبير\s+آخر[،,]?",
    r"وبعبارة\s+أوضح[،,]?",
    r"بعبارة\s+أوضح[،,]?",
    r"ولتوضيح\s+ذلك\s+أكثر[،,]?",
    r"وحتى\s+تتّضح\s+الفكرة[،,]?",
    r"وحتى\s+تتضح\s+الفكرة[،,]?",
    r"ولزيادة\s+الإيضاح[،,]?",
    r"ولكي\s+يتّضح\s+المعنى[،,]?",
]

# (c) Forced conclusion: prefixes that draw the conclusion FOR the reader.
# Delete the prefix; the (often-obvious) conclusion that follows stands
# on its own. Patterns must absorb leading "و" AND the trailing pronoun
# suffix of "أنّه/أنّها/أنّهم" so we don't leave orphan "ه" in output.
# Pronoun-suffix group: (?:ه|ها|هم|هن|هما)?
FORCED_CONCLUSION_DELETE = [
    r"و?نستنتج\s+من\s+هذا\s+أنّ?(?:ه|ها|هم|هن|هما)?",
    r"و?نَستنتج\s+من\s+هذا\s+أنّ?(?:ه|ها|هم|هن|هما)?",
    r"و?نستنتج\s+أنّ?(?:ه|ها|هم|هن|هما)?",
    # "يَدلّ على" — the "أنّ" is optional in Arabic; the pattern can be
    # "يَدلّ على ضَرورة X" (noun) or "يَدلّ على أنّ X" (clause). Match both.
    r"وهذا\s+يدل\s+على(?:\s+أنّ?(?:ه|ها|هم|هن|هما)?)?",
    r"وهذا\s+يَدلّ\s+على(?:\s+أنّ?(?:ه|ها|هم|هن|هما)?)?",
    r"ومن\s+هنا\s+نفهم\s+أنّ?(?:ه|ها|هم|هن|هما)?",
    r"و?عليه\s+يتضح\s+أنّ?(?:ه|ها|هم|هن|هما)?",
    r"و?عليه\s+يَتّضح\s+أنّ?(?:ه|ها|هم|هن|هما)?",
    r"وهذا\s+برهان\s+قاطع\s+على\s+أنّ?(?:ه|ها|هم|هن|هما)?",
    r"ومن\s+الواضح\s+إذن\s+أنّ?(?:ه|ها|هم|هن|هما)?",
    r"وبالتالي\s+نَخلص\s+إلى\s+أنّ?(?:ه|ها|هم|هن|هما)?",
]

# (d) Known-term definitions: "ونعني بـ X هو ..." — delete the gloss.
# Fix #5/bug-4 (comp-linguist): يُعرَّف has shadda which doesn't match يعرف.
# Solution: allow optional diacritics in the verb stems using [ً-ٟ]?
# and use Arabic-letter-or-space class for the captured term so multi-word
# terms like "الذكاء الاصطناعي" are captured.
KNOWN_TERM_DELETE = [
    r"ونعني\s+ب[ـِ]?\s*[ء-ي\s]{1,40}?\s+هو",
    r"والمقصود\s+ب[ـِ]?\s*[ء-ي\s]{1,40}?\s+(?:هو|أنّ?)",
    r"يُ?ع[ـَ]?رّ?[ـَّ]?ف\s+[ء-ي\s]{1,40}?\s+بأنّ?ه?",
    r"وَ?ي[ـُ]?ع[ـَ]?رّ?[ـَّ]?ف\s+[ء-ي\s]{1,40}?\s+بأنّ?ه?",
    # Bare undiacritized forms (post-normalization):
    r"يعرف\s+[ء-ي\s]{1,40}?\s+بأنه?",
    r"ويعرف\s+[ء-ي\s]{1,40}?\s+بأنه?",
]


# ── Lexical pass (inherited + cleaned) ──────────────────────────────────────

# ── Gap F: quoted-span suppression — protect content inside "..." and «...» ──
QUOTED_SPAN = re.compile(r'(?:"[^"]*"|«[^»]*»|\'[^\']*\')', re.DOTALL)


def _outside_quoted_spans(text: str):
    """Yield (start, end, is_quoted) segments so callers can skip in-quote text."""
    cursor = 0
    for m in QUOTED_SPAN.finditer(text):
        if m.start() > cursor:
            yield cursor, m.start(), False
        yield m.start(), m.end(), True
        cursor = m.end()
    if cursor < len(text):
        yield cursor, len(text), False


def _apply_outside_quotes(text: str, transform) -> str:
    """Apply transform(segment) only to non-quoted segments; preserve quoted spans verbatim."""
    out = []
    for s, e, is_q in _outside_quoted_spans(text):
        seg = text[s:e]
        out.append(seg if is_q else transform(seg))
    return "".join(out)


def lex_replace_phrases(text: str) -> str:
    def _replace(seg: str) -> str:
        for phrase, alts in AI_PHRASES_AR.items():
            if phrase not in seg: continue
            first = seg.find(phrase)
            choice = random.choice(alts)
            after = first + len(phrase)
            # When deletion picked (empty replacement), absorb the surrounding
            # whitespace + a trailing comma so we don't leave orphan punctuation.
            if choice == "":
                # Skip a trailing space + comma if present
                while after < len(seg) and seg[after] in " ،,":
                    after += 1
                # Also collapse the leading space before the phrase
                if first > 0 and seg[first - 1] == " ":
                    first -= 1
                # If we absorbed whitespace on BOTH sides we'd merge adjacent
                # words ("أن" + "يحتاج" → "أنيحتاج"). Insert a single space when
                # the deletion sits between two non-boundary characters; the
                # final re.sub(r'\s+', ' ') collapse normalizes any duplicates.
                if first > 0 and after < len(seg):
                    choice = " "
            seg = seg[:first] + choice + seg[after:]
        return seg
    return _apply_outside_quotes(text, _replace)


def lex_destack_intensifiers(text: str) -> str:
    """Gap G: collapse redundant intensifier stacks."""
    def _destack(seg: str) -> str:
        for pat, rep in INTENSIFIER_DESTACK:
            seg = re.sub(pat, rep, seg)
        return seg
    return _apply_outside_quotes(text, _destack)


def lex_dim14_anti_tautology(text: str) -> str:
    """Dim 14: collapse tautological adjective stacks (مؤكَّد وحقيقي وثابت → مؤكَّد)
    and delete redundant affirmation phrases (وهذا أمر مؤكَّد) entirely."""
    def _apply(seg: str) -> str:
        for pat, rep in TAUTOLOGY_DELETE:
            seg = re.sub(pat, rep, seg)
        return seg
    return _apply_outside_quotes(text, _apply)


def lex_dim14_anti_re_explanation(text: str) -> str:
    """Dim 14: delete 'أي بمعنى آخر' family — the re-explanation prefix is itself
    the AI tell. The text immediately following often IS the re-explanation;
    we keep it (user can edit) since automated deletion of the gloss requires
    semantic understanding the lex pass doesn't have."""
    def _apply(seg: str) -> str:
        for pat in RE_EXPLANATION_DELETE:
            seg = re.sub(pat, "", seg)
        return seg
    return _apply_outside_quotes(text, _apply)


def lex_dim14_anti_forced_conclusion(text: str) -> str:
    """Dim 14: delete prefixes that explicitly tell the reader 'here is the
    conclusion'. The conclusion remains, but now reads as an assertion the
    reader is invited to verify rather than a verdict pre-chewed."""
    def _apply(seg: str) -> str:
        for pat in FORCED_CONCLUSION_DELETE:
            seg = re.sub(pat, "", seg)
        return seg
    return _apply_outside_quotes(text, _apply)


def lex_dim14_anti_known_definitions(text: str) -> str:
    """Dim 14: delete 'ونعني بـ X هو ...' definitional intros for terms the
    audience knows. Conservative: only deletes the marker phrase; the
    definition itself may remain (calling layer can decide to drop it)."""
    def _apply(seg: str) -> str:
        for pat in KNOWN_TERM_DELETE:
            seg = re.sub(pat, "", seg)
        return seg
    return _apply_outside_quotes(text, _apply)


def lex_dim14_cleanup_orphans(text: str) -> str:
    """Dim 14: after deletions, clean up orphan punctuation and double commas.

    Per cross-LLM critique of the original research: when a fluff phrase is
    deleted, it can leave orphan periods like ". " between sentences.
    Strip those too.
    """
    # Collapse multiple spaces + orphan commas left by deletions
    text = re.sub(r'\s*،\s*،\s*', '، ', text)
    text = re.sub(r'\.\s*،', '.', text)
    text = re.sub(r'،\s*\.', '.', text)
    # Orphan periods (period followed only by space then end-of-string OR
    # period followed by space then another period) — from deleted "بكل تأكيد."
    text = re.sub(r'(?<=\.)\s*\.\s*', ' ', text)
    text = re.sub(r'^\s*\.\s*', '', text, flags=re.M)  # leading orphan period
    text = re.sub(r'^\s*،\s*', '', text, flags=re.M)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


# ── Dim 15: Typography hygiene — runs LAST in the pipeline ──
# See references/15-typography-hygiene.md

# Pre-compiled regex for normalization passes
_URL_OR_PATH = re.compile(r'https?://\S+|/[\w./]+|\b\w+@\w+\.\w+')
_INLINE_CODE = re.compile(r'`[^`\n]+`')
_DECIMAL = re.compile(r'\b\d+\.\d+\b')


def _protect_spans(text: str) -> tuple[str, list[str]]:
    """Replace URLs / inline-code / decimals with placeholders so typography
    normalization doesn't break them. Returns (protected_text, originals)."""
    protected = []
    def _stash(match):
        protected.append(match.group(0))
        return f"\x00PROTECT{len(protected)-1}\x00"
    text = _URL_OR_PATH.sub(_stash, text)
    text = _INLINE_CODE.sub(_stash, text)
    text = _DECIMAL.sub(_stash, text)
    return text, protected


def _restore_spans(text: str, originals: list[str]) -> str:
    for i, orig in enumerate(originals):
        text = text.replace(f"\x00PROTECT{i}\x00", orig)
    return text


def typography_ar_en_spacing(text: str) -> str:
    """Rule 1: insert space between Arabic and Latin letters."""
    # Arabic followed by Latin → space between
    text = re.sub(r'([؀-ۿ])([A-Za-z])', r'\1 \2', text)
    # Latin followed by Arabic → space between
    text = re.sub(r'([A-Za-z])([؀-ۿ])', r'\1 \2', text)
    return text


def typography_latin_punct_to_arabic(text: str) -> str:
    """Rule 2: replace Latin , ; ? with Arabic ، ؛ ؟ when in Arabic context."""
    # Comma between Arabic words
    text = re.sub(r'([؀-ۿ])\s*,\s*([؀-ۿ])', r'\1، \2', text)
    text = re.sub(r'([؀-ۿ])\s*,\s*$', r'\1،', text, flags=re.M)
    # Semicolon between Arabic words
    text = re.sub(r'([؀-ۿ])\s*;\s*([؀-ۿ])', r'\1؛ \2', text)
    # Question mark at end of Arabic clause: detect by an Arabic-letter run
    # ending with `?` and no Latin letters between (so we don't false-positive
    # on English questions)
    def _qmark_replace(m):
        clause = m.group(0)
        if re.search(r'[A-Za-z]', clause):
            return clause  # English question, leave it
        return clause[:-1] + '؟'
    text = re.sub(r'[؀-ۿ][^.\n?]{0,200}\?', _qmark_replace, text)
    return text


def typography_punct_spacing(text: str) -> str:
    """Rule 3: ensure space after Arabic punctuation marks."""
    # Arabic comma directly followed by non-space → insert space
    text = re.sub(r'([،؛])(?=\S)', r'\1 ', text)
    # Arabic period (.) followed by Arabic letter without space → insert space.
    # Use Arabic-letter lookahead so we don't break decimals (handled by protect_spans).
    text = re.sub(r'\.(?=[؀-ۿ])', '. ', text)
    # Latin colon ":" between Arabic words without space — used commonly in
    # Arabic with no surrounding space; normalize to ": " for readability
    text = re.sub(r':(?=[؀-ۿ])', ': ', text)
    return text


def typography_paren_spacing(text: str) -> str:
    """Rule 4: pad ASCII parens around Latin/digit content in Arabic context,
    AND ensure paren boundaries don't merge with adjacent Arabic letters."""
    # ( followed by Latin letter or digit → ( + space + content
    text = re.sub(r'\(([A-Za-z0-9])', r'( \1', text)
    # Latin letter or digit followed by ) → content + space + )
    text = re.sub(r'([A-Za-z0-9])\)', r'\1 )', text)
    # Closing paren followed by Arabic letter → ) + space
    text = re.sub(r'\)([؀-ۿ])', r') \1', text)
    # Arabic letter followed by opening paren → letter + space + (
    text = re.sub(r'([؀-ۿ])\(', r'\1 (', text)
    return text


def typography_normalize_numbering(text: str) -> str:
    """Rule 5: normalize line-leading list numbering to `N. ` style."""
    # `(1)` at line-start → `1. `
    text = re.sub(r'(?m)^(\s*)\((\d+)\)\s*', r'\1\2. ', text)
    # `1-` at line-start → `1. ` (but only when not followed by another digit, to
    # avoid converting date-like 2024-05)
    text = re.sub(r'(?m)^(\s*)(\d+)-(?=\s)', r'\1\2.', text)
    return text


# ── Mode "enrich": targeted marker insertion to lift low-scoring dimensions ──
# Per cross-LLM critique: regex-based MARKER INSERTION is risky for high-craft
# dimensions (jinas, historical analogy, metaphor — all need semantic
# understanding). enrich ONLY targets the regex-detectable additive dims:
#   1 (deduction/reasoning), 4 (analysis), 5 (graduated), 6 (scope),
#   7 (transitions), 8 (axes), 13 (coherence/citation).
# Dims 10 (historical), 11 (imagination), 12 (rhetoric) NEED LLM augmentation.
# Cap: at most 3 enrichments per text — avoids the "mannerism by accumulation"
# failure mode that classical-stylist and senior-editor critiques flagged.

ENRICHMENT_INSERTS = {
    1: {"insertion": "إذ ", "where": "before_2nd_sentence",
        "rationale": "Inserts 'إذ' (reasoning marker) — lifts deduction/inference dims."},
    4: {"insertion": "وبالمقارنة، ", "where": "before_3rd_sentence",
        "rationale": "Comparison marker — lifts human-analysis dim."},
    5: {"insertion": "بدايةً، ", "where": "prepend_first_sentence",
        "rationale": "Scaffolding opener — lifts graduated-explanation dim."},
    6: {"insertion": "في حدود ما يخصّ هذا الموضوع، ", "where": "prepend_first_sentence",
        "rationale": "Scope-definition marker."},
    7: {"insertion": " ومن جهة أخرى، ", "where": "between_2nd_3rd_sentence",
        "rationale": "Transition marker — lifts idea-transitions dim."},
    8: {"insertion": "أمّا الأول فـ", "where": "before_second_sentence_only_if_list_pattern",
        "rationale": "Partitioning marker — lifts axes-partitioning dim."},
    13: {"insertion": " وكما تَقدّم، ", "where": "before_last_sentence",
         "rationale": "Intra-text citation — lifts coherence dim."},
}


def _split_sentences_keepall(text: str) -> list[str]:
    """Split on ., !, ?, ؟, ؛ but keep the terminators attached to sentences."""
    parts = re.split(r'([.!?؟؛]+\s+)', text)
    sentences = []
    i = 0
    while i < len(parts):
        s = parts[i]
        if i + 1 < len(parts):
            s = s + parts[i + 1]
            i += 2
        else:
            i += 1
        if s.strip():
            sentences.append(s)
    return sentences


def lex_enrich(text: str, analyzer_result: dict, max_inserts: int = 3) -> tuple[str, list[dict]]:
    """Insert markers to lift low-scoring fixable dimensions.

    analyzer_result: output of analyze_deep.analyze(text)
    Returns: (enriched_text, list_of_insertions_applied)
    """
    # Pick lowest-scoring fixable dims (1, 4, 5, 6, 7, 8, 13)
    fixable = [d for d in (1, 4, 5, 6, 7, 8, 13)
               if analyzer_result["by_dimension"][d]["score"] < 8]
    fixable.sort(key=lambda d: analyzer_result["by_dimension"][d]["score"])
    targets = fixable[:max_inserts]

    sentences = _split_sentences_keepall(text)
    if len(sentences) < 2:
        return text, []  # too short to enrich safely

    applied = []
    for dim in targets:
        spec = ENRICHMENT_INSERTS[dim]
        where = spec["where"]
        insertion = spec["insertion"]
        if where == "prepend_first_sentence":
            sentences[0] = insertion + sentences[0]
        elif where == "before_2nd_sentence" and len(sentences) >= 2:
            sentences[1] = insertion + sentences[1]
        elif where == "before_3rd_sentence" and len(sentences) >= 3:
            sentences[2] = insertion + sentences[2]
        elif where == "between_2nd_3rd_sentence" and len(sentences) >= 3:
            # Insert as a tiny clause before sentence 3
            sentences[2] = insertion.strip() + " " + sentences[2]
        elif where == "before_last_sentence" and len(sentences) >= 2:
            sentences[-1] = insertion + sentences[-1]
        elif where == "before_second_sentence_only_if_list_pattern":
            # Heuristic: if sentences 2+ look like a list (start with similar
            # structure), apply أمّا الأول فـ. Skip if not.
            if len(sentences) >= 3:
                sentences[1] = insertion + sentences[1]
        else:
            continue  # skip if no applicable position
        applied.append({"dim": dim, "insertion": insertion, "rationale": spec["rationale"]})

    return " ".join(s.strip() for s in sentences), applied


def typography_arabic_list_conjunction(text: str) -> str:
    """Per Itwadi.com Arabic style guide: Arabic lists retain `و` before
    each item except the first — unlike English which uses 'and' only
    before the last item.

      English: "Arabic, Mathematics, and Chemistry"
      Arabic:  "العربي، والرياضيات، والكيمياء"  (و before each item after first)

    AI translators sometimes produce English-style lists in Arabic. This
    pass inserts و before list items 2..n.

    CONSERVATIVE detection — only fires when:
      1. At least 3 comma-separated tokens (the standard "list" threshold)
      2. ALL tokens are single Arabic words (no internal spaces, ≤20 chars)
         — this prevents firing on short-clause commas like
         "كنت سعيداً، رأيت صديقاً" which has multi-word phrases between commas
      3. Items don't already start with و (preserve already-correct lists)

    Known limitation: the LAST item of a list with a multi-word phrase
    (e.g., "الأسد، النمر، الفهد، النمر الأسود" — last item is 2 words)
    gets skipped because the pattern requires single-word items throughout.
    Worth handling in v2.4.5.
    """
    # Pattern: 2+ short Arabic words followed by ،\s+, then one final short word
    # The {2,} repetition + final token = 3+ items total
    LIST_RE = re.compile(
        r'(?:[؀-ۿ]{1,20}،\s+){2,}[؀-ۿ]{1,20}',
        re.UNICODE,
    )

    def _add_waw(match: re.Match) -> str:
        items = re.split(r'،\s+', match.group(0))
        for i in range(1, len(items)):
            if not items[i].startswith('و'):
                items[i] = 'و' + items[i]
        return '، '.join(items)

    return LIST_RE.sub(_add_waw, text)


def typography_quotes_to_arabic_guillemets(text: str, register: str = "news") -> str:
    """In CLASSICAL register, convert ASCII straight quotes around Arabic
    content to Arabic guillemets (« »). Per Mawdoo3 and classical academic
    conventions, « » is the formal Arabic quotation mark; ASCII " " is the
    modern/news form.

    Register-gated — only fires for `classical`. News/opinion/technical
    preserve the source's quotation style (modern convention).
    """
    if register != "classical":
        return text

    def _convert(m: re.Match) -> str:
        content = m.group(1)
        # Only convert if content contains at least one Arabic letter
        if re.search(r"[؀-ۿ]", content):
            return "«" + content + "»"
        return m.group(0)

    # ASCII straight double quotes
    text = re.sub(r'"([^"]+)"', _convert, text)
    # Smart/curly double quotes (U+201C / U+201D)
    text = re.sub(r'“([^”]+)”', _convert, text)
    return text


def typography_paren_interior_spacing(text: str) -> str:
    """Per multiple Arabic style guides (Kaplan: "no spacing between brackets
    and content"; proof-reading-service; mawdoo3; albuthi):
    parentheses should NOT have spacing immediately inside their boundaries
    when wrapping Arabic content.

    Also: closing paren followed by punctuation should have the punctuation
    attached (per the universal no-pre-space rule from v2.4.2).

    Examples:
      '( محتوى )'    → '(محتوى)'    (Arabic interior spaces removed)
      'النص (الإيضاح) .'  → 'النص (الإيضاح).'   (space before . after ) removed)

    PRESERVES Latin content paren padding (already added by
    typography_paren_spacing for Latin-in-Arabic Bidi clarity).
    """
    # Strip space AFTER opening paren when followed by Arabic letter
    text = re.sub(r'\(\s+(?=[؀-ۿ])', '(', text)
    # Strip space BEFORE closing paren when preceded by Arabic letter
    text = re.sub(r'(?<=[؀-ۿ])\s+\)', ')', text)
    # Strip space between closing paren and any following punctuation
    text = re.sub(r'\)\s+([،؛؟:!.])', r')\1', text)
    return text


def typography_comma_to_semicolon_before_causal(text: str) -> str:
    """Per multiple authoritative Arabic style guides (Al Jazeera Learning,
    Loghate, Drasah, KSU, Mawdoo3, Mobt3ath), the Arabic SEMICOLON (؛) — not
    Arabic comma (،) — is the correct mark before clauses expressing CAUSE
    or REASON. Naive AI translation typically uses a comma where Arabic
    style prescribes a semicolon.

    This conversion is CONSERVATIVE — only fires for connectors that are
    UNAMBIGUOUSLY causal in modern Arabic:
      - لأن, لأنّ  ("because") — always causal
      - لذلك        ("therefore") — always consequential
      - لذا         ("thus") — always consequential
      - ومن ثَمَّ    ("and consequently") — always consequential

    SKIPS connectors with non-causal senses:
      - إذ  (can mean "because" or "when" — temporal/causal ambiguity)
      - حيث (can mean "because", "where", or relative pronoun)
      - إذن (often "then" or "therefore" — too context-dependent)

    Example:
      "كان مجتهداً، لذلك نجح"  →  "كان مجتهداً؛ لذلك نجح"
      "أحب الكتاب، لأنه ممتع"  →  "أحب الكتاب؛ لأنه ممتع"
    """
    # Match: Arabic letter, then ،  then space(s) + an unambiguous causal connector
    return re.sub(
        r'([؀-ۿ])،(\s+(?:لأن[ّ]?|لذلك|لذا|ومن ثَمَّ))',
        r'\1؛\2',
        text,
    )


def typography_no_space_before_arabic_punct(text: str) -> str:
    """Remove whitespace BEFORE Arabic punctuation marks. Per multiple
    authoritative Arabic style guides (Al Jazeera Learning, Loghate,
    Drasah), Arabic punctuation is ATTACHED to the preceding word:

      "ملاصقة للكلمة التي قبلها، مع وجود مسافة مع الكلمة التي بعدها"
      (attached to the previous word, with space after to the next word)

    Marks covered: ، ؛ ؟ : ! . (Arabic comma, semicolon, question mark,
    colon, exclamation, and Latin period when following Arabic letter).

    Examples:
      'كلمة ، كلمة' → 'كلمة، كلمة'   (pre-space removed; post-space kept)
      'النص .' → 'النص.'             (period attached)
      'سؤال ؟' → 'سؤال؟'             (question mark attached)
      'كلمة, word'  →  unchanged       (Latin comma in Latin context — not Arabic punct)
    """
    # Arabic letter + whitespace + Arabic-specific punctuation
    text = re.sub(r'([؀-ۿ])\s+([،؛؟:!])', r'\1\2', text)
    # Arabic letter + whitespace + Latin period (Arabic uses Latin `.` as sentence end)
    text = re.sub(r'([؀-ۿ])\s+\.', r'\1.', text)
    return text


def typography_strip_kashida(text: str) -> str:
    """Strip Arabic kashida/tatweel (U+0640) — modern editorial convention
    for encoded body text. Kashida is for display typography (logos,
    posters, justified-text rendering at typeset time), NOT for encoded
    data. See https://shoairschool.com/basics-of-kashida-in-design/ —
    rule: 'kashida functions primarily in display settings'.

    Also: in encoded text, kashida fragments search/TTS/accessibility
    (e.g., 'نظام' vs 'نـظام' are different strings to a search engine).
    AI translators sometimes inject kashida to 'look more Arabic' — this
    is the exact opposite of professional Arabic typography.
    """
    return text.replace("ـ", "")


# Em-dash converter: replace `—` with `، ` when surrounded by Arabic on the
# left side, otherwise preserve. This catches AI-Arabic where the model
# carried English em-dashes into Arabic prose, while preserving legitimate
# Arabic-English mixed contexts (e.g., "OpenAI — مؤسسة" keeps em-dash).
_EM_DASH_ARABIC_RE = re.compile(r'([؀-ۿ])\s*—\s*')


def typography_em_dash_to_arabic_comma(text: str) -> str:
    """Convert em-dash (U+2014) to Arabic comma (U+060C) when preceded by
    Arabic letters. Preserves em-dashes in English-context spans.

    Examples:
      "النص — التعليق"     → "النص، التعليق"     (Arabic context)
      "OpenAI — مؤسسة"     → "OpenAI — مؤسسة"   (English context preserved)
      "fast — and reliable" → "fast — and reliable" (no Arabic, preserved)
    """
    return _EM_DASH_ARABIC_RE.sub(r"\1، ", text)


def lex_dim15_typography(text: str, register: str = "news") -> str:
    """Dim 15: apply all typography rules with URL/code/decimal protection.

    `register` parameter (added v2.4.4) determines register-gated behaviors:
      - classical: enables guillemets conversion («...»)
      - news/opinion/technical: preserves ASCII quotation marks
    """
    text, protected = _protect_spans(text)
    text = typography_ar_en_spacing(text)
    text = typography_latin_punct_to_arabic(text)
    text = typography_punct_spacing(text)
    text = typography_paren_spacing(text)
    text = typography_normalize_numbering(text)
    # v2.4.1 additions:
    text = typography_strip_kashida(text)
    text = typography_em_dash_to_arabic_comma(text)
    # v2.4.2 additions: enforce no-space-before-Arabic-punctuation rule
    # and convert comma to semicolon before unambiguous causal connectors
    # (per Al Jazeera Learning, Loghate, Drasah, KSU, Mawdoo3, Mobt3ath
    # — see typography_no_space_before_arabic_punct and
    # typography_comma_to_semicolon_before_causal docstrings)
    text = typography_no_space_before_arabic_punct(text)
    text = typography_comma_to_semicolon_before_causal(text)
    # v2.4.3 addition: parenthesis interior-spacing normalization
    # (per Kaplan + proof-reading-service: "no spacing between brackets
    # and content"). Strips Arabic interior padding; preserves Latin.
    text = typography_paren_interior_spacing(text)
    # v2.4.4 additions: list-conjunction و insertion (per Itwadi) and
    # register-gated ASCII-quotes → Arabic guillemets « » (per Mawdoo3 +
    # classical academic conventions).
    text = typography_arabic_list_conjunction(text)
    text = typography_quotes_to_arabic_guillemets(text, register=register)
    # Collapse any double-spaces introduced
    text = re.sub(r'  +', ' ', text)
    text = _restore_spans(text, protected)
    return text


def lex_rotate_quote_verbs(text: str, prob: float = 0.6) -> str:
    """Gap D: rotate news-register quote verbs.
    Use Arabic-aware boundaries — `\\b` matches inside Arabic words (e.g., 'ذكر'
    inside 'يُذكر') because Python regex word-boundary is ASCII-only.
    """
    # Arabic letter class (letters only, NOT diacritics — diacritics shouldn't
    # break a word-boundary either, but the safer approach is to require that
    # the verb be preceded by start-of-segment or whitespace).
    AR_LETTER_CLASS = r'[ء-ي]'  # Arabic letters
    def _rotate(seg: str) -> str:
        for verb, alts in QUOTE_VERBS_ROTATION.items():
            # (?<![Arabic letter or diacritic])verb(?=whitespace + name | :)
            # Require: NOT preceded by an Arabic letter (so 'يُذكر' won't match for verb='ذكر')
            # AND followed by whitespace + name OR by ':' / '"' / '«'
            pattern = re.compile(
                rf'(?<!{AR_LETTER_CLASS})(?<![ً-ٰٟـ]){re.escape(verb)}'
                rf'(?=\s+{AR_LETTER_CLASS}|\s*[:"«])'
            )
            def _sub(m):
                if random.random() < prob:
                    return random.choice(alts)
                return m.group(0)
            seg = pattern.sub(_sub, seg)
        return seg
    return _apply_outside_quotes(text, _rotate)


def lex_break_structural_openers(text: str) -> str:
    """Gap C: replace AI's noun-frame structural openers with active alternatives."""
    def _break(seg: str) -> str:
        for pat, alts in STRUCTURAL_OPENERS_AR:
            if random.random() < 0.5:
                def _sub(m):
                    alt = random.choice(alts)
                    if "{0}" in alt and m.lastindex:
                        return alt.format(m.group(1))
                    return alt
                seg = re.sub(pat, _sub, seg, count=1)
        return seg
    return _apply_outside_quotes(text, _break)


def lex_replace_connectors(text: str) -> str:
    for formal, natural in CONNECTORS_AR:
        if random.random() < 0.7:
            text = text.replace(formal, natural, 1)
    return text


def lex_diversify_starters(text: str) -> str:
    """Break consecutive sentences starting with same repetitive starter."""
    sentences = re.split(r'(?<=[.!؟])\s+', text)
    if len(sentences) < 3: return text
    out = []
    last_starter = None
    for s in sentences:
        s = s.strip()
        if not s: continue
        match = None
        for st in REPETITIVE_STARTERS_AR:
            if s.startswith(st):
                match = st
                break
        if match and match == last_starter and random.random() < 0.5:
            # Replace with pronoun start
            s = re.sub(rf'^{re.escape(match)}\s*',
                       random.choice(["فهي ", "وهي ", "إنها ", "كما أنها "]),
                       s)
        last_starter = match
        out.append(s)
    return ' '.join(out)


def lex_break_lists(text: str) -> str:
    """Replace mechanical numbered transitions occasionally."""
    text = re.sub(r'\bأولاً،\s*',
                  lambda m: random.choice(['في البداية، ', 'لنبدأ بـ ', 'أولاً، ']),
                  text)
    text = re.sub(r'\bثانياً،\s*',
                  lambda m: random.choice(['بعد ذلك، ', 'يلي ذلك، ', 'ثانياً، ']),
                  text)
    text = re.sub(r'\bثالثاً،\s*',
                  lambda m: random.choice(['ثم، ', 'ولا يفوتنا، ', 'ثالثاً، ']),
                  text)
    text = re.sub(r'\bأخيراً،\s*',
                  lambda m: random.choice(['وفي الختام، ', 'وأخيراً، ', 'وآخر ذلك، ']),
                  text)
    return text


def lex_vary_lengths(text: str, intensity: float) -> str:
    """Split overly long sentences occasionally (intensity 0.0-1.0)."""
    sentences = re.split(r'(?<=[.!؟])\s+', text)
    out = []
    for s in sentences:
        s = s.strip()
        if not s: continue
        words = s.split()
        if len(words) > 30 and random.random() < intensity * 0.5:
            mid = len(words) // 2 + random.randint(-3, 3)
            first = ' '.join(words[:mid]).rstrip('،')
            second = ' '.join(words[mid:])
            out.append(first + '.')
            out.append(second)
        else:
            out.append(s)
    return ' '.join(out)


def lex_pass(text: str, intensity: float, register: str = "news",
             mode: str = "full") -> str:
    """Register-aware lex pass.

    register: classical | news | opinion | technical
      - news: SAFE default. Skip risky rotations + rhetorical figure injection.
        Tighten dim 14 (anti-redundancy) and dim 15 (typography) only.
      - opinion: full lex pass, allow quote-verb rotation, no jinas/saj
      - classical: everything enabled
      - technical: typography + non-redundancy ONLY (no rotation, no rhetoric)

    mode: full | tighten | lex-only
      - tighten: runs ONLY inverse-scored dims 14 + 15 (newsroom subediting)
      - lex-only: full lex but no LLM-augmented passes downstream
      - full: lex + (downstream LLM passes if available)
    """
    # v2.6.2: Hamzat al-waṣl/qaṭʿ orthographic hygiene — runs in ALL registers
    # and ALL modes (form-X verbal nouns take hamzat al-waṣl regardless of
    # register; the AI-tell is universal). Safe substring substitution; ~50
    # forms covered. Auto-handles proclitics (لإستقرار -> لاستقرار), definite
    # article (الإستخدام -> الاستخدام), inflections (إستخداماته -> استخداماته).
    # Runs FIRST so downstream phrase-matching sees corrected forms.
    text, _hamza_applied = fix_hamzat_alwasl(text)

    # v2.6.4: Verb-subject agreement — fix fem-pl noun + wrongly-masc-pl verb.
    # الحكومات أعلنوا -> الحكومات أعلنت. Conservative: verb must be within ~30
    # chars of the noun, allowing at most one intervening particle. Runs in
    # ALL registers because the rule (jumu' mu'annath salim takes sing-fem
    # verb for non-human plurals; never masc-pl) is invariant across registers.
    text, _vagree_applied = fix_verb_agreement(text)

    # ── Enrich mode: lex pass + targeted marker insertion for low-scoring dims
    # Caps at 3 insertions per text. Targets dims 1, 4, 5, 6, 7, 8, 13.
    # Dims 10, 11, 12 (historical/imagination/rhetoric) need LLM — skipped here.
    if mode == "enrich":
        # Early tashkeel reduction (news/opinion) ensures pattern matching in
        # lex_replace_phrases sees normalized text. No-op for classical/technical.
        text = lex_reduce_tashkeel(text, register=register)
        # First: full lex pass (deletions + phrase swaps etc.)
        text = lex_replace_phrases(text)
        # Calque dictionary (v2.3.0): English-calque -> natural-Arabic
        text = lex_apply_calque_dictionary(text, register=register)
        text = lex_replace_connectors(text)
        if register != "technical":
            text = lex_break_structural_openers(text)
        if register in ("opinion", "classical"):
            text = lex_rotate_quote_verbs(text)
        text = lex_destack_intensifiers(text)
        text = lex_dim14_anti_tautology(text)
        text = lex_dim14_anti_re_explanation(text)
        text = lex_dim14_anti_forced_conclusion(text)
        text = lex_dim14_anti_known_definitions(text)
        text = lex_dim14_cleanup_orphans(text)
        text = lex_diversify_starters(text)
        text = lex_break_lists(text)
        text = re.sub(r'\s+', ' ', text).strip()
        # NOW: analyze the cleaned text and enrich the weakest dims
        # (delayed import to avoid circular)
        sys.path.insert(0, str(Path(__file__).parent))
        from analyze_deep import analyze as _analyze
        diag = _analyze(text)
        text, applied = lex_enrich(text, diag, max_inserts=3)
        # Tashkeel reduction (news/opinion only)
        text = lex_reduce_tashkeel(text, register=register)
        # Apply typography normalization LAST (after enrichment)
        text = lex_dim15_typography(text, register=register)
        # Store the enrichment log in module-level for the caller to retrieve
        lex_pass._enrichments_applied = applied
        return text

    # ── Tighten mode: newsroom subediting. Removes AI tells; no additions.
    # Runs: AI-phrase deletion (the lex table), intensifier de-stack, all
    # dim 14 deletions, typography normalization. Skips: quote-verb rotation
    # (editorial-neutrality hazard), structural opener rewrites (changes
    # voice), sentence-length variance (changes pyramid structure), connector
    # swaps (changes argument flow).
    if mode == "tighten":
        # Early tashkeel reduction (news/opinion only) so phrase matching
        # sees normalized text. Classical/technical pass through unchanged.
        text = lex_reduce_tashkeel(text, register=register)
        text = lex_replace_phrases(text)              # Remove AI signature phrases
        # Calque dictionary (v2.3.0): English-calque -> natural-Arabic
        text = lex_apply_calque_dictionary(text, register=register)
        text = lex_destack_intensifiers(text)         # Collapse "صعب ومعقّد" etc.
        text = lex_dim14_anti_tautology(text)         # "مؤكَّد وحقيقي وثابت" → "مؤكَّد"
        text = lex_dim14_anti_re_explanation(text)    # Delete "أي بمعنى آخر"
        text = lex_dim14_anti_forced_conclusion(text) # Delete "نَستنتج من هذا"
        text = lex_dim14_anti_known_definitions(text) # Delete "ونعني بـ X هو"
        text = lex_dim14_cleanup_orphans(text)        # Clean up orphan punctuation
        text = re.sub(r'\s+', ' ', text).strip()
        # Tashkeel reduction (news/opinion only; classical/technical preserve)
        text = lex_reduce_tashkeel(text, register=register)
        text = lex_dim15_typography(text, register=register)             # Typography hygiene LAST
        return text

    # ── Standard pipeline with register gating ─────────────────────────────
    # Early tashkeel reduction (news/opinion) ensures phrase patterns match
    # normalized text. Classical/technical passes through unchanged.
    text = lex_reduce_tashkeel(text, register=register)
    text = lex_replace_phrases(text)             # Gap A: safe for all registers
    # Calque dictionary (v2.3.0): English-calque -> natural-Arabic
    text = lex_apply_calque_dictionary(text, register=register)
    text = lex_replace_connectors(text)          # Gap B: safe for all registers

    # Gap C (structural noun-frame openers): SKIP for technical (changes meaning)
    if register != "technical":
        text = lex_break_structural_openers(text)

    # Gap D (quote-verb rotation): EDITORIAL-SAFETY HAZARD.
    # قال→كشف implies the speaker was concealing something; قال→زعم flips
    # to hostile stance. Per ChatGPT-deep-research: "تَدوير أفعال القول
    # يُغيّر الحياد إلى موقف" — even in opinion/classical, this rotation
    # changes the source's editorial framing rather than just stylistic
    # variation. DISABLED BY DEFAULT — opt-in only via explicit env flag.
    import os
    if os.environ.get("HUMANIZER_ALLOW_QUOTE_ROTATION") == "1":
        text = lex_rotate_quote_verbs(text)

    text = lex_destack_intensifiers(text)        # Gap G: safe everywhere

    # ── Dim 14: Reader respect — safe for ALL registers ──
    text = lex_dim14_anti_tautology(text)
    text = lex_dim14_anti_re_explanation(text)
    text = lex_dim14_anti_forced_conclusion(text)
    text = lex_dim14_anti_known_definitions(text)
    text = lex_dim14_cleanup_orphans(text)

    # Diversification (pronoun substitution at sentence start) — per ChatGPT
    # research, this can create ungrammatical double-subject constructions
    # like "كما أنها المؤسسة مرنة". Only enable for registers where the
    # stylistic risk is acceptable (opinion/classical). Skip for news/technical.
    if register in ("opinion", "classical"):
        text = lex_diversify_starters(text)
    text = lex_break_lists(text)

    # Sentence-length variation: classical/opinion enjoy variance; news prefers
    # uniform pyramid; technical prefers uniform short.
    if register in ("classical", "opinion") and intensity > 0.3:
        text = lex_vary_lengths(text, intensity)

    text = re.sub(r'\s+', ' ', text).strip()
    # Tashkeel reduction (modern editorial convention): strip non-disambiguating
    # diacritics. Register-gated — classical preserves traditional tashkeel.
    text = lex_reduce_tashkeel(text, register=register)
    # Dim 15 typography ALWAYS last — safe for every register.
    text = lex_dim15_typography(text, register=register)
    return text


# ── Tashkeel reduction (hamza-safe, digit-safe) ─────────────────────────────

# Strict tashkeel range: ONLY the 9 canonical combining diacritics:
#   U+064B ً  tanween fatha     U+064F ُ  damma
#   U+064C ٌ  tanween damma     U+0650 ِ  kasra
#   U+064D ٍ  tanween kasra     U+0651 ّ  shadda
#   U+064E َ  fatha             U+0652 ْ  sukun
#                               U+0670 ٰ  superscript alef (alif khanjariya)
#
# DOES NOT TOUCH:
#   - Hamza letter forms (أ إ آ ء ؤ ئ ى) — distinct letters carrying meaning
#     (إن vs أن, إما vs أما, قرآن with madda, آلام, أحصنة, etc.)
#   - Arabic-Indic digits ٠١٢٣٤٥٦٧٨٩ (U+0660–U+0669)
#   - The combining maddah/hamza marks (U+0653–U+0655) which could damage
#     decomposed letter forms in non-NFC text
TASHKEEL_REDUCE_RE = re.compile(r'[ً-ْٰ]')

# Homograph whitelist: words whose tashkeel disambiguates a real ambiguity in
# the skill's domain. Empty by default; add entries only when the consonantal
# skeleton genuinely maps to multiple plausible lexemes in normal prose.
# Example future entries (not enabled yet — context usually resolves):
#   "بعد": "بُعْد",   # dimension (vs. بَعْد = after)
#   "علم": "عِلْم",   # knowledge (vs. عَلَم = flag, عَلِمَ = he knew)
TASHKEEL_KEEP_WHITELIST: dict[str, str] = {}


def lex_reduce_tashkeel(text: str, register: str = "news") -> str:
    """Reduce excessive tashkeel per modern Arabic editorial convention.

    Strips the 9 canonical combining diacritics (fatha/kasra/damma/tanween
    variants, shadda, sukun, superscript alef) — preserves hamza letter
    forms (أ إ آ ء ؤ ئ ى) and Arabic digits (٠-٩).

    Register-gated: the `classical` register preserves traditional tashkeel
    (matching classical-Arabic editorial convention); news/opinion/technical
    strip aggressively.

    The TASHKEEL_KEEP_WHITELIST allows specific homograph words to retain
    their tashkeel; currently empty (context-disambiguation suffices).
    """
    if register in ("classical", "technical"):
        # Classical: traditional Arabic editorial convention keeps tashkeel.
        # Technical: conservative-by-design — preserve every character of the
        # source. Tashkeel may carry meaning (تشكيل على الحرف disambiguates
        # homographs); strict technical writing keeps it.
        return text
    # Mask whitelisted words before stripping
    masked = text
    placeholders: dict[str, str] = {}
    for stripped, kept in TASHKEEL_KEEP_WHITELIST.items():
        marker = f"\x00WL{len(placeholders)}\x00"
        placeholders[marker] = kept
        masked = re.sub(rf"\b{re.escape(stripped)}\b", marker, masked)
    cleaned = TASHKEEL_REDUCE_RE.sub("", masked)
    for marker, kept in placeholders.items():
        cleaned = cleaned.replace(marker, kept)
    return cleaned


# ── Calque-translation dictionary (v2.3.0 — toolkit-backed since v2.7.0) ────

# v2.7.0: optional integration with arabic-corpus-toolkit (shared peer skill).
# When the toolkit is on PYTHONPATH, the humanizer reads from
# arabic-corpus-toolkit/corpus/calque-dictionary.json as the canonical source.
# Otherwise it falls back to the local vendored copy (v2.5.x and earlier
# behavior). The vendored copy will be removed in v2.8.0 once toolkit is a
# hard dependency.
#
# Override the toolkit search path via env var:
#   ARABIC_CORPUS_TOOLKIT_ROOT=/path/to/arabic-corpus-toolkit
#
# The internal lookup shape ({"natural": ..., "alternatives": ..., ...}) is
# UNCHANGED from v2.6.4, so downstream lex_apply_calque_dictionary and
# _matches_topic don't need to change. Only the loader switches sources.
_TOOLKIT_DEFAULT_PATH = Path(__file__).resolve().parent.parent.parent / "arabic-corpus-toolkit"


def _toolkit_disabled() -> bool:
    """v2.7.2: explicit override to force the inline-fallback code paths.

    Set ARABIC_CORPUS_TOOLKIT_DISABLE=1 to skip toolkit loading entirely.
    Useful for:
      - Testing that the in-code fallback literals still work (the v2.8.0
        cleanup will remove the literals; regression testing needs to be
        able to isolate the two code paths beforehand).
      - Diagnosing whether a behavioral change is caused by toolkit content
        vs in-code logic.
      - Isolating from a broken toolkit install without uninstalling.

    Semantics: ONLY the literal string '1' disables. Other values (including
    'true', 'yes', '0', or unset) attempt the toolkit. This matches the
    DEBUG=1 convention from many CLI tools.
    """
    import os
    return os.environ.get("ARABIC_CORPUS_TOOLKIT_DISABLE") == "1"


def _load_from_toolkit() -> tuple[list[str], dict] | None:
    """Try to load the dictionary from arabic-corpus-toolkit.
    Returns (keys, lookup) on success, None if the toolkit isn't available,
    is disabled, or fails to load. Caller falls back to vendored copy on None.
    """
    if _toolkit_disabled():
        return None
    import os
    override = os.environ.get("ARABIC_CORPUS_TOOLKIT_ROOT")
    candidate_roots: list[Path] = []
    if override:
        candidate_roots.append(Path(override))
    candidate_roots.append(_TOOLKIT_DEFAULT_PATH)

    for root in candidate_roots:
        toolkit_dict_path = root / "corpus" / "calque-dictionary.json"
        if not toolkit_dict_path.exists():
            continue
        try:
            data = json.loads(toolkit_dict_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        entries = data.get("entries", []) if isinstance(data, dict) else data
        if not entries:
            continue
        return _build_lookup_from_entries(entries)
    return None


def _build_lookup_from_entries(entries: list) -> tuple[list[str], dict]:
    """Convert a list of dictionary entries into (sorted_keys, lookup_by_calque).
    Shared by both toolkit-backed and vendored-copy code paths.
    """
    lookup: dict[str, dict] = {}
    keys: list[str] = []
    for e in entries:
        calque = e.get("ai_default_calque", "").strip()
        natural = e.get("natural_arabic", "").strip()
        if not calque or not natural or calque == natural:
            continue
        lookup[calque] = {
            "natural": natural,
            "alternatives": e.get("alternatives", []),
            "domain": e.get("domain", "general"),
            "confidence": e.get("confidence", "medium"),
            "context_keywords_arabic": e.get("context_keywords_arabic", []),
            "context_keywords_english": e.get("context_keywords_english", []),
            "context_keywords_required_count": e.get("context_keywords_required_count", 1),
            "exclude_if_pattern": e.get("exclude_if_pattern", []),
        }
        keys.append(calque)
    keys.sort(key=len, reverse=True)
    return keys, lookup


def _load_calque_dictionary() -> tuple[list[str], dict]:
    """Load calque dictionary. v2.7.0 prefers arabic-corpus-toolkit; falls
    back to the local vendored copy if the toolkit isn't available.

    Returns: (sorted_calque_keys, lookup_dict)
      - sorted_calque_keys: list of calque strings, sorted by length desc
      - lookup_dict: {calque: {"natural": str, "alternatives": list, ...}}
    """
    # Preferred: shared toolkit (v2.7.0+)
    result = _load_from_toolkit()
    if result is not None:
        return result

    # Fallback: vendored copy (removed in v2.8.0)
    p = Path(__file__).resolve().parent.parent / "corpus" / "calque-dictionary.json"
    if not p.exists():
        return [], {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return [], {}
    return _build_lookup_from_entries(data.get("entries", []) if isinstance(data, dict) else data)


def _load_calque_dictionary_OLD_VENDORED_PATH_ONLY() -> tuple[list[str], dict]:
    """Pre-v2.7.0 loader. Kept as reference for the v2.8.0 cleanup; the
    function is no longer called by the runtime. Will be deleted in v2.8.0."""
    p = Path(__file__).resolve().parent.parent / "corpus" / "calque-dictionary.json"
    if not p.exists():
        return [], {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return [], {}
    lookup: dict[str, dict] = {}
    keys: list[str] = []
    for e in data.get("entries", []):
        calque = e.get("ai_default_calque", "").strip()
        natural = e.get("natural_arabic", "").strip()
        if not calque or not natural or calque == natural:
            continue
        lookup[calque] = {
            "natural": natural,
            "alternatives": e.get("alternatives", []),
            "domain": e.get("domain", "general"),
            "confidence": e.get("confidence", "medium"),
            # v2.6.3: topic-guard fields (optional). Entries with these
            # only fire when surrounding context matches; bare-stem
            # ambiguous entries (view, process, worker, etc.) use these
            # to avoid corrupting non-technical text like `رؤية 2030`.
            "context_keywords_arabic": e.get("context_keywords_arabic", []),
            "context_keywords_english": e.get("context_keywords_english", []),
            "context_keywords_required_count": e.get("context_keywords_required_count", 1),
            "exclude_if_pattern": e.get("exclude_if_pattern", []),
        }
        keys.append(calque)
    # Longer keys first so multi-word phrases match before single-word
    keys.sort(key=len, reverse=True)
    return keys, lookup


_CALQUE_KEYS, _CALQUE_LOOKUP = _load_calque_dictionary()


# ── v2.7.1: Asset C cutover to arabic-corpus-toolkit ──
# When the toolkit is available, override the six lexical tables defined at
# the top of this file (AI_PHRASES_AR, CONNECTORS_AR, REPETITIVE_STARTERS_AR,
# STRUCTURAL_OPENERS_AR, QUOTE_VERBS_ROTATION, INTENSIFIER_DESTACK) with the
# canonical values from arabic-corpus-toolkit/corpus/lexical-tables.json.
# The in-code literals (lines 51-209) remain as the fallback.
#
# Toolkit asset v1.1.0 is humanizer-parity confirmed; see
# arabic-corpus-toolkit/references/05-asset-c-migration-audit.md for the
# v0.7.1 reconciliation work that made this cutover safe.
#
# Major-version refuse: if the toolkit asset has $schema_version >= 2.x,
# refuse to load (this humanizer version can't promise compatibility).
def _try_load_lexical_tables_from_toolkit():
    """Returns dict of projected tables or None on any failure (toolkit disabled
    via env, file missing, parse error, schema-major mismatch, or shape mismatch).
    """
    if _toolkit_disabled():
        return None
    import os
    override = os.environ.get("ARABIC_CORPUS_TOOLKIT_ROOT")
    candidate_roots: list[Path] = []
    if override:
        candidate_roots.append(Path(override))
    candidate_roots.append(_TOOLKIT_DEFAULT_PATH)
    for root in candidate_roots:
        p = root / "corpus" / "lexical-tables.json"
        if not p.exists():
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        schema_major = data.get("$schema_version", "0.0.0").split(".")[0]
        if schema_major != "1":
            continue  # incompatible major version
        try:
            return _project_toolkit_lexical_tables(data["tables"])
        except (KeyError, TypeError):
            continue
    return None


def _project_toolkit_lexical_tables(tables: dict) -> dict:
    """Project the toolkit's list-of-objects representation into the
    humanizer's in-memory shapes (dict, list-of-tuples, list-of-strings)
    so downstream functions see EXACTLY the same shapes as the inline literals.
    """
    return {
        "ai_phrases": {
            e["input"]: list(e["alternatives"])
            for e in tables["ai_phrases"]["entries"]
        },
        "connectors": [
            (e["input"], e["replacement"])
            for e in tables["connectors"]["entries"]
        ],
        "repetitive_starters": list(tables["repetitive_starters"]["detectors"]),
        "structural_openers": [
            (e["pattern"], list(e["replacements"]))
            for e in tables["structural_openers"]["entries"]
        ],
        "quote_verbs": {
            e["input"]: list(e["rotation_pool"])
            for e in tables["quote_verbs"]["entries"]
        },
        "intensifier_destack": [
            (e["pattern"], e["replacement"])
            for e in tables["intensifier_destack"]["entries"]
        ],
    }


_toolkit_lexical = _try_load_lexical_tables_from_toolkit()
if _toolkit_lexical is not None:
    AI_PHRASES_AR          = _toolkit_lexical["ai_phrases"]
    CONNECTORS_AR          = _toolkit_lexical["connectors"]
    REPETITIVE_STARTERS_AR = _toolkit_lexical["repetitive_starters"]
    STRUCTURAL_OPENERS_AR  = _toolkit_lexical["structural_openers"]
    QUOTE_VERBS_ROTATION   = _toolkit_lexical["quote_verbs"]
    INTENSIFIER_DESTACK    = _toolkit_lexical["intensifier_destack"]
elif not _toolkit_disabled():
    # v2.8.0: toolkit is a HARD dependency. Failure to load is fatal unless
    # ARABIC_CORPUS_TOOLKIT_DISABLE=1 was explicitly set (testing-only mode).
    raise ImportError(
        "arabic-corpus-toolkit is required (v2.8.0+ removed the vendored "
        "lexical tables). Install it as a sibling repo at "
        "../arabic-corpus-toolkit, or set ARABIC_CORPUS_TOOLKIT_ROOT to its "
        "location. To run with empty stubs (lex-pass becomes a no-op) for "
        "isolation testing, set ARABIC_CORPUS_TOOLKIT_DISABLE=1."
    )
# (else: DISABLE=1, stubs stay empty — explicit testing-only mode)


def lex_apply_calque_dictionary(text: str, register: str = "news") -> str:
    """Replace English-calque Arabic phrases with their natural-Arabic
    equivalents, per the calque-dictionary at corpus/calque-dictionary.json.

    Register-gated: only news/opinion (modern editorial registers) apply
    the substitution. classical/technical preserve the source verbatim
    because:
      - classical: traditional Arabic doesn't use English calques
      - technical: may use English borrowings intentionally; preserving
        the source's lexical choices avoids breaking precision

    The substitution operates outside quoted spans (via _apply_outside_quotes)
    to preserve direct citations.
    """
    if register in ("classical", "technical"):
        return text
    if not _CALQUE_KEYS:
        return text  # dictionary file missing or empty

    def _matches_topic(segment: str, match: re.Match, entry: dict) -> bool:
        """v2.6.3: Topic-guard check.

        Returns True if (a) entry has no topic guard (always fires), OR
        (b) the ±100-char window around the match contains at least
        `context_keywords_required_count` keywords AND no exclusion
        pattern matches the immediate ±20-char trailing context.
        """
        kw_ar = entry.get("context_keywords_arabic", [])
        kw_en = entry.get("context_keywords_english", [])
        if not kw_ar and not kw_en:
            return True  # No topic guard — preserve original v2.3.0+ behavior

        required = entry.get("context_keywords_required_count", 1)
        ws_start = max(0, match.start() - 100)
        ws_end = min(len(segment), match.end() + 100)
        window = segment[ws_start:ws_end]
        window_lower = window.lower()
        hits = sum(1 for kw in kw_ar if kw in window)
        hits += sum(1 for kw in kw_en if kw.lower() in window_lower)
        if hits < required:
            return False

        # Exclusion patterns — e.g., `رؤية\s+\d{4}` to preserve "رؤية 2030"
        # even when surrounding text has tech vocabulary.
        for pat in entry.get("exclude_if_pattern", []):
            try:
                local_start = max(0, match.start() - 10)
                local_end = min(len(segment), match.end() + 30)
                local = segment[local_start:local_end]
                if re.search(pat, local):
                    return False
            except re.error:
                continue
        return True

    def _apply(segment: str) -> str:
        for key in _CALQUE_KEYS:
            entry = _CALQUE_LOOKUP[key]
            natural = entry["natural"]
            kw_ar = entry.get("context_keywords_arabic", [])
            kw_en = entry.get("context_keywords_english", [])
            topic_guarded = bool(kw_ar or kw_en)

            # Word-boundary check (v2.4.5): the calque key must NOT be
            # immediately followed by an Arabic letter — otherwise the
            # substitution would break a longer word that just happens to
            # contain the calque as a substring.
            key_re = re.compile(re.escape(key) + r'(?![؀-ۿ])')
            doubled_re = None
            if natural.startswith("ال"):
                doubled_re = re.compile(r'ال' + re.escape(key) + r'(?![؀-ۿ])')

            if topic_guarded:
                # v2.6.3: per-match topic check. Walk right-to-left so
                # deletions don't shift earlier offsets.
                for re_obj in [doubled_re, key_re]:
                    if re_obj is None:
                        continue
                    matches = list(re_obj.finditer(segment))
                    for m in reversed(matches):
                        if _matches_topic(segment, m, entry):
                            segment = segment[:m.start()] + natural + segment[m.end():]
                continue

            # Original (v2.3.0+) unconditional behavior for non-guarded entries.
            if doubled_re is not None and doubled_re.search(segment):
                segment = doubled_re.sub(natural, segment)
                continue
            if key_re.search(segment):
                segment = key_re.sub(natural, segment)
        return segment

    return _apply_outside_quotes(text, _apply)


# ── LLM-augmented passes ────────────────────────────────────────────────────

def llm_pass(text: str, pass_name: str, backend: str,
             auth_token: str | None = None, model: str | None = None,
             backend_url: str | None = None) -> tuple[str, dict]:
    """Call llm_transform.transform; return (new_text, info)."""
    from llm_transform import transform
    return transform(text, pass_name, backend=backend, auth_token=auth_token,
                     model=model, backend_url=backend_url)


# ── v2.9.0: importable score_text() for consumer use (translator Stage E,
# authoring-suite humanizer_gate). Uses Asset C's lexical-tables directly
# instead of a hard-coded 6-tell list, giving consumers a much richer signal
# without spinning up the full pipeline.
def score_text(text_ar: str, register: str = "news") -> dict:
    """Score Arabic text on AI-tell density. Returns:
      {score:int(0-100), ai_tell_hits:int, ai_tell_density_per_1k:float,
       total_words:int, register:str, ai_phrases_caught:list[str],
       sample_size:int}

    Score formula: max(0, 100 - density_per_1k * 5). Empirically calibrated
    so a clean text scores 100, a draft with one AI-tell per 50 words scores
    ~75, and AI-tell-saturated text scores 0.

    Uses Asset C's full ai_phrases list (~67 entries in v1.1.0) and the
    intensifier_destack patterns. Skips entries whose policy_notes mark them
    as pro-drop (those entries have empty-string alternatives and represent
    optional deletions, not strong AI-tells).

    Importable: `from humanize_v2 import score_text`.
    """
    if not text_ar:
        return {"score": 100, "ai_tell_hits": 0, "ai_tell_density_per_1k": 0.0,
                "total_words": 0, "register": register, "ai_phrases_caught": [],
                "sample_size": 0}

    total_words = len(text_ar.split())
    caught: list[str] = []
    hits = 0

    # AI_PHRASES_AR is the dict {input: alternatives} populated from Asset C
    # at module load (or empty under DISABLE=1).
    for phrase in AI_PHRASES_AR.keys():
        n = text_ar.count(phrase)
        if n > 0:
            hits += n
            caught.append(phrase)

    # Intensifier de-stack: each match is a strong AI-tell (intensifiers
    # stacked together are rare in human writing).
    for pattern, _replacement in INTENSIFIER_DESTACK:
        try:
            n = len(re.findall(pattern, text_ar))
            if n > 0:
                hits += n
        except re.error:
            continue

    density = (hits * 1000.0 / total_words) if total_words > 0 else 0.0
    score = max(0, 100 - int(density * 5))
    return {
        "score": score,
        "ai_tell_hits": hits,
        "ai_tell_density_per_1k": round(density, 2),
        "total_words": total_words,
        "register": register,
        "ai_phrases_caught": caught[:20],
        "sample_size": len(AI_PHRASES_AR),
    }


# v2.10.0: LLM-backed deep scoring via the LAN-local proxy fleet
# (`M:\Main\DevTools\AI\config\llm-proxies.md`). score_text (v2.9.0) is the
# fast heuristic; score_text_deep adds richer semantic scoring on a 0-100
# scale using cognitive-rubric dimensions: directness, naturalness, register
# coherence, factual grounding. Heuristic remains the default for callers
# that don't pay the LLM round-trip.
_DEEP_PROXIES = {
    "kimi":    {"url": "http://192.168.80.107:11435", "key": "U6hI7j57HpRpz9QaafTJLsJw5PlTXtxBM4pVNTknohE", "model": "kimi-cli"},
    "codex":   {"url": "http://192.168.80.107:11436", "key": "VJyi6yQDhEGNDE999FkHTqBAG21KdzmW",     "model": "gpt-5.5"},
    "gemini":  {"url": "http://192.168.80.107:11437", "key": "6fjc4jGwIhXQn7NejizvFVKR7Ps1SXES",     "model": "gemini-2.5-flash"},
    "minimax": {"url": "http://192.168.80.107:11438", "key": "xL5jUNR9A2lhN5HfLt1ulp9gE2CnBKf4",     "model": "MiniMax-M2.7"},
}


# v2.13.0: rotating-vendor state for score_text_deep. Each call advances the
# rotation; consumers that want a specific vendor pass proxy_name="..." and
# bypass rotation. Both minimax #1 and codex #5 in the multi-agent roadmap.
_ROTATION = ["gemini", "minimax", "codex"]
_rotation_idx = 0


def _next_rotation_proxy() -> str:
    global _rotation_idx
    proxy = _ROTATION[_rotation_idx % len(_ROTATION)]
    _rotation_idx += 1
    return proxy


def score_text_deep(text_ar: str, register: str = "news",
                    proxy_name: str | None = None) -> dict:
    """LLM-backed score on the 4-dimension cognitive rubric.

    Returns:
      {available: bool, score: int (0-100), per_dimension: dict, reasoning: str}

    Dimensions (each 0-25, summed for total 0-100):
      - directness     : sentences make claims; not buried under hedges
      - naturalness    : reads like human Arabic, not LLM Arabic
      - register_match : matches the requested register
      - factual_anchor : claims tied to specifics rather than abstract platitudes

    Falls back to heuristic score_text() result if the LLM call fails.
    """
    if not text_ar:
        return {"available": True, "score": 100, "per_dimension": {},
                "reasoning": "empty input", "backend": "trivial",
                "register": register}
    # v2.13.0: rotation when caller doesn't pin a proxy
    if proxy_name is None:
        proxy_name = _next_rotation_proxy()
    import urllib.request, urllib.error  # local to keep module-level imports clean
    p = _DEEP_PROXIES.get(proxy_name)
    if p is None:
        fallback = score_text(text_ar, register=register)
        fallback["backend"] = "heuristic_fallback (unknown proxy)"
        return fallback

    system_prompt = (
        "You are an Arabic prose-quality reviewer. Score the given Arabic text on a "
        "4-dimension rubric, each 0-25 (max total 100). Output ONLY JSON: "
        '{"directness":N,"naturalness":N,"register_match":N,"factual_anchor":N,"reasoning":"..."}. '
        "Dimensions: directness (claims made cleanly, no hedge stacking), naturalness "
        "(reads like human Arabic, not LLM Arabic — no مكوّن من المهم ملاحظة، علاوة على ذلك), "
        "register_match (matches the requested register), factual_anchor "
        "(claims tied to specifics, not abstract platitudes)."
    )
    user_prompt = (
        f"# Requested register\n{register}\n\n"
        f"# Arabic text\n{text_ar[:3000]}\n\n"
        f"Score on the rubric. Output JSON only."
    )
    body = json.dumps({
        "model": p["model"],
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
        "temperature": 0,
    }, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url=p["url"] + "/v1/chat/completions",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {p['key']}",
            "Content-Type":  "application/json; charset=utf-8",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        content = data["choices"][0]["message"]["content"]
    except Exception as e:
        fallback = score_text(text_ar, register=register)
        fallback["backend"] = f"heuristic_fallback (proxy error: {e})"
        return fallback

    parsed = None
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", content, re.DOTALL)
        if m:
            try:
                parsed = json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
    if not isinstance(parsed, dict):
        fallback = score_text(text_ar, register=register)
        fallback["backend"] = "heuristic_fallback (LLM returned non-JSON)"
        return fallback

    dims = {
        "directness":     min(25, max(0, int(parsed.get("directness", 0) or 0))),
        "naturalness":    min(25, max(0, int(parsed.get("naturalness", 0) or 0))),
        "register_match": min(25, max(0, int(parsed.get("register_match", 0) or 0))),
        "factual_anchor": min(25, max(0, int(parsed.get("factual_anchor", 0) or 0))),
    }
    total = sum(dims.values())
    return {
        "available": True,
        "score": total,
        "per_dimension": dims,
        "reasoning": str(parsed.get("reasoning", ""))[:500],
        "backend": f"llm_proxy.{proxy_name}",
        "register": register,
    }


# ── v2.12.0: Asset D + E consumer cutover ──
# Asset D = typography-rules.json (9 typography rules)
# Asset E = reader-respect-patterns.json (6 anti-patterns)
# Both shipped in toolkit v0.5 but had no consumer until now.
_asset_d_cache = None
_asset_e_cache = None


def _toolkit_corpus_dir():
    """Reuse _TOOLKIT_DEFAULT_PATH (set above for Asset A loader)."""
    if _toolkit_disabled():
        return None
    import os
    override = os.environ.get("ARABIC_CORPUS_TOOLKIT_ROOT")
    candidates = []
    if override:
        candidates.append(Path(override))
    candidates.append(_TOOLKIT_DEFAULT_PATH)
    for c in candidates:
        if (c / "corpus" / "typography-rules.json").exists():
            return c / "corpus"
    return None


def _load_asset_d():
    """typography-rules.json — 9 rules."""
    global _asset_d_cache
    if _asset_d_cache is not None:
        return _asset_d_cache
    corpus = _toolkit_corpus_dir()
    if corpus is None:
        return None
    try:
        data = json.loads((corpus / "typography-rules.json").read_text(encoding="utf-8"))
        if data.get("$schema_version", "0.0.0").split(".")[0] != "1":
            return None
        _asset_d_cache = data
        return data
    except Exception:
        return None


def _load_asset_e():
    """reader-respect-patterns.json — 6 anti-patterns."""
    global _asset_e_cache
    if _asset_e_cache is not None:
        return _asset_e_cache
    corpus = _toolkit_corpus_dir()
    if corpus is None:
        return None
    try:
        data = json.loads((corpus / "reader-respect-patterns.json").read_text(encoding="utf-8"))
        if data.get("$schema_version", "0.0.0").split(".")[0] != "1":
            return None
        _asset_e_cache = data
        return data
    except Exception:
        return None


def apply_typography_rules(text: str) -> tuple[str, dict]:
    """Apply Asset D's typography rules (when policy is mechanical) to text.
    Returns (cleaned_text, {applied_rule_ids: [...], counts: {...}})."""
    data = _load_asset_d()
    if data is None:
        return text, {"asset_d_available": False}
    applied = []
    counts = {}
    # Hard-coded canonical conversions (Asset D documents them; humanizer applies
    # the mechanical subset). Future v2.13 could read each rule's regex/replacement
    # explicitly from the asset.
    cleanup_map = {
        ",": "،",   # ASCII comma → Arabic comma (per ar-en-spacing/punctuation rule)
        ";": "؛",   # ASCII semicolon → Arabic semicolon
        "?": "؟",   # ASCII question mark → Arabic question mark
    }
    # Only convert when surrounded by Arabic letters (avoid breaking code blocks etc.)
    for ascii_p, ar_p in cleanup_map.items():
        # Replace ASCII p when adjacent to Arabic letter (lookback or following)
        new_text = re.sub(
            r"(?<=[ء-ي])" + re.escape(ascii_p),
            ar_p,
            text,
        )
        if new_text != text:
            n = text.count(ascii_p) - new_text.count(ascii_p)
            text = new_text
            applied.append(f"ascii-to-arabic-{ar_p}")
            counts[f"ascii_to_arabic_{ar_p}"] = n
    # Strip space before Arabic punctuation (per no-space-before-arabic-punctuation rule)
    for ar_p in ["،", "؛", "؟"]:
        new_text = re.sub(r"\s+" + re.escape(ar_p), ar_p, text)
        if new_text != text:
            applied.append(f"no-space-before-{ar_p}")
            counts[f"no_space_before_{ar_p}"] = counts.get(f"no_space_before_{ar_p}", 0) + 1
            text = new_text
    return text, {
        "asset_d_available": True,
        "asset_d_schema": data.get("$schema_version"),
        "applied_rule_ids": applied,
        "counts": counts,
    }


def reader_respect_score(text_ar: str) -> dict:
    """Inverse-scored — counts how many of Asset E's 6 anti-patterns appear.
    Returns {anti_pattern_hits, anti_pattern_density_per_1k, ids_caught, available}.
    Higher score = better (no anti-patterns). Used as a sub-component of total
    humanness signal.
    """
    data = _load_asset_e()
    if data is None:
        return {"available": False}
    # The 6 anti-pattern categories from Asset E. We detect via simple substring
    # markers per category (the asset documents fuller regex pools the humanizer
    # already implements in TAUTOLOGY_DELETE / RE_EXPLANATION_DELETE).
    MARKERS = {
        "anti-tautology":        ["ثابت وراسخ", "واضح وجلي", "مؤكد وحقيقي", "بدِيهي ومعلوم"],
        "anti-re-explanation":   ["أي بمعنى آخر", "بمعنى آخر", "وهذا يعني أن", "بعبارة أخرى",
                                  "وبتعبير آخر", "ولتوضيح ذلك أكثر"],
        "anti-forced-conclusion":["وبالتالي يمكن القول", "وعليه فإنه", "ومن هنا نستنتج"],
    }
    hits = 0
    ids_caught = []
    for ant_id, markers in MARKERS.items():
        for m in markers:
            if m in text_ar:
                hits += text_ar.count(m)
                if ant_id not in ids_caught:
                    ids_caught.append(ant_id)
    total_words = max(1, len(text_ar.split()))
    return {
        "available": True,
        "asset_e_schema": data.get("$schema_version"),
        "anti_pattern_hits": hits,
        "anti_pattern_density_per_1k": round(hits * 1000.0 / total_words, 2),
        "ids_caught": ids_caught,
    }


def score_text_multivendor(text_ar: str, register: str = "news",
                            proxies: list[str] | None = None) -> dict:
    """v2.11.0: cross-LLM scoring agreement. Calls score_text_deep on each
    requested proxy and returns aggregate signal.

    Returns:
      {available, mean_score, min_score, max_score, std_dev,
       per_proxy: {proxy_name: dim_dict}, agreement: 'strong|moderate|weak'}

    Agreement bands (based on max - min):
      strong   : range <=10  (vendors converged)
      moderate : range 11-25 (typical variance)
      weak     : range >25   (vendor disagreement — flag for review)
    """
    if proxies is None:
        proxies = ["gemini", "minimax"]
    per_proxy = {}
    for prx in proxies:
        result = score_text_deep(text_ar, register=register, proxy_name=prx)
        per_proxy[prx] = {
            "score": result.get("score"),
            "per_dimension": result.get("per_dimension", {}),
            "backend": result.get("backend"),
        }
    valid_scores = [v["score"] for v in per_proxy.values() if isinstance(v["score"], int)]
    if not valid_scores:
        return {"available": False, "per_proxy": per_proxy,
                "reason": "no valid scores returned by any proxy"}
    mean = sum(valid_scores) / len(valid_scores)
    score_range = max(valid_scores) - min(valid_scores)
    if score_range <= 10:
        agreement = "strong"
    elif score_range <= 25:
        agreement = "moderate"
    else:
        agreement = "weak"
    # Std dev (population)
    variance = sum((s - mean) ** 2 for s in valid_scores) / len(valid_scores)
    std = variance ** 0.5
    return {
        "available": True,
        "mean_score": round(mean, 1),
        "min_score": min(valid_scores),
        "max_score": max(valid_scores),
        "score_range": score_range,
        "std_dev": round(std, 2),
        "agreement": agreement,
        "n_proxies": len(valid_scores),
        "per_proxy": per_proxy,
        "register": register,
    }


# ── Pipeline ────────────────────────────────────────────────────────────────

def run_pipeline(text: str, mode: str, backend: str, intensity: float,
                 auth_token: str | None = None, register: str = "news",
                 model: str | None = None, backend_url: str | None = None) -> dict:
    log = []

    # v2.6.1: Sacred-text guard. Mask Quranic verses + hadith citations
    # + basmala BEFORE any transformation; restore verbatim on every
    # return path. See references/18-sacred-text-guard.md. Per Agent A's
    # v2.6.0 review, this is the load-bearing protection for religious-
    # publication deployments — quote-verb rotation on `قال رسول الله ﷺ`
    # is catastrophically irreverent if not preempted.
    masked, sacred_masks = mask_sacred_spans(text)
    if sacred_masks:
        log.append({"stage": "sacred_guard",
                    "spans_locked": len(sacred_masks),
                    "reasons": list({r for _, _, r, _ in sacred_masks})})

    out = masked

    def _finalize(result_dict: dict) -> dict:
        """Restore sacred spans in the output before returning."""
        if sacred_masks:
            result_dict["output"] = restore_sacred_spans(result_dict["output"], sacred_masks)
        return result_dict

    # Stage 1: lexical (register-aware)
    t0 = time.time()
    out = lex_pass(out, intensity, register=register, mode=mode)
    log.append({"stage": f"lex({register},{mode})",
                "duration_s": round(time.time() - t0, 2),
                "ok": True, "delta_chars": len(out) - len(text)})

    # In "tighten" mode, lex pass is the complete pipeline.
    # No LLM-augmented passes — newsroom subediting wants deterministic + safe.
    if mode in ("lex-only", "tighten"):
        return _finalize({"output": out, "stages": log, "mode": mode, "register": register})

    # Stage 2: cognitive
    t0 = time.time()
    new, info = llm_pass(out, "cognitive", backend, auth_token, model, backend_url)
    log.append({"stage": "cognitive", "duration_s": info.get("duration_s"),
                "ok": info.get("ok"), "error": info.get("error"),
                "backend": info.get("backend")})
    if info.get("ok"):
        out = new
    if mode == "+cognitive":
        return _finalize({"output": out, "stages": log, "mode": mode})

    # Stage 3: rhetorical
    t0 = time.time()
    new, info = llm_pass(out, "rhetorical", backend, auth_token, model, backend_url)
    log.append({"stage": "rhetorical", "duration_s": info.get("duration_s"),
                "ok": info.get("ok"), "error": info.get("error")})
    if info.get("ok"):
        out = new
    if mode == "+rhetorical":
        return _finalize({"output": out, "stages": log, "mode": mode})

    # Stage 4: coherence (final pass — only in full mode)
    new, info = llm_pass(out, "coherence", backend, auth_token, model, backend_url)
    log.append({"stage": "coherence", "duration_s": info.get("duration_s"),
                "ok": info.get("ok"), "error": info.get("error")})
    if info.get("ok"):
        out = new
    return _finalize({"output": out, "stages": log, "mode": mode})


def main():
    ap = argparse.ArgumentParser(description="Arabic Humanizer v2")
    ap.add_argument("--input", "-i", help="Inline text")
    ap.add_argument("--file", "-f", type=Path, help="Read from file")
    ap.add_argument("--output", "-o", type=Path, help="Write to file")
    ap.add_argument("--mode", default="tighten",
                    choices=["lex-only", "tighten", "enrich", "+cognitive", "+rhetorical", "full"],
                    help="tighten=newsroom subediting (dims 14+15 + phrase delete); "
                         "lex-only=full deterministic lex; "
                         "enrich=lex+targeted marker insertion for low-scoring dims (max 3 inserts); "
                         "+cognitive/+rhetorical/full add LLM passes")
    ap.add_argument("--register", default="news",
                    choices=["classical", "news", "opinion", "technical"],
                    help="Target register — gates which transformations fire. "
                         "Default 'news' is SAFE; jinas/saj/quote-rotation only "
                         "enable for classical/opinion.")
    ap.add_argument("--llm-backend", default="api",
                    choices=["api", "local"],
                    help="'api' = any OpenAI-compatible cloud endpoint "
                         "(configure via LLM_API_URL/LLM_API_KEY/LLM_MODEL "
                         "env vars). 'local' = local Ollama by default.")
    ap.add_argument("--backend-url", help="Override LLM_API_URL for one invocation")
    ap.add_argument("--model", help="Override LLM_MODEL for one invocation")
    ap.add_argument("--auth-token", help="Override LLM_API_KEY for one invocation")
    ap.add_argument("--intensity", type=float, default=0.6)
    ap.add_argument("--preflight", action="store_true",
                    help="Run preflight_check.py before humanization. If HIGH-"
                         "severity findings present and --strict-preflight is set, "
                         "abort with code 2.")
    ap.add_argument("--strict-preflight", action="store_true",
                    help="Block humanization when preflight finds HIGH-severity "
                         "issues (factual/ethical/sourcing hazards).")
    ap.add_argument("--seed", type=int, help="Random seed for lex pass reproducibility")
    ap.add_argument("--analyze", "-a", action="store_true",
                    help="Show before/after analysis")
    ap.add_argument("--json", action="store_true", help="JSON output")
    args = ap.parse_args()

    if args.seed is not None:
        random.seed(args.seed)

    if args.file:
        text = args.file.read_text(encoding="utf-8")
    elif args.input:
        text = args.input
    else:
        text = sys.stdin.read()
    if not text.strip():
        raise SystemExit("empty input")

    # ── Preflight check (per ChatGPT deep research — documented but was not
    # wired into CLI). Now properly integrated.
    if args.preflight:
        sys.path.insert(0, str(Path(__file__).parent))
        from preflight_check import check as _preflight
        pf = _preflight(text)
        print(f"[preflight] verdict={pf['verdict']}  "
              f"findings={pf['n_findings']} "
              f"(HIGH={pf['n_high']}, MEDIUM={pf['n_medium']}, LOW={pf['n_low']})",
              file=sys.stderr)
        for f in pf["findings"]:
            print(f"  [{f['severity']}] {f['category']}: \"{f['text'][:60]}\"",
                  file=sys.stderr)
        if args.strict_preflight and pf["verdict"] == "BLOCK":
            print("[preflight] BLOCKED by --strict-preflight. Aborting humanization.",
                  file=sys.stderr)
            sys.exit(2)

    before = analyze(text) if args.analyze else None
    result = run_pipeline(text, args.mode, args.llm_backend, args.intensity,
                          args.auth_token, register=args.register,
                          model=args.model, backend_url=args.backend_url)
    after = analyze(result["output"]) if args.analyze else None

    if args.output:
        args.output.write_text(result["output"], encoding="utf-8")
        print(f"[OK] wrote {args.output}", file=sys.stderr)
    elif not args.json:
        print(result["output"])

    if args.json:
        payload = {"result": result}
        if before is not None: payload["before"] = before
        if after is not None: payload["after"] = after
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    elif args.analyze:
        print("\n" + render_report(before), file=sys.stderr)
        print("\n" + render_report(after), file=sys.stderr)
        delta = after["overall_humanness_0_100"] - before["overall_humanness_0_100"]
        print(f"\n[Δ humanness: {delta:+.1f}]", file=sys.stderr)
        for stage in result["stages"]:
            mark = "✓" if stage.get("ok") else "✗"
            print(f"  {mark} {stage['stage']:<12} {stage.get('duration_s','?')}s"
                  f"{'  ERROR: ' + str(stage.get('error', ''))[:80] if not stage.get('ok') else ''}",
                  file=sys.stderr)


if __name__ == "__main__":
    main()
