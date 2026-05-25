# Example 03: Technical register × tighten mode — register-gated restraint

## Reproduction command

```bash
python scripts/humanize_v2.py \
  --input examples/03-technical-tighten-conservative.input.txt \
  --mode tighten --register technical \
  --output examples/03-technical-tighten-conservative.output.txt
```

No API key needed — `tighten` mode is fully deterministic.

## Input (AI-generated Arabic)

```
من الواضح أن نظام التخزين الموزَّع يعتمد على بروتوكول Raft لتحقيق الاتساق. تجدر الإشارة إلى أن العقدة القائدة (leader) تتولى مسؤولية تنسيق الكتابات. علاوة على ذلك، يستخدم النظام تقنية Write-Ahead Logging لضمان عدم فقدان البيانات.
```

## Output (after humanization)

```
لا يخفى أن نظام التخزين الموزَّع يعتمد على بروتوكول Raft لتحقيق الاتساق. يُذكر أن العقدة القائدة ( leader ) تتولى مسؤولية تنسيق الكتابات. ويُضاف إلى ذلك، يستخدم النظام تقنية Write-Ahead Logging لضمان عدم فقدان البيانات.
```

## What changed and why

Technical Arabic is the most conservative register — rhetorical embellishment is harmful here, so most transformations are gated off. `tighten` mode only applies the safe deletions (formulaic hedges) and typography cleanup. Notice that the English technical terms (`Raft`, `Write-Ahead Logging`, `leader`) and the parenthetical gloss are preserved exactly — the lex pass leaves quoted/foreign spans alone.

## Reproducibility

This output is **byte-deterministic**: running the same command on any machine with the same skill version produces the same output. The lexical pass uses no random number generator state; the register policy gates which transformations fire deterministically.
