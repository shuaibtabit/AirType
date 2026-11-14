"""Record one guided AirType session with timestamped cue boundaries."""

import argparse
import csv
import json
import queue
import signal
import subprocess
import tempfile
import threading
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECORDER = ROOT / ".build/debug/airtype-capture"
DURATION = 60

PALM_TURNS = [
    (f"palm_{direction}", f"PALM {direction.upper()}. Turn toward the {target} once, then hold.")
    for direction, target in (
        ("up", "ceiling"), ("down", "floor"), ("down", "floor"),
        ("up", "ceiling"), ("down", "floor"), ("up", "ceiling"),
    )
]
SIX_GESTURES = [
    ("roll_in", "ROLL IN. Turn your palm toward the floor, then hold."),
    ("tilt_up", "TILT UP. Raise your forearm from the elbow, then hold."),
    ("swing_right", "SWING RIGHT. Pivot your forearm right, thumb up, then hold."),
    ("roll_out", "ROLL OUT. Turn your palm toward the ceiling, then hold."),
    ("tilt_down", "TILT DOWN. Lower your forearm from the elbow, then hold."),
    ("swing_left", "SWING LEFT. Pivot your forearm left, thumb up, then hold."),
]
BACKGROUND_CUES = [
    (39, "walk", None, "Walk normally near the Mac. Keep the screen in view."),
    (47, "transition", None, "Return to the table and get ready for a sip."),
    (50, "drink", None, "Pick up your cup, take a sip, and set it down normally."),
    (58, "rest", None, "Rest your wrist until recording ends."),
]


def cue_schedule(gestures, starting_pose):
    cues = [(0, "rest", None, starting_pose)]
    for turn, (label, instruction) in enumerate(gestures, start=1):
        start = 3 + 6 * (turn - 1)
        cues += [
            (start, label, turn, f"Turn {turn} of {len(gestures)}: {instruction}"),
            (start + 3, "reset", turn, f"Reset after turn {turn}: return slowly to your starting pose, thumb up."),
        ]
    return cues + BACKGROUND_CUES


def forward_log(stream, log, messages):
    for line in stream:
        log.write(line)
        log.flush()
        print(line.rstrip(), flush=True)
        if line.startswith("Received live R21 data."):
            messages.put(time.monotonic())
    messages.put(None)


def record(folder, device, cues_to_run, recorder=RECORDER):
    messages = queue.Queue()
    with (
        (folder / "motion.csv").open("wb") as motion,
        (folder / "motion.log").open("w") as log,
        (folder / "cues.csv").open("w", newline="") as cues,
    ):
        writer = csv.writer(cues)
        writer.writerow(["cue", "scheduled_s", "host_monotonic_s", "host_unix_s", "turn_number"])
        cues.flush()
        process = subprocess.Popen(
            [str(recorder), "capture", str(device), "--allow-mac-bond", str(DURATION)],
            stdout=motion, stderr=subprocess.PIPE, text=True, start_new_session=True,
        )
        with process.stderr as stderr:
            reader = threading.Thread(target=forward_log, args=(stderr, log, messages))
            reader.start()
            try:
                started = messages.get()
                if started is not None:
                    for offset, label, turn, instruction in cues_to_run:
                        try:
                            messages.get(timeout=max(0, started + offset - time.monotonic()))
                            break
                        except queue.Empty:
                            writer.writerow([label, offset, time.monotonic(), time.time(), turn])
                            cues.flush()
                            print(f"\n\a>>> {instruction}", flush=True)
                process.wait()
            except KeyboardInterrupt:
                if process.poll() is None:
                    process.send_signal(signal.SIGINT)
            finally:
                status = process.wait()
                reader.join()
    return status


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("device", type=uuid.UUID, help="Bluetooth UUID from AirType discovery")
    parser.add_argument("--allow-mac-bond", action="store_true", required=True)
    parser.add_argument("--detect", action="store_true", help="Replay the capture to detect palm turns")
    parser.add_argument("--six-gestures", action="store_true",
                        help="Record roll, tilt and swing in both directions")
    args = parser.parse_args()
    if not RECORDER.is_file():
        parser.error("Run swift build in AirType first.")
    wrist = input("Which wrist is wearing the WHOOP? [left/right] ").strip().lower()
    if wrist not in ("left", "right"):
        parser.error("Enter left or right.")
    orientation = input("Describe the strap position (e.g. sensor on top of wrist): ").strip()
    if not orientation:
        parser.error("Enter a short strap position description.")

    captures = ROOT / "captures"
    captures.mkdir(exist_ok=True)
    folder = Path(tempfile.mkdtemp(prefix="gesture-pilot.", dir=captures))
    if args.six_gestures:
        schedule = cue_schedule(SIX_GESTURES, "Support your elbow, forearm clear to pivot, thumb up.")
    else:
        schedule = cue_schedule(PALM_TURNS, "Rest your forearm on the table, thumb up.")
    metadata = {"session": folder.name, "wrist": wrist, "strap_position": orientation,
                "protocol": "six_gestures" if args.six_gestures else "palm_turns",
                "cue_times": "Prompt times only. Compare host_unix_s with motion.csv. "
                             "Sample motion times and cue times need alignment before training."}
    (folder / "session.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(f"Saving to {folder}", flush=True)
    status = record(folder, args.device, schedule)
    if status == 0 and args.detect:
        from detect_turns import replay

        try:
            replay(folder / "motion.csv")
        except (OSError, ValueError, KeyError) as error:
            parser.exit(1, f"Could not replay motion: {error}\n")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
