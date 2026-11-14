import AppKit
import ApplicationServices

// A floating panel that never takes keyboard focus, plus keystroke injection into
// whichever app is focused. Driven by JSON lines on stdin:
//   {"status": "Listening", "detail": "…"}   update the panel
//   {"type": "go home "}                     type text into the focused app

func report(_ message: String) {
    FileHandle.standardError.write(Data((message + "\n").utf8))
}

final class Overlay {
    private let panel: NSPanel
    private let status = NSTextField(labelWithString: "AirType")
    private let detail = NSTextField(wrappingLabelWithString: "Starting…")

    init() {
        let size = NSSize(width: 560, height: 120)
        panel = NSPanel(contentRect: NSRect(origin: .zero, size: size),
                        styleMask: [.nonactivatingPanel, .hudWindow, .utilityWindow, .titled],
                        backing: .buffered, defer: false)
        panel.title = "AirType"
        panel.level = .statusBar
        panel.isFloatingPanel = true
        panel.hidesOnDeactivate = false
        panel.becomesKeyOnlyIfNeeded = true
        panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]

        status.font = .systemFont(ofSize: 24, weight: .bold)
        detail.font = .monospacedSystemFont(ofSize: 17, weight: .regular)
        detail.textColor = .white
        detail.maximumNumberOfLines = 3
        let stack = NSStackView(views: [status, detail])
        stack.orientation = .vertical
        stack.alignment = .leading
        stack.spacing = 8
        stack.edgeInsets = NSEdgeInsets(top: 12, left: 16, bottom: 12, right: 16)
        stack.translatesAutoresizingMaskIntoConstraints = false
        let content = panel.contentView!
        content.addSubview(stack)
        NSLayoutConstraint.activate([
            stack.leadingAnchor.constraint(equalTo: content.leadingAnchor),
            stack.trailingAnchor.constraint(equalTo: content.trailingAnchor),
            stack.topAnchor.constraint(equalTo: content.topAnchor),
            stack.bottomAnchor.constraint(lessThanOrEqualTo: content.bottomAnchor),
        ])

        if let screen = NSScreen.main?.visibleFrame {
            panel.setFrameOrigin(NSPoint(x: screen.midX - size.width / 2, y: screen.maxY - size.height - 24))
        }
        show(status: "AirType", detail: "Starting…")
        panel.orderFrontRegardless()
    }

    func show(status text: String, detail body: String) {
        status.stringValue = text
        detail.stringValue = body
        switch text {
        case "Listening": status.textColor = .systemGreen
        case "Typed": status.textColor = .systemBlue
        default: status.textColor = .secondaryLabelColor
        }
    }
}

func type(_ text: String) {
    guard AXIsProcessTrusted() else {
        report("Cannot type: allow this terminal under System Settings → Privacy & Security → Accessibility, then restart AirType.")
        return
    }
    let source = CGEventSource(stateID: .combinedSessionState)
    for character in text {
        let units = Array(String(character).utf16)
        for keyDown in [true, false] {
            guard let event = CGEvent(keyboardEventSource: source, virtualKey: 0, keyDown: keyDown) else {
                report("Could not create a keyboard event.")
                return
            }
            event.keyboardSetUnicodeString(stringLength: units.count, unicodeString: units)
            event.post(tap: .cghidEventTap)
        }
        usleep(6000)
    }
}

let app = NSApplication.shared
app.setActivationPolicy(.accessory)
let overlay = Overlay()
if !AXIsProcessTrusted() {
    // Shows the system prompt once. Granting it is the user's decision.
    let prompt = [kAXTrustedCheckOptionPrompt.takeUnretainedValue() as String: true] as CFDictionary
    _ = AXIsProcessTrustedWithOptions(prompt)
    report("Typing needs Accessibility permission for this terminal. The panel still works without it.")
}

Thread.detachNewThread {
    while let line = readLine() {
        guard let data = line.data(using: .utf8),
              let message = try? JSONSerialization.jsonObject(with: data) as? [String: String] else {
            report("Ignored a malformed overlay message.")
            continue
        }
        DispatchQueue.main.async {
            if let status = message["status"] {
                overlay.show(status: status, detail: message["detail"] ?? "")
            }
            if let text = message["type"] { type(text) }
        }
    }
    DispatchQueue.main.async { exit(0) }
}
app.run()
