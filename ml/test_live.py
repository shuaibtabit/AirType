"""Tests for live gesture detection. Run: python3 -B -m unittest discover -s ml"""

import itertools
import math
import tempfile
import unittest
import uuid
from pathlib import Path

import live
from detect_turns import detect, read_motion

HEADER = ("host_unix_s,host_uptime_s,record_index,strap_unix_s,strap_fraction_ticks,sample_index,"
          "accel_count,gyro_count,estimated_sample_unix_s,ax_raw,ay_raw,az_raw,gx_raw,gy_raw,gz_raw,"
          "ax_g,ay_g,az_g,gx_rad_s,gy_rad_s,gz_rad_s\n")
RATE = 100


def motion_lines(turn_speeds, rest_seconds=1.0, turn_seconds=0.6):
    """Synthetic strap CSV: a thumb-up rest, then one X-axis turn and hold per speed."""
    segments = [(0.0, rest_seconds)]
    for speed in turn_speeds:
        # Turn out, hold, turn back slowly enough to stay under the detector's start speed.
        angle = speed * turn_seconds
        segments += [(speed, turn_seconds), (0.0, rest_seconds),
                     (-math.copysign(0.3, speed), abs(angle) / 0.3), (0.0, rest_seconds)]
    lines = [HEADER]
    angle = 0.0
    index = 0
    for speed, seconds in segments:
        for _ in range(round(seconds * RATE)):
            angle += speed / RATE
            gravity = (0.0, math.sin(angle), -math.cos(angle))
            record, sample = divmod(index, RATE)
            fields = [1.0, 1.0, record, 1000 + record, 0, sample, RATE, RATE, 1000 + index / RATE,
                      0, 0, 0, 1, 0, 0, *gravity, speed, 0.0, 0.0]
            lines.append(",".join(str(field) for field in fields) + "\n")
            index += 1
    return lines


class LiveDetectionTests(unittest.TestCase):
    def test_turn_directions_are_reported_in_order(self):
        events = list(live.gestures(motion_lines([2.0, -2.0, -2.0])))
        self.assertEqual([event.direction for event in events], ["palm_up", "palm_down", "palm_down"])

    def test_streaming_matches_offline_replay_of_the_same_file(self):
        lines = motion_lines([2.0, -2.0, 2.0])
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "motion.csv"
            path.write_text("".join(lines))
            offline = list(detect(*read_motion(path)))
        self.assertEqual(list(live.gestures(lines)), offline)
        self.assertEqual(len(offline), 3)

    def test_events_arrive_before_the_stream_ends(self):
        lines = motion_lines([2.0, -2.0])
        consumed = 0

        def counted():
            nonlocal consumed
            for line in lines:
                consumed += 1
                yield line

        next(live.gestures(counted()))
        self.assertLess(consumed, len(lines) / 2)

    def test_stream_without_samples_is_an_error(self):
        with self.assertRaises(ValueError):
            list(live.gestures([HEADER]))

    def test_moving_start_cannot_calibrate(self):
        lines = motion_lines([2.0])
        tumbling = [HEADER] + [line.replace(",0.0,0.0,-1.0,", ",0.0,0.0,-0.2,") for line in lines[1:]]
        with self.assertRaises(ValueError):
            list(live.gestures(tumbling))


class SourceTests(unittest.TestCase):
    def test_saved_lines_copy_the_stream_unchanged(self):
        lines = motion_lines([2.0])
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "motion.csv"
            passed = list(live.saved(lines, path))
            self.assertEqual(passed, lines)
            self.assertEqual(path.read_text(), "".join(lines))

    def test_replay_yields_the_file_lines(self):
        lines = motion_lines([2.0])
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "motion.csv"
            path.write_text("".join(lines))
            self.assertEqual(list(live.replayed(path, realtime=False)), lines)

    def test_realtime_replay_pauses_once_per_frame(self):
        lines = motion_lines([2.0])
        pauses = []
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "motion.csv"
            path.write_text("".join(lines))
            list(live.replayed(path, realtime=True, sleep=pauses.append))
        frames = {line.split(",")[2] for line in lines[1:]}
        self.assertEqual(len(pauses), len(frames))


FAKE_RECORDER = """#!/usr/bin/env python3
import pathlib, signal, sys, time
folder = pathlib.Path(__file__).parent
(folder / "arguments").write_text(" ".join(sys.argv[1:]))
def stop(*_):
    (folder / "stopped").write_text("clean")
    sys.exit(0)
signal.signal(signal.SIGINT, stop)
sys.stdout.write((folder / "motion.csv").read_text())
sys.stdout.flush()
time.sleep(30)
"""


class StrapTests(unittest.TestCase):
    def test_strap_streams_lines_then_stops_the_recorder_cleanly(self):
        lines = motion_lines([2.0, -2.0])
        device = uuid.UUID("12345678-1234-1234-1234-123456789abc")
        with tempfile.TemporaryDirectory() as name:
            folder = Path(name)
            (folder / "motion.csv").write_text("".join(lines))
            recorder = folder / "recorder"
            recorder.write_text(FAKE_RECORDER)
            recorder.chmod(0o755)
            with live.strap(device, recorder) as stream:
                events = itertools.islice(live.gestures(stream), 2)
                directions = [event.direction for event in events]
            self.assertEqual(directions, ["palm_up", "palm_down"])
            self.assertEqual((folder / "stopped").read_text(), "clean")
            self.assertEqual((folder / "arguments").read_text(), f"stream {device} --allow-mac-bond")


if __name__ == "__main__":
    unittest.main()
