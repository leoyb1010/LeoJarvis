import SwiftUI

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

                HStack(spacing: 10) {
                    MobileMetricTile(title: "Jarvis 健康", value: "\(Int(store.jarvisOverview.health.score.rounded()))", detail: "服务 \(store.jarvisOverview.health.servicesOnline)/\(store.jarvisOverview.health.servicesTotal)", symbol: "gauge.with.dots.needle.67percent")
                    MobileMetricTile(title: "记事", value: "\(store.mobileNoteStats.total)", detail: "置顶 \(store.mobileNoteStats.pinned) · 重要 \(store.mobileNoteStats.favorite)", symbol: "note.text")
                }

                HStack(spacing: 10) {
                    MobileMetricTile(title: "天气", value: store.jarvisOverview.weather.temperatureText, detail: weatherDetail, symbol: "cloud.sun")
                    MobileMetricTile(title: "日期", value: dateValue, detail: "\(weekdayText) · 更新 \(updatedText)", symbol: "calendar")
                }

                HStack(spacing: 10) {
                    MobileMetricTile(title: "三台主机", value: "\(store.remoteOnlineCount)/\(store.hosts.count)", detail: "\(store.activeBridgeName) 探测", symbol: "server.rack")
                    MobileMetricTile(title: "记忆", value: "\(store.jarvisOverview.memory.active)", detail: "待确认 \(store.jarvisOverview.memory.pending)", symbol: "brain.head.profile")
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
    @State private var saving = false

    var body: some View {
        Form {
            Section {
                TextField("标题", text: $title)
                TextField("项目", text: $project)
                TextField("标签", text: $tags)
            }
            Section("正文") {
                TextEditor(text: $content)
                    .frame(minHeight: 180)
            }
        }
        .navigationTitle("新建记事")
        .toolbar {
            ToolbarItem(placement: .cancellationAction) {
                Button("取消") { dismiss() }
            }
            ToolbarItem(placement: .confirmationAction) {
                Button(saving ? "保存中" : "保存") {
                    Task { await save() }
                }
                .disabled(saving || (title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && content.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty))
            }
        }
    }

    private func save() async {
        saving = true
        let tagRows = tags
            .split { $0 == " " || $0 == "," || $0 == "，" || $0 == "#" }
            .map { String($0).trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
        let ok = await store.createMobileNote(title: title, content: content, tags: tagRows, projectName: project)
        saving = false
        if ok {
            dismiss()
        }
    }
}

private struct MobileNoteDetailView: View {
    let note: MobileNote

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                Text(note.displayTitle)
                    .font(.title.weight(.bold))
                if let project = note.projectName, !project.isEmpty {
                    Label(project, systemImage: "folder")
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(.secondary)
                }
                if !note.tags.isEmpty {
                    FlowTags(tags: note.tags)
                }
                Text(note.content.isEmpty ? note.displayExcerpt : note.content)
                    .font(.body)
                    .lineSpacing(4)
                    .textSelection(.enabled)
            }
            .padding(16)
        }
        .navigationTitle("记事详情")
        .navigationBarTitleDisplayMode(.inline)
    }
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
        return [item.sourceDetail, item.detail]
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
