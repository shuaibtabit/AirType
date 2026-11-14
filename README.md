# AirType

AirType is a WHOOP wrist-gesture text-entry prototype. The current text design uses one gesture per letter group, infers spaces from a continuous stream, and uses a generative Gemini LLM to propose phrases, with exact gesture-to-letter validation. A dictionary decoder remains as a comparison baseline. It replaces the earlier two-gesture character design. See [app/README.md](app/README.md) for the runnable decoder and evaluation.

The Swift capture tool and Python demo decoder run without third-party packages; exporting a larger vocabulary optionally uses wordfreq. The capture tool targets macOS 13+ with Swift 5.9+. It implements the reverse-engineered WHOOP 5.0/MG `fd4b` capture path. The hardware validation results are recorded in PLAN.md; decoder accuracy and live site integration remain unvalidated.

## Open in Codex

In the Codex sidebar, choose the option to add or open a local project and select this **AirType** folder (the folder containing `Package.swift` and `.git`). Start a local chat in that project. A starting prompt is “Read AGENTS.md and PLAN.md. Walk me through WHOOP discovery first, then help me validate a local six-axis capture. Ask me before any pairing change.”

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
- `ml/` holds the gesture collection and classification design.
- `app/` holds the character encoding and text-entry design.
- [PLAN.md](PLAN.md) tracks milestones and evidence.
