"""Check Gemini Decisions API access using synthetic text, without WHOOP data."""

import json
import os
import sys
import time
import urllib.error
import urllib.request

ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/decisions"
MODEL = "gemini-decision-1"


def main():
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        print("Set GEMINI_API_KEY in this terminal before running the check.", file=sys.stderr)
        return 1

    payload = {
        "model": MODEL,
        "input": "The customer says their mug arrived broken.",
        "questions": {
            "category": {
                "type": "choice",
                "instructions": "Classify this customer message.",
                "criteria": {
                    "damaged_item": "An item arrived broken or damaged.",
                    "billing": "A payment or invoice problem.",
                    "other": "Anything else.",
                },
            }
        },
    }
    request = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": key},
        method="POST",
    )
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            result = json.load(response)
    except urllib.error.HTTPError as error:
        # Do not print raw exceptions, headers or response bodies: they may contain secrets.
        hints = {
            400: "Check key validity and the current Decisions API request format.",
            401: "Check the API key.",
            403: "Check project permissions, key restrictions and model access.",
            404: "Check model availability and the API endpoint/version.",
            429: "Check project quota, rate limits and billing tier.",
        }
        print(
            f"API check failed (HTTP {error.code}). "
            + hints.get(error.code, "Check service status; try again later."),
            file=sys.stderr,
        )
        return 1
    except (urllib.error.URLError, TimeoutError, OSError):
        print("Connection failed or timed out. Check internet access and retry.", file=sys.stderr)
        return 1
    except (ValueError, UnicodeError):
        print("API returned an unreadable response.", file=sys.stderr)
        return 1

    try:
        answer = result["answers"]["category"]
        choice = answer["choice"]
        confidence = answer["confidence"]
        probabilities = answer["probabilities"]
        if answer["type"] != "choice" or choice not in payload["questions"]["category"]["criteria"]:
            raise ValueError("Unexpected decision")
        if not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
            raise ValueError("Invalid confidence")
        if not isinstance(probabilities, dict):
            raise ValueError("Invalid probabilities")
    except (KeyError, TypeError, ValueError):
        print("API response did not contain the expected choice answer.", file=sys.stderr)
        return 1

    print(f"API access works: {MODEL}")
    print(f"Choice: {choice}")
    print(f"Confidence: {confidence}")
    print("Probabilities:", json.dumps(probabilities, sort_keys=True))
    print(f"Round-trip time: {time.monotonic() - started:.2f} seconds")
    if choice != "damaged_item":
        print("Note: the expected synthetic-example label was damaged_item.")
    print("This checks API access only, not wrist-gesture accuracy.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
