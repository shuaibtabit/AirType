# Generative Gemini phrase decoder

Current primary experiment: a **generative Gemini LLM** proposes phrases directly
from the continuous gesture groups. This supersedes Gemini Decision as the primary
language step. Dictionary lookup remains a local baseline and optional comparison;
no new neural model is trained. Spaces are inferred automatically.

## Start here

From the repository root, with GEMINI_API_KEY set in your terminal:

```sh
python3 -m venv work/llm-venv
source work/llm-venv/bin/activate
python -m pip install -r app/requirements-llm.txt
python3 -B app/llm_decoder.py 242442 --context 'I want to'
```

Enable automatic text acceptance on a **finished utterance**:

```sh
python3 -B app/llm_decoder.py 242442 --context 'I want to' --auto-commit
```

The default model is gemini-3.5-flash-lite. Set --model or GEMINI_TEXT_MODEL to
another available generative model if your project lacks access. A successful
Decisions API test does not establish access to this model. This path uses the
Gemini Interactions API with structured JSON output and store=false, not the
Decisions endpoint. Standard-library validation runs locally; google-genai is
needed for live calls. No live Gemini test has run in the development workspace.

The request includes the mapping, group stream, allowed letters at each position,
and preceding confirmed text. It does not include expected test answers, wrist
sensor data, or the user's API key in prompt text. Keep the key on the backend.
It uses a 15-second request timeout, disables retries and automatic continuation,
and enables no tools. Actual end-to-end latency still needs measurement.

Gemini returns up to five phrases in ranked order. Code re-encodes each phrase
and requires exact equality to the entire input stream. Wrong letters, wrong
length, punctuation and extra words are filtered. A name absent from the
frequency dictionary can still pass. Rank-one validity alone does NOT prove the
intended meaning, grammar, or spelling. No dictionary word or sensor error is
silently repaired. A model cannot guarantee all possible phrases were found.

--auto-commit returns committed=true and committed_text only if the LLM's first
suggestion passes validation, status is ok, and the utterance is finalized.
An invalid top suggestion, uncertain status, API failure, missing key or no valid
output leaves committed=false. Preview calls in the backend should keep
finalized=False. The CLI treats --auto-commit as a finished utterance. The site
must apply each finalized request once, ignore stale responses after edits, show
committed text and offer undo. No site integration or agent actions are included.

Unlike Decision API probabilities, a generative model's self-reported confidence
is not an acceptance probability. We do not invent one or reuse the old 0.7 gate.
Automatic mode accepts the best constraint-valid suggestion by policy, not by a
measured correctness guarantee. It may still commit the wrong valid phrase.

## Phrase tests and results

Run the supplied **16 development examples** against the live model:

```sh
python3 -B app/llm_decoder.py --cases app/phrase_cases.jsonl --auto-commit > work/llm-results.json
```

This makes up to 16 API requests using your project quota/billing. Report top-1
aligned word accuracy, WER, exact phrase accuracy, top-3 coverage, invalid outputs,
API failures, auto-commit rate and correctness among commits. An uncertain or
failed response counts as a miss, not an excluded example. Expected labels are
used only for scoring and never sent to Gemini. Context must contain previously
confirmed words only.

The fixture includes go home, help me, hello world, i need water, please call me,
i am home, come back, stop now, my name is shayaan, we are home, can you help me,
yes, no, home, hope and zebra. It tests collisions, inferred boundaries and names.
These are development probes, not a held-out benchmark. The home/hope cases share
2442 and differ in preceding context.

For an arbitrary probe with no known intended phrase:

```sh
python3 -B app/llm_decoder.py 1234356435
```

We cannot score its accuracy without an intended phrase. The larger local
frequency baseline found e.g. "be in is unit" and "be in it unit"; those are
constraint-valid candidates, not meaningful or validated interpretations.

Offline checks (no real LLM responses):

```sh
python3 -B -m unittest discover -s app -p 'test_*decoder.py' -v
```

31 test methods pass: 18 existing baseline checks plus 13 LLM request/validation
checks. They include simulated responses for go home, help me, hello world,
i need water, please call me and a name, along with wrong letters/length/order,
uncertainty, duplicates, missing key, malformed response and API failure. Mocked
answers verify software behavior, NOT Gemini's semantic accuracy.

A real-vocabulary **local frequency-only** experiment inspected 50,000 wordfreq
entries and exported 47,973 ASCII words. On the 16 hand-chosen development cases,
it matched 17/35 target words under minimum-edit alignment and 5/16 whole phrases.
The intended phrase survived in the 32-path beam for 15/16 cases. These results
show why contextual language ranking is needed; they do not measure Gemini.
A compact results table is in [PHRASE_TEST_RESULTS.md](PHRASE_TEST_RESULTS.md).
Generated third-party vocabulary remains local under work/.

The 80–90% first-suggestion word goal remains unvalidated. After developing this
prompt, use a fresh phrase set with fixed groups and model version; test both
perfect gesture inputs and actual classifier recordings. Track real wearer
acceptance separately from offline text correctness.

## Dictionary / Gemini Decision comparison implementation

The remainder documents the previous local baseline and optional Decisions API
comparison. These remain runnable but are not the new primary LLM path.

### Continuous six-group predictive text

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
