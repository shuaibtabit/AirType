import AppKit
import Security

final class Launcher: NSObject, NSApplicationDelegate {
    private let window = NSWindow(
        contentRect: NSRect(x: 0, y: 0, width: 570, height: 325),
        styleMask: [.titled, .closable], backing: .buffered, defer: false
    )
    private let uuidField = NSTextField(string: "")
    private let outputMenu = NSPopUpButton()
    private let voiceMenu = NSPopUpButton()
    private let openAIKey = NSSecureTextField(string: "")
    private let deepgramKey = NSSecureTextField(string: "")
    private let status = NSTextField(wrappingLabelWithString: "")
    private var process: Process?
    private var input: FileHandle?
    private var overlay: Overlay?
    private var diagnostics = ""
    private var quitting = false

    override init() {
        super.init()
        window.title = "AirType"
        window.isReleasedWhenClosed = false
        let menuBar = NSMenu()
        let airTypeItem = NSMenuItem()
        let appMenu = NSMenu(title: "AirType")
        appMenu.addItem(withTitle: "Quit AirType", action: #selector(NSApplication.terminate(_:)),
                        keyEquivalent: "q")
        airTypeItem.submenu = appMenu
        menuBar.addItem(airTypeItem)
        NSApp.mainMenu = menuBar
        window.center()

        let defaults = UserDefaults.standard
        uuidField.stringValue = defaults.string(forKey: "WHOOPUUID")
            ?? (Bundle.main.object(forInfoDictionaryKey: "AirTypeDeviceUUID") as? String ?? "")
        uuidField.placeholderString = "UUID from WHOOP discovery"
        outputMenu.addItems(withTitles: ["Type and speak", "Type only", "Speak only", "Preview"])
        voiceMenu.addItems(withTitles: ["Deepgram", "Mac voice"])
        outputMenu.selectItem(at: defaults.integer(forKey: "Output"))
        voiceMenu.selectItem(at: defaults.integer(forKey: "Voice"))

        let connect = NSButton(title: "Connect", target: self, action: #selector(connect))
        connect.bezelStyle = .rounded
        connect.keyEquivalent = "\r"
        let save = NSButton(title: "Save keys", target: self, action: #selector(saveKeys))
        save.bezelStyle = .rounded
        let buttons = NSStackView(views: [connect, save])
        buttons.spacing = 8

        let grid = NSGridView(views: [
            [NSTextField(labelWithString: "WHOOP UUID"), uuidField],
            [NSTextField(labelWithString: "Output"), outputMenu],
            [NSTextField(labelWithString: "Voice"), voiceMenu],
            [NSTextField(labelWithString: "OpenAI key"), openAIKey],
            [NSTextField(labelWithString: "Deepgram key"), deepgramKey],
        ])
        grid.column(at: 0).xPlacement = .trailing
        grid.column(at: 1).xPlacement = .fill
        grid.column(at: 1).width = 345
        grid.columnSpacing = 14
        grid.rowSpacing = 9
        status.textColor = .secondaryLabelColor
        status.maximumNumberOfLines = 3
        status.stringValue = "Leave saved key fields blank to reuse them. Select AirPods in Sound for playback."

        let content = NSStackView(views: [grid, buttons, status])
        content.orientation = .vertical
        content.alignment = .leading
        content.spacing = 14
        content.translatesAutoresizingMaskIntoConstraints = false
        let host = window.contentView!
        host.addSubview(content)
        NSLayoutConstraint.activate([
            content.leadingAnchor.constraint(equalTo: host.leadingAnchor, constant: 22),
            content.trailingAnchor.constraint(equalTo: host.trailingAnchor, constant: -22),
            content.topAnchor.constraint(equalTo: host.topAnchor, constant: 22),
            content.bottomAnchor.constraint(lessThanOrEqualTo: host.bottomAnchor, constant: -16),
            status.widthAnchor.constraint(equalTo: content.widthAnchor),
        ])
    }

    func present() {
        guard process == nil else { return }
        refreshKeyFields()
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    func applicationShouldHandleReopen(_ application: NSApplication, hasVisibleWindows: Bool) -> Bool {
        present()
        return true
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        process == nil
    }

    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        guard let process, process.isRunning else { return .terminateNow }
        quitting = true
        send("stop")
        return .terminateLater
    }

    private func refreshKeyFields() {
        openAIKey.placeholderString = APIKey.openAI.isSaved ? "Saved in Keychain" : "Paste once for new sentences"
        deepgramKey.placeholderString = APIKey.deepgram.isSaved ? "Saved in Keychain" : "Paste once for Deepgram"
    }

    private func saveEnteredKeys() throws -> Bool {
        window.endEditing(for: nil)
        defer { refreshKeyFields() }
        var saved = false
        for (provider, field) in [(APIKey.openAI, openAIKey), (APIKey.deepgram, deepgramKey)] {
            let key = field.stringValue.trimmingCharacters(in: .whitespacesAndNewlines)
            if key.isEmpty { continue }
            try provider.save(key)
            field.stringValue = ""
            saved = true
        }
        return saved
    }

    @objc private func saveKeys() {
        do {
            status.stringValue = try saveEnteredKeys()
                ? "Saved to Keychain. AirType will reuse these keys when it reopens."
                : "Leave saved fields blank. Paste a key here if you need to add or replace it."
        } catch {
            status.stringValue = error.localizedDescription
        }
    }

    @objc private func connect() {
        guard process == nil else { return }
        window.endEditing(for: nil)
        let rawUUID = uuidField.stringValue.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let uuid = UUID(uuidString: rawUUID) else {
            status.stringValue = "Enter the WHOOP UUID shown by AirType discovery."
            return
        }
        let root = Bundle.main.bundleURL.deletingLastPathComponent()
        let runner = root.appendingPathComponent("app/airtype.py")
        let capture = root.appendingPathComponent(".build/debug/airtype-capture")
        let python = Bundle.main.object(forInfoDictionaryKey: "AirTypePython") as? String ?? "/usr/bin/python3"
        guard FileManager.default.fileExists(atPath: runner.path),
              FileManager.default.isExecutableFile(atPath: capture.path),
              FileManager.default.isExecutableFile(atPath: python) else {
            status.stringValue = "Keep AirType.app in the AirType folder with its built capture tool and Python."
            return
        }

        let outputs = ["both", "type", "speak", "preview"]
        let output = outputs[outputMenu.indexOfSelectedItem]
        let useDeepgram = (output == "both" || output == "speak") && voiceMenu.indexOfSelectedItem == 0
        var environment = ProcessInfo.processInfo.environment
        var arguments = ["-B", runner.path, uuid.uuidString, "--allow-mac-bond",
                         "--panel-stdio", "--auto-decode", "--output", output]

        do {
            _ = try saveEnteredKeys()
            environment["OPENAI_API_KEY"] = try APIKey.openAI.load()
            if useDeepgram {
                guard let key = try APIKey.deepgram.load() else {
                    throw ConfigurationError(message: "Paste your Deepgram key once, then click Save keys or Connect.")
                }
                arguments += ["--speech-backend", "deepgram"]
                environment["DEEPGRAM_API_KEY"] = key
            }
        } catch {
            status.stringValue = error.localizedDescription
            return
        }

        let defaults = UserDefaults.standard
        defaults.set(uuid.uuidString, forKey: "WHOOPUUID")
        defaults.set(outputMenu.indexOfSelectedItem, forKey: "Output")
        defaults.set(voiceMenu.indexOfSelectedItem, forKey: "Voice")
        if output == "both" || output == "type" { requestTypingPermission() }
        launch(python: python, root: root, arguments: arguments, environment: environment)
    }

    private func launch(python: String, root: URL, arguments: [String], environment: [String: String]) {
        let child = Process()
        let commands = Pipe()
        let updates = Pipe()
        let errors = Pipe()
        child.executableURL = URL(fileURLWithPath: python)
        child.currentDirectoryURL = root
        child.arguments = arguments
        child.environment = environment
        child.standardInput = commands
        child.standardOutput = updates
        child.standardError = errors
        diagnostics = ""

        readLines(updates.fileHandleForReading) { [weak self] line in
            let prefix = "@airtype "
            guard line.hasPrefix(prefix), let overlay = self?.overlay,
                  let message = try? JSONDecoder().decode([String: String].self,
                      from: Data(line.dropFirst(prefix.count).utf8)) else { return }
            apply(message, to: overlay)
        }
        readLines(errors.fileHandleForReading) { [weak self] line in
            guard let self else { return }
            if line.contains("error:") || line.hasPrefix("Could not") || line.contains("failed")
                || line.contains("did not appear") || line.contains("denied") {
                self.diagnostics = line
            }
        }

        child.terminationHandler = { [weak self] ended in
            DispatchQueue.main.async { self?.ended(status: ended.terminationStatus) }
        }
        do {
            try child.run()
        } catch {
            status.stringValue = "Could not start AirType: \(error.localizedDescription)"
            return
        }

        process = child
        input = commands.fileHandleForWriting
        overlay = Overlay(controls: true) { [weak self] action in self?.send(action) }
        overlay?.show(status: "Connecting", detail: "Waiting for WHOOP motion")
        window.orderOut(nil)
    }

    private func send(_ action: String) {
        do {
            try input?.write(contentsOf: Data((action + "\n").utf8))
        } catch {
            overlay?.show(status: "Connection closed", detail: "Returning to AirType setup")
        }
    }

    private func ended(status exitCode: Int32) {
        try? input?.close()
        input = nil
        overlay?.close()
        overlay = nil
        process = nil
        if quitting {
            NSApp.reply(toApplicationShouldTerminate: true)
            return
        }
        status.stringValue = diagnostics.isEmpty
            ? (exitCode == 0 ? "Disconnected." : "Capture ended. Check the WHOOP connection and try again.")
            : diagnostics
        present()
    }
}

private func readLines(_ file: FileHandle, onLine: @escaping (String) -> Void) {
    Thread.detachNewThread {
        var buffer = Data()
        while true {
            // Read each small status update as soon as it arrives on the open pipe.
            let chunk = file.availableData
            if chunk.isEmpty { return }
            buffer.append(chunk)
            while let newline = buffer.firstIndex(of: 10) {
                let line = String(decoding: buffer[..<newline], as: UTF8.self)
                buffer.removeSubrange(...newline)
                DispatchQueue.main.async { onLine(line) }
            }
        }
    }
}

private struct APIKey {
    static let openAI = APIKey(service: "airtype-openai", variable: "OPENAI_API_KEY", label: "OpenAI")
    static let deepgram = APIKey(service: "deepgram", variable: "DEEPGRAM_API_KEY", label: "Deepgram")

    let service: String
    let variable: String
    let label: String

    private var query: [String: Any] {
        [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: NSUserName(),
        ]
    }

    var isSaved: Bool {
        var lookup = query
        lookup[kSecReturnAttributes as String] = true
        var attributes: CFTypeRef?
        return SecItemCopyMatching(lookup as CFDictionary, &attributes) == errSecSuccess
    }

    func save(_ value: String) throws {
        let data = Data(value.utf8)
        var result = SecItemUpdate(query as CFDictionary, [kSecValueData as String: data] as CFDictionary)
        if result == errSecItemNotFound {
            var item = query
            item[kSecValueData as String] = data
            result = SecItemAdd(item as CFDictionary, nil)
        }
        guard result == errSecSuccess else {
            throw ConfigurationError(message: "Could not save the \(label) key to Keychain (\(result)).")
        }
    }

    func load() throws -> String? {
        if let value = ProcessInfo.processInfo.environment[variable], !value.isEmpty { return value }
        var lookup = query
        lookup[kSecReturnData as String] = true
        var item: CFTypeRef?
        let result = SecItemCopyMatching(lookup as CFDictionary, &item)
        if result == errSecItemNotFound { return nil }
        guard result == errSecSuccess, let data = item as? Data,
              let value = String(data: data, encoding: .utf8), !value.isEmpty else {
            throw ConfigurationError(message: "Could not read the saved \(label) key. Allow AirType in the Keychain prompt and retry.")
        }
        return value
    }
}

private struct ConfigurationError: LocalizedError {
    let message: String
    var errorDescription: String? { message }
}
