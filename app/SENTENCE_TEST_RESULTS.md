# Fresh full-sentence evaluation

Twelve assistant-authored sentences, not copied from the user's examples. No context or intended answers are supplied to inference. Inputs were encoded once with illustrative-v1-not-final; the prompt/model was not tuned on these results. This small authored set does not establish general or wearer accuracy.

Cases SHA256: `7a41e26fabd88164ef0726958391c19b935a32c77b5db52ba5a861d6fe8c5bf7`.

## Local baseline: executed, not Gemini

47,973 ASCII words exported from the top 50,000 wordfreq 3.1.1 entries; beam 32. Ground truth is used for scoring only.

| ID | Expected | Actual local top suggestion |
| --- | --- | --- |
| sentence_01 | the meeting starts after lunch | the meeting starts after lunch |
| sentence_02 | could you open the window | could you open the window |
| sentence_03 | i left the keys beside the door | light the jews beside the a not |
| sentence_04 | the train arrives in twenty minutes | the train arrives in twenty minutes |
| sentence_05 | we should bring jackets because it might rain | we should bring jackets because is might rain |
| sentence_06 | please move the blue chair next to the desk | please move the blue chair next to the desk |
| sentence_07 | my sister sent a message about dinner tonight | my sisters for a message about dinner tonight |
| sentence_08 | did you remember to charge the camera battery | did you remember to charge the camera battery |
| sentence_09 | i think the package was delivered to our neighbor | i think the package was delivered to out neighbor |
| sentence_10 | after the movie ends we can walk to the station | after the now keep drug can walk to the station |
| sentence_11 | although the instructions looked simple the final step took longer than expected | although the instructions looked simple the final step took longer than expected |
| sentence_12 | if the weather stays clear tomorrow we could visit the museum before meeting our friends for dinner | if the weather stays clear tomorrow we could visit the museum before meeting out friends for dinner |

- 92/104 target words matched under minimum-edit alignment: **88.5% aligned word accuracy**.
- 13 word edits / 104 reference words: **12.5% WER**, including insertions.
- **6/12 exact full sentences: 50%.**
- Intended sentence in top three: 10/12. Retained anywhere in beam: 11/12.
- Perfect synthetic gestures only; not hardware recordings, not real user acceptance, and not Gemini. All 12 cases required beam pruning.

## Live LLM: blocked by missing credentials

Neither GEMINI_API_KEY nor GOOGLE_API_KEY is configured in the execution workspace. The evaluator reports missing_key; no live Gemini request has been made and there are no LLM recognition results to report. Do not interpret missing-key zeros as recognition accuracy.

On the Mac with the key already set and the PR branch checked out:

```sh
python3 -m pip install -r app/requirements-llm.txt
python3 -B app/llm_decoder.py --cases app/sentence_cases.jsonl --auto-commit > work/sentence-llm-results.json
```

This sends at most twelve requests, consuming quota and potentially incurring charges. Only the mapping, gesture stream, allowed letters and empty context are sent, not expected answers. Review predictions, invalid suggestions, latency, abstentions, auto-commit rate and accuracy. A sentence can be letter-valid yet express the wrong intention. Run a new sentence set after changing the prompt or mapping.
