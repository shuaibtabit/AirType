import CoreBluetooth
import Foundation

func report(_ message: String) {
    FileHandle.standardError.write(Data((message + "\n").utf8))
}

final class Capture: NSObject, CBCentralManagerDelegate, CBPeripheralDelegate {
    enum Mode {
        case discover
        case capture(UUID, seconds: Int)
    }

    private enum Phase: String {
        case bluetooth, scanning, connecting, services, characteristics, hello, subscribing
        case startRaw, enableIMU, streaming, stopRaw, disableIMU, disconnecting
    }

    private static func uuid(_ prefix: String) -> CBUUID {
        CBUUID(string: "fd4b\(prefix)-cce1-4033-93ce-002d5875f58a")
    }

    private let serviceID = uuid("0001")
    private let writeID = uuid("0002")
    private let responseID = uuid("0003")
    private let dataID = uuid("0005")
    private let mode: Mode
    private var central: CBCentralManager!
    private var device: CBPeripheral?
    private var command: CBCharacteristic?
    private var notifications: [CBCharacteristic] = []
    private var awaitingNotifications: Set<CBUUID> = []
    private var phase = Phase.bluetooth
    private var deadline: DispatchWorkItem?
    private var silence: DispatchWorkItem?
    private var found: Set<UUID> = []
    private var readers: [CBUUID: FrameReader] = [:]
    private var sequence: UInt8 = 0
    private var commandNames: [UInt8: UInt8] = [:]
    private var shouldStop = false
    private var exitStatus: Int32 = 0
    private var rows = 0
    private var frames = 0
    private var priorMotion: MotionFrame?

    init(mode: Mode) {
        self.mode = mode
        super.init()
    }

    func start() {
        advance(to: .bluetooth, timeout: 20)
        central = CBCentralManager(delegate: self, queue: .main,
                                   options: [CBCentralManagerOptionShowPowerAlertKey: false])
    }

    func interrupt() {
        if case .discover = mode {
            finish()
        }
        report("Stop requested.")
        shouldStop = true
        if phase == .streaming {
            stopRaw()
        } else if phase != .startRaw && phase != .enableIMU && phase != .stopRaw &&
                    phase != .disableIMU && phase != .disconnecting {
            fail("Capture interrupted before streaming.")
        }
    }

    func centralManagerDidUpdateState(_ central: CBCentralManager) {
        switch central.state {
        case .poweredOn:
            guard phase == .bluetooth else { return }
            advance(to: .scanning, timeout: 12)
            for peripheral in central.retrieveConnectedPeripherals(withServices: [serviceID]) {
                observe(peripheral)
                if phase != .scanning { return }
            }
            central.scanForPeripherals(withServices: [serviceID])
            report("Scanning for the WHOOP 5.0/MG fd4b service for up to 12 seconds.")
        case .unknown, .resetting:
            break
        default:
            fail("Bluetooth is unavailable (state \(central.state.rawValue), authorization \(CBCentralManager.authorization.rawValue)). Check Bluetooth and System Settings → Privacy & Security → Bluetooth.")
        }
    }

    func centralManager(_ central: CBCentralManager, didDiscover peripheral: CBPeripheral,
                        advertisementData: [String: Any], rssi RSSI: NSNumber) {
        guard phase == .scanning else { return }
        observe(peripheral, name: advertisementData[CBAdvertisementDataLocalNameKey] as? String)
    }

    private func observe(_ peripheral: CBPeripheral, name: String? = nil) {
        switch mode {
        case .discover:
            guard found.insert(peripheral.identifier).inserted else { return }
            let label = (name ?? peripheral.name ?? "Unnamed").components(separatedBy: .controlCharacters)
            print("\(peripheral.identifier.uuidString)\t\(label.joined(separator: " "))")
        case .capture(let id, _):
            guard peripheral.identifier == id else { return }
            central.stopScan()
            device = peripheral
            peripheral.delegate = self
            advance(to: .connecting)
            central.connect(peripheral)
        }
    }

    func centralManager(_ central: CBCentralManager, didConnect peripheral: CBPeripheral) {
        guard phase == .connecting else { return }
        advance(to: .services)
        peripheral.discoverServices([serviceID])
    }

    func centralManager(_ central: CBCentralManager, didFailToConnect peripheral: CBPeripheral, error: Error?) {
        fail("Connection failed: \(error?.localizedDescription ?? "unknown reason").")
    }

    func centralManager(_ central: CBCentralManager, didDisconnectPeripheral peripheral: CBPeripheral, error: Error?) {
        if phase != .disconnecting {
            exitStatus = 1
            report("Unexpected disconnect: \(error?.localizedDescription ?? "link closed"). Stream cleanup could not be confirmed.")
        }
        finish()
    }

    func peripheral(_ peripheral: CBPeripheral, didDiscoverServices error: Error?) {
        guard phase == .services else { return }
        guard error == nil, let service = peripheral.services?.first(where: { $0.uuid == serviceID }) else {
            fail("WHOOP service discovery failed: \(error?.localizedDescription ?? "fd4b service missing").")
            return
        }
        advance(to: .characteristics)
        peripheral.discoverCharacteristics([writeID, responseID, dataID], for: service)
    }

    func peripheral(_ peripheral: CBPeripheral, didDiscoverCharacteristicsFor service: CBService, error: Error?) {
        guard phase == .characteristics else { return }
        let characteristics = service.characteristics ?? []
        guard error == nil,
              let writer = characteristics.first(where: { $0.uuid == writeID && $0.properties.contains(.write) }),
              let response = characteristics.first(where: { $0.uuid == responseID }),
              let data = characteristics.first(where: { $0.uuid == dataID }) else {
            fail("WHOOP command/data characteristics unavailable: \(error?.localizedDescription ?? "missing required characteristic").")
            return
        }

        command = writer
        notifications = [response, data]
        // The confirmed Hello may trigger macOS pairing. Only explicit capture mode reaches this write.
        send(145, arguments: [1], phase: .hello, timeout: 20)
    }

    func peripheral(_ peripheral: CBPeripheral, didWriteValueFor characteristic: CBCharacteristic, error: Error?) {
        guard characteristic.uuid == writeID else { return }
        if let error {
            exitStatus = 1
            report("\(phase.rawValue) write failed: \(error.localizedDescription).")
            switch phase {
            case .startRaw, .enableIMU: stopRaw()
            case .stopRaw: send(106, arguments: [1, 0], phase: .disableIMU)
            case .disableIMU: disconnect()
            default: fail("If macOS reports an authentication or encryption error, stop and review the pairing section in README.md.")
            }
            return
        }

        switch phase {
        case .hello:
            advance(to: .subscribing)
            awaitingNotifications = Set(notifications.map(\.uuid))
            for channel in notifications { peripheral.setNotifyValue(true, for: channel) }
        case .startRaw:
            if shouldStop { stopRaw() } else { send(106, arguments: [1, 1], phase: .enableIMU) }
        case .enableIMU:
            guard !shouldStop else { stopRaw(); return }
            advance(to: .streaming, timeout: 8)
            report("Start writes acknowledged by Bluetooth. Waiting for live R21 frames.")
        case .stopRaw:
            send(106, arguments: [1, 0], phase: .disableIMU)
        case .disableIMU:
            report("Stop writes acknowledged by Bluetooth.")
            disconnect()
        default:
            break
        }
    }

    func peripheral(_ peripheral: CBPeripheral, didUpdateNotificationStateFor characteristic: CBCharacteristic,
                    error: Error?) {
        guard phase == .subscribing, awaitingNotifications.contains(characteristic.uuid) else { return }
        guard error == nil, characteristic.isNotifying else {
            fail("Notification setup failed on \(characteristic.uuid): \(error?.localizedDescription ?? "notifications unavailable").")
            return
        }
        awaitingNotifications.remove(characteristic.uuid)
        if awaitingNotifications.isEmpty {
            send(81, arguments: [1], phase: .startRaw)
        }
    }

    func peripheral(_ peripheral: CBPeripheral, didUpdateValueFor characteristic: CBCharacteristic,
                    error: Error?) {
        guard characteristic.uuid == dataID || characteristic.uuid == responseID else { return }
        if let error {
            report("Notification error on \(characteristic.uuid): \(error.localizedDescription).")
            return
        }
        guard let value = characteristic.value else { return }

        let hostUnix = Date().timeIntervalSince1970
        let hostUptime = ProcessInfo.processInfo.systemUptime
        let decoded = readers[characteristic.uuid, default: FrameReader()].append(value)
        for bytes in decoded {
            if bytes.count >= 17, bytes[8] == 36, commandNames[bytes[11]] == bytes[10] {
                report("WHOOP response: opcode \(bytes[10]), request \(bytes[11]), result \(bytes[12]).")
                if bytes[12] != 1 && bytes[12] != 2 {
                    exitStatus = 1
                    if phase == .streaming {
                        stopRaw()
                    } else if phase == .startRaw || phase == .enableIMU {
                        shouldStop = true
                    }
                }
            }
            if phase == .streaming, characteristic.uuid == dataID,
               let frame = MotionFrame(validated: bytes) {
                record(frame, hostUnix: hostUnix, hostUptime: hostUptime)
            }
        }
    }

    private func record(_ frame: MotionFrame, hostUnix: Double, hostUptime: Double) {
        if let priorMotion {
            if frame.sequence == priorMotion.sequence, frame.seconds == priorMotion.seconds,
               frame.fractionalTicks == priorMotion.fractionalTicks { return }
            if frame.sequence != priorMotion.sequence &+ 1 {
                report("Record index changed from \(priorMotion.sequence) to \(frame.sequence). Check the strap clock and stream gaps.")
            }
        }
        if frames == 0, case .capture(_, let seconds) = mode {
            advance(to: .streaming, timeout: seconds)
            report("Received live R21 data. Recording for \(seconds) seconds.")
        }
        silence?.cancel()
        let silence = DispatchWorkItem { [weak self] in
            guard let self, self.phase == .streaming else { return }
            self.exitStatus = 1
            report("No new R21 frame for five seconds.")
            self.stopRaw()
        }
        self.silence = silence
        DispatchQueue.main.asyncAfter(deadline: .now() + 5, execute: silence)

        let csv = frame.csvRows(hostUnix: hostUnix, hostUptime: hostUptime)
        do {
            try FileHandle.standardOutput.write(contentsOf: Data(csv.utf8))
            priorMotion = frame
            rows += frame.pairedCount
            frames += 1
        } catch {
            exitStatus = 1
            report("Could not write CSV: \(error.localizedDescription).")
            stopRaw()
        }
    }

    private func send(_ opcode: UInt8, arguments: [UInt8], phase: Phase, timeout: Int = 8) {
        guard let device, let command, device.state == .connected else {
            fail("Link closed before \(phase.rawValue) could be sent.")
            return
        }
        advance(to: phase, timeout: timeout)
        sequence &+= 1
        commandNames[sequence] = opcode
        device.writeValue(WhoopWire.command(opcode, sequence: sequence, arguments: arguments),
                          for: command, type: .withResponse)
    }

    private func stopRaw() {
        silence?.cancel()
        send(82, arguments: [1], phase: .stopRaw)
    }

    private func advance(to next: Phase, timeout: Int = 8) {
        deadline?.cancel()
        phase = next
        let work = DispatchWorkItem { [weak self] in self?.timedOut() }
        deadline = work
        DispatchQueue.main.asyncAfter(deadline: .now() + .seconds(timeout), execute: work)
    }

    private func timedOut() {
        switch phase {
        case .scanning:
            if case .discover = mode {
                if found.isEmpty { report("No matching device seen. Leave the phone pairing as is.") }
                finish()
            }
            fail("The selected UUID did not appear on the fd4b service.")
        case .streaming:
            if frames == 0 {
                exitStatus = 1
                report("No valid live six-axis R21 frame received. Check firmware, bond and command results.")
            }
            stopRaw()
        case .startRaw, .enableIMU, .stopRaw, .disableIMU:
            fail("Timed out at \(phase.rawValue). The pending Bluetooth write and stream cleanup are unconfirmed.")
        case .disconnecting:
            finish()
        default:
            fail("Timed out at \(phase.rawValue).")
        }
    }

    private func fail(_ message: String) {
        exitStatus = 1
        report(message)
        disconnect()
    }

    private func disconnect() {
        guard phase != .disconnecting else { return }
        silence?.cancel()
        guard let device, device.state != .disconnected else { finish() }
        advance(to: .disconnecting, timeout: 3)
        central.cancelPeripheralConnection(device)
    }

    private func finish() -> Never {
        central?.stopScan()
        if case .capture = mode {
            let rejected = readers.values.reduce(0) { $0 + $1.rejected }
            report("Capture ended. \(frames) live R21 frames, \(rows) rows, \(rejected) framing rejects.")
            if rows == 0 { exitStatus = 1 }
        }
        exit(exitStatus)
    }
}
