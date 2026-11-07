import Foundation

/// Decodes a Novation Launchpad Pro MK3 firmware update (.syx) into the raw application image.
///
/// Format (verified on stock 4.40 and CoreFW builds):
///   F0 00 20 29 00 <cmd> ... F7
///   71 = start header, 7C = version + nibble-coded size + CRC, 72 = data block, 73 = block 0 (sent last)
///   Data block: 37 septets -> big-endian 259-bit integer >> 3 -> 32 bytes.
///   Header CRC: CRC-32/MPEG-2 over the whole image.
enum SyxDecoder {
    struct Image {
        var bytes: Data
        var version: String
        var crcOK: Bool
    }

    enum DecodeError: LocalizedError {
        case notSysex, noData, badBlock(Int)
        var errorDescription: String? {
            switch self {
            case .notSysex: return "Not a Novation SysEx firmware file."
            case .noData: return "The file contains no firmware data blocks."
            case .badBlock(let i): return "Malformed firmware block \(i)."
            }
        }
    }

    static func decode(_ file: Data) throws -> Image {
        let d = [UInt8](file)
        var msgs: [ArraySlice<UInt8>] = []
        var i = 0
        while i < d.count {
            guard d[i] == 0xF0, let j = d[i...].firstIndex(of: 0xF7) else { throw DecodeError.notSysex }
            msgs.append(d[(i + 1)..<j])
            i = j + 1
        }
        let header: [UInt8] = [0x00, 0x20, 0x29, 0x00]
        guard !msgs.isEmpty, msgs.allSatisfy({ Array($0.prefix(4)) == header }) else { throw DecodeError.notSysex }

        var blocks: [Data] = []
        var block0: Data?
        var version = "?"
        var sizeField = 0, crcField: UInt32 = 0
        for (n, m) in msgs.enumerated() {
            let cmd = m[m.startIndex + 4]
            let payload = Array(m.dropFirst(5))
            switch cmd {
            case 0x72, 0x73:
                guard payload.count == 37 else { throw DecodeError.badBlock(n) }
                let b = unpack37(payload)
                if cmd == 0x73 { block0 = b } else { blocks.append(b) }
            case 0x7C where payload.count >= 23:
                version = String(bytes: payload[1..<7], encoding: .ascii) ?? "?"
                sizeField = payload[7..<15].reduce(0) { $0 << 4 | Int($1 & 0xF) }
                crcField = payload[15..<23].reduce(UInt32(0)) { $0 << 4 | UInt32($1 & 0xF) }
            default:
                break
            }
        }
        guard !blocks.isEmpty else { throw DecodeError.noData }
        var image = Data()
        if let b0 = block0 { image.append(b0) }
        for b in blocks { image.append(b) }
        if sizeField > 0 && image.count > sizeField { image = image.prefix(sizeField) }
        return Image(bytes: image, version: version, crcOK: crc32mpeg2(image) == crcField)
    }

    /// 37 septets, MSB-first, top 256 of 259 bits.
    static func unpack37(_ s: [UInt8]) -> Data {
        var out = [UInt8](repeating: 0, count: 32)
        var acc: UInt64 = 0, nbits = 0, o = 0
        for septet in s {
            acc = (acc << 7) | UInt64(septet & 0x7F); nbits += 7
            while nbits >= 8 && o < 32 {
                nbits -= 8
                out[o] = UInt8((acc >> UInt64(nbits)) & 0xFF); o += 1
            }
            acc &= (1 << UInt64(nbits)) - 1
        }
        return Data(out)
    }

    static func crc32mpeg2(_ data: Data) -> UInt32 {
        var table = [UInt32](repeating: 0, count: 256)
        for i in 0..<256 {
            var c = UInt32(i) << 24
            for _ in 0..<8 { c = (c & 0x8000_0000) != 0 ? (c << 1) ^ 0x04C1_1DB7 : c << 1 }
            table[i] = c
        }
        var crc: UInt32 = 0xFFFF_FFFF
        for b in data { crc = (crc << 8) ^ table[Int(((crc >> 24) ^ UInt32(b)) & 0xFF)] }
        return crc
    }
}
