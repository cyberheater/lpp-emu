// Sends a firmware .syx file to a Launchpad in bootloader mode over CoreMIDI (no Python packages needed).
// usage: swift scripts/flash_syx.swift <file.syx> [port-name-substring]   (default port: one containing "Bootloader")
//        swift scripts/flash_syx.swift --list
import CoreMIDI
import Foundation

setvbuf(stdout, nil, _IONBF, 0)
let args = Array(CommandLine.arguments.dropFirst())

func name(_ e: MIDIEndpointRef) -> String {
    var s: Unmanaged<CFString>?
    MIDIObjectGetStringProperty(e, kMIDIPropertyDisplayName, &s)
    return (s?.takeRetainedValue() as String?) ?? "?"
}
let destinations = (0..<MIDIGetNumberOfDestinations()).map { MIDIGetDestination($0) }
if args.first == "--list" || args.isEmpty {
    for d in destinations { print(name(d)) }
    exit(args.isEmpty ? 1 : 0)
}

let data = [UInt8](try Data(contentsOf: URL(fileURLWithPath: args[0])))
var messages: [[UInt8]] = []
var i = 0
while i < data.count {
    guard data[i] == 0xF0 else { i += 1; continue }
    guard let end = data[i...].firstIndex(of: 0xF7) else { print("unterminated SysEx"); exit(1) }
    messages.append(Array(data[i...end]))
    i = end + 1
}
let want = args.count > 1 ? args[1] : "Bootloader"
let matches = destinations.filter { name($0).contains(want) }
guard matches.count == 1, let dest = matches.first else {
    print("Need exactly one MIDI destination containing \"\(want)\"; found: \(matches.map(name))")
    print("All destinations: \(destinations.map(name))")
    exit(1)
}
print("Sending \(messages.count) SysEx messages (\(data.count) bytes) to \(name(dest))")

var client = MIDIClientRef(), port = MIDIPortRef()
MIDIClientCreate("flash_syx" as CFString, nil, nil, &client)
MIDIOutputPortCreate(client, "out" as CFString, &port)

// One message at a time, each waiting for CoreMIDI to finish sending it, then 1 ms (as tools/flash.py does).
final class Done: @unchecked Sendable { var flag = false }
for (n, m) in messages.enumerated() {
    let done = Done()
    let buf = UnsafeMutablePointer<UInt8>.allocate(capacity: m.count)
    buf.initialize(from: m, count: m.count)
    let ctx = Unmanaged.passRetained(done).toOpaque()
    var req = MIDISysexSendRequest(destination: dest, data: buf, bytesToSend: UInt32(m.count), complete: false,
                                   reserved: (0, 0, 0), completionProc: { r in
                                       Unmanaged<Done>.fromOpaque(r.pointee.completionRefCon!).takeRetainedValue().flag = true
                                   }, completionRefCon: ctx)
    MIDISendSysex(&req)
    let deadline = Date().addingTimeInterval(5)
    while !done.flag && Date() < deadline { RunLoop.current.run(until: Date().addingTimeInterval(0.0005)) }
    buf.deallocate()
    if !done.flag { print("\nTimed out sending message \(n + 1)"); exit(1) }
    usleep(1000)
    if n % 50 == 0 || n == messages.count - 1 { print("\r\(n + 1)/\(messages.count)", terminator: "") }
}
print("\nDone.")
