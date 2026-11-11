import Foundation

let usage = """
Usage:
  airtype-capture discover
  airtype-capture capture <macOS-device-UUID> --allow-mac-bond [seconds]

Discover scans without connecting. Capture writes to the selected strap, and macOS
may attempt to bond. Only run capture after accepting that the phone may need to
be paired again. Duration is 5–60 seconds (default 20) after the first frame.
"""

let args = Array(CommandLine.arguments.dropFirst())
let mode: Capture.Mode
switch args.first {
case nil, "help", "--help", "-h":
    print(usage)
    exit(0)
case "discover" where args.count == 1:
    mode = .discover
case "capture" where args.count == 3 || args.count == 4:
    let seconds = args.count == 4 ? Int(args[3]) : 20
    guard let id = UUID(uuidString: args[1]), args[2] == "--allow-mac-bond",
          let seconds, (5...60).contains(seconds) else {
        report(usage)
        exit(64)
    }
    mode = .capture(id, seconds: seconds)
default:
    report(usage)
    exit(64)
}

let capture = Capture(mode: mode)
signal(SIGPIPE, SIG_IGN)
signal(SIGINT, SIG_IGN)
signal(SIGTERM, SIG_IGN)
let interrupts = [SIGINT, SIGTERM].map { number in
    let source = DispatchSource.makeSignalSource(signal: number, queue: .main)
    source.setEventHandler { capture.interrupt() }
    source.resume()
    return source
}

if case .capture = mode {
    let header = "host_unix_s,host_uptime_s,record_index,strap_unix_s,strap_fraction_ticks,sample_index,accel_count,gyro_count,estimated_sample_unix_s,ax_raw,ay_raw,az_raw,gx_raw,gy_raw,gz_raw,ax_g,ay_g,az_g,gx_rad_s,gy_rad_s,gz_rad_s\n"
    do {
        try FileHandle.standardOutput.write(contentsOf: Data(header.utf8))
    } catch {
        report("Could not write CSV header: \(error.localizedDescription).")
        exit(1)
    }
}

capture.start()
dispatchMain()
