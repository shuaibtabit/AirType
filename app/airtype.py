"""AirType demo app: wrist gestures in, text typed into whichever app is focused.

Double tap the strap to start listening, gesture one letter group at a time,
pause between words, and double tap again (or stay silent) to type the sentence.

  python3 -B app/airtype.py '<UUID>' --allow-mac-bond          live from the strap
  python3 -B app/airtype.py --replay motion.csv --realtime     replay a recording
  python3 -B app/airtype.py --keys                             keyboard stand-in, no strap
"""

import argparse
import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Iterable, Iterator, List, Optional, Sequence

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ml"))

from decoder import Lexicon, first_choices, load_layout, load_words  # noqa: E402
from session import Action, Session, Show, TypeText  # noqa: E402
from taps import double_taps  # noqa: E402

OVERLAY = ROOT / ".build/debug/airtype-overlay"
DEFAULT_MODEL = ROOT / "models/six-model.joblib"
TICK_SECONDS = 0.25
LLM_MODEL = "claude-haiku-5-5"
LLM_TIMEOUT_SECONDS = 8
KEY_HELP = "Keys: 1-6 = gestures in layout order, space = next word, Enter = type it, t = double tap, q = quit."


class Screen:
    """Mirror every update to the terminal, and to the floating overlay when it is running."""

    def __init__(self, overlay: Optional[subprocess.Popen], typing: bool,
                 *, phrase_output: str = "preview", speaker=None) -> None:
        self.overlay = overlay
        self.typing = typing
        self.phrase_output = phrase_output
        self.speaker = speaker

    def apply(self, actions: Iterable[Action]) -> None:
        for action in actions:
            if isinstance(action, Show):
                if action.status == "Decoded" and self.speaker is not None:
                    print("[Speech] Sending phrase to the selected audio output", flush=True)
                    self._send({"status": "Speech", "detail": "Sending phrase to audio output"})
                    self.speaker.speak(action.detail)
                    continue
                print(f"[{action.status}] {action.detail}", flush=True)
                self._send({"status": action.status, "detail": action.detail})
                if action.status == "Decoded" and self.phrase_output == "type":
                    self._send({"type": action.detail + " "})
            elif isinstance(action, TypeText):
                print(f"TYPE: {action.text!r}", flush=True)
                if self.typing:
                    self._send({"type": action.text})

    def _send(self, message: dict) -> None:
        if self.overlay is None or self.overlay.poll() is not None:
            return
        try:
            self.overlay.stdin.write(json.dumps(message) + "\n")
            self.overlay.stdin.flush()
        except (BrokenPipeError, OSError) as error:
            print(f"Overlay stopped responding: {error}", flush=True)
            self.overlay = None


def llm_chooser(api_key: str):
    """Let an LLM pick one word per position. Falls back to first choices on any failure.
    This sends the candidate words to Anthropic's API."""

    def choose(candidate_lists: Sequence[Sequence[str]]) -> str:
        fallback = first_choices(candidate_lists)
        if all(len(words) <= 1 for words in candidate_lists):
            return fallback
        prompt = ("Each list holds the possible words for one position in a short sentence or command. "
                  "Pick exactly one word from each list, in order, to make the most sensible phrase. "
                  "An empty list means an unknown word: write ? there. "
                  "Reply with only the chosen words separated by spaces.\n"
                  + json.dumps([list(words) for words in candidate_lists]))
        request = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=json.dumps({"model": LLM_MODEL, "max_tokens": 100,
                             "messages": [{"role": "user", "content": prompt}]}).encode(),
            headers={"x-api-key": api_key, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=LLM_TIMEOUT_SECONDS) as response:
                reply = json.load(response)["content"][0]["text"].strip().lower().split()
        except (urllib.error.URLError, TimeoutError, KeyError, IndexError, ValueError) as error:
            print(f"LLM unavailable ({error}); using first choices.", flush=True)
            return fallback
        valid = len(reply) == len(candidate_lists) and all(
            word in words or (not words and word == "?") for word, words in zip(reply, candidate_lists))
        if not valid:
            print(f"LLM reply did not match the candidates ({' '.join(reply)!r}); using first choices.", flush=True)
            return fallback
        return " ".join(reply)

    return choose


def pump_gestures(lines: Iterable[str], detector, events: queue.Queue, use_taps: bool = True) -> None:
    """Background thread: raw CSV lines → double taps and classified gestures."""
    try:
        if use_taps:
            lines = double_taps(lines, lambda _: events.put(("tap", None)))
        for event in detector(lines):
            events.put(("gesture", event))
        events.put(("end", None))
    except Exception as error:  # surfaced on the main thread
        events.put(("error", error))


def run_stream(lines: Iterable[str], detector, session: Session, screen: Screen, *, use_taps: bool = True) -> None:
    events: queue.Queue = queue.Queue()
    threading.Thread(target=pump_gestures, args=(lines, detector, events, use_taps), daemon=True).start()
    screen.apply(session.ready())
    while True:
        try:
            kind, payload = events.get(timeout=TICK_SECONDS)
        except queue.Empty:
            screen.apply(session.on_tick(time.monotonic()))
            continue
        now = time.monotonic()
        if kind == "gesture":
            print(f"  gesture: {payload.direction}", flush=True)
            screen.apply(session.on_gesture(payload.direction, payload.start, payload.end, now))
        elif kind == "tap":
            print("  double tap", flush=True)
            screen.apply(session.on_double_tap(now))
        elif kind == "error":
            raise payload
        else:
            screen.apply(session.on_double_tap(now) if session.active and (session.words or session.current) else [])
            return


def run_keys(session: Session, screen: Screen, gestures: List[str], lines: Iterator[str],
             *, word_pauses: bool = True) -> None:
    """Keyboard stand-in for the strap. Each line is a batch of keys; see KEY_HELP."""
    print(KEY_HELP if word_pauses else "Keys: 1-6 = gesture groups, Enter = decode, q = quit.", flush=True)
    print("Layout: " + "  ".join(f"{i}={label}" for i, label in enumerate(gestures, start=1)), flush=True)
    screen.apply(session.ready())
    clock = 0.0
    for line in lines:
        for key in line.rstrip("\n") + "\n":
            if key == "q":
                return
            if key == "t":
                screen.apply(session.on_double_tap(clock))
            elif key == " " and word_pauses:
                clock += session.word_gap + 1
            elif key == "\n":
                # Give you three seconds to click into the target app before typing.
                if session.words or session.current:
                    time.sleep(3 if screen.typing else 0)
                    screen.apply(session.on_tick(clock + session.sentence_gap + 1))
            elif key.isdigit() and 1 <= int(key) <= len(gestures):
                screen.apply(session.on_gesture(gestures[int(key) - 1], clock, clock + 0.5, clock))
                clock += 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("device", type=uuid.UUID, nargs="?", help="Bluetooth UUID from AirType discovery")
    parser.add_argument("--allow-mac-bond", action="store_true",
                        help="Required for live mode. The Mac may replace the phone's pairing.")
    parser.add_argument("--replay", type=Path, help="Replay a saved motion.csv without Bluetooth")
    parser.add_argument("--realtime", action="store_true", help="Pace a replay at one frame per second")
    parser.add_argument("--keys", action="store_true", help="Use the keyboard instead of the strap")
    parser.add_argument("--six-model", type=Path, default=DEFAULT_MODEL, help="Trained six-gesture model file")
    parser.add_argument("--always-on", action="store_true", help="Listen from the start; no double tap needed")
    parser.add_argument("--word-gap", type=float, default=3.0, help="Seconds between gestures that end a word")
    parser.add_argument("--sentence-gap", type=float, default=6.0, help="Seconds of silence that type the sentence")
    parser.add_argument("--no-overlay", action="store_true", help="Terminal output only")
    parser.add_argument("--no-typing", action="store_true", help="Show text in the overlay without typing it")
    parser.add_argument("--llm", action="store_true",
                        help="Let Claude choose between candidate words. Needs ANTHROPIC_API_KEY and "
                             "sends the candidate words to Anthropic.")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--phrase-demo", action="store_true",
                       help="Decode rehearsed abbreviated phrases")
    modes.add_argument("--prefix-preview", action="store_true",
                       help="Preview dictionary phrases from the first three letters of each word")
    parser.add_argument("--prefix-gemini", action="store_true",
                        help="Let Gemini rank prefix-preview candidates (requires GEMINI_API_KEY)")
    parser.add_argument("--phrase-gemini", action="store_true",
                        help="Use Gemini to rank tied phrase-demo matches (requires GEMINI_API_KEY)")
    parser.add_argument("--phrase-output", choices=("preview", "type", "speak"), default="preview",
                        help="Display, type into the focused app, or speak a decoded demo phrase")
    parser.add_argument("--speech-backend", choices=("macos", "deepgram"), default="macos",
                        help="Speech provider for --phrase-output speak")
    args = parser.parse_args()
    continuous_preview = args.phrase_demo or args.prefix_preview
    if args.prefix_gemini and not args.prefix_preview:
        parser.error("--prefix-gemini requires --prefix-preview.")
    if args.prefix_gemini and not os.environ.get("GEMINI_API_KEY", "").strip():
        parser.error("--prefix-gemini requires GEMINI_API_KEY in the environment.")
    if args.prefix_preview and args.llm:
        parser.error("Use --prefix-gemini for the prefix preview.")
    if args.phrase_output != "preview" and not args.phrase_demo:
        parser.error("--phrase-output requires --phrase-demo.")
    if args.phrase_output == "type" and (args.no_overlay or args.no_typing):
        parser.error("Typing phrases requires the overlay and cannot use --no-typing.")
    if args.speech_backend == "deepgram" and args.phrase_output != "speak":
        parser.error("--speech-backend deepgram requires --phrase-output speak.")
    speech_key = None
    if args.speech_backend == "deepgram":
        speech_key = os.environ.get("DEEPGRAM_API_KEY", "").strip()
        if not speech_key:
            parser.error("--speech-backend deepgram requires DEEPGRAM_API_KEY.")
    if args.phrase_gemini and not args.phrase_demo:
        parser.error("--phrase-gemini requires --phrase-demo.")
    if args.phrase_gemini and not os.environ.get("GEMINI_API_KEY", "").strip():
        parser.error("--phrase-gemini requires GEMINI_API_KEY in the environment.")
    if args.phrase_demo and args.llm:
        parser.error("Use --phrase-gemini for the phrase demo.")
    if sum([args.device is not None, args.replay is not None, args.keys]) != 1:
        parser.error("Choose one: a device UUID, --replay with a motion.csv, or --keys.")

    choose = first_choices
    if args.llm:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            parser.error("--llm needs ANTHROPIC_API_KEY in the environment.")
        choose = llm_chooser(api_key)

    layout = load_layout()
    if args.phrase_demo:
        from phrase_demo import PhraseSession
        session = PhraseSession(layout, sentence_gap=args.sentence_gap, use_gemini=args.phrase_gemini)
    elif args.prefix_preview:
        from prefix_preview import PrefixSession
        session = PrefixSession(layout, load_words(), sentence_gap=args.sentence_gap, use_gemini=args.prefix_gemini)
    else:
        session = Session(Lexicon(load_words(), layout), word_gap=args.word_gap, sentence_gap=args.sentence_gap,
                          always_on=args.always_on or args.keys, choose=choose)

    overlay = None
    if not args.no_overlay:
        if not OVERLAY.is_file():
            parser.error("Run swift build in AirType first, or pass --no-overlay.")
        overlay = subprocess.Popen([str(OVERLAY)], stdin=subprocess.PIPE, text=True)
    speaker = None
    if args.phrase_output == "speak":
        from speech import Speaker
        speaker = Speaker(deepgram_key=speech_key)
    typing = args.phrase_output == "type" or not (args.no_typing or continuous_preview)
    screen = Screen(overlay, typing=typing, phrase_output=args.phrase_output, speaker=speaker)

    try:
        if args.keys:
            run_keys(session, screen, list(layout), iter(sys.stdin.readline, ""),
                     word_pauses=not continuous_preview)
            return 0
        import live
        from functools import partial
        from six_model import gestures as six_gestures, load_model

        detector = partial(six_gestures, estimator=load_model(args.six_model)["estimator"])
        if args.replay is not None:
            run_stream(live.replayed(args.replay, args.realtime), detector, session, screen, use_taps=not continuous_preview)
        else:
            if not args.allow_mac_bond:
                parser.error("Live mode needs --allow-mac-bond.")
            captures = ROOT / "captures"
            captures.mkdir(exist_ok=True)
            folder = Path(tempfile.mkdtemp(prefix="live.", dir=captures))
            print(f"Saving raw motion to {folder}. Ctrl-C to stop.", flush=True)
            with live.strap(args.device) as lines:
                run_stream(live.saved(lines, folder / "motion.csv"), detector, session, screen, use_taps=not continuous_preview)
    except KeyboardInterrupt:
        print("\nStopping.", flush=True)
    except ModuleNotFoundError as error:
        parser.exit(1, f"Missing dependency: {error.name}. The six-gesture model needs scikit-learn and joblib.\n")
    except (OSError, ValueError, KeyError, EOFError) as error:
        parser.exit(1, f"Could not run AirType: {error}\n")
    finally:
        if overlay is not None and overlay.poll() is None:
            overlay.stdin.close()
            overlay.wait(timeout=5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
