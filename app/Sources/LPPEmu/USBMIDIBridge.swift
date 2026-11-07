import CoreMIDI
import Foundation
import Network

/// Connects to the emulated USB host inside Renode (renode/LPPOTGFS.cs, `usbOtgFs StartBridge <port>`) and
/// publishes the firmware's USB-MIDI cables as CoreMIDI virtual ports, so DAWs see the emulator like the
/// real Launchpad ("LPProMK3 MIDI", "LPProMK3 DIN", "LPProMK3 DAW", suffixed " (Emu)").
///
/// Bridge lines: "dev vid pid name", "cable in|out n name", "ready", "m xxxxxxxx" (USB-MIDI packet), "log text".
final class USBMIDIBridge: @unchecked Sendable {
    struct Status: Equatable {
        var connected = false
        var configured = false
        var device = ""
        var ports: [String] = []
        var packetsIn = 0
        var packetsOut = 0
    }

    /// Called on the bridge queue whenever the status changes.
    var onStatus: ((Status) -> Void)?
    /// Called on the bridge queue with "log" lines from the emulated host.
    var onLog: ((String) -> Void)?

    private let queue = DispatchQueue(label: "lppemu.usbmidi")
    private var conn: NWConnection?
    private var port: UInt16 = 0
    private var generation = 0
    private var lineBuffer = Data()
    private var status = Status()

    private var client = MIDIClientRef()
    /// cable number -> virtual source (firmware -> Mac)
    private var sources: [Int: MIDIEndpointRef] = [:]
    /// cable number -> virtual destination (Mac -> firmware)
    private var destinations: [Int: MIDIEndpointRef] = [:]
    /// endpoints by name, kept across restarts so DAW connections survive
    private var endpointsByName: [String: MIDIEndpointRef] = [:]
    private var pendingIn: [(Int, String)] = []
    private var pendingOut: [(Int, String)] = []
    /// per-cable SysEx assembly (USB-MIDI -> UMP and UMP -> USB-MIDI)
    private var sysexFromDevice: [Int: [UInt8]] = [:]
    private var sysexToDevice: [Int: [UInt8]] = [:]

    init() {
        let err = MIDIClientCreateWithBlock("LPP MK3 Emulator" as CFString, &client) { _ in }
        if err != noErr { NSLog("LPPEmu: MIDIClientCreate failed \(err)") }
    }

    // MARK: connection

    func connect(port: UInt16) {
        queue.async { [self] in
            generation += 1
            self.port = port
            conn?.cancel()
            conn = nil
            status = Status()
            publish()
            open(gen: generation)
        }
    }

    func disconnect() {
        queue.async { [self] in
            generation += 1
            conn?.cancel()
            conn = nil
            status = Status()
            publish()
        }
    }

    private func open(gen: Int) {
        guard gen == generation, port != 0 else { return }
        let tcp = NWProtocolTCP.Options()
        tcp.noDelay = true
        let c = NWConnection(host: "127.0.0.1", port: NWEndpoint.Port(rawValue: port)!,
                             using: NWParameters(tls: nil, tcp: tcp))
        c.stateUpdateHandler = { [weak self] state in
            guard let self else { return }
            switch state {
            case .ready:
                self.status.connected = true
                self.publish()
                self.receive(c, gen: gen)
            case .waiting, .failed:
                c.cancel()
                self.queue.asyncAfter(deadline: .now() + 0.5) { self.open(gen: gen) }
            default:
                break
            }
        }
        conn = c
        lineBuffer.removeAll()
        c.start(queue: queue)
    }

    private func receive(_ c: NWConnection, gen: Int) {
        c.receive(minimumIncompleteLength: 1, maximumLength: 65536) { [weak self] data, _, done, error in
            guard let self, gen == self.generation else { return }
            if let data, !data.isEmpty { self.handle(data) }
            if done || error != nil {
                self.status.connected = false
                self.status.configured = false
                self.publish()
                self.queue.asyncAfter(deadline: .now() + 0.5) { self.open(gen: gen) }
            } else {
                self.receive(c, gen: gen)
            }
        }
    }

    private func publish() { onStatus?(status) }

    private func handle(_ data: Data) {
        lineBuffer.append(data)
        guard let last = lineBuffer.lastIndex(of: 0x0A) else { return }
        let text = String(decoding: lineBuffer[..<last], as: UTF8.self)
        lineBuffer.removeSubrange(...last)
        var counted = false
        for line in text.split(separator: "\n") {
            if line.hasPrefix("m "), line.count == 10, let v = UInt32(line.dropFirst(2), radix: 16) {
                fromDevice(v)
                counted = true
                continue
            }
            let f = line.split(separator: " ", maxSplits: 3).map(String.init)
            switch f.first {
            case "dev":
                status.device = f.count >= 4 ? f[3] : "USB device"
                pendingIn.removeAll()
                pendingOut.removeAll()
            case "cable" where f.count >= 4:
                if let n = Int(f[2]) {
                    if f[1] == "in" { pendingIn.append((n, f[3])) } else { pendingOut.append((n, f[3])) }
                }
            case "ready":
                makeEndpoints()
                status.configured = true
                publish()
            case "log":
                onLog?(String(line.dropFirst(4)))
            default:
                break
            }
        }
        if counted { publish() }
    }

    private func send(_ packets: [UInt32]) {
        guard !packets.isEmpty, let c = conn else { return }
        var s = ""
        for p in packets { s += "m " + String(format: "%08x", p) + "\n" }
        c.send(content: Data(s.utf8), completion: .contentProcessed { _ in })
        status.packetsOut += packets.count
    }

    // MARK: CoreMIDI endpoints

    private static func displayName(_ name: String) -> String { name + " (Emu)" }

    private static func uniqueID(_ name: String) -> MIDIUniqueID {
        var h: UInt32 = 2166136261
        for b in name.utf8 { h = (h ^ UInt32(b)) &* 16777619 }
        return MIDIUniqueID(bitPattern: h | 0x4000_0000)
    }

    private func makeEndpoints() {
        sources.removeAll()
        destinations.removeAll()
        var names: [String] = []
        for (n, name) in pendingIn {
            let full = Self.displayName(name)
            names.append(full)
            if let ep = endpointsByName["src:" + full] { sources[n] = ep; continue }
            var ep = MIDIEndpointRef()
            if MIDISourceCreateWithProtocol(client, full as CFString, ._1_0, &ep) == noErr {
                MIDIObjectSetIntegerProperty(ep, kMIDIPropertyUniqueID, Self.uniqueID("src:" + full))
                MIDIObjectSetStringProperty(ep, kMIDIPropertyManufacturer, "Novation (emulated)" as CFString)
                endpointsByName["src:" + full] = ep
                sources[n] = ep
            }
        }
        for (n, name) in pendingOut {
            let full = Self.displayName(name)
            if !names.contains(full) { names.append(full) }
            if let ep = endpointsByName["dst:" + full] { destinations[n] = ep; continue }
            var ep = MIDIEndpointRef()
            let cable = n
            let err = MIDIDestinationCreateWithProtocol(client, full as CFString, ._1_0, &ep) { [weak self] list, _ in
                let packets = Self.umpToUSB(list, cable: cable, bridge: self)
                guard let self, !packets.isEmpty else { return }
                self.queue.async { self.send(packets) }
            }
            if err == noErr {
                MIDIObjectSetIntegerProperty(ep, kMIDIPropertyUniqueID, Self.uniqueID("dst:" + full))
                MIDIObjectSetStringProperty(ep, kMIDIPropertyManufacturer, "Novation (emulated)" as CFString)
                endpointsByName["dst:" + full] = ep
                destinations[n] = ep
            }
        }
        status.ports = names
    }

    // MARK: USB-MIDI -> CoreMIDI (UMP, MIDI 1.0 protocol)

    private func fromDevice(_ v: UInt32) {
        status.packetsIn += 1
        let cable = Int(v >> 28)
        let cin = Int((v >> 24) & 0xF)
        let b1 = UInt8((v >> 16) & 0xFF), b2 = UInt8((v >> 8) & 0xFF), b3 = UInt8(v & 0xFF)
        guard let src = sources[cable] else { return }
        var words: [UInt32] = []
        switch cin {
        case 0x8...0xE:
            words = [0x2000_0000 | UInt32(b1) << 16 | UInt32(b2) << 8 | UInt32(b3)]
        case 0x2, 0x3:
            words = [0x1000_0000 | UInt32(b1) << 16 | UInt32(b2) << 8 | (cin == 3 ? UInt32(b3) : 0)]
        case 0xF:
            words = [0x1000_0000 | UInt32(b1) << 16]
        case 0x4, 0x5, 0x6, 0x7:
            let n = [0x4: 3, 0x5: 1, 0x6: 2, 0x7: 3][cin]!
            let bytes = Array([b1, b2, b3].prefix(n))
            if cin == 0x5 && b1 != 0xF7 && sysexFromDevice[cable] == nil {
                words = [0x1000_0000 | UInt32(b1) << 16]          // single-byte system common
                break
            }
            sysexFromDevice[cable, default: []].append(contentsOf: bytes)
            if cin != 0x4 {                                         // end of SysEx
                let all = sysexFromDevice.removeValue(forKey: cable) ?? []
                words = MIDIUMP.sysexToUMP(all)
            }
        default:
            return
        }
        MIDIUMP.emit(words, to: src)
    }

    // MARK: CoreMIDI -> USB-MIDI

    private static func umpToUSB(_ list: UnsafePointer<MIDIEventList>, cable: Int, bridge: USBMIDIBridge?) -> [UInt32] {
        var out: [UInt32] = []
        let cn = UInt32(cable) << 28
        func pkt(_ cin: UInt32, _ a: UInt8, _ b: UInt8 = 0, _ c: UInt8 = 0) -> UInt32 {
            cn | cin << 24 | UInt32(a) << 16 | UInt32(b) << 8 | UInt32(c)
        }
        for packet in list.unsafeSequence() {
            let count = Int(packet.pointee.wordCount)
            let words: [UInt32] = withUnsafeBytes(of: packet.pointee.words) { Array($0.bindMemory(to: UInt32.self).prefix(count)) }
            var i = 0
            while i < words.count {
                let w = words[i]
                let mt = w >> 28
                let s = UInt8((w >> 16) & 0xFF), d1 = UInt8((w >> 8) & 0xFF), d2 = UInt8(w & 0xFF)
                switch mt {
                case 0x2:
                    out.append(pkt(UInt32(s >> 4), s, d1, d2))
                    i += 1
                case 0x1:
                    switch s {
                    case 0xF1, 0xF3: out.append(pkt(0x2, s, d1))
                    case 0xF2: out.append(pkt(0x3, s, d1, d2))
                    case 0xF6: out.append(pkt(0x5, s))
                    default: out.append(pkt(0xF, s))
                    }
                    i += 1
                case 0x3 where i + 1 < words.count:
                    let st = (w >> 20) & 0xF
                    let n = Int((w >> 16) & 0xF)
                    let w2 = words[i + 1]
                    let bytes = [UInt8((w >> 8) & 0xFF), UInt8(w & 0xFF), UInt8(w2 >> 24), UInt8((w2 >> 16) & 0xFF),
                                 UInt8((w2 >> 8) & 0xFF), UInt8(w2 & 0xFF)].prefix(min(n, 6))
                    var buf = bridge?.sysexToDevice[cable] ?? []
                    if st == 0 || st == 1 { buf = [0xF0] }
                    buf += bytes
                    if st == 0 || st == 3 {
                        buf.append(0xF7)
                        var j = 0
                        while j < buf.count {
                            let rest = buf.count - j
                            if rest > 3 { out.append(pkt(0x4, buf[j], buf[j + 1], buf[j + 2])); j += 3; continue }
                            let c = buf[j..<buf.count].map { $0 } + [0, 0]
                            out.append(pkt(UInt32(4 + rest), c[0], rest > 1 ? c[1] : 0, rest > 2 ? c[2] : 0))
                            j = buf.count
                        }
                        bridge?.sysexToDevice[cable] = nil
                    } else {
                        bridge?.sysexToDevice[cable] = buf
                    }
                    i += 2
                default:
                    i += (mt == 0x3 || mt == 0x4) ? 2 : (mt == 0x5 ? 4 : 1)
                }
            }
        }
        return out
    }
}
