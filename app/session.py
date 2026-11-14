"""Activation, word boundaries and sentence commit for gesture typing. Pure logic, no I/O."""

from dataclasses import dataclass
from typing import Callable, List, Optional, Sequence, Union

from decoder import Lexicon, first_choices

SYMBOLS = {"roll_in": "⟲", "roll_out": "⟳", "tilt_up": "↑", "tilt_down": "↓",
           "swing_left": "←", "swing_right": "→"}
MAX_SHOWN_CANDIDATES = 4


@dataclass(frozen=True)
class Show:
    status: str
    detail: str


@dataclass(frozen=True)
class TypeText:
    text: str


Action = Union[Show, TypeText]
Chooser = Callable[[Sequence[Sequence[str]]], str]


class Session:
    """Double tap toggles listening. A gap between gestures ends a word. Silence or a
    double tap ends the sentence and types it."""

    def __init__(self, lexicon: Lexicon, *, word_gap: float = 3.0, sentence_gap: float = 6.0,
                 always_on: bool = False, choose: Chooser = first_choices) -> None:
        self.lexicon = lexicon
        self.word_gap = word_gap
        self.sentence_gap = sentence_gap
        self.always_on = always_on
        self.choose = choose
        self.active = always_on
        self.words: List[List[str]] = []
        self.current: List[str] = []
        self.last_end: Optional[float] = None
        self.last_heard: Optional[float] = None

    def ready(self) -> List[Action]:
        if self.active:
            return [Show("Listening", "Gesture to type")]
        return [Show("Asleep", "Double tap the strap to start")]

    def on_double_tap(self, now: float) -> List[Action]:
        if not self.active:
            self.active = True
            self.last_heard = now
            return [Show("Listening", "Gesture to type")]
        actions = self._commit()
        if not self.always_on:
            self.active = False
            actions.append(Show("Asleep", "Double tap the strap to start"))
        return actions

    def on_gesture(self, label: str, start: float, end: float, now: float) -> List[Action]:
        """`start` and `end` are strap-stream seconds. `now` is the host clock."""
        if not self.active or label not in self.lexicon.by_gesture():
            return []
        if self.current and self.last_end is not None and start - self.last_end > self.word_gap:
            self._close_word()
        self.current.append(label)
        self.last_end = end
        self.last_heard = now
        return [Show("Listening", self._preview())]

    def on_tick(self, now: float) -> List[Action]:
        heard = self.active and (self.words or self.current) and self.last_heard is not None
        if heard and now - self.last_heard > self.sentence_gap:
            return self._commit() + self.ready()
        return []

    def _close_word(self) -> None:
        if self.current:
            self.words.append(self.current)
            self.current = []

    def _preview(self) -> str:
        done = [(self.lexicon.candidates(code) or ["?"])[0] for code in self.words]
        options = self.lexicon.candidates(self.current)[:MAX_SHOWN_CANDIDATES]
        strokes = "".join(SYMBOLS.get(label, "·") for label in self.current)
        current = f"{strokes}  {' / '.join(options) if options else '…'}"
        return " ".join(done + [current])

    def _commit(self) -> List[Action]:
        self._close_word()
        if not self.words:
            return []
        sentence = self.choose([self.lexicon.candidates(code) for code in self.words])
        self.words = []
        self.last_end = None
        self.last_heard = None
        return [TypeText(sentence + " "), Show("Typed", sentence)]
