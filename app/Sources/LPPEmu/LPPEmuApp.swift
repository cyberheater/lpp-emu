import AppKit
import CoreMIDI
import SwiftUI
import UniformTypeIdentifiers

@main
struct LPPEmuApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) var delegate
    @StateObject private var emu = Emulator()
    @StateObject private var library = FirmwareLibrary()

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
            CommandMenu("Firmware") {
                Button("Open Firmware…") { openFirmware() }
                Button("Firmware Library…") { LibraryWindow.show(library: library, emu: emu) }
                    .keyboardShortcut("l")
                Divider()
                Section("CoreFW build") {
                    ForEach(Array(library.coreFW.enumerated()), id: \.element.id) { i, e in
                        Button(e.kind == "ELF" ? "CoreFW — latest ELF build" : "CoreFW — latest .syx") { load(e.url) }
                            .keyboardShortcut(KeyEquivalent(Character(String(i + 1))))
                    }
                    Button("Set CoreFW Folder…") { library.chooseCoreFWFolder() }
                }
                if !library.library.isEmpty {
                    Divider()
                    Section("Library") {
                        ForEach(library.library) { e in Button(e.name) { load(e.url) } }
                    }
                }
                if !library.otherRecents.isEmpty {
                    Divider()
                    Section("Recent") {
                        ForEach(library.otherRecents) { e in Button(e.name) { load(e.url) } }
                        Button("Clear Recent") { library.clearRecents() }
                    }
                }
                Divider()
                Button("Add Current Firmware to Library") {
                    if let url = emu.originalFirmwareURL ?? emu.firmwareURL { library.add([url]) }
                }
                .disabled(emu.firmwareURL == nil)
                Button("Show Library Folder in Finder") { NSWorkspace.shared.activateFileViewerSelecting([library.folder]) }
            }
            CommandMenu("Hardware") {
                Toggle("Mirror on Connected Launchpad", isOn: $emu.mirrorHardware)

                Text(emu.hardwareStatus.connected ? "Connected: \(emu.hardwareStatus.name)" : "No Launchpad Pro MK3 connected")
            }
            CommandMenu("MIDI") {
                Picker("DIN Out 1 →", selection: $emu.dinOut1Device) {
                    Text("None").tag(MIDIUniqueID(0))
                    ForEach(emu.midiDevices.destinations) { Text($0.name).tag($0.id) }
                }
                Picker("DIN Out 2 →", selection: $emu.dinOut2Device) {
                    Text("None").tag(MIDIUniqueID(0))
                    ForEach(emu.midiDevices.destinations) { Text($0.name).tag($0.id) }
                }
                Picker("DIN In ←", selection: $emu.dinInDevice) {
                    Text("None").tag(MIDIUniqueID(0))
                    Text("All MIDI inputs (omni)").tag(MIDIRouter.allInputs)
                    ForEach(emu.midiDevices.sources) { Text($0.name).tag($0.id) }
                }
                Divider()
                Text("Tip: a Launchpad running Novation firmware echoes its pads out of its own DIN jack,")
                Text("so a separate MIDI interface gives cleaner results than its \"LPProMK3 DIN\" port.")
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
        if panel.runModal() == .OK, let url = panel.url { load(url) }
    }

    /// Every firmware load goes through here so the Recent list stays current.
    private func load(_ url: URL) {
        guard FileManager.default.fileExists(atPath: url.path) else {
            let alert = NSAlert()
            alert.messageText = "Firmware not found"
            alert.informativeText = url.path + "\n\nFor CoreFW builds, run `cargo lppmk3` in the CoreFW folder first."
            alert.runModal()
            return
        }
        library.noteOpened(url)
        emu.load(url)
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
        MainActor.assumeIsolated {
            emulator?.hardware.releaseNow()   // give the real Launchpad back its normal mode
            emulator?.shutdown()
        }
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
            if emu.hardwareStatus.connected {
                Text("Hardware ✓").foregroundStyle(.green).help("Mirroring on \(emu.hardwareStatus.name)")
            }
            Text(emu.din.connected ? "DIN ✓" : "DIN —")
                .help("DIN Out 1 → \(emu.deviceName(emu.dinOut1Device) ?? "None")\nDIN Out 2 → \(emu.deviceName(emu.dinOut2Device) ?? "None")\nDIN In ← \(emu.deviceName(emu.dinInDevice, sources: true) ?? "None")\nAlso as CoreMIDI ports: LPP Emu DIN Out 1/2, DIN In")
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

/// The Firmware Library window (plain AppKit window hosting the SwiftUI view, reused while open).
@MainActor
enum LibraryWindow {
    private static var window: NSWindow?

    static func show(library: FirmwareLibrary, emu: Emulator) {
        if let w = window {
            w.makeKeyAndOrderFront(nil)
            NSApp.activate(ignoringOtherApps: true)
            return
        }
        let view = FirmwareLibraryView().environmentObject(library).environmentObject(emu)
        let w = NSWindow(contentViewController: NSHostingController(rootView: view))
        w.title = "Firmware Library"
        w.setContentSize(NSSize(width: 900, height: 420))
        w.isReleasedWhenClosed = false
        w.setFrameAutosaveName("FirmwareLibrary")
        w.center()
        window = w
        w.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }
}
