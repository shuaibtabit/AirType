"""Record one guided AirType session with timestamped cue boundaries."""

import argparse
import csv
import json
import queue
import random
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
ROLL_TRAINING_CYCLES = 4
STOP_TIMEOUT = 20

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


STANDING_POSES = {
    "front": "Stand with your elbow bent near your ribs, forearm ahead, thumb up.",
    "side": "Stand with your upper arm at your side. Bend your elbow slightly so your hand hangs a little forward and can move up, down, left or right.",
}


def six_training_schedule(rng, repetitions, arm_position):
    pose = STANDING_POSES[arm_position]
    cues = [(0, "arm_" + arm_position, None, pose)]
    seconds = 4
    trial = 0
    total = repetitions * len(SIX_GESTURES)
    for round_number in range(repetitions):
        if round_number == repetitions // 2:
            cues.append((seconds, "background", None,
                         "For 12 seconds, move your arm naturally: lower it, reach, and bring it back. No commands."))
            seconds += 12
            cues.append((seconds, "rest", None, pose + " Follow the next cue."))
            seconds += 3
        gestures = list(SIX_GESTURES)
        rng.shuffle(gestures)
        for label, instruction in gestures:
            trial += 1
            cues.append((seconds, label, trial, f"Turn {trial} of {total}: {instruction}"))
            cues.append((seconds + 2, "reset", trial, "Reset. Return to your starting position and wait."))
            seconds += 4
    cues += [
        (seconds, "walk", None, "Walk normally for 10 seconds without intentional gestures."),
        (seconds + 10, "drink", None, "Take a normal sip using the WHOOP hand. No commands."),
        (seconds + 20, "rest", None, "Relax. Recording ends in a few seconds."),
    ]
    return cues


def six_mixed_schedule(rng):
    sequences = [
        ("roll_in", "roll_out", "tilt_up"),
        ("tilt_down", "swing_left", "swing_right"),
        ("roll_out", "roll_in", "tilt_down"),
        ("swing_right", "tilt_up", "swing_left"),
        ("tilt_up", "tilt_down", "roll_out"),
        ("swing_left", "swing_right", "roll_in"),
        ("roll_out", "roll_out"),
        ("tilt_up", "tilt_up"),
    ]
    cues = []
    seconds = 0
    trial = 0
    for position in ("front", "side"):
        cues.append((seconds, "background", None, STANDING_POSES[position]))
        seconds += 5
        cues.append((seconds, "arm_" + position, None, "Ready. Wait for the sequence preview."))
        seconds += 1
        rng.shuffle(sequences)
        for sequence in sequences:
            names = " → ".join(gesture.replace("_", " ").upper() for gesture in sequence)
            cues.append((seconds, "rest", None, f"Next sequence: {names}. Get comfortable and wait for GO."))
            seconds += 2
            previous = None
            for gesture in sequence:
                if gesture == previous:
                    cues.append((seconds, "reposition", None, "Make room for the repeat. This movement is background."))
                    seconds += 2
                trial += 1
                name = gesture.replace("_", " ").upper()
                cues.append((seconds, gesture, trial, f"GO {trial}: {name} once. Stop briefly before the next cue."))
                seconds += 2
                previous = gesture
            cues.append((seconds, "reset", None, "Sequence over. Relax and get comfortable."))
            seconds += 2
    cues += [
        (seconds, "walk", None, "Walk naturally for 10 seconds. No commands."),
        (seconds + 10, "drink", None, "Take a normal sip using the WHOOP hand. No commands."),
        (seconds + 20, "rest", None, "Relax until recording stops."),
    ]
    return cues


def roll_pose_schedule(cycles=1):
    """Record the same command and repositioning trials in two standing poses."""
    poses = [
        ("arm_front", "Stand with your elbow comfortably bent and your hand in front."),
        ("arm_side", "Stay standing and let your arm hang at your side."),
    ]
    trials = [
        (3, "roll_in", 1, "Command 1 of 2: ROLL IN."),
        (5, "roll_out", 1, "Command 2 of 2: ROLL OUT from where you ended."),
        (7, "reposition", 1, "Trial over. Get comfortable with room to roll outward next."),
        (9, "roll_out", 2, "Command 1 of 2: ROLL OUT."),
        (11, "roll_in", 2, "Command 2 of 2: ROLL IN from where you ended."),
        (13, "reposition", 2, "Trial over. Get comfortable with room to roll inward next."),
        (15, "roll_in", 3, "Single command: ROLL IN."),
        (17, "reposition", 3, "Relax back outward naturally. That movement is ordinary repositioning."),
        (20, "roll_out", 4, "Single command: ROLL OUT."),
        (22, "reposition", 4, "Relax back inward naturally. That movement is ordinary repositioning."),
        (25, "rest", None, "Pause in any comfortable position."),
    ]
    cues = []
    blocks = poses * cycles
    for block, (pose, instruction) in enumerate(blocks):
        offset = 28 * block
        prefix = f"Block {block + 1} of {len(blocks)}. " if cycles > 1 else ""
        cues.append((offset, pose, None, prefix + instruction + " Leave room to roll inward first."))
        for seconds, label, number, instruction in trials:
            trial = 4 * block + number if number is not None else None
            prompt = f"Trial {trial}: {instruction}" if trial is not None else instruction
            cues.append((offset + seconds, label, trial, prompt))
    background = 28 * len(blocks) - 2
    return cues + [
        (background, "background", None, "Move your arm naturally, like reaching or adjusting your sleeve."),
        (background + 4, "rest", None, "Relax until recording ends."),
    ]


def forward_log(stream, log, messages):
    for line in stream:
        log.write(line)
        log.flush()
        print(line.rstrip(), flush=True)
        if line.startswith("Received live R21 data."):
            messages.put(time.monotonic())
    messages.put(None)


def record(folder, device, cues_to_run, recorder=RECORDER, *, duration=DURATION):
    extended = duration > DURATION
    command = ["stream" if extended else "capture", str(device), "--allow-mac-bond"]
    if not extended:
        command.append(str(duration))
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
            [str(recorder), *command],
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
                if started is not None and extended:
                    try:
                        messages.get(timeout=max(0, started + duration - time.monotonic()))
                    except queue.Empty:
                        pass  # Scheduled end. Ask the recorder to stop in finally.
                else:
                    process.wait()
            except KeyboardInterrupt:
                print("\nStopping.", flush=True)
            finally:
                if process.poll() is None:
                    process.send_signal(signal.SIGINT)
                try:
                    status = process.wait(timeout=STOP_TIMEOUT)
                except subprocess.TimeoutExpired:
                    print("Recorder did not stop in time. Strap cleanup is unconfirmed.", flush=True)
                    process.kill()
                    process.wait()
                    status = 1
                reader.join()
    return status


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("device", type=uuid.UUID, help="Bluetooth UUID from AirType discovery")
    parser.add_argument("--allow-mac-bond", action="store_true", required=True)
    parser.add_argument("--detect", action="store_true", help="Replay the capture to detect palm turns")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--six-gestures", action="store_true",
                      help="Record roll, tilt and swing in both directions")
    mode.add_argument("--six-training", action="store_true",
                      help="Collect repeated standing examples of six gestures and ordinary movement")
    mode.add_argument("--six-mixed", action="store_true",
                      help="Record mixed standing sequences and repeats in both arm positions")
    mode.add_argument("--roll-poses", action="store_true",
                      help="Record deliberate roll pairs and repositioning with the arm in front and at the side")
    mode.add_argument("--roll-training", action="store_true",
                      help="Collect 24 cues per roll direction in one extended run")
    parser.add_argument("--holdout", choices=("normal", "varied"),
                        help="Mark the recording as an evaluation session")
    parser.add_argument("--arm-position", choices=STANDING_POSES,
                        help="Starting arm position for --six-training (default: front)")
    args = parser.parse_args()
    if args.arm_position is not None and not args.six_training:
        parser.error("--arm-position requires --six-training.")
    if args.holdout and (not (args.roll_poses or args.six_training or args.six_mixed) or args.detect):
        parser.error("--holdout requires --roll-poses, --six-training or --six-mixed, without --detect.")
    if (args.roll_poses or args.roll_training or args.six_training or args.six_mixed) and args.detect:
        parser.error("--detect uses the thumb-up detector. Omit it for this collection mode.")
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
    duration = DURATION
    if args.six_mixed:
        protocol = "six_mixed"
        schedule = six_mixed_schedule(random.Random())
        duration = schedule[-1][0] + 3
        print(f"Mixed sequence run: {duration // 60} min {duration % 60} sec. "
              "Follow the GO and reposition cues. The recorder stops automatically.", flush=True)
    elif args.six_training:
        protocol = "six_training"
        schedule = six_training_schedule(random.Random(), 4 if args.holdout else 10, args.arm_position or "front")
        duration = schedule[-1][0] + 3
        print(f"Standing six-gesture run: {duration // 60} min {duration % 60} sec. "
              "Follow the numbered cues. The recorder stops automatically.", flush=True)
    elif args.roll_training:
        protocol = "roll_training"
        schedule = roll_pose_schedule(ROLL_TRAINING_CYCLES)
        duration = schedule[-1][0] + 2
        print(f"Training run: {duration // 60} min {duration % 60} sec. "
              "Follow the numbered cues. The recorder stops automatically.", flush=True)
    elif args.roll_poses:
        protocol = "roll_poses"
        schedule = roll_pose_schedule()
    elif args.six_gestures:
        protocol = "six_gestures"
        schedule = cue_schedule(SIX_GESTURES, "Stand facing forward, elbow bent near your side, forearm pointing ahead, thumb up.")
    else:
        protocol = "palm_turns"
        schedule = cue_schedule(PALM_TURNS, "Rest your forearm on the table, thumb up.")
    metadata = {"session": folder.name, "wrist": wrist, "strap_position": orientation,
                "protocol": protocol, "scheduled_duration_s": duration,
                "cue_times": "Prompt times only. Compare host_unix_s with motion.csv. "
                             "Sample motion times and cue times need alignment before training."}
    if args.six_training:
        metadata["arm_position"] = args.arm_position or "front"
    if args.holdout:
        metadata.update(dataset_split="holdout", test_style=args.holdout)
    (folder / "session.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(f"Saving to {folder}", flush=True)
    status = record(folder, args.device, schedule, duration=duration)
    if status == 0 and args.detect:
        from detect_turns import replay

        try:
            replay(folder / "motion.csv")
        except (OSError, ValueError, KeyError) as error:
            parser.exit(1, f"Could not replay motion: {error}\n")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
