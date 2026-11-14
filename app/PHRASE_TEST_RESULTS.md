# Local frequency baseline: development probes

No live Gemini result is included. Source vocabulary: wordfreq 3.1.1, top 50,000 source entries, filtered to 47,973 ASCII words. Mapping is illustrative; beam size 32. Expected phrases were hand-chosen development probes, not held-out evaluation.

| Gesture input | Intended phrase | Local top suggestion | Intended phrase retained? |
| --- | --- | --- | --- |
| `242442` | go home | go home | yes |
| `223442` | help me | help of | yes |
| `2233464531` | hello world | hello world | yes |
| `3422161525` | i need water | i need water | yes |
| `432152113342` | please call me | please call of | yes |
| `3142442` | i am home | lane one | yes |
| `14421113` | come back | comeback | yes |
| `5544446` | stop now | stop now | yes |
| `464142355216114` | my name is shayaan | my panels shaw can | no |
| `621522442` | we are home | what he one | yes |
| `114646223442` | can you help me | can you help of | yes |
| `625` | yes | yet | yes |
| `44` | no | on | yes |
| `2442` | home | home | yes |
| `2442` | hope | home | yes |
| `62151` | zebra | what a | yes |

17/35 aligned target words correct (48.6%); 5/16 exact phrases correct; 15/16 intended phrases retained. These are local unigram results, not LLM accuracy. The absent personal name illustrates the vocabulary limitation.

Run generative Gemini on the same cases with `python3 -B app/llm_decoder.py --cases app/phrase_cases.jsonl --auto-commit`. A fresh test set is still needed after development.
