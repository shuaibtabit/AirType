"""Expand spoken-language shortcuts from the detector's existing gesture groups."""

import json
import math

from decoder import Lexicon
from session import Session, Show
from t9_decoder import gemini_rank

PHRASES = (
    ("hnse", "Hey, my name is Shuaib. I am excited."),
    ("sepe", "Send email to prof asking for extension."),
    ("wkdr", "Please walk to the door."),
)


def edit_distance(first, second):
    """Count missing, extra, or substituted gestures."""
    previous = list(range(len(second) + 1))
    for i, event in enumerate(first, 1):
        row = [i]
        for j, target in enumerate(second, 1):
            row.append(min(row[-1] + 1, previous[j] + 1, previous[j - 1] + (event != target)))
        previous = row
    return previous[-1]


class PhraseSession(Session):
    """Collect a single gesture buffer and display the decoded phrase."""

    def __init__(self, layout, *, sentence_gap=6.0, use_gemini=False):
        super().__init__(Lexicon([], layout), word_gap=math.inf,
                         sentence_gap=sentence_gap, always_on=True)
        self.layout = layout
        self.digit = {label: str(i) for i, label in enumerate(layout, start=1)}
        self.codes = [(self.lexicon.code_of(shortcut), phrase) for shortcut, phrase in PHRASES]
        if any(not code for code, _ in self.codes):
            raise ValueError("A phrase shortcut contains a letter outside the layout.")
        self.use_gemini = use_gemini

    def ready(self):
        return [Show("Listening", "Enter an abbreviated phrase")]

    def _preview(self):
        return "Gesture code " + self._digits(self.current)

    def _digits(self, code):
        return "".join(self.digit[label] for label in code)

    def on_tick(self, now):
        if self.current and self.last_heard is not None and now - self.last_heard > self.sentence_gap:
            # Leave the sentence visible until the wearer begins the next one.
            return self._commit()
        return []

    def _commit(self):
        if not self.current:
            return []
        code = tuple(self.current)
        self.current = []
        self.last_end = None
        self.last_heard = None
        digits = self._digits(code)
        scores = [(edit_distance(code, expected), phrase) for expected, phrase in self.codes]
        best = min(distance for distance, _ in scores)
        if best > 1:
            return [Show("Try again", f"No phrase close to {digits}")]
        matches = [phrase for distance, phrase in scores if distance == best]
        if len(matches) == 1:
            return [Show("Decoded", matches[0])]
        if self.use_gemini:
            context = json.dumps({
                "observed_t9_digits": digits,
                "letter_groups": {self.digit[label]: letters for label, letters in self.layout.items()},
            })
            result = gemini_rank({
                "status": "uncertain",
                "source": "shortcut_matching",
                "candidates": [{"id": f"p{i}", "text": phrase, "log_score": -best}
                               for i, phrase in enumerate(matches)],
            }, context=context)
            if result["source"] == "gemini_decision" and result["status"] == "ok":
                return [Show("Decoded", result["candidates"][0]["text"])]
        return [Show("Try again", f"Gesture code {digits} matches more than one phrase")]
