import Foundation
import XCTest
@testable import AirTypeCapture

final class ModeTests: XCTestCase {
    private let id = "12345678-1234-1234-1234-123456789ABC"

    func testDiscoverTakesNoArguments() {
        XCTAssertEqual(Capture.Mode(arguments: ["discover"]), .discover)
        XCTAssertNil(Capture.Mode(arguments: ["discover", "extra"]))
    }

    func testCaptureDefaultsToTwentySecondsAndStaysBounded() {
        let uuid = UUID(uuidString: id)!
        XCTAssertEqual(Capture.Mode(arguments: ["capture", id, "--allow-mac-bond"]),
                       .capture(uuid, seconds: 20))
        XCTAssertEqual(Capture.Mode(arguments: ["capture", id, "--allow-mac-bond", "60"]),
                       .capture(uuid, seconds: 60))
        XCTAssertNil(Capture.Mode(arguments: ["capture", id, "--allow-mac-bond", "61"]))
        XCTAssertNil(Capture.Mode(arguments: ["capture", id, "--allow-mac-bond", "4"]))
    }

    func testStreamRunsUntilStoppedAndStillNeedsTheBondOptIn() {
        let uuid = UUID(uuidString: id)!
        XCTAssertEqual(Capture.Mode(arguments: ["stream", id, "--allow-mac-bond"]),
                       .capture(uuid, seconds: nil))
        XCTAssertNil(Capture.Mode(arguments: ["stream", id]))
        XCTAssertNil(Capture.Mode(arguments: ["stream", id, "--allow-mac-bond", "30"]))
        XCTAssertNil(Capture.Mode(arguments: ["stream", "not-a-uuid", "--allow-mac-bond"]))
    }

    func testUnknownCommandsAreRejected() {
        XCTAssertNil(Capture.Mode(arguments: []))
        XCTAssertNil(Capture.Mode(arguments: ["record"]))
    }
}
