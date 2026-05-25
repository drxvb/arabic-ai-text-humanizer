# Example 02: Opinion register × tighten mode — de-stacking intensifiers

## Reproduction command

```bash
python scripts/humanize_v2.py \
  --input examples/02-opinion-tighten-intensifier-destack.input.txt \
  --mode tighten --register opinion \
  --output examples/02-opinion-tighten-intensifier-destack.output.txt
```

No API key needed — `tighten` mode is fully deterministic.

## Input (AI-generated Arabic)

```
لا شك أن التحول الرقمي في غاية الأهمية البالغة جداً للمؤسسات الحديثة. من ناحية أخرى، فإن مقاومة التغيير ظاهرة سلبية للغاية وتُشكِّل عائقاً كبيراً جداً أمام التطوير. وعلاوة على ذلك، يجب على القيادات أن تتبنى نهجاً استباقياً. من المؤكَّد أن النجاح يتطلب التزاماً حقيقياً وفعلياً من جميع الأطراف.
```

## Output (after humanization)

```
التحول الرقمي بالغ الأهمية للمؤسسات الحديثة. وبالمقابل، فإن مقاومة التغيير ظاهرة سلبية للغاية وتُشكِّل عائقاً كبيراً جداً أمام التطوير. وويُضاف إلى ذلك، يجب على القيادات أن تتبنى نهجاً استباقياً. من المؤكَّد أن النجاح يتطلب التزاماً حقيقياً وفعلياً من جميع الأطراف.
```

## What changed and why

Opinion text often stacks intensifiers (`في غاية الأهمية البالغة جداً` ≈ "extremely extraordinarily very important"). The empirical corpus shows humans rarely stack — usually one intensifier per phrase. The lex pass de-stacks, deletes the hedging openers (`لا شك أن`, `من المؤكد أن`), and rotates `علاوة على ذلك` to a less mechanical connector. Quote verbs are absent here so the rotation env-gate doesn't come into play.

## Reproducibility

This output is **byte-deterministic**: running the same command on any machine with the same skill version produces the same output. The lexical pass uses no random number generator state; the register policy gates which transformations fire deterministically.
