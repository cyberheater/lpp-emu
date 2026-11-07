import AppKit
import SwiftUI
import UniformTypeIdentifiers

@main
struct LPPEmuApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) var delegate
    @StateObject private var emu = Emulator()

    init() {
        // Command-line helper: LPPEmu --decode in.syx out.bin
        let args = CommandLine.arguments
        if let i = args.firstIndex(of: "--decode"), args.count > i + 2 {
            do {
                let img = try SyxDecoder.decode(try Data(contentsOf: URL(fileURLWithPath: args[i + 1])))
                try img.bytes.write(to: URL(fileURLWithPath: args[i + 2]))
                print("decoded \(img.bytes.count) bytes, version \(img.version), crc \(img.crcOK ? "OK" : "MISMATCH")")
                exit(0)
            } catch {
                print("decode failed: \(error.localizedDescription)")
                exit(1)
            }
        }
    }

    var body: some Scene {
        // WindowGroup (not Window): it always opens a window at launch, even if the last one was closed.
        WindowGroup("LPP MK3 Emulator", id: "main") {
            ContentView()
                .environmentObject(emu)
                .frame(minWidth: 520, minHeight: 580)
                .onAppear {
                    delegate.emulator = emu
                    autoload()
                }
        }
        .defaultSize(width: 860, height: 920)
        .commands {
            CommandGroup(replacing: .newItem) {
                Button("Open Firmware…") { openFirmware() }
                    .keyboardShortcut("o")
            }
            CommandMenu("Emulator") {
                Button("Restart") { emu.restart() }
                    .keyboardShortcut("r")
                Button("Stop") { emu.stop() }
                    .keyboardShortcut(".")
                Divider()
                Picker("CPU rate after boot", selection: $emu.runMips) {
                    Text("216 MIPS (216 MHz, 1 instr/cycle)").tag(216)
                    Text("462 MIPS (peak dual-issue)").tag(462)
                    Text("100 MIPS (pessimistic)").tag(100)
                }
                Divider()
                Button("Show Renode Log") { NSWorkspace.shared.open(emu.logURL) }
                Button("Show Workspace in Finder") { NSWorkspace.shared.activateFileViewerSelecting([emu.workspace]) }
            }
        }
    }

    private func openFirmware() {
        let panel = NSOpenPanel()
        panel.title = "Open Launchpad Pro MK3 firmware"
        panel.message = "Choose an ELF (e.g. CoreFW target/…/release/core), a raw .bin, or a .syx update file."
        panel.allowsMultipleSelection = false
        panel.canChooseDirectories = false
        if panel.runModal() == .OK, let url = panel.url { emu.load(url) }
    }

    /// Reopen the last firmware, or the CoreFW build next to this checkout if there is one.
    private func autoload() {
        guard emu.firmwareURL == nil else { return }
        emu.loadCached()
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    weak var emulator: Emulator?
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }
    func applicationWillTerminate(_ notification: Notification) {
        MainActor.assumeIsolated { emulator?.shutdown() }
    }
}

struct ContentView: View {
    @EnvironmentObject var emu: Emulator

    var body: some View {
        VStack(spacing: 0) {
            PanelView()
            StatusBar()
        }
        .background(Color(white: 0.02))
    }
}

struct StatusBar: View {
    @EnvironmentObject var emu: Emulator

    private var dotColor: Color {
        switch emu.status {
        case .running: return .green
        case .booting, .starting: return .yellow
        case .failed: return .red
        case .stopped: return .gray
        }
    }

    var body: some View {
        HStack(spacing: 14) {
            HStack(spacing: 6) {
                Circle().fill(dotColor).frame(width: 8, height: 8)
                Text(emu.status.text).foregroundStyle(Color(white: 0.85))
            }
            Text(emu.firmwareName).foregroundStyle(Color(white: 0.6)).lineLimit(1).truncationMode(.middle)
            Spacer()
            Text(emu.usb.configured ? "USB MIDI: \(emu.usb.ports.count) ports" : (emu.usb.connected ? "USB: enumerating…" : "USB: —"))
                .help(emu.usb.ports.joined(separator: "\n"))
            Text(emu.din.connected ? "DIN ✓" : "DIN —")
                .help("CoreMIDI: LPP Emu DIN Out 1, DIN Out 2, DIN In")
            Text("\(emu.framesPerSecond) frames/s").monospacedDigit()
            Text("LED commits \(emu.stats.ledCommits)").monospacedDigit()
            if emu.stats.overruns > 0 {
                Text("overruns \(emu.stats.overruns)").monospacedDigit()
            }
            Text("Shift-click latches · ⌥-click soft").foregroundStyle(Color(white: 0.45))
        }
        .font(.system(size: 11))
        .foregroundStyle(Color(white: 0.6))
        .padding(.horizontal, 14)
        .padding(.vertical, 7)
        .background(Color(white: 0.06))
    }
}
