import SwiftUI

struct AddSSHDeviceView: View {
    @EnvironmentObject private var store: FleetStore
    @Environment(\.dismiss) private var dismiss

    @State private var draft: HostDraft
    @State private var saving = false

    init(draft: HostDraft = HostDraft()) {
        _draft = State(initialValue: draft)
    }

    var body: some View {
        Form {
            Section("显示") {
                TextField("名称，例如 Studio Mac", text: $draft.name)
                Toggle("启用探测", isOn: $draft.enabled)
            }

            Section {
                Picker("方式", selection: $draft.connectionKind) {
                    ForEach([MonitoredHost.ConnectionKind.direct], id: \.self) { kind in
                        Text(kind.label).tag(kind)
                    }
                }
                if draft.connectionKind == .cloudflareAccess {
                    TextField("授权域名", text: $draft.authDomain)
                        .urlEntryField()
                }
            } header: {
                Text("连接")
            } footer: {
                Text("这是备用直连 SSH 配置。默认推荐使用 Mac mini Bridge；直连模式需要 iPhone/iPad 能访问目标主机的 IP。")
            }

            Section {
                TextField("host / IP", text: $draft.host)
                    .urlEntryField()
                TextField("user", text: $draft.username)
                    .plainEntryField()
                TextField("端口", text: $draft.port)
                    .numberEntryField()
                SecureField(passwordPlaceholder, text: $draft.password)
                    .plainEntryField()
            } header: {
                Text("SSH")
            } footer: {
                Text("备用直连模式支持密码登录。密码保存在 iOS Keychain；编辑已有主机时留空表示不改密码。")
            }

            Section {
                Button {
                    Task { await saveAndProbe() }
                } label: {
                    Label("保存后探测", systemImage: "bolt.horizontal.circle")
                }
                .disabled(saving || !canSave)
            }
        }
        .navigationTitle(draft.id == nil ? "添加 SSH" : "编辑 SSH")
        .toolbar {
            ToolbarItem(placement: .cancellationAction) {
                Button("取消") { dismiss() }
            }
            ToolbarItem(placement: .confirmationAction) {
                Button {
                    save()
                } label: {
                    if saving {
                        ProgressView()
                    } else {
                        Text("保存")
                    }
                }
                .disabled(saving || !canSave)
            }
        }
    }

    private var passwordPlaceholder: String {
        draft.id == nil ? "password" : "password（留空不改）"
    }

    private var canSave: Bool {
        !draft.host.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty &&
        !draft.username.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty &&
        (draft.id != nil || !draft.password.isEmpty)
    }

    private func save() {
        saving = true
        store.saveHost(draft)
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
