"""Replay an AirType motion CSV and detect palm turns without cue times."""

import argparse
import csv
import math
from dataclasses import dataclass
from pathlib import Path

START_SPEED = 0.45  # rad/s, magnitude across the three gyro axes
QUIET_SECONDS = 0.20
MAX_SAMPLE_GAP = 0.025
MAX_TURN_SECONDS = 2.5
NEUTRAL_TOLERANCE = math.cos(math.radians(20))
TIPPED_MINIMUM = math.cos(math.radians(25))
MIN_ROTATION = math.radians(25)
MIN_X_ENERGY = 0.88
MIN_DIRECTION_CONSISTENCY = 0.72


@dataclass(frozen=True)
class Sample:
    time: float
    gravity: tuple
    rotation: tuple

    @property
    def moving(self):
        return math.hypot(*self.rotation) >= START_SPEED


@dataclass(frozen=True)
class Turn:
    start: float
    end: float
    direction: str
    angle_degrees: float
    x_energy: float


def read_motion(path):
    with path.open(newline="") as file:
        rows = list(csv.DictReader(file))
    if not rows:
        raise ValueError("The capture contains no samples.")
    first = rows[0]
    origin = int(first["strap_unix_s"]) + int(first["strap_fraction_ticks"]) / 32768
    # The pilot starts in thumb-up rest. Partial frames may calibrate gravity,
    # but only samples with estimated timestamps can drive the detector.
    calibration = []
    samples = []
    for row in rows:
        gravity = tuple(float(row[key]) for key in ("ax_g", "ay_g", "az_g"))
        if row["record_index"] == first["record_index"] and int(row["sample_index"]) < 50:
            calibration.append(gravity)
        if not row["estimated_sample_unix_s"]:
            continue
        if all(int(row[key]) == -32768 for key in ("gx_raw", "gy_raw", "gz_raw")):
            continue
        rotation = tuple(float(row[key]) for key in ("gx_rad_s", "gy_rad_s", "gz_rad_s"))
        samples.append(Sample(float(row["estimated_sample_unix_s"]) - origin, gravity, rotation))
    neutral = mean_gravity(calibration)
    if neutral is None or not samples:
        raise ValueError("Need a thumb-up rest at the start and timestamped motion samples.")
    return samples, neutral


def mean_gravity(vectors):
    if not vectors:
        return None
    average = tuple(sum(axis) / len(vectors) for axis in zip(*vectors))
    magnitude = math.hypot(*average)
    if not 0.8 <= magnitude <= 1.2:
        return None
    return tuple(value / magnitude for value in average)


def similarity(gravity, neutral):
    return sum(axis * reference for axis, reference in zip(gravity, neutral))


def classify(burst, settled, neutral):
    start, end = burst[0].time, burst[-1].time
    if end - start > MAX_TURN_SECONDS:
        return None

    energy = sum(sum(value * value for value in sample.rotation) for sample in burst)
    x_energy = sum(sample.rotation[0] ** 2 for sample in burst) / energy
    # Trapezoidal integration uses the reconstructed sample intervals.
    steps = [
        ((a.rotation[0] + b.rotation[0]) * (b.time - a.time)) / 2
        for a, b in zip(burst, burst[1:])
    ]
    angle = sum(steps)
    total_rotation = sum(abs(step) for step in steps)
    if (abs(angle) < MIN_ROTATION or x_energy < MIN_X_ENERGY
            or abs(angle) < MIN_DIRECTION_CONSISTENCY * total_rotation):
        return None

    final_gravity = mean_gravity([sample.gravity for sample in settled])
    if final_gravity is None or similarity(final_gravity, neutral) > TIPPED_MINIMUM:
        return None

    return Turn(start, end, "palm_up" if angle > 0 else "palm_down",
                math.degrees(angle), x_energy)


def detect(samples, neutral):
    quiet = []
    burst = []
    started_neutral = False
    previous = None
    for sample in samples:
        if previous is not None and not 0 < sample.time - previous <= MAX_SAMPLE_GAP:
            quiet.clear()
            burst.clear()
            started_neutral = False
        previous = sample.time

        if sample.moving:
            if not burst:
                rested = quiet and quiet[-1].time - quiet[0].time >= QUIET_SECONDS
                pose = mean_gravity([s.gravity for s in quiet[-25:]]) if rested else None
                started_neutral = pose is not None and similarity(pose, neutral) >= NEUTRAL_TOLERANCE
            burst.append(sample)
            quiet.clear()
            continue

        quiet.append(sample)
        if burst and quiet[-1].time - quiet[0].time >= QUIET_SECONDS:
            if started_neutral:
                event = classify(burst, quiet, neutral)
                if event is not None:
                    yield event
            burst.clear()
        elif burst:
            burst.append(sample)
        elif len(quiet) > 30:
            quiet.pop(0)


def replay(path):
    samples, neutral = read_motion(path)
    turns = list(detect(samples, neutral))
    print("\nPalm-turn detector (seconds from first strap frame)")
    for turn in turns:
        print(f"  {turn.start:5.2f}–{turn.end:5.2f} s  {turn.direction.replace('_', ' '):9}  "
              f"X turn {turn.angle_degrees:+.0f}°  X energy {turn.x_energy:.0%}")
    print(f"Detected {len(turns)} turns.")
    return turns


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("motion", type=Path, help="Path to an AirType motion.csv")
    args = parser.parse_args()
    try:
        replay(args.motion)
    except (OSError, ValueError, KeyError) as error:
        parser.exit(1, f"Could not replay motion: {error}\n")


if __name__ == "__main__":
    main()
