"""Train a roll classifier and replay WHOOP captures without pose calibration."""

import argparse
import csv
import hashlib
import json
import math
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import joblib
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC

from detect_turns import MAX_SAMPLE_GAP, MIN_ROTATION, MIN_X_ENERGY

LABELS = ("roll_in", "roll_out", "reposition")
START_SPEED = 0.65
QUIET_SECONDS = 0.16
MIN_POINTS = 8
MIN_OVERLAP = 0.20
MODEL_VERSION = 1


@dataclass(frozen=True)
class Bout:
    start: float
    end: float
    features: tuple


def gyro_rows(lines):
    """Yield full-frame sample estimates from live or recorded CSV lines."""
    for row in csv.DictReader(lines):
        stamp = row["estimated_sample_unix_s"]
        if stamp and not all(int(row[key]) == -32768 for key in ("gx_raw", "gy_raw", "gz_raw")):
            yield (float(stamp), *(float(row[k]) for k in ("gx_rad_s", "gy_rad_s", "gz_rad_s")))


def motion_rows(path):
    with path.open(newline="") as file:
        yield from gyro_rows(file)


def load_model(path):
    model = joblib.load(path)
    if model["version"] != MODEL_VERSION:
        raise ValueError("Unsupported model version.")
    return model


def features(rows):
    signed = 0.0
    travel = 0.0
    for a, b in zip(rows, rows[1:]):
        step = (a[1] + b[1]) * (b[0] - a[0]) / 2
        signed += step
        travel += abs(step)
    roll_energy = sum(x * x for _, x, _, _ in rows)
    total_energy = sum(x * x + y * y + z * z for _, x, y, z in rows)
    return (
        signed, math.log1p(travel), signed / max(travel, 1e-9),
        math.log1p(max(abs(x) for _, x, _, _ in rows)),
        math.log1p(math.sqrt(roll_energy / len(rows))),
        roll_energy / max(total_energy, 1e-9),
        math.log1p(rows[-1][0] - rows[0][0]),
    )


def movement_spans(rows):
    """Close an interval after a lull and discard incomplete motion at a gap."""
    active = []
    previous = None
    last_moving = 0
    for row in rows:
        timestamp, *values = row
        gap = previous is not None and not 0 < timestamp - previous <= MAX_SAMPLE_GAP
        if gap:
            active.clear()
        if active and timestamp - active[last_moving][0] >= QUIET_SECONDS:
            if last_moving + 1 >= MIN_POINTS:
                yield active[:last_moving + 1]
            active.clear()
        previous = timestamp
        if math.hypot(*values[:3]) >= START_SPEED:
            last_moving = len(active)
            active.append(row)
        elif active:
            active.append(row)
    # A capture can end mid-motion. Wait for the same lull required in live use.


def motion_bouts(rows):
    for motion in movement_spans(rows):
        yield Bout(motion[0][0], motion[-1][0], features(motion))

def match_bouts(events, bouts, origin):
    """Pair reviewed events and detected bouts uniquely by temporal overlap."""
    overlaps = []
    for i, event in enumerate(events):
        start, end = origin + event["start_s"], origin + event["end_s"]
        for j, bout in enumerate(bouts):
            intersection = min(end, bout.end) - max(start, bout.start)
            union = max(end, bout.end) - min(start, bout.start)
            if union > 0 and intersection / union >= MIN_OVERLAP:
                overlaps.append((intersection / union, i, j))
    matches = {}
    used = set()
    for _, i, j in sorted(overlaps, reverse=True):
        if i not in matches and j not in used:
            matches[i] = j
            used.add(j)
    return matches


@dataclass
class Session:
    folder: Path
    origin: float
    events: list
    bouts: list
    examples: list
    matches: dict


def read_session(folder, purpose):
    data = json.loads((folder / "labels.json").read_text())
    if data["purpose"] != purpose:
        raise ValueError(f"{folder.name} labels must have purpose {purpose!r}.")
    clock = data["timebase"]
    if clock["sample_column"] != "estimated_sample_unix_s":
        raise ValueError(f"Unsupported label timebase in {folder.name}.")
    origin = clock["origin_unix_s"]
    rows = list(motion_rows(folder / "motion.csv"))
    if not rows:
        raise ValueError(f"No timed samples in {folder.name}.")
    bouts = list(motion_bouts(rows))
    events = data["events"]
    matches = match_bouts(events, bouts, origin)
    examples = []
    for i, event in enumerate(events):
        start, end = origin + event["start_s"], origin + event["end_s"]
        if event["label"] not in LABELS or not start < end:
            raise ValueError(f"Invalid training or evaluation span in {folder.name}.")
        if i in matches:
            examples.append(bouts[matches[i]].features)
            continue
        part = [row for row in rows if start <= row[0] < end]
        if len(part) < MIN_POINTS or any(not 0 < b[0] - a[0] <= MAX_SAMPLE_GAP for a, b in zip(part, part[1:])):
            raise ValueError(f"Incomplete samples in trial {event['trial']} of {folder.name}.")
        examples.append(features(part))
    return Session(folder, origin, events, bouts, examples, matches)


def roll_label(bout, prediction):
    """Reject command predictions without a substantial roll in that direction."""
    if prediction in LABELS[:2]:
        angle, _, _, _, _, x_energy, _ = bout.features
        matching_direction = angle < 0 if prediction == "roll_in" else angle > 0
        if abs(angle) < MIN_ROTATION or x_energy < MIN_X_ENERGY or not matching_direction:
            return "background"
    return prediction


def readout(estimator, bouts, *, guard=True):
    if not bouts:
        return []
    predictions = estimator.predict([bout.features for bout in bouts]).tolist()
    if guard:
        return [roll_label(bout, prediction) for bout, prediction in zip(bouts, predictions)]
    return predictions


def reviewed_predictions(session, predictions):
    return [predictions[session.matches[i]] if i in session.matches else "missed"
            for i in range(len(session.events))]


def fingerprint(folder):
    return hashlib.sha256((folder / "motion.csv").read_bytes()).hexdigest()


def fit(estimator, sessions):
    inputs = [vector for session in sessions for vector in session.examples]
    labels = [event["label"] for session in sessions for event in session.events]
    return estimator.fit(inputs, labels)


def train(folders, output):
    if len(folders) < 3 or len({folder.resolve() for folder in folders}) != len(folders):
        raise ValueError("Supply at least three distinct reviewed training folders.")
    for folder in folders:
        metadata = folder / "session.json"
        if metadata.exists() and json.loads(metadata.read_text()).get("dataset_split") == "holdout":
            raise ValueError(f"{folder.name} is reserved for evaluation.")
    hashes = {fingerprint(folder) for folder in folders}
    if len(hashes) != len(folders):
        raise ValueError("Training folders must contain distinct captures.")
    sessions = [read_session(folder, "training") for folder in folders]
    models = {
        "logistic regression": make_pipeline(StandardScaler(), LogisticRegression(class_weight="balanced")),
        "RBF SVM": make_pipeline(StandardScaler(), SVC(class_weight="balanced")),
        "random forest": RandomForestClassifier(n_estimators=200, max_depth=4, min_samples_leaf=3,
                                               class_weight="balanced", random_state=0),
    }
    truth = [event["label"] for session in sessions for event in session.events]
    scores = {}
    print("Development results, holding out one entire training recording at a time.")
    for name, estimator in models.items():
        predicted = []
        for held in sessions:
            fit(estimator, [session for session in sessions if session is not held])
            predicted.extend(reviewed_predictions(held, readout(estimator, held.bouts, guard=False)))
        score = f1_score(truth, predicted, labels=LABELS, average="macro", zero_division=0)
        scores[name] = score
        correct = sum(a == b for a, b in zip(truth, predicted))
        returns = sum(a == "reposition" and b in LABELS[:2] for a, b in zip(truth, predicted))
        print(f"{name}: macro F1 {score:.3f}, {correct}/{len(truth)} correct reviewed events, "
              f"{returns} reviewed repositions called commands")

    name = max(scores, key=scores.get)
    estimator = fit(models[name], sessions)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as file:
        joblib.dump({"version": MODEL_VERSION, "name": name, "estimator": estimator,
                     "training_sha256": sorted(hashes), "training_counts": dict(Counter(truth)),
                     "development_macro_f1": scores}, file)
    print(f"Trained {name} on {len(truth)} spans across {len(sessions)} recordings.")
    print(f"Saved {output}")


def score(model, folder):
    if fingerprint(folder) in model["training_sha256"]:
        raise ValueError("This capture was used to train the model. Select a fresh recording.")
    session = read_session(folder, "evaluation")
    predictions = readout(model["estimator"], session.bouts)
    counts = Counter()
    by_pose = {}
    for event, label in zip(session.events, reviewed_predictions(session, predictions)):
        expected = event["label"]
        if expected == "reposition":
            result = "false command on reposition" if label in LABELS[:2] else "reposition ignored"
        elif expected == label:
            result = "correct command"
        elif label in LABELS[:2]:
            result = "wrong direction"
        else:
            result = "missed command"
        counts[result] += 1
        by_pose.setdefault(event["arm_position"], Counter())[result] += 1
        print(f"Trial {event['trial']} {event['arm_position']} {expected}: {result}")
    print("Overall:", dict(counts))
    for pose, results in by_pose.items():
        print(pose, dict(results))
    matched = set(session.matches.values())
    for i, (bout, label) in enumerate(zip(session.bouts, predictions)):
        if i not in matched and label in LABELS[:2]:
            print(f"Unmatched command at {bout.start - session.origin:.2f} s: {label} (review against capture)")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    training = commands.add_parser("train")
    training.add_argument("sessions", nargs="+", type=Path)
    training.add_argument("--output", type=Path, required=True)
    replay = commands.add_parser("replay")
    replay.add_argument("motion", type=Path)
    replay.add_argument("--model", type=Path, required=True)
    evaluation = commands.add_parser("score")
    evaluation.add_argument("session", type=Path)
    evaluation.add_argument("--model", type=Path, required=True)
    args = parser.parse_args()

    try:
        if args.command == "train":
            train(args.sessions, args.output)
            return
        model = load_model(args.model)
        if args.command == "score":
            score(model, args.session)
        else:
            rows = list(motion_rows(args.motion))
            if not rows:
                raise ValueError("No timed motion samples.")
            bouts = list(motion_bouts(rows))
            for bout, label in zip(bouts, readout(model["estimator"], bouts)):
                print(f"{bout.start - rows[0][0]:7.2f}–{bout.end - rows[0][0]:7.2f} s  {label}")
    except (OSError, ValueError, KeyError) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
