"""Run: python3 -B -m unittest discover -s app"""

import unittest

from decoder import Lexicon, first_choices, load_layout, load_words
from session import Session, Show, TypeText
from taps import double_taps

LAYOUT = {"roll_in": "abcd", "roll_out": "efgh", "tilt_up": "ijkl",
          "tilt_down": "mnop", "swing_left": "qrst", "swing_right": "uvwxyz"}
GO = ["roll_out", "tilt_down"]
HOME = ["roll_out", "tilt_down", "tilt_down", "roll_out"]


def lexicon():
    return Lexicon(["go", "home", "gone", "hope", "en"], LAYOUT)


class DecoderTests(unittest.TestCase):
    def test_words_sharing_a_sequence_keep_list_order(self):
        self.assertEqual(lexicon().candidates(HOME), ["home", "gone", "hope"])
        self.assertEqual(lexicon().candidates(GO), ["go", "en"])

    def test_unknown_sequence_has_no_candidates_and_shows_a_placeholder(self):
        self.assertEqual(lexicon().candidates(["swing_right"] * 3), [])
        self.assertEqual(first_choices([["go"], []]), "go ?")

    def test_words_with_letters_outside_the_layout_are_skipped(self):
        self.assertEqual(Lexicon(["it's", "go"], LAYOUT).by_code, {tuple(GO): ["go"]})

    def test_shipped_layout_covers_the_alphabet_and_every_shipped_word(self):
        layout = load_layout()
        self.assertEqual(sorted("".join(layout.values())), list("abcdefghijklmnopqrstuvwxyz"))
        shipped = Lexicon(load_words(), layout)
        self.assertTrue(all(shipped.code_of(word) for word in load_words()))
        self.assertIn("hello", shipped.candidates(shipped.code_of("hello")))


class SessionTests(unittest.TestCase):
    def enter(self, session, words, start=0.0, step=1.0, gap=5.0):
        time = start
        for word in words:
            for label in word:
                session.on_gesture(label, time, time + 0.5, time)
                time += step
            time += gap
        return time

    def test_asleep_until_double_tap(self):
        session = Session(lexicon())
        self.assertEqual(session.on_gesture("roll_out", 0, 0.5, 0), [])
        self.assertEqual(session.on_double_tap(1)[0].status, "Listening")

    def test_gap_splits_words_and_second_double_tap_types_the_sentence(self):
        session = Session(lexicon())
        session.on_double_tap(0)
        end = self.enter(session, [GO, HOME], gap=3.5)
        actions = session.on_double_tap(end)
        self.assertEqual(actions[0], TypeText("go home "))
        self.assertEqual(actions[-1].status, "Asleep")
        self.assertFalse(session.active)

    def test_short_gaps_stay_in_one_word(self):
        session = Session(lexicon(), always_on=True)
        self.enter(session, [HOME], step=2.0)
        self.assertEqual(session.words, [])
        self.assertEqual(session.current, HOME)

    def test_silence_commits_and_always_on_keeps_listening(self):
        session = Session(lexicon(), always_on=True, sentence_gap=6)
        self.enter(session, [GO])
        self.assertEqual(session.on_tick(4), [])
        actions = session.on_tick(30)
        self.assertEqual(actions[0], TypeText("go "))
        self.assertTrue(session.active)
        self.assertEqual(session.on_tick(60), [])

    def test_preview_lists_candidates_for_the_word_in_progress(self):
        session = Session(lexicon(), always_on=True)
        shown = [session.on_gesture(label, i, i + 0.5, i) for i, label in enumerate(HOME)][-1]
        self.assertIsInstance(shown[0], Show)
        self.assertIn("home / gone / hope", shown[0].detail)

    def test_chooser_receives_candidate_lists(self):
        seen = []
        session = Session(lexicon(), always_on=True, choose=lambda lists: seen.append(lists) or "go hope")
        end = self.enter(session, [GO, HOME], gap=3.5)
        self.assertEqual(session.on_double_tap(end)[0], TypeText("go hope "))
        self.assertEqual(seen, [[["go", "en"], ["home", "gone", "hope"]]])

    def test_labels_outside_the_layout_are_ignored(self):
        session = Session(lexicon(), always_on=True)
        self.assertEqual(session.on_gesture("background", 0, 1, 0), [])


class TapTests(unittest.TestCase):
    HEADER = "estimated_sample_unix_s,ax_g,ay_g,az_g\n"

    def lines(self, spikes, seconds=4.0):
        rows = [self.HEADER]
        for index in range(int(seconds * 100)):
            time = index / 100
            z = 2.5 if any(abs(time - spike) < 0.005 for spike in spikes) else 1.0
            rows.append(f"{time},0.0,0.0,{z}\n")
        return rows

    def taps(self, spikes):
        found = []
        lines = self.lines(spikes)
        self.assertEqual(list(double_taps(lines, found.append)), lines)
        return found

    def test_two_quick_taps_count_once(self):
        self.assertEqual(len(self.taps([1.0, 1.3])), 1)

    def test_single_tap_and_slow_pair_do_not_count(self):
        self.assertEqual(self.taps([1.0]), [])
        self.assertEqual(self.taps([1.0, 2.5]), [])

    def test_still_wrist_does_not_count(self):
        self.assertEqual(self.taps([]), [])


if __name__ == "__main__":
    unittest.main()
