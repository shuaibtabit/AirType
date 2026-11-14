# Fitted AirType models

These files contain fitted logistic regression estimators and normalization
parameters. They were fitted using local WHOOP recordings with the strap
on top of the left wrist. Training recordings stay under the ignored
`captures/` directory. Install the tested versions in
[ml/requirements.txt](../ml/requirements.txt) before loading the models.

- `six-model.joblib` recognizes six gestures plus background. It was fitted from
  161 command examples and 124 background examples across five sessions.
  The live overlay uses this file by default.
- `roll-model.joblib` recognizes the two rolls and repositioning. Use it with
  `ml/live.py --model models/roll-model.joblib`.

Use models from a trusted source because joblib deserializes Python objects.
