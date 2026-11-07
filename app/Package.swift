// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "LPPEmu",
    platforms: [.macOS(.v14)],
    targets: [
        .executableTarget(name: "LPPEmu", path: "Sources/LPPEmu")
    ]
)
