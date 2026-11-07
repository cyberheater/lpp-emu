import CoreMIDI
import Foundation
import Network
import SwiftUI

/// Owns the Renode process and the link to its M0 model (renode/LPPM0.cs); publishes LED state to the UI.
@MainActor
final class Emulator: ObservableObject {
    enum Status: Equatable {
        case stopped, starting, booting, running, failed(String)
        var text: String {
            switch self {
            case .stopped: return "Stopped"
            case .starting: return "Starting Renode…"
            case .booting: return "Booting firmware…"
            case .running: return "Running"
            case .failed(let m): return m
            }
        }
    }

    @Published private(set) var leds: [Int: RGB] = [:]
    @Published private(set) var status: Status = .stopped
    @Published private(set) var firmwareName: String = "No firmware"
    @Published private(set) var framesPerSecond = 0
    @Published private(set) var stats = M0Model.Stats()
    @Published var runMips = 216
    @Published private(set) var usb = USBMIDIBridge.Status()

    private let usbBridge = USBMIDIBridge()
    private var usbPort: UInt16 = 0
    @Published private(set) var din = DINBridge.Status()
    private let dinBridge = DINBridge()
    private var dinPort: UInt16 = 0

    private nonisolated let queue = DispatchQueue(label: "lppemu.m0")
    private var process: Process?
    private var panel: NWConnection?
    private var panelPort: UInt16 = 0
    private var monitorPort: UInt16 = 0
    private var generation = 0
    private var lastFrames = 0
    private var statsTimer: Timer?
    private(set) var firmwareURL: URL?

    let workspace: URL = {
        // No spaces: Renode's @path arguments do not accept them.
        let base = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask)[0]
        let url = base.appendingPathComponent("local.lppemu", isDirectory: true)
        try? FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
        return url
    }()

    init() {
        hardware.enabled = mirrorHardware
        hardware.onInput = { [weak self] index, down, value in
            Task { @MainActor in self?.hardwarePress(index, down: down, value: value) }
        }
        dinBridge.onOutput = { [weak self] output, words in self?.router.send(output: output, words: words) }
        router.onInput = { [weak self] bytes in self?.dinBridge.input(bytes) }
        router.onDevices = { [weak self] snap in
            guard let self else { return }
            let sel = (self.router.out1, self.router.out2, self.router.input)
            Task { @MainActor in
                self.midiDevices = snap
                // keep the menu ticks in step with re-resolved devices (without re-triggering didSet)
                if self.dinOut1Device != sel.0 { self.dinOut1Device = sel.0 }
                if self.dinOut2Device != sel.1 { self.dinOut2Device = sel.1 }
                if self.dinInDevice != sel.2 { self.dinInDevice = sel.2 }
            }
        }
        hardware.onStatus = { [weak self] s in
            Task { @MainActor in self?.hardwareStatus = s }
        }
        usbBridge.onStatus = { [weak self] s in
            Task { @MainActor in self?.usb = s }
        }
        usbBridge.onLog = { line in NSLog("LPPEmu USB: %@", line) }
        dinBridge.onStatus = { [weak self] s in
            Task { @MainActor in self?.din = s }
        }
        statsTimer = Timer.scheduledTimer(withTimeInterval: 1.0, repeats: true) { [weak self] _ in
            Task { @MainActor in self?.pollStats() }
        }
    }

    // MARK: - LEDs and input

    private var maxSeen: UInt8 = 0
    private func applyLEDs(_ changed: [Int: RGB]) {
        let before = maxSeen
        for (k, v) in changed {
            leds[k] = v
            maxSeen = max(maxSeen, v.r, v.g, v.b)
        }
        // Colour depth just switched from 7-bit to 8-bit: resend everything at the new scale.
        if before <= 127 && maxSeen > 127 {
            hardware.resetLEDs(leds, sevenBit: false)
        } else {
            hardware.setLEDs(changed, sevenBit: maxSeen <= 127)
        }
    }

    // MARK: - Real Launchpad (Programmer mode mirror)

    let hardware = HardwareMirror()
    @Published private(set) var hardwareStatus = HardwareMirror.Status()
    // MARK: - DIN jacks <-> real MIDI devices on the Mac

    let router = MIDIRouter()
    @Published private(set) var midiDevices = MIDIRouter.Snapshot()
    @Published var dinOut1Device: MIDIUniqueID = MIDIUniqueID(UserDefaults.standard.integer(forKey: "dinOut1Device")) {
        didSet { router.setOut(1, to: dinOut1Device) }
    }
    @Published var dinOut2Device: MIDIUniqueID = MIDIUniqueID(UserDefaults.standard.integer(forKey: "dinOut2Device")) {
        didSet { router.setOut(2, to: dinOut2Device) }
    }
    @Published var dinInDevice: MIDIUniqueID = MIDIUniqueID(UserDefaults.standard.integer(forKey: "dinInDevice")) {
        didSet { router.setInput(dinInDevice) }
    }

    func deviceName(_ id: MIDIUniqueID, sources: Bool = false) -> String? {
        (sources ? midiDevices.sources : midiDevices.destinations).first { $0.id == id }?.name
    }
    @Published var mirrorHardware = UserDefaults.standard.object(forKey: "mirrorHardware") as? Bool ?? true {
        didSet {
            UserDefaults.standard.set(mirrorHardware, forKey: "mirrorHardware")
            hardware.enabled = mirrorHardware
            if mirrorHardware { hardware.resetLEDs(leds, sevenBit: maxSeen <= 127) }
        }
    }

    /// Firmware colours may be 7-bit; scale them up when nothing above 127 has been seen.
    func displayColor(_ id: Int) -> Color? {
        guard let c = leds[id], Int(c.r) + Int(c.g) + Int(c.b) > 6 else { return nil }
        let k: Double = maxSeen <= 127 ? 2 : 1
        return Color(red: min(1, Double(c.r) * k / 255), green: min(1, Double(c.g) * k / 255),
                     blue: min(1, Double(c.b) * k / 255))
    }

    func press(_ id: Int, down: Bool, soft: Bool = false) {
        press(id, down: down, pressure: soft ? 0x0200 : 0x0B00)
    }

    /// From the real Launchpad: velocity / pressure 1-127 scaled to the M0's pad pressure range.
    func hardwarePress(_ id: Int, down: Bool, value: Int) {
        let p = UInt16(max(1, min(value, 127)) * Int(M0Model.maxPressure) / 127)
        press(id, down: down, pressure: max(p, 0x0100))
    }

    private func press(_ id: Int, down: Bool, pressure p: UInt16) {
        if let ctrl = M0Model.logicalToControl[id] {
            sendPanel("p \(ctrl) \(down ? Int(p) : 0)\n")
        }
        // Setup and Shift are wired straight to main-MCU GPIOs (PA2 / PA3), not through the M0.
        if id == 0 { monitor("sysbus.gpioPortA OnGPIO 2 \(down)") }
        if id == 90 { monitor("sysbus.gpioPortA OnGPIO 3 \(down)") }
    }

    private func pollStats() { sendPanel("?\n") }

    private func applyStats(_ f: [Int]) {
        guard f.count >= 6 else { return }
        let s = M0Model.Stats(frames: f[0], pings: f[1], ledCommits: f[2], overruns: f[3], unknown: f[4],
                              streaming: f[5] != 0)
        framesPerSecond = max(0, s.frames - lastFrames)
        lastFrames = s.frames
        stats = s
        if status == .booting && s.frames > 50 { status = .running }
    }

    // MARK: - Firmware

    /// Opens a firmware file. A copy is kept in the workspace so the next launch can start from it without reading
    /// the original: macOS asks again for Downloads/Documents access after every rebuild of this (ad-hoc signed) app,
    /// and that prompt would block start-up.
    func load(_ url: URL) {
        originalFirmwareURL = url
        UserDefaults.standard.set(url.path, forKey: "lastFirmwareOriginal")
        firmwareURL = cacheCopy(of: url) ?? url
        UserDefaults.standard.set(firmwareURL!.path, forKey: "lastFirmware")
        start()
    }

    /// Launch: start from the cached copy (no access prompt); falls back to the original.
    func loadCached() {
        let d = UserDefaults.standard
        if let orig = d.string(forKey: "lastFirmwareOriginal") { originalFirmwareURL = URL(fileURLWithPath: orig) }
        let cached = cacheDir.appendingPathComponent(originalFirmwareURL?.lastPathComponent ?? "")
        if originalFirmwareURL != nil, FileManager.default.fileExists(atPath: cached.path) {
            firmwareURL = cached
            start()
        } else if let last = d.string(forKey: "lastFirmware"), FileManager.default.fileExists(atPath: last) {
            load(URL(fileURLWithPath: last))
        }
    }

    /// Restart re-reads the original file, so a fresh CoreFW build is picked up.
    func restart() {
        if let orig = originalFirmwareURL, let copy = cacheCopy(of: orig) { firmwareURL = copy }
        start()
    }

    private(set) var originalFirmwareURL: URL?
    private var cacheDir: URL { workspace.appendingPathComponent("firmware-cache", isDirectory: true) }

    private func cacheCopy(of url: URL) -> URL? {
        let fm = FileManager.default
        let dest = cacheDir.appendingPathComponent(url.lastPathComponent)
        if url.standardizedFileURL == dest.standardizedFileURL { return dest }
        try? fm.createDirectory(at: cacheDir, withIntermediateDirectories: true)
        guard let data = try? Data(contentsOf: url) else { return nil }
        try? fm.removeItem(at: dest)
        return (try? data.write(to: dest)) != nil ? dest : nil
    }

    /// Writes the firmware into the workspace and returns the Renode command that loads it.
    private func stageFirmware(_ url: URL) throws -> String {
        let ext = url.pathExtension.lowercased()
        switch ext {
        case "syx":
            let img = try SyxDecoder.decode(try Data(contentsOf: url))
            let bin = workspace.appendingPathComponent("firmware.bin")
            try img.bytes.write(to: bin)
            firmwareName = "\(url.lastPathComponent) — v\(img.version)\(img.crcOK ? "" : " (CRC mismatch)")"
            return "sysbus LoadBinary @\(bin.path) 0x08010000"
        case "bin":
            let bin = workspace.appendingPathComponent("firmware.bin")
            try? FileManager.default.removeItem(at: bin)
            try FileManager.default.copyItem(at: url, to: bin)
            firmwareName = url.lastPathComponent
            return "sysbus LoadBinary @\(bin.path) 0x08010000"
        default:   // ELF (e.g. CoreFW target/thumbv7em-none-eabihf/release/core)
            let elf = workspace.appendingPathComponent("firmware.elf")
            try? FileManager.default.removeItem(at: elf)
            try FileManager.default.copyItem(at: url, to: elf)
            firmwareName = url.lastPathComponent
            return "sysbus LoadELF @\(elf.path)"
        }
    }

    // MARK: - Renode process

    private var renodeExecutable: URL? {
        let fm = FileManager.default
        var candidates: [URL] = []
        if let r = Bundle.main.resourceURL { candidates.append(r.appendingPathComponent("Renode.app/Contents/MacOS/renode")) }
        candidates.append(fm.homeDirectoryForCurrentUser.appendingPathComponent("Applications/Renode.app/Contents/MacOS/renode"))
        candidates.append(URL(fileURLWithPath: "/Applications/Renode.app/Contents/MacOS/renode"))
        return candidates.first { fm.isExecutableFile(atPath: $0.path) }
    }

    /// Directory holding lppmk3.repl, stm32f745_base.repl, STM32_TimerLP.cs and usb_stub.py.
    private var platformSource: URL? {
        let fm = FileManager.default
        var candidates: [URL] = []
        if let r = Bundle.main.resourceURL { candidates.append(r.appendingPathComponent("platform")) }
        // Running from the source tree (swift run): lpp-emu/app/.build/... -> lpp-emu/renode
        let exe = URL(fileURLWithPath: CommandLine.arguments[0]).resolvingSymlinksInPath()
        var dir = exe.deletingLastPathComponent()
        for _ in 0..<6 {
            candidates.append(dir.appendingPathComponent("renode"))
            dir = dir.deletingLastPathComponent()
        }
        return candidates.first { fm.fileExists(atPath: $0.appendingPathComponent("lppmk3.repl").path) }
    }

    /// Copies the platform files into the workspace, rewriting their absolute paths.
    private func stagePlatform() throws {
        guard let src = platformSource else { throw NSError(domain: "LPPEmu", code: 1, userInfo: [NSLocalizedDescriptionKey: "Platform files not found."]) }
        let ws = workspace.path
        for name in Self.platformFiles {
            var text = try String(contentsOf: src.appendingPathComponent(name), encoding: .utf8)
            // The repo files reference their own folder with absolute paths.
            if let r = text.range(of: #"/[^"\s]*/lpp-emu/renode/"#, options: .regularExpression) {
                let prefix = String(text[r])
                text = text.replacingOccurrences(of: prefix, with: ws + "/")
            }
            try text.write(to: workspace.appendingPathComponent(name), atomically: true, encoding: .utf8)
        }
    }

    static let platformFiles = ["lppmk3.repl", "stm32f745_base.repl", "STM32_TimerLP.cs",
                                "STM32DMA_LP.cs", "LPPM0.cs", "LPPOTGFS.cs", "LPPDIN.cs", "LPPSpiFlash.cs"]

    private static func freePort() -> UInt16 {
        let fd = socket(AF_INET, SOCK_STREAM, 0)
        defer { close(fd) }
        var addr = sockaddr_in()
        addr.sin_family = sa_family_t(AF_INET)
        addr.sin_addr.s_addr = inet_addr("127.0.0.1")
        addr.sin_port = 0
        var len = socklen_t(MemoryLayout<sockaddr_in>.size)
        _ = withUnsafeMutablePointer(to: &addr) {
            $0.withMemoryRebound(to: sockaddr.self, capacity: 1) { bind(fd, $0, len) }
        }
        _ = withUnsafeMutablePointer(to: &addr) {
            $0.withMemoryRebound(to: sockaddr.self, capacity: 1) { getsockname(fd, $0, &len) }
        }
        return UInt16(bigEndian: addr.sin_port)
    }

    func start() {
        stop()
        guard let url = firmwareURL else { status = .failed("Open a firmware file (⌘O)"); return }
        guard let renode = renodeExecutable else { status = .failed("Renode not found"); return }
        generation += 1
        let gen = generation
        status = .starting
        leds = [:]
        maxSeen = 0
        hardware.resetLEDs([:], sevenBit: true)
        lastFrames = 0
        stats = M0Model.Stats()
        do {
            try stagePlatform()
            let loadLine = try stageFirmware(url)
            panelPort = Self.freePort()
            usbPort = Self.freePort()
            dinPort = Self.freePort()
            monitorPort = Self.freePort()
            let resc = """
            include @\(workspace.path)/STM32_TimerLP.cs
            include @\(workspace.path)/STM32DMA_LP.cs
            include @\(workspace.path)/LPPM0.cs
            include @\(workspace.path)/LPPOTGFS.cs
            include @\(workspace.path)/LPPDIN.cs
            include @\(workspace.path)/LPPSpiFlash.cs
            using sysbus
            mach create "lppmk3"
            machine LoadPlatformDescription @\(workspace.path)/lppmk3.repl
            \(loadLine)
            cpu PerformanceInMips 50
            cpu VectorTableOffset 0x08010000
            cpu SP `sysbus ReadDoubleWord 0x08010000`
            cpu PC `sysbus ReadDoubleWord 0x08010004`
            m0 StreamUpMips \(max(0, runMips))
            m0 StartPanel \(panelPort)
            usbOtgFs StartBridge \(usbPort)
            din StartBridge \(dinPort)
            spi1.spiFlash UseFile @\(flashURL.path)
            logLevel 3
            start

            """
            let rescURL = workspace.appendingPathComponent("session.resc")
            try resc.write(to: rescURL, atomically: true, encoding: .utf8)

            // A Renode left behind by a crashed or force-quit app would keep running (and halve the speed).
            let reap = Process()
            reap.executableURL = URL(fileURLWithPath: "/usr/bin/pkill")
            reap.arguments = ["-9", "-f", rescURL.path]
            try? reap.run()
            reap.waitUntilExit()

            let p = Process()
            p.executableURL = renode
            p.arguments = ["--disable-gui", "-P", "\(monitorPort)", "-e", "include @\(rescURL.path)"]
            p.currentDirectoryURL = workspace
            let logURL = workspace.appendingPathComponent("renode.log")
            FileManager.default.createFile(atPath: logURL.path, contents: nil)
            let log = try FileHandle(forWritingTo: logURL)
            p.standardOutput = log
            p.standardError = log
            p.standardInput = FileHandle.nullDevice
            p.terminationHandler = { [weak self] proc in
                Task { @MainActor in
                    guard let self, self.generation == gen else { return }
                    self.status = .failed("Renode exited (\(proc.terminationStatus)) — see renode.log")
                    self.process = nil
                }
            }
            try p.run()
            process = p
            status = .booting
            connectPanel(gen: gen)
            usbBridge.connect(port: usbPort)
            dinBridge.connect(port: dinPort)
        } catch {
            status = .failed(error.localizedDescription)
        }
    }

    func stop() {
        generation += 1
        panel?.cancel()
        panel = nil
        panelSnapshot = nil
        usbBridge.disconnect()
        dinBridge.disconnect()
        if let p = process, p.isRunning {
            monitor("quit")
            let pid = p.processIdentifier
            DispatchQueue.global().asyncAfter(deadline: .now() + 3) {
                if kill(pid, 0) == 0 { kill(pid, SIGTERM) }
            }
        }
        process = nil
        if case .failed = status {} else { status = .stopped }
    }

    /// Synchronous shutdown for app termination.
    func shutdown() {
        guard let p = process, p.isRunning else { return }
        p.terminate()
        p.waitUntilExit()
    }

    var logURL: URL { workspace.appendingPathComponent("renode.log") }

    /// The emulated 16 MB SPI flash (settings, sequencer projects). Kept across runs; one file for all firmwares.
    var flashURL: URL { workspace.appendingPathComponent("flash.bin") }

    // MARK: - M0 front-panel socket (text lines, see renode/LPPM0.cs)

    private nonisolated(unsafe) var panelSnapshot: NWConnection?
    private nonisolated(unsafe) var lineBuffer = Data()     // touched only on `queue`

    private func sendPanel(_ line: String) {
        panelSnapshot?.send(content: Data(line.utf8), completion: .contentProcessed { _ in })
    }

    private func connectPanel(gen: Int) {
        guard gen == generation else { return }
        let conn = NWConnection(host: "127.0.0.1", port: NWEndpoint.Port(rawValue: panelPort)!,
                                using: {
                                    let tcp = NWProtocolTCP.Options()
                                    tcp.noDelay = true
                                    return NWParameters(tls: nil, tcp: tcp)
                                }())
        conn.stateUpdateHandler = { [weak self] state in
            switch state {
            case .ready:
                self?.receive(conn, gen: gen)
            case .waiting, .failed:
                conn.cancel()
                Task { @MainActor in
                    try? await Task.sleep(nanoseconds: 300_000_000)
                    self?.connectPanel(gen: gen)
                }
            default:
                break
            }
        }
        panel = conn
        panelSnapshot = conn
        queue.sync { lineBuffer.removeAll() }
        conn.start(queue: queue)
    }

    private nonisolated func receive(_ conn: NWConnection, gen: Int) {
        conn.receive(minimumIncompleteLength: 1, maximumLength: 65536) { [weak self] data, _, done, error in
            guard let self else { return }
            if let data, !data.isEmpty { self.handlePanelData(data) }
            if done || error != nil {
                Task { @MainActor in
                    try? await Task.sleep(nanoseconds: 300_000_000)
                    self.connectPanel(gen: gen)
                }
            } else {
                self.receive(conn, gen: gen)
            }
        }
    }

    /// Runs on `queue`: splits lines, batches LED changes, hands them to the main actor.
    private nonisolated func handlePanelData(_ data: Data) {
        lineBuffer.append(data)
        guard let last = lineBuffer.lastIndex(of: 0x0A) else { return }
        let text = String(decoding: lineBuffer[..<last], as: UTF8.self)
        lineBuffer.removeSubrange(...last)
        var changed: [Int: RGB] = [:]
        var statsLine: [Int]?
        var up = false
        for line in text.split(separator: "\n") {
            let f = line.split(separator: " ")
            guard let tag = f.first else { continue }
            switch tag {
            case "l" where f.count == 5:
                if let hw = Int(f[1]), let lg = M0Model.hwLedToLogical[hw],
                   let r = UInt8(f[2]), let g = UInt8(f[3]), let b = UInt8(f[4]) {
                    changed[lg] = RGB(r: r, g: g, b: b)
                }
            case "s":
                statsLine = f.dropFirst().compactMap { Int($0) }
            case "up":
                up = true
            default:
                break
            }
        }
        Task { @MainActor [weak self] in
            guard let self else { return }
            if !changed.isEmpty { self.applyLEDs(changed) }
            if let statsLine { self.applyStats(statsLine) }
            if up { self.status = .running }
        }
    }

    // MARK: - Renode monitor (accepts one client at a time: connect, send, close)

    func monitor(_ command: String) {
        let port = monitorPort
        guard port != 0 else { return }
        DispatchQueue.global().async {
            let fd = socket(AF_INET, SOCK_STREAM, 0)
            guard fd >= 0 else { return }
            defer { close(fd) }
            var addr = sockaddr_in()
            addr.sin_family = sa_family_t(AF_INET)
            addr.sin_addr.s_addr = inet_addr("127.0.0.1")
            addr.sin_port = port.bigEndian
            let ok = withUnsafePointer(to: &addr) {
                $0.withMemoryRebound(to: sockaddr.self, capacity: 1) {
                    connect(fd, $0, socklen_t(MemoryLayout<sockaddr_in>.size))
                }
            }
            guard ok == 0 else { return }
            var tv = timeval(tv_sec: 0, tv_usec: 300_000)
            setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &tv, socklen_t(MemoryLayout<timeval>.size))
            var sink = [UInt8](repeating: 0, count: 4096)
            _ = recv(fd, &sink, sink.count, 0)                 // banner / prompt
            let line = Array("mach set 0\n\(command)\n".utf8)
            _ = line.withUnsafeBytes { send(fd, $0.baseAddress, line.count, 0) }
            usleep(300_000)
        }
    }
}
