// swift-tools-version: 5.9
import Foundation
import PackageDescription

let plist = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
    .appendingPathComponent("sensor/Info.plist").path

let package = Package(
    name: "AirType",
    platforms: [.macOS(.v13)],
    products: [.executable(name: "airtype-capture", targets: ["AirTypeCapture"])],
    targets: [
        .executableTarget(
            name: "AirTypeCapture",
            path: "sensor/Sources/AirTypeCapture",
            linkerSettings: [.unsafeFlags(["-Xlinker", "-sectcreate", "-Xlinker", "__TEXT",
                                           "-Xlinker", "__info_plist", "-Xlinker", plist])]
        ),
        .testTarget(name: "AirTypeCaptureTests", dependencies: ["AirTypeCapture"],
                    path: "sensor/Tests/AirTypeCaptureTests")
    ]
)
