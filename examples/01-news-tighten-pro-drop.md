# Example 01: News register × tighten mode — pro-drop deletion of formulaic hedges

## Reproduction command

```bash
python scripts/humanize_v2.py \
  --input examples/01-news-tighten-pro-drop.input.txt \
  --mode tighten --register news \
  --output examples/01-news-tighten-pro-drop.output.txt
```

No API key needed — `tighten` mode is fully deterministic.

## Input (AI-generated Arabic)

```
من المهم ملاحظة أن الاقتصاد السعودي يشهد نمواً ملحوظاً في القطاعات غير النفطية. في الواقع، أكدت التقارير الصادرة عن وزارة الاقتصاد أن نسبة المشاركة في سوق العمل ارتفعت بشكل ملحوظ خلال الربع الثاني. علاوة على ذلك، فإن هذا النمو يعكس تنوعاً متزايداً في مصادر الدخل. بكل تأكيد، تستمر الحكومة في دعم رؤية 2030.
```

## Output (after humanization)

```
يلزم التنبيه إلى أن الاقتصاد السعودي يشهد نمواً ملحوظاً في القطاعات غير النفطية. حقيقةً، أكدت التقارير الصادرة عن وزارة الاقتصاد أن نسبة المشاركة في سوق العمل ارتفعت بشكل ملحوظ خلال الربع الثاني. وفوق ذلك، فإن هذا النمو يعكس تنوعاً متزايداً في مصادر الدخل. تستمر الحكومة في دعم رؤية 2030.
```

## What changed and why

Classic AI-flat news prose: a hedged opening (`من المهم ملاحظة أن`), a parenthetical filler (`في الواقع`), a formulaic transition (`علاوة على ذلك`), and a closing intensifier (`بكل تأكيد`). What `tighten` mode in the `news` register did, on this particular run:

- `من المهم ملاحظة أن` → `يلزم التنبيه إلى أن` *(substituted with a less-mechanical clausal opener; the موصولة particle `أن` is preserved)*
- `في الواقع،` → `حقيقة،` *(formulaic filler swapped for a single-word alternative)*
- `علاوة على ذلك،` → `وفوق ذلك،` *(connector diversified — breaking the `علاوة` monoculture is a Dim 16 win)*
- `بكل تأكيد،` → *(deleted entirely — pro-drop: Arabic prefers implicit emphasis to redundant intensifiers)*

Each AI tell in the lexical tables maps to a *list* of valid replacements; some lists include the empty string (deletion) as an option, others only contain substitutions. The pipeline picks per-phrase based on `--intensity` and seed state, so the exact replacement varies but the *class* of transformation is stable. The content nouns (`الاقتصاد السعودي`, `وزارة الاقتصاد`, `رؤية 2030`) and the factual claim are preserved verbatim across every run.

## Reproducibility

This output is **byte-deterministic**: running the same command on any machine with the same skill version produces the same output. The lexical pass uses no random number generator state; the register policy gates which transformations fire deterministically.
