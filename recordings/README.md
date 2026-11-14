# Shared AirType recordings

These are the six runs that captured motion. The strap was a WHOOP 5.0 on firmware `50.43.2.0`, captured on macOS `26.3`. The three guided pilots used the left wrist with the sensor on top.

| Recording | Samples | What happened |
| --- | ---: | --- |
| [01 — First live frame](01-first-live-frame/) | 99 | First sample batch after Mac pairing. The strap was off-wrist and the stream stopped after one batch. Use this as a protocol check. |
| [02 — Wrist motion check](02-wrist-motion-check/) | 2,098 | 20-second hardware validation. Still periods, wrist rotations and flexion. Movement was not individually labeled. |
| [03 — Ctrl-C stop check](03-ctrl-c-stop-check/) | 598 | Short hardware recording stopped with Ctrl-C to check cleanup. No gesture labels. |
| [04 — First palm-turn pilot](04-palm-turns-first-pilot/) | 6,199 | Six prompted turns, resets, walking and drinking cues. The wearer reported direction mix-ups. The first palm-up cue showed little movement in its window. Review before using as training data. |
| [05 — Slower palm turns and seated arm swings](05-palm-turns-seated-arm-swings/) | 6,199 | Six numbered turns with more time, then seated arm swings and a drinking cue. The wearer confirmed that the arm swings were performed seated, so this copy labels that cue `seated_arm_swings`. Turns 2 and 3 were ambiguous when checked against the cue windows. Used during detector development. |
| [06 — Palm-turn evaluation, walking and water](06-palm-turns-walking-and-water/) | 6,199 | Six numbered turns, actual walking, and a sip of water. The wearer confirmed following the prompts. On this held-out run, the original rule-based detector matched all six directions and made no extra calls during resets, walking, or drinking. |

`motion.csv` contains the unmodified sensor rows with six axes and timestamps. `cues.csv` marks when the prompt appeared, so review the trace before using it as the exact start or end of an action. `palm_up` corresponds to roll out, and `palm_down` to roll in. `reset` is the return to the starting pose. This set has no labeled tilt or sideways swing trials.

From the repository root, replay the evaluation capture without Bluetooth:

```sh
python3 -B ml/detect_turns.py recordings/06-palm-turns-walking-and-water/motion.csv
```

New captures are saved under the ignored `captures/` directory. Device IDs, diagnostic logs, and the two failed attempts with zero samples are omitted from this dataset.
