# Check Gemini Decisions API access

Run this once before integrating wrist-gesture classification. It sends one
synthetic customer-message example to Google's Gemini Decisions endpoint.
It does not read captures, connect to Bluetooth, or classify real gestures.
It uses Python 3's standard library; no SDK installation is needed.

From the AirType repository root, in macOS Terminal (default zsh):

```zsh
read -s "GEMINI_API_KEY?Paste your Gemini API key, then press Enter: "
export GEMINI_API_KEY
echo
python3 -B ml/test_gemini_decision.py
```

The hidden prompt keeps the key out of the command you type. Use an existing
Gemini API key from your own AI Studio project. Access to
`gemini-decision-1` still depends on the project's permissions and availability.
The variable lasts for this terminal session; the script explicitly uses
`GEMINI_API_KEY`.

Expected output begins with `API access works: gemini-decision-1`, followed by
the chosen label, confidence, probabilities and measured request duration.
The expected example label is `damaged_item`; a different label is reported but
does not mean authentication failed. A successful access check does not establish
motion-classification quality.

The request has a 20-second timeout and no automatic retries. Each run makes
one request, consuming project quota and potentially incurring input charges.
This timeout is for setup, not a proposed live-input latency budget.

If it fails, the script prints a short diagnostic and exits nonzero:

- Missing key: set it using the prompt above in the same terminal.
- HTTP 400/401: check key validity; 400 can also indicate an invalid request.
- HTTP 403: check project permissions, API restrictions and model access.
- HTTP 404: verify model availability and API version/endpoint.
- HTTP 429: check quota, rate limits and billing tier.
- Connection failure: check internet access and retry.

It deliberately avoids printing raw API errors or request headers. Share only
sanitized diagnostics when asking for help. Never commit your key, include it in
browser JavaScript, or paste it into chat. A website should call a backend that
holds the key.

Remove the key from this terminal when finished:

```zsh
unset GEMINI_API_KEY
```

Next: send one reviewed, segmented movement's numeric features and calibration
examples, then evaluate on separate recordings. That gesture experiment is not
implemented by this access check.

References:
- [Decisions API](https://aistudio.google.com/docs/decisions-api)
- [API keys](https://aistudio.google.com/docs/api-key)
