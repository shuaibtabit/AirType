# Character entry

With six reliably distinguishable gestures, ordered pairs allow 36 codes. A versioned codebook can cover 26 letters, space, backspace and a small set of controls. Repeated gestures within a pair require a distinct onset and release for each event. Start with a few characters during the three-gesture pilot.

Keep one pending gesture, show it in the demo, and clear it after a measured inter-gesture timeout or an explicit cancel. Require a confidence threshold for committing each event. Apply the chosen code to an app-local text buffer and log rejected pairs, correction events and latency for evaluation.

Contextual reconstruction is optional. Show the literal decoded text and offer ranked local suggestions, including vowel restoration only in a clearly selected abbreviation mode. Preserve the literal input when the user declines a suggestion.
