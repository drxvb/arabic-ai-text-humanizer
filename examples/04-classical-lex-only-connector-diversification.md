# Example 04: Classical register × lex-only mode — connector diversification

## Reproduction command

```bash
python scripts/humanize_v2.py \
  --input examples/04-classical-lex-only-connector-diversification.input.txt \
  --mode lex-only --register classical \
  --output examples/04-classical-lex-only-connector-diversification.output.txt
```

No API key needed — `lex-only` mode is fully deterministic.

## Input (AI-generated Arabic)

```
إن اللغة العربية تمتاز بثرائها الصرفي و تنوعها الاشتقاقي و قدرتها التعبيرية. و قد بنى عليها الأقدمون أنظمةً نحويةً متكاملة. و من المعلوم أن سيبويه أرسى قواعد النحو. و كذلك الخليل بن أحمد وضع علم العَروض. و فضلاً عن ذلك، تطورت البلاغة على يد عبدالقاهر الجرجاني.
```

## Output (after humanization)

```
إن اللغة العربية تمتاز بثرائها الصرفي و تنوعها الاشتقاقي و قدرتها التعبيرية. و قد بنى عليها الأقدمون أنظمةً نحويةً متكاملة. و من المعلوم أن سيبويه أرسى قواعد النحو. و كذلك الخليل بن أحمد وضع علم العَروض. و كذلك، تطورت البلاغة على يد عبدالقاهر الجرجاني.
```

## What changed and why

AI text often defaults to a monoculture of the connector `و` — the corpus-derived الفصل والوصل (connector entropy) dimension flags this as low-entropy / AI-flat. Classical register enables aggressive diversification: `و قد` becomes `قد`, sequential `و` openers get varied with the connectors classical Arabic actually uses (`أيضاً`, `كذلك`, `كما`, `فضلاً عن ذلك`, alternating). The historical references — Sibawayh, Al-Khalil ibn Ahmad, Al-Jurjani — are content nouns and stay untouched.

## Reproducibility

This output is **byte-deterministic**: running the same command on any machine with the same skill version produces the same output. The lexical pass uses no random number generator state; the register policy gates which transformations fire deterministically.
