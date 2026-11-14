# AirType hackathon handoff

AirType is a Mac prototype for silent text entry using wrist motion from a
WHOOP 5.0. The [main README](README.md) has the setup and run commands.

- **Capture and live gesture recognition work.** Use the bundled six-gesture
  model. A separate mixed recording scored 43/44 reviewed gestures and 14/16
  exact sequences, with three false commands in reviewed background motion.
  The standing live rehearsal emitted all six gesture labels. Repeated tilt-up
  still needs work.
- **The local overlay is ready for a live rehearsal.** It uses pause-based word
  boundaries. The keyboard stand-in and motion replay exercised the text path.
  Start with `--always-on --no-typing` to check the overlay without relying on
  the experimental tap gesture or typing into another app.
- **The continuous decoder is available separately.** It infers spaces and can
  rank candidates with Gemini. Connecting it to the live overlay and measuring
  real phrase accuracy are the next integration tasks.

Before the demo, rehearse one short phrase standing, including the pauses and
finish behavior you will use on stage. Record a backup. Prefer the rehearsal
sequence you can repeat reliably.

New raw recordings, device identifiers, and label files stay local under
`captures/`. The [shared recording catalog](recordings/README.md) describes the
earlier recordings already in the repository.
