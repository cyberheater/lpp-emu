import CoreMIDI
import Foundation

/// Helpers shared by the USB and DIN bridges: MIDI 1.0 byte streams <-> UMP (MIDI 1.0 protocol) for CoreMIDI.
enum MIDIUMP {
    /// F0 ... F7 -> UMP type-3 SysEx7 packets (two words each, up to 6 data bytes).
    static func sysexToUMP(_ raw: [UInt8]) -> [UInt32] {
        var data = raw
        if data.first == 0xF0 { data.removeFirst() }
        if data.last == 0xF7 { data.removeLast() }
        var out: [UInt32] = []
        let chunks = stride(from: 0, to: max(data.count, 1), by: 6).map { Array(data[$0..<min($0 + 6, data.count)]) }
        for (i, chunk) in chunks.enumerated() {
            let st: UInt32 = chunks.count == 1 ? 0 : (i == 0 ? 1 : (i == chunks.count - 1 ? 3 : 2))
            let b = chunk + [UInt8](repeating: 0, count: 6 - chunk.count)
            out.append(0x3000_0000 | st << 20 | UInt32(chunk.count) << 16 | UInt32(b[0]) << 8 | UInt32(b[1]))
            out.append(UInt32(b[2]) << 24 | UInt32(b[3]) << 16 | UInt32(b[4]) << 8 | UInt32(b[5]))
        }
        return out
    }

    /// One complete MIDI 1.0 message (status first; SysEx as F0 ... F7) -> UMP words.
    static func words(for msg: [UInt8]) -> [UInt32] {
        guard let s = msg.first else { return [] }
        let d1 = UInt32(msg.count > 1 ? msg[1] : 0), d2 = UInt32(msg.count > 2 ? msg[2] : 0)
        switch s {
        case 0x80...0xEF: return [0x2000_0000 | UInt32(s) << 16 | d1 << 8 | d2]
        case 0xF0: return sysexToUMP(msg)
        default: return [0x1000_0000 | UInt32(s) << 16 | d1 << 8 | d2]
        }
    }

    static func emit(_ words: [UInt32], to src: MIDIEndpointRef) {
        guard !words.isEmpty else { return }
        let size = 4096
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
        MIDIReceivedEventList(src, list)
    }

    /// UMP (MIDI 1.0 protocol) -> MIDI 1.0 bytes. `sysex` carries a SysEx split across event lists.
    static func bytes(from list: UnsafePointer<MIDIEventList>, sysex: inout [UInt8]) -> [UInt8] {
        var out: [UInt8] = []
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
                    out += (s & 0xF0 == 0xC0 || s & 0xF0 == 0xD0) ? [s, d1] : [s, d1, d2]
                    i += 1
                case 0x1:
                    switch s {
                    case 0xF1, 0xF3: out += [s, d1]
                    case 0xF2: out += [s, d1, d2]
                    default: out.append(s)
                    }
                    i += 1
                case 0x3 where i + 1 < words.count:
                    let st = (w >> 20) & 0xF
                    let n = min(Int((w >> 16) & 0xF), 6)
                    let w2 = words[i + 1]
                    let data = [d1, d2, UInt8(w2 >> 24), UInt8((w2 >> 16) & 0xFF), UInt8((w2 >> 8) & 0xFF), UInt8(w2 & 0xFF)].prefix(n)
                    if st == 0 || st == 1 { sysex = [0xF0] }
                    sysex += data
                    if st == 0 || st == 3 { out += sysex + [0xF7]; sysex = [] }
                    i += 2
                default:
                    i += (mt == 0x3 || mt == 0x4) ? 2 : (mt == 0x5 ? 4 : 1)
                }
            }
        }
        return out
    }
}

/// MIDI 1.0 byte-stream parser with running status, interleaved real-time bytes and SysEx.
struct MIDIByteParser {
    private var status: UInt8 = 0
    private var data: [UInt8] = []
    private var sysex: [UInt8]?

    mutating func feed(_ b: UInt8) -> [UInt8]? {
        if b >= 0xF8 { return [b] }                           // real-time: never disturbs anything
        if b == 0xF0 { sysex = [0xF0]; status = 0; return nil }
        if b == 0xF7 {
            defer { sysex = nil }
            return sysex.map { $0 + [0xF7] }
        }
        if sysex != nil {
            if b < 0x80 { sysex!.append(b); return nil }
            sysex = nil                                       // aborted by a new status byte
        }
        if b >= 0x80 {
            status = b
            data = []
            if b == 0xF6 || b == 0xF4 || b == 0xF5 { status = 0; return b == 0xF6 ? [b] : nil }
            return nil
        }
        guard status != 0 else { return nil }                 // stray data byte
        data.append(b)
        let need: Int
        switch status {
        case 0xC0...0xDF, 0xF1, 0xF3: need = 1
        default: need = 2
        }
        guard data.count == need else { return nil }
        let msg = [status] + data
        data = []
        if status >= 0xF0 { status = 0 }                      // system common cancels running status
        return msg
    }
}
