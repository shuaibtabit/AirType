"""Dictionary and beam search for continuous abbreviated T9 input."""

import math
import re


class Decoder:
    """Exact dictionary lattice + bounded unigram beam. No sensor or pair handling."""

    def __init__(self, mapping, entries, *, prefix_length=None):
        if prefix_length is not None and (type(prefix_length) is not int or prefix_length < 1):
            raise ValueError("Prefix length must be a positive integer.")
        groups = mapping["groups"]
        if not isinstance(groups, dict) or not groups:
            raise ValueError("Mapping needs nonempty groups.")
        self.version = mapping.get("version", "unversioned")
        self.aliases = {}
        self.letter_groups = {}
        for group, spec in groups.items():
            if not isinstance(group, str) or not group or re.search(r"[\s,/|]", group):
                raise ValueError("Group IDs must be nonempty tokens without separators.")
            gesture, letters = spec["gesture"], spec["letters"]
            if not isinstance(gesture, str) or not gesture or not letters:
                raise ValueError("Each group needs a gesture name and letters.")
            for alias in (group, gesture):
                if alias in self.aliases and self.aliases[alias] != group:
                    raise ValueError("Gesture aliases must be unique.")
                self.aliases[alias] = group
            for letter in letters:
                if letter not in "abcdefghijklmnopqrstuvwxyz" or letter in self.letter_groups:
                    raise ValueError("Each lowercase ASCII letter must occur exactly once.")
                self.letter_groups[letter] = group
        if set(self.letter_groups) != set("abcdefghijklmnopqrstuvwxyz"):
            raise ValueError("Groups must cover all 26 letters exactly once.")

        weights = {}
        for word, weight in entries:
            if not isinstance(word, str) or not re.fullmatch(r"[a-z]+", word):
                raise ValueError("Lexicon words must be lowercase ASCII letters only.")
            weight = float(weight)
            if not math.isfinite(weight) or weight <= 0:
                raise ValueError("Lexicon weights must be finite and positive.")
            weights[word] = max(weights.get(word, 0), weight)
        if not weights:
            raise ValueError("Lexicon contains no usable words.")
        # Log-sum-exp prevents overflow when importing arbitrary positive weights.
        logs = {word: math.log(weight) for word, weight in weights.items()}
        maximum = max(logs.values())
        normalizer = maximum + math.log(sum(math.exp(v - maximum) for v in logs.values()))
        self.word_scores = {word: score - normalizer for word, score in logs.items()}
        self.index = {}
        for word in weights:
            self.index.setdefault(self.encode(word)[:prefix_length], []).append(word)
        for words in self.index.values():
            words.sort(key=lambda word: (-self.word_scores[word], word))
        self.prefixes = {code[:i] for code in self.index for i in range(1, len(code) + 1)}
        self.max_word_length = max(map(len, self.index))

    def encode(self, word):
        if not isinstance(word, str) or not re.fullmatch(r"[a-z]+", word):
            raise ValueError("Encode one lowercase ASCII word at a time.")
        return tuple(self.letter_groups[letter] for letter in word)

    def tokens(self, gestures):
        if isinstance(gestures, str):
            gestures = gestures.replace(",", " ").split()
        if not isinstance(gestures, (list, tuple)):
            raise ValueError("Gestures must be a list or whitespace-separated tokens.")
        result = []
        for gesture in gestures:
            if isinstance(gesture, bool) or not isinstance(gesture, (str, int)):
                raise ValueError("Each gesture must be a group ID or exact gesture name.")
            key = str(gesture)
            if key not in self.aliases:
                raise ValueError(f"Unknown gesture token: {key!r}")
            result.append(self.aliases[key])
        return tuple(result)

    def decode(self, gestures, beam_size=32, max_tokens=128):
        if not 1 <= beam_size <= 254:
            raise ValueError("Beam size must be between 1 and 254.")
        tokens = self.tokens(gestures)
        if len(tokens) > max_tokens:
            raise ValueError(f"Finish a phrase within {max_tokens} gestures.")
        base = {"mapping_version": self.version, "groups": list(tokens),
                "source": "frequency", "committed": False}
        if not tokens:
            return dict(base, status="empty", candidates=[], beam_pruned=False)

        # Each edge consumes the encoded letters or prefix of one dictionary word.
        # Word boundaries are inferred; no input pauses are needed.
        lattice = [[] for _ in range(len(tokens))]
        for start in range(len(tokens)):
            for end in range(start + 1, min(len(tokens), start + self.max_word_length) + 1):
                code = tokens[start:end]
                if code not in self.prefixes:
                    break
                for word in self.index.get(code, []):
                    lattice[start].append((end, word, self.word_scores[word]))

        beams = [[] for _ in range(len(tokens) + 1)]
        beams[0] = [(0.0, ())]
        pruned = False
        for start in range(len(tokens)):
            beams[start].sort(key=lambda item: (-item[0], item[1]))
            if len(beams[start]) > beam_size:
                pruned = True
                del beams[start][beam_size:]
            for score, words in beams[start]:
                for end, word, word_score in lattice[start]:
                    beams[end].append((score + word_score, words + (word,)))
                    # Bound intermediate storage while preserving the top unigram paths.
                    if len(beams[end]) > beam_size * 2:
                        beams[end].sort(key=lambda item: (-item[0], item[1]))
                        del beams[end][beam_size:]
                        pruned = True
        complete = sorted(beams[-1], key=lambda item: (-item[0], item[1]))
        if len(complete) > beam_size:
            pruned = True
        candidates = [
            {"id": f"p{i:03d}", "text": " ".join(words), "words": list(words),
             "log_score": score}
            for i, (score, words) in enumerate(complete[:beam_size])
        ]
        return dict(base, status="ok" if candidates else "no_match",
                    candidates=candidates, beam_pruned=pruned)
