# AirType live demo

[airtype.py](airtype.py) consumes predictions from the bundled six-gesture model.
See [the main README](../README.md) for setup, discovery, and test status.

## Automatic decoding and rehearsal

Finder uses automatic decoding. A unique exact shortcut or a unique shortcut
within one missing, extra, or changed gesture resolves locally. Other
sequences go to OpenAI if a key is available, with the dictionary as a preview
fallback. In Terminal, use `--auto-decode` for the same routing. For a two-path
rehearsal, use `6315` for “Please walk to the door” and `24235` for “Go first.”
The sequence `52642` is one extra gesture away from the extension shortcut,
so automatic mode resolves it as that shortcut.

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

Use `--output type` to type into the focused app, `--output speak` for speech
only, or `--output both` to type and speak the same phrase. For Deepgram,
save its key with `python3 -B app/speak.py --save-key` or set
`DEEPGRAM_API_KEY`, then add `--speech-backend deepgram` to speech mode.
Playback follows the Mac's selected audio output.

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
`AIRTYPE_OPENAI_MODEL` to override the default Responses API model. Use
`--output type`, `--output speak`, or `--output both` to deliver an accepted
OpenAI suggestion. Dictionary alternatives stay in preview. The app does not
execute an agent action.

## Live controls

Build the overlay with `swift build`. Add `--controls` to the live
`--auto-decode` command. The floating
panel shows **Start** once the strap sends motion. If typing, click the target
document or prompt field first. Then click **Start**, make the gestures, wait
for the last digit to appear, and click **Finish**. **Clear** discards the
current sequence. Click **Start** again for the next sentence.

Typing requires macOS Accessibility permission. Use a document or unsent
draft for rehearsals. During live capture, the gesture code and decoder
status are saved to `events.log` beside the raw motion CSV.

## Launch from Finder

Run `sh app/build-mac-app.sh` once after installing the ML requirements.
Double-click **AirType.app** in the AirType folder. Keep the app there so it
can find the model, Python runner, and built capture tool.

Choose an output and voice in the setup window. Enter the WHOOP UUID
and paste the provider keys once, then click **Save keys** or **Connect**.
AirType stores both in macOS Keychain, regardless of output mode. In later
launches, leave fields marked **Saved in Keychain** blank to reuse them. Click **Connect**, focus the target
document, and use **Start** and **Finish** on the floating panel. Click
**Disconnect** to return to setup and switch outputs. For typing from Finder,
grant Accessibility access to **AirType** when macOS asks.
