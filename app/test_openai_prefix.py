import io
import json
import unittest
from unittest.mock import patch

from openai_prefix import ENDPOINT, suggest_sentence


class OpenAIPrefixTests(unittest.TestCase):
    def test_responses_api_request_contains_the_full_gesture_sequence(self):
        result = {
            "status": "completed",
            "output": [{"type": "message", "content": [
                {"type": "output_text", "text": '{"status":"ok","sentence":"Send email."}'},
            ]}],
        }
        with patch("openai_prefix.urllib.request.urlopen",
                   return_value=io.BytesIO(json.dumps(result).encode())) as urlopen:
            sentence = suggest_sentence(
                "test-token", list("524241"), {"5": {"gesture": "swing left", "letters": "qrst"}},
                ["send email", "show email"], ["send", "email"], "Demo vocabulary",
            )

        self.assertEqual(sentence, "Send email.")
        request, = urlopen.call_args.args
        self.assertEqual(request.full_url, ENDPOINT)
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.get_header("Authorization"), "Bearer test-token")
        payload = json.loads(request.data)
        self.assertFalse(payload["store"])
        self.assertTrue(payload["text"]["format"]["strict"])
        self.assertEqual(json.loads(payload["input"]), {
            "gesture_ids": list("524241"),
            "letter_groups": {"5": "qrst"},
            "dictionary_candidates": ["send email", "show email"],
            "likely_words": ["send", "email"],
            "topic_hint": "Demo vocabulary",
        })
