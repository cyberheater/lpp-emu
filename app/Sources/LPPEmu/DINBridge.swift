import CoreMIDI
import Foundation
import Network

/// The emulator's DIN MIDI jacks as CoreMIDI ports: sources "LPP Emu DIN Out 1/2" (what the firmware transmits on
/// UART4 / UART7) and destination "LPP Emu DIN In" (fed into UART4's receiver). Talks to renode/LPPDIN.cs.
final class DINBridge: @unchecked Sendable {
    struct Status: Equatable { var connected = false; var bytesOut = 0; var bytesIn = 0 }
    var onStatus: ((Status) -> Void)?
    /// Called on the bridge queue with each output's parsed messages as UMP words (1 = DIN Out 1, 2 = DIN Out 2).
    var onOutput: ((Int, [UInt32]) -> Void)?

    private let queue = DispatchQueue(label: "lppemu.din")
    private var conn: NWConnection?
    private var port: UInt16 = 0
    private var generation = 0
    private var lineBuffer = Data()
    private var status = Status()

    private var client = MIDIClientRef()
    private var outs: [Int: MIDIEndpointRef] = [:]
    private var input = MIDIEndpointRef()
    private var parsers: [Int: MIDIByteParser] = [1: MIDIByteParser(), 2: MIDIByteParser()]
    private var sysexIn: [UInt8] = []          // touched only on the CoreMIDI callback thread

    init() {
        MIDIClientCreateWithBlock("LPP MK3 Emulator DIN" as CFString, &client) { _ in }
        for n in [1, 2] {
            let name = "LPP Emu DIN Out \(n)"
            var ep = MIDIEndpointRef()
            if MIDISourceCreateWithProtocol(client, name as CFString, ._1_0, &ep) == noErr {
                MIDIObjectSetIntegerProperty(ep, kMIDIPropertyUniqueID, Self.uniqueID(name))
                outs[n] = ep
            }
        }
        let name = "LPP Emu DIN In"
        MIDIDestinationCreateWithProtocol(client, name as CFString, ._1_0, &input) { [weak self] list, _ in
            guard let self else { return }
            let bytes = MIDIUMP.bytes(from: list, sysex: &self.sysexIn)
            guard !bytes.isEmpty else { return }
            self.queue.async { self.send(bytes) }
        }
        MIDIObjectSetIntegerProperty(input, kMIDIPropertyUniqueID, Self.uniqueID(name))
    }

    private static func uniqueID(_ name: String) -> MIDIUniqueID {
        var h: UInt32 = 2166136261
        for b in name.utf8 { h = (h ^ UInt32(b)) &* 16777619 }
        return MIDIUniqueID(bitPattern: h | 0x4000_0000)
    }

    func connect(port: UInt16) {
        queue.async { [self] in
            generation += 1
            self.port = port
            conn?.cancel()
            conn = nil
            status = Status()
            parsers = [1: MIDIByteParser(), 2: MIDIByteParser()]
            onStatus?(status)
            open(gen: generation)
        }
    }

    func disconnect() {
        queue.async { [self] in
            generation += 1
            conn?.cancel()
            conn = nil
            status = Status()
            onStatus?(status)
        }
    }

    private func open(gen: Int) {
        guard gen == generation, port != 0 else { return }
        let tcp = NWProtocolTCP.Options()
        tcp.noDelay = true
        let c = NWConnection(host: "127.0.0.1", port: NWEndpoint.Port(rawValue: port)!, using: NWParameters(tls: nil, tcp: tcp))
        c.stateUpdateHandler = { [weak self] state in
            guard let self else { return }
            switch state {
            case .ready:
                self.status.connected = true
                self.onStatus?(self.status)
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
                self.onStatus?(self.status)
                self.queue.asyncAfter(deadline: .now() + 0.5) { self.open(gen: gen) }
            } else {
                self.receive(c, gen: gen)
            }
        }
    }

    /// Lines "o <port> <hex>": bytes the firmware sent on DIN Out 1/2.
    private func handle(_ data: Data) {
        lineBuffer.append(data)
        guard let last = lineBuffer.lastIndex(of: 0x0A) else { return }
        let text = String(decoding: lineBuffer[..<last], as: UTF8.self)
        lineBuffer.removeSubrange(...last)
        var words: [Int: [UInt32]] = [:]
        for line in text.split(separator: "\n") {
            let f = line.split(separator: " ")
            guard f.count >= 3, f[0] == "o", let n = Int(f[1]), parsers[n] != nil else { continue }
            for h in f.dropFirst(2) {
                guard let b = UInt8(h, radix: 16) else { continue }
                status.bytesOut += 1
                if let msg = parsers[n]!.feed(b) { words[n, default: []] += MIDIUMP.words(for: msg) }
            }
        }
        for (n, w) in words {
            if let src = outs[n] { MIDIUMP.emit(w, to: src) }
            onOutput?(n, w)
        }
        onStatus?(status)
    }

    /// Feeds MIDI bytes into the emulator's DIN In (e.g. from the real Launchpad's MIDI In).
    func input(_ bytes: [UInt8]) {
        queue.async { [self] in send(bytes) }
    }

    private func send(_ bytes: [UInt8]) {
        guard let c = conn else { return }
        // keep lines short; LPPDIN feeds them to the UART, which paces them at 31250 baud
        var s = ""
        for chunk in stride(from: 0, to: bytes.count, by: 32) {
            s += "i " + bytes[chunk..<min(chunk + 32, bytes.count)].map { String(format: "%02x", $0) }.joined(separator: " ") + "\n"
        }
        c.send(content: Data(s.utf8), completion: .contentProcessed { _ in })
        status.bytesIn += bytes.count
    }
}
