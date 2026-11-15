import unittest
from unittest.mock import patch

from decoder import load_layout
from prefix_preview import PrefixSession
from session import Show

WORDS = ["send", "show", "email", "to"]


class PrefixPreviewTests(unittest.TestCase):
    def enter(self, words, *, gemini=False):
        session = PrefixSession(load_layout(), WORDS, use_gemini=gemini)
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
        self.assertEqual(self.enter(["zzz"]), [Show("Try again", "No dictionary phrase matches those groups.")])

    def test_optional_ranker_receives_only_dictionary_candidates(self):
        def rank(result, **kwargs):
            self.assertEqual({c["text"] for c in result["candidates"]}, {"send email", "show email"})
            self.assertIn('"groups"', kwargs["context"])
            return dict(result, source="gemini_decision")
        with patch("prefix_preview.gemini_rank", side_effect=rank):
            self.assertEqual(self.enter(["send", "email"], gemini=True)[0].status, "Gemini suggestions")
