import CoreMIDI
import Foundation

/// Takes over a real Launchpad Pro MK3 connected over USB (running Novation's firmware): puts it in Programmer mode,
/// mirrors the emulator's LEDs onto it and feeds its pads and buttons into the emulated Launchpad.
///
/// Programmer mode (Launchpad Pro MK3 Programmer's Reference): pads send notes and buttons send CCs numbered with the
/// same XY indices the emulator uses (11-88 grid, 91-98 top, 10-80 left, 19-89 right, 1-8 / 101-108 bottom rows);
/// LEDs are set with SysEx F0 00 20 29 02 0E 03 {03 index r g b}... F7 (0-127 per colour).
final class HardwareMirror: @unchecked Sendable {
    struct Status: Equatable {
        var connected = false
        var name = ""
        var dinConnected = false
    }

    /// Which emulated DIN outputs go to the real Launchpad's DIN jacks. Its firmware sends everything on its USB
    /// "DIN" port to both physical outputs, so routing both merges them (clock is taken from Out 1 only).
    enum DINRoute: String, CaseIterable, Identifiable {
        case off = "Off", both = "DIN Out 1 + 2 (merged)", out1 = "DIN Out 1 only", out2 = "DIN Out 2 only"
        var id: String { rawValue }
    }

    /// Called on the mirror queue: (logical index, pressed, 0-127 velocity/pressure).
    var onInput: ((Int, Bool, Int) -> Void)?
    var onStatus: ((Status) -> Void)?
    /// Called on the mirror queue with MIDI bytes that arrived at the real Launchpad's DIN MIDI In.
    var onDINInput: (([UInt8]) -> Void)?

    private static let header: [UInt8] = [0xF0, 0x00, 0x20, 0x29, 0x02, 0x0E]
    private static let programmerMode: [UInt8] = header + [0x0E, 0x01, 0xF7]
    private static let liveMode: [UInt8] = header + [0x0E, 0x00, 0xF7]
    /// Every LED index on the Pro MK3 (grid, edge buttons, both bottom rows, logo).
    private static let allLEDs: [Int] = {
        var a: [Int] = []
        for row in 1...8 { for col in 0...9 { a.append(row * 10 + col) } }
        a += Array(90...99) + Array(1...8) + Array(101...108)
        return a
    }()

    private let queue = DispatchQueue(label: "lppemu.hardware")
    private var client = MIDIClientRef()
    private var inPort = MIDIPortRef()
    private var outPort = MIDIPortRef()
    private var source: MIDIEndpointRef = 0
    private var destination: MIDIEndpointRef = 0
    private var dinInPort = MIDIPortRef()
    private var dinSource: MIDIEndpointRef = 0
    private var dinDestination: MIDIEndpointRef = 0
    private var dinSysex: [UInt8] = []    // touched only on the CoreMIDI input thread
    var dinRoute: DINRoute = .both
    private var status = Status()

    /// Emulator LED state (logical index -> 7-bit colour) and what the hardware currently shows.
    private var wanted: [Int: (UInt8, UInt8, UInt8)] = [:]
    private var shown: [Int: (UInt8, UInt8, UInt8)] = [:]
    private var flushScheduled = false
    private var held: Set<Int> = []

    var enabled = true {
        didSet { queue.async { [self] in enabled ? rescan() : release() } }
    }

    init() {
        MIDIClientCreateWithBlock("LPP MK3 Emulator hardware" as CFString, &client) { [weak self] note in
            if note.pointee.messageID == .msgSetupChanged {
                self?.queue.async { self?.rescan() }
            }
        }
        MIDIInputPortCreateWithProtocol(client, "from Launchpad" as CFString, ._1_0, &inPort) { [weak self] list, _ in
            guard let self else { return }
            var events: [(index: Int, kind: UInt8, value: Int)] = []
            for packet in list.unsafeSequence() {
                let n = Int(packet.pointee.wordCount)
                let words = withUnsafeBytes(of: packet.pointee.words) { Array($0.bindMemory(to: UInt32.self).prefix(n)) }
                for w in words where w >> 28 == 0x2 {
                    let status = UInt8((w >> 16) & 0xF0), d1 = Int((w >> 8) & 0x7F), d2 = Int(w & 0x7F)
                    if [0x80, 0x90, 0xA0, 0xB0].contains(status) { events.append((d1, status, d2)) }
                }
            }
            guard !events.isEmpty else { return }
            self.queue.async {
                for e in events {
                    switch e.kind {
                    case 0x90 where e.value > 0, 0xB0 where e.value > 0:
                        self.held.insert(e.index)
                        self.onInput?(e.index, true, e.value)
                    case 0x80, 0x90, 0xB0:
                        if self.held.remove(e.index) != nil { self.onInput?(e.index, false, 0) }
                    case 0xA0:
                        // polyphonic aftertouch = pad pressure, only while the pad is held
                        if self.held.contains(e.index) && e.value > 0 { self.onInput?(e.index, true, e.value) }
                    default:
                        break
                    }
                }
            }
        }
        MIDIInputPortCreateWithProtocol(client, "from Launchpad DIN" as CFString, ._1_0, &dinInPort) { [weak self] list, _ in
            guard let self else { return }
            let bytes = MIDIUMP.bytes(from: list, sysex: &self.dinSysex)
            guard !bytes.isEmpty else { return }
            self.queue.async {
                if self.dinRoute != .off { self.onDINInput?(bytes) }
            }
        }
        MIDIOutputPortCreate(client, "to Launchpad" as CFString, &outPort)
        queue.async { [self] in rescan() }
    }

    // MARK: - detection

    private static func name(_ e: MIDIEndpointRef) -> String {
        var s: Unmanaged<CFString>?
        MIDIObjectGetStringProperty(e, kMIDIPropertyDisplayName, &s)
        return (s?.takeRetainedValue() as String?) ?? ""
    }

    /// The real device's "LPProMK3 MIDI" port; the emulator's own "(Emu)" ports are ignored.
    private static func isLaunchpad(_ name: String) -> Bool {
        name.contains("LPProMK3 MIDI") && !name.contains("(Emu)") && !name.contains("LPP Emu")
    }

    /// The real device's "LPProMK3 DIN" port (USB <-> its DIN jacks).
    private static func isLaunchpadDIN(_ name: String) -> Bool {
        name.contains("LPProMK3 DIN") && !name.contains("(Emu)") && !name.contains("LPP Emu")
    }

    private func findDIN() {
        var src: MIDIEndpointRef = 0, dst: MIDIEndpointRef = 0
        if source != 0 {
            for i in 0..<MIDIGetNumberOfSources() where Self.isLaunchpadDIN(Self.name(MIDIGetSource(i))) {
                src = MIDIGetSource(i)
            }
            for i in 0..<MIDIGetNumberOfDestinations() where Self.isLaunchpadDIN(Self.name(MIDIGetDestination(i))) {
                dst = MIDIGetDestination(i)
            }
        }
        if src != dinSource {
            if dinSource != 0 { MIDIPortDisconnectSource(dinInPort, dinSource) }
            if src != 0 { MIDIPortConnectSource(dinInPort, src, nil) }
            dinSource = src
        }
        dinDestination = dst
        var s = status
        s.dinConnected = dst != 0
        setStatus(s)
    }

    /// Emulator DIN output messages (UMP words) for output 1 or 2.
    func sendDIN(output: Int, words: [UInt32]) {
        queue.async { [self] in
            guard dinDestination != 0 else { return }
            let wanted: Bool
            switch dinRoute {
            case .off: wanted = false
            case .both: wanted = true
            case .out1: wanted = output == 1
            case .out2: wanted = output == 2
            }
            guard wanted else { return }
            // Merged: real-time messages (clock, start, stop) only from Out 1, or the clock would run twice as fast.
            var out: [UInt32] = []
            var i = 0
            while i < words.count {
                let w = words[i]
                let n = (w >> 28) == 3 ? 2 : 1
                let realtime = (w >> 28) == 1 && ((w >> 16) & 0xFF) >= 0xF8
                if !(dinRoute == .both && output == 2 && realtime) { out += words[i..<min(i + n, words.count)] }
                i += n
            }
            sendWords(out, to: dinDestination)
        }
    }

    private func rescan() {
        guard enabled else { return }
        var src: MIDIEndpointRef = 0, dst: MIDIEndpointRef = 0, found = ""
        for i in 0..<MIDIGetNumberOfSources() {
            let e = MIDIGetSource(i)
            if Self.isLaunchpad(Self.name(e)) { src = e; found = Self.name(e); break }
        }
        for i in 0..<MIDIGetNumberOfDestinations() {
            let e = MIDIGetDestination(i)
            if Self.isLaunchpad(Self.name(e)) { dst = e; break }
        }
        if src == source && dst == destination {
            findDIN()
            return
        }
        if source != 0 { MIDIPortDisconnectSource(inPort, source) }
        source = src
        destination = dst
        if src != 0 && dst != 0 {
            MIDIPortConnectSource(inPort, src, nil)
            take(name: found)
            findDIN()
        } else {
            source = 0
            destination = 0
            held.removeAll()
            findDIN()
            setStatus(Status())
        }
    }

    private func take(name: String) {
        send(Self.programmerMode)
        shown.removeAll()
        // Paint everything (off where the emulator has nothing lit) so no stock LEDs linger.
        for i in Self.allLEDs where wanted[i] == nil { wanted[i] = (0, 0, 0) }
        flush()
        setStatus(Status(connected: true, name: name))
    }

    /// Hands the device back to its normal (Live) mode. Safe to call when nothing is connected.
    func release() {
        if destination != 0 { send(Self.liveMode) }
        if source != 0 { MIDIPortDisconnectSource(inPort, source) }
        source = 0
        destination = 0
        held.removeAll()
        findDIN()
        setStatus(Status())
    }

    /// Synchronous release for app termination.
    func releaseNow() {
        queue.sync { release() }
    }

    private func setStatus(_ s: Status) {
        guard s != status else { return }
        status = s
        onStatus?(s)
    }

    // MARK: - LEDs

    /// Emulator LED changes (logical index -> colour). `sevenBit`: the firmware already uses 0-127 colours.
    func setLEDs(_ changed: [Int: RGB], sevenBit: Bool) {
        let conv: (UInt8) -> UInt8 = sevenBit ? { min($0, 127) } : { $0 >> 1 }
        let mapped = changed.mapValues { (conv($0.r), conv($0.g), conv($0.b)) }
        queue.async { [self] in
            for (k, v) in mapped { wanted[k] = v }
            scheduleFlush()
        }
    }

    /// Resends everything (e.g. after the firmware restarted and the LED cache was cleared).
    func resetLEDs(_ all: [Int: RGB], sevenBit: Bool) {
        queue.async { [self] in
            wanted.removeAll()
            for i in Self.allLEDs { wanted[i] = (0, 0, 0) }
            shown.removeAll()
        }
        setLEDs(all, sevenBit: sevenBit)
    }

    private func scheduleFlush() {
        guard !flushScheduled else { return }
        flushScheduled = true
        // Coalesce bursts (a full redraw arrives as many small updates) into one SysEx every ~8 ms.
        queue.asyncAfter(deadline: .now() + 0.008) { [self] in
            flushScheduled = false
            flush()
        }
    }

    private func flush() {
        guard destination != 0 else { return }
        var body: [UInt8] = []
        for (k, v) in wanted {
            if let s = shown[k], s == v { continue }
            body += [0x03, UInt8(k), v.0, v.1, v.2]
            shown[k] = v
        }
        guard !body.isEmpty else { return }
        // The Pro MK3 accepts up to 81 LED specs per message; stay well below.
        let chunk = 5 * 64
        for start in stride(from: 0, to: body.count, by: chunk) {
            send(Self.header + [0x03] + body[start..<min(start + chunk, body.count)] + [0xF7])
        }
    }

    private func send(_ sysex: [UInt8]) {
        guard destination != 0 else { return }
        sendWords(MIDIUMP.sysexToUMP(sysex), to: destination)
    }

    private func sendWords(_ words: [UInt32], to endpoint: MIDIEndpointRef) {
        guard !words.isEmpty else { return }
        let size = 1024 + words.count * 12
        let raw = UnsafeMutableRawPointer.allocate(byteCount: size, alignment: 8)
        defer { raw.deallocate() }
        let list = raw.bindMemory(to: MIDIEventList.self, capacity: 1)
        var packet = MIDIEventListInit(list, ._1_0)
        var i = 0
        while i < words.count {
            let n = (words[i] >> 28) == 3 ? 2 : 1
            let chunk = Array(words[i..<min(i + n, words.count)])
            packet = chunk.withUnsafeBufferPointer { MIDIEventListAdd(list, size, packet, 0, chunk.count, $0.baseAddress!) }
            i += n
        }
        MIDISendEventList(outPort, endpoint, list)
    }
}
