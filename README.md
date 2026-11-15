# AirType

AirType turns wrist movements from a WHOOP 5.0 into text on a Mac. The six-gesture model recognizes roll in/out, tilt up/down, and swing left/right. The live demo maps each recognized gesture to a letter group and shows candidate words in a floating overlay.

## Run the macOS app

Install the Python dependencies and build the Finder app from the repository root.
The Swift capture and overlay target macOS 13+ with Swift 5.9+.

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r ml/requirements.txt
sh app/build-mac-app.sh
```

1. Run `.build/debug/airtype-capture discover` and copy the UUID for your strap.
2. Open **AirType.app** from the AirType folder in Finder. Enter your UUID and choose an output such as **Type only** or **Type and speak**.
3. For new sentences, enter an OpenAI key. For Deepgram playback, select **Deepgram** and enter its key. **Save keys** stores them in macOS Keychain. Select AirPods in macOS Sound if you want audio there.
4. Click **Connect**. For typing, grant AirType macOS Accessibility permission and click into the target document. Use **Start** to begin a sequence, **Clear** to retry, and **Finish** to decode it. **Disconnect** returns to setup.

AirType automatically checks for an exact shortcut or a unique shortcut within one gesture edit. Other sequences use the dictionary and optional OpenAI decoding. Enter the first three letters of each word (all letters if shorter) without a separate space gesture. Uncertain dictionary candidates stay in preview. Raw motion stays on the Mac when using these services. OpenAI receives the gesture groups and dictionary context, and Deepgram receives the finished text.

Try the shortcuts without Bluetooth:

```sh
printf '2452\n6315\nq\n' | python -B app/airtype.py --keys --auto-decode --no-overlay
```

For a gesture-only hardware check, use the same model in the Terminal readout.

```sh
python -B ml/live.py '<UUID from discovery>' --allow-mac-bond --six-model models/six-model.joblib
```

See [demo commands and shortcuts](app/README.md) for the letter-group layout, OpenAI preview, and Terminal speech setup.

## What has been verified

- WHOOP 5.0 hardware capture and Ctrl-C cleanup work on the tested Mac. The strap delivered about 100 samples per second in roughly one-second batches.
- The frozen six-gesture model got 43 of 44 reviewed movements and 14 of 16 exact sequences on a separate mixed recording, with three false commands during reviewed background motion. The wearer reported one unidentified execution mistake, so these counts use the reviewed cue-aligned movements.
- The six-gesture readout ran live with all six labels represented, 32 calls, and no framing rejects. This was an unguided rehearsal, so the call count is not an accuracy score. Repeated tilt-up and its downward return remain trouble spots.
- Live logs show all three rehearsed shortcuts resolving in the macOS panel and accepted OpenAI suggestions from wrist input. Combined typing and Deepgram playback still need an end-to-end rehearsal.

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
