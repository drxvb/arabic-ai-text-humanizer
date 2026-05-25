# Example 05: Diagnostic-only — 16-dimension scorecard

## Reproduction command

```bash
python scripts/analyze_deep.py   --file examples/05-diagnostic-only-analyze.input.txt   --report > examples/05-diagnostic-only-analyze.report.txt
```

`analyze_deep` is fully deterministic and never calls the LLM — it produces the same scorecard for the same input on any machine.

## Input

```
من المهم ملاحظة أن الذكاء الاصطناعي يَشهد تطوراً متسارعاً. في الواقع، أكدت الدراسات أن العديد من القطاعات بدأت في تبني هذه التقنيات. علاوة على ذلك، فإن المستقبل يبدو واعداً. تجدر الإشارة إلى أن التحديات الأخلاقية ما تزال قائمة. بكل تأكيد، يتطلب الأمر تنسيقاً دولياً.
```

## Output: 16-dimension diagnostic

```
======================================================================
13-Dimension Humanness Analysis
======================================================================
Words: 44  Sentences: 5  Burstiness: 0.273
Overall humanness: 26.2/100  (63/240 points)

  # Dimension                                        Score
----------------------------------------------------------------------
  1 الاستنتاج (Deduction)                              5/15
  2 الاستدلال (Inference)                              5/15
  3 الاستنباط (Specific inference)                     5/15
  4 التحليل البشري (Human analysis)                    0/15
  5 التدرج في الشرح (Graduated explanation)            0/15
  6 تحديد النطاق (Scope definition)                    0/15
  7 التنقل في الأفكار (Idea transitions)               0/15
  8 التقسيم للمحاور (Axes partitioning)                0/15
  9 الفن الأدبي (Literary art)                         3/15
 10 الاستدلال التاريخي (Historical anchoring)          0/15
 11 التخيل وتوسيع الإدراك (Imagination)                0/15
 12 البلاغة (Rhetorical figures)                       0/15
 13 عدم التكرار + الاستدلال الداخلي (Coherence)        7/15
 14 ضبط القارئ — Cognitive Restraint Score (positive: high=good)  15/15
 15 إتقان الصياغة — Typographic Precision Score (positive: high=good)  15/15
 16 الفصل والوصل (Junction-disjunction — DISTRIBUTIONAL)   8/15

Weakest 3 dimensions (target with humanize_v2.py):
  [ 0/15] dim 4: التحليل البشري (Human analysis)
  [ 0/15] dim 5: التدرج في الشرح (Graduated explanation)
  [ 0/15] dim 6: تحديد النطاق (Scope definition)
```

## Interpretation

The text shows classic AI fingerprints: formulaic hedges (`من المهم ملاحظة أن`, `تجدر الإشارة إلى أن`), monoculture of the connector `و`, intensifier stacking (`بكل تأكيد`, `العديد من`). Dimension 14 (reader-respect, inverse-scored) and Dimension 16 (الفصل والوصل entropy) are usually the weakest dimensions for AI-flat news text. The scorecard tells you which dimensions are weakest — pick the matching `--mode` to address them.
