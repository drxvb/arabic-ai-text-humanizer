# Lexical Layer — Inherited Substitution Tables

This file consolidates the lexical-substitution tables inherited from a **predecessor lexical-only Arabic humanizer** (referred to throughout as "v1" — the baseline pipeline this skill builds on). These tables form the **lexical layer** of the current pipeline — the deterministic, no-LLM substitution pass that runs in Stage 1 (`--mode lex-only`). The cognitive, rhetorical, register, and rhythm layers (`references/01-11`) operate on top of this lexical baseline.

This skill does **not** reinvent these tables. It reuses them as-is, then layers higher-order transformations above. If you change anything here and you also maintain a separate lexical-only sibling, propagate the change there — both should share the same substrate.

## 1. AI_PHRASES_AR — Formulaic AI Lead-ins and Hedges

| AI phrase (input) | Alternatives (one chosen at runtime) |
|---|---|
| من المهم ملاحظة | للعلم / من الجدير بالذكر / تذكر |
| من الجدير بالذكر | للعلم / من المهم ملاحظة / تذكر |
| من المفيد الإشارة | من الجدير بالذكر / من المهم ملاحظة |
| في سياق متصل | أيضاً / كذلك / بالإضافة إلى ذلك |
| في نفس السياق | أيضاً / كذلك / علاوة على ذلك |
| علاوة على ذلك | بالإضافة / أيضاً / فضلاً عن ذلك |
| بالإضافة إلى ذلك | أيضاً / كذلك / علاوة على ذلك |
| من ناحية أخرى | لكن / بالمقابل / في المقابل |
| على الجانب الآخر | بالمقابل / في المقابل / لكن |
| في النهاية | أخيراً / ختاماً / في الختام |
| في الختام | أخيراً / ختاماً / في النهاية |
| في البداية | أولاً / في الأول / لنبدأ بـ |
| كما ذكر سابقاً | كما قلنا / كما أسلفنا / كما سبق |
| كما أسلفنا | كما ذكرنا / كما سبق / كما قلنا |
| من الواضح أن | بوضوح / واضحاً / من البديهي أن |
| من المهم التأكيد | نؤكد / يجب التنويه / من الجدير التنويه |
| لا بد من الإشارة | من الجدير بالذكر / من المهم ملاحظة |
| في إطار | ضمن / في نطاق / في مجال |
| على صعيد | في مجال / فيما يتعلق بـ / بخصوص |
| في ظل | مع / في حال / في وقت |
| بناءً على ما تقدم | وبناءً عليه / لذلك / وعليه |
| في ظل التطورات | مع التطورات / بالنظر إلى التطورات |
| جدير بالذكر | من المهم / من الجدير بالذكر / للعلم |
| من الممكن أن | قد / يمكن أن / ربما |
| من المتوقع أن | من المرجح / من المنتظر / يُتوقع |
| يشار إلى أن | للعلم / من الجدير بالذكر |
| يُعتبر من | هو من / يُعد من |
| في هذا الإطار | في هذا السياق / ضمن هذا / في هذا المجال |
| على المستوى | في مجال / فيما يخص |
| في مجال | بخصوص / فيما يتعلق بـ |

**Total entries:** 30
**Substitution policy in v1:** every match is rewritten (no probabilistic skip). v2 keeps this default but allows `--intensity` < 1.0 to skip a fraction.

## 2. CONNECTORS_AI_AR — Sentence Connectors

| AI connector | Natural alternative |
|---|---|
| وعلاوة على ذلك، | كما أن، |
| ومع ذلك، | لكن، |
| وبالتالي، | لذلك، |
| وبناءً عليه، | لذلك، |
| على سبيل المثال، | مثلاً، |
| في المقابل، | بالمقابل، |
| على العكس من ذلك، | بعكس ذلك، |
| باختصار، | بشكل مختصر، |

**Total entries:** 8
**Substitution policy in v1:** selective — each match is replaced with probability 0.7. The remaining 0.3 are left as-is to retain variation rather than uniform stripping.

## 3. REPETITIVE_STARTERS_AR — Over-used Sentence-Initial Tokens

The detector list (sentences starting with these are candidates for diversification):

| Starter |
|---|
| تعتبر |
| تُعتبر |
| يُعتبر |
| تعد |
| يُعد |
| تُعد |
| يمكن |
| تستطيع |
| نستطيع |
| يعتبر |
| يعد |

**Total entries:** 11

**Diversification policy in v1:** when the same starter recurs across consecutive sentences, replace with one of the pronoun-prefixed alternatives:

| Replacement starters |
|---|
| فهي |
| وهي |
| إنها |
| كما أنها |

**Trigger:** 50% probability of rewrite on consecutive-same-starter detection.

## 4. Arabic Fillers — Imperfection Layer

When `--intensity > 0.4`, v1 occasionally prepends a "human filler" to a sentence (probability ≈ intensity × 0.1, only on sentences > 40 chars, never the first sentence):

| Filler |
|---|
| طبعاً، |
| بالمناسبة، |
| في الحقيقة، |
| أعني، |

## 5. Structural Pattern Breakers — Numbered Transitions

v1 rewrites positional adverbs with 50% probability to introduce variance:

| AI pattern | Alternative |
|---|---|
| أولاً، | في البداية، |
| ثانياً، | بعد ذلك، |
| ثالثاً، | أيضاً، |
| رابعاً، | علاوة على ذلك، |
| أخيراً، | في النهاية، |

## How v2 calls this layer

```python
# Stage 1 — Lexical pass, deterministic
from references_v1 import (
    AI_PHRASES_AR,            # 30 entries
    CONNECTORS_AI_AR,         #  8 entries
    REPETITIVE_STARTERS_AR,   # 11 entries
    ARABIC_FILLERS,           #  4 entries
    NUMBERED_TRANSITIONS_AR,  #  5 entries
)
text = replace_ai_phrases(text, AI_PHRASES_AR)
text = replace_connectors(text, CONNECTORS_AI_AR, prob=0.7)
text = diversify_starters(text, REPETITIVE_STARTERS_AR)
text = break_structural_patterns(text, NUMBERED_TRANSITIONS_AR)
text = vary_sentence_lengths(text)
if intensity > 0.4:
    text = add_imperfections(text, ARABIC_FILLERS, intensity)
```

This is the entire v1 pipeline. Total runtime per 1,000 words: ≈ 1 second.

## GAPS in v1's lexical layer

The corpus mining in `references/12-corpus-findings.md` reveals patterns the v1 lexical layer misses. The current pipeline extends the tables with the following entries — each grounded in the empirical distribution.

### Gap A — Missing AI lead-ins not caught by v1
v1 catches "من المهم ملاحظة" and "من الجدير بالذكر" but misses these statistically-frequent AI tells:

| Missed AI phrase | Why it's an AI tell | Suggested alternatives |
|---|---|---|
| تجدر الإشارة إلى أنّ | absent from corpus; AI signature | يُذكر أنّ / والحقيقة أنّ / [delete] |
| في هذا الصدد | corpus rank low; AI over-uses | هنا / بصدد ذلك / [delete] |
| من هذا المنطلق | rare in corpus | من هنا / لذلك |
| على هذا الأساس | rare in corpus | بناءً على ذلك / لذلك |
| لا شك أنّ | over-used as filler | بلا شك / [delete intensifier] |
| من المعروف أنّ | AI hedge | المعروف أنّ / [delete] |
| كما هو معلوم | AI hedge | المعلوم أنّ / [delete] |
| في حقيقة الأمر | AI filler | في الحقيقة / [delete] |
| لا يخفى على أحد | AI cliché | الواضح أنّ |
| تجدر الإشارة كذلك | AI cliché | كذلك / يُضاف |

### Gap B — Missing AI connectors
v1's CONNECTORS_AI_AR list has only 8 entries. Add these high-frequency AI connectors:

| Missed AI connector | Natural alternative |
|---|---|
| فضلاً عن ذلك، | كذلك، / أيضاً، |
| إضافة إلى ذلك، | كذلك، / و، |
| من جهة أخرى، | بالمقابل، / لكن، |
| من جانب آخر، | بالمقابل، |
| بصورة عامة، | عموماً، |
| بشكل عام، | عموماً، |
| بشكل خاص، | خصوصاً، |
| في الواقع، | فعلاً، / حقيقة، |
| في حين أنّ | بينما / لكن |
| على الرغم من ذلك، | رغم ذلك، / لكن، |
| نتيجة لذلك، | لذلك، / فـ، |
| استناداً إلى ذلك، | بناءً عليه، |
| تبعاً لذلك، | لذلك، |

### Gap C — Missing repetitive starters
v1's starter list focuses on verb-initial forms (تعتبر / يُعد). The corpus exposes these additional AI-favored openers:

| Missed AI starter | Replacement strategy |
|---|---|
| يلعب ... دوراً | dive directly into the role: "X يحدّد / يُشكّل / يَصنع" |
| يشكّل ... عاملاً | replace with active claim: "X هو السبب الرئيسي" |
| يمثّل ... جزءاً | "X هو" / "X يُعدّ" |
| يكمن ... في | "السبب: ..." / "ها هو السبب:" |
| تنبع ... من | "يَأتي من" / "أصلها" |
| تتمثّل ... في | "هي:" / "تَتلخّص في" |
| تكتسب ... أهمية | "تُهمّ" / "حاسمة" |
| تواجه ... تحديات | "أمام X تحديات" / "X يَتعثّر في" |
| تشهد ... تطوراً | "X يَتطوّر" |
| تسعى ... إلى | "X تُريد" / "X تَطمح إلى" |

### Gap D — Missing quote-introducing verb diversity (news register)
v1 doesn't rotate quote-verbs. The corpus shows news writers rotate أكد، أشار، أوضح، أضاف، أعلن، صرّح، ذكر، نقل، روى — but AI defaults to قال and يقول repeatedly. v2 should add a quote-verb rotation pass:

| AI default | Rotation pool (news register) |
|---|---|
| قال | أكّد / أشار / أوضح / أضاف / صرّح / ذكر / نوّه / لفت |
| يقول | يَرى / يَعتقد / يَزعم / يُقرّر / يُؤكّد |
| ذكر أن | أفاد بأنّ / أشار إلى أنّ / لفت إلى أنّ / كشف أنّ |

### Gap E — Missing register-aware substitution
v1 applies all substitutions uniformly regardless of register. v2 should gate substitutions:
- **Heritage register** (Stage 2 detects fصحى التراث): suppress vernacular fillers (طبعاً، يعني)
- **News register**: allow news-style transitions, suppress poetic devices
- **Educational register**: prefer simpler alternatives in every substitution table
- See `references/10-register-modulation.md` for the gating logic

### Gap F — No suppression of false positives
v1 substitutes blindly. The string "من المهم" inside a quoted phrase or technical term should be preserved. v2 should add a quoted-span detector to bypass substitution within "..." and «...».

### Gap G — No handling of redundant intensifiers
v1 doesn't catch AI's stacked intensifiers: "في غاية الأهمية البالغة جداً"، "بشكل كبير جداً"، "بصورة ملحوظة وواضحة". The corpus shows humans rarely stack these — usually one intensifier per phrase, at most. v2 should add a de-stacking pass.
