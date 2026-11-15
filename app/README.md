# AirType live demo

[airtype.py](airtype.py) consumes predictions from the bundled six-gesture model.
See [the main README](../README.md) for setup, discovery, and test status.

## Rehearsed phrases

Run from the repository root. In keyboard mode, type a code and press Enter to
finish. In live mode, replace `--keys` with the discovered UUID and
`--allow-mac-bond` after approving capture. Pause for six seconds after the last
gesture. The shortcuts work locally.

| Gesture code | Message |
| --- | --- |
| 2452 | Hey, my name is Shuaib. I am excited. |
| 5242 | Send email to prof asking for extension. |
| 6315 | Please walk to the door. |

```sh
printf '2452\n5242\nq\n' | python3 -B app/airtype.py --keys --phrase-demo --no-overlay
```

Use `--phrase-output type` with the overlay to type into the focused app.
Use `--phrase-output speak` for the Mac voice. To use Deepgram, save its key
with `python3 -B app/speak.py --save-key` or set `DEEPGRAM_API_KEY` and run
with `--speak`. Playback follows the Mac's selected audio output.

## Experimental three-letter prefix mode

Enter the first three letters of each word, or the whole word if it is shorter.
Enter the gesture groups continuously without a separator between words, then
pause for six seconds to finish the sentence. For example, `SEN EMA` becomes
`524241`. The local decoder looks up prefixes in [words.txt](words.txt) and
proposes word boundaries.

```sh
printf '524241\nq\n' | python3 -B app/airtype.py --keys --prefix-preview --no-overlay
```

With `OPENAI_API_KEY` set in the environment, add `--prefix-openai`:

```sh
printf '524241\nq\n' | python3 -B app/airtype.py --keys --prefix-preview --prefix-openai \
  --prefix-context 'Demo vocabulary: send, email, professor, extension' --no-overlay
```

OpenAI receives the full gesture code, the letter groups, dictionary candidates,
common words, and your optional context. Raw motion stays on the Mac. A
suggested sentence must encode back to the gesture string within one missing,
extra, or substituted gesture. If the request fails or the suggestion is
unsupported, AirType shows local candidates when available. Set
`AIRTYPE_OPENAI_MODEL` to override the default Responses API model. Add
`--speak` to play a supported OpenAI suggestion through Deepgram. Prefix mode
previews or speaks text and performs no requested action.
