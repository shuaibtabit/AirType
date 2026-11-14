"""Review, fit, and replay a standing gesture classifier with a background class."""

import argparse
import csv
import itertools
import json
import math
from bisect import bisect_right
from collections import Counter, defaultdict
from pathlib import Path

import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC

from detect_turns import Turn
from record_pilot import SIX_GESTURES
from roll_model import Bout, fingerprint, match_bouts, movement_spans

COMMANDS = tuple(label for label, _ in SIX_GESTURES)
BACKGROUND = "background"
CLASSES = COMMANDS + (BACKGROUND,)
NON_COMMAND_CUES = ("rest", "reset", "reposition", "background", "walk", "drink", "transition", "arm_front", "arm_side")
MIN_CONFIDENCE = 0.60
REVIEW_FILE = "six-labels.json"
VERSION = 1


def six_bouts(lines):
    def samples():
        for row in csv.DictReader(lines):
            stamp = row["estimated_sample_unix_s"]
            if stamp and not all(int(row[k]) == -32768 for k in ("gx_raw", "gy_raw", "gz_raw")):
                axes = ("gx_rad_s", "gy_rad_s", "gz_rad_s", "ax_g", "ay_g", "az_g")
                yield (float(stamp), *(float(row[k]) for k in axes))

    for span in movement_spans(samples()):
        rows = np.asarray(span)
        elapsed = rows[-1, 0] - rows[0, 0]
        gyro, accel = rows[:, 1:4], rows[:, 4:7]
        steps = (gyro[1:] + gyro[:-1]) * (np.diff(rows[:, 0])[:, None] / 2)
        turn = steps.sum(axis=0)
        energy = (gyro * gyro).sum(axis=0)
        peak = np.max(np.abs(gyro), axis=0)
        vector = (*turn, *np.log1p(np.abs(steps).sum(axis=0)),
                  *(energy / max(float(energy.sum()), 1e-9)), *np.log1p(peak),
                  *accel.mean(axis=0), *(accel[-1] - accel[0]),
                  *accel.std(axis=0), math.log1p(elapsed))
        yield Bout(float(rows[0, 0]), float(rows[-1, 0]), vector)


def capture_bouts(folder):
    with (folder / "motion.csv").open(newline="") as file:
        return list(six_bouts(file))


def review(folder, skipped):
    """Export cue-aligned labels and flag command windows with competing motion."""
    meta = json.loads((folder / "session.json").read_text())
    if meta["protocol"] not in ("six_gestures", "six_training", "six_mixed"):
        raise ValueError("Choose a six-gesture recording.")
    with (folder / "cues.csv").open(newline="") as file:
        cues = list(csv.DictReader(file))
    if not cues or cues[-1]["cue"] != "rest" or not any(cue["cue"] == "drink" for cue in cues):
        raise ValueError(f"Incomplete cue log in {folder.name}.")
    origin = float(cues[0]["host_unix_s"])
    bouts = capture_bouts(folder)
    times = [float(cue["host_unix_s"]) for cue in cues]
    candidate_windows = defaultdict(list)
    for bout in bouts:
        midpoint = (bout.start + bout.end) / 2
        # A small clock allowance keeps a slightly early move with its cue.
        index = bisect_right(times, midpoint + .20) - 1
        if (.07 <= bout.end - bout.start <= 1.8
                and math.hypot(*bout.features[:3]) >= math.radians(15)):
            candidate_windows[index].append(bout)

    events = []
    ambiguous = {}
    position = "arm_" + meta.get("arm_position", "front")
    for index, cue in enumerate(cues[:-1]):
        label = cue["cue"]
        if label in ("arm_front", "arm_side"):
            position = label
        if label not in COMMANDS:
            continue
        trial = int(cue["turn_number"])
        if trial in skipped:
            ambiguous[trial] = "wearer flagged"
            continue
        candidates = candidate_windows[index]
        if len(candidates) != 1:
            ambiguous[trial] = f"{len(candidates)} plausible motion intervals"
            continue
        bout = candidates[0]
        events.append(dict(trial=trial, arm_position=position, label=label,
                           start_s=bout.start - origin, end_s=bout.end - origin))

    output = dict(session_id=folder.name, origin_unix_s=origin,
                  purpose="evaluation" if meta.get("dataset_split") == "holdout" else "training",
                  review_status="Provisional cue alignment. Exclude wrong or missed cues before using.",
                  excluded_trials=ambiguous, events=events)
    (folder / REVIEW_FILE).write_text(json.dumps(output, indent=2) + "\n")
    print(folder.name, len(events), "commands", dict(Counter(event["label"] for event in events)))
    print("Excluded trials:", ambiguous or "none")


def dataset(folder):
    review_data = json.loads((folder / REVIEW_FILE).read_text())
    events = review_data["events"]
    origin = review_data["origin_unix_s"]
    bouts = capture_bouts(folder)
    reviewed = events + review_data.get("background_events", [])
    reviewed_matches = match_bouts(reviewed, bouts, origin)
    matches = {index: bout for index, bout in reviewed_matches.items() if index < len(events)}
    labels = {bout_index: reviewed[event_index]["label"] for event_index, bout_index in reviewed_matches.items()}
    with (folder / "cues.csv").open(newline="") as file:
        cues = list(csv.DictReader(file))
    times = [float(cue["host_unix_s"]) for cue in cues]
    for index, bout in enumerate(bouts):
        if index in labels:
            continue
        if any(bout.start < origin + end and bout.end > origin + start
               for start, end in review_data.get("ignore_background_s", [])):
            continue
        # Use fully contained ordinary-motion spans. Leave ambiguous command windows unlabeled.
        if any(cue["cue"] in NON_COMMAND_CUES and start + .20 <= bout.start <= bout.end < end - .20
               for cue, start, end in zip(cues, times, times[1:])):
            labels[index] = BACKGROUND
    return review_data, bouts, matches, labels


def predict(estimator, vectors):
    if not vectors:
        return []
    probabilities = estimator.predict_proba(vectors)
    choices = probabilities.argmax(axis=1)
    return [str(estimator.classes_[index]) if row[index] >= MIN_CONFIDENCE else BACKGROUND
            for row, index in zip(probabilities, choices)]


def fit(estimator, sessions):
    inputs = [bouts[index].features for _, bouts, _, labels in sessions for index in labels]
    truth = [label for _, _, _, labels in sessions for label in labels.values()]
    return estimator.fit(inputs, truth)


def train(folders, output):
    hashes = {fingerprint(folder) for folder in folders}
    if len(hashes) != len(folders) or len(folders) < 2:
        raise ValueError("Use at least two distinct reviewed recordings.")
    sessions = []
    for folder in folders:
        meta = json.loads((folder / "session.json").read_text())
        session = dataset(folder)
        if meta.get("dataset_split") == "holdout" or session[0]["purpose"] != "training":
            raise ValueError(f"{folder.name} is reserved for evaluation.")
        sessions.append(session)
    counts = Counter(label for _, _, _, labels in sessions for label in labels.values())
    if set(counts) != set(CLASSES):
        raise ValueError(f"Training needs all six directions and background. Found {dict(counts)}.")
    candidates = [
        ("logistic regression", make_pipeline(StandardScaler(), LogisticRegression(class_weight="balanced"))),
        ("RBF SVM", make_pipeline(StandardScaler(), SVC(class_weight="balanced", probability=True, random_state=0))),
    ]
    best_name, best = candidates[0]
    best_score = -1
    for name, estimator in candidates:
        actual, guessed = [], []
        for i, (_, bouts, _, labels) in enumerate(sessions):
            other = sessions[:i] + sessions[i + 1:]
            if {label for _, _, _, part in other for label in part.values()} != set(CLASSES):
                continue
            fit(estimator, other)
            actual.extend(labels.values())
            guessed.extend(predict(estimator, [bouts[index].features for index in labels]))
        if actual:
            score = f1_score(actual, guessed, labels=CLASSES, average="macro", zero_division=0)
            print(name, f"development macro F1 {score:.3f}")
            if score > best_score:
                best_score, best_name, best = score, name, estimator
    fit(best, sessions)
    with output.open("xb") as file:
        joblib.dump(dict(kind="six_gestures", version=VERSION, estimator=best, classifier=best_name,
                         training_sha256=sorted(hashes), training_counts=dict(counts)), file)
    print(f"Saved {best_name} to {output} with {dict(counts)}")


def load_model(path):
    model = joblib.load(path)
    if model["kind"] != "six_gestures" or model["version"] != VERSION:
        raise ValueError("This is not a supported six-gesture model.")
    return model


def score(model, folder):
    if fingerprint(folder) in model["training_sha256"]:
        raise ValueError("This recording was used in training.")
    review_data, bouts, matches, labels = dataset(folder)
    if review_data["purpose"] != "evaluation":
        raise ValueError("Use a recording made with --holdout.")
    guesses = predict(model["estimator"], [bout.features for bout in bouts])
    scores = defaultdict(Counter)
    for i, event in enumerate(review_data["events"]):
        expected = event["label"]
        got = guesses[matches[i]] if i in matches else BACKGROUND
        result = "correct" if got == expected else ("missed" if got == BACKGROUND else "wrong")
        scores[event["arm_position"]][result] += 1
        if result != "correct":
            print(f"Turn {event['trial']}: expected {expected}, got {got}")
    for pose, counts in scores.items():
        print(pose, dict(counts))
    false_calls = [i for i, label in labels.items() if label == BACKGROUND and guesses[i] != BACKGROUND]
    unreviewed = [i for i, label in enumerate(guesses) if label != BACKGROUND and i not in labels]
    print("False commands in background:", len(false_calls))
    print("Commands in unreviewed intervals:", len(unreviewed))
    excluded_turns = review_data["excluded_trials"]
    reviewed_count = len(review_data["events"])
    print(f"Command coverage: {reviewed_count}/{reviewed_count + len(excluded_turns)} prompts reviewed")
    print("Excluded turns:", excluded_turns)
    meta = json.loads((folder / "session.json").read_text())
    if meta["protocol"] == "six_mixed":
        with (folder / "cues.csv").open(newline="") as file:
            cues = list(csv.DictReader(file))
        sequence_results = Counter()
        reviewed_by_trial = {str(event["trial"]): event for event in review_data["events"]}
        group = []
        origin = review_data["origin_unix_s"]
        for cue in cues:
            if cue["cue"] in COMMANDS:
                group.append(cue)
            elif cue["cue"] == "reset" and group:
                reviewed = [reviewed_by_trial.get(command["turn_number"]) for command in group]
                if any(event is None for event in reviewed):
                    sequence_results["unresolved"] += 1
                else:
                    # Reviewed onset/offset can fall outside the nominal cue windows.
                    start = min(float(group[0]["host_unix_s"]) - .20,
                                origin + reviewed[0]["start_s"])
                    stop = max(float(cue["host_unix_s"]) - .20,
                               origin + reviewed[-1]["end_s"])
                    actual = [label for bout, label in zip(bouts, guesses)
                              if start <= (bout.start + bout.end) / 2 < stop and label != BACKGROUND]
                    expected = [event["label"] for event in reviewed]
                    result = "exact" if actual == expected else "different"
                    sequence_results[result] += 1
                    if result == "different":
                        print(f"Sequence starting at turn {reviewed[0]['trial']}: expected {expected}, got {actual}")
                group = []
        print("Mixed sequences:", dict(sequence_results))
    for i in false_calls + unreviewed:
        print(f"{bouts[i].start - review_data['origin_unix_s']:.2f}s {guesses[i]}")


def gestures(lines, estimator):
    stream = six_bouts(lines)
    first = next(stream, None)
    if first is None:
        return
    for bout in itertools.chain((first,), stream):
        label = predict(estimator, [bout.features])[0]
        if label != BACKGROUND:
            angle = math.degrees(math.hypot(*bout.features[:3]))
            yield Turn(bout.start - first.start, bout.end - first.start, label, angle, 0.0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    annotate = sub.add_parser("review")
    annotate.add_argument("folder", type=Path)
    annotate.add_argument("--skip", type=int, nargs="*", default=[])
    training = sub.add_parser("train")
    training.add_argument("folders", type=Path, nargs="+")
    training.add_argument("--output", type=Path, required=True)
    evaluation = sub.add_parser("score")
    evaluation.add_argument("folder", type=Path)
    evaluation.add_argument("--model", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.action == "review":
            review(args.folder, args.skip)
        elif args.action == "train":
            train(args.folders, args.output)
        else:
            score(load_model(args.model), args.folder)
    except (ValueError, OSError, KeyError) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
