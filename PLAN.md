# AirType development plan

## 1. Prove the sensor stream

- [x] Audit both upstream repositories and select the capture route.
- [x] Implement a local macOS executable with discover-only mode, bounded capture, timestamped CSV and stop handling.
- [x] Run connection-free discovery beside the user's strap. Note the device model, firmware and macOS version.
- [x] With the user's approval for the bonding risk, run the still → move → still capture and verify all six axes, timestamp order, effective rate, gaps, stop behavior and phone sync where applicable. Use the checklist in README.md.
- If the bond succeeds but the stream fails, inspect confirmed-write status, command responses, and framing rejects. Compare with NOOP's Raw Data Collector only with approval for its bonding and device behavior. If AirType discovers a different service profile, inspect evidence before broadening the parser.

Hardware validation on November 11, 2026: WHOOP 5.0, firmware 50.43.2.0, macOS 26.3. Connection-free discovery found the strap twice with phone Bluetooth off. The first capture failed at Hello with insufficient encryption and no pairing prompt. Putting the strap into pairing mode produced a Mac prompt and a short capture. The next run reused the Mac pairing.

- The timed wrist trial received 21 consecutive live R21 frames and 2,098 samples with all six axes over 20 seconds, about 100 samples per second, with zero framing rejects. Frame timestamps increased in order. Two frames had 99 samples each. Quiet acceleration was about 1.02 g, and rotation increased during movement. Four startup rows hit the minimum raw value on all three gyroscope axes and were excluded from the movement comparison.
- The timed stop and Ctrl-C stop were both acknowledged. The Ctrl-C run saved 6 frames and 598 samples with zero framing rejects. The user restored the phone pairing and confirmed that WHOOP synced.

## 2. Collect labeled gestures

Choose three separable gestures and include background motion. Capture prompted examples and a continuous session with rest, natural movement and gestures in different orders. Mark gesture onsets and offsets on the host monotonic clock. Use a hardware trial to measure delivery delay before aligning labels. Details are in [ml/README.md](ml/README.md).

## 3. Classify and segment

Train a small local baseline and evaluate it on a held-out recording session. Report per-class precision and recall, false activations per minute, segmentation error, and latency. Use the confusion matrix to decide whether to expand to six gestures. Test consecutive identical gestures before encoding letters.

## 4. Decode two-gesture characters

Map ordered pairs to characters in a versioned local codebook. Validate framing and correction in an in-app text buffer using known phrases, then compare character error rate and entry speed. See [app/README.md](app/README.md).

## 5. Optionally reconstruct words

Keep the raw decoded text visible. Use a local dictionary and candidate scores from the gesture classifier to propose completions or vowel restoration in an explicit abbreviated input mode. Measure top-k suggestions, correction burden, and wrong substitutions against the direct decoder on held-out phrases. Accept replacements only through an explicit user action.
