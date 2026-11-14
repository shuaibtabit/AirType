# AirType hackathon handoff

AirType is a Mac prototype for silent text entry using a WHOOP 5.0 on your wrist. The pipeline is **motion capture → gesture detection → text entry**. We have live capture and an offline detector for two gestures. Text entry is still a design.

## What works

- **Live capture.** Swift and CoreBluetooth record three accelerometer axes and three gyroscope axes, with raw values and timestamps. A 20-second hardware run on WHOOP 5.0 firmware `50.43.2.0` and macOS `26.3` produced 2,098 samples at about 100 Hz. The strap delivers samples in roughly one-second batches. Normal stop, Ctrl-C, and phone sync after re-pairing all passed.
- **Guided recording.** [The pilot script](ml/record_pilot.py) saves the motion CSV, timed cues, and session details locally. It supports the original palm-turn protocol and a six-gesture protocol. Cue timestamps tell you when the prompt appeared. Review the trace or the wearer's notes before treating them as exact movement boundaries.
- **Palm-turn detection.** [The detector](ml/detect_turns.py) replays a motion CSV without reading cues. It looks for rotation mainly around the strap's X axis, uses the sign to distinguish directions, and checks that the turn starts near the calibrated thumb-up pose to avoid counting returns. These are hand-written rules. On one fresh guided run, it matched all six turns and made no extra detections during resets, walking, or drinking water. That result applies to the tested left-wrist strap placement.

## Run it

Requires macOS 13+, Swift 5.9+, and Python 3 for the pilot. From the repo root:

```sh
swift build
swift test
.build/debug/airtype-capture discover
```

Discovery scans without connecting. The phone may need Bluetooth temporarily turned off for the strap to appear. Capture uses an encrypted Bluetooth connection and may replace the phone's saved pairing. Get the strap owner's approval before capturing. Restore phone Bluetooth and confirm sync in the WHOOP app afterward. If the Mac reports a stale pairing, see the pairing section in the [README](README.md) before retrying.

With the UUID printed by discovery, choose a pilot:

```sh
# Guided palm turns, followed by offline detector output.
python3 -B ml/record_pilot.py '<UUID from discovery>' --allow-mac-bond --detect

# Guided roll, tilt, and swing collection.
python3 -B ml/record_pilot.py '<UUID from discovery>' --allow-mac-bond --six-gestures
```

Recordings go under `captures/`. Keep raw recordings, cue logs, and device IDs out of Git. To replay an existing local CSV without connecting to Bluetooth, run `python3 -B ml/detect_turns.py /path/to/motion.csv`.

## What to build next

1. **Test all six directions.** Keep the elbow supported and start with the thumb up. Roll in and out turn the palm down and up. Tilt up and down lift and lower the forearm from the elbow. Swing left and right pivot the forearm sideways. Collect repeated examples across sessions and include returns, walking, reaching, and drinking. The six-gesture pilot collects examples. Tilt and swing recognition still need validation.
2. **Train and score a gesture model.** Compare it with the rule-based detector on separate recordings. Measure which gestures get confused, how often extra calls happen during everyday motion, and how long feedback takes. Check repeated gestures and how the detector handles the return to neutral.
3. **Prototype text entry in a local text buffer.** Six gestures give 36 ordered pairs for exact letters and controls. A second option groups letters into six buckets and uses word context to infer the intended text from one gesture per letter. Compare entry speed and correction effort before choosing a default. A tap for space and a shake for undo are ideas to test if the six directions work well.

The [project plan](PLAN.md) has the hardware results and milestones. The [protocol notes](research/whoop-ble.md) explain the WHOOP stream and pairing behavior.
