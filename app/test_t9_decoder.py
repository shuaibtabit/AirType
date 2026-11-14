import io
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch
import urllib.error

from evaluate_t9 import alignment, evaluate
from t9_decoder import Decoder, HERE, gemini_rank


class DecoderTests(unittest.TestCase):
    def setUp(self):
        self.mapping = json.loads((HERE / "gesture_groups.example.json").read_text())
        self.decoder = Decoder(self.mapping, [("go", 100), ("home", 100), ("gone", 20),
                                              ("hope", 10), ("ho", 1), ("me", 1), ("i", 10)])

    def test_continuous_stream_infers_word_boundaries(self):
        result = self.decoder.decode([2, 4, 2, 4, 4, 2])
        self.assertEqual(result["candidates"][0]["text"], "go home")
        self.assertIn("go gone", [c["text"] for c in result["candidates"]])
        self.assertFalse(result["committed"])

    def test_one_word_can_also_have_multiple_segmentations(self):
        phrases = [c["text"] for c in self.decoder.decode([2, 4, 4, 2])["candidates"]]
        self.assertIn("home", phrases)
        self.assertIn("ho me", phrases)

    def test_every_output_preserves_every_gesture(self):
        tokens = ("2", "4", "2", "4", "4", "2")
        for candidate in self.decoder.decode(tokens)["candidates"]:
            encoded = tuple(group for word in candidate["words"] for group in self.decoder.encode(word))
            self.assertEqual(encoded, tokens)

    def test_labels_and_numbers_are_equivalent(self):
        self.assertEqual(self.decoder.decode(["roll_out", "tilt_down"]), self.decoder.decode([2, 4]))

    def test_repeated_gestures_are_not_collapsed(self):
        self.assertEqual(len(self.decoder.tokens([4, 4])), 2)

    def test_unknown_or_rejected_events_are_not_silently_deleted(self):
        for value in ([2, "uncertain"], [7], [True], [None]):
            with self.assertRaises(ValueError):
                self.decoder.decode(value)

    def test_empty_and_unmatched_input(self):
        self.assertEqual(self.decoder.decode([])["status"], "empty")
        self.assertEqual(self.decoder.decode([6, 6, 6])["status"], "no_match")

    def test_invalid_mapping_or_weights(self):
        self.mapping["groups"]["1"]["letters"] += "e"
        with self.assertRaises(ValueError):
            Decoder(self.mapping, [("go", 1)])
        for weight in (0, -1, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                Decoder(self.decoder_mapping(), [("go", weight)])

    def decoder_mapping(self):
        return json.loads((HERE / "gesture_groups.example.json").read_text())

    def test_pruning_is_reported(self):
        result = self.decoder.decode([2, 4, 2, 4, 4, 2], beam_size=1)
        self.assertTrue(result["beam_pruned"])
        self.assertEqual(len(result["candidates"]), 1)

    def test_word_limit_is_explicit(self):
        with self.assertRaises(ValueError):
            self.decoder.decode([2] * 129)

    def test_no_match_counts_as_evaluation_failure(self):
        result = evaluate(self.decoder, [{"gestures": [6, 6], "expected": "go"}])
        self.assertEqual(result["top1_aligned_word_accuracy"], 0)
        self.assertEqual(result["word_error_rate"], 1)
        self.assertEqual(result["counts"]["no_match"], 1)

    def test_segmentation_errors_affect_word_metrics(self):
        self.assertEqual(alignment(["go", "home"], ["go", "ho", "me"]), (2, 1))
        self.assertEqual(alignment(["go", "home"], []), (2, 0))

    def test_evaluation_includes_expected_out_of_vocabulary_words(self):
        result = evaluate(self.decoder, [{"gestures": [2, 4], "expected": "zebra"}])
        self.assertEqual(result["lexicon_word_coverage"], 0)
        self.assertEqual(result["top1_aligned_word_accuracy"], 0)

    def test_missing_key_never_calls_api(self):
        with patch.dict(os.environ, {}, clear=True), patch("urllib.request.urlopen") as request:
            result = gemini_rank(self.decoder.decode([2, 4]))
        request.assert_not_called()
        self.assertEqual(result["source"], "frequency")
        self.assertIn("missing_key", result["gemini_status"])

    def test_gemini_selects_only_a_supplied_candidate(self):
        original = self.decoder.decode([2, 4, 4, 2])
        target = next(c for c in original["candidates"] if c["text"] == "hope")
        probabilities = {c["id"]: 0.0 for c in original["candidates"]}
        probabilities.update({target["id"]: 0.95, "reject": 0.05})
        response = {"answers": {"phrase": {"type": "choice", "choice": target["id"],
                                           "confidence": 0.95, "probabilities": probabilities}}}
        with patch.dict(os.environ, {"GEMINI_API_KEY": "unit-test-placeholder"}), \
                patch("urllib.request.urlopen", return_value=io.BytesIO(json.dumps(response).encode())):
            result = gemini_rank(original, "I have")
        self.assertEqual(result["candidates"][0]["text"], "hope")
        self.assertEqual(result["source"], "gemini_decision")
        self.assertNotIn("gemini_probability", original["candidates"][0])

    def test_invented_gemini_choice_falls_back(self):
        response = {"answers": {"phrase": {"type": "choice", "choice": "invented",
                                           "confidence": 0.99, "probabilities": {"invented": 1.0}}}}
        with patch.dict(os.environ, {"GEMINI_API_KEY": "unit-test-placeholder"}), \
                patch("urllib.request.urlopen", return_value=io.BytesIO(json.dumps(response).encode())):
            result = gemini_rank(self.decoder.decode([2, 4]))
        self.assertEqual(result["gemini_status"], "invalid_response_local_fallback")
        self.assertEqual(result["candidates"][0]["text"], "go")

    def test_api_timeout_retains_local_alternatives(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "unit-test-placeholder"}), \
                patch("urllib.request.urlopen", side_effect=TimeoutError):
            result = gemini_rank(self.decoder.decode([2, 4]))
        self.assertEqual(result["gemini_status"], "connection_error_local_fallback")

    def test_gemini_reject_is_not_committed_or_counted_correct(self):
        original = self.decoder.decode([2, 4])
        probabilities = {c["id"]: 0.0 for c in original["candidates"]}
        probabilities["reject"] = 1.0
        response = {"answers": {"phrase": {"type": "choice", "choice": "reject",
                                           "confidence": 1.0, "probabilities": probabilities}}}
        with patch.dict(os.environ, {"GEMINI_API_KEY": "unit-test-placeholder"}), \
                patch("urllib.request.urlopen", return_value=io.BytesIO(json.dumps(response).encode())):
            result = evaluate(self.decoder, [{"gestures": [2, 4], "expected": "go"}], use_gemini=True)
        self.assertEqual(result["top1_aligned_word_accuracy"], 0)
        self.assertEqual(result["counts"]["uncertain"], 1)


if __name__ == "__main__":
    unittest.main()
