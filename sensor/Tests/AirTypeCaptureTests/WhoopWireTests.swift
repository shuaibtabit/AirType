import Foundation
import XCTest
@testable import AirTypeCapture

final class WhoopWireTests: XCTestCase {
    func testCommandFramesMatchPublishedWireBytes() {
        XCTAssertEqual(WhoopWire.command(145, sequence: 1, arguments: [1]),
                       Data([0xaa, 0x01, 0x08, 0x00, 0x00, 0x01, 0xe6, 0x71,
                             0x23, 0x01, 0x91, 0x01, 0x36, 0x3e, 0x5c, 0x8d]))
        XCTAssertEqual(WhoopWire.command(106, sequence: 0xf1, arguments: [1, 1]),
                       Data([0xaa, 0x01, 0x0c, 0x00, 0x00, 0x01, 0xe7, 0x41,
                             0x23, 0xf1, 0x6a, 0x01, 0x01, 0x00, 0x00, 0x00,
                             0x58, 0xe9, 0x61, 0xfc]))
    }

    func testReassemblyChecksBothChecksumsAndRecovers() {
        let valid = WhoopWire.command(145, sequence: 1, arguments: [1])
        var badHeader = valid
        badHeader[6] ^= 1
        var badBody = valid
        badBody[12] ^= 1

        var reader = FrameReader()
        XCTAssertTrue(reader.append(Data([0, 1]) + valid.prefix(5)).isEmpty)
        XCTAssertEqual(reader.append(valid.dropFirst(5) + badHeader + badBody + valid),
                       [Array(valid), Array(valid)])
        XCTAssertEqual(reader.rejected, 2)
    }

    func testMotionPreservesSixSignedAxesAndDoesNotFillMissingGyro() throws {
        var bytes = [UInt8](repeating: 0, count: 1244)
        bytes[8] = 43
        bytes[9] = 21
        bytes[11] = 17
        bytes[15] = 10
        bytes[20] = 0x40
        bytes[24] = 100
        bytes[630] = 1
        bytes[29] = 0x10
        bytes[229] = 0xf0
        bytes[428] = 1
        bytes[641] = 0x40
        bytes[841] = 0xc0
        bytes[1040] = 1

        let partial = try XCTUnwrap(MotionFrame(validated: bytes))
        XCTAssertEqual(partial.pairedCount, 1)
        let fields = partial.csvRows(hostUnix: 20, hostUptime: 30).trimmingCharacters(in: .newlines)
            .components(separatedBy: ",")
        XCTAssertEqual(Array(fields[0..<9]), ["20.0", "30.0", "17", "10", "16384", "0", "100", "1", ""])
        XCTAssertEqual(Array(fields[9..<15]), ["4096", "-4096", "1", "16384", "-16384", "1"])
        XCTAssertEqual(Double(fields[15]), 1)
        XCTAssertEqual(try XCTUnwrap(Double(fields[18])), 1000 * .pi / 180, accuracy: 0.000001)

        bytes[630] = 100
        let full = try XCTUnwrap(MotionFrame(validated: bytes))
        let rows = full.csvRows(hostUnix: 20, hostUptime: 30).split(separator: "\n")
        XCTAssertEqual(rows.count, 100)
        XCTAssertEqual(rows[1].split(separator: ",")[8], "10.51")

        bytes[8] = 47
        XCTAssertNil(MotionFrame(validated: bytes))
        bytes[8] = 43
        bytes[630] = 101
        XCTAssertNil(MotionFrame(validated: bytes))
    }
}
