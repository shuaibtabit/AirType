"""Speak completed demo phrases on the Mac's selected audio output."""

import json
import subprocess
import sys
import tempfile
import threading
import urllib.request
from pathlib import Path

SPEAK_URL = "https://api.deepgram.com/v1/speak?model=aura-2-thalia-en&encoding=linear16&container=wav"
MAX_AUDIO_BYTES = 4 * 1024 * 1024


def deepgram_speak(text, key):
    request = urllib.request.Request(
        SPEAK_URL,
        data=json.dumps({"text": text}).encode("utf-8"),
        headers={"Authorization": "Token " + key, "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=8) as response:
        audio = response.read(MAX_AUDIO_BYTES + 1)
    if len(audio) > MAX_AUDIO_BYTES or audio[:4] != b"RIFF" or audio[8:12] != b"WAVE":
        raise ValueError("Deepgram returned invalid WAV audio.")
    with tempfile.TemporaryDirectory(prefix="airtype-speech.") as folder:
        path = Path(folder) / "phrase.wav"
        path.write_bytes(audio)
        subprocess.run(["/usr/bin/afplay", str(path)], check=True, timeout=20)


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
            try:
                deepgram_speak(text, self.deepgram_key)
                return
            except (OSError, ValueError, subprocess.SubprocessError):
                print("Deepgram speech failed. Using the Mac voice.", file=sys.stderr, flush=True)
        try:
            subprocess.run(["/usr/bin/say", text], check=True, timeout=20)
        except (OSError, subprocess.SubprocessError) as error:
            print(f"Could not play the phrase: {error}", file=sys.stderr, flush=True)
