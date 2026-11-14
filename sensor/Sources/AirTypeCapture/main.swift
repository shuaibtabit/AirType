import Foundation

let usage = """
Usage:
  airtype-capture discover
  airtype-capture capture <macOS-device-UUID> --allow-mac-bond [seconds]
  airtype-capture stream <macOS-device-UUID> --allow-mac-bond

Discover scans without connecting. Capture and stream write to the selected strap,
and macOS may attempt to bond. Only run them after accepting that the phone may
need to be paired again. Capture lasts 5–60 seconds (default 20) after the first
frame. Stream runs until Ctrl-C, or until the strap is silent for five seconds.
"""

let args = Array(CommandLine.arguments.dropFirst())
if args.isEmpty || ["help", "--help", "-h"].contains(args[0]) {
    print(usage)
    exit(0)
}
guard let mode = Capture.Mode(arguments: args) else {
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
