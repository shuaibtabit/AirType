"""Preview words from up to three gesture groups per word, with inferred spaces."""

import math
import re

from decoder import Lexicon
from session import Session, Show
from prefix_decoder import Decoder
from phrase_demo import edit_distance
from openai_prefix import suggest_sentence

PREFIX_LETTERS = 3
MAX_TOKENS = 48
BEAM_SIZE = 32


class PrefixSession(Session):
    def __init__(self, layout, words, *, sentence_gap=6.0, openai_key=None, context=""):
        super().__init__(Lexicon([], layout), word_gap=math.inf,
                         sentence_gap=sentence_gap, always_on=True)
        self.digit = {label: str(i) for i, label in enumerate(layout, start=1)}
        self.mapping = {self.digit[label]: {"gesture": label, "letters": letters}
                        for label, letters in layout.items()}
        self.decoder = Decoder({"version": "three-letter-prefix", "groups": self.mapping},
                               [(word, 1 / (1 + i)) for i, word in enumerate(words)],
                               prefix_length=PREFIX_LETTERS)
        self.words = words[:60]
        self.openai_key = openai_key
        self.context = context

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
        candidates = [candidate["text"] for candidate in result["candidates"][:8]]
        if self.openai_key:
            try:
                sentence = suggest_sentence(self.openai_key, result["groups"], self.mapping,
                                            candidates, self.words, self.context)
            except (OSError, ValueError, KeyError, TypeError, AttributeError):
                sentence = None
            if sentence and re.fullmatch(r"[A-Za-z][A-Za-z .,!?'-]{0,239}", sentence):
                words = re.findall(r"[a-z]+", sentence.lower().replace("'", ""))
                encoded = [group for word in words for group in self.decoder.encode(word[:PREFIX_LETTERS])]
                if edit_distance(result["groups"], encoded) <= 1:
                    return [Show("OpenAI suggestion", sentence)]
        if not candidates:
            return [Show("Try again", "No supported phrase matches those groups.")]
        status = "Dictionary fallback" if self.openai_key else "Candidates"
        return [Show(status, "\n".join(candidates[:3]))]
