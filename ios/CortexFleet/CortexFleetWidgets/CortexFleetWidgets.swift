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
                             GitHubRepoSnapshot.self, DeviceSample.self,
                             Notebook.self, NotebookSource.self])
        guard let url = FileManager.default
            .containerURL(forSecurityApplicationGroupIdentifier: "group.com.leo.cortexfleet")?
            .appendingPathComponent("Jarvis.store") else { return nil }
        return try? ModelContainer(for: schema, configurations: [ModelConfiguration(schema: schema, url: url)])
    }

    @MainActor
    static func topIntel(kind: String? = nil, limit: Int = 5) -> [WidgetIntel] {
        guard let container = container() else { return [] }
        var d = FetchDescriptor<IntelItem>(sortBy: [SortDescriptor(\.score, order: .reverse)])
        d.fetchLimit = 60
        let items = (try? container.mainContext.fetch(d)) ?? []
        let filtered = kind == nil ? items : items.filter { $0.kind == kind }
        return filtered.prefix(limit).map {
            WidgetIntel(title: $0.displayTitle, source: $0.sourceName, priority: $0.priority,
                        channel: $0.channel, coverURL: $0.coverURL)
        }
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

struct WidgetIntel { let title: String; let source: String; let priority: String; var channel: String = "tech"; var coverURL: String? = nil }
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
        .configurationDisplayName("今日要闻")
        .description("Jarvis 本地信源的今日要闻，多条带图。")
        .supportedFamilies([.systemSmall, .systemMedium, .systemLarge, .accessoryRectangular])
    }
}

private func channelColor(_ id: String) -> Color {
    switch id {
    case "ai": return .indigo
    case "tech": return .cyan
    case "world": return .orange
    case "finance": return .green
    case "china": return .red
    case "engineering": return .purple
    case "science": return .teal
    case "github": return .pink
    default: return .blue
    }
}

struct IntelWidgetView: View {
    @Environment(\.widgetFamily) var family
    let entry: IntelEntry

    var body: some View {
        switch family {
        case .accessoryRectangular:
            VStack(alignment: .leading) {
                Text("今日要闻").font(.caption2.weight(.bold))
                Text(entry.items.first?.title ?? "暂无情报").font(.caption2).lineLimit(2)
            }
        case .systemSmall:
            VStack(alignment: .leading, spacing: 4) {
                Label("今日要闻", systemImage: "newspaper").font(.caption2.weight(.bold)).foregroundStyle(.tint)
                ForEach(Array(entry.items.prefix(3).enumerated()), id: \.offset) { _, item in
                    HStack(spacing: 4) {
                        Capsule().fill(channelColor(item.channel)).frame(width: 3, height: 12)
                        Text(item.title).font(.system(size: 11)).lineLimit(1)
                    }
                }
                Spacer(minLength: 0)
            }
        default:
            VStack(alignment: .leading, spacing: 8) {
                HStack {
                    Label("今日要闻", systemImage: "newspaper").font(.caption.weight(.bold)).foregroundStyle(.tint)
                    Spacer()
                    Text(entry.date, style: .time).font(.caption2).foregroundStyle(.secondary)
                }
                if entry.items.isEmpty {
                    Text("暂无情报，打开 App 扫描").font(.caption2).foregroundStyle(.secondary)
                } else {
                    ForEach(Array(entry.items.prefix(family == .systemLarge ? 5 : 3).enumerated()), id: \.offset) { _, item in
                        HStack(spacing: 8) {
                            Capsule().fill(channelColor(item.channel)).frame(width: 3)
                            VStack(alignment: .leading, spacing: 1) {
                                Text(item.title).font(.system(size: 13, weight: .medium)).lineLimit(2)
                                Text(item.source).font(.system(size: 10)).foregroundStyle(.secondary)
                            }
                            Spacer(minLength: 0)
                            if let cover = item.coverURL, let u = URL(string: cover) {
                                AsyncImage(url: u) { $0.resizable().aspectRatio(contentMode: .fill) } placeholder: { Color.gray.opacity(0.1) }
                                    .frame(width: 44, height: 44).clipShape(RoundedRectangle(cornerRadius: 6))
                            }
                        }
                        .frame(height: family == .systemLarge ? 48 : 40)
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
            DeviceWidgetView(device: entry.device)
                .containerBackground(.fill.tertiary, for: .widget)
        }
        .configurationDisplayName("本机健康")
        .description("iPhone 电量、存储、温控多维仪表。")
        .supportedFamilies([.systemSmall, .systemMedium, .accessoryCircular])
    }
}

struct DeviceWidgetView: View {
    @Environment(\.widgetFamily) var family
    let device: WidgetDevice?

    var body: some View {
        if family == .accessoryCircular {
            Gauge(value: device?.battery ?? 0) { Image(systemName: "iphone") }
                .gaugeStyle(.accessoryCircularCapacity)
        } else if family == .systemMedium {
            HStack(spacing: 14) {
                metric("电量", device?.battery.map { "\(Int($0*100))%" } ?? "-", "battery.100", .green)
                metric("存储", device.map { "\(Int($0.storageUsed))%" } ?? "-", "internaldrive", .orange)
                metric("温控", device?.thermal ?? "-", "thermometer.medium", .red)
            }
            .frame(maxWidth: .infinity)
        } else {
            VStack(alignment: .leading, spacing: 5) {
                Label("本机", systemImage: "iphone").font(.caption.weight(.bold)).foregroundStyle(.green)
                if let d = device {
                    if let b = d.battery { row("电量", "\(Int(b*100))%") }
                    row("存储", "\(Int(d.storageUsed))%")
                    row("温控", d.thermal)
                } else { Text("打开 App 采样").font(.caption2).foregroundStyle(.secondary) }
                Spacer(minLength: 0)
            }
        }
    }

    private func metric(_ t: String, _ v: String, _ icon: String, _ c: Color) -> some View {
        VStack(spacing: 3) {
            Image(systemName: icon).foregroundStyle(c)
            Text(v).font(.caption.weight(.bold))
            Text(t).font(.caption2).foregroundStyle(.secondary)
        }.frame(maxWidth: .infinity)
    }
    private func row(_ t: String, _ v: String) -> some View {
        HStack { Text(t).font(.caption2).foregroundStyle(.secondary); Spacer(); Text(v).font(.caption2.weight(.semibold)) }
    }
}
