import json
import os
import unittest
from unittest.mock import patch

from llm_decoder import decode_llm, evaluate_llm
from t9_decoder import Decoder, HERE


class LLMTests(unittest.TestCase):
    def setUp(self):
        self.decoder = Decoder(json.loads((HERE / "gesture_groups.example.json").read_text()), [("a", 1)])
        self.env = patch.dict(os.environ, {"GEMINI_API_KEY": "test-placeholder"})
        self.env.start()
        self.addCleanup(self.env.stop)

    def run_response(self, raw, sequence="242442", **kwargs):
        with patch("llm_decoder.call_gemini", return_value=raw):
            return decode_llm(self.decoder, sequence, **kwargs)

    def test_valid_go_home_auto_commits(self):
        r = self.run_response({"status": "ok", "suggestions": ["go home", "go hope"]},
                              automatic=True, finalized=True)
        self.assertEqual(r["committed_text"], "go home")

    def test_other_phrase_examples_roundtrip(self):
        for phrase in ("help me", "hello world", "i need water", "please call me", "my name is shayaan"):
            sequence = ''.join(g for w in phrase.split() for g in self.decoder.encode(w))
            r = self.run_response({"status": "ok", "suggestions": [phrase]}, sequence)
            self.assertEqual(r["suggestions"][0]["text"], phrase)

    def test_wrong_letters_are_filtered_not_rewritten(self):
        r = self.run_response({"status": "ok", "suggestions": ["hello world", "go home"]},
                              automatic=True, finalized=True)
        self.assertEqual(r["invalid_suggestions"], 1)
        self.assertFalse(r["committed"])
        self.assertEqual(r["status"], "uncertain")

    def test_no_inserting_deleting_or_reordering_letters(self):
        for text in ("go homes", "go ho", "og home"):
            r = self.run_response({"status": "ok", "suggestions": [text]})
            self.assertFalse(r["suggestions"])

    def test_preview_does_not_commit(self):
        r = self.run_response({"status": "ok", "suggestions": ["go home"]}, automatic=True)
        self.assertFalse(r["committed"])

    def test_uncertain_does_not_commit(self):
        r = self.run_response({"status": "uncertain", "suggestions": ["go home", "go hope"]},
                              automatic=True, finalized=True)
        self.assertFalse(r["committed"])

    def test_duplicates_punctuation_and_nontext(self):
        r = self.run_response({"status": "ok", "suggestions": ["go home", "go home", "Go home!", 42]})
        self.assertEqual(len(r["suggestions"]), 1)
        self.assertEqual(r["invalid_suggestions"], 2)

    def test_api_failure_no_commit_or_secret_output(self):
        with patch("llm_decoder.call_gemini", side_effect=TimeoutError("secret text")):
            r = decode_llm(self.decoder, "242442", automatic=True, finalized=True)
        self.assertFalse(r["committed"])
        self.assertNotIn("secret text", json.dumps(r))

    def test_missing_key_does_not_call_api(self):
        with patch.dict(os.environ, {}, clear=True), patch("llm_decoder.call_gemini") as call:
            r = decode_llm(self.decoder, "242442")
        call.assert_not_called()
        self.assertEqual(r["status"], "missing_key")

    def test_empty_and_unknown_input(self):
        with patch("llm_decoder.call_gemini") as call:
            self.assertEqual(decode_llm(self.decoder, "")["status"], "empty")
            with self.assertRaises(ValueError):
                decode_llm(self.decoder, "7")
        call.assert_not_called()

    def test_context_sent_without_expected_answer(self):
        with patch("llm_decoder.call_gemini", return_value={"status": "ok", "suggestions": ["go home"]}) as call:
            report = evaluate_llm(self.decoder, [{"gestures": "242442", "context": "I want to", "expected": "go home"}], automatic=True)
        payload = call.call_args.args[0]
        self.assertEqual(payload["preceding_confirmed_text"], "I want to")
        self.assertNotIn("expected", payload)
        self.assertNotIn("go home", json.dumps(payload))
        self.assertEqual(report["auto_commit_rate"], 1)

    def test_abstention_is_counted_as_miss(self):
        with patch("llm_decoder.call_gemini", return_value={"status": "uncertain", "suggestions": []}):
            report = evaluate_llm(self.decoder, [{"gestures": "242442", "expected": "go home"}], automatic=True)
        self.assertEqual(report["top1_aligned_word_accuracy"], 0)
        self.assertIsNone(report["auto_commit_phrase_accuracy"])

    def test_malformed_response(self):
        for raw in ({}, [], {"status": "ok", "suggestions": "go home"}):
            self.assertEqual(self.run_response(raw)["status"], "invalid_response")


if __name__ == "__main__":
    unittest.main()
