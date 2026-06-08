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
                        Text("个人中枢 · 设备状态 · 简报记忆")
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
                    MobileMetricTile(title: "简报", value: "\(store.jarvisOverview.briefing.business + store.jarvisOverview.briefing.life)", detail: "业务 \(store.jarvisOverview.briefing.business) · 生活 \(store.jarvisOverview.briefing.life)", symbol: "newspaper")
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

                SectionHeader(title: "近期动态")
                if store.jarvisOverview.timeline.isEmpty {
                    Text("暂无近期动态")
                        .foregroundStyle(.secondary)
                } else {
                    ForEach(store.jarvisOverview.timeline.prefix(6)) { item in
                        BriefingCompactRow(item: item)
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

struct MobileBriefingView: View {
    @EnvironmentObject private var store: FleetStore

    var body: some View {
        List {
            Section {
                HStack(spacing: 10) {
                    MobileMetricTile(title: "业务", value: "\(store.mobileBriefing.business.count)", detail: "今日简报", symbol: "briefcase")
                    MobileMetricTile(title: "生活", value: "\(store.mobileBriefing.life.count)", detail: "今日简报", symbol: "person.crop.circle")
                }
                .listRowInsets(EdgeInsets())
                .listRowBackground(Color.clear)
            }

            Section("重点") {
                if store.mobileBriefing.topItems.isEmpty {
                    Text("暂无简报内容")
                        .foregroundStyle(.secondary)
                } else {
                    ForEach(store.mobileBriefing.topItems) { item in
                        BriefingCompactRow(item: item)
                    }
                }
            }
        }
        .navigationTitle("简报")
        .toolbar {
            Button {
                Task { await store.refreshJarvisContent() }
            } label: {
                Image(systemName: "arrow.clockwise")
            }
        }
        .refreshable {
            await store.refreshJarvisContent()
        }
        .task {
            await store.refreshJarvisContent()
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
        VStack(alignment: .leading, spacing: 7) {
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
            if let take = item.take, !take.isEmpty {
                Text(take)
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .lineLimit(3)
            }
            if let next = item.nextStep, !next.isEmpty {
                Label(next, systemImage: "arrow.right.circle")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
            }
        }
        .padding(.vertical, 4)
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
