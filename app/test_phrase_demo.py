import unittest

from decoder import load_layout
from phrase_demo import PHRASES, PhraseSession
from session import Show


class PhraseDemoTests(unittest.TestCase):
    def enter(self, digits):
        layout = load_layout()
        session = PhraseSession(layout)
        for i, digit in enumerate(digits):
            # Deliberately exceed a legacy word pause while staying within a phrase.
            t = i * 3.5
            session.on_gesture(list(layout)[int(digit)-1], t, t+.4, t)
            self.assertEqual(session.on_tick(t+2), [])
        return session.on_tick(len(digits)*3.5+6)

    def test_preview_outputs_both_phrases_without_typing(self):
        self.assertEqual(self.enter('2452'), [Show('Decoded', PHRASES[0][1])])
        self.assertEqual(self.enter('5242'), [Show('Decoded', PHRASES[1][1])])

    def test_one_missing_signal_can_be_recovered(self):
        self.assertEqual(self.enter('452'), [Show('Decoded', PHRASES[0][1])])

    def test_ambiguous_and_faraway_codes_abstain(self):
        self.assertEqual(self.enter('242')[0].status, 'Try again')
        self.assertEqual(self.enter('6666')[0].status, 'Try again')



class PhraseOutputTests(unittest.TestCase):
    def test_speech_output_does_not_show_plaintext_or_type(self):
        from contextlib import redirect_stdout
        from io import StringIO
        from unittest.mock import Mock

        from airtype import Screen

        phrase = PHRASES[2][1]
        speaker = Mock()
        overlay = Mock()
        overlay.poll.return_value = None
        with redirect_stdout(StringIO()) as terminal:
            Screen(overlay, typing=False, phrase_output='speak', speaker=speaker).apply([Show('Decoded', phrase)])
        speaker.speak.assert_called_once_with(phrase)
        self.assertNotIn(phrase, terminal.getvalue())
        message = overlay.stdin.write.call_args.args[0]
        self.assertNotIn(phrase, message)
        self.assertNotIn('"type"', message)

    def test_typing_is_explicit(self):
        from contextlib import redirect_stdout
        from io import StringIO
        import json
        from unittest.mock import Mock

        from airtype import Screen

        phrase = PHRASES[0][1]
        overlay = Mock()
        overlay.poll.return_value = None
        with redirect_stdout(StringIO()):
            Screen(overlay, typing=False).apply([Show('Decoded', phrase)])
            self.assertNotIn('type', json.loads(overlay.stdin.write.call_args.args[0]))
            Screen(overlay, typing=True, phrase_output='type').apply([Show('Decoded', phrase)])
        self.assertEqual(json.loads(overlay.stdin.write.call_args.args[0]), {'type': phrase + ' '})

    def test_prefix_can_type_and_speak_without_delivering_dictionary_fallback(self):
        from contextlib import redirect_stdout
        from io import StringIO
        import json
        from unittest.mock import Mock

        from airtype import Screen

        overlay = Mock()
        overlay.poll.return_value = None
        speaker = Mock()
        screen = Screen(overlay, typing=True, phrase_output="both", speaker=speaker)
        screen.audit = StringIO()
        with redirect_stdout(StringIO()):
            screen.apply([
                Show("Listening", "Gesture code 24235"),
                Show("Dictionary fallback", "go fire"),
                Show("OpenAI suggestion", "Go first."),
            ])

        messages = [json.loads(call.args[0]) for call in overlay.stdin.write.call_args_list]
        self.assertEqual([message["type"] for message in messages if "type" in message], ["Go first. "])
        speaker.speak.assert_called_once_with("Go first.")
        self.assertEqual(screen.audit.getvalue(),
                         "Gesture code 24235\nDictionary fallback\nOpenAI suggestion\n")
