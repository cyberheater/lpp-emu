import AppKit
import SwiftUI

/// One physical control on the Launchpad Pro MK3 surface, placed on a 10 x 11 grid.
struct Control: Identifiable {
    enum Kind { case pad, button, side, track, logo, small, setup, record }
    let id: Int            // Programmer-mode (XY) index used by CoreFW
    let col: Int, row: Int // 0-based grid position
    var rowSpan = 1
    let kind: Kind
    var label = ""
    var sub = ""
}

/// Layout copied from the hardware: top row 90-98 + logo, grid 11-88 with side columns
/// (left 80..10, right 89..19), track-select bars 101-108, bottom row 1-8, Setup.
enum Surface {
    static let controls: [Control] = {
        var c: [Control] = []
        let top: [(String, String)] = [("Shift", ""), ("◀", ""), ("▶", ""), ("Session", ""), ("Note", ""),
                                       ("Chord", ""), ("Custom", ""), ("Sequencer", ""), ("Projects", "Save")]
        for (i, t) in top.enumerated() {
            c.append(Control(id: 90 + i, col: i, row: 0, kind: i == 0 ? .small : .button, label: t.0, sub: t.1))
        }
        c.append(Control(id: 99, col: 9, row: 0, kind: .logo))
        let left: [Int: (String, String)] = [80: ("▲", ""), 70: ("▼", ""), 60: ("Clear", ""), 50: ("Duplicate", "Double"),
                                             40: ("Quantise", "Record Quantise"), 30: ("Fixed Length", ""),
                                             20: ("▷", ""), 10: ("○", "Capture MIDI")]
        let right: [Int: String] = [89: "Patterns", 79: "Steps", 69: "Pattern Settings", 59: "Velocity",
                                    49: "Probability", 39: "Mutation", 29: "Micro-Step", 19: "Print to Clip"]
        for y in stride(from: 8, through: 1, by: -1) {
            let r = 9 - y
            let l = left[y * 10]!
            c.append(Control(id: y * 10, col: 0, row: r, kind: y == 1 ? .record : .button, label: l.0, sub: l.1))
            for x in 1...8 { c.append(Control(id: y * 10 + x, col: x, row: r, kind: .pad)) }
            c.append(Control(id: y * 10 + 9, col: 9, row: r, kind: .side, label: ">", sub: right[y * 10 + 9]!))
        }
        let bottom: [(String, String)] = [("Record Arm", "Undo"), ("Mute", "Redo"), ("Solo", "Click"), ("Volume", "•"),
                                          ("Pan", "••"), ("Sends", "Tap"), ("Device", "Tempo"), ("Stop Clip", "Swing")]
        for x in 1...8 {
            c.append(Control(id: 100 + x, col: x, row: 9, kind: .track))
            c.append(Control(id: x, col: x, row: 10, kind: .button, label: bottom[x - 1].0, sub: bottom[x - 1].1))
        }
        c.append(Control(id: 0, col: 0, row: 9, rowSpan: 2, kind: .setup, label: "Setup"))
        return c
    }()

    // Proportions measured from the hardware photo.
    static let rowWeights: [CGFloat] = [0.95] + Array(repeating: 1, count: 8) + [0.42, 0.72]
    static let padding: CGFloat = 0.032
    static let gap: CGFloat = 0.011

    static func frame(for c: Control, side: CGFloat) -> CGRect {
        let pad = side * padding, g = side * gap
        let inner = side - 2 * pad
        let colW = (inner - 9 * g) / 10
        let unit = (inner - CGFloat(rowWeights.count - 1) * g) / rowWeights.reduce(0, +)
        let x = pad + CGFloat(c.col) * (colW + g)
        var y = pad
        for r in 0..<c.row { y += rowWeights[r] * unit + g }
        var h: CGFloat = 0
        for r in c.row..<(c.row + c.rowSpan) { h += rowWeights[r] * unit }
        h += CGFloat(c.rowSpan - 1) * g
        return CGRect(x: x, y: y, width: colW, height: h)
    }
}

struct PanelView: View {
    @EnvironmentObject var emu: Emulator

    var body: some View {
        GeometryReader { geo in
            let side = min(geo.size.width, geo.size.height)
            ZStack(alignment: .topLeading) {
                RoundedRectangle(cornerRadius: side * 0.022)
                    .fill(Color(white: 0.07))
                    .overlay(RoundedRectangle(cornerRadius: side * 0.022).stroke(Color(white: 0.11), lineWidth: 2))
                    .shadow(color: .black.opacity(0.6), radius: 20, y: 10)
                ForEach(Surface.controls) { c in
                    let f = Surface.frame(for: c, side: side)
                    ControlView(control: c, lit: emu.displayColor(c.id), unit: side)
                        .frame(width: f.width, height: f.height)
                        .offset(x: f.minX, y: f.minY)
                }
            }
            .frame(width: side, height: side)
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .padding(16)
        .background(Color(white: 0.02))
    }
}

/// Cuts the corner of a pad that faces the centre of the grid (the diamond on the hardware).
struct PadShape: Shape {
    var cut: UnitPoint?          // which corner to cut, e.g. .bottomTrailing
    var radius: CGFloat
    func path(in rect: CGRect) -> Path {
        guard let cut else { return RoundedRectangle(cornerRadius: radius).path(in: rect) }
        let k = rect.width * 0.22
        var p = Path()
        let pts: [CGPoint]
        switch cut {
        case .bottomTrailing:
            pts = [CGPoint(x: rect.minX, y: rect.minY), CGPoint(x: rect.maxX, y: rect.minY),
                   CGPoint(x: rect.maxX, y: rect.maxY - k), CGPoint(x: rect.maxX - k, y: rect.maxY),
                   CGPoint(x: rect.minX, y: rect.maxY)]
        case .bottomLeading:
            pts = [CGPoint(x: rect.minX, y: rect.minY), CGPoint(x: rect.maxX, y: rect.minY),
                   CGPoint(x: rect.maxX, y: rect.maxY), CGPoint(x: rect.minX + k, y: rect.maxY),
                   CGPoint(x: rect.minX, y: rect.maxY - k)]
        case .topTrailing:
            pts = [CGPoint(x: rect.minX, y: rect.minY), CGPoint(x: rect.maxX - k, y: rect.minY),
                   CGPoint(x: rect.maxX, y: rect.minY + k), CGPoint(x: rect.maxX, y: rect.maxY),
                   CGPoint(x: rect.minX, y: rect.maxY)]
        default: // topLeading
            pts = [CGPoint(x: rect.minX + k, y: rect.minY), CGPoint(x: rect.maxX, y: rect.minY),
                   CGPoint(x: rect.maxX, y: rect.maxY), CGPoint(x: rect.minX, y: rect.maxY),
                   CGPoint(x: rect.minX, y: rect.minY + k)]
        }
        p.addLines(pts)
        p.closeSubpath()
        return p
    }
}

struct ControlView: View {
    @EnvironmentObject var emu: Emulator
    let control: Control
    let lit: Color?
    let unit: CGFloat
    @State private var down = false
    @State private var latched = false

    private var cut: UnitPoint? {
        switch control.id {
        case 44: return .topTrailing      // row 4 is below the centre line
        case 45: return .topLeading
        case 54: return .bottomTrailing
        case 55: return .bottomLeading
        default: return nil
        }
    }

    var body: some View {
        content
            .scaleEffect(down || latched ? 0.96 : 1)
            .animation(.easeOut(duration: 0.04), value: down || latched)
            .contentShape(Rectangle())
            .gesture(control.kind == .logo ? nil : pressGesture)
            .help(control.label.isEmpty ? "" : control.label)
    }

    private var pressGesture: some Gesture {
        DragGesture(minimumDistance: 0)
            .onChanged { _ in
                guard !down else { return }
                down = true
                let mods = NSEvent.modifierFlags
                if mods.contains(.shift) {
                    latched.toggle()
                    emu.press(control.id, down: latched)
                } else if !latched {
                    emu.press(control.id, down: true, soft: mods.contains(.option))
                }
            }
            .onEnded { _ in
                down = false
                if !latched && !NSEvent.modifierFlags.contains(.shift) { emu.press(control.id, down: false) }
            }
    }

    @ViewBuilder private var content: some View {
        let fontSize = max(6, unit * 0.0125)
        switch control.kind {
        case .pad:
            PadShape(cut: cut, radius: unit * 0.006)
                .fill(lit ?? Color(white: 0.14))
                .overlay(PadShape(cut: cut, radius: unit * 0.006).stroke(Color.white.opacity(0.04)))
                .shadow(color: (lit ?? .clear).opacity(0.7), radius: lit == nil ? 0 : unit * 0.012)
        case .track:
            RoundedRectangle(cornerRadius: unit * 0.005)
                .fill(Color(white: 0.17))
                .overlay(
                    Capsule().fill(lit ?? Color(white: 0.8).opacity(0.55))
                        .frame(width: unit * 0.04, height: max(2, unit * 0.004))
                        .shadow(color: (lit ?? .clear), radius: lit == nil ? 0 : 4)
                )
        case .logo:
            RoundedRectangle(cornerRadius: unit * 0.006)
                .fill(lit ?? Color(white: 0.95))
                .overlay(
                    RoundedRectangle(cornerRadius: unit * 0.004).fill(Color(white: 0.07))
                        .frame(width: unit * 0.04, height: unit * 0.04)
                        .rotationEffect(.degrees(45))
                )
        default:
            ButtonFace(control: control, lit: lit, fontSize: fontSize, unit: unit)
                .scaleEffect(control.kind == .small ? 0.72 : (control.kind == .setup ? 0.78 : 1),
                             anchor: control.kind == .setup ? .bottom : .center)
        }
    }
}

struct ButtonFace: View {
    let control: Control
    let lit: Color?
    let fontSize: CGFloat
    let unit: CGFloat

    private var textColor: Color {
        guard let lit, let c = NSColor(lit).usingColorSpace(.sRGB) else { return Color(white: 0.92) }
        let lum = 0.3 * c.redComponent + 0.59 * c.greenComponent + 0.11 * c.blueComponent
        return lum > 0.67 ? Color(white: 0.07) : .white
    }

    var body: some View {
        let shape = RoundedRectangle(cornerRadius: unit * 0.006)
        ZStack {
            shape.fill(LinearGradient(colors: lit.map { [$0, $0.opacity(0.7)] } ?? [Color(white: 0.2), Color(white: 0.165)],
                                      startPoint: .top, endPoint: .bottom))
            shape.stroke(Color.black.opacity(0.4), lineWidth: 1)
            VStack(spacing: fontSize * 0.3) {
                let glyph = control.label.allSatisfy { "▲▼◀▶▷○>".contains($0) }
                Text(control.label)
                    .font(.system(size: glyph ? fontSize * (control.kind == .side ? 1.7 : 1.9) : fontSize,
                                  weight: glyph && control.kind == .side ? .light : .medium))
                    .foregroundStyle(control.kind == .record ? Color(red: 1, green: 0.3, blue: 0.3) : textColor)
                if !control.sub.isEmpty {
                    Text(control.sub)
                        .font(.system(size: fontSize * 0.78))
                        .foregroundStyle(control.kind == .record ? Color(red: 1, green: 0.42, blue: 0.42)
                                         : textColor.opacity(lit == nil ? 0.62 : 0.8))
                }
            }
            .multilineTextAlignment(.center)
            .lineLimit(2)
            .minimumScaleFactor(0.6)
            .padding(.horizontal, 2)
        }
        .shadow(color: (lit ?? .clear).opacity(0.5), radius: lit == nil ? 0 : unit * 0.008)
    }
}
