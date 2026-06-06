import SwiftUI

struct DeviceSummary: Decodable {
    struct Metrics: Decodable {
        let cpu_load_pct: Double?
        let ram_used_pct: Double?
        let ssd_used_pct: Double?
        let battery_percent: Double?
        let battery_plugged: Bool?
    }
    struct Services: Decodable {
        let online: Int
        let total: Int
    }
    struct Risk: Decodable, Identifiable {
        var id: String { title + advice }
        let title: String
        let advice: String
        let level: String
    }

    let device_name: String
    let model: String?
    let health: Double
    let status: String
    let metrics: Metrics
    let services: Services
    let risks: [Risk]
}

@main
struct LeoJarvisMenuBarApp: App {
    @StateObject private var model = LeoJarvisHealthModel()

    var body: some Scene {
        MenuBarExtra("LeoJarvis", systemImage: model.symbolName) {
            VStack(alignment: .leading, spacing: 12) {
                HStack {
                    VStack(alignment: .leading) {
                        Text(model.summary?.device_name ?? "LeoJarvis")
                            .font(.headline)
                        Text(model.summary?.model ?? "Local Mac")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    Spacer()
                    Text(model.healthText)
                        .font(.system(size: 28, weight: .bold, design: .rounded))
                }

                Divider()

                Grid(alignment: .leading, horizontalSpacing: 18, verticalSpacing: 8) {
                    metric("CPU", model.percent(model.summary?.metrics.cpu_load_pct))
                    metric("RAM", model.percent(model.summary?.metrics.ram_used_pct))
                    metric("SSD", model.percent(model.summary?.metrics.ssd_used_pct))
                    metric("电源", model.batteryText)
                    metric("服务", model.servicesText)
                    metric("状态", model.summary?.status ?? "未知")
                }

                if let risks = model.summary?.risks, !risks.isEmpty {
                    Divider()
                    ForEach(risks.prefix(4)) { risk in
                        VStack(alignment: .leading, spacing: 2) {
                            Text("\(risk.level) · \(risk.title)")
                                .font(.caption.weight(.semibold))
                            Text(risk.advice)
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                        }
                    }
                }

                Divider()

                HStack {
                    Button("刷新") { Task { await model.refresh() } }
                    Button("打开控制台") { model.openConsole() }
                }
            }
            .padding(14)
            .frame(width: 320)
            .task { await model.refresh() }
        }
        .menuBarExtraStyle(.window)
    }

    @GridRowBuilder
    private func metric(_ label: String, _ value: String) -> some View {
        GridRow {
            Text(label).foregroundStyle(.secondary)
            Text(value).fontWeight(.semibold)
        }
    }
}

@MainActor
final class LeoJarvisHealthModel: ObservableObject {
    @Published var summary: DeviceSummary?
    @Published var error: String?

    private let endpoint = URL(string: "http://127.0.0.1:8787/device/summary")!

    var healthText: String {
        guard let summary else { return "—" }
        return String(Int(summary.health.rounded()))
    }

    var symbolName: String {
        guard let summary else { return "waveform.path.ecg" }
        if summary.health < 65 { return "exclamationmark.triangle.fill" }
        if summary.health < 82 { return "waveform.path.ecg.rectangle" }
        return "checkmark.circle.fill"
    }

    var batteryText: String {
        guard let metrics = summary?.metrics else { return "—" }
        let pct = metrics.battery_percent.map { "\(Int($0.rounded()))%" } ?? "—"
        return metrics.battery_plugged == true ? "\(pct) 外接" : pct
    }

    var servicesText: String {
        guard let services = summary?.services else { return "—" }
        return "\(services.online)/\(services.total)"
    }

    func percent(_ value: Double?) -> String {
        guard let value else { return "—" }
        return "\(Int(value.rounded()))%"
    }

    func refresh() async {
        do {
            let (data, _) = try await URLSession.shared.data(from: endpoint)
            summary = try JSONDecoder().decode(DeviceSummary.self, from: data)
            error = nil
        } catch {
            self.error = error.localizedDescription
        }
    }

    func openConsole() {
        NSWorkspace.shared.open(URL(string: "http://127.0.0.1:8787")!)
    }
}
