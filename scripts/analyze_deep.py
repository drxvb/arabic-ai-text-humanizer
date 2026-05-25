#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Deep 13-dimension diagnostic analyzer for Arabic AI text.

Goes beyond the lighter lexical-only sibling analyzer. Scores each dimension
0-15 based on detectable diagnostic signals (NOT LLM-graded — deterministic
heuristics so the analyzer is repeatable and cheap).

Dimensions:
  1. الاستنتاج / Deduction
  2. الاستدلال / Inference
  3. الاستنباط / Specific inference
  4. التحليل البشري / Human analysis methods
  5. التدرج / Graduated explanation
  6. تحديد النطاق / Scope definition
  7. التنقل / Idea transitions
  8. التقسيم / Axes & data partitioning
  9. الفن الأدبي / Literary art
 10. الاستدلال التاريخي / Historical anchoring
 11. التخيل / Imagination & concretization
 12. البلاغة / Rhetorical figures
 13. عدم التكرار + الاستدلال الداخلي / Coherence + intra-text citation

Each dimension's score is a heuristic — diagnostic-only, not judge-quality.
Use score_humanness.py for before/after comparison.

Usage:
    python analyze_deep.py --input "نص" --report
    python analyze_deep.py --file in.txt --json
"""
from __future__ import annotations
import argparse, json, math, re, sys
from collections import Counter
from pathlib import Path

# math.log2 needed for Dim 16 Shannon entropy; already imported via `math`

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# ── Patterns per dimension (detectable in Arabic text) ──────────────────────

# Dim 1-3: Cognitive structure — reasoning markers
# Extended with corpus-frequent connectors that carry reasoning meaning
REASONING_MARKERS = [
    "إذ", "حيث", "بناءً عليه", "يستنتج من ذلك", "يلزم من هذا",
    "لأن", "بما أن", "بسبب", "لذلك", "ولأجل ذلك",
    "ومن هنا", "فإن", "نخلص إلى", "نستنتج",
    # corpus-grounded extensions (top connectors from empirical-patterns.json):
    "وقد",  # 605 — soft-asserted prior fact / argumentative bridge
    "إذا",  # 945 — conditional reasoning
    "حتى",  # 1072 — limit / extreme-case argument
    "بل",   # 809 — corrective reasoning ("rather...")
    "كما أن",        # parallel inference
    "ومن ثم",        # consequential
    "وهكذا",         # synthetic conclusion
    "ولذلك",         # consequent
    "فلهذا",         # consequent
    "ومن البديهي أن",
    "وعليه فإن",
    "يقتضي ذلك",
    "وقد ثبت",
    "فلا غرو أن",
]

# Dim 4: Human analysis — comparison/classification markers
ANALYSIS_MARKERS = [
    "مقارنة بـ", "بالمقارنة مع", "على عكس", "بخلاف", "ومن ناحية",
    "ينقسم إلى", "يتفرع", "ينتمي إلى", "يندرج تحت", "بينما",
    "في حين أن",
    # extensions:
    "في حين أنّ", "بالنظر إلى", "إذا قارنّا", "وفي مقابل ذلك",
    "ولا يقاس على", "والفرق بين", "أمّا", "وأما",
    "ومن وجه آخر", "ومن زاوية مغايرة",
]

# Dim 5: Graduated explanation — scaffolding markers
SCAFFOLD_MARKERS = [
    "بدايةً", "نبدأ بـ", "أولاً نتأمل", "ثم ننتقل إلى",
    "بعد أن أوضحنا", "والآن وقد", "وإذا توضح ذلك",
    "نمضي خطوة أبعد",
    # extensions:
    "نَستهلّ بـ", "وقبل الخوض في", "وَفي ضوء ما تقدّم",
    "وإذ قد تَوضّح", "ولكي يتّضح الأمر", "وَلنبدأ من الأبسط",
    "ثم نَرقى إلى", "وإذا انتهينا من ... فلننتقل إلى",
]

# Dim 6: Scope — boundary markers
SCOPE_MARKERS = [
    "في حدود ما يخص", "بمعزل عن", "دون الخوض في", "ولا نقصد هنا",
    "في حدود هذا البحث", "في نطاق", "يقتصر هذا على", "خارج إطار",
    # extensions:
    "ولا يَدخل في هذا", "بمعزل عن السؤال عن", "وفي حدود اهتمامنا",
    "ولسنا بصدد", "ولا نَطمح هنا إلى", "خارج نطاق هذا المقال",
    "وَنترك جانباً", "ولا يَتسع المقام",
]

# Dim 7: Transitions — sophisticated transition markers
TRANSITION_MARKERS = [
    "ومن جانب آخر", "ومن جهة أخرى",  # both common variants
    "بمعزل عن ذلك", "وعلى مفترق آخر",
    "وفي اتجاه مختلف", "ولا يفوتنا أن", "ومن زاوية مغايرة",
    # extensions:
    "ولعلّ من المفيد الانتقال إلى", "وَنَرى من المناسب",
    "وتحضرنا هنا فكرة أخرى", "ولا يَخفى ارتباط ذلك بـ",
    "وَلَستُ أَنسى", "وَهنا نقطة تستحقّ التأمل",
    "وفي مَوضعٍ آخر", "ومن جهةٍ أخرى",
    "وَأمّا الجانب الآخر", "وعلى نَحوٍ مغاير",
]

# Dim 8: Partitioning — axis markers
AXIS_MARKERS = [
    "المحور الأول", "المحور الثاني", "البعد الأول", "البعد الثاني",
    "ينقسم إلى", "ثلاثة وجوه", "أربع زوايا", "خمسة محاور",
    # extensions (corpus shows واما 1983 as sentence-initial; partitioning pattern):
    "أمّا الأول فـ", "أمّا الأول، ف",  # both common punctuation styles
    "أمّا الثاني فـ", "أمّا الثاني، ف",
    "أمّا الثالث فـ", "أمّا الثالث، ف",
    "أمّا الأول", "أمّا الثاني", "أمّا الثالث",  # bare forms
    "ومن وجه أوّل", "ومن وجه ثانٍ", "أحدهما", "والآخر",
    "ينقسم القول في هذا إلى",
    "أوّلاً", "ثانياً", "ثالثاً", "رابعاً",  # ordinal markers as partition signals
]

# Dim 9: Literary art — image / rhythm markers (heuristic via parallel structure)
# Detected via parallel-structure count + sentence-length variance (burstiness)

# Dim 10: Historical — history-referencing markers
HISTORICAL_MARKERS = [
    "في عصر", "في زمن", "إبان", "خلال حقبة", "في القرن",
    "في عهد", "في الأندلس", "في بغداد", "إذ كان العباسيون",
    "كما حدث في", "يذكرنا التاريخ", "ما حدث عام",
    "في زمن الفتنة", "في زمن النهضة",
    # extensions (5-analogy catalog per references/06-historical-anchoring.md):
    "كما شهدت الأندلس", "كما حدث في زمن الفتح",
    "كما رأينا في عصر الازدهار العباسي", "كما حلّ بالعالم الإسلامي مع المغول",
    "كما تشهد منطقتنا اليوم",
    "ولعلّ التاريخ يَعيد نفسه", "ولنا في الماضي عبرة", "ويذكّرنا هذا بـ",
    "كأنّنا في عصر", "إنّ التاريخ يُحدّثنا عن",
    # Historical-figure references (treating named classical scholars as anchors):
    "ابن خلدون", "ابن رشد", "ابن سينا", "الجاحظ", "الجرجاني", "الغزالي",
    "ابن تيمية", "ابن النفيس", "الفارابي", "الكندي",
    "كما ذكر ابن", "كما قال ابن", "ما ذَكَره ابن",
    "القرن السادس الهجري", "القرن الثامن عشر", "القرن التاسع عشر",
    "القرن العشرين", "في القرن الماضي", "في الحقبة",
]

# Dim 11: Imagination — sensory/metaphor markers (heuristic)
# Pronoun-suffix tolerance now in count_marker_safe handles كأنّنا / كأنّه etc.
SENSORY_MARKERS = [
    "وكأن", "كأن", "أشبه بـ", "يشبه", "يذكّر بـ", "تخيّل",
    "تصوّر", "كما لو", "صورة من", "مشهد",
    # extensions:
    "وَنَكاد نَسمع", "ويُخيَّل إلينا", "يبدو الأمر كأنّه",
    "صورة هذا أنّ", "ولو رأيت", "ولو تَأمّلت",
    "كَمن يقف على", "كَمَن يَنظر إلى", "والمشهد كأنّه",
    # Concrete-image / scene-setting markers:
    "نَهر يَجري", "كَنَهر", "كَطَير", "كالماء", "كالنار",
    "كَأَنّنا أَمام", "والصورة هي", "كَمَن",
]

# Dim 12: Rhetorical figures — heuristic detection
# جناس detection: sound-alike word pairs (approx via repeated 3-letter roots)
# طباق detection: antonym pairs (expanded with classical + modern oppositions)
ANTITHESIS_PAIRS = [
    # Classical pairs:
    ("ليل", "نهار"), ("شرق", "غرب"), ("حياة", "موت"),
    ("قوة", "ضعف"), ("علم", "جهل"), ("ظاهر", "باطن"),
    ("قديم", "حديث"), ("سلم", "حرب"), ("غنى", "فقر"),
    # Spatial / dimensional:
    ("صغير", "كبير"), ("قريب", "بعيد"), ("داخل", "خارج"),
    ("أعلى", "أسفل"), ("فوق", "تحت"),
    # Cognitive / philosophical:
    ("ثابت", "متغير"), ("مطلق", "نسبي"), ("معروف", "مجهول"),
    ("صدق", "كذب"), ("حق", "باطل"), ("خير", "شر"),
    # Modern / political / technological:
    ("تسارع", "تباطؤ"), ("التسارع", "التباطؤ"),
    ("انفتاح", "انغلاق"), ("الانفتاح", "الانغلاق"),
    ("تقدّم", "تأخّر"), ("التقدّم", "التأخّر"),
    ("نقل", "تحقيق"), ("النقل", "التحقيق"),  # Andalusian rhetoric anchor
    ("مندفع", "متردد"), ("مستقبل", "ماضي"),
    ("حركة", "سكون"), ("الحركة", "السكون"),
    ("ساكنة", "متدفقة"), ("الساكن", "المتدفق"),
    # Verb pairs:
    ("يَغرّه", "يُثنيه"),  # observed in real classical text
]

# Tashbeeh-by-prefix-kaf — كَ + noun is a common Arabic similitude marker
TASHBEEH_KAF_PATTERN = re.compile(
    r'(?<![ء-ي])كَ?[َـ]?'         # prefix kaf with optional fatha/tatweel
    r'(?:ال)?'                        # optional ال
    r'(?:نهر|طير|بحر|جبل|نار|ماء|ريح|شمس|قمر|نسيج|نَهر|طَير)'  # concrete image nouns
)

# Dim 13: Coherence — intra-text citation markers
CITATION_MARKERS = [
    "كما قدّمنا", "وفي ضوء ما تقدّم", "إذ سبق أن قلنا",
    "وقد أشرنا آنفاً", "كما أشرنا", "بناءً على ما أسلفنا",
    "ولعل القارئ يتذكر", "كما ذكرنا",
    # extensions (the 12-phrase catalog from references/09-coherence-non-repetition.md):
    "كما قدّمنا", "وقد قلنا", "ومرّ بنا", "كما تقدّم",
    "وفيما سبق رأينا", "ولعلّك تَذكر", "وهو ما أَلمحنا إليه",
    "وَقد جرى ذكره",
    "وَلْنُذَكِّر بـ", "وَلنَستحضر ما قلناه عن",
]

# Dim 14: Reader respect — NEGATIVE markers (their presence = WEAK on this dim)
# See references/14-reader-respect.md
OVER_EXPLANATION_MARKERS = [
    "أي بمعنى آخر", "بمعنى آخر", "وهذا يعني أن", "وهذا يعني أنّ",
    "أي أن", "أي أنّ", "بمعنى أنه", "بمعنى أنّه",
    "بعبارة أخرى", "وبتعبير آخر", "وبعبارة أوضح", "بعبارة أوضح",
    "ولتوضيح ذلك أكثر", "وحتى تتضح الفكرة", "وحتى تتّضح الفكرة",
    "ولزيادة الإيضاح", "ولكي يتّضح المعنى",
]

REDUNDANT_AFFIRMATION_MARKERS = [
    "وهذا أمر مؤكّد", "وهذا أمر مؤكد", "وهذا حقيقة",
    "بلا شك ولا ريب", "والأمر واضح وجلي", "والأمر واضح وجَلِيّ",
    "كما هو معلوم ومعروف", "وهذا واضح وجَلِيّ", "وهذا واضح وجلي",
    "وهذا أمر بديهي ومعلوم", "ولا يخفى على أحد",
    "مؤكّد وحقيقي وثابت", "حقيقي ومؤكّد", "ثابت وراسخ",
    "واقعي ومؤكّد", "ولا شك أنّ", "ولا ريب أنّ",
]

FORCED_CONCLUSION_MARKERS = [
    "نستنتج من هذا أن", "نَستنتج من هذا أنّ", "ونستنتج أن",
    "وهذا يدل على", "وهذا يَدلّ على",
    "ومن هنا نفهم أن", "ومن هنا نَفهم أنّ",
    "وعليه يتضح أن", "وعليه يَتّضح أنّ",
    "وهذا برهان قاطع على", "وهذا دليل قاطع على",
    "ومن الواضح إذن أن", "وبالتالي نَخلص إلى أنّ",
    "وعلى هذا فإنّ", "وَنَستنبط من ذلك أنّ",
]

KNOWN_TERM_DEFINITIONS = [
    "ونعني بـ", "والمقصود بـ", "والمقصود بِـ",
    "ونَقصد بـ", "وَيُعرَّف بأنّه", "ويُعرَّف بِأنّه",
    "ويَعني ذلك أن",
]

# ── Dim 16: الفصل والوصل (Junction-Disjunction) ──
# Distributional analysis — connector diversity via Shannon entropy.
# See references/16-fasl-wa-wasl.md
# Connectors with their conceptual roles. We measure the DISTRIBUTION,
# not presence, so the ordering is just for readability.
FASL_WASL_CONNECTORS = [
    "و", "فـ", "ثم", "بل", "لكن", "غير أن", "بيد أن",
    "أو", "أم", "حتى", "إذ", "إذا", "لما", "لأن", "كي",
    "كما", "حيث", "إن", "أن", "قد",
]

# ── Dim 15: Typography hygiene — mechanical issues, regex-detectable ──
# See references/15-typography-hygiene.md
AR_EN_ADJACENCY = re.compile(r'[؀-ۿ][A-Za-z]|[A-Za-z][؀-ۿ]')
LATIN_COMMA_IN_AR = re.compile(r'[؀-ۿ]\s*,\s*[؀-ۿ]')
LATIN_SEMICOLON_IN_AR = re.compile(r'[؀-ۿ]\s*;\s*[؀-ۿ]')
LATIN_QMARK_IN_AR = re.compile(r'[؀-ۿ][^.\n]{0,80}\?')  # ? after Arabic clause
# Punct directly followed by a non-space, non-digit-decimal, non-URL char:
PUNCT_NO_SPACE = re.compile(r'[،؛](?![\s$])')  # Arabic punct with no space
# Paren directly adjacent to a Latin letter (no space inside):
PAREN_EN_NO_SPACE = re.compile(r'\([A-Za-z]|[A-Za-z]\)')
# Mixed numbering styles in close proximity (within ~200 chars):
NUM_STYLE_PARENS = re.compile(r'(?:^|\n)\s*\(\d+\)')
NUM_STYLE_DOT    = re.compile(r'(?:^|\n)\s*\d+\.\s')
NUM_STYLE_DASH   = re.compile(r'(?:^|\n)\s*\d+-\s')


# ── Normalization helpers (Fix #1 from cross-LLM critique) ─────────────────
# The comp-linguist found that bare text.count() conflates إذ/إذا/إذن
# (substring matches inside the longer words). We need:
#   1. Diacritic-insensitive matching (يُعرَّف ≡ يعرف)
#   2. Word-boundary-aware matching (إذ NOT matched inside إذا)
#   3. Prefix-aware و detection (و in والكتاب counts as a connector)

_DIACRITICS_RE = re.compile(r'[ً-ٰٟۖ-ۭ]')  # all Arabic diacritics
_AR_LETTER_CLASS = r'[ء-يٱ-ۓ]'  # Arabic letters (excludes diacritics)


def _normalize_diacritics(s: str) -> str:
    """Strip Arabic diacritics. يُعرَّف → يعرف."""
    return _DIACRITICS_RE.sub('', s)


# Common Arabic pronoun suffixes that legally attach to verbs/particles.
# Including these as OPTIONAL match suffix solves the كأنّنا / كأنّه problem
# without re-introducing the إذ/إذا conflation: "ا" is NOT a pronoun suffix,
# so 'إذ' + 'ا' still won't match because the negative lookahead rejects it.
_PRONOUN_SUFFIX_PATTERN = r'(?:ه|ها|هم|هن|هما|ك|كم|كن|نا|ي)?'


def count_marker_safe(text: str, marker: str) -> int:
    """Word-boundary-aware, diacritic-insensitive, pronoun-suffix-tolerant.

    Strips diacritics from both text and marker before matching.
    Allows an optional Arabic pronoun suffix attached to the marker (so كأنّنا
    matches the marker كأن with pronoun نا, but إذا still won't match إذ since
    ا isn't a pronoun suffix).
    Asserts the AFTER position (after any pronoun suffix) is bounded by
    non-Arabic-letter context.
    """
    text_n = _normalize_diacritics(text)
    marker_n = _normalize_diacritics(marker)
    if not marker_n:
        return 0
    pattern = (
        r'(?<!' + _AR_LETTER_CLASS + r')' +
        re.escape(marker_n) +
        _PRONOUN_SUFFIX_PATTERN +
        r'(?!' + _AR_LETTER_CLASS + r')'
    )
    return len(re.findall(pattern, text_n))


def count_markers(text: str, markers: list[str]) -> int:
    """Count occurrences of any marker in text, with proper Arabic boundaries."""
    return sum(count_marker_safe(text, m) for m in markers)


def _count_connector_distrib(text: str, connector: str) -> int:
    """Loose, prefix-aware counter for Dim 16 distributional analysis.

    Single-char connectors (و, ف, ك, ل) may attach as prefixes to the next
    word ("والذكاء") and should still count. Multi-char short connectors
    (ثم, بل, إذ) need word-boundary on both sides to avoid the إذ/إذا
    conflation. Multi-word phrases ("بيد أن") use simple substring match.
    """
    text_n = _normalize_diacritics(text)
    c_n = _normalize_diacritics(connector)
    if not c_n:
        return 0
    if len(c_n) == 1:
        # Prefix-allowed: preceded by non-letter (boundary on LEFT only)
        pattern = r'(?<![ء-ي])' + re.escape(c_n)
        return len(re.findall(pattern, text_n))
    if len(c_n) <= 3:
        # Strict boundary both sides — prevents إذ matching inside إذا/إذن
        pattern = (r'(?<![ء-ي])' + re.escape(c_n) + r'(?![ء-ي])')
        return len(re.findall(pattern, text_n))
    # Multi-word phrases: substring match with normalization
    return text_n.count(c_n)


def sentence_split(text: str) -> list[str]:
    """Fix #5 (bug 3): also split on Arabic semicolon ؛"""
    return [s.strip() for s in re.split(r'[.!?؟؛…]+\s+', text) if s.strip()]


def word_count(text: str) -> int:
    return len(text.split())


def detect_repetition(sentences: list[str]) -> dict:
    """Lexical + structural repetition signals."""
    # Lexical: same word in nearby sentences
    lex_repeats = 0
    for i, s in enumerate(sentences):
        if i + 1 >= len(sentences): break
        s_words = set(w for w in s.split() if len(w) > 3)
        next_words = set(w for w in sentences[i+1].split() if len(w) > 3)
        lex_repeats += len(s_words & next_words)
    # Structural: same first word in consecutive sentences
    struct_repeats = sum(
        1 for i in range(len(sentences)-1)
        if sentences[i].split()[0:1] == sentences[i+1].split()[0:1]
        if sentences[i].split()
    )
    return {"lexical_overlap_pairs": lex_repeats, "same_starter_runs": struct_repeats}


def detect_antithesis(text: str) -> int:
    """Count طباق pairs co-occurring in the text."""
    hits = 0
    for a, b in ANTITHESIS_PAIRS:
        if a in text and b in text:
            hits += 1
    return hits


def burstiness(sentences: list[str]) -> float:
    """Sentence length variance / mean = coefficient of variation."""
    if len(sentences) < 2: return 0.0
    lengths = [len(s.split()) for s in sentences]
    mean = sum(lengths) / len(lengths)
    if mean == 0: return 0.0
    var = sum((l - mean) ** 2 for l in lengths) / len(lengths)
    return math.sqrt(var) / mean


def score_dimension(text: str, sentences: list[str], words: int, dim_num: int) -> dict:
    """Score one dimension 0-15 with detected signals."""
    if dim_num in (1, 2, 3):  # reasoning markers
        hits = count_markers(text, REASONING_MARKERS)
        rate = hits / max(1, words / 100)  # per 100 words
        score = min(15, int(rate * 5))
        return {"score": score, "signals": {"reasoning_marker_count": hits,
                                              "per_100_words": round(rate, 2)}}
    if dim_num == 4:
        hits = count_markers(text, ANALYSIS_MARKERS)
        rate = hits / max(1, words / 100)
        score = min(15, int(rate * 6))
        return {"score": score, "signals": {"analysis_marker_count": hits}}
    if dim_num == 5:
        hits = count_markers(text, SCAFFOLD_MARKERS)
        score = min(15, int(hits * 4))
        return {"score": score, "signals": {"scaffold_marker_count": hits}}
    if dim_num == 6:
        hits = count_markers(text, SCOPE_MARKERS)
        score = min(15, int(hits * 5))
        return {"score": score, "signals": {"scope_marker_count": hits}}
    if dim_num == 7:
        hits = count_markers(text, TRANSITION_MARKERS)
        score = min(15, int(hits * 4))
        return {"score": score, "signals": {"transition_marker_count": hits}}
    if dim_num == 8:
        hits = count_markers(text, AXIS_MARKERS)
        score = min(15, int(hits * 5))
        return {"score": score, "signals": {"axis_marker_count": hits}}
    if dim_num == 9:
        # literary art = burstiness proxy + parallel structure presence
        b = burstiness(sentences)
        # Score on burstiness curve: 0.0=0, 0.5=8, 1.0=12, 2.0+=15
        score = min(15, int(b * 12))
        return {"score": score, "signals": {"burstiness": round(b, 2)}}
    if dim_num == 10:
        hits = count_markers(text, HISTORICAL_MARKERS)
        score = min(15, int(hits * 5))
        return {"score": score, "signals": {"historical_marker_count": hits}}
    if dim_num == 11:
        # Sensory markers (existing list) + tashbeeh-by-prefix-kaf detection
        hits = count_markers(text, SENSORY_MARKERS)
        # كـ + concrete noun (NEW — catches كالنهر، كالطير، كالنسيج)
        kaf_hits = len(TASHBEEH_KAF_PATTERN.findall(_normalize_diacritics(text)))
        total = hits + kaf_hits
        score = min(15, int(total * 4))
        return {"score": score, "signals": {
            "sensory_marker_count": hits,
            "tashbeeh_kaf_count": kaf_hits,
            "total": total,
        }}
    if dim_num == 12:
        ant = detect_antithesis(text)
        score = min(15, ant * 4)
        return {"score": score, "signals": {"antithesis_pairs": ant}}
    if dim_num == 13:
        cit = count_markers(text, CITATION_MARKERS)
        rep = detect_repetition(sentences)
        # Score = high citation, low repetition
        score_cit = min(8, cit * 3)
        rep_total = rep["lexical_overlap_pairs"] + rep["same_starter_runs"]
        score_norep = max(0, 7 - rep_total // 2)
        score = score_cit + score_norep
        return {"score": score, "signals": {**rep, "citation_marker_count": cit}}
    if dim_num == 14:
        # INVERSE scoring: starts at 15, subtracts for negative markers.
        # The presence of these markers means the text disrespects the reader's
        # intelligence (over-explains, repeats, draws conclusions for them, etc.)
        over_exp = count_markers(text, OVER_EXPLANATION_MARKERS)
        redund = count_markers(text, REDUNDANT_AFFIRMATION_MARKERS)
        forced = count_markers(text, FORCED_CONCLUSION_MARKERS)
        defs = count_markers(text, KNOWN_TERM_DEFINITIONS)
        # Each marker subtracts 2 points; floor at 0
        penalty = 2 * (over_exp + redund + forced + defs)
        score = max(0, 15 - penalty)
        return {"score": score, "signals": {
            "over_explanation_count": over_exp,
            "redundant_affirmation_count": redund,
            "forced_conclusion_count": forced,
            "known_term_definitions": defs,
            "total_penalty_points": penalty,
        }}
    if dim_num == 16:
        # الفصل والوصل — distributional analysis of connector diversity.
        # Score 0-15 based on Shannon entropy of connector distribution.
        # Use _count_connector_distrib (loose, prefix-aware) instead of
        # the strict count_marker_safe — because و typically attaches as a
        # prefix (والذكاء) and rejecting that under-counts the dominant case.
        counts = {c: _count_connector_distrib(text, c) for c in FASL_WASL_CONNECTORS}
        total = sum(counts.values())
        nonzero = [n for n in counts.values() if n > 0]
        # Three failure modes are distinct:
        # (a) too few connectors total to assess → neutral 8
        # (b) total≥5 but only ONE distinct connector → MONOCULTURE → low 2
        # (c) classical-rich connector distribution → compute entropy below
        if total < 5:
            return {"score": 8, "signals": {
                "total_connectors": total,
                "distinct_connectors": len(nonzero),
                "note": "too few connectors to score reliably; returning neutral 8",
            }}
        if len(nonzero) < 2:
            # Monoculture: 5+ uses of a single connector. Classic AI tell.
            sole = next((c for c, n in counts.items() if n > 0), "?")
            return {"score": 2, "signals": {
                "total_connectors": total,
                "distinct_connectors": 1,
                "monoculture_connector": sole,
                "note": "extreme monoculture: only one connector used 5+ times",
            }}
        # Shannon entropy of the connector distribution
        probs = [n / total for n in nonzero]
        H = -sum(p * math.log2(p) for p in probs)
        H_max = math.log2(len(nonzero))
        diversity = H / H_max if H_max > 0 else 0
        # Bonus for using rare connectors (بل, بيد أن, غير أن, إذ)
        rare_used = sum(1 for c in ["بل", "بيد أن", "غير أن", "إذ"]
                        if counts.get(c, 0) > 0)
        # و should be <65% of total for human-like distribution
        w_share = counts.get("و", 0) / total
        w_penalty = max(0, (w_share - 0.65) * 10)  # 0-3.5 penalty if >65%
        base_score = 15 * diversity
        score = max(0, min(15, round(base_score + rare_used - w_penalty)))
        # Top 5 connectors used (for diagnostic transparency)
        top = sorted(counts.items(), key=lambda kv: -kv[1])[:5]
        return {"score": score, "signals": {
            "total_connectors": total,
            "distinct_connectors": len(nonzero),
            "shannon_entropy": round(H, 2),
            "diversity_ratio": round(diversity, 2),
            "rare_connectors_used": rare_used,
            "w_share": round(w_share, 2),
            "top_5_connectors": top,
        }}
    if dim_num == 15:
        # Typography hygiene — INVERSE scoring on mechanical issues.
        ar_en_adj = len(AR_EN_ADJACENCY.findall(text))
        lat_comma = len(LATIN_COMMA_IN_AR.findall(text))
        lat_semi = len(LATIN_SEMICOLON_IN_AR.findall(text))
        paren_en = len(PAREN_EN_NO_SPACE.findall(text))
        # Mixed numbering: penalize if 2+ styles co-exist in the text
        styles = sum([
            bool(NUM_STYLE_PARENS.search(text)),
            bool(NUM_STYLE_DOT.search(text)),
            bool(NUM_STYLE_DASH.search(text)),
        ])
        mixed_numbering = max(0, styles - 1)  # 0 if only one style, 1 if mixed
        # Each issue subtracts 1 point; mixed-numbering subtracts 3
        penalty = ar_en_adj + lat_comma + lat_semi + paren_en + 3 * mixed_numbering
        score = max(0, 15 - penalty)
        return {"score": score, "signals": {
            "ar_en_adjacency_no_space": ar_en_adj,
            "latin_comma_in_arabic": lat_comma,
            "latin_semicolon_in_arabic": lat_semi,
            "paren_english_no_space": paren_en,
            "mixed_numbering_styles": mixed_numbering,
            "total_penalty_points": penalty,
        }}
    return {"score": 0, "signals": {}}


DIM_NAMES = {
    1: "الاستنتاج (Deduction)",
    2: "الاستدلال (Inference)",
    3: "الاستنباط (Specific inference)",
    4: "التحليل البشري (Human analysis)",
    5: "التدرج في الشرح (Graduated explanation)",
    6: "تحديد النطاق (Scope definition)",
    7: "التنقل في الأفكار (Idea transitions)",
    8: "التقسيم للمحاور (Axes partitioning)",
    9: "الفن الأدبي (Literary art)",
    10: "الاستدلال التاريخي (Historical anchoring)",
    11: "التخيل وتوسيع الإدراك (Imagination)",
    12: "البلاغة (Rhetorical figures)",
    13: "عدم التكرار + الاستدلال الداخلي (Coherence)",
    14: "ضبط القارئ — Cognitive Restraint Score (positive: high=good)",
    15: "إتقان الصياغة — Typographic Precision Score (positive: high=good)",
    16: "الفصل والوصل (Junction-disjunction — DISTRIBUTIONAL)",
}


def analyze(text: str) -> dict:
    sentences = sentence_split(text)
    words = word_count(text)
    by_dim = {}
    total = 0
    for n in range(1, 17):
        r = score_dimension(text, sentences, words, n)
        by_dim[n] = {"name": DIM_NAMES[n], **r}
        total += r["score"]
    # Overall on a 0-100 scale (max 240 = 15 × 16)
    overall = round(100 * total / (15 * 16), 1)
    weakest = sorted(by_dim.items(), key=lambda kv: kv[1]["score"])[:3]
    return {
        "word_count": words,
        "sentence_count": len(sentences),
        "burstiness": round(burstiness(sentences), 3),
        "by_dimension": by_dim,
        "total_points": total,
        "overall_humanness_0_100": overall,
        "weakest_dimensions": [(n, by_dim[n]["name"], by_dim[n]["score"])
                                for n, _ in weakest],
    }


def render_report(a: dict) -> str:
    lines = []
    lines.append("=" * 70)
    lines.append("13-Dimension Humanness Analysis")
    lines.append("=" * 70)
    lines.append(f"Words: {a['word_count']}  Sentences: {a['sentence_count']}  "
                 f"Burstiness: {a['burstiness']}")
    lines.append(f"Overall humanness: {a['overall_humanness_0_100']}/100  "
                 f"({a['total_points']}/240 points)")
    lines.append("")
    lines.append(f"{'#':>3} {'Dimension':<48} {'Score':>5}")
    lines.append("-" * 70)
    for n in range(1, 17):
        d = a["by_dimension"][n]
        lines.append(f"{n:>3} {d['name']:<48} {d['score']:>3}/15")
    lines.append("")
    lines.append("Weakest 3 dimensions (target with humanize_v2.py):")
    for n, name, sc in a["weakest_dimensions"]:
        lines.append(f"  [{sc:>2}/15] dim {n}: {name}")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", "-i", help="Inline text")
    ap.add_argument("--file", "-f", type=Path, help="Read from file")
    ap.add_argument("--json", action="store_true", help="Output JSON")
    ap.add_argument("--report", action="store_true",
                    help="Output human-readable report")
    args = ap.parse_args()

    if args.file:
        text = args.file.read_text(encoding="utf-8")
    elif args.input:
        text = args.input
    else:
        text = sys.stdin.read()
    if not text.strip():
        raise SystemExit("empty input")

    result = analyze(text)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(render_report(result))


if __name__ == "__main__":
    main()
