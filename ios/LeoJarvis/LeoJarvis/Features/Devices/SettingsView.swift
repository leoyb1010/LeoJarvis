import SwiftUI

struct SettingsView: View {
    @EnvironmentObject private var store: JarvisStore
    @State private var testing = false
    @State private var showingAddMac = false
    @State private var tavilyKeyDraft = ""
    @State private var tavilyNotice = ""
    @State private var deviceToRemove: FleetDevice?

    var body: some View {
        let onlineTargetCount = store.macTargets.filter { $0.online }.count
        let currentFastestTarget = fastestTarget
        ScreenScaffold(
            title: "设备",
            subtitle: "\(store.macTargets.count) 个控制端 · \(onlineTargetCount)/\(max(store.macTargets.count, 1)) 可控",
            systemImage: "macbook.and.iphone",
            trailing: { addMacButton }
        ) {
            remoteControlHero(onlineTargets: onlineTargetCount, fastestTarget: currentFastestTarget)
                .appearLift(delay: 0.03)
            fleetCommandCard
                .appearLift(delay: 0.05)
            controlTargetsCard
                .appearLift(delay: 0.09)
            fleetCard
                .appearLift(delay: 0.13)
            connectionCard
                .appearLift(delay: 0.17)
            tavilyCard
                .appearLift(delay: 0.19)
            statusCard
                .appearLift(delay: 0.23)
            deviceCard
                .appearLift(delay: 0.27)
        }
        .refreshable {
            await store.refreshAll()
            await store.refreshMacTargets()
            await store.refreshFleetRuntime()
        }
        .sheet(isPresented: $showingAddMac) {
            AddMacSheet()
                .presentationDetents([.medium])
        }
    }

    private func remoteControlHero(onlineTargets: Int, fastestTarget: MacTarget?) -> some View {
        RemoteControlHero(
            activeName: activeTarget?.name ?? "未选择控制端",
            endpoint: JarvisAPIClient(baseURL: store.endpoint, token: store.token).normalizedBaseURL,
            onlineTargets: onlineTargets,
            totalTargets: store.macTargets.count,
            fastestName: fastestTarget?.name,
            fastestLatencyMs: fastestTarget?.latencyMs,
            latencyMs: activeTarget?.latencyMs,
            isOnline: store.health?.ok == true
        )
    }

    private var activeTarget: MacTarget? {
        store.macTargets.first(where: isActive)
    }

    private var fastestTarget: MacTarget? {
        store.macTargets
            .filter { $0.online }
            .sorted { ($0.latencyMs ?? Int.max) < ($1.latencyMs ?? Int.max) }
            .first
    }

    private var addMacButton: some View {
        Button {
            Haptics.lightImpact()
            showingAddMac = true
        } label: {
            ZStack {
                Circle()
                    .fill(AppTheme.accent)
                Image(systemName: "plus")
                    .font(.system(size: 16, weight: .heavy))
                    .foregroundStyle(AppTheme.onAccent)
            }
            .frame(width: 42, height: 42)
        }
        .buttonStyle(PressScaleButtonStyle())
        .accessibilityLabel("添加 Mac")
    }

    private var runtimeSnapshots: [MacRuntimeSnapshot] {
        store.macTargets.map { target in
            store.macRuntime[target.id] ?? MacRuntimeSnapshot(
                target: target,
                online: target.online,
                latencyMs: target.latencyMs,
                health: nil,
                device: nil,
                services: [],
                agents: [],
                sessions: [],
                lastChecked: target.lastChecked,
                error: nil
            )
        }
    }

    private var fleetCommandCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                SectionTitle(title: "全舰队实时控制", icon: "rectangle.connected.to.line.below")
                Spacer()
                Button {
                    Haptics.lightImpact()
                    Task {
                        await store.refreshFleetRuntime()
                    }
                } label: {
                    Label(store.isRefreshingFleetRuntime ? "同步中" : "同步", systemImage: "arrow.triangle.2.circlepath")
                        .font(.system(size: 11, weight: .heavy))
                        .foregroundStyle(AppTheme.accent)
                }
                .buttonStyle(PressScaleButtonStyle())
                .disabled(store.isRefreshingFleetRuntime)
            }

            Text("公网控制已就绪 · 按响应时间排序 · 运行状态来自各机实时接口。")
                .font(.system(size: 12, weight: .semibold))
                .foregroundStyle(AppTheme.muted)
                .lineSpacing(3)

            LazyVStack(spacing: 10) {
                ForEach(runtimeSnapshots) { snapshot in
                    Button {
                        Haptics.selection()
                        Task { await store.switchMacTarget(snapshot.target) }
                    } label: {
                        MacRuntimeCard(snapshot: snapshot, isActive: isActive(snapshot.target))
                    }
                    .buttonStyle(.plain)
                }
            }
        }
        .panel()
    }

    private var controlTargetsCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                SectionTitle(title: "控制端", icon: "bolt.horizontal.circle.fill")
                Spacer()
                Button {
                    Haptics.lightImpact()
                    Task { await store.switchFastestMacTarget() }
                } label: {
                    Label("切最快", systemImage: "bolt.fill")
                        .font(.system(size: 11, weight: .heavy))
                        .foregroundStyle(AppTheme.success)
                }
                .buttonStyle(PressScaleButtonStyle())
                .disabled(store.isRefreshingTargets || store.macTargets.isEmpty)
                Button {
                    Haptics.lightImpact()
                    Task { await store.refreshMacTargets() }
                } label: {
                    Label(store.isRefreshingTargets ? "测速中" : "并发测速", systemImage: "speedometer")
                        .font(.system(size: 11, weight: .heavy))
                        .foregroundStyle(AppTheme.accent)
                }
                .buttonStyle(PressScaleButtonStyle())
                .disabled(store.isRefreshingTargets)
            }

            Text("三台 Mac 已内置公网 HTTPS 入口。iPhone 在外网时会并发测速，新版 Jarvis 可直接切换；旧桥接设备会显示需升级状态。")
                .font(.system(size: 12, weight: .semibold))
                .foregroundStyle(AppTheme.muted)
                .lineSpacing(3)

            if store.macTargets.isEmpty {
                EmptyState(text: "还没有公网 Mac 控制端。点右上角添加 Cloudflare Tunnel 或 Tailscale Funnel 的 HTTPS 地址。", systemImage: "network")
                    .frame(minHeight: 96)
            } else {
                ForEach(store.macTargets) { target in
                    Button {
                        Haptics.selection()
                        Task { await store.switchMacTarget(target) }
                    } label: {
                        MacTargetRow(target: target, isActive: isActive(target))
                    }
                    .buttonStyle(PressScaleButtonStyle())
                    .transition(.move(edge: .bottom).combined(with: .opacity))
                    .contextMenu {
                        if store.macTargets.count > 1 {
                            Button(role: .destructive) {
                                store.removeMacTarget(target)
                            } label: {
                                Label("移除", systemImage: "trash")
                            }
                        }
                    }
                }
            }
        }
        .panel()
        .animation(AppMotion.spring, value: store.macTargets.count)
    }

    private var fleetCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                SectionTitle(title: "设备舰队", icon: "desktopcomputer")
                Spacer()
                StatusPill(
                    title: "\(store.devices.filter { $0.online == true }.count)/\(store.devices.count)",
                    icon: "antenna.radiowaves.left.and.right",
                    tint: store.devices.contains { $0.online == false } ? AppTheme.warn : AppTheme.success
                )
            }
            if store.devices.isEmpty {
                EmptyState(text: "当前 Hub 只登记了本机。其它 Mac 运行后，通过心跳同步到这里。", systemImage: "macbook.and.iphone")
            } else {
                ForEach(store.devices) { device in
                    FleetDeviceCard(device: device)
                        .contextMenu {
                            if device.is_current != true {
                                Button(role: .destructive) {
                                    deviceToRemove = device
                                } label: {
                                    Label("移除登记", systemImage: "trash")
                                }
                            }
                        }
                }
            }
        }
        .panel()
        .confirmationDialog(
            "移除该设备登记？",
            isPresented: Binding(get: { deviceToRemove != nil }, set: { if !$0 { deviceToRemove = nil } }),
            titleVisibility: .visible
        ) {
            Button("移除登记", role: .destructive) {
                if let device = deviceToRemove {
                    Task { await store.removeFleetDevice(device) }
                }
                deviceToRemove = nil
            }
            Button("取消", role: .cancel) { deviceToRemove = nil }
        } message: {
            Text("将从 Hub 删除「\(deviceToRemove?.device_name ?? deviceToRemove?.host_name ?? deviceToRemove?.device_id ?? "该设备")」的登记，此操作不可撤销。")
        }
    }

    private var connectionCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            SectionTitle(title: "连接地址", icon: "link")
            TextField("Jarvis 地址", text: $store.endpoint)
                .font(.system(size: 15, weight: .semibold))
                .textInputAutocapitalization(.never)
                .keyboardType(.URL)
                .softField()
            SecureField("Bearer token（可选）", text: $store.token)
                .font(.system(size: 15, weight: .semibold))
                .softField()
            Button {
                testing = true
                Task {
                    _ = await store.testConnection()
                    testing = false
                }
            } label: {
                HStack(spacing: 8) {
                    if testing {
                        ProgressView()
                            .tint(AppTheme.onAccent)
                    } else {
                        Image(systemName: "bolt.horizontal.circle.fill")
                    }
                    Text(testing ? "检测中" : "检测连接")
                        .font(.system(size: 15, weight: .heavy))
                }
                .foregroundStyle(AppTheme.onAccent)
                .frame(maxWidth: .infinity)
                .frame(height: 46)
                .background(AppTheme.accent, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
            }
            .disabled(testing)
            .buttonStyle(PressScaleButtonStyle())
        }
        .panel()
    }

    private var tavilyCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                SectionTitle(title: "Tavily 兜底", icon: "magnifyingglass.circle.fill")
                Spacer()
                StatusPill(
                    title: store.hasLocalTavilyKey ? "本机 Keychain" : "走 Mac 代理",
                    icon: store.hasLocalTavilyKey ? "checkmark.seal.fill" : "macbook",
                    tint: store.hasLocalTavilyKey ? AppTheme.success : AppTheme.violet
                )
            }
            Text("Tavily 只作为主信源之外的付费兜底：24 小时内主 RSS/Atom 明显不足、冷却结束且每日额度未用完时才会触发；不配置手机 Key 时走当前在线 Mac 代理。")
                .font(.system(size: 12, weight: .semibold))
                .foregroundStyle(AppTheme.muted)
                .lineSpacing(3)
            SecureField(store.hasLocalTavilyKey ? "已保存，可粘贴新 key 替换" : "粘贴 Tavily API Key（可选）", text: $tavilyKeyDraft)
                .font(.system(size: 15, weight: .semibold))
                .textInputAutocapitalization(.never)
                .softField()
            HStack(spacing: 8) {
                Button {
                    store.saveTavilyAPIKey(tavilyKeyDraft)
                    tavilyKeyDraft = ""
                    tavilyNotice = store.hasLocalTavilyKey ? "已保存到 Keychain" : "已清空"
                    Haptics.success()
                } label: {
                    Label("保存", systemImage: "key.fill")
                        .font(.system(size: 13, weight: .heavy))
                        .foregroundStyle(AppTheme.onAccent)
                        .frame(maxWidth: .infinity)
                        .frame(height: 40)
                        .background(AppTheme.accent, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                }
                .buttonStyle(PressScaleButtonStyle())
                .disabled(tavilyKeyDraft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)

                Button {
                    store.saveTavilyAPIKey("")
                    tavilyKeyDraft = ""
                    tavilyNotice = "已清除本机 Keychain"
                    Haptics.lightImpact()
                } label: {
                    Label("清除", systemImage: "trash")
                        .font(.system(size: 13, weight: .heavy))
                        .foregroundStyle(AppTheme.danger)
                        .frame(maxWidth: .infinity)
                        .frame(height: 40)
                        .background(AppTheme.dangerSoft, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                }
                .buttonStyle(PressScaleButtonStyle())
            }
            if !tavilyNotice.isEmpty {
                Text(tavilyNotice)
                    .font(.system(size: 11, weight: .heavy))
                    .foregroundStyle(AppTheme.success)
            }
        }
        .panel()
    }

    private var statusCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                SectionTitle(title: "当前状态", icon: "checklist")
                Spacer()
                StatusPill(
                    title: store.health?.ok == true ? "在线" : "离线",
                    icon: store.health?.ok == true ? "checkmark.circle.fill" : "exclamationmark.circle.fill",
                    tint: store.health?.ok == true ? AppTheme.success : AppTheme.warn
                )
            }
            SettingsLine(label: "服务", value: store.health?.service ?? "-")
            SettingsLine(label: "地址", value: store.endpoint)
            SettingsLine(label: "规范化", value: JarvisAPIClient(baseURL: store.endpoint, token: store.token).normalizedBaseURL)
            SettingsLine(label: "Token", value: store.token.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? "未配置" : "已配置")
            SettingsLine(label: "iPhone Whisper", value: localWhisperStatus)
            SettingsLine(label: "刷新", value: DisplayFormat.relative(store.lastRefreshed))
        }
        .panel()
    }

    private var localWhisperStatus: String {
        guard LocalWhisperTranscriber.isBundledModelAvailable else {
            return "离线模型缺失"
        }
        if let size = LocalWhisperTranscriber.bundledModelSizeMB() {
            return "离线可用 · base \(Int(size.rounded()))MB"
        }
        return "离线可用 · base"
    }

    private var deviceCard: some View {
        VStack(alignment: .leading, spacing: 10) {
            SectionTitle(title: "外网连接", icon: "iphone.gen3")
            Text("真机只推荐公网 HTTPS 地址。每台 Mac 用 Cloudflare Tunnel 或 Tailscale Funnel 暴露 8787；模拟器开发时才使用 127.0.0.1。")
                .font(.system(size: 13, weight: .semibold))
                .foregroundStyle(AppTheme.muted)
                .lineSpacing(3)
            HStack(spacing: 8) {
                StatusPill(title: "公网 HTTPS", icon: "lock.fill", tint: AppTheme.success)
                StatusPill(title: "Cloudflare Tunnel", icon: "network", tint: AppTheme.accent)
                StatusPill(title: "Tailscale Funnel", icon: "point.3.connected.trianglepath.dotted", tint: AppTheme.violet)
            }
        }
        .panel()
    }

    private func isActive(_ target: MacTarget) -> Bool {
        JarvisAPIClient(baseURL: target.endpoint, token: store.token).normalizedBaseURL == JarvisAPIClient(baseURL: store.endpoint, token: store.token).normalizedBaseURL
    }
}

struct RemoteControlHero: View {
    let activeName: String
    let endpoint: String
    let onlineTargets: Int
    let totalTargets: Int
    let fastestName: String?
    let fastestLatencyMs: Int?
    let latencyMs: Int?
    let isOnline: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(alignment: .center, spacing: 12) {
                LiveHalo(online: isOnline, tint: isOnline ? AppTheme.success : AppTheme.warn)
                    .frame(width: 52, height: 52)

                VStack(alignment: .leading, spacing: 4) {
                    Text(isOnline ? "外网控制就绪" : "等待公网控制端")
                        .font(.system(size: 22, weight: .heavy, design: .rounded))
                        .foregroundStyle(AppTheme.ink)
                        .lineLimit(1)
                        .minimumScaleFactor(0.72)
                    Text(activeName)
                        .font(.system(size: 13, weight: .heavy))
                        .foregroundStyle(isOnline ? AppTheme.success : AppTheme.warn)
                        .lineLimit(1)
                }

                Spacer(minLength: 0)

                StatusPill(
                    title: latencyMs.map { "当前 \($0)ms" } ?? "未测速",
                    icon: "speedometer",
                    tint: latencyTint
                )
            }

            Text(endpoint.isEmpty ? "尚未配置公网 HTTPS 地址" : endpoint)
                .font(.system(size: 12, weight: .heavy, design: .monospaced))
                .foregroundStyle(AppTheme.muted)
                .lineLimit(1)
                .truncationMode(.middle)

            HStack(spacing: 8) {
                RemoteHeroStat(title: "在线控制端", value: "\(onlineTargets)/\(max(totalTargets, 1))", tint: isOnline ? AppTheme.success : AppTheme.warn)
                RemoteHeroStat(title: "最快响应", value: fastestLabel, tint: AppTheme.accent)
            }
        }
        .padding(16)
        .adaptiveGlass(cornerRadius: 18, interactive: false)
        .overlay(
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .stroke(isOnline ? AppTheme.success.opacity(0.20) : AppTheme.warn.opacity(0.22), lineWidth: 1)
        )
        .shadow(color: (isOnline ? AppTheme.success : AppTheme.warn).opacity(0.10), radius: 18, y: 10)
    }

    private var latencyTint: Color {
        guard let latencyMs else { return AppTheme.muted }
        if latencyMs <= 180 { return AppTheme.success }
        if latencyMs <= 650 { return AppTheme.warn }
        return AppTheme.danger
    }

    private var fastestLabel: String {
        guard let fastestName else { return "-" }
        if let fastestLatencyMs {
            return "\(fastestName) · \(fastestLatencyMs)ms"
        }
        return fastestName
    }
}

struct RemoteHeroStat: View {
    let title: String
    let value: String
    let tint: Color

    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(value)
                .font(.system(size: 18, weight: .heavy, design: .rounded))
                .foregroundStyle(tint)
                .lineLimit(1)
                .minimumScaleFactor(0.62)
            Text(title)
                .font(.system(size: 10, weight: .heavy))
                .foregroundStyle(AppTheme.muted)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.horizontal, 12)
        .padding(.vertical, 9)
        .background(AppTheme.elevated, in: RoundedRectangle(cornerRadius: 11, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 11, style: .continuous)
                .stroke(tint.opacity(0.12), lineWidth: 1)
        )
    }
}

struct MacTargetRow: View {
    let target: MacTarget
    let isActive: Bool

    var body: some View {
        HStack(spacing: 12) {
            ZStack {
                RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .fill(isActive ? AppTheme.accentSoft : AppTheme.elevated)
                Image(systemName: isActive ? "bolt.fill" : "macbook")
                    .font(.system(size: 17, weight: .heavy))
                    .foregroundStyle(isActive ? AppTheme.accent : AppTheme.muted)
            }
            .frame(width: 42, height: 42)

            VStack(alignment: .leading, spacing: 4) {
                HStack(spacing: 6) {
                    Text(target.name)
                        .font(.system(size: 15, weight: .heavy))
                        .foregroundStyle(AppTheme.ink)
                        .lineLimit(1)
                    if isActive {
                        StatusPill(title: "当前", icon: nil, tint: AppTheme.accent)
                    }
                }
                Text(target.endpoint)
                    .font(.system(size: 11, weight: .semibold, design: .monospaced))
                    .foregroundStyle(AppTheme.muted)
                    .lineLimit(1)
                    .truncationMode(.middle)
                if let detail = target.detail, !detail.isEmpty {
                    Text(detail)
                        .font(.system(size: 10, weight: .heavy))
                        .foregroundStyle(AppTheme.faint)
                        .lineLimit(1)
                        .truncationMode(.tail)
                }
            }

            Spacer(minLength: 0)

            VStack(alignment: .trailing, spacing: 5) {
                HStack(spacing: 5) {
                    AnimatedStatusDot(online: target.online)
                    Text(target.online ? "在线" : "离线")
                        .font(.system(size: 11, weight: .heavy))
                        .foregroundStyle(target.online ? AppTheme.success : AppTheme.warn)
                }
                Text(target.latencyMs.map { "\($0)ms" } ?? "未测速")
                    .font(.system(size: 10, weight: .heavy, design: .monospaced))
                    .foregroundStyle(AppTheme.faint)
                LatencyBars(latencyMs: target.latencyMs, online: target.online)
            }
        }
        .compactPanel()
        .overlay(
            RoundedRectangle(cornerRadius: AppTheme.tightCorner, style: .continuous)
                .stroke(isActive ? AppTheme.accent.opacity(0.42) : Color.clear, lineWidth: 1.2)
        )
    }
}

private struct MacRuntimeCardDisplay {
    let device: FleetDevice?
    let isRuntimePending: Bool
    let onlineServiceCount: Int
    let serviceCount: Int
    let exposedServiceCount: Int
    let installedAgentCount: Int
    let runningSessionCount: Int
    let topServices: [ServiceStatus]

    init(snapshot: MacRuntimeSnapshot) {
        self.device = snapshot.device
        self.isRuntimePending = snapshot.online
            && snapshot.device == nil
            && snapshot.services.isEmpty
            && snapshot.agents.isEmpty
            && snapshot.sessions.isEmpty
            && snapshot.error == nil
        self.onlineServiceCount = snapshot.services.reduce(0) { count, service in
            let isOnline = (service.health ?? "").lowercased() == "online" || service.pid != nil
            return count + (isOnline ? 1 : 0)
        }
        self.serviceCount = snapshot.services.count
        self.exposedServiceCount = snapshot.services.reduce(0) { $0 + ($1.exposed == true ? 1 : 0) }
        self.installedAgentCount = snapshot.agents.reduce(0) { $0 + ($1.installed ? 1 : 0) }
        self.runningSessionCount = snapshot.sessions.reduce(0) { count, session in
            count + (((session.status ?? "").lowercased() == "stopped") ? 0 : 1)
        }
        self.topServices = Array(snapshot.services.sorted { lhs, rhs in
            if lhs.exposed != rhs.exposed { return lhs.exposed == true }
            return (lhs.port ?? 0) < (rhs.port ?? 0)
        }.prefix(4))
    }
}

struct MacRuntimeCard: View {
    let snapshot: MacRuntimeSnapshot
    let isActive: Bool
    private let display: MacRuntimeCardDisplay

    init(snapshot: MacRuntimeSnapshot, isActive: Bool) {
        self.snapshot = snapshot
        self.isActive = isActive
        self.display = MacRuntimeCardDisplay(snapshot: snapshot)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .top, spacing: 12) {
                ZStack {
                    RoundedRectangle(cornerRadius: 13, style: .continuous)
                        .fill(snapshot.online ? AppTheme.successSoft : AppTheme.warnSoft)
                    Image(systemName: snapshot.online ? "desktopcomputer.and.macbook" : "wifi.slash")
                        .font(.system(size: 18, weight: .heavy))
                        .foregroundStyle(snapshot.online ? AppTheme.success : AppTheme.warn)
                }
                .frame(width: 46, height: 46)

                VStack(alignment: .leading, spacing: 5) {
                    HStack(spacing: 6) {
                        Text(snapshot.target.name)
                            .font(.system(size: 16, weight: .heavy))
                            .foregroundStyle(AppTheme.ink)
                            .lineLimit(1)
                        if isActive {
                            StatusPill(title: "当前控制", icon: nil, tint: AppTheme.accent)
                        }
                    }
                    Text(device?.host_name ?? snapshot.target.endpoint)
                        .font(.system(size: 11, weight: .semibold, design: .monospaced))
                        .foregroundStyle(AppTheme.muted)
                        .lineLimit(1)
                        .truncationMode(.middle)
                    if let error = snapshot.error {
                        Text(error)
                            .font(.system(size: 11, weight: .heavy))
                            .foregroundStyle(AppTheme.warn)
                            .lineLimit(2)
                    }
                }

                Spacer(minLength: 0)

                VStack(alignment: .trailing, spacing: 4) {
                    Text(device?.health.map(String.init) ?? (snapshot.online ? (display.isRuntimePending ? "同步中" : "OK") : "--"))
                        .font(.system(size: 24, weight: .heavy, design: .rounded))
                        .foregroundStyle(statusTint)
                        .lineLimit(1)
                        .minimumScaleFactor(0.56)
                    Text(snapshot.latencyMs.map { "\($0)ms" } ?? "未测速")
                        .font(.system(size: 10, weight: .heavy, design: .monospaced))
                        .foregroundStyle(AppTheme.faint)
                }
            }

            HStack(spacing: 8) {
                RuntimeMetric(title: "CPU", value: percent(device?.metrics?.cpu_load_pct), tint: AppTheme.success)
                RuntimeMetric(title: "RAM", value: percent(device?.metrics?.ram_used_pct), tint: AppTheme.violet)
                RuntimeMetric(title: "SSD", value: percent(device?.metrics?.ssd_used_pct), tint: AppTheme.warn)
                RuntimeMetric(title: "CLI", value: display.isRuntimePending ? "--" : "\(display.installedAgentCount)", tint: AppTheme.accent)
            }

            HStack(spacing: 7) {
                if display.isRuntimePending {
                    StatusPill(title: "明细同步中", icon: "arrow.triangle.2.circlepath", tint: AppTheme.accent)
                } else {
                    StatusPill(title: "\(display.onlineServiceCount)/\(max(display.serviceCount, 1)) 服务", icon: "server.rack", tint: snapshot.online ? AppTheme.success : AppTheme.warn)
                    StatusPill(title: "\(display.exposedServiceCount) 暴露", icon: "network", tint: display.exposedServiceCount == 0 ? AppTheme.muted : AppTheme.warn)
                    StatusPill(title: "\(display.runningSessionCount) 会话", icon: "terminal.fill", tint: display.runningSessionCount > 0 ? AppTheme.accent : AppTheme.muted)
                }
                Spacer(minLength: 0)
            }

            if !display.topServices.isEmpty {
                VStack(alignment: .leading, spacing: 6) {
                    ForEach(display.topServices) { service in
                        HStack(spacing: 8) {
                            Circle()
                                .fill(service.exposed == true ? AppTheme.warn : AppTheme.success)
                                .frame(width: 7, height: 7)
                            Text(service.display ?? service.name ?? "Service")
                                .font(.system(size: 11, weight: .heavy))
                                .foregroundStyle(AppTheme.ink)
                                .lineLimit(1)
                            Spacer(minLength: 0)
                            Text(service.port.map { ":\($0)" } ?? service.source ?? "")
                                .font(.system(size: 10, weight: .heavy, design: .monospaced))
                                .foregroundStyle(AppTheme.muted)
                        }
                    }
                }
                .padding(10)
                .background(AppTheme.elevated, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
            }
        }
        .compactPanel()
        .overlay(
            RoundedRectangle(cornerRadius: AppTheme.tightCorner, style: .continuous)
                .stroke(isActive ? AppTheme.accent.opacity(0.44) : Color.clear, lineWidth: 1.2)
        )
    }

    private var device: FleetDevice? { display.device }

    private var statusTint: Color {
        if !snapshot.online { return AppTheme.warn }
        let health = display.device?.health ?? 100
        if health < 70 { return AppTheme.danger }
        if health < 85 { return AppTheme.warn }
        return AppTheme.success
    }

    private func percent(_ value: Double?) -> String {
        guard let value else { return "--" }
        return "\(Int(value.rounded()))%"
    }
}

struct RuntimeMetric: View {
    let title: String
    let value: String
    let tint: Color

    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(value)
                .font(.system(size: 15, weight: .heavy, design: .rounded))
                .foregroundStyle(tint)
                .lineLimit(1)
                .minimumScaleFactor(0.72)
            Text(title)
                .font(.system(size: 9, weight: .heavy))
                .foregroundStyle(AppTheme.muted)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.horizontal, 9)
        .padding(.vertical, 8)
        .background(AppTheme.elevated, in: RoundedRectangle(cornerRadius: 9, style: .continuous))
    }
}

struct FleetDeviceCard: View {
    let device: FleetDevice

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .top, spacing: 12) {
                ZStack {
                    Circle()
                        .fill(statusTint.opacity(0.13))
                    Image(systemName: device.online == true ? "desktopcomputer" : "powerplug.fill")
                        .font(.system(size: 17, weight: .heavy))
                        .foregroundStyle(statusTint)
                }
                .frame(width: 42, height: 42)

                VStack(alignment: .leading, spacing: 4) {
                    HStack(spacing: 6) {
                        Text(device.device_name ?? device.host_name ?? "Mac")
                            .font(.system(size: 16, weight: .heavy))
                            .foregroundStyle(AppTheme.ink)
                            .lineLimit(1)
                        if device.is_current == true {
                            StatusPill(title: "Hub 本机", icon: nil, tint: AppTheme.accent)
                        }
                    }
                    Text([device.model, device.host_name].compactMap(nonEmpty).joined(separator: " · "))
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundStyle(AppTheme.muted)
                        .lineLimit(1)
                        .truncationMode(.middle)
                }

                Spacer(minLength: 0)

                VStack(alignment: .trailing, spacing: 2) {
                    Text("\(device.health ?? 0)")
                        .font(.system(size: 24, weight: .heavy, design: .rounded))
                        .foregroundStyle(statusTint)
                        .contentTransition(.numericText())
                    Text(device.status ?? (device.online == true ? "健康" : "离线"))
                        .font(.system(size: 10, weight: .heavy))
                        .foregroundStyle(AppTheme.muted)
                }
            }

            HStack(spacing: 8) {
                DeviceMiniMetric(title: "CPU", value: percent(device.metrics?.cpu_load_pct))
                DeviceMiniMetric(title: "RAM", value: percent(device.metrics?.ram_used_pct))
                DeviceMiniMetric(title: "SSD", value: percent(device.metrics?.ssd_used_pct))
                DeviceMiniMetric(title: "服务", value: servicesText)
            }

            HStack(spacing: 8) {
                StatusPill(
                    title: device.online == true ? "在线" : "离线",
                    icon: device.online == true ? "checkmark.circle.fill" : "exclamationmark.circle.fill",
                    tint: statusTint
                )
                StatusPill(
                    title: "心跳 \(DisplayFormat.secondsAgo(device.seen_ago_s))",
                    icon: "clock",
                    tint: AppTheme.muted
                )
                Spacer(minLength: 0)
            }

            let risks = Array((device.risks ?? []).prefix(2))
            if !risks.isEmpty {
                VStack(alignment: .leading, spacing: 6) {
                    ForEach(risks) { risk in
                        HStack(alignment: .top, spacing: 7) {
                            Image(systemName: risk.level == "异常" ? "xmark.octagon.fill" : "exclamationmark.triangle.fill")
                                .font(.system(size: 11, weight: .heavy))
                                .foregroundStyle(risk.level == "异常" ? AppTheme.danger : AppTheme.warn)
                                .padding(.top, 2)
                            Text(nonEmpty(risk.title) ?? nonEmpty(risk.detail) ?? "风险项")
                                .font(.system(size: 11, weight: .semibold))
                                .foregroundStyle(AppTheme.muted)
                                .lineLimit(2)
                        }
                    }
                }
            }
        }
        .compactPanel()
    }

    private var statusTint: Color {
        if device.online != true { return AppTheme.warn }
        if (device.health ?? 0) < 65 || device.status == "异常" { return AppTheme.danger }
        if (device.health ?? 0) < 82 || device.status == "注意" { return AppTheme.warn }
        return AppTheme.success
    }

    private var servicesText: String {
        guard let online = device.services?.online, let total = device.services?.total, total > 0 else {
            return "-"
        }
        return "\(online)/\(total)"
    }

    private func percent(_ value: Double?) -> String {
        guard let value else { return "-" }
        return "\(Int(value.rounded()))%"
    }
}

struct DeviceMiniMetric: View {
    let title: String
    let value: String

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(value)
                .font(.system(size: 13, weight: .heavy, design: .rounded))
                .foregroundStyle(AppTheme.ink)
                .lineLimit(1)
            Text(title)
                .font(.system(size: 9, weight: .heavy))
                .foregroundStyle(AppTheme.muted)
            MetricBar(value: ratio, tint: barTint)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.horizontal, 8)
        .padding(.vertical, 7)
        .background(AppTheme.elevated, in: RoundedRectangle(cornerRadius: 9, style: .continuous))
    }

    private var ratio: Double? {
        guard value.hasSuffix("%"), let raw = Double(value.dropLast()) else { return nil }
        return min(max(raw / 100, 0), 1)
    }

    private var barTint: Color {
        guard let ratio else { return AppTheme.faint }
        if ratio >= 0.9 { return AppTheme.danger }
        if ratio >= 0.72 { return AppTheme.warn }
        return AppTheme.success
    }
}

struct AddMacSheet: View {
    @Environment(\.dismiss) private var dismiss
    @EnvironmentObject private var store: JarvisStore
    @State private var name = ""
    @State private var endpoint = ""

    var body: some View {
        NavigationStack {
            ZStack {
                AppBackground()
                VStack(alignment: .leading, spacing: 14) {
                    VStack(alignment: .leading, spacing: 12) {
                        SectionTitle(title: "添加 Mac", icon: "plus.circle.fill")
                        TextField("名称，例如 Studio / MBP / Mini", text: $name)
                            .font(.system(size: 15, weight: .semibold))
                            .softField()
                        TextField("地址，例如 https://jarvis-mbp.example.com", text: $endpoint)
                            .font(.system(size: 15, weight: .semibold))
                            .textInputAutocapitalization(.never)
                            .keyboardType(.URL)
                            .softField()
                        Text("推荐 Cloudflare Tunnel 绑定固定域名；也可以用 Tailscale Funnel。不要填 127.0.0.1 或局域网地址，外出时 iPhone 会连不上。保存后会立刻切换并测速。")
                            .font(.system(size: 12, weight: .semibold))
                            .foregroundStyle(AppTheme.muted)
                            .lineSpacing(3)
                    }
                    .panel()
                    Spacer()
                }
                .padding(16)
            }
            .navigationTitle("公网控制端")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("取消") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("保存") {
                        let clean = endpoint.trimmingCharacters(in: .whitespacesAndNewlines)
                        store.addOrUpdateMacTarget(name: name, endpoint: clean, select: true)
                        Haptics.success()
                        Task {
                            await store.refreshMacTargets()
                            await store.refreshAll()
                        }
                        dismiss()
                    }
                    .disabled(endpoint.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                }
            }
        }
    }
}
