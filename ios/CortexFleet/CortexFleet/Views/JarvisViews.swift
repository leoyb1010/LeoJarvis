import AVFoundation
import PhotosUI
import SwiftUI
import UniformTypeIdentifiers

struct JarvisHomeView: View {
    @EnvironmentObject private var store: FleetStore

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                HStack(spacing: 12) {
                    Image("LeoJarvisLogo")
                        .resizable()
                        .scaledToFill()
                        .frame(width: 52, height: 52)
                        .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
                    VStack(alignment: .leading, spacing: 3) {
                        Text("LeoJarvis")
                            .font(.title2.weight(.bold))
                        Text("个人中枢 · 设备状态 · 个人记事")
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                    }
                    Spacer()
                    if store.isLoadingJarvis {
                        ProgressView()
                    }
                }

                if let message = store.errorMessage {
                    MessageBanner(text: message, level: .bad)
                } else if let message = store.noticeMessage {
                    MessageBanner(text: message, level: .good)
                }

                LazyVGrid(columns: [GridItem(.flexible(), spacing: 8), GridItem(.flexible(), spacing: 8)], spacing: 8) {
                    CompactHomeMetric(title: "Jarvis", value: "\(Int(store.jarvisOverview.health.score.rounded()))", detail: "服务 \(store.jarvisOverview.health.servicesOnline)/\(store.jarvisOverview.health.servicesTotal)", symbol: "gauge.with.dots.needle.67percent")
                    CompactHomeMetric(title: "记事", value: "\(store.mobileNoteStats.total)", detail: "置顶 \(store.mobileNoteStats.pinned) · 重要 \(store.mobileNoteStats.favorite)", symbol: "note.text")
                    CompactHomeMetric(title: "天气", value: store.jarvisOverview.weather.temperatureText, detail: weatherDetail, symbol: "cloud.sun")
                    CompactHomeMetric(title: "日期", value: dateValue, detail: "\(weekdayText) · \(updatedText)", symbol: "calendar")
                    CompactHomeMetric(title: "主机", value: "\(store.remoteOnlineCount)/\(store.hosts.count)", detail: "\(store.activeBridgeName)", symbol: "server.rack")
                    CompactHomeMetric(title: "记忆", value: "\(store.jarvisOverview.memory.active)", detail: "待确认 \(store.jarvisOverview.memory.pending)", symbol: "brain.head.profile")
                }

                NavigationLink {
                    MobileCapabilitiesView()
                } label: {
                    HStack(spacing: 12) {
                        Image(systemName: "rectangle.stack.badge.plus")
                            .font(.title3)
                            .foregroundStyle(.tint)
                        VStack(alignment: .leading, spacing: 3) {
                            Text("Jarvis 能力")
                                .font(.headline)
                            Text("来源矩阵、设备管家、Mole/Burrow 安全预览")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        Spacer()
                        Image(systemName: "chevron.right")
                            .font(.caption.weight(.bold))
                            .foregroundStyle(.tertiary)
                    }
                    .padding(13)
                    .background(.background, in: RoundedRectangle(cornerRadius: 8, style: .continuous))
                    .overlay(
                        RoundedRectangle(cornerRadius: 8, style: .continuous)
                            .stroke(Color.blue.opacity(0.16), lineWidth: 1)
                    )
                }

                if !store.mobileBriefing.topItems.isEmpty || !store.jarvisOverview.briefing.top.isEmpty {
                    SectionHeader(title: "今日简报")
                    ForEach(Array((store.mobileBriefing.topItems.isEmpty ? store.jarvisOverview.briefing.top : store.mobileBriefing.topItems).prefix(2))) { item in
                        NavigationLink {
                            MobileBriefingDetailView(item: item)
                        } label: {
                            BriefingCompactRow(item: item)
                        }
                    }
                    .buttonStyle(.plain)
                }

                SectionHeader(title: "需要关注")
                if store.jarvisOverview.health.attentionItems.isEmpty {
                    RiskLine(risk: .init(title: "暂无风险项", advice: "Jarvis 最近一次总览没有发现重点异常。", level: .good))
                } else {
                    ForEach(store.jarvisOverview.health.attentionItems.prefix(5)) { item in
                        RiskLine(risk: .init(title: item.label, advice: item.detail, level: item.level == "异常" ? .bad : .warn))
                    }
                }

            }
            .padding(16)
        }
        .navigationTitle("总览")
        .toolbar {
            Button {
                Task { await store.refreshJarvisContent() }
            } label: {
                Image(systemName: "arrow.clockwise")
            }
            .disabled(store.isLoadingJarvis)
        }
        .refreshable {
            await store.refreshJarvisContent()
        }
        .task {
            await store.refreshJarvisContent()
        }
    }

    private var weatherDetail: String {
        let weather = store.jarvisOverview.weather
        return "\(weather.city) · \(weather.text) · \(weather.humidityText)"
    }

    private var dateValue: String {
        Date.now.formatted(.dateTime.month(.defaultDigits).day(.defaultDigits))
    }

    private var weekdayText: String {
        Date.now.formatted(.dateTime.weekday(.wide))
    }

    private var updatedText: String {
        guard store.jarvisOverview.generatedAt > 0 else { return "等待同步" }
        let date = Date(timeIntervalSince1970: TimeInterval(store.jarvisOverview.generatedAt))
        return date.formatted(.dateTime.hour().minute())
    }
}

struct MobileBriefingView: View {
    @EnvironmentObject private var store: FleetStore

    private var items: [MobileBriefingItem] {
        let rows = store.mobileBriefing.topItems
        if !rows.isEmpty { return rows }
        return store.jarvisOverview.briefing.top
    }

    var body: some View {
        List {
            Section {
                LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 8) {
                    CompactHomeMetric(title: "资讯", value: "\(store.mobileBriefing.newsItems.count)", detail: "RSS/网页/生活", symbol: "newspaper")
                    CompactHomeMetric(title: "GitHub", value: "\(store.mobileBriefing.githubItems.count)", detail: "项目雷达", symbol: "chevron.left.forwardslash.chevron.right")
                    CompactHomeMetric(title: "X", value: "\(store.mobileBriefing.xItems.count)", detail: "社媒监控", symbol: "at")
                    CompactHomeMetric(title: "邮件", value: "\(store.mobileBriefing.mailItems.count)", detail: "Apple Mail", symbol: "envelope")
                }
                .listRowInsets(EdgeInsets())
                .listRowBackground(Color.clear)
            }

            if let error = store.sectionError("briefing") {
                Section {
                    MessageBanner(text: "简报暂未同步：\(error)", level: .warn)
                        .listRowInsets(EdgeInsets())
                        .listRowBackground(Color.clear)
                }
            }

            Section("今日重点") {
                if items.isEmpty {
                    ContentUnavailableView("暂无简报", systemImage: "newspaper", description: Text("刷新后会从 Mac mini Bridge 同步今日情报简报。"))
                } else {
                    ForEach(items) { item in
                        NavigationLink {
                            MobileBriefingDetailView(item: item)
                        } label: {
                            BriefingCompactRow(item: item)
                        }
                    }
                }
            }

            if !store.mobileBriefing.newsItems.isEmpty {
                Section("资讯与情报") {
                    ForEach(store.mobileBriefing.newsItems) { item in
                        NavigationLink {
                            MobileBriefingDetailView(item: item)
                        } label: {
                            BriefingMiniRow(item: item)
                        }
                    }
                }
            }

            if !store.mobileBriefing.githubItems.isEmpty {
                Section("GitHub 项目") {
                    ForEach(store.mobileBriefing.githubItems) { item in
                        NavigationLink {
                            MobileBriefingDetailView(item: item)
                        } label: {
                            BriefingMiniRow(item: item)
                        }
                    }
                }
            }

            if !store.mobileBriefing.xItems.isEmpty {
                Section("X 监控") {
                    ForEach(store.mobileBriefing.xItems) { item in
                        NavigationLink {
                            MobileBriefingDetailView(item: item)
                        } label: {
                            BriefingMiniRow(item: item)
                        }
                    }
                }
            }

            if !store.mobileBriefing.mailItems.isEmpty {
                Section("邮件") {
                    ForEach(store.mobileBriefing.mailItems) { item in
                        NavigationLink {
                            MobileBriefingDetailView(item: item)
                        } label: {
                            BriefingMiniRow(item: item)
                        }
                    }
                }
            }
        }
        .navigationTitle("情报简报")
        .toolbar {
            Button {
                Task { await store.refreshMobileBriefing() }
            } label: {
                Image(systemName: "arrow.clockwise")
            }
            .disabled(store.isLoadingJarvis)
        }
        .refreshable {
            await store.refreshMobileBriefing()
        }
        .task {
            await store.refreshMobileBriefing()
        }
    }
}

private struct MobileBriefingDetailView: View {
    @EnvironmentObject private var store: FleetStore
    @State private var detail: MobileBriefingItem
    @State private var isLoading = false

    init(item: MobileBriefingItem) {
        _detail = State(initialValue: item)
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                HStack(spacing: 8) {
                    Text(detail.priority ?? "简报")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(priorityColor)
                        .padding(.horizontal, 9)
                        .padding(.vertical, 5)
                        .background(priorityColor.opacity(0.12), in: Capsule())
                    if let source = detail.source, !source.isEmpty {
                        Text(source)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    Spacer()
                    if isLoading {
                        ProgressView()
                    }
                }

                Text(detail.title)
                    .font(.title2.weight(.bold))
                    .textSelection(.enabled)

                DetailBlock(title: "核心摘要", text: detail.summaryText)

                if let sourceText = readableSourceText {
                    DetailBlock(title: "来源详情", text: sourceText)
                }

                if let why = detail.whyImportant, !why.isEmpty {
                    DetailBlock(title: "为什么重要", text: why)
                }

                if let relation = detail.relation, !relation.isEmpty {
                    DetailBlock(title: "和我有什么关系", text: relation)
                }

                if let next = detail.nextStep, !next.isEmpty {
                    DetailBlock(title: "下一步", text: next)
                }

                if let tags = detail.tags, !tags.isEmpty {
                    FlowTags(tags: tags)
                }

                if let url = detail.url, let link = URL(string: url) {
                    Link(destination: link) {
                        Label("打开来源", systemImage: "safari")
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.borderedProminent)
                }
            }
            .padding(16)
        }
        .navigationTitle("简报详情")
        .navigationBarTitleDisplayMode(.inline)
        .task {
            guard !isLoading else { return }
            isLoading = true
            detail = await store.loadMobileBriefingDetail(detail)
            isLoading = false
        }
    }

    private var priorityColor: Color {
        if detail.priority == "高优先" { return .red }
        if detail.priority == "中优先" { return .orange }
        return .blue
    }

    private var readableSourceText: String? {
        if let translated = detail.translatedSourceDetail {
            return translated
        }
        let candidate = detail.sourceDetail ?? detail.detail
        guard let text = candidate?.trimmingCharacters(in: .whitespacesAndNewlines), !text.isEmpty else {
            return nil
        }
        return text.containsCJK ? text : nil
    }
}

private struct DetailBlock: View {
    let title: String
    let text: String

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title)
                .font(.headline)
                .foregroundStyle(.tint)
            Text(text)
                .font(.body)
                .lineSpacing(4)
                .textSelection(.enabled)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(13)
        .background(.background, in: RoundedRectangle(cornerRadius: 8, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 8, style: .continuous)
                .stroke(Color.secondary.opacity(0.16), lineWidth: 1)
        )
    }
}

private struct BriefingMiniRow: View {
    let item: MobileBriefingItem

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text(item.priority ?? "简报")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.tint)
                Spacer()
                if let source = item.source, !source.isEmpty {
                    Text(source)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
            }
            Text(item.title)
                .font(.headline)
                .lineLimit(2)
            Text(item.summaryText)
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .lineLimit(3)
        }
        .padding(.vertical, 4)
    }
}

struct MobileNotesView: View {
    @EnvironmentObject private var store: FleetStore
    @State private var isComposerPresented = false

    var body: some View {
        List {
            Section {
                HStack(spacing: 10) {
                    MobileMetricTile(title: "全部", value: "\(store.mobileNoteStats.total)", detail: "Jarvis 记事库", symbol: "tray.full")
                    MobileMetricTile(title: "项目", value: "\(store.mobileNoteStats.projects.count)", detail: "来自 Jarvis", symbol: "folder")
                }
                .listRowInsets(EdgeInsets())
                .listRowBackground(Color.clear)
            }

            Section("最近记事") {
                if store.mobileNotes.isEmpty {
                    ContentUnavailableView("暂无记事", systemImage: "note.text", description: Text("保存新记事后会进入 Jarvis 个人记事库。"))
                } else {
                    ForEach(store.mobileNotes) { note in
                        NavigationLink {
                            MobileNoteDetailView(note: note)
                        } label: {
                            MobileNoteRow(note: note)
                        }
                    }
                }
            }

            if !store.mobileNoteStats.projects.isEmpty {
                Section("项目") {
                    ForEach(store.mobileNoteStats.projects.prefix(12)) { project in
                        HStack {
                            Label(project.name, systemImage: "folder")
                            Spacer()
                            Text("\(project.count)")
                                .foregroundStyle(.secondary)
                        }
                    }
                }
            }
        }
        .navigationTitle("记事")
        .toolbar {
            ToolbarItemGroup(placement: .primaryAction) {
                Button {
                    isComposerPresented = true
                } label: {
                    Image(systemName: "square.and.pencil")
                }
                .accessibilityLabel("新建记事")

                Button {
                    Task { await store.refreshMobileNotes() }
                } label: {
                    Image(systemName: "arrow.clockwise")
                }
                .disabled(store.isLoadingJarvis)
            }
        }
        .refreshable {
            await store.refreshMobileNotes()
        }
        .task {
            await store.refreshMobileNotes()
        }
        .sheet(isPresented: $isComposerPresented) {
            NavigationStack {
                MobileNoteComposerView()
            }
        }
    }
}

struct MobileCapabilitiesView: View {
    @EnvironmentObject private var store: FleetStore
    @State private var preview: DeviceOpsPreview?
    @State private var busyKey = ""

    struct OpsAction: Identifiable {
        let id: String
        let title: String
        let capabilityKey: String
        let symbol: String
    }

    private static let opsActions: [OpsAction] = [
        .init(id: "status", title: "系统状态", capabilityKey: "status", symbol: "gauge.with.dots.needle.50percent"),
        .init(id: "clean", title: "缓存清理", capabilityKey: "clean_preview", symbol: "sparkles"),
        .init(id: "optimize", title: "系统优化", capabilityKey: "optimize_preview", symbol: "wand.and.stars"),
        .init(id: "purge", title: "项目垃圾", capabilityKey: "purge_preview", symbol: "folder.badge.minus"),
        .init(id: "installers", title: "安装包", capabilityKey: "installer_preview", symbol: "shippingbox"),
        .init(id: "analyze", title: "磁盘地图", capabilityKey: "disk_analyze", symbol: "chart.pie"),
        .init(id: "apps", title: "应用列表", capabilityKey: "app_uninstall_list", symbol: "square.grid.2x2"),
    ]

    private var reachByID: [String: ReachChannel] {
        Dictionary(uniqueKeysWithValues: store.reachStatus.channels.map { ($0.id, $0) })
    }

    var body: some View {
        List {
            if let message = store.errorMessage {
                Section {
                    MessageBanner(text: message, level: .bad)
                        .listRowInsets(EdgeInsets())
                        .listRowBackground(Color.clear)
                }
            } else if let message = store.noticeMessage {
                Section {
                    MessageBanner(text: message, level: .good)
                        .listRowInsets(EdgeInsets())
                        .listRowBackground(Color.clear)
                }
            }

            Section {
                HStack(spacing: 10) {
                    MobileMetricTile(title: "Reach 可用", value: "\(store.reachStatus.summary.ready)", detail: "\(store.reachStatus.summary.total) 个来源", symbol: "antenna.radiowaves.left.and.right")
                    MobileMetricTile(title: "待配置", value: "\(store.reachStatus.summary.partial)", detail: "登录/Cookie/MCP", symbol: "person.badge.key")
                }
                .listRowInsets(EdgeInsets())
                .listRowBackground(Color.clear)

                HStack(spacing: 10) {
                    MobileMetricTile(title: "核心低噪", value: "\(store.reachStatus.summary.coreReady)/\(store.reachStatus.summary.coreTotal)", detail: "网页/GitHub/RSS 等", symbol: "scope")
                    MobileMetricTile(title: "设备管家", value: "\(store.deviceOpsStatus.summary.ready)/\(store.deviceOpsStatus.summary.targets)", detail: "Mole/Burrow 就绪", symbol: "wrench.and.screwdriver")
                }
                .listRowInsets(EdgeInsets())
                .listRowBackground(Color.clear)
            }

            Section("Reach 来源矩阵") {
                if store.reachStatus.sourceMatrix.isEmpty {
                    ContentUnavailableView("暂无来源矩阵", systemImage: "antenna.radiowaves.left.and.right", description: Text("刷新后会从 Jarvis Bridge 同步 Web 端的 Agent-Reach 来源矩阵。"))
                } else {
                    ForEach(store.reachStatus.sourceMatrix) { group in
                        VStack(alignment: .leading, spacing: 10) {
                            Text(group.group)
                                .font(.headline)
                            Text(group.use)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                            FlowTags(tags: group.channels.map { reachByID[$0]?.name ?? $0 })
                        }
                        .padding(.vertical, 5)
                    }
                }
            }

            Section("16 个信息来源") {
                if store.reachStatus.channels.isEmpty {
                    Text("暂无 Reach 数据")
                        .foregroundStyle(.secondary)
                } else {
                    ForEach(store.reachStatus.channels) { channel in
                        ReachChannelRow(channel: channel)
                    }
                }
            }

            Section("设备管家 / Burrow 安全预览") {
                if store.deviceOpsStatus.targets.isEmpty {
                    ContentUnavailableView("暂无设备管家数据", systemImage: "wrench.and.screwdriver", description: Text("刷新后会显示每台 Mac 的 Mole/Burrow 就绪状态。"))
                } else {
                    ForEach(store.deviceOpsStatus.targets) { target in
                        DeviceOpsTargetPanel(
                            target: target,
                            actions: Self.opsActions,
                            busyKey: busyKey,
                            onPreview: runPreview
                        )
                    }
                }
            }
        }
        .navigationTitle("能力")
        .toolbar {
            Button {
                Task { await store.refreshJarvisContent() }
            } label: {
                Image(systemName: "arrow.clockwise")
            }
            .disabled(store.isLoadingJarvis)
        }
        .refreshable {
            await store.refreshJarvisContent()
        }
        .task {
            await store.refreshJarvisContent()
        }
        .sheet(item: $preview) { result in
            NavigationStack {
                DeviceOpsPreviewDetail(preview: result)
            }
        }
    }

    private func runPreview(target: DeviceOpsTarget, action: OpsAction) {
        let key = "\(target.id)-\(action.id)"
        guard busyKey.isEmpty else { return }
        busyKey = key
        Task {
            let result = await store.previewDeviceOps(targetID: target.targetID, action: action.id)
            await MainActor.run {
                busyKey = ""
                preview = result
            }
        }
    }
}

private struct ReachChannelRow: View {
    let channel: ReachChannel

    var body: some View {
        VStack(alignment: .leading, spacing: 7) {
            HStack(alignment: .firstTextBaseline) {
                Text(channel.name)
                    .font(.headline)
                Spacer()
                Text(statusLabel)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(statusColor)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(statusColor.opacity(0.12), in: Capsule())
            }
            Text("\(channel.setupLevel ?? "Tier \(channel.tier)") · \(channel.backends.joined(separator: " / "))")
                .font(.caption)
                .foregroundStyle(.secondary)
            Text(channel.description)
                .font(.subheadline)
            Text(channel.message)
                .font(.caption)
                .foregroundStyle(.secondary)
                .lineLimit(3)
            if let example = (channel.searchExamples.first ?? channel.readExamples.first), !example.isEmpty {
                Text(example)
                    .font(.caption.monospaced())
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
                    .padding(8)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(.secondary.opacity(0.08), in: RoundedRectangle(cornerRadius: 8, style: .continuous))
            } else if let installHint = channel.installHint, !installHint.isEmpty {
                Text(installHint)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
            }
        }
        .padding(.vertical, 5)
    }

    private var statusLabel: String {
        switch channel.status {
        case "ok": return "可用"
        case "warn": return "待配置"
        default: return "未安装"
        }
    }

    private var statusColor: Color {
        switch channel.status {
        case "ok": return .green
        case "warn": return .orange
        default: return .secondary
        }
    }
}

private struct DeviceOpsTargetPanel: View {
    let target: DeviceOpsTarget
    let actions: [MobileCapabilitiesView.OpsAction]
    let busyKey: String
    let onPreview: (DeviceOpsTarget, MobileCapabilitiesView.OpsAction) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 11) {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 3) {
                    Text(target.targetName)
                        .font(.headline)
                    Text(target.kind == "local" ? "本机 · \(target.host)" : "\(target.host) · \(target.online == false ? "离线" : "SSH")")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Spacer()
                Text(target.moleInstalled ? "Mole 已就绪" : "需安装 Mole")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(target.moleInstalled ? .green : .orange)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background((target.moleInstalled ? Color.green : Color.orange).opacity(0.12), in: Capsule())
            }

            if !target.version.isEmpty || !target.moPath.isEmpty {
                Text([target.version, target.moPath].filter { !$0.isEmpty }.joined(separator: " · "))
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
            } else if !target.installHint.isEmpty {
                Text(target.installHint)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }

            LazyVGrid(columns: [GridItem(.adaptive(minimum: 112), spacing: 8)], spacing: 8) {
                ForEach(actions) { action in
                    let enabled = target.capabilities[action.capabilityKey] ?? target.moleInstalled
                    Button {
                        onPreview(target, action)
                    } label: {
                        Label(busyKey == "\(target.id)-\(action.id)" ? "读取中" : action.title, systemImage: action.symbol)
                            .font(.caption.weight(.semibold))
                            .lineLimit(1)
                            .minimumScaleFactor(0.78)
                    }
                    .buttonStyle(.bordered)
                    .disabled(!enabled || !busyKey.isEmpty)
                }
            }
        }
        .padding(.vertical, 6)
    }
}

private struct DeviceOpsPreviewDetail: View {
    @Environment(\.dismiss) private var dismiss
    let preview: DeviceOpsPreview

    var body: some View {
        List {
            Section {
                DetailRow(title: "目标", value: preview.targetID, detail: preview.ok ? "预览完成" : "预览失败")
                DetailRow(title: "动作", value: preview.action, detail: preview.safeMode ? "安全预览，不执行删除" : "")
                if let command = preview.command, !command.isEmpty {
                    DetailRow(title: "命令", value: command, detail: "")
                }
                if let gb = preview.summary?.estimatedGB {
                    DetailRow(title: "预估空间", value: String(format: "%.2f GB", gb), detail: "")
                }
                if let duration = preview.durationMS {
                    DetailRow(title: "耗时", value: "\(duration)ms", detail: "")
                }
            }

            Section("输出摘要") {
                let lines = preview.summary?.highlights ?? []
                if lines.isEmpty {
                    Text(preview.error ?? preview.installHint ?? preview.summary?.raw ?? "暂无输出")
                        .font(.body.monospaced())
                        .textSelection(.enabled)
                } else {
                    ForEach(lines, id: \.self) { line in
                        Text(line)
                            .font(.body.monospaced())
                            .textSelection(.enabled)
                    }
                }
            }
        }
        .navigationTitle("安全预览")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .confirmationAction) {
                Button("完成") { dismiss() }
            }
        }
    }
}

private struct MobileNoteComposerView: View {
    @EnvironmentObject private var store: FleetStore
    @Environment(\.dismiss) private var dismiss
    @State private var title = ""
    @State private var content = ""
    @State private var tags = ""
    @State private var project = ""
    @State private var naturalInput = ""
    @State private var mediaSelection: [PhotosPickerItem] = []
    @State private var pendingAttachments: [PendingNoteAttachment] = []
    @State private var audioRecorder: AVAudioRecorder?
    @State private var audioURL: URL?
    @State private var isRecording = false
    @State private var drafting = false
    @State private var attachmentBusy = false
    @State private var saving = false

    var body: some View {
        Form {
            Section("自然语言记录") {
                TextEditor(text: $naturalInput)
                    .frame(minHeight: 110)
                    .overlay(alignment: .topLeading) {
                        if naturalInput.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                            Text("直接说要记录什么：会议纪要、灵感、待办、生活记录、图片说明都可以。AI 会整理成标题、标签、项目和正文，保存前仍可手改。")
                                .foregroundStyle(.tertiary)
                                .padding(.top, 8)
                                .padding(.leading, 4)
                        }
                    }
                Button {
                    Task { await draftWithAI() }
                } label: {
                    Label(drafting ? "整理中" : "AI 整理成笔记", systemImage: "sparkles")
                }
                .disabled(drafting || naturalInput.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }

            Section {
                TextField("标题", text: $title)
                TextField("项目", text: $project)
                TextField("标签", text: $tags)
            }
            Section("正文") {
                TextEditor(text: $content)
                    .frame(minHeight: 180)
            }

            Section("图片 / 视频 / 录音") {
                PhotosPicker(selection: $mediaSelection, maxSelectionCount: 10, matching: .any(of: [.images, .videos])) {
                    Label("选择图片或视频", systemImage: "photo.on.rectangle.angled")
                }
                .disabled(attachmentBusy)

                Button {
                    if isRecording {
                        stopRecording()
                    } else {
                        startRecording()
                    }
                } label: {
                    Label(isRecording ? "停止录音" : "开始录音", systemImage: isRecording ? "stop.circle" : "mic.circle")
                        .foregroundStyle(isRecording ? .red : .primary)
                }

                if pendingAttachments.isEmpty {
                    Text("附件会在保存记事后上传到 Jarvis，可在 Web/Mac 端继续查看和整理。")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                } else {
                    ForEach(pendingAttachments) { attachment in
                        HStack {
                            Image(systemName: attachment.symbol)
                                .foregroundStyle(.tint)
                            VStack(alignment: .leading, spacing: 2) {
                                Text(attachment.fileName)
                                    .font(.subheadline.weight(.semibold))
                                    .lineLimit(1)
                                Text("\(attachment.mimeType) · \(ByteCountFormatter.string(fromByteCount: Int64(attachment.size), countStyle: .file))")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                            Spacer()
                            Button(role: .destructive) {
                                pendingAttachments.removeAll { $0.id == attachment.id }
                            } label: {
                                Image(systemName: "trash")
                            }
                        }
                    }
                }
            }
        }
        .navigationTitle("新建记事")
        .onChange(of: mediaSelection) { _, newItems in
            Task { await importMedia(newItems) }
        }
        .toolbar {
            ToolbarItem(placement: .cancellationAction) {
                Button("取消") { dismiss() }
            }
            ToolbarItem(placement: .confirmationAction) {
                Button(saving ? "保存中" : "保存") {
                    Task { await save() }
                }
                .disabled(saving || attachmentBusy || !canSave)
            }
        }
    }

    private func save() async {
        saving = true
        let tagRows = tags
            .split { $0 == " " || $0 == "," || $0 == "，" || $0 == "#" }
            .map { String($0).trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
        let finalContent = content.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? naturalInput : content
        let finalTitle = title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && !pendingAttachments.isEmpty ? "媒体记事" : title
        let note = await store.createMobileNote(title: finalTitle, content: finalContent, tags: tagRows, projectName: project)
        if let note {
            for attachment in pendingAttachments {
                _ = await store.uploadMobileAttachment(
                    noteID: note.id,
                    fileName: attachment.fileName,
                    mimeType: attachment.mimeType,
                    dataBase64: attachment.dataBase64
                )
            }
        }
        saving = false
        if note != nil {
            dismiss()
        }
    }

    private var canSave: Bool {
        !title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ||
        !content.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ||
        !naturalInput.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ||
        !pendingAttachments.isEmpty
    }

    private func draftWithAI() async {
        drafting = true
        if let draft = await store.draftMobileNote(prompt: naturalInput, projectName: project) {
            title = draft.title
            content = draft.content
            tags = draft.tags.joined(separator: " ")
            if !draft.projectName.isEmpty {
                project = draft.projectName
            }
        }
        drafting = false
    }

    private func importMedia(_ items: [PhotosPickerItem]) async {
        guard !items.isEmpty else { return }
        attachmentBusy = true
        defer {
            attachmentBusy = false
            mediaSelection = []
        }
        for item in items {
            guard let data = try? await item.loadTransferable(type: Data.self) else { continue }
            let type = item.supportedContentTypes.first ?? .data
            let ext = type.preferredFilenameExtension ?? "bin"
            let mime = type.preferredMIMEType ?? "application/octet-stream"
            let prefix = type.conforms(to: .movie) ? "video" : "image"
            pendingAttachments.append(PendingNoteAttachment(
                fileName: "\(prefix)-\(Int(Date().timeIntervalSince1970)).\(ext)",
                mimeType: mime,
                dataBase64: data.base64EncodedString(),
                size: data.count,
                symbol: type.conforms(to: .movie) ? "video" : "photo"
            ))
        }
    }

    private func startRecording() {
        do {
            let session = AVAudioSession.sharedInstance()
            try session.setCategory(.playAndRecord, mode: .default)
            try session.setActive(true)
            let url = FileManager.default.temporaryDirectory
                .appendingPathComponent("leojarvis-audio-\(Int(Date().timeIntervalSince1970)).m4a")
            let settings: [String: Any] = [
                AVFormatIDKey: Int(kAudioFormatMPEG4AAC),
                AVSampleRateKey: 44_100,
                AVNumberOfChannelsKey: 1,
                AVEncoderAudioQualityKey: AVAudioQuality.high.rawValue,
            ]
            let recorder = try AVAudioRecorder(url: url, settings: settings)
            recorder.record()
            audioRecorder = recorder
            audioURL = url
            isRecording = true
        } catch {
            store.errorMessage = error.localizedDescription
        }
    }

    private func stopRecording() {
        audioRecorder?.stop()
        isRecording = false
        guard let url = audioURL, let data = try? Data(contentsOf: url) else { return }
        pendingAttachments.append(PendingNoteAttachment(
            fileName: url.lastPathComponent,
            mimeType: "audio/mp4",
            dataBase64: data.base64EncodedString(),
            size: data.count,
            symbol: "waveform"
        ))
        try? FileManager.default.removeItem(at: url)
        audioRecorder = nil
        audioURL = nil
    }
}

private struct PendingNoteAttachment: Identifiable, Equatable {
    let id = UUID()
    let fileName: String
    let mimeType: String
    let dataBase64: String
    let size: Int
    let symbol: String
}

private struct MobileNoteDetailView: View {
    @EnvironmentObject private var store: FleetStore
    @State private var note: MobileNote
    @State private var title: String
    @State private var content: String
    @State private var tags: String
    @State private var project: String
    @State private var favorite: Bool
    @State private var pinned: Bool
    @State private var archived: Bool
    @State private var attachments: [MobileNoteAttachment] = []
    @State private var mode: NoteEditorMode = .preview
    @State private var isLoading = false
    @State private var isSaving = false

    init(note: MobileNote) {
        _note = State(initialValue: note)
        _title = State(initialValue: note.title)
        _content = State(initialValue: note.content)
        _tags = State(initialValue: note.tags.joined(separator: " "))
        _project = State(initialValue: note.projectName ?? "")
        _favorite = State(initialValue: note.favorite)
        _pinned = State(initialValue: note.pinned)
        _archived = State(initialValue: note.archived)
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                if isLoading {
                    ProgressView("读取完整记事")
                        .frame(maxWidth: .infinity, alignment: .center)
                }

                TextField("标题", text: $title)
                    .font(.title2.weight(.bold))
                    .textFieldStyle(.plain)
                    .textSelection(.enabled)

                HStack(spacing: 8) {
                    Toggle("置顶", isOn: $pinned)
                        .toggleStyle(.button)
                    Toggle("重要", isOn: $favorite)
                        .toggleStyle(.button)
                    Toggle("归档", isOn: $archived)
                        .toggleStyle(.button)
                }
                .font(.caption.weight(.semibold))

                VStack(alignment: .leading, spacing: 8) {
                    TextField("项目", text: $project)
                        .textFieldStyle(.roundedBorder)
                    TextField("标签，空格或 # 分隔", text: $tags)
                        .textFieldStyle(.roundedBorder)
                }

                Picker("记事模式", selection: $mode) {
                    Text("预览").tag(NoteEditorMode.preview)
                    Text("编辑").tag(NoteEditorMode.edit)
                }
                .pickerStyle(.segmented)

                if mode == .edit {
                    TextEditor(text: $content)
                        .frame(minHeight: 340)
                        .padding(8)
                        .background(.background, in: RoundedRectangle(cornerRadius: 8, style: .continuous))
                        .overlay(
                            RoundedRectangle(cornerRadius: 8, style: .continuous)
                                .stroke(Color.secondary.opacity(0.16), lineWidth: 1)
                        )
                } else {
                    MarkdownPreviewView(content: content.isEmpty ? note.displayExcerpt : content)
                }

                if !attachments.isEmpty {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("附件")
                            .font(.headline)
                        ForEach(attachments) { attachment in
                            HStack(spacing: 10) {
                                Image(systemName: attachment.isImage ? "photo" : "paperclip")
                                    .foregroundStyle(.tint)
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(attachment.fileName)
                                        .font(.subheadline.weight(.semibold))
                                        .lineLimit(1)
                                    Text("\(attachment.mimeType ?? "文件") · \(ByteCountFormatter.string(fromByteCount: Int64(attachment.size), countStyle: .file))")
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                }
                            }
                        }
                    }
                    .padding(12)
                    .background(.background, in: RoundedRectangle(cornerRadius: 8, style: .continuous))
                    .overlay(
                        RoundedRectangle(cornerRadius: 8, style: .continuous)
                            .stroke(Color.secondary.opacity(0.14), lineWidth: 1)
                    )
                }
            }
            .padding(16)
        }
        .navigationTitle("记事详情")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .confirmationAction) {
                Button(isSaving ? "保存中" : "保存") {
                    Task { await save() }
                }
                .disabled(isSaving || !canSave)
            }
        }
        .task {
            guard !isLoading else { return }
            isLoading = true
            if let detail = await store.loadMobileNoteDetail(note.id) {
                apply(detail)
            }
            isLoading = false
        }
    }

    private var canSave: Bool {
        !title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ||
        !content.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    private var parsedTags: [String] {
        tags
            .split { $0 == " " || $0 == "," || $0 == "，" || $0 == "#" }
            .map { String($0).trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
    }

    private func apply(_ detail: MobileNoteDetailPayload) {
        note = detail.note
        title = detail.note.title
        content = detail.note.content
        tags = detail.note.tags.joined(separator: " ")
        project = detail.note.projectName ?? ""
        favorite = detail.note.favorite
        pinned = detail.note.pinned
        archived = detail.note.archived
        attachments = detail.attachments
    }

    private func save() async {
        isSaving = true
        let updated = await store.updateMobileNote(
            noteID: note.id,
            title: title,
            content: content,
            tags: parsedTags,
            projectName: project,
            favorite: favorite,
            pinned: pinned,
            archived: archived
        )
        if let updated {
            note = updated
            mode = .preview
        }
        isSaving = false
    }
}

private enum NoteEditorMode: Hashable {
    case preview
    case edit
}

private struct MobileNoteRow: View {
    let note: MobileNote

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text(note.displayTitle)
                    .font(.headline)
                    .lineLimit(1)
                if note.pinned {
                    Image(systemName: "pin.fill")
                        .foregroundStyle(.tint)
                }
                if note.favorite {
                    Image(systemName: "star.fill")
                        .foregroundStyle(.yellow)
                }
                if note.sensitive {
                    Text("敏感")
                        .font(.caption2.weight(.semibold))
                        .padding(.horizontal, 7)
                        .padding(.vertical, 3)
                        .background(.orange.opacity(0.14), in: Capsule())
                        .foregroundStyle(.orange)
                }
            }
            Text(note.displayExcerpt)
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .lineLimit(2)
            HStack(spacing: 8) {
                if let project = note.projectName, !project.isEmpty {
                    Label(project, systemImage: "folder")
                }
                Text(note.tags.prefix(3).map { "#\($0)" }.joined(separator: " "))
            }
            .font(.caption)
            .foregroundStyle(.secondary)
        }
        .padding(.vertical, 4)
    }
}

private struct BriefingCompactRow: View {
    let item: MobileBriefingItem

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text(item.priority ?? "简报")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.tint)
                Spacer()
                if let score = item.score {
                    Text(String(format: "%.2f", score))
                        .font(.caption.monospacedDigit())
                        .foregroundStyle(.secondary)
                }
            }
            Text(item.title)
                .font(.headline)
            let paragraphs = readableParagraphs
            if !paragraphs.isEmpty {
                VStack(alignment: .leading, spacing: 6) {
                    ForEach(Array(paragraphs.enumerated()), id: \.offset) { _, paragraph in
                        Text(paragraph)
                            .font(.subheadline)
                            .foregroundStyle(.primary)
                            .lineLimit(6)
                            .textSelection(.enabled)
                    }
                }
            } else {
                Text("该来源没有提供可读取的正文摘录，请打开来源查看完整内容。")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }
            HStack(spacing: 8) {
                if let source = item.source, !source.isEmpty {
                    Label(source, systemImage: "newspaper")
                }
                if let next = item.nextStep, !next.isEmpty {
                    Label(next, systemImage: "arrow.right.circle")
                        .lineLimit(1)
                }
            }
            .font(.caption)
            .foregroundStyle(.secondary)
        }
        .padding(.vertical, 4)
    }

    private var readableParagraphs: [String] {
        var seen = Set<String>()
        let candidates: [String?] = [item.take, item.whyImportant, item.relation, item.nextStep, item.translatedSourceDetail]
        return candidates
            .compactMap { $0?.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { text in
                guard !text.isEmpty, !seen.contains(text) else { return false }
                seen.insert(text)
                return true
            }
            .prefix(2)
            .map { $0 }
    }
}

private struct MarkdownPreviewView: View {
    let content: String

    private var blocks: [MarkdownBlock] {
        MarkdownBlock.parse(content)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            if blocks.isEmpty {
                Text("还没有可预览的内容。")
                    .foregroundStyle(.secondary)
            } else {
                ForEach(Array(blocks.enumerated()), id: \.offset) { _, block in
                    switch block.kind {
                    case .heading1:
                        Text(inline(block.text))
                            .font(.title3.weight(.bold))
                            .textSelection(.enabled)
                    case .heading2:
                        Text(inline(block.text))
                            .font(.headline)
                            .textSelection(.enabled)
                    case .bullet:
                        HStack(alignment: .firstTextBaseline, spacing: 8) {
                            Text("•")
                                .foregroundStyle(.tint)
                            Text(inline(block.text))
                                .textSelection(.enabled)
                        }
                    case .quote:
                        Text(inline(block.text))
                            .foregroundStyle(.secondary)
                            .padding(.leading, 10)
                            .overlay(alignment: .leading) {
                                Rectangle()
                                    .fill(Color.accentColor.opacity(0.35))
                                    .frame(width: 3)
                            }
                            .textSelection(.enabled)
                    case .code:
                        Text(block.text)
                            .font(.system(.caption, design: .monospaced))
                            .textSelection(.enabled)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(10)
                            .background(Color.secondary.opacity(0.09), in: RoundedRectangle(cornerRadius: 8, style: .continuous))
                    case .paragraph:
                        Text(inline(block.text))
                            .font(.body)
                            .lineSpacing(4)
                            .textSelection(.enabled)
                    }
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(13)
        .background(.background, in: RoundedRectangle(cornerRadius: 8, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 8, style: .continuous)
                .stroke(Color.secondary.opacity(0.16), lineWidth: 1)
        )
    }

    private func inline(_ text: String) -> AttributedString {
        if let parsed = try? AttributedString(markdown: text) {
            return parsed
        }
        return AttributedString(text)
    }
}

private struct MarkdownBlock: Equatable {
    enum Kind {
        case heading1
        case heading2
        case paragraph
        case bullet
        case quote
        case code
    }

    let kind: Kind
    let text: String

    static func parse(_ content: String) -> [MarkdownBlock] {
        let lines = content.replacingOccurrences(of: "\r\n", with: "\n").split(separator: "\n", omittingEmptySubsequences: false).map(String.init)
        var out: [MarkdownBlock] = []
        var paragraph: [String] = []
        var code: [String] = []
        var inCode = false

        func flushParagraph() {
            let text = paragraph.joined(separator: "\n").trimmingCharacters(in: .whitespacesAndNewlines)
            paragraph.removeAll()
            if !text.isEmpty {
                out.append(.init(kind: .paragraph, text: text))
            }
        }

        for rawLine in lines {
            let line = rawLine.trimmingCharacters(in: .whitespaces)
            if line.hasPrefix("```") {
                if inCode {
                    out.append(.init(kind: .code, text: code.joined(separator: "\n")))
                    code.removeAll()
                    inCode = false
                } else {
                    flushParagraph()
                    inCode = true
                }
                continue
            }
            if inCode {
                code.append(rawLine)
                continue
            }
            if line.isEmpty {
                flushParagraph()
                continue
            }
            if line.hasPrefix("# ") {
                flushParagraph()
                out.append(.init(kind: .heading1, text: String(line.dropFirst(2))))
            } else if line.hasPrefix("## ") || line.hasPrefix("### ") {
                flushParagraph()
                out.append(.init(kind: .heading2, text: line.replacingOccurrences(of: #"^#{2,6}\s+"#, with: "", options: .regularExpression)))
            } else if line.hasPrefix("- ") || line.hasPrefix("* ") {
                flushParagraph()
                out.append(.init(kind: .bullet, text: String(line.dropFirst(2))))
            } else if line.hasPrefix("> ") {
                flushParagraph()
                out.append(.init(kind: .quote, text: String(line.dropFirst(2))))
            } else {
                paragraph.append(rawLine)
            }
        }
        flushParagraph()
        if !code.isEmpty {
            out.append(.init(kind: .code, text: code.joined(separator: "\n")))
        }
        return out
    }
}

private struct CompactHomeMetric: View {
    let title: String
    let value: String
    let detail: String
    let symbol: String

    var body: some View {
        HStack(spacing: 9) {
            Image(systemName: symbol)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(.tint)
                .frame(width: 24, height: 24)
                .background(Color.accentColor.opacity(0.1), in: RoundedRectangle(cornerRadius: 6, style: .continuous))
            VStack(alignment: .leading, spacing: 1) {
                HStack(alignment: .firstTextBaseline, spacing: 5) {
                    Text(value)
                        .font(.system(.headline, design: .rounded, weight: .bold))
                        .lineLimit(1)
                        .minimumScaleFactor(0.72)
                    Text(title)
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }
                Text(detail)
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
                    .lineLimit(1)
                    .minimumScaleFactor(0.78)
            }
            Spacer(minLength: 0)
        }
        .frame(maxWidth: .infinity, minHeight: 54, alignment: .leading)
        .padding(.horizontal, 10)
        .padding(.vertical, 8)
        .background(.background, in: RoundedRectangle(cornerRadius: 8, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 8, style: .continuous)
                .stroke(Color.blue.opacity(0.16), lineWidth: 1)
        )
    }
}

private struct MobileMetricTile: View {
    let title: String
    let value: String
    let detail: String
    let symbol: String

    var body: some View {
        VStack(alignment: .leading, spacing: 7) {
            Image(systemName: symbol)
                .foregroundStyle(.tint)
            Text(value)
                .font(.system(.title2, design: .rounded, weight: .bold))
            Text(title)
                .font(.caption.weight(.semibold))
                .foregroundStyle(.secondary)
            Text(detail)
                .font(.caption2)
                .foregroundStyle(.tertiary)
                .lineLimit(1)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(12)
        .background(.background, in: RoundedRectangle(cornerRadius: 8, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 8, style: .continuous)
                .stroke(Color.blue.opacity(0.18), lineWidth: 1)
        )
    }
}

private struct SectionHeader: View {
    let title: String

    var body: some View {
        Text(title)
            .font(.headline)
            .padding(.top, 4)
    }
}

private struct FlowTags: View {
    let tags: [String]

    var body: some View {
        LazyVGrid(columns: [GridItem(.adaptive(minimum: 72), spacing: 8)], alignment: .leading, spacing: 8) {
            ForEach(tags, id: \.self) { tag in
                Text("#\(tag)")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.tint)
                    .padding(.horizontal, 10)
                    .padding(.vertical, 6)
                    .background(Color.accentColor.opacity(0.12), in: Capsule())
            }
        }
    }
}

private extension String {
    var containsCJK: Bool {
        range(of: #"\p{Han}"#, options: .regularExpression) != nil
    }
}
