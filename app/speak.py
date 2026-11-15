"""Say text aloud with Deepgram Aura. Audio plays on the Mac's current output, so AirPods
work once they are connected and selected in System Settings > Sound.

  python3 -B app/speak.py "hello world"

Needs DEEPGRAM_API_KEY in the environment. This sends the text to Deepgram.
"""

import json
import os
import subprocess
import sys
import tempfile
import threading
import urllib.error
import urllib.request

MODEL = "aura-2-thalia-en"
TIMEOUT_SECONDS = 10


def speak(text: str, api_key: str = "") -> bool:
    """Blocking. True if the audio played. Failures print a short reason and return False;
    the key and the text are never printed."""
    key = api_key or os.environ.get("DEEPGRAM_API_KEY", "").strip()
    if not key or not text.strip():
        print("Speech skipped: need DEEPGRAM_API_KEY and non-empty text.", flush=True)
        return False
    request = urllib.request.Request(
        f"https://api.deepgram.com/v1/speak?model={MODEL}",
        data=json.dumps({"text": text.strip()}).encode(), method="POST",
        headers={"Authorization": f"Token {key}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            audio = response.read()
        with tempfile.NamedTemporaryFile(suffix=".mp3") as file:
            file.write(audio)
            file.flush()
            subprocess.run(["afplay", file.name], check=True)
        return True
    except (urllib.error.URLError, TimeoutError, OSError, subprocess.CalledProcessError) as error:
        code = getattr(error, "code", None)
        print(f"Speech unavailable ({'HTTP ' + str(code) if code else type(error).__name__}).", flush=True)
        return False


def speak_in_background(text: str, api_key: str = "") -> None:
    """Non-blocking, so gesture input stays responsive. Not a daemon thread: the program
    waits for the last sentence to finish before it exits."""
    threading.Thread(target=speak, args=(text, api_key)).start()


if __name__ == "__main__":
    sys.exit(0 if speak(" ".join(sys.argv[1:])) else 1)
