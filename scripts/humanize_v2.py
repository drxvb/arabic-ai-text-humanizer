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

# Import the LLM wrapper lazily (only when --mode > lex-only)


# ── Inherited lexical patterns (Arabic only — see reference 13) ─────────────

AI_PHRASES_AR = {
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

CONNECTORS_AR = [
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

REPETITIVE_STARTERS_AR = [
    "تعتبر", "تُعتبر", "يُعتبر", "تعد", "يُعد", "تُعد",
    "يمكن", "تستطيع", "نستطيع", "يعتبر", "يعد",
]

# ── Gap C (from references/13): AI structural openers → active rephrasings ──
# Fix #5/bug-1 (comp-linguist): `\S+` doesn't span two-word compounds like
# "الذكاء الاصطناعي". Switched to `([ء-ي\s]{1,40}?)` — Arabic-letters-or-spaces,
# bounded length, lazy match, so "يلعب الذكاء الاصطناعي دوراً" now matches.
STRUCTURAL_OPENERS_AR = [
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
QUOTE_VERBS_ROTATION = {
    "قال":   ["أكّد", "أشار", "أوضح", "أضاف", "صرّح", "ذكر", "نوّه", "لفت"],
    "يقول":  ["يَرى", "يَعتقد", "يَزعم", "يُقرّر", "يُؤكّد"],
    "ذكر أن": ["أفاد بأنّ", "أشار إلى أنّ", "لفت إلى أنّ", "كشف أنّ"],
    "ذكر أنّ": ["أفاد بأنّ", "أشار إلى أنّ", "لفت إلى أنّ", "كشف أنّ"],
}

# ── Gap G (from references/13): redundant intensifier stacks ──
INTENSIFIER_DESTACK = [
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


# ── Calque-translation dictionary (v2.3.0) ──────────────────────────────────

def _load_calque_dictionary() -> tuple[list[str], dict]:
    """Load corpus/calque-dictionary.json at module init.

    The dictionary captures English-calque -> natural-Arabic translation
    pairs validated against the AITNews corpus (and multi-LLM swarm).
    Source-of-truth lives in the JSON file so it can be audited/extended
    without touching code.

    Returns: (sorted_calque_keys, lookup_dict)
      - sorted_calque_keys: list of calque strings, sorted by length desc
        (longer phrases match first to avoid partial overlaps)
      - lookup_dict: {calque: {"natural": str, "alternatives": list,
                               "domain": str, "confidence": str}}
    """
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
        }
        keys.append(calque)
    # Longer keys first so multi-word phrases match before single-word
    keys.sort(key=len, reverse=True)
    return keys, lookup


_CALQUE_KEYS, _CALQUE_LOOKUP = _load_calque_dictionary()


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

    def _apply(segment: str) -> str:
        for key in _CALQUE_KEYS:
            natural = _CALQUE_LOOKUP[key]["natural"]
            # Double-ال fix: if input has "ال" + calque (with definite article)
            # AND the natural form ALSO starts with "ال", substitute the
            # ال+calque sequence with the natural form to avoid "الال..."
            if natural.startswith("ال") and ("ال" + key) in segment:
                segment = segment.replace("ال" + key, natural)
                continue
            if key in segment:
                segment = segment.replace(key, natural)
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


# ── Pipeline ────────────────────────────────────────────────────────────────

def run_pipeline(text: str, mode: str, backend: str, intensity: float,
                 auth_token: str | None = None, register: str = "news",
                 model: str | None = None, backend_url: str | None = None) -> dict:
    log = []
    out = text

    # Stage 1: lexical (register-aware)
    t0 = time.time()
    out = lex_pass(out, intensity, register=register, mode=mode)
    log.append({"stage": f"lex({register},{mode})",
                "duration_s": round(time.time() - t0, 2),
                "ok": True, "delta_chars": len(out) - len(text)})

    # In "tighten" mode, lex pass is the complete pipeline.
    # No LLM-augmented passes — newsroom subediting wants deterministic + safe.
    if mode in ("lex-only", "tighten"):
        return {"output": out, "stages": log, "mode": mode, "register": register}

    # Stage 2: cognitive
    t0 = time.time()
    new, info = llm_pass(out, "cognitive", backend, auth_token, model, backend_url)
    log.append({"stage": "cognitive", "duration_s": info.get("duration_s"),
                "ok": info.get("ok"), "error": info.get("error"),
                "backend": info.get("backend")})
    if info.get("ok"):
        out = new
    if mode == "+cognitive":
        return {"output": out, "stages": log, "mode": mode}

    # Stage 3: rhetorical
    t0 = time.time()
    new, info = llm_pass(out, "rhetorical", backend, auth_token, model, backend_url)
    log.append({"stage": "rhetorical", "duration_s": info.get("duration_s"),
                "ok": info.get("ok"), "error": info.get("error")})
    if info.get("ok"):
        out = new
    if mode == "+rhetorical":
        return {"output": out, "stages": log, "mode": mode}

    # Stage 4: coherence (final pass — only in full mode)
    new, info = llm_pass(out, "coherence", backend, auth_token, model, backend_url)
    log.append({"stage": "coherence", "duration_s": info.get("duration_s"),
                "ok": info.get("ok"), "error": info.get("error")})
    if info.get("ok"):
        out = new
    return {"output": out, "stages": log, "mode": mode}


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
