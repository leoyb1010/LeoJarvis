import WidgetKit
import SwiftUI
import SwiftData

// MARK: - Widget bundle

@main
struct CortexFleetWidgetsBundle: WidgetBundle {
    var body: some Widget {
        IntelWidget()
        GitHubRadarWidget()
        DeviceHealthWidget()
        if #available(iOS 16.1, *) {
            ScanLiveActivityWidget()
        }
    }
}

// MARK: - Shared snapshot loading (reads the App Group SwiftData store)

enum WidgetData {
    static func container() -> ModelContainer? {
        let schema = Schema([Note.self, NoteAttachment.self, FeedSource.self,
                             ProfileInterest.self, IntelItem.self,
                             GitHubRepoSnapshot.self, DeviceSample.self])
        guard let url = FileManager.default
            .containerURL(forSecurityApplicationGroupIdentifier: "group.com.leo.cortexfleet")?
            .appendingPathComponent("Jarvis.store") else { return nil }
        return try? ModelContainer(for: schema, configurations: [ModelConfiguration(schema: schema, url: url)])
    }

    @MainActor
    static func topIntel(kind: String? = nil, limit: Int = 3) -> [WidgetIntel] {
        guard let container = container() else { return [] }
        var d = FetchDescriptor<IntelItem>(sortBy: [SortDescriptor(\.score, order: .reverse)])
        d.fetchLimit = 40
        let items = (try? container.mainContext.fetch(d)) ?? []
        let filtered = kind == nil ? items : items.filter { $0.kind == kind }
        return filtered.prefix(limit).map { WidgetIntel(title: $0.displayTitle, source: $0.sourceName, priority: $0.priority) }
    }

    @MainActor
    static func latestDevice() -> WidgetDevice? {
        guard let container = container() else { return nil }
        var d = FetchDescriptor<DeviceSample>(sortBy: [SortDescriptor(\.timestamp, order: .reverse)])
        d.fetchLimit = 1
        guard let s = (try? container.mainContext.fetch(d))?.first else { return nil }
        return WidgetDevice(battery: s.batteryPercent, storageUsed: s.storageUsedPercent, thermal: s.thermal)
    }
}

struct WidgetIntel { let title: String; let source: String; let priority: String }
struct WidgetDevice { let battery: Double?; let storageUsed: Double; let thermal: String }

// MARK: - Intel widget (今日重点)

struct IntelEntry: TimelineEntry { let date: Date; let items: [WidgetIntel] }

struct IntelProvider: TimelineProvider {
    func placeholder(in context: Context) -> IntelEntry {
        IntelEntry(date: Date(), items: [WidgetIntel(title: "今日重点情报", source: "Jarvis", priority: "高优先")])
    }
    func getSnapshot(in context: Context, completion: @escaping (IntelEntry) -> Void) {
        Task { @MainActor in completion(IntelEntry(date: Date(), items: WidgetData.topIntel())) }
    }
    func getTimeline(in context: Context, completion: @escaping (Timeline<IntelEntry>) -> Void) {
        Task { @MainActor in
            let entry = IntelEntry(date: Date(), items: WidgetData.topIntel())
            completion(Timeline(entries: [entry], policy: .after(Date().addingTimeInterval(3600))))
        }
    }
}

struct IntelWidget: Widget {
    var body: some WidgetConfiguration {
        StaticConfiguration(kind: "IntelWidget", provider: IntelProvider()) { entry in
            IntelWidgetView(entry: entry)
                .containerBackground(.fill.tertiary, for: .widget)
        }
        .configurationDisplayName("今日重点情报")
        .description("Jarvis 本地信源的今日高优先情报。")
        .supportedFamilies([.systemSmall, .systemMedium, .accessoryRectangular])
    }
}

struct IntelWidgetView: View {
    @Environment(\.widgetFamily) var family
    let entry: IntelEntry

    var body: some View {
        if family == .accessoryRectangular {
            VStack(alignment: .leading) {
                Text("今日重点").font(.caption2.weight(.bold))
                Text(entry.items.first?.title ?? "暂无情报").font(.caption2).lineLimit(2)
            }
        } else {
            VStack(alignment: .leading, spacing: 6) {
                Label("今日重点", systemImage: "sparkles").font(.caption.weight(.bold)).foregroundStyle(.tint)
                if entry.items.isEmpty {
                    Text("暂无情报，打开 App 扫描").font(.caption2).foregroundStyle(.secondary)
                } else {
                    ForEach(Array(entry.items.prefix(family == .systemSmall ? 2 : 3).enumerated()), id: \.offset) { _, item in
                        Text("• \(item.title)").font(.caption2).lineLimit(2)
                    }
                }
                Spacer(minLength: 0)
            }
        }
    }
}

// MARK: - GitHub radar widget

struct GitHubRadarWidget: Widget {
    var body: some WidgetConfiguration {
        StaticConfiguration(kind: "GitHubRadarWidget", provider: GitHubProvider()) { entry in
            VStack(alignment: .leading, spacing: 6) {
                Label("GitHub 雷达", systemImage: "chevron.left.forwardslash.chevron.right")
                    .font(.caption.weight(.bold)).foregroundStyle(.purple)
                if entry.items.isEmpty { Text("暂无项目").font(.caption2).foregroundStyle(.secondary) }
                else { ForEach(Array(entry.items.prefix(3).enumerated()), id: \.offset) { _, i in
                    Text("• \(i.title)").font(.caption2).lineLimit(1) } }
                Spacer(minLength: 0)
            }
            .containerBackground(.fill.tertiary, for: .widget)
        }
        .configurationDisplayName("GitHub 雷达")
        .description("涨幅最快的开源项目。")
        .supportedFamilies([.systemSmall, .systemMedium])
    }
}

struct GitHubProvider: TimelineProvider {
    func placeholder(in context: Context) -> IntelEntry { IntelEntry(date: Date(), items: []) }
    func getSnapshot(in context: Context, completion: @escaping (IntelEntry) -> Void) {
        Task { @MainActor in completion(IntelEntry(date: Date(), items: WidgetData.topIntel(kind: "github_repo"))) }
    }
    func getTimeline(in context: Context, completion: @escaping (Timeline<IntelEntry>) -> Void) {
        Task { @MainActor in
            completion(Timeline(entries: [IntelEntry(date: Date(), items: WidgetData.topIntel(kind: "github_repo"))],
                                policy: .after(Date().addingTimeInterval(3600))))
        }
    }
}

// MARK: - Device health widget

struct DeviceEntry: TimelineEntry { let date: Date; let device: WidgetDevice? }

struct DeviceProvider: TimelineProvider {
    func placeholder(in context: Context) -> DeviceEntry { DeviceEntry(date: Date(), device: nil) }
    func getSnapshot(in context: Context, completion: @escaping (DeviceEntry) -> Void) {
        Task { @MainActor in completion(DeviceEntry(date: Date(), device: WidgetData.latestDevice())) }
    }
    func getTimeline(in context: Context, completion: @escaping (Timeline<DeviceEntry>) -> Void) {
        Task { @MainActor in
            completion(Timeline(entries: [DeviceEntry(date: Date(), device: WidgetData.latestDevice())],
                                policy: .after(Date().addingTimeInterval(1800))))
        }
    }
}

struct DeviceHealthWidget: Widget {
    var body: some WidgetConfiguration {
        StaticConfiguration(kind: "DeviceHealthWidget", provider: DeviceProvider()) { entry in
            VStack(alignment: .leading, spacing: 6) {
                Label("本机", systemImage: "iphone").font(.caption.weight(.bold)).foregroundStyle(.green)
                if let d = entry.device {
                    if let b = d.battery { Text("电量 \(Int(b * 100))%").font(.caption2) }
                    Text("存储 \(Int(d.storageUsed))%").font(.caption2)
                    Text("温控 \(d.thermal)").font(.caption2).foregroundStyle(.secondary)
                } else {
                    Text("打开 App 采样").font(.caption2).foregroundStyle(.secondary)
                }
                Spacer(minLength: 0)
            }
            .containerBackground(.fill.tertiary, for: .widget)
        }
        .configurationDisplayName("本机健康")
        .description("iPhone 电量、存储与温控。")
        .supportedFamilies([.systemSmall, .accessoryCircular])
    }
}
