"""Speak completed demo phrases, using the shared Deepgram client when requested."""

import subprocess
import sys
import threading

from speak import speak as deepgram_speak


class Speaker:
    def __init__(self, deepgram_key=None):
        self.deepgram_key = deepgram_key
        self.worker = None

    def speak(self, text):
        if self.worker is not None and self.worker.is_alive():
            print("AirType is still speaking. Repeat this phrase after it finishes.", file=sys.stderr, flush=True)
            return
        self.worker = threading.Thread(target=self._speak, args=(text,))
        self.worker.start()

    def _speak(self, text):
        if self.deepgram_key:
            if deepgram_speak(text, self.deepgram_key):
                return
            print("Using the Mac voice instead.", file=sys.stderr, flush=True)
        try:
            subprocess.run(["/usr/bin/say", text], check=True, timeout=20)
        except (OSError, subprocess.SubprocessError) as error:
            print(f"Could not play the phrase: {error}", file=sys.stderr, flush=True)
