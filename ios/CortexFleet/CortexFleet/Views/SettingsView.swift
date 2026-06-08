import SwiftUI

struct SettingsView: View {
    @EnvironmentObject private var store: FleetStore
    @State private var editor: HostEditorState?
    @State private var isBridgeSheetPresented = false
    @State private var isSharedPasswordSheetPresented = false

    var body: some View {
        List {
            Section {
                HStack {
                    VStack(alignment: .leading, spacing: 3) {
                        Text("Mac mini Bridge")
                            .font(.headline)
                        Text(store.bridgeSettings.normalizedBaseURL)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    Spacer()
                    VStack(alignment: .trailing, spacing: 5) {
                        Label(store.bridgeSettings.enabled ? "已启用" : "已关闭", systemImage: store.bridgeSettings.enabled ? "checkmark.circle.fill" : "pause.circle")
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(store.bridgeSettings.enabled ? Color.green : Color.secondary)
                        Text(store.bridgeTokenIsSaved() ? "token 已保存" : "缺少 token")
                            .font(.caption2)
                            .foregroundStyle(store.bridgeTokenIsSaved() ? Color.secondary : Color.orange)
                    }
                    Image(systemName: "server.rack")
                        .font(.title2)
                        .foregroundStyle(.tint)
                }
                .padding(.vertical, 4)
            }

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
                Button {
                    isBridgeSheetPresented = true
                } label: {
                    Label("Bridge 设置", systemImage: "server.rack")
                }

                Button {
                    editor = HostEditorState(draft: HostDraft())
                } label: {
                    Label("添加备用直连 SSH 主机", systemImage: "plus.circle")
                }

                Button {
                    Task { await store.refreshAll() }
                } label: {
                    Label(store.isRefreshing ? "探测中" : "探测全部主机", systemImage: "bolt.horizontal.circle")
                }
                .disabled(store.hosts.isEmpty || store.isRefreshing)

                Button {
                    isSharedPasswordSheetPresented = true
                } label: {
                    Label("备用直连 SSH 共用密码", systemImage: "key.fill")
                }
                .disabled(store.hosts.isEmpty)
            } header: {
                Text("操作")
            } footer: {
                Text("默认由 Mac mini Bridge 探测三台 Mac，iPhone 不需要打开 Tailscale。备用直连 SSH 仍保留，密码只保存在当前设备 Keychain。")
            }

            Section {
                if store.hosts.isEmpty {
                    ContentUnavailableView("暂无主机", systemImage: "terminal")
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 12)
                } else {
                    ForEach(store.hosts) { host in
                        Button {
                            editor = HostEditorState(draft: store.draft(for: host))
                        } label: {
                            HostSettingsRow(host: host)
                        }
                        .buttonStyle(.plain)
                        .swipeActions {
                            Button(role: .destructive) {
                                store.deleteHost(host)
                            } label: {
                                Label("删除", systemImage: "trash")
                            }
                        }
                    }
                }
            } header: {
                Text("主机 \(store.hosts.count)/3")
            }
        }
        .navigationTitle("设置")
        .toolbar {
            Button {
                editor = HostEditorState(draft: HostDraft())
            } label: {
                Image(systemName: "plus")
            }
            .accessibilityLabel("添加主机")
        }
        .sheet(item: $editor) { state in
            NavigationStack {
                AddSSHDeviceView(draft: state.draft)
            }
        }
        .sheet(isPresented: $isBridgeSheetPresented) {
            NavigationStack {
                BridgeSettingsEditor()
            }
        }
        .sheet(isPresented: $isSharedPasswordSheetPresented) {
            NavigationStack {
                SharedPasswordView()
            }
        }
    }
}

private struct BridgeSettingsEditor: View {
    @EnvironmentObject private var store: FleetStore
    @Environment(\.dismiss) private var dismiss
    @State private var settings: BridgeSettings
    @State private var token = ""
    @State private var saving = false

    init() {
        _settings = State(initialValue: BridgeSettings())
    }

    var body: some View {
        Form {
            Section {
                Toggle("启用 Bridge 模式", isOn: $settings.enabled)
                TextField("名称", text: $settings.name)
                TextField("Bridge URL", text: $settings.baseURL)
                    .urlEntryField()
            } footer: {
                Text("同一 Wi-Fi 下使用 Mac mini 的局域网地址；以后换成公网 HTTPS 域名时只需要改这里。")
            }

            Section {
                SecureField(store.bridgeTokenIsSaved() ? "token 已保存，留空不改" : "mobile bridge token", text: $token)
                    .plainEntryField()
            } footer: {
                Text("token 保存在 iOS Keychain，用于访问 Mac mini 的 mobile-only bridge。")
            }

            Section {
                Button {
                    Task { await saveAndProbe() }
                } label: {
                    Label(saving ? "测试中" : "保存并测试", systemImage: "network")
                }
                .disabled(saving || !settings.isUsable)
            }
        }
        .navigationTitle("Bridge")
        .toolbar {
            ToolbarItem(placement: .cancellationAction) {
                Button("取消") { dismiss() }
            }
            ToolbarItem(placement: .confirmationAction) {
                Button("保存") { save() }
                    .disabled(saving || !settings.isUsable)
            }
        }
        .onAppear {
            settings = store.bridgeSettings
        }
    }

    private func save() {
        saving = true
        store.saveBridgeSettings(settings, token: token)
        saving = false
        if store.errorMessage == nil {
            dismiss()
        }
    }

    private func saveAndProbe() async {
        saving = true
        store.saveBridgeSettings(settings, token: token)
        if store.errorMessage == nil {
            await store.refreshAll()
        }
        saving = false
        if store.errorMessage == nil {
            dismiss()
        }
    }
}

struct HostEditorState: Identifiable {
    let id = UUID()
    let draft: HostDraft
}

private struct HostSettingsRow: View {
    let host: MonitoredHost

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: host.enabled ? "terminal.fill" : "pause.circle")
                .foregroundStyle(host.enabled ? Color.accentColor : Color.secondary)
                .frame(width: 26)

            VStack(alignment: .leading, spacing: 3) {
                Text(host.title)
                    .font(.body.weight(.semibold))
                    .foregroundStyle(.primary)
                Text(host.addressLine)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                if !host.authDomain.isEmpty {
                    Label(host.connectionKind == .cloudflareAccess ? host.authDomain : "备用域名 \(host.authDomain)", systemImage: "cloud")
                        .font(.caption2)
                        .foregroundStyle(.orange)
                        .lineLimit(1)
                }
            }

            Spacer()

            Image(systemName: "chevron.right")
                .font(.caption.weight(.semibold))
                .foregroundStyle(.tertiary)
        }
        .padding(.vertical, 4)
    }
}

private struct SharedPasswordView: View {
    @EnvironmentObject private var store: FleetStore
    @Environment(\.dismiss) private var dismiss
    @State private var password = ""
    @State private var saving = false

    var body: some View {
        Form {
            Section {
                SecureField("SSH password", text: $password)
                    .plainEntryField()
            } footer: {
                Text("保存到当前 iPhone/iPad 的 Keychain，只覆盖本 App 内已配置主机的 SSH 密码。")
            }

            Section {
                Button {
                    Task { await saveAndProbe() }
                } label: {
                    Label(saving ? "保存中" : "保存并探测", systemImage: "bolt.horizontal.circle")
                }
                .disabled(password.isEmpty || saving)
            }
        }
        .navigationTitle("共用密码")
        .toolbar {
            ToolbarItem(placement: .cancellationAction) {
                Button("取消") { dismiss() }
            }
            ToolbarItem(placement: .confirmationAction) {
                Button("保存") {
                    save()
                }
                .disabled(password.isEmpty || saving)
            }
        }
    }

    private func save() {
        saving = true
        store.saveSharedPassword(password)
        saving = false
        if store.errorMessage == nil {
            dismiss()
        }
    }

    private func saveAndProbe() async {
        save()
        if store.errorMessage == nil {
            await store.refreshAll()
        }
    }
}

extension View {
    @ViewBuilder
    func urlEntryField() -> some View {
        #if os(iOS)
        self
            .textInputAutocapitalization(.never)
            .keyboardType(.URL)
            .autocorrectionDisabled()
        #else
        self
        #endif
    }

    @ViewBuilder
    func plainEntryField() -> some View {
        #if os(iOS)
        self
            .textInputAutocapitalization(.never)
            .autocorrectionDisabled()
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
