"""Detect gestures while the strap streams, or while replaying a saved motion CSV.

Live mode connects to the strap, which can replace the phone's pairing. Start
thumb-up and hold still for the first second so the rest pose can be calibrated.
"""

import argparse
import csv
import itertools
import signal
import subprocess
import tempfile
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterable, Iterator, Optional

from detect_turns import Sample, Turn, detect, mean_gravity

ROOT = Path(__file__).resolve().parents[1]
RECORDER = ROOT / ".build/debug/airtype-capture"
CALIBRATION_SAMPLES = 50
TICKS_PER_SECOND = 32768
RECORD_INDEX_COLUMN = 2
FRAME_SECONDS = 1.0
STOP_TIMEOUT_SECONDS = 20

Row = dict


def gravity_of(row: Row) -> tuple:
    return tuple(float(row[key]) for key in ("ax_g", "ay_g", "az_g"))


def sample_of(row: Row, origin: float) -> Optional[Sample]:
    """Mirror detect_turns.read_motion: skip untimed rows and saturated gyro startup rows."""
    if not row["estimated_sample_unix_s"]:
        return None
    if all(int(row[key]) == -32768 for key in ("gx_raw", "gy_raw", "gz_raw")):
        return None
    rotation = tuple(float(row[key]) for key in ("gx_rad_s", "gy_rad_s", "gz_rad_s"))
    return Sample(float(row["estimated_sample_unix_s"]) - origin, gravity_of(row), rotation)


def calibrated(lines: Iterable[str]) -> tuple:
    """Read just enough of the stream to calibrate, then return (neutral, lazy samples)."""
    rows = csv.DictReader(lines)
    head = []
    for row in rows:
        head.append(row)
        in_first_record = row["record_index"] == head[0]["record_index"]
        if not in_first_record or int(row["sample_index"]) >= CALIBRATION_SAMPLES:
            break
    if not head:
        raise ValueError("The stream contains no samples.")
    first = head[0]
    origin = int(first["strap_unix_s"]) + int(first["strap_fraction_ticks"]) / TICKS_PER_SECOND
    neutral = mean_gravity([
        gravity_of(row) for row in head
        if row["record_index"] == first["record_index"] and int(row["sample_index"]) < CALIBRATION_SAMPLES
    ])
    if neutral is None:
        raise ValueError("Could not calibrate. Start thumb-up and hold still for the first second.")

    def samples() -> Iterator[Sample]:
        for row in itertools.chain(head, rows):
            sample = sample_of(row, origin)
            if sample is not None:
                yield sample

    return neutral, samples()


def gestures(lines: Iterable[str]) -> Iterator[Turn]:
    """Yield each gesture as soon as the stream has enough samples to confirm it."""
    neutral, samples = calibrated(lines)
    yield from detect(samples, neutral)


def saved(lines: Iterable[str], path: Path) -> Iterator[str]:
    """Pass lines through unchanged while keeping the raw stream on disk."""
    with path.open("w", newline="") as file:
        for line in lines:
            file.write(line)
            file.flush()
            yield line


def replayed(path: Path, realtime: bool, sleep: Callable[[float], None] = time.sleep) -> Iterator[str]:
    """Yield a saved CSV, optionally paced one frame per second like the strap delivers it."""
    with path.open(newline="") as file:
        yield next(file, "")
        frame = None
        for line in file:
            record = line.split(",")[RECORD_INDEX_COLUMN]
            if realtime and record != frame:
                sleep(FRAME_SECONDS)
            frame = record
            yield line


@contextmanager
def strap(device: uuid.UUID, recorder: Path = RECORDER) -> Iterator[Iterable[str]]:
    """Stream CSV lines from the strap and always ask it to stop cleanly."""
    # A separate session keeps Ctrl-C away from the recorder so we can stop it in order.
    process = subprocess.Popen(
        [str(recorder), "stream", str(device), "--allow-mac-bond"],
        stdout=subprocess.PIPE, text=True, start_new_session=True,
    )
    try:
        yield process.stdout
    finally:
        if process.poll() is None:
            process.send_signal(signal.SIGINT)
        try:
            process.wait(timeout=STOP_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            process.kill()
            print("The recorder did not stop in time. Strap cleanup is unconfirmed.", flush=True)
        finally:
            process.stdout.close()


def show(lines: Iterable[str]) -> int:
    """Print gestures as they are confirmed. Ctrl-C ends the readout and keeps the count."""
    count = 0
    try:
        for event in gestures(lines):
            count += 1
            print(f"  {event.end:7.2f} s  {event.direction.replace('_', ' '):9}  "
                  f"X turn {event.angle_degrees:+.0f}°", flush=True)
    except KeyboardInterrupt:
        print("\nStopping.", flush=True)
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("device", type=uuid.UUID, nargs="?", help="Bluetooth UUID from AirType discovery")
    parser.add_argument("--allow-mac-bond", action="store_true",
                        help="Required for live mode. The Mac may replace the phone's pairing.")
    parser.add_argument("--replay", type=Path, help="Replay a saved motion.csv without Bluetooth")
    parser.add_argument("--realtime", action="store_true", help="Pace a replay at one frame per second")
    args = parser.parse_args()
    if (args.device is None) == (args.replay is None):
        parser.error("Give a device UUID for live mode, or --replay with a motion.csv.")

    count = 0
    try:
        if args.replay is not None:
            count = show(replayed(args.replay, args.realtime))
        else:
            if not args.allow_mac_bond:
                parser.error("Live mode needs --allow-mac-bond.")
            if not RECORDER.is_file():
                parser.error("Run swift build in AirType first.")
            captures = ROOT / "captures"
            captures.mkdir(exist_ok=True)
            folder = Path(tempfile.mkdtemp(prefix="live.", dir=captures))
            print(f"Saving raw motion to {folder}", flush=True)
            print("Hold thumb-up and still until the first gesture prompt. Ctrl-C to stop.", flush=True)
            with strap(args.device) as lines:
                count = show(saved(lines, folder / "motion.csv"))
    except (OSError, ValueError, KeyError) as error:
        parser.exit(1, f"Could not read motion: {error}\n")
    print(f"Detected {count} gestures.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
