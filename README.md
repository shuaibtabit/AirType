# AirType

AirType turns wrist movements from a WHOOP 5.0 into text on a Mac. The six-gesture model recognizes roll in/out, tilt up/down, and swing left/right. The live demo maps each recognized gesture to a letter group and shows candidate words in a floating overlay.

## Try the demo

The Swift capture and overlay target macOS 13+ with Swift 5.9+. The ML model was tested with Python 3.9 and the pinned dependencies below. Run from the repository root.

```sh
swift build
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r ml/requirements.txt
```

Check the text path without Bluetooth. This sample shows “go home” in Terminal.

```sh
printf '24 2442\nq\n' | python -B app/airtype.py --keys --no-overlay --no-typing
```

For the live demo, discover your strap as described below and use the UUID printed beside it. The overlay opens in preview mode with this command. `--always-on` skips the experimental double-tap activation.

```sh
python -B app/airtype.py '<UUID from discovery>' --allow-mac-bond --always-on --no-typing
```

The overlay currently uses a short pause between words and a longer pause to finish the sentence. For a gesture-only check, use the same model in the Terminal readout.

```sh
python -B ml/live.py '<UUID from discovery>' --allow-mac-bond --six-model models/six-model.joblib
```

The [demo modes](app/README.md) include rehearsed phrase shortcuts and an experimental three-letter prefix decoder with optional OpenAI sentence suggestions.

## Speech

`--speak` says each finished sentence aloud with Deepgram, on the Mac's current audio output (AirPods when connected and selected in System Settings → Sound). It sends the sentence to Deepgram. Store the key once in the macOS Keychain, with a hidden prompt, and nothing else is needed:

```sh
python3 -B app/speak.py --save-key      # once; paste the key at the hidden prompt
python3 -B app/speak.py "hello"        # quick check
python -B app/airtype.py '<UUID from discovery>' --allow-mac-bond --always-on --no-typing --speak
```

The `DEEPGRAM_API_KEY` environment variable also works. Never put the key in a file in the repository. From code, call `speak_in_background(text)` from `app/speak.py`.

## What has been verified

- WHOOP 5.0 hardware capture and Ctrl-C cleanup work on the tested Mac. The strap delivered about 100 samples per second in roughly one-second batches.
- The frozen six-gesture model got 43 of 44 reviewed movements and 14 of 16 exact sequences on a separate mixed recording, with three false commands during reviewed background motion. The wearer reported one unidentified execution mistake, so these counts use the reviewed cue-aligned movements.
- The six-gesture readout ran live with all six labels represented, 32 calls, and no framing rejects. This was an unguided rehearsal, so the call count is not an accuracy score. Repeated tilt-up and its downward return remain trouble spots.
- The overlay path works in offline replay and keyboard tests. A full live sentence through the overlay, double-tap activation, and typing into another app still need a rehearsal. Typing mode requires macOS Accessibility permission for the Terminal or app launching AirType.

See [the hackathon handoff](HACKATHON.md) for the demo checklist and [the plan](PLAN.md) for next steps.

## Build and discover

In Terminal on the Mac with the wearable nearby, open the AirType folder, then run:

```sh
swift build
swift test
.build/debug/airtype-capture discover
```

If macOS prompts for Bluetooth access, allow the terminal or app running the tool. Check System Settings → Privacy & Security → Bluetooth if access is denied. Discovery scans for the `fd4b` service and prints the UUID and name for each result. It sends no commands and makes no Bluetooth connection. A phone-connected strap may be absent. Leave the phone setup intact and record what discovery reports.

## Pairing and capture

WHOOP 5.0's proprietary command channel needs an encrypted link. The capture command sends a confirmed Hello, which may prompt macOS to establish a bond. NOOP reports that changing the bond can interrupt phone syncing and require pairing again through the official WHOOP app. A successful standard heart-rate reading does not establish access to IMU data.

Only run capture after you explicitly accept that risk for your strap. Cancel any unexpected pairing prompt. If discovery fails or the Hello reports insufficient authentication or encryption, stop and review the failure before changing anything. Leave firmware, phone Bluetooth settings, and existing pairing intact during initial discovery. If an approved experiment changes the bond, use WHOOP's official in-app pairing procedure to restore phone syncing. [WHOOP setup and pairing](https://support.whoop.com/s/article/Setting-Up-Your-WHOOP-4-0?language=en_US)

Use the UUID printed by discovery. Keep the strap still for the first few seconds, rotate and flex the wrist, then return it to rest. The capture window starts on the first live R21 frame.

```sh
mkdir -p captures
set -o noclobber
.build/debug/airtype-capture capture '<UUID from discovery>' --allow-mac-bond 20 \
  > captures/first-motion.csv 2> captures/first-motion.log
```

Use Ctrl-C to stop early. The tool attempts both stop writes before disconnecting. Check the log if the strap disconnects, a write times out, or cleanup cannot be confirmed. Choose new output filenames for repeated runs.

## Hardware pass criteria

- Record the WHOOP model and firmware as shown in the phone app, along with macOS version, duration, pairing context, and any errors. Keep identifiers and raw captures local.
- Confirm live R21 frames continue throughout the 20-second run and each emitted row has all six axes. In a full buffer, expect 100 rows. Check for partial buffers, missing intervals, and unexpected jumps in record index and strap time.
- Compare the still → motion → still intervals. Acceleration magnitude should be roughly 1 g at rest, and gyroscope magnitude should rise during rotation and settle near zero at rest. Inspect changing raw values as well as scaled values.
- Verify normal stop and repeat once with Ctrl-C. Check official phone syncing after any authorized bond change.

For a quick look after the run:

```sh
head -5 captures/first-motion.csv
wc -l captures/first-motion.csv
cat captures/first-motion.log
```

The CSV has one row per paired sample. It preserves strap Unix seconds and fractional ticks, record and sample indices, sensor counts, all six signed raw values, and their provisional scaling in g and rad/s. Host Unix time and monotonic uptime record when the notification completing a frame reached the Mac. These timestamps repeat across a batch. The estimated per-sample Unix time assumes 100 Hz for full buffers and is blank for partial buffers or invalid fractional ticks. Keep frame counts and gaps visible during analysis.

## Project layout

- `sensor/` holds the capture executable and protocol tests.
- `research/` holds the source audit, firmware evidence, and local checkout locations.
- `ml/` contains the prompted recorder, training, evaluation, and live gesture readout.
- `app/` contains the live demo.
- `models/` holds the two fitted gesture models.
- [PLAN.md](PLAN.md) tracks milestones and evidence.
