// Draws the LPP MK3 Emulator app icon: a stylised Launchpad Pro MK3 showing an 8-track step sequence.
// usage: swift make_icon.swift <out.png> [size]      (default 1024; make_icns.sh renders every size)
import AppKit

let args = CommandLine.arguments
let outPath = args.count > 1 ? args[1] : "icon.png"
let px = args.count > 2 ? Int(args[2])! : 1024

func rgb(_ hex: UInt32, _ a: CGFloat = 1) -> CGColor {
    CGColor(srgbRed: CGFloat((hex >> 16) & 0xFF) / 255, green: CGFloat((hex >> 8) & 0xFF) / 255,
            blue: CGFloat(hex & 0xFF) / 255, alpha: a)
}

// Same colours as the sequencer's TRACK_COLOURS (corefw/src/app/sequencer/mod.rs).
let trackColours: [UInt32] = [0xFF3030, 0xFF8A00, 0xFFE000, 0x40FF50, 0x00E0E0, 0x2F6BFF, 0xA64BFF, 0xFF45C8]
// One row per track (top = track 1), one column per step.
let pattern: [[Int]] = [
    [1, 0, 0, 0, 1, 0, 0, 0],
    [0, 0, 1, 0, 0, 0, 1, 0],
    [1, 1, 0, 1, 1, 0, 1, 1],
    [0, 0, 0, 1, 0, 1, 0, 0],
    [1, 0, 1, 0, 0, 1, 0, 1],
    [0, 1, 0, 0, 1, 0, 0, 0],
    [0, 0, 1, 1, 0, 0, 1, 0],
    [1, 0, 0, 0, 0, 1, 1, 1],
]
let playhead = 4   // highlighted step column

let space = CGColorSpace(name: CGColorSpace.sRGB)!
let ctx = CGContext(data: nil, width: px, height: px, bitsPerComponent: 8, bytesPerRow: 0, space: space,
                    bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)!
let s = CGFloat(px) / 1024
ctx.scaleBy(x: s, y: s)
// Work in a top-left origin, 1024 x 1024 canvas.
ctx.translateBy(x: 0, y: 1024)
ctx.scaleBy(x: 1, y: -1)

func roundRect(_ r: CGRect, _ radius: CGFloat) -> CGPath {
    CGPath(roundedRect: r, cornerWidth: radius, cornerHeight: radius, transform: nil)
}

func fillGradient(_ path: CGPath, _ top: CGColor, _ bottom: CGColor, _ rect: CGRect) {
    ctx.saveGState()
    ctx.addPath(path)
    ctx.clip()
    let g = CGGradient(colorsSpace: space, colors: [top, bottom] as CFArray, locations: [0, 1])!
    ctx.drawLinearGradient(g, start: CGPoint(x: rect.midX, y: rect.minY), end: CGPoint(x: rect.midX, y: rect.maxY),
                           options: [])
    ctx.restoreGState()
}

// ---- body (macOS icon grid: 824 x 824 content inside the 1024 canvas) ----
let body = CGRect(x: 100, y: 100, width: 824, height: 824)
let bodyPath = roundRect(body, 186)
ctx.saveGState()
ctx.setShadow(offset: CGSize(width: 0, height: 14), blur: 40, color: rgb(0x000000, 0.55))
ctx.addPath(bodyPath)
ctx.setFillColor(rgb(0x1A1A1E))
ctx.fillPath()
ctx.restoreGState()
fillGradient(bodyPath, rgb(0x34343A), rgb(0x111114), body)
// bevel
ctx.addPath(roundRect(body.insetBy(dx: 3, dy: 3), 183))
ctx.setStrokeColor(rgb(0xFFFFFF, 0.10))
ctx.setLineWidth(6)
ctx.strokePath()
// recessed face
let face = body.insetBy(dx: 44, dy: 44)
let facePath = roundRect(face, 146)
fillGradient(facePath, rgb(0x0B0B0D), rgb(0x18181C), face)
ctx.addPath(facePath)
ctx.setStrokeColor(rgb(0x000000, 0.6))
ctx.setLineWidth(4)
ctx.strokePath()

// ---- layout: 10 x 10 cells (edge buttons + 8 x 8 pads) ----
let area = face.insetBy(dx: 36, dy: 36)
let cell = area.width / 10
let gap = cell * 0.14

func cellRect(_ col: Int, _ row: Int, inset: CGFloat = 0) -> CGRect {
    CGRect(x: area.minX + CGFloat(col) * cell + gap / 2 + inset,
           y: area.minY + CGFloat(row) * cell + gap / 2 + inset,
           width: cell - gap - 2 * inset, height: cell - gap - 2 * inset)
}

func pad(_ r: CGRect, colour: UInt32?, lit: CGFloat, radius: CGFloat) {
    let path = roundRect(r, radius)
    if let colour, lit > 0 {
        // glow
        ctx.saveGState()
        ctx.setShadow(offset: .zero, blur: r.width * 0.55 * lit, color: rgb(colour, 0.85 * lit))
        ctx.addPath(path)
        ctx.setFillColor(rgb(colour))
        ctx.fillPath()
        ctx.restoreGState()
        // lit face: brighter centre
        ctx.saveGState()
        ctx.addPath(path)
        ctx.clip()
        let c = CGPoint(x: r.midX, y: r.midY - r.height * 0.1)
        let g = CGGradient(colorsSpace: space, colors: [rgb(0xFFFFFF, 0.55 * lit), rgb(colour), rgb(colour)] as CFArray,
                           locations: [0, 0.45, 1])!
        ctx.drawRadialGradient(g, startCenter: c, startRadius: 0, endCenter: c, endRadius: r.width * 0.8, options: [.drawsAfterEndLocation])
        ctx.restoreGState()
    } else {
        fillGradient(path, rgb(0x34343A), rgb(0x26262B), r)
        ctx.addPath(path)
        ctx.setStrokeColor(rgb(0xFFFFFF, 0.06))
        ctx.setLineWidth(2)
        ctx.strokePath()
    }
}

// ---- 8 x 8 grid: tracks x steps ----
for row in 0..<8 {
    for col in 0..<8 {
        let r = cellRect(col + 1, row + 1)
        let on = pattern[row][col] == 1
        if col == playhead {
            // playhead column: white on hits, light grey otherwise
            if on {
                pad(r, colour: 0xFFFFFF, lit: 1.0, radius: cell * 0.16)
            } else {
                let path = roundRect(r, cell * 0.16)
                fillGradient(path, rgb(0x6E6E78), rgb(0x55555D), r)
            }
        } else {
            pad(r, colour: on ? trackColours[row] : nil, lit: on ? 0.9 : 0, radius: cell * 0.16)
        }
    }
}

// ---- edge buttons (small, like the hardware's round-cornered function buttons) ----
let small = cell * 0.17
for i in 1...8 {
    // top row: Sequencer button lit white
    pad(cellRect(i, 0, inset: small), colour: i == 7 ? 0xFFFFFF : nil, lit: i == 7 ? 0.8 : 0, radius: cell * 0.12)
    // left column: Play lit green
    pad(cellRect(0, i, inset: small), colour: i == 7 ? 0x40FF50 : nil, lit: i == 7 ? 0.8 : 0, radius: cell * 0.12)
    // right column: dim
    pad(cellRect(9, i, inset: small), colour: nil, lit: 0, radius: cell * 0.12)
    // bottom row: track colours, dimmed (track select)
    pad(cellRect(i, 9, inset: small), colour: trackColours[i - 1], lit: 0.35, radius: cell * 0.12)
}
// logo corner (top right): Novation-free white diamond
let lr = cellRect(9, 0, inset: small * 1.4)
ctx.saveGState()
ctx.translateBy(x: lr.midX, y: lr.midY)
ctx.rotate(by: .pi / 4)
ctx.addPath(roundRect(CGRect(x: -lr.width * 0.36, y: -lr.width * 0.36, width: lr.width * 0.72, height: lr.width * 0.72), 4))
ctx.setFillColor(rgb(0xF2F2F2))
ctx.fillPath()
ctx.restoreGState()

// ---- top sheen ----
ctx.saveGState()
ctx.addPath(bodyPath)
ctx.clip()
let sheen = CGGradient(colorsSpace: space, colors: [rgb(0xFFFFFF, 0.10), rgb(0xFFFFFF, 0.0)] as CFArray, locations: [0, 1])!
ctx.drawLinearGradient(sheen, start: CGPoint(x: 512, y: 100), end: CGPoint(x: 512, y: 420), options: [])
ctx.restoreGState()

let image = ctx.makeImage()!
let rep = NSBitmapImageRep(cgImage: image)
try! rep.representation(using: .png, properties: [:])!.write(to: URL(fileURLWithPath: outPath))
print("wrote \(outPath) (\(px) px)")
