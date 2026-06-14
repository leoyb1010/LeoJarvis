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
    @State private var isGmailSheetPresented = false
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
                Button { isGmailSheetPresented = true } label: {
                    statusRow(title: "Gmail 监控", systemImage: "envelope.badge",
                              value: gmailValueText,
                              detail: store.mobileGmailConfig.enabled ? "已启用" : "未启用",
                              tint: store.mobileGmailConfig.enabled ? .green : .orange)
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
        .hudFormBackground()
        .navigationTitle("设置")
        .sheet(item: $editor) { state in NavigationStack { AddSSHDeviceView(draft: state.draft) } }
        .sheet(isPresented: $isBridgeSheetPresented) { NavigationStack { BridgeSettingsEditor() } }
        .sheet(isPresented: $isSharedPasswordSheetPresented) { NavigationStack { SharedPasswordView() } }
        .sheet(isPresented: $isLLMSheetPresented) { NavigationStack { LLMSettingsEditor() } }
        .sheet(isPresented: $isGmailSheetPresented) { NavigationStack { GmailSettingsView() } }
        .task { await store.loadMobileMailConfig() }
    }

    private var lastScanText: String {
        if let last = env.intel.lastScan { return "上次扫描 \(last.formatted(.dateTime.month().day().hour().minute()))" }
        return "尚未扫描"
    }

    private var gmailValueText: String {
        let gmail = store.mobileGmailConfig
        if gmail.user.isEmpty { return "未配置 Gmail 账号" }
        return "\(gmail.user) · \(gmail.host):\(gmail.port)"
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
        .hudFormBackground()
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
    @EnvironmentObject private var store: FleetStore
    @Query(sort: \FeedSource.name) private var feeds: [FeedSource]
    @Query(sort: \ProfileInterest.term) private var interests: [ProfileInterest]
    @State private var newFeedName = ""
    @State private var newFeedURL = ""
    @State private var newInterest = ""

    var body: some View {
        List {
            Section {
                HStack(spacing: 12) {
                    Image(systemName: "envelope.badge")
                        .foregroundStyle(Brand.vital)
                        .frame(width: 28)
                    VStack(alignment: .leading, spacing: 3) {
                        Text("Mail 监控")
                        Text("来自 Mac mini Bridge 的 Apple Mail / IMAP / Gmail 采集")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                    Spacer()
                    Text("\(store.mobileBriefing.mailItems.count) 封")
                        .font(.caption.monospacedDigit())
                        .foregroundStyle(Brand.vital)
                }
                if let error = store.sectionError("sources") {
                    Text(error).font(.caption2).foregroundStyle(.red)
                }
                if let error = store.sectionError("mail") {
                    Text(error).font(.caption2).foregroundStyle(.red)
                }
                NavigationLink { GmailSettingsView() } label: {
                    Label(store.mobileGmailConfig.enabled ? "管理 Gmail 监控" : "配置 Gmail 监控", systemImage: "envelope.badge")
                }
                Button {
                    Task { await store.refreshSourcesFromBridge() }
                } label: {
                    Label(store.isLoadingJarvis ? "刷新中…" : "刷新 Mail 与后端信源", systemImage: "arrow.clockwise")
                }
                .disabled(store.isLoadingJarvis || !store.bridgeSettings.isUsable || !store.bridgeTokenIsSaved())
            } header: { Text("Mail") } footer: {
                Text("iOS 无法直接读取系统 Mail 沙盒数据；LeoJarvis 通过 Mac mini Bridge 读取已授权的 Apple Mail/IMAP/Gmail，再同步到手机简报。")
            }

            Section {
                NavigationLink { RSSHubRoutesView() } label: {
                    Label("RSSHub 一键订阅（微博/知乎/B站…）", systemImage: "antenna.radiowaves.left.and.right")
                }
                NavigationLink { FeedDiscoverView() } label: {
                    Label("从网址发现订阅源", systemImage: "link.badge.plus")
                }
            } header: { Text("扩充信源") } footer: {
                Text("RSSHub 把微博/知乎/B站/公众号等转成 RSS；默认公共实例，可在下方改成自建。")
            }

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
        .hudFormBackground()
        .navigationTitle("信源状态")
        .task { await store.loadMobileMailConfig() }
    }
}

// MARK: - RSSHub one-tap routes

private struct RSSHubRoutesView: View {
    @Environment(\.modelContext) private var context
    @Query private var feeds: [FeedSource]
    @State private var instance = RSSHubClient.instanceBase
    @State private var added: Set<String> = []

    private var existingURLs: Set<String> { Set(feeds.map(\.url)) }

    var body: some View {
        List {
            Section {
                TextField("RSSHub 实例地址", text: $instance).urlEntryField()
                Button("保存实例") { RSSHubClient.setInstance(instance) }
            } header: { Text("实例") } footer: {
                Text("默认公共实例 \(RSSHubClient.defaultInstance)。公共实例不稳定时建议自建。")
            }
            Section("热门订阅") {
                ForEach(RSSHubClient.popularRoutes, id: \.id) { route in
                    routeRow(route)
                }
            }
        }
        .hudFormBackground()
        .navigationTitle("RSSHub 订阅")
        .onAppear { instance = RSSHubClient.instanceBase }
    }

    @ViewBuilder
    private func routeRow(_ route: RSSHubClient.Route) -> some View {
        let url = RSSHubClient.feedURL(for: route)
        let exists = existingURLs.contains(url) || added.contains(url)
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text(route.name).font(.subheadline)
                Text(route.note.isEmpty ? route.id : route.note)
                    .font(.caption2).foregroundStyle(route.note.isEmpty ? Color.secondary : Color.orange).lineLimit(2)
            }
            Spacer()
            Button {
                context.insert(RSSHubClient.makeSource(from: route))
                try? context.save(); added.insert(url)
            } label: { Image(systemName: exists ? "checkmark.circle.fill" : "plus.circle") }
                .disabled(exists)
        }
    }
}

// MARK: - Discover feed from URL

private struct FeedDiscoverView: View {
    @Environment(\.modelContext) private var context
    @State private var pageURL = ""
    @State private var results: [FeedDiscovery.Found] = []
    @State private var loading = false
    @State private var added: Set<String> = []

    var body: some View {
        List {
            Section {
                TextField("网站地址，如 example.com", text: $pageURL).urlEntryField()
                Button { Task { await discover() } } label: {
                    Label(loading ? "查找中…" : "查找订阅源", systemImage: "magnifyingglass")
                }.disabled(loading || pageURL.trimmingCharacters(in: .whitespaces).isEmpty)
            } footer: {
                Text("会读取页面的 RSS/Atom 链接（RSSHub-Radar 思路），找不到则尝试常见路径。")
            }
            if !results.isEmpty {
                Section("发现 \(results.count) 个") {
                    ForEach(results, id: \.url) { f in
                        HStack {
                            VStack(alignment: .leading, spacing: 2) {
                                Text(f.title).font(.subheadline).lineLimit(1)
                                Text(f.url).font(.caption2).foregroundStyle(.secondary).lineLimit(1)
                            }
                            Spacer()
                            Button {
                                context.insert(FeedSource(name: f.title, url: f.url, category: "自定义",
                                                          channel: "tech", origin: "discover"))
                                try? context.save(); added.insert(f.url)
                            } label: { Image(systemName: added.contains(f.url) ? "checkmark.circle.fill" : "plus.circle") }
                                .disabled(added.contains(f.url))
                        }
                    }
                }
            }
        }
        .hudFormBackground()
        .navigationTitle("发现订阅源")
    }

    private func discover() async {
        loading = true; defer { loading = false }
        results = await FeedDiscovery.discover(from: pageURL)
    }
}

// MARK: - Gmail

private struct GmailSettingsView: View {
    @EnvironmentObject private var store: FleetStore
    @Environment(\.dismiss) private var dismiss
    @State private var draft = MobileGmailConfig()
    @State private var appPassword = ""
    @State private var testMessage: String?

    private var canSave: Bool {
        if !draft.enabled { return true }
        let hasAccount = !draft.user.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        let hasPassword = draft.hasPassword || !appPassword.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        return hasAccount && hasPassword && store.bridgeSettings.isUsable && store.bridgeTokenIsSaved()
    }

    var body: some View {
        Form {
            Section {
                Toggle("启用 Gmail 监控", isOn: $draft.enabled)
                TextField("Gmail 地址", text: $draft.user)
                    .textInputAutocapitalization(.never)
                    .keyboardType(.emailAddress)
                    .plainEntryField()
                SecureField(draft.hasPassword ? "App Password 已保存，留空不改" : "Gmail App Password", text: $appPassword)
                    .textInputAutocapitalization(.never)
                    .plainEntryField()
            } footer: {
                Text("Gmail 需要开启 IMAP，并使用 Google 账号的 App Password；普通登录密码通常无法通过 IMAP。")
            }

            Section {
                TextField("IMAP Host", text: $draft.host)
                    .textInputAutocapitalization(.never)
                    .urlEntryField()
                Stepper("端口 \(draft.port)", value: $draft.port, in: 1...65535)
                TextField("邮箱目录", text: $draft.mailbox)
                    .textInputAutocapitalization(.never)
                    .plainEntryField()
                TextField("搜索条件", text: $draft.search)
                    .textInputAutocapitalization(.characters)
                    .plainEntryField()
                Stepper("每次最多 \(draft.limit) 封", value: $draft.limit, in: 1...80)
            } header: {
                Text("IMAP")
            } footer: {
                Text("默认读取 INBOX 中 UNSEEN 邮件，只抓取标题、发件人和 Message-ID，不下载正文。")
            }

            if let error = store.sectionError("mail") {
                Section {
                    MessageBanner(text: error, level: .warn)
                        .listRowInsets(EdgeInsets())
                        .listRowBackground(Color.clear)
                }
            }

            if let testMessage {
                Section {
                    MessageBanner(text: testMessage, level: testMessage.contains("成功") ? .good : .warn)
                        .listRowInsets(EdgeInsets())
                        .listRowBackground(Color.clear)
                }
            }

            Section {
                Button {
                    Task { await save() }
                } label: {
                    Label(store.isSavingMailConfig ? "保存并测试中…" : "保存并测试 Gmail", systemImage: "checkmark.seal")
                }
                .disabled(store.isSavingMailConfig || !canSave)

                Button {
                    Task { await store.refreshSourcesFromBridge() }
                } label: {
                    Label(store.isLoadingJarvis ? "刷新中…" : "刷新 Mail 简报", systemImage: "arrow.clockwise")
                }
                .disabled(store.isLoadingJarvis || !store.bridgeSettings.isUsable || !store.bridgeTokenIsSaved())
            }
        }
        .hudFormBackground()
        .navigationTitle("Gmail 监控")
        .toolbar {
            ToolbarItem(placement: .cancellationAction) { Button("关闭") { dismiss() } }
        }
        .task { await load() }
    }

    private func load() async {
        await store.loadMobileMailConfig()
        draft = store.mobileGmailConfig
    }

    private func save() async {
        var next = draft
        next.user = next.user.trimmingCharacters(in: .whitespacesAndNewlines)
        next.host = next.host.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? "imap.gmail.com" : next.host.trimmingCharacters(in: .whitespacesAndNewlines)
        next.mailbox = next.mailbox.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? "INBOX" : next.mailbox.trimmingCharacters(in: .whitespacesAndNewlines)
        next.search = next.search.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? "UNSEEN" : next.search.trimmingCharacters(in: .whitespacesAndNewlines)
        if let result = await store.saveMobileGmailConfig(next, appPassword: appPassword) {
            testMessage = result.message
            draft = store.mobileGmailConfig
            appPassword = ""
        }
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
        .hudFormBackground()
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
        .hudFormBackground()
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
