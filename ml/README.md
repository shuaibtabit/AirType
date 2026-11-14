# Gesture collection and classification

After a successful hardware run, choose three easily repeated movements such as wrist flexion, outward rotation and a short flick. Treat idle and ordinary movement as background. Start with 30–50 prompted trials per gesture over at least two sessions and a continuous mixed session for false-trigger testing.

Save the original capture CSV and a label file with session ID, gesture, onset and offset on the host monotonic clock. Record wrist side, strap orientation, firmware and protocol version. Measure the delay from the wearer action to a complete BLE buffer before aligning strap timestamps with host markers. Flag gaps and incomplete frames in training windows.

Try a motion-energy onset detector with a quiet-period reset, followed by a simple classifier such as logistic regression or a small random forest using axis statistics, peak angular velocity, duration, and acceleration magnitude. Split by session before windowing or normalizing. Evaluate per-class precision/recall, false triggers per minute, onset latency and end-to-end latency including frame batching. Add gestures only after checking the confusion matrix.

## Roll model and held-out replay

The first model recognizes inward rolls, outward rolls, and repositioning from
gyroscope data. It uses the direction, speed, axis concentration, and duration
of each short movement. It takes no cue or pose input. Rows with blank estimated
sample times are skipped, and a timing gap ends any incomplete movement.

Use Python with scikit-learn and joblib. Train from reviewed local capture
folders whose `labels.json` files have purpose `training`. The trainer compares
logistic regression, an RBF SVM, and a small random forest by holding out one
whole training recording at a time. Development scores cover reviewed movements.
Unlabeled time does not contribute confirmed false positive counts.

```sh
python3 -B ml/roll_model.py train captures/TRAIN_1 captures/TRAIN_2 captures/TRAIN_3 --output captures/roll-model.joblib
python3 -B ml/roll_model.py replay captures/TEST_RUN/motion.csv --model captures/roll-model.joblib
```

Use `record_pilot.py --roll-poses --holdout normal` and `--holdout varied` with
the usual device UUID and pairing opt-in to record the two evaluation sessions.
Review actual movement spans against the cues and wearer notes. Save reviewed
labels with purpose `evaluation` before scoring. The scorer rejects training
captures and lists unmatched command predictions for review against the motion
trace. Report those as false triggers only where the background or return is
confirmed. Use only the model file saved by the local trainer.

```sh
python3 -B ml/roll_model.py score captures/TEST_RUN --model captures/roll-model.joblib
```

For a live readout, pass the saved model file to `ml/live.py` with the device UUID
and the pairing opt-in. The model prints roll commands and keeps the raw CSV in
the session folder. Start with your arm in any comfortable position.
Live readout and offline replay require at least 25° of signed rotation with
at least 88% of gyroscope energy on the roll axis and a sign matching the
model's command direction. This rejects some ordinary movements before they
reach the readout. The thresholds apply to the two-roll model. To try the
same readout without a Bluetooth connection, use `--replay`.

```sh
python3 -B ml/live.py '<UUID from discovery>' --allow-mac-bond --model captures/roll-model.joblib
python3 -B ml/live.py --replay captures/TEST_RUN/motion.csv --model captures/roll-model.joblib
```

## Standing six-gesture demo prototype

Record single gestures in front with `--six-training`, and at the side with
`--six-training --arm-position side`. Use `--six-mixed` for sequences in both
positions, with repositioning and ordinary movement between commands. Use a
separate `--six-mixed --holdout varied` recording for evaluation. The pilot
commands still require the UUID and `--allow-mac-bond`.

```sh
python3 -B ml/six_model.py review captures/RUN --skip 7 18
python3 -B ml/six_model.py train captures/TRAIN_FRONT captures/TRAIN_SIDE captures/TRAIN_MIXED --output captures/six-model.joblib
python3 -B ml/six_model.py score captures/TEST_MIXED --model captures/six-model.joblib
python3 -B ml/live.py '<UUID from discovery>' --allow-mac-bond --six-model captures/six-model.joblib
```

Omit `--skip` if all numbered cues were followed. The review command exports
cue-aligned draft labels to `six-labels.json`. Check the exclusions and the
wearer's notes before fitting or scoring. Background examples include reset
and ordinary motion cues. The model uses gyroscope and accelerometer features
and ignores low-confidence predictions. The score lists coverage, errors by
arm position, false commands in reviewed background intervals, and exact mixed
sequences. Review commands from unlabeled intervals before interpreting the
result. For the shared model, use `models/six-model.joblib` in live or replay mode.
Install [the tested ML dependency versions](requirements.txt). Load models you trust.

## Decoder interface

Current text design is one gesture per letter group with automatically inferred spaces, not gesture pairs. The classifier should emit one event label for each intended letter position, preserving repeated gestures. app/t9_decoder.py accepts group IDs or exact gesture names. Keep unknown/rejected events explicit so the UI can request correction; do not silently delete letter positions. Final groups and the live adapter remain to be selected. See [the decoder guide](../app/README.md).
