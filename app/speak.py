"""Say text aloud with Deepgram Aura. Audio plays on the Mac's current output, so AirPods
work once they are connected and selected in System Settings > Sound.

  python3 -B app/speak.py "hello world"

Needs a Deepgram key: the DEEPGRAM_API_KEY environment variable, or a macOS Keychain item
named "deepgram" (store it once with: python3 -B app/speak.py --save-key).
This sends the text to Deepgram.
"""

import json
import os
import ssl
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
import urllib.error
import urllib.request

MODEL = "aura-2-thalia-en"
TIMEOUT_SECONDS = 10
SYSTEM_CERTS = Path("/etc/ssl/cert.pem")  # python.org Pythons on macOS ship without certificates


def find_key() -> str:
    """Environment variable first, then the macOS Keychain. Empty string if neither has one."""
    key = os.environ.get("DEEPGRAM_API_KEY", "").strip()
    if key:
        return key
    try:
        result = subprocess.run(["security", "find-generic-password", "-a", os.environ.get("USER", ""),
                                 "-s", "deepgram", "-w"], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def speak(text: str, api_key: str = "") -> bool:
    """Blocking. True if the audio played. Failures print a short reason and return False;
    the key and the text are never printed."""
    key = api_key or find_key()
    if not key or not text.strip():
        print("Speech skipped: no Deepgram key (see app/speak.py) or empty text.", flush=True)
        return False
    context = ssl.create_default_context(cafile=str(SYSTEM_CERTS)) if SYSTEM_CERTS.is_file() else None
    request = urllib.request.Request(
        f"https://api.deepgram.com/v1/speak?model={MODEL}",
        data=json.dumps({"text": text.strip()}).encode(), method="POST",
        headers={"Authorization": f"Token {key}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS, context=context) as response:
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


def save_key() -> int:
    """Store the key in the Keychain once. `security` prompts for it with hidden input on this
    terminal, so the key never appears in the command line or shell history. -U replaces an old one."""
    return subprocess.run(["security", "add-generic-password", "-a", os.environ.get("USER", ""),
                           "-s", "deepgram", "-U", "-w"]).returncode


if __name__ == "__main__":
    if sys.argv[1:] == ["--save-key"]:
        sys.exit(save_key())
    sys.exit(0 if speak(" ".join(sys.argv[1:])) else 1)
