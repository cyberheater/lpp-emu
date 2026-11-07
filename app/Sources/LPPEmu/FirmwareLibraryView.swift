import AppKit
import SwiftUI
import UniformTypeIdentifiers

/// Firmware ▸ Firmware Library… : every firmware the app knows about, with Load / Show in Finder / Remove.
struct FirmwareLibraryView: View {
    @EnvironmentObject var library: FirmwareLibrary
    @EnvironmentObject var emu: Emulator
    @State private var selection: FirmwareLibrary.Entry.ID?
    @State private var dropTargeted = false

    private var entries: [FirmwareLibrary.Entry] { library.all }
    private var selected: FirmwareLibrary.Entry? { entries.first { $0.id == selection } }

    var body: some View {
        VStack(spacing: 0) {
            Table(entries, selection: $selection) {
                TableColumn("Name") { e in
                    HStack(spacing: 6) {
                        if e.url == emu.originalFirmwareURL || e.url == emu.firmwareURL {
                            Image(systemName: "play.fill").foregroundStyle(.green).help("Running now")
                        }
                        Text(e.name).foregroundStyle(e.exists ? .primary : .secondary)
                    }
                }
                .width(min: 180, ideal: 240)
                TableColumn("Source") { e in Text(e.source.rawValue).foregroundStyle(.secondary) }
                    .width(90)
                TableColumn("Type") { e in Text(e.kind) }
                    .width(100)
                TableColumn("Version") { e in Text(e.version ?? (e.exists ? "—" : "missing")) }
                    .width(70)
                TableColumn("Modified") { e in
                    Text(e.modified.map { $0.formatted(date: .abbreviated, time: .shortened) } ?? "")
                }
                .width(140)
                TableColumn("Location") { e in
                    Text(e.url.deletingLastPathComponent().path.replacingOccurrences(of: NSHomeDirectory(), with: "~"))
                        .foregroundStyle(.secondary).lineLimit(1).truncationMode(.middle)
                }
            }
            .contextMenu(forSelectionType: FirmwareLibrary.Entry.ID.self) { ids in
                if let e = entries.first(where: { ids.contains($0.id) }) {
                    Button("Load") { load(e) }
                    Button("Show in Finder") { NSWorkspace.shared.activateFileViewerSelecting([e.url]) }
                    if e.source != .library { Button("Copy into Library") { library.add([e.url]); library.refreshDetails() } }
                    if e.source != .coreFW { Button(e.source == .library ? "Move to Trash" : "Remove from Recent") { library.remove(e) } }
                }
            } primaryAction: { ids in
                if let e = entries.first(where: { ids.contains($0.id) }) { load(e) }
            }
            .overlay {
                if entries.isEmpty {
                    VStack(spacing: 8) {
                        Text("No firmware yet").font(.headline)
                        Text("""
                            This app does not include any firmware. Add your own:
                            • CoreFW — build it (`cargo lppmk3`) and use Firmware ▸ Set CoreFW Folder…, or add its .syx / ELF here.
                            • Novation's official Launchpad Pro MK3 firmware — use your own copy of the update file (.syx).
                            Drop files here or click Add Files….
                            """)
                            .font(.callout).foregroundStyle(.secondary).multilineTextAlignment(.leading)
                    }
                    .padding(24)
                }
                if dropTargeted {
                    RoundedRectangle(cornerRadius: 6).stroke(Color.accentColor, lineWidth: 3).padding(2)
                }
            }
            .onDrop(of: [.fileURL], isTargeted: $dropTargeted) { providers in
                for p in providers {
                    _ = p.loadObject(ofClass: URL.self) { url, _ in
                        guard let url else { return }
                        Task { @MainActor in library.add([url]); library.refreshDetails() }
                    }
                }
                return true
            }

            Divider()
            HStack {
                Button("Add Files…") { addFiles() }
                Button("Refresh") { library.refreshDetails() }
                Text("Drop .syx, .bin or ELF files here to copy them into the library.")
                    .font(.caption).foregroundStyle(.secondary)
                Spacer()
                Button("Show in Finder") { if let e = selected { NSWorkspace.shared.activateFileViewerSelecting([e.url]) } }
                    .disabled(selected == nil)
                Button("Load") { if let e = selected { load(e) } }
                    .keyboardShortcut(.defaultAction)
                    .disabled(selected?.exists != true)
            }
            .padding(10)
        }
        .frame(minWidth: 760, minHeight: 320)
        .onAppear { library.refreshDetails() }
    }

    private func load(_ e: FirmwareLibrary.Entry) {
        guard FileManager.default.fileExists(atPath: e.url.path) else { NSSound.beep(); return }
        library.noteOpened(e.url)
        emu.load(e.url)
        library.refreshDetails()
    }

    private func addFiles() {
        let panel = NSOpenPanel()
        panel.title = "Add firmware to the library"
        panel.allowsMultipleSelection = true
        panel.canChooseDirectories = false
        if panel.runModal() == .OK {
            library.add(panel.urls)
            library.refreshDetails()
        }
    }
}
