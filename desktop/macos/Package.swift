// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "LeoJarvisDesktop",
    platforms: [.macOS(.v13)],
    products: [
        .executable(name: "LeoJarvisDesktop", targets: ["LeoJarvisDesktop"]),
    ],
    targets: [
        .executableTarget(
            name: "LeoJarvisDesktop",
            path: "Sources/LeoJarvisDesktop"
        ),
    ],
    swiftLanguageVersions: [.v5]
)
