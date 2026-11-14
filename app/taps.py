"""Spot a double tap on the strap in the raw motion stream. Thresholds are guesses
until checked against a real tap recording."""

import math
from typing import Callable, Iterable, Iterator

TAP_JERK_G = 0.6          # change in acceleration magnitude between neighbouring samples
TAP_REFRACTORY_S = 0.08   # one physical tap rings for a few samples
DOUBLE_MIN_S = 0.10
DOUBLE_MAX_S = 0.60
LOCKOUT_S = 1.0


def double_taps(lines: Iterable[str], on_double_tap: Callable[[float], None]) -> Iterator[str]:
    """Pass CSV lines through unchanged, calling back with the strap time of each double tap."""
    columns = None
    previous = None
    last_tap = None
    locked_until = -math.inf
    for line in lines:
        yield line
        fields = line.rstrip("\n").split(",")
        if columns is None:
            columns = {name: index for index, name in enumerate(fields)}
            continue
        try:
            stamp = fields[columns["estimated_sample_unix_s"]]
            if not stamp:
                previous = None
                continue
            time = float(stamp)
            magnitude = math.hypot(*(float(fields[columns[key]]) for key in ("ax_g", "ay_g", "az_g")))
        except (KeyError, ValueError, IndexError):
            previous = None
            continue
        jerk = abs(magnitude - previous) if previous is not None else 0.0
        previous = magnitude
        if jerk < TAP_JERK_G or time < locked_until:
            continue
        if last_tap is not None and time - last_tap < TAP_REFRACTORY_S:
            continue
        if last_tap is not None and DOUBLE_MIN_S <= time - last_tap <= DOUBLE_MAX_S:
            on_double_tap(time)
            locked_until = time + LOCKOUT_S
            last_tap = None
        else:
            last_tap = time
