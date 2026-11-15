"""Preview words from up to three gesture groups per word, with inferred spaces."""

import json
import math

from decoder import Lexicon
from session import Session, Show
from t9_decoder import Decoder, gemini_rank

PREFIX_LETTERS = 3
MAX_TOKENS = 48
BEAM_SIZE = 32


class PrefixSession(Session):
    def __init__(self, layout, words, *, sentence_gap=6.0, use_gemini=False):
        super().__init__(Lexicon([], layout), word_gap=math.inf,
                         sentence_gap=sentence_gap, always_on=True)
        self.digit = {label: str(i) for i, label in enumerate(layout, start=1)}
        self.mapping = {self.digit[label]: {"gesture": label, "letters": letters}
                        for label, letters in layout.items()}
        self.decoder = Decoder({"version": "three-letter-prefix", "groups": self.mapping},
                               [(word, 1 / (1 + i)) for i, word in enumerate(words)],
                               prefix_length=PREFIX_LETTERS)
        self.use_gemini = use_gemini

    def ready(self):
        return [Show("Listening", "Enter up to three letters per word. Pause to finish the phrase.")]

    def _preview(self):
        return "Gesture code " + "".join(self.digit[label] for label in self.current)

    def on_gesture(self, label, start, end, now):
        if len(self.current) >= MAX_TOKENS:
            self.current.clear()
            self.last_end = self.last_heard = None
            return [Show("Try again", f"Finish within {MAX_TOKENS} gestures.")]
        return super().on_gesture(label, start, end, now)

    def on_tick(self, now):
        if self.current and self.last_heard is not None and now - self.last_heard > self.sentence_gap:
            return self._commit()
        return []

    def _commit(self):
        if not self.current:
            return []
        result = self.decoder.decode(self.current, beam_size=BEAM_SIZE, max_tokens=MAX_TOKENS)
        self.current.clear()
        self.last_end = self.last_heard = None
        if not result["candidates"]:
            return [Show("Try again", "No dictionary phrase matches those groups.")]
        if self.use_gemini and len(result["candidates"]) > 1:
            result = gemini_rank(result, context=json.dumps({
                "groups": result["groups"],
                "letter_groups": self.mapping,
                "letters_per_word": "first three letters, or all letters of a shorter word",
            }))
        status = "Candidates"
        if result["status"] == "uncertain":
            status = "Uncertain"
        elif result["source"] == "gemini_decision":
            status = "Gemini suggestions"
        return [Show(status, "\n".join(candidate["text"] for candidate in result["candidates"][:3]))]
