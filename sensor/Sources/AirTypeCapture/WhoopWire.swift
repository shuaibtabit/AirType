import Foundation

// Format 1 and R21 field definitions are linked in research/whoop-ble.md.
enum WhoopWire {
    static func command(_ opcode: UInt8, sequence: UInt8, arguments: [UInt8]) -> Data {
        var body = [0x23, sequence, opcode] + arguments
        while !body.count.isMultiple(of: 4) { body.append(0) }
        let length = body.count + 4
        var header: [UInt8] = [0xaa, 1, UInt8(length & 0xff), UInt8(length >> 8), 0, 1]
        let checksum = crc16(header)
        header += [UInt8(truncatingIfNeeded: checksum), UInt8(checksum >> 8)]
        let trailer = withUnsafeBytes(of: crc32(body).littleEndian) { Array($0) }
        return Data(header + body + trailer)
    }

    static func u16(_ bytes: [UInt8], _ index: Int) -> UInt16 {
        UInt16(bytes[index]) | (UInt16(bytes[index + 1]) << 8)
    }

    static func u32(_ bytes: [UInt8], _ index: Int) -> UInt32 {
        UInt32(u16(bytes, index)) | (UInt32(u16(bytes, index + 2)) << 16)
    }

    static func crc16(_ bytes: some Sequence<UInt8>) -> UInt16 {
        var crc: UInt16 = 0xffff
        for byte in bytes {
            crc ^= UInt16(byte)
            for _ in 0..<8 {
                crc = (crc >> 1) ^ (crc & 1 == 1 ? 0xa001 : 0)
            }
        }
        return crc
    }

    static func crc32(_ bytes: some Sequence<UInt8>) -> UInt32 {
        var crc: UInt32 = 0xffff_ffff
        for byte in bytes {
            crc ^= UInt32(byte)
            for _ in 0..<8 {
                crc = (crc >> 1) ^ (crc & 1 == 1 ? 0xedb8_8320 : 0)
            }
        }
        return ~crc
    }
}

struct FrameReader {
    private var buffer: [UInt8] = []
    private(set) var rejected = 0

    mutating func append(_ fragment: Data) -> [[UInt8]] {
        buffer.append(contentsOf: fragment)
        var frames: [[UInt8]] = []
        while let start = buffer.firstIndex(of: 0xaa) {
            buffer.removeFirst(start)
            guard buffer.count >= 8 else { return frames }

            let length = Int(WhoopWire.u16(buffer, 2)) + 8
            guard buffer[1] == 1, length >= 13, length <= 8192,
                  WhoopWire.crc16(buffer.prefix(6)) == WhoopWire.u16(buffer, 6) else {
                rejected += 1
                buffer.removeFirst()
                continue
            }
            guard buffer.count >= length else { return frames }

            let end = length - 4
            if WhoopWire.crc32(buffer[8..<end]) == WhoopWire.u32(buffer, end) {
                frames.append(Array(buffer.prefix(length)))
                buffer.removeFirst(length)
            } else {
                rejected += 1
                buffer.removeFirst()
            }
        }
        buffer.removeAll(keepingCapacity: true)
        return frames
    }
}

struct MotionFrame {
    let bytes: [UInt8]
    let sequence: UInt32
    let seconds: UInt32
    let fractionalTicks: UInt16
    let accelerationCount: Int
    let rotationCount: Int

    init?(validated bytes: [UInt8]) {
        guard bytes.count == 1244, bytes[8] == 43, bytes[9] == 21 else { return nil }

        let accelerationCount = Int(WhoopWire.u16(bytes, 24))
        let rotationCount = Int(WhoopWire.u16(bytes, 630))
        guard (1...100).contains(accelerationCount), (1...100).contains(rotationCount) else {
            return nil
        }

        self.bytes = bytes
        self.sequence = WhoopWire.u32(bytes, 11)
        self.seconds = WhoopWire.u32(bytes, 15)
        self.fractionalTicks = WhoopWire.u16(bytes, 19)
        self.accelerationCount = accelerationCount
        self.rotationCount = rotationCount
    }

    var pairedCount: Int { min(accelerationCount, rotationCount) }

    func csvRows(hostUnix: Double, hostUptime: Double) -> String {
        var rows = ""
        for index in 0..<pairedCount {
            let counts = [28, 228, 428, 640, 840, 1040].map {
                Int16(bitPattern: WhoopWire.u16(bytes, $0 + 2 * index))
            }
            let acceleration = counts.prefix(3).map { Double($0) / 4096 }
            let rotation = counts.suffix(3).map { Double($0) * (2000.0 / 32768) * (.pi / 180) }
            // Use the 100 Hz estimate only for full buffers and plausible fractional ticks.
            let estimate: String
            if accelerationCount == 100, rotationCount == 100, fractionalTicks < 32768 {
                estimate = String(Double(seconds) + Double(fractionalTicks) / 32768 + Double(index) / 100)
            } else {
                estimate = ""
            }
            let timing = [String(hostUnix), String(hostUptime), String(sequence), String(seconds),
                          String(fractionalTicks), String(index), String(accelerationCount),
                          String(rotationCount), estimate]
            let values = counts.map { String($0) } + (acceleration + rotation).map { String($0) }
            rows += (timing + values).joined(separator: ",") + "\n"
        }
        return rows
    }
}
