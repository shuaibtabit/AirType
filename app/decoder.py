"""Turn gesture sequences into candidate words. Plain lookups, no model."""

import json
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

APP = Path(__file__).resolve().parent
Code = Tuple[str, ...]
UNKNOWN = "?"


def load_layout(path: Path = APP / "layout.json") -> Dict[str, str]:
    groups = json.loads(path.read_text())["groups"]
    letters = "".join(groups.values())
    if len(set(letters)) != len(letters):
        raise ValueError("A letter appears in more than one gesture group.")
    return groups


def load_words(path: Path = APP / "words.txt") -> List[str]:
    lines = (line.strip().lower() for line in path.read_text().splitlines())
    return list(dict.fromkeys(line for line in lines if line and not line.startswith("#")))


class Lexicon:
    """Words indexed by the gesture sequence that spells them, most likely first."""

    def __init__(self, words: Iterable[str], layout: Dict[str, str]) -> None:
        self.gesture_of = {letter: gesture for gesture, letters in layout.items() for letter in letters}
        self.by_code: Dict[Code, List[str]] = {}
        for word in words:
            code = self.code_of(word)
            if code and word not in self.by_code.setdefault(code, []):
                self.by_code[code].append(word)

    def by_gesture(self) -> set:
        return set(self.gesture_of.values())

    def code_of(self, word: str) -> Code:
        """The gesture sequence for a word, or () if it has a letter outside the layout."""
        try:
            return tuple(self.gesture_of[letter] for letter in word.lower())
        except KeyError:
            return ()

    def candidates(self, code: Sequence[str]) -> List[str]:
        return list(self.by_code.get(tuple(code), []))


def first_choices(candidate_lists: Sequence[Sequence[str]]) -> str:
    """Pick the most likely word for each position. Unmatched sequences show as '?'."""
    return " ".join(words[0] if words else UNKNOWN for words in candidate_lists)
