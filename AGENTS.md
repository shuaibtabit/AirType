# Working on AirType

Read README.md, PLAN.md and research/whoop-ble.md before changing the sensor path.

- Keep AirType local unless the user explicitly authorizes an external GitHub repository or push.
- Ask before any operation that can re-pair the strap or disturb its official phone bond. A confirmed Hello can trigger macOS bonding. Discovery is connection-free. Use the explicit capture opt-in only with the user's approval. Avoid firmware changes during initial validation.
- Treat source review, synthetic/offline decoding, macOS compilation, and real BLE capture as distinct evidence. Record the wearable model, firmware, macOS version and actual observations before marking a hardware milestone complete.
- Keep third-party checkouts separate from the AirType Git repository. Use NOOP as a protocol reference under its source-available terms. Keep captures and device identifiers out of Git.
- Preserve raw values, counts, frame times and host receive times. Document any interpolation or inferred sample rate. Keep gap handling and replay semantics explicit.
- Run `swift test` after protocol changes. Use the hardware checklist before starting gesture collection. Keep the first demo local and use an in-app text buffer.
