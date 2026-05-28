# 18 — Sacred-Text Preservation Guard (v2.6.0+)

The humanizer transformation passes (`humanize_v2.py` lex pass, cognitive pass, quote-verb rotation) are designed for modern MSA prose. Applying them to Quranic verses or hadith citations is **theologically and editorially wrong**: rotating `قال رسول الله ﷺ` to `أكد رسول الله` corrupts a fixed isnad formula; stripping connectors inside a Qur'anic ayah breaks the divine text. Per Agent A's native-speaker review (multi-agent synthesis, v2.6.0), this is **the highest-severity missing feature for any religious-publication deployment** — "a malpractice claim waiting to happen."

## What ships in v2.6.0

`scripts/sacred_text_guard.py` provides:

```python
detect_locked_spans(text: str) -> List[Tuple[start, end, reason]]
mask_sacred_spans(text: str)   -> (masked_text, masks)
restore_sacred_spans(masked, masks) -> text
```

The mask/restore pair mirrors the code-block protection pattern from `humanize_english.py` (v2.5.1 T3 fix). Callers should mask BEFORE any transformation pass and restore AFTER.

## Detection layers (conservative — high precision, low recall by design)

| Layer | Heuristic |
|---|---|
| **Quranic tajweed marks** | 3+ marks from U+06D6–U+06ED cluster within a 200-char window → lock the surrounding paragraph |
| **Quranic citation framing** | `قال تعالى:`, `قال الله تعالى:`, `يقول تعالى`, `في قوله تعالى`, `كما قال تعالى` |
| **Hadith attribution chains** | `قال رسول الله ﷺ` / `صلى الله عليه وسلم`, `قال النبي`, `روى X عن Y`, `حدثنا X عن Y عن Z`, `أخرجه البخاري`/`مسلم`/`الترمذي`/`أبو داود`/`النسائي`/`ابن ماجه`/`أحمد` |
| **Basmala** | `بسم الله الرحمن الرحيم` |

Each detected anchor extends to the natural span end: closing guillemet `»`, ASCII `"`, end-of-sentence punctuation `.`/`؟`/`!`, or a hard 400-character cap if no terminator is found.

## What this guard does NOT do (yet)

- It does NOT do semantic verification — it can't tell if a quoted phrase is genuinely Quranic vs. an attributed-to-a-similar-frame quote from a different source.
- It does NOT handle classical poetry citations (`قال الشاعر`).
- It does NOT preserve sacred-text spans embedded in code blocks (those are already protected by `humanize_english.py`'s code-block layer).
- It does NOT auto-detect orphaned ayah numbers (e.g., `(٢١)` after a verse without the framing).

These are v2.6.1+ candidates. The current scope is the load-bearing 80% — the cases that produce the worst editorial outcomes when mishandled.

## Integration (current)

`humanize_v2.py` does NOT yet call this guard automatically — the v2.6.0 ship is the *guard module* itself. A v2.6.1 minor ships the integration: every transformation pass in `humanize_v2.py` will mask via `mask_sacred_spans()` before the first lex sub-pass and restore via `restore_sacred_spans()` after the last typography pass.

For now, callers who deploy the humanizer in a religious-publication context can use the guard manually:

```python
from scripts.sacred_text_guard import mask_sacred_spans, restore_sacred_spans

masked, masks = mask_sacred_spans(input_text)
# ... run humanize_v2.py on `masked` ...
output = restore_sacred_spans(transformed, masks)
```

## CLI

```bash
python scripts/sacred_text_guard.py --text "قال تعالى: «...»" --json
python scripts/sacred_text_guard.py --input article.md
```

JSON output includes `start`, `end`, `reason`, and an 80-char preview per span.

## Failure modes and mitigations

| Failure | Mitigation |
|---|---|
| False negative (real Quranic content not flagged because the citation frame is unusual) | Conservative regex chosen for high precision; users in religious-publication contexts should manually wrap suspect passages in `«…»` guillemets, which the guard treats as natural span end markers |
| False positive (modern prose locked because someone said `قال تعالى` in a literary sense) | Span only locks AFTER the framing; if no quoted content follows, the impact is minimal (a single sentence) |
| Tajweed-mark cluster in non-Quranic content (e.g., academic linguistics paper about Quranic recitation) | The 3+marks-in-200-chars heuristic is tunable; in academic contexts, set window_size=50 or min_marks=5 |
| Sacred-text inside a code block | Already preserved by code-block layer in humanize_english.py; for humanize_v2.py, the guard runs first, code blocks aren't a concern in Arabic prose anyway |
