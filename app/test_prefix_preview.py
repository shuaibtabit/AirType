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

    def test_automatic_session_routes_shortcuts_and_new_sentences(self):
        layout = load_layout()
        session = PrefixSession(layout, ["go", "first"], openai_key="mock-key", prefer_shortcuts=True)

        def enter(digits):
            for i, digit in enumerate(digits):
                session.on_gesture(list(layout)[int(digit) - 1], i, i + .4, i)
            return session.on_tick(len(digits) + 6)

        intro = Show("Decoded", "Hey, my name is Shuaib. I am excited.")
        extension = Show("Decoded", "Send email to prof asking for extension.")
        with patch("prefix_preview.suggest_sentence", return_value="Go first.") as decode:
            self.assertEqual(enter("2452"), [intro])
            self.assertEqual(enter("452"), [intro])
            self.assertEqual(enter("52642"), [extension])
            decode.assert_not_called()

            self.assertEqual(enter("24235"), [Show("OpenAI suggestion", "Go first.")])
            self.assertEqual(decode.call_args.args[1], list("24235"))

            self.assertEqual(enter("242")[0].status, "Try again")
            self.assertEqual(decode.call_args.args[1], list("242"))
