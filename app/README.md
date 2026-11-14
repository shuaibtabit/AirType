# Continuous six-group predictive text

Current design: **one gesture per letter position**, with **automatically inferred spaces**. The old two-gesture character code and first/second-input timeout are superseded. The groups in gesture_groups.example.json are illustrative, not final.

## Run the prototype

No dependencies or API key are needed for this small local software demo:

```sh
python3 -B app/t9_decoder.py 2 4 2 4 4 2
python3 -B app/t9_decoder.py roll_out tilt_down roll_out tilt_down tilt_down roll_out
```

The hand-written demo vocabulary ranks "go home" first. Spaces are inferred, with no word-boundary token. This is a software fixture, not a measured accuracy result or a general English model. Use `--encode 'go home'` to generate group IDs for debugging only; the real decoder receives gesture labels/IDs, never intended text or arbitrary representative letters.

## Architecture

1. Map each recognized gesture to its complete letter group using a versioned JSON config. Cover all 26 letters exactly once. Repeated gestures remain separate positions.
2. Encode every dictionary word as a group-ID tuple and index those tuples.
3. Build a lattice of matching words across the continuous stream. Each complete path is a phrase with inferred spaces. Every path consumes every gesture exactly once, with no inserted, deleted or substituted letters.
4. Keep a bounded beam of phrase paths, scored by the sum of normalized log word frequencies. This is a unigram language baseline, not a trained neural model. It ignores grammar and context and has word-count/segmentation biases.
5. Optionally ask Gemini Decision to rank retained phrases using preceding confirmed text. Only validated candidate IDs or rejection are allowed. It cannot invent missing words or repair misclassified gestures.
6. Return suggestions for wearer confirmation. Nothing is committed automatically and no agent actions occur.

This code owns text decoding, not detection, wrist classification or activation. Your partner's sensor and classifier code is unchanged.

## Real vocabulary

lexicon.demo.tsv contains only hand-written fixture words and illustrative weights. Do not use it to measure an 80–90% goal. Supply a larger frequency vocabulary with custom names/domain terms added deliberately.

TSV format: header `word<TAB>weight`, followed by lowercase ASCII words and positive finite weights, separated by actual tabs. Apostrophes, punctuation, digits, accents and multilingual text need future handling. Unknown words can produce no exact path; a wrong input can also match a different valid phrase.

Optional local exporter:

```sh
python3 -m venv work/t9-venv
source work/t9-venv/bin/activate
python -m pip install wordfreq==3.1.1
python app/build_lexicon.py work/english.tsv --words 50000
python app/t9_decoder.py --lexicon work/english.tsv 2 4 2 4 4 2
```

The exporter inspects the requested number of source entries and filters non-ASCII/nonalphabetic words, so fewer entries are exported. It refuses to overwrite files. Keep generated data and virtual environments under work/ and out of commits.

[wordfreq](https://github.com/rspeer/wordfreq) supplies historical frequency estimates. Its code is Apache-licensed; its data has CC BY-SA and source-specific attribution terms. Preserve applicable licenses and notices if redistributing an exported lexicon. This change bundles no third-party vocabulary.

WordNet could augment vocabulary, but meanings and semantic relationships are not the main requirement. Word frequencies and phrase context are more useful for ranking collisions.

## Gemini ranking

Set GEMINI_API_KEY locally using [the existing setup](../ml/GEMINI_SETUP.md), then:

```sh
python3 -B app/t9_decoder.py --gemini --context 'I want to' 2 4 2 4 4 2
```

This sends candidate phrases and preceding confirmed text to Google, not raw WHOOP data. Network use is opt-in. REST uses gemini-decision-1 and v1beta/decisions; no SDK is required. Keep the key in your backend, never browser JavaScript or Git.

A five-second timeout and no retries bound the setup experiment. Missing keys, API errors, timeouts and malformed responses retain explicitly marked local suggestions. A valid rejection or confidence below 0.7 produces status=uncertain. **0.7 is an unvalidated starting threshold**; tune on development data, not test data. Every response has committed=false; confirmation remains necessary.

The default beam keeps 32 hypotheses, capped at 254 plus reject. beam_pruned=true indicates dropped paths. Gemini cannot recover a phrase pruned before the request. Increase --beam using development data if needed, weighing latency and input cost. Local log_score is a ranking score, not probability of wearer intent.

## Integration

Put app/ on your backend's Python module path:

```python
from t9_decoder import Decoder, gemini_rank

decoder = Decoder.load('app/gesture_groups.example.json', 'work/english.tsv')
events = ['roll_out', 'tilt_down', 'roll_out', 'tilt_down', 'tilt_down', 'roll_out']
suggestions = decoder.decode(events)
# Optional on utterance finish or a debounced preview:
# suggestions = gemini_rank(suggestions, context='I want to')
```

Keep the gesture buffer. Backspace removes its last event and decodes again; cancel clears it. Inferring spaces does not infer when the wearer has finished: provide an utterance finish/confirm control. Limit a prototype utterance to 128 gestures. Local previews can be recomputed as input grows; a partial final word may temporarily give no match. No website server or live BLE adapter is included. Unknown/rejected labels raise an error rather than silently losing a letter position.

## Evaluate the 80–90% target

Target: intended words appear **first**, not merely among alternatives. It is unproven. With inferred spaces, measure aligned word accuracy, word error rate (WER), phrase accuracy and candidate coverage together. Offline correctness is a proxy; actual acceptance needs wearer confirmation/correction logs.

Held-out JSONL format:

```json
{"gestures":[2,4,2,4,4,2],"expected":"go home","context":"I want to"}
```

Expected text is scoring ground truth only; it is never sent to Gemini. Context contains only preceding confirmed text available in real use, never answers/future words. Expected phrases use lowercase ASCII words and single spaces.

```sh
python3 -B app/evaluate_t9.py app/evaluation.example.jsonl
python3 -B app/evaluate_t9.py work/heldout.jsonl --lexicon work/english.tsv
python3 -B app/evaluate_t9.py work/heldout.jsonl --lexicon work/english.tsv --gemini
python3 -B -m unittest discover -s app -p 'test_t9_decoder.py' -v
```

The included two-phrase fixture checks wiring, not accuracy. Reports include top-1 aligned word accuracy, WER (including extra words), top-1 exact phrase accuracy, top-3 phrase coverage, retained candidate coverage, lexicon coverage, abstentions and API fallbacks. No-match/uncertain phrases count as misses. Top-3 coverage is diagnostic, not the success criterion.

Prepare at least 100 separate phrases as an initial pilot, including collisions, names and repeated gestures. Freeze groups, vocabulary, beam, thresholds and prompt using development phrases only. Do not add test words just to improve scores. Evaluate perfect gesture streams first, then actual classifier recordings, reporting them separately. Include unknown words, missed gestures and duplicates.

## Next options

- **Implemented:** dictionary lattice + frequency beam + optional Gemini context ranking.
- **Next local alternative:** smoothed bigram/trigram language model trained on a licensed development corpus; adds word order without an API.
- **Later:** noisy-channel decoding using per-gesture probability distributions, to tolerate recognition errors. The current exact decoder does not repair wrong/missing/duplicate gestures.

Final grouping, full-vocabulary accuracy, live Gemini calls, activation and site feedback have not been validated by this change.
