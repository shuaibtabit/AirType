import AppKit
import ApplicationServices

// A floating panel that never takes keyboard focus, plus keystroke injection into
// whichever app is focused. Driven by JSON lines on stdin:
//   {"status": "Listening", "detail": "…"}   update the panel
//   {"type": "go home "}                     type text into the focused app

func report(_ message: String) {
    FileHandle.standardError.write(Data((message + "\n").utf8))
}

private final class AirTypePanel: NSPanel {
    override var canBecomeKey: Bool { false }
}

final class Overlay: NSObject {
    private let panel: NSPanel
    private let status = NSTextField(labelWithString: "AirType")
    private let detail = NSTextField(wrappingLabelWithString: "Starting…")
    private let inputButton = NSButton(title: "Start", target: nil, action: nil)
    private let clearButton = NSButton(title: "Clear", target: nil, action: nil)
    private var command = "disabled"
    private let onAction: ((String) -> Void)?
    private let stopButton = NSButton(title: "Disconnect", target: nil, action: nil)

    init(controls: Bool, onAction: ((String) -> Void)? = nil) {
        self.onAction = onAction
        let size = NSSize(width: 480, height: controls ? 170 : 120)
        panel = AirTypePanel(contentRect: NSRect(origin: .zero, size: size),
                        styleMask: [.nonactivatingPanel, .hudWindow, .utilityWindow, .titled],
                        backing: .buffered, defer: false)
        super.init()
        panel.title = "AirType"
        panel.level = .statusBar
        panel.isFloatingPanel = true
        panel.hidesOnDeactivate = false
        panel.becomesKeyOnlyIfNeeded = true
        panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]

        status.font = .systemFont(ofSize: 24, weight: .bold)
        detail.font = .monospacedSystemFont(ofSize: 17, weight: .regular)
        detail.textColor = .labelColor
        detail.maximumNumberOfLines = 3
        let stack = NSStackView(views: [status, detail])
        if controls {
            inputButton.target = self
            inputButton.action = #selector(toggleInput)
            clearButton.target = self
            clearButton.action = #selector(clearInput)
            inputButton.bezelStyle = .rounded
            clearButton.bezelStyle = .rounded
            let buttons = NSStackView(views: [inputButton, clearButton])
            buttons.spacing = 8
            if onAction != nil {
                stopButton.target = self
                stopButton.action = #selector(disconnect)
                stopButton.bezelStyle = .rounded
                buttons.addArrangedSubview(stopButton)
            }
            stack.addArrangedSubview(buttons)
            showControl("disabled")
        }
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

    func showControl(_ action: String) {
        command = action
        if action == "start" { inputButton.title = "Start" }
        if action == "finish" { inputButton.title = "Finish" }
        inputButton.isEnabled = action == "start" || action == "finish"
        clearButton.isEnabled = action == "finish"
    }

    @objc private func toggleInput() {
        guard command == "start" || command == "finish" else { return }
        send(command)
    }

    @objc private func clearInput() {
        guard command == "finish" else { return }
        send("clear")
    }

    @objc private func disconnect() {
        stopButton.isEnabled = false
        show(status: "Disconnecting", detail: "Stopping the WHOOP stream")
        send("stop")
    }

    func close() {
        panel.orderOut(nil)
    }

    private func send(_ action: String) {
        showControl("disabled")
        if let onAction {
            onAction(action)
            return
        }
        FileHandle.standardOutput.write(Data((action + "\n").utf8))
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

func requestTypingPermission() {
    guard !AXIsProcessTrusted() else { return }
    let prompt = [kAXTrustedCheckOptionPrompt.takeUnretainedValue() as String: true] as CFDictionary
    _ = AXIsProcessTrustedWithOptions(prompt)
    report("Typing needs macOS Accessibility permission for AirType or the terminal launching it.")
}

func apply(_ message: [String: String], to overlay: Overlay) {
    if let status = message["status"] {
        overlay.show(status: status, detail: message["detail"] ?? "")
    }
    if let action = message["control"] { overlay.showControl(action) }
    if let text = message["type"] { type(text) }
}

let app = NSApplication.shared
if Bundle.main.bundleURL.pathExtension == "app" {
    let launcher = Launcher()
    app.delegate = launcher
    app.setActivationPolicy(.regular)
    launcher.present()
    withExtendedLifetime(launcher) { app.run() }
} else {
    app.setActivationPolicy(.accessory)
    let overlay = Overlay(controls: CommandLine.arguments.contains("--controls"))
    if CommandLine.arguments.contains("--typing") { requestTypingPermission() }
    Thread.detachNewThread {
        while let line = readLine() {
            guard let message = try? JSONDecoder().decode([String: String].self, from: Data(line.utf8)) else {
                report("Ignored a malformed overlay message.")
                continue
            }
            DispatchQueue.main.async { apply(message, to: overlay) }
        }
        DispatchQueue.main.async { exit(0) }
    }
    app.run()
}
