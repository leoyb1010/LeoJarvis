import SwiftUI
import SwiftData

/// Settings (第五页), reorganized: 信源状态 + AI 录入接口 at the top; the legacy
/// bridge / SSH / probe controls are sunk into a collapsible "高级 / 远端" section.
struct SettingsView: View {
    @EnvironmentObject private var store: FleetStore
    @EnvironmentObject private var env: AppEnvironment
    @EnvironmentObject private var llmConfig: LLMConfigStore
    @Environment(\.modelContext) private var context

    @Query private var feeds: [FeedSource]
    @Query private var interests: [ProfileInterest]

    @State private var editor: HostEditorState?
    @State private var isBridgeSheetPresented = false
    @State private var isSharedPasswordSheetPresented = false
    @State private var isLLMSheetPresented = false
    @State private var isSourcesSheetPresented = false
    @State private var importer: BridgeImporter?
    @State private var importMessage: String?

    var body: some View {
        List {
            // 1) 信源状态
            Section {
                NavigationLink {
                    SourcesManagerView()
                } label: {
                    statusRow(title: "信源状态", systemImage: "antenna.radiowaves.left.and.right",
                              value: "\(feeds.filter(\.enabled).count) 个源 · \(interests.count) 关注项",
                              detail: lastScanText, tint: .blue)
                }
            } header: { Text("信源") }

            // 2) AI 录入接口
            Section {
                Button { isLLMSheetPresented = true } label: {
                    statusRow(title: "AI 录入接口", systemImage: "brain.head.profile",
                              value: "\(llmConfig.settings.engineLabel) · \(llmConfig.settings.model)",
                              detail: llmConfig.hasKey ? "API Key 已保存" : "未配置 API Key",
                              tint: llmConfig.hasKey ? .green : .orange)
                }
            } header: { Text("AI 助手") } footer: {
                Text("Jarvis 对话、简报生成、英文翻译都走这个 OpenAI 兼容接口；Key 只保存在本机 Keychain。")
            }

            if let importMessage {
                Section { MessageBanner(text: importMessage, level: .good).listRowInsets(EdgeInsets()).listRowBackground(Color.clear) }
            }

            // 3) 高级 / 远端（下沉）
            Section {
                Button {
                    Task { await runImport() }
                } label: {
                    Label(importer?.isImporting == true ? "导入中…" : "从 Bridge 导入历史记事", systemImage: "square.and.arrow.down.on.square")
                }
                .disabled(importer?.isImporting == true)

                Button { isBridgeSheetPresented = true } label: {
                    Label("Bridge 设置", systemImage: "server.rack")
                }
                Button { editor = HostEditorState(draft: HostDraft()) } label: {
                    Label("添加直连 SSH 主机", systemImage: "plus.circle")
                }
                Button { isSharedPasswordSheetPresented = true } label: {
                    Label("SSH 共用密码", systemImage: "key.fill")
                }.disabled(store.hosts.isEmpty)
            } header: {
                Text("高级 / 远端（可选）")
            } footer: {
                Text("iPhone 已完全独立运行，以下为可选的远端能力：一次性导入旧 Bridge 记事、直连 SSH 查看 Mac 状态。")
            }

            if !store.hosts.isEmpty {
                Section("SSH 主机 \(store.hosts.count)") {
                    ForEach(store.hosts) { host in
                        Button { editor = HostEditorState(draft: store.draft(for: host)) } label: {
                            HostSettingsRow(host: host)
                        }
                        .buttonStyle(.plain)
                        .swipeActions {
                            Button(role: .destructive) { store.deleteHost(host) } label: { Label("删除", systemImage: "trash") }
                        }
                    }
                }
            }
        }
        .navigationTitle("设置")
        .sheet(item: $editor) { state in NavigationStack { AddSSHDeviceView(draft: state.draft) } }
        .sheet(isPresented: $isBridgeSheetPresented) { NavigationStack { BridgeSettingsEditor() } }
        .sheet(isPresented: $isSharedPasswordSheetPresented) { NavigationStack { SharedPasswordView() } }
        .sheet(isPresented: $isLLMSheetPresented) { NavigationStack { LLMSettingsEditor() } }
    }

    private var lastScanText: String {
        if let last = env.intel.lastScan { return "上次扫描 \(last.formatted(.dateTime.month().day().hour().minute()))" }
        return "尚未扫描"
    }

    private func statusRow(title: String, systemImage: String, value: String, detail: String, tint: Color) -> some View {
        HStack(spacing: 12) {
            Image(systemName: systemImage).font(.title3).foregroundStyle(tint).frame(width: 30)
            VStack(alignment: .leading, spacing: 3) {
                Text(title).font(.headline)
                Text(value).font(.caption).foregroundStyle(.secondary).lineLimit(1)
            }
            Spacer()
            Text(detail).font(.caption2).foregroundStyle(tint)
        }
        .padding(.vertical, 4)
    }

    private func runImport() async {
        let imp = importer ?? BridgeImporter(context: context)
        importer = imp
        let summary = await imp.importFrom(settings: store.bridgeSettings)
        importMessage = imp.lastResult
        _ = summary
    }
}

// MARK: - LLM editor (AI 录入接口)

private struct LLMSettingsEditor: View {
    @EnvironmentObject private var llmConfig: LLMConfigStore
    @Environment(\.dismiss) private var dismiss

    @State private var settings = LLMSettings()
    @State private var apiKey = ""
    @State private var testing = false
    @State private var testResult: String?

    var body: some View {
        Form {
            Section("引擎") {
                Picker("预设", selection: presetBinding) {
                    Text("自定义").tag(-1)
                    ForEach(Array(LLMSettings.presets.enumerated()), id: \.offset) { idx, p in
                        Text(p.engineLabel).tag(idx)
                    }
                }
                TextField("引擎名称", text: $settings.engineLabel).plainEntryField()
                TextField("Base URL", text: $settings.baseURL).urlEntryField()
                TextField("模型 ID", text: $settings.model).plainEntryField()
            }
            Section {
                SecureField(llmConfig.hasKey ? "API Key 已保存，留空不改" : "API Key", text: $apiKey).plainEntryField()
            } footer: {
                Text("保存在 iOS Keychain（仅本设备）。")
            }
            Section("行为") {
                Toggle("自动把英文标题翻译成中文", isOn: $settings.allowTranslation)
                Toggle("用 AI 生成「为什么重要/关系/下一步」", isOn: $settings.allowBriefingLLM)
            }
            Section {
                Button { Task { await test() } } label: {
                    Label(testing ? "测试中…" : "测试连通", systemImage: "bolt.horizontal.circle")
                }.disabled(testing)
                if let testResult { Text(testResult).font(.caption).foregroundStyle(.secondary) }
            }
        }
        .navigationTitle("AI 录入接口")
        .toolbar {
            ToolbarItem(placement: .cancellationAction) { Button("取消") { dismiss() } }
            ToolbarItem(placement: .confirmationAction) { Button("保存") { save() } }
        }
        .onAppear { settings = llmConfig.settings }
    }

    private var presetBinding: Binding<Int> {
        Binding(get: { -1 }, set: { idx in
            if idx >= 0, idx < LLMSettings.presets.count {
                let p = LLMSettings.presets[idx]
                settings.baseURL = p.baseURL; settings.model = p.model; settings.engineLabel = p.engineLabel
            }
        })
    }

    private func save() {
        llmConfig.save(settings, key: apiKey.isEmpty ? nil : apiKey)
        dismiss()
    }

    private func test() async {
        testing = true; testResult = nil
        defer { testing = false }
        llmConfig.save(settings, key: apiKey.isEmpty ? nil : apiKey)
        guard let client = llmConfig.makeClient() else { testResult = "缺少 API Key。"; return }
        do {
            let reply = try await client.complete(user: "用一个字回复：好", temperature: 0)
            testResult = "连通成功：\(reply.prefix(20))"
        } catch {
            testResult = "失败：\(error.localizedDescription)"
        }
    }
}

// MARK: - Sources manager (信源状态)

private struct SourcesManagerView: View {
    @Environment(\.modelContext) private var context
    @Query(sort: \FeedSource.name) private var feeds: [FeedSource]
    @Query(sort: \ProfileInterest.term) private var interests: [ProfileInterest]
    @State private var newFeedName = ""
    @State private var newFeedURL = ""
    @State private var newInterest = ""

    var body: some View {
        List {
            Section("关注项") {
                ForEach(interests) { interest in
                    HStack { Text(interest.term); Spacer(); Text(interest.kind).font(.caption2).foregroundStyle(.tertiary) }
                }
                .onDelete { idx in idx.map { interests[$0] }.forEach(context.delete); try? context.save() }
                HStack {
                    TextField("新增关注项", text: $newInterest).plainEntryField()
                    Button("添加") {
                        let term = newInterest.trimmingCharacters(in: .whitespaces)
                        guard !term.isEmpty else { return }
                        context.insert(ProfileInterest(term: term)); try? context.save(); newInterest = ""
                    }.disabled(newInterest.trimmingCharacters(in: .whitespaces).isEmpty)
                }
            }
            Section("RSS 信源 \(feeds.count)") {
                ForEach(feeds) { feed in
                    VStack(alignment: .leading, spacing: 2) {
                        HStack {
                            Toggle(isOn: Binding(get: { feed.enabled }, set: { feed.enabled = $0; try? context.save() })) {
                                Text(feed.name).font(.subheadline)
                            }
                        }
                        Text(feed.category + " · " + feed.domain).font(.caption2).foregroundStyle(.secondary)
                        if let err = feed.lastError { Text("上次错误：\(err)").font(.caption2).foregroundStyle(.red).lineLimit(1) }
                    }
                }
                .onDelete { idx in idx.map { feeds[$0] }.forEach(context.delete); try? context.save() }
                VStack(spacing: 6) {
                    TextField("信源名称", text: $newFeedName).plainEntryField()
                    TextField("RSS/Atom URL", text: $newFeedURL).urlEntryField()
                    Button("添加信源") {
                        let name = newFeedName.trimmingCharacters(in: .whitespaces)
                        let url = newFeedURL.trimmingCharacters(in: .whitespaces)
                        guard !name.isEmpty, !url.isEmpty else { return }
                        context.insert(FeedSource(name: name, url: url, category: "自定义"))
                        try? context.save(); newFeedName = ""; newFeedURL = ""
                    }.disabled(newFeedName.isEmpty || newFeedURL.isEmpty)
                }
            }
        }
        .navigationTitle("信源状态")
    }
}

// MARK: - Bridge / SSH helpers (carried over from the original settings screen)

struct HostEditorState: Identifiable {
    let id = UUID()
    let draft: HostDraft
}

private struct BridgeSettingsEditor: View {
    @EnvironmentObject private var store: FleetStore
    @Environment(\.dismiss) private var dismiss
    @State private var settings = BridgeSettings()
    @State private var token = ""
    @State private var saving = false

    var body: some View {
        Form {
            Section {
                Toggle("启用 Bridge 模式", isOn: $settings.enabled)
                TextField("名称", text: $settings.name)
                TextField("Bridge URL", text: $settings.baseURL).urlEntryField()
            } footer: {
                Text("仅用于一次性导入旧记事或查看远端 Mac；iPhone 日常运行不依赖它。")
            }
            Section {
                SecureField(store.bridgeTokenIsSaved() ? "token 已保存，留空不改" : "mobile bridge token", text: $token)
                    .plainEntryField()
            }
            Section {
                Button { Task { await saveAndProbe() } } label: {
                    Label(saving ? "测试中" : "保存并测试", systemImage: "network")
                }.disabled(saving || !settings.isUsable)
            }
        }
        .navigationTitle("Bridge")
        .toolbar {
            ToolbarItem(placement: .cancellationAction) { Button("取消") { dismiss() } }
            ToolbarItem(placement: .confirmationAction) {
                Button("保存") { save() }.disabled(saving || !settings.isUsable)
            }
        }
        .onAppear { settings = store.bridgeSettings }
    }

    private func save() {
        saving = true
        store.saveBridgeSettings(settings, token: token)
        saving = false
        if store.errorMessage == nil { dismiss() }
    }

    private func saveAndProbe() async {
        saving = true
        store.saveBridgeSettings(settings, token: token)
        saving = false
        if store.errorMessage == nil { dismiss() }
    }
}

struct HostSettingsRow: View {
    let host: MonitoredHost

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: host.enabled ? "terminal.fill" : "pause.circle")
                .foregroundStyle(host.enabled ? Color.accentColor : Color.secondary)
                .frame(width: 26)
            VStack(alignment: .leading, spacing: 3) {
                Text(host.title).font(.body.weight(.semibold))
                Text(host.addressLine).font(.caption).foregroundStyle(.secondary).lineLimit(1)
            }
            Spacer()
            Image(systemName: "chevron.right").font(.caption.weight(.semibold)).foregroundStyle(.tertiary)
        }
        .padding(.vertical, 4)
    }
}

private struct SharedPasswordView: View {
    @EnvironmentObject private var store: FleetStore
    @Environment(\.dismiss) private var dismiss
    @State private var password = ""

    var body: some View {
        Form {
            Section {
                SecureField("SSH password", text: $password).plainEntryField()
            } footer: {
                Text("保存到本机 Keychain，覆盖已配置主机的 SSH 密码。")
            }
            Section {
                Button { save() } label: { Label("保存", systemImage: "key") }
                    .disabled(password.isEmpty)
            }
        }
        .navigationTitle("共用密码")
        .toolbar {
            ToolbarItem(placement: .cancellationAction) { Button("取消") { dismiss() } }
        }
    }

    private func save() {
        store.saveSharedPassword(password)
        if store.errorMessage == nil { dismiss() }
    }
}

extension View {
    @ViewBuilder
    func urlEntryField() -> some View {
        #if os(iOS)
        self.textInputAutocapitalization(.never).keyboardType(.URL).autocorrectionDisabled()
        #else
        self
        #endif
    }

    @ViewBuilder
    func plainEntryField() -> some View {
        #if os(iOS)
        self.textInputAutocapitalization(.never).autocorrectionDisabled()
        #else
        self
        #endif
    }

    @ViewBuilder
    func numberEntryField() -> some View {
        #if os(iOS)
        self.keyboardType(.numberPad)
        #else
        self
        #endif
    }
}
