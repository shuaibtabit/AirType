import contextlib
from io import StringIO
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from airtype import run_stream
from decoder import load_layout
from phrase_demo import PhraseSession
from session import Show


class ControlsTests(unittest.TestCase):
    def test_finish_decodes_only_gestures_after_start_and_clear_discards_input(self):
        layout = load_layout()
        labels = list(layout)
        session = PhraseSession(layout)
        screen = Mock()

        def gesture(digit, time):
            return ("gesture", SimpleNamespace(direction=labels[int(digit) - 1],
                                               start=time, end=time + .4))

        events = [
            ("streaming", None),
            gesture("1", 0),
            ("control", "start"),
            gesture("6", 1),
            ("control", "clear"),
            gesture("1", 2),
            ("control", "start"),
            *(gesture(digit, time) for time, digit in enumerate("2452", start=3)),
            ("control", "finish"),
            gesture("1", 7),
            ("end", None),
        ]
        with patch("airtype.threading.Thread"), patch("airtype.queue.Queue") as queue:
            queue.return_value.get.side_effect = events
            with contextlib.redirect_stdout(StringIO()):
                run_stream([], None, session, screen, use_taps=False, controls=[])

        shows = [show for call in screen.apply.call_args_list for show in call.args[0]]
        self.assertEqual([show.detail for show in shows if show.status == "Decoded"],
                         ["Hey, my name is Shuaib. I am excited."])
        self.assertNotIn(Show("Listening", "Gesture code 1"), shows)
        self.assertEqual(session.current, [])
        self.assertFalse(session.active)

    def test_finder_disconnect_exits_without_decoding_unfinished_phrase(self):
        layout = load_layout()
        session = PhraseSession(layout)
        screen = Mock()
        events = [
            ("streaming", None),
            ("control", "start"),
            ("gesture", SimpleNamespace(direction="roll_out", start=1.0, end=1.5)),
            ("control", "stop"),
        ]
        with patch("airtype.threading.Thread"), patch("airtype.queue.Queue") as queue:
            queue.return_value.get.side_effect = events
            with contextlib.redirect_stdout(StringIO()):
                run_stream([], None, session, screen, use_taps=False, controls=[])
        shows = [show for call in screen.apply.call_args_list for show in call.args[0]]
        self.assertEqual(shows[-1], Show("Listening", "Gesture code 2"))
