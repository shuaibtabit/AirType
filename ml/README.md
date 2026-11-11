# Gesture collection and classification

After a successful hardware run, choose three easily repeated movements such as wrist flexion, outward rotation and a short flick. Treat idle and ordinary movement as background. Start with 30–50 prompted trials per gesture over at least two sessions and a continuous mixed session for false-trigger testing.

Save the original capture CSV and a label file with session ID, gesture, onset and offset on the host monotonic clock. Record wrist side, strap orientation, firmware and protocol version. Measure the delay from the wearer action to a complete BLE buffer before aligning strap timestamps with host markers. Flag gaps and incomplete frames in training windows.

Try a motion-energy onset detector with a quiet-period reset, followed by a simple classifier such as logistic regression or a small random forest using axis statistics, peak angular velocity, duration, and acceleration magnitude. Split by session before windowing or normalizing. Evaluate per-class precision/recall, false triggers per minute, onset latency and end-to-end latency including frame batching. Add gestures only after checking the confusion matrix.
