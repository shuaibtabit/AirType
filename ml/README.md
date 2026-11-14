# Gesture collection and classification

After a successful hardware run, choose three easily repeated movements such as wrist flexion, outward rotation and a short flick. Treat idle and ordinary movement as background. Start with 30–50 prompted trials per gesture over at least two sessions and a continuous mixed session for false-trigger testing.

Save the original capture CSV and a label file with session ID, gesture, onset and offset on the host monotonic clock. Record wrist side, strap orientation, firmware and protocol version. Measure the delay from the wearer action to a complete BLE buffer before aligning strap timestamps with host markers. Flag gaps and incomplete frames in training windows.

Try a motion-energy onset detector with a quiet-period reset, followed by a simple classifier such as logistic regression or a small random forest using axis statistics, peak angular velocity, duration, and acceleration magnitude. Split by session before windowing or normalizing. Evaluate per-class precision/recall, false triggers per minute, onset latency and end-to-end latency including frame batching. Add gestures only after checking the confusion matrix.

## Decoder interface

Current text design is one gesture per letter group with automatically inferred spaces, not gesture pairs. The classifier should emit one event label for each intended letter position, preserving repeated gestures. app/t9_decoder.py accepts group IDs or exact gesture names. Keep unknown/rejected events explicit so the UI can request correction; do not silently delete letter positions. Final groups and the live adapter remain to be selected. See [the decoder guide](../app/README.md).
