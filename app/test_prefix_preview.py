import unittest
from unittest.mock import patch

from decoder import load_layout
from prefix_preview import PrefixSession
from session import Show

WORDS = ["send", "show", "email", "to"]


class PrefixPreviewTests(unittest.TestCase):
    def enter(self, words, *, openai_key=None):
        session = PrefixSession(load_layout(), WORDS, openai_key=openai_key)
        code = [label for word in words for label in session.lexicon.code_of(word[:3])]
        for i, label in enumerate(code):
            t = i * 3.5
            session.on_gesture(label, t, t+.4, t)
        return session.on_tick(len(code) * 3.5 + 6)

    def test_full_words_from_prefixes_and_short_words_with_no_spaces(self):
        actions = self.enter(["send", "email", "to"])
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].status, "Candidates")
        self.assertIn("send email to", actions[0].detail.splitlines())
        self.assertIn("show email to", actions[0].detail.splitlines())

    def test_unmatched_input_requests_retry(self):
        self.assertEqual(self.enter(["zzz"]), [Show("Try again", "No supported phrase matches those groups.")])

    def test_full_sequence_and_dictionary_candidates_reach_openai(self):
        with patch("prefix_preview.suggest_sentence", return_value="Send email.") as decode:
            result = self.enter(["send", "email"], openai_key="mock-key")
        self.assertEqual(result, [Show("OpenAI suggestion", "Send email.")])
        _, groups, mapping, candidates, vocabulary, _ = decode.call_args.args
        self.assertEqual(groups, list("524241"))
        self.assertEqual(mapping["5"]["letters"], "qrst")
        self.assertEqual(set(candidates), {"send email", "show email"})
        self.assertIn("send", vocabulary)

    def test_unsupported_openai_guess_keeps_dictionary_candidates(self):
        with patch("prefix_preview.suggest_sentence", return_value="Completely unrelated suggestion."):
            self.assertEqual(self.enter(["send", "email"], openai_key="mock-key")[0].status,
                             "Dictionary fallback")
