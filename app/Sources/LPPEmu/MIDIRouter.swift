import CoreMIDI
import Foundation
import os

/// Connects the emulator's DIN jacks to real MIDI devices on the Mac: DIN Out 1 / DIN Out 2 to any MIDI destination
/// (a USB-MIDI interface, a synth's USB port, the real Launchpad's "LPProMK3 DIN" port...), DIN In from any source.
/// Choices are stored by CoreMIDI unique ID, so a device reconnects automatically when it is plugged back in.
final class MIDIRouter: @unchecked Sendable {
    struct Endpoint: Identifiable, Hashable {
        let id: MIDIUniqueID
        let name: String
    }

    struct Snapshot: Equatable {
        var destinations: [Endpoint] = []
        var sources: [Endpoint] = []
    }

    /// Called on the router queue with MIDI bytes from the chosen DIN In source.
    var onInput: (([UInt8]) -> Void)?
    /// Called on the router queue when the device lists change.
    var onDevices: ((Snapshot) -> Void)?

    private let queue = DispatchQueue(label: "lppemu.router")
    private var client = MIDIClientRef()
    private var outPort = MIDIPortRef()
    private var inPort = MIDIPortRef()
    private var connectedSources: Set<MIDIEndpointRef> = []

    /// DIN In choice meaning "every MIDI source on the Mac" (omni across devices). The Launchpad's own ports are
    /// left out: in Programmer mode its MIDI port carries the pads, which the mirror already handles.
    static let allInputs = MIDIUniqueID.min
    private var inSysex: [UInt8] = []        // CoreMIDI input thread only

    /// Selected unique IDs (0 = none).
    private(set) var out1: MIDIUniqueID = 0
    private(set) var out2: MIDIUniqueID = 0
    private(set) var input: MIDIUniqueID = 0

    init() {
        let d = UserDefaults.standard
        out1 = MIDIUniqueID(d.integer(forKey: "dinOut1Device"))
        out2 = MIDIUniqueID(d.integer(forKey: "dinOut2Device"))
        input = d.object(forKey: "dinInDevice") == nil ? Self.allInputs : MIDIUniqueID(d.integer(forKey: "dinInDevice"))
        MIDIClientCreateWithBlock("LPP MK3 Emulator router" as CFString, &client) { [weak self] note in
            // Any change (devices added/removed, renamed, new IDs): refresh the lists and reconnect.
            _ = note
            self?.queue.async { self?.refresh() }
        }
        MIDIOutputPortCreate(client, "DIN out" as CFString, &outPort)
        MIDIInputPortCreateWithProtocol(client, "DIN in" as CFString, ._1_0, &inPort) { [weak self] list, _ in
            guard let self else { return }
            let bytes = MIDIUMP.bytes(from: list, sysex: &self.inSysex)
            guard !bytes.isEmpty else { return }
            self.queue.async { self.onInput?(bytes) }
        }
        queue.async { [self] in refresh() }
    }

    // MARK: - choices

    func setOut(_ output: Int, to id: MIDIUniqueID) {
        queue.async { [self] in
            if output == 1 { out1 = id } else { out2 = id }
            let key = output == 1 ? "dinOut1Device" : "dinOut2Device"
            UserDefaults.standard.set(Int(id), forKey: key)
            UserDefaults.standard.set(nameOf(id, destination: true), forKey: key + "Name")
        }
    }

    func setInput(_ id: MIDIUniqueID) {
        queue.async { [self] in
            input = id
            UserDefaults.standard.set(Int(id), forKey: "dinInDevice")
            UserDefaults.standard.set(nameOf(id, destination: false), forKey: "dinInDeviceName")
            connectInput()
        }
    }

    private var latest = Snapshot()

    private func nameOf(_ id: MIDIUniqueID, destination: Bool) -> String? {
        (destination ? latest.destinations : latest.sources).first { $0.id == id }?.name
    }

    /// A chosen device that came back with a new unique ID (software synths often recreate their ports) is found
    /// again by its name; the stored ID is then updated.
    private func reresolve(_ snap: Snapshot) {
        let d = UserDefaults.standard
        func fix(_ id: inout MIDIUniqueID, key: String, in list: [Endpoint]) {
            guard id != 0, id != Self.allInputs, !list.contains(where: { $0.id == id }),
                  let name = d.string(forKey: key + "Name"), let e = list.first(where: { $0.name == name }) else { return }
            id = e.id
            d.set(Int(e.id), forKey: key)
        }
        fix(&out1, key: "dinOut1Device", in: snap.destinations)
        fix(&out2, key: "dinOut2Device", in: snap.destinations)
        fix(&input, key: "dinInDevice", in: snap.sources)
    }

    /// Current choices (after re-resolving), for the menu.
    var selection: (out1: MIDIUniqueID, out2: MIDIUniqueID, input: MIDIUniqueID) {
        queue.sync { (out1, out2, input) }
    }

    // MARK: - devices

    private static func name(_ e: MIDIObjectRef) -> String {
        var s: Unmanaged<CFString>?
        MIDIObjectGetStringProperty(e, kMIDIPropertyDisplayName, &s)
        return (s?.takeRetainedValue() as String?) ?? "?"
    }

    private static func uniqueID(_ e: MIDIObjectRef) -> MIDIUniqueID {
        var id: MIDIUniqueID = 0
        MIDIObjectGetIntegerProperty(e, kMIDIPropertyUniqueID, &id)
        return id
    }

    /// The emulator's own virtual ports are not offered (that would loop back into itself).
    private static func isOwn(_ name: String) -> Bool { name.contains("(Emu)") || name.hasPrefix("LPP Emu") }

    private func list(_ count: Int, _ get: (Int) -> MIDIEndpointRef) -> [Endpoint] {
        (0..<count).map(get).compactMap { e in
            let n = Self.name(e)
            return Self.isOwn(n) ? nil : Endpoint(id: Self.uniqueID(e), name: n)
        }
    }

    private func refresh() {
        let snap = Snapshot(destinations: list(MIDIGetNumberOfDestinations()) { MIDIGetDestination($0) },
                            sources: list(MIDIGetNumberOfSources()) { MIDIGetSource($0) })
        latest = snap
        reresolve(snap)
        connectInput()
        onDevices?(snap)
    }

    private func endpoint(_ id: MIDIUniqueID) -> MIDIEndpointRef {
        guard id != 0 else { return 0 }
        var obj: MIDIObjectRef = 0
        var type: MIDIObjectType = .other
        guard MIDIObjectFindByUniqueID(id, &obj, &type) == noErr,
              type == .destination || type == .externalDestination || type == .source || type == .externalSource
        else { return 0 }
        return obj
    }

    private func connectInput() {
        var want: Set<MIDIEndpointRef> = []
        if input == Self.allInputs {
            for e in latest.sources where !e.name.contains("LPProMK3") {
                let src = endpoint(e.id)
                if src != 0 { want.insert(src) }
            }
        } else {
            let src = endpoint(input)
            if src != 0 { want.insert(src) }
        }
        for src in connectedSources.subtracting(want) { MIDIPortDisconnectSource(inPort, src) }
        for src in want.subtracting(connectedSources) { MIDIPortConnectSource(inPort, src, nil) }
        if want != connectedSources {
            let names = latest.sources.filter { want.contains(endpoint($0.id)) }.map(\.name)
            Logger(subsystem: "local.lppemu", category: "router").notice("DIN In: listening to \(names.joined(separator: ", "), privacy: .public)")
        }
        connectedSources = want
    }

    // MARK: - output

    /// Emulator DIN output messages (UMP words) for output 1 or 2.
    func send(output: Int, words: [UInt32]) {
        queue.async { [self] in
            let id = output == 1 ? out1 : out2
            let dest = endpoint(id)
            guard dest != 0 else { return }
            var out = words
            // Both outputs on one device: send real-time (clock, start, stop) once, from Out 1.
            if output == 2 && out1 == out2 {
                out = []
                var i = 0
                while i < words.count {
                    let w = words[i]
                    let n = (w >> 28) == 3 ? 2 : 1
                    let realtime = (w >> 28) == 1 && ((w >> 16) & 0xFF) >= 0xF8
                    if !realtime { out += words[i..<min(i + n, words.count)] }
                    i += n
                }
            }
            sendWords(out, to: dest)
        }
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
