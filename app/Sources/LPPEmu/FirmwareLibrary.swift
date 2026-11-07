import AppKit
import Foundation

/// Firmware the app knows about: a library folder of copies, recently opened files, and the latest CoreFW build.
///
/// Library copies live in ~/Library/Application Support/LPP MK3 Emulator/Firmware, so loading them never triggers
/// macOS's Downloads/Documents access prompt. Recents and CoreFW builds point at the original files; their details
/// (existence, date, version) are only read when the library window refreshes, never at launch.
@MainActor
final class FirmwareLibrary: ObservableObject {
    enum Source: String { case library = "Library", coreFW = "CoreFW build", recent = "Recent" }

    struct Entry: Identifiable, Hashable {
        var id: String { url.path }
        let url: URL
        let source: Source
        var name: String { url.lastPathComponent == "core" ? "core (CoreFW ELF)" : url.lastPathComponent }
        var kind: String {
            switch url.pathExtension.lowercased() {
            case "syx": return "SysEx update"
            case "bin": return "Raw image"
            default: return "ELF"
            }
        }
        var exists = true
        var modified: Date?
        var version: String?
    }

    @Published private(set) var library: [Entry] = []
    @Published private(set) var recents: [Entry] = []
    @Published private(set) var coreFW: [Entry] = []
    /// A CoreFW checkout (contains Cargo.toml). Found next to this source tree when run from it, or set by the user.
    @Published var coreFWFolder: URL? {
        didSet { UserDefaults.standard.set(coreFWFolder?.path, forKey: "coreFWFolder"); rebuildCoreFW() }
    }

    let folder: URL = {
        let base = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
        let url = base.appendingPathComponent("LPP MK3 Emulator/Firmware", isDirectory: true)
        try? FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
        return url
    }()

    private static let maxRecents = 10

    init() {
        coreFWFolder = UserDefaults.standard.string(forKey: "coreFWFolder").map { URL(fileURLWithPath: $0) }
            ?? Self.findCoreFWNextToApp()
        rebuildLibrary()
        rebuildRecents()
        rebuildCoreFW()
    }

    var all: [Entry] {
        coreFW + library + recents.filter { r in !library.contains { $0.url == r.url } && !coreFW.contains { $0.url == r.url } }
    }

    /// Recent files not already listed as a CoreFW build or a library copy (for the menu).
    var otherRecents: [Entry] { recents.filter { r in !coreFW.contains { $0.url == r.url } } }

    /// When the app runs from a checkout (app/build/… or app/.build/…), a `corefw` folder beside `app` is used.
    private static func findCoreFWNextToApp() -> URL? {
        var dir = Bundle.main.bundleURL.deletingLastPathComponent()
        for _ in 0..<6 {
            let candidate = dir.appendingPathComponent("corefw", isDirectory: true)
            if FileManager.default.fileExists(atPath: candidate.appendingPathComponent("Cargo.toml").path) {
                return candidate
            }
            dir = dir.deletingLastPathComponent()
        }
        return nil
    }

    // MARK: - Lists

    private func rebuildLibrary() {
        let fm = FileManager.default
        let files = (try? fm.contentsOfDirectory(at: folder, includingPropertiesForKeys: [.contentModificationDateKey]))
            ?? []
        library = files
            .filter { !$0.lastPathComponent.hasPrefix(".") }
            .sorted { $0.lastPathComponent.localizedStandardCompare($1.lastPathComponent) == .orderedAscending }
            .map { url in
                var e = Entry(url: url, source: .library)
                e.modified = (try? url.resourceValues(forKeys: [.contentModificationDateKey]))?.contentModificationDate
                return e
            }
    }

    private func rebuildRecents() {
        let paths = UserDefaults.standard.stringArray(forKey: "recentFirmware") ?? []
        recents = paths.map { Entry(url: URL(fileURLWithPath: $0), source: .recent) }
    }

    private func rebuildCoreFW() {
        guard let coreFWFolder else {
            coreFW = []
            return
        }
        coreFW = [
            Entry(url: coreFWFolder.appendingPathComponent("target/thumbv7em-none-eabihf/release/core"), source: .coreFW),
            Entry(url: coreFWFolder.appendingPathComponent("build/lppmk3/fw.syx"), source: .coreFW),
        ]
    }

    /// Reads existence, dates and versions of every entry. Called when the library window opens (user action).
    func refreshDetails() {
        rebuildLibrary()
        rebuildRecents()
        rebuildCoreFW()
        func fill(_ list: [Entry]) -> [Entry] {
            list.map { e in
                var e = e
                let fm = FileManager.default
                e.exists = fm.fileExists(atPath: e.url.path)
                if e.exists {
                    e.modified = (try? e.url.resourceValues(forKeys: [.contentModificationDateKey]))?.contentModificationDate
                    e.version = Self.version(of: e.url)
                }
                return e
            }
        }
        library = fill(library)
        recents = fill(recents)
        coreFW = fill(coreFW)
    }

    /// Firmware version: from the .syx header, or the 4-byte trailer of a raw image.
    private static func version(of url: URL) -> String? {
        switch url.pathExtension.lowercased() {
        case "syx":
            guard let data = try? Data(contentsOf: url), let img = try? SyxDecoder.decode(data) else { return nil }
            return Int(img.version).map(String.init) ?? img.version
        case "bin":
            guard let data = try? Data(contentsOf: url), data.count >= 8 else { return nil }
            let v = data[data.count - 8..<data.count - 4]
            return v.allSatisfy({ (0x20...0x7e).contains($0) }) ? String(decoding: v, as: UTF8.self) : nil
        default:
            return nil
        }
    }

    // MARK: - Actions

    func noteOpened(_ url: URL) {
        guard url.path.hasPrefix(folder.path) == false else { return }
        var paths = UserDefaults.standard.stringArray(forKey: "recentFirmware") ?? []
        paths.removeAll { $0 == url.path }
        paths.insert(url.path, at: 0)
        UserDefaults.standard.set(Array(paths.prefix(Self.maxRecents)), forKey: "recentFirmware")
        rebuildRecents()
    }

    func clearRecents() {
        UserDefaults.standard.removeObject(forKey: "recentFirmware")
        rebuildRecents()
    }

    /// Copies firmware files into the library folder (an ELF named "core" is renamed after its build date).
    @discardableResult
    func add(_ urls: [URL]) -> [URL] {
        let fm = FileManager.default
        var added: [URL] = []
        for url in urls {
            var name = url.lastPathComponent
            if name == "core" {
                let f = DateFormatter()
                f.dateFormat = "yyyy-MM-dd-HHmm"
                let date = (try? url.resourceValues(forKeys: [.contentModificationDateKey]))?.contentModificationDate ?? Date()
                name = "corefw-\(f.string(from: date)).elf"
            }
            let dest = folder.appendingPathComponent(name)
            try? fm.removeItem(at: dest)
            if (try? fm.copyItem(at: url, to: dest)) != nil { added.append(dest) }
        }
        rebuildLibrary()
        return added
    }

    func remove(_ entry: Entry) {
        switch entry.source {
        case .library:
            try? FileManager.default.trashItem(at: entry.url, resultingItemURL: nil)
            rebuildLibrary()
        case .recent:
            var paths = UserDefaults.standard.stringArray(forKey: "recentFirmware") ?? []
            paths.removeAll { $0 == entry.url.path }
            UserDefaults.standard.set(paths, forKey: "recentFirmware")
            rebuildRecents()
        case .coreFW:
            break
        }
    }

    func chooseCoreFWFolder() {
        let panel = NSOpenPanel()
        panel.title = "Choose the CoreFW folder"
        panel.message = "The launchpad-core-firmware checkout (it contains Cargo.toml)."
        panel.canChooseFiles = false
        panel.canChooseDirectories = true
        panel.directoryURL = coreFWFolder
        if panel.runModal() == .OK, let url = panel.url { coreFWFolder = url }
    }
}
