"""Evaluate continuous T9 decoding on held-out JSONL; no network unless --gemini."""

import argparse
import json
from pathlib import Path
import re

from t9_decoder import Decoder, HERE, gemini_rank


def alignment(reference, predicted):
    """Return (edit distance, exact matches) under minimum-edit word alignment."""
    table = [[(0, 0)] * (len(predicted) + 1) for _ in range(len(reference) + 1)]
    for i in range(len(reference) + 1):
        table[i][0] = (i, 0)
    for j in range(len(predicted) + 1):
        table[0][j] = (j, 0)
    for i, expected in enumerate(reference, 1):
        for j, actual in enumerate(predicted, 1):
            edits, matches = table[i - 1][j - 1]
            same = expected == actual
            choices = [(edits + (not same), matches + same),
                       (table[i - 1][j][0] + 1, table[i - 1][j][1]),
                       (table[i][j - 1][0] + 1, table[i][j - 1][1])]
            table[i][j] = min(choices, key=lambda value: (value[0], -value[1]))
    return table[-1][-1]


def evaluate(decoder, rows, beam_size=32, use_gemini=False):
    counts = dict(phrases=0, target_words=0, matched_words=0, word_edits=0,
                  top1_phrases=0, top3_phrases=0, candidate_covered_phrases=0,
                  lexicon_covered_words=0, no_match=0, uncertain=0,
                  gemini_fallbacks=0, beam_pruned_phrases=0)
    details = []
    for row in rows:
        expected_text = row["expected"]
        if not isinstance(expected_text, str) or not re.fullmatch(r"[a-z]+(?: [a-z]+)*", expected_text):
            raise ValueError("Expected phrases must contain lowercase ASCII words separated by spaces.")
        expected = expected_text.split()
        context = row.get("context", "")
        result = decoder.decode(row["gestures"], beam_size=beam_size)
        if use_gemini:
            result = gemini_rank(result, context)
        candidates = [candidate["text"] for candidate in result["candidates"]]
        # Abstentions are misses. Explicitly marked API fallbacks use the local suggestion.
        prediction = candidates[0] if candidates and result["status"] == "ok" else ""
        edits, matches = alignment(expected, prediction.split())
        counts["phrases"] += 1
        counts["target_words"] += len(expected)
        counts["matched_words"] += matches
        counts["word_edits"] += edits
        counts["top1_phrases"] += prediction == expected_text
        counts["top3_phrases"] += expected_text in candidates[:3]
        counts["candidate_covered_phrases"] += expected_text in candidates
        counts["lexicon_covered_words"] += sum(word in decoder.word_scores for word in expected)
        counts["no_match"] += result["status"] == "no_match"
        counts["uncertain"] += result["status"] == "uncertain"
        counts["beam_pruned_phrases"] += result["beam_pruned"]
        counts["gemini_fallbacks"] += "fallback" in result.get("gemini_status", "")
        details.append({"expected": expected_text, "predicted": prediction,
                        "top3": candidates[:3], "status": result["status"],
                        "source": result["source"], "gemini_status": result.get("gemini_status"),
                        "gemini_seconds": result.get("gemini_seconds")})
    if not counts["phrases"]:
        raise ValueError("Evaluation needs at least one labeled phrase.")
    return {"counts": counts,
            "top1_aligned_word_accuracy": counts["matched_words"] / counts["target_words"],
            "word_error_rate": counts["word_edits"] / counts["target_words"],
            "top1_exact_phrase_accuracy": counts["top1_phrases"] / counts["phrases"],
            "top3_exact_phrase_coverage": counts["top3_phrases"] / counts["phrases"],
            "retained_candidate_phrase_coverage": counts["candidate_covered_phrases"] / counts["phrases"],
            "lexicon_word_coverage": counts["lexicon_covered_words"] / counts["target_words"],
            "note": "Offline correctness, not measured user acceptance. Fixture results are not field accuracy.",
            "details": details}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data", type=Path, help="JSONL: gestures, expected, optional context")
    parser.add_argument("--mapping", type=Path, default=HERE / "gesture_groups.example.json")
    parser.add_argument("--lexicon", type=Path, default=HERE / "lexicon.demo.tsv")
    parser.add_argument("--beam", type=int, default=32)
    parser.add_argument("--gemini", action="store_true")
    args = parser.parse_args()
    try:
        decoder = Decoder.load(args.mapping, args.lexicon)
        rows = [json.loads(line) for line in args.data.read_text().splitlines() if line.strip()]
        print(json.dumps(evaluate(decoder, rows, args.beam, args.gemini), indent=2, allow_nan=False))
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f"Could not evaluate: {error}\n")


if __name__ == "__main__":
    main()
