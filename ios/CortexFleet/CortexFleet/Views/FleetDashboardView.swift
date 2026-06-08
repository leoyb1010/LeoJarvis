import SwiftUI

struct FleetDashboardView: View {
    @EnvironmentObject private var store: FleetStore
    @State private var autoRefreshTask: Task<Void, Never>?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                BrandHeader(
                    bridgeName: store.activeBridgeName,
                    bridgeEnabled: store.bridgeSettings.enabled
                )

                LocalDeviceCard(snapshot: store.localSnapshot)

                HStack {
                    VStack(alignment: .leading, spacing: 2) {
                        Text("SSH 主机")
                            .font(.title2.weight(.bold))
                        Text("\(store.remoteOnlineCount)/\(store.hosts.count) 在线")
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                    }
                    Spacer()
                    if store.isRefreshing {
                        ProgressView()
                    } else {
                        Gauge(value: store.averageRemoteHealth, in: 0...100) {
                            Text("健康")
                        }
                        .gaugeStyle(.accessoryCircularCapacity)
                        .tint(.green)
                        .frame(width: 52, height: 52)
                    }
                }

                if let message = store.errorMessage {
                    MessageBanner(text: message, level: .bad)
                } else if let message = store.noticeMessage {
                    MessageBanner(text: message, level: .good)
                }

                if store.hosts.isEmpty {
                    ContentUnavailableView("还没有主机数据", systemImage: "server.rack", description: Text("刷新后会从 Mac mini Bridge 同步三台 Mac 的状态。"))
                        .frame(maxWidth: .infinity)
                        .padding(.top, 28)
                } else {
                    LazyVStack(spacing: 12) {
                        ForEach(store.orderedSnapshots) { snapshot in
                            NavigationLink {
                                DeviceDetailView(hostID: snapshot.hostID)
                            } label: {
                                DeviceCardView(snapshot: snapshot)
                            }
                            .buttonStyle(.plain)
                        }
                    }
                }
            }
            .padding(16)
        }
        .navigationTitle("LeoJarvis")
        .toolbar {
            ToolbarItemGroup(placement: .primaryAction) {
                Button {
                    store.refreshLocal()
                } label: {
                    Image(systemName: "iphone.gen3.radiowaves.left.and.right")
                }
                .accessibilityLabel("扫描本机")

                Button {
                    Task { await store.refreshAll() }
                } label: {
                    Image(systemName: "arrow.clockwise")
                }
                .disabled(store.isRefreshing)
                .accessibilityLabel("刷新全部")
            }
        }
        .refreshable {
            await store.refreshAll()
        }
        .task {
            store.refreshLocal()
            await store.refreshAll()
            startAutoRefresh()
        }
        .onDisappear {
            autoRefreshTask?.cancel()
            autoRefreshTask = nil
        }
    }

    private func startAutoRefresh() {
        guard autoRefreshTask == nil else { return }
        autoRefreshTask = Task {
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(30))
                if Task.isCancelled { return }
                await store.refreshAll()
            }
        }
    }
}

private struct BrandHeader: View {
    let bridgeName: String
    let bridgeEnabled: Bool

    var body: some View {
        HStack(spacing: 14) {
            Image("LeoJarvisLogo")
                .resizable()
                .scaledToFill()
                .frame(width: 58, height: 58)
                .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
                .overlay(
                    RoundedRectangle(cornerRadius: 8, style: .continuous)
                        .stroke(Color.blue.opacity(0.34), lineWidth: 1)
                )

            VStack(alignment: .leading, spacing: 3) {
                Text("LeoJarvis")
                    .font(.title2.weight(.bold))
                Text(bridgeEnabled ? "本机与三台 Mac · \(bridgeName)" : "本机与三台 Mac · 备用直连 SSH")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
            }

            Spacer(minLength: 0)
        }
        .padding(14)
        .background(.background, in: RoundedRectangle(cornerRadius: 8, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 8, style: .continuous)
                .stroke(Color.blue.opacity(0.18), lineWidth: 1)
        )
    }
}

struct LocalDeviceCard: View {
    let snapshot: LocalDeviceSnapshot
    @State private var isExpanded = false

    private var tone: HealthTone { .local(health: snapshot.health) }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Button {
                withAnimation(.snappy(duration: 0.2)) {
                    isExpanded.toggle()
                }
            } label: {
                HStack(alignment: .top) {
                    VStack(alignment: .leading, spacing: 4) {
                        Label("本机", systemImage: "iphone")
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(.secondary)
                        Text(snapshot.name)
                            .font(.title2.weight(.bold))
                            .foregroundStyle(.primary)
                        Text("\(snapshot.interfaceIdiom) · \(snapshot.modelIdentifier)")
                            .font(.footnote)
                            .foregroundStyle(.secondary)
                        Text("\(snapshot.systemVersion) · build \(snapshot.osBuild)")
                            .font(.caption2)
                            .foregroundStyle(.tertiary)
                            .lineLimit(1)
                            .minimumScaleFactor(0.8)
                    }
                    Spacer()
                    VStack(alignment: .trailing, spacing: 3) {
                        Text("\(Int(snapshot.health.rounded()))")
                            .font(.system(size: 34, weight: .bold, design: .rounded))
                            .foregroundStyle(tone.color)
                        HStack(spacing: 4) {
                            Text("本机健康")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                            Image(systemName: isExpanded ? "chevron.up" : "chevron.down")
                                .font(.caption.weight(.bold))
                                .foregroundStyle(.secondary)
                        }
                    }
                }
            }
            .buttonStyle(.plain)

            HStack(spacing: 10) {
                MetricTile(title: "电量", value: batteryText, detail: snapshot.batteryState, systemImage: "battery.75percent")
                MetricTile(title: "存储", value: percent(snapshot.storageUsedPercent), detail: "可用 \(format(snapshot.storageFreeGB))G", systemImage: "internaldrive")
            }

            if isExpanded {
                HStack(spacing: 10) {
                    MetricTile(title: "电池健康", value: snapshot.batteryHealth, detail: snapshot.batteryHealthDetail, systemImage: "heart.text.square")
                    MetricTile(title: "可清理空间", value: "\(format(snapshot.storageAvailableOpportunisticGB))G", detail: "系统评估", systemImage: "arrow.triangle.2.circlepath")
                }

                HStack(spacing: 10) {
                    MetricTile(title: "内存", value: "\(format(snapshot.memoryTotalGB))G", detail: "物理内存", systemImage: "memorychip")
                    MetricTile(title: "CPU", value: "\(snapshot.activeProcessorCount)/\(snapshot.processorCount)", detail: "活跃/总核心", systemImage: "cpu")
                }

                HStack(spacing: 10) {
                    MetricTile(title: "屏幕", value: snapshot.screenDescription, detail: screenDetail, systemImage: "display")
                    MetricTile(title: "温控", value: snapshot.thermalState, detail: snapshot.lowPowerMode ? "低电量模式" : "正常功耗", systemImage: "thermometer.medium")
                }

                HStack(spacing: 10) {
                    MetricTile(title: "运行时间", value: uptimeText, detail: "本次开机", systemImage: "clock")
                    MetricTile(title: "地区", value: snapshot.localeIdentifier, detail: snapshot.timeZoneIdentifier, systemImage: "globe.asia.australia")
                }

                ForEach(snapshot.risks.prefix(2)) { risk in
                    RiskLine(risk: risk)
                }
            }
        }
        .padding(16)
        .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 8, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 8, style: .continuous)
                .stroke(tone.color.opacity(0.25), lineWidth: 1)
        )
    }

    private var batteryText: String {
        guard let value = snapshot.batteryPercent else { return "-" }
        return "\(Int(value.rounded()))%"
    }

    private var screenDetail: String {
        "\(snapshot.maxFramesPerSecond)Hz · \(format(snapshot.screenScale))x"
    }

    private var uptimeText: String {
        if snapshot.uptimeHours < 24 { return "\(format(snapshot.uptimeHours))h" }
        return "\(format(snapshot.uptimeHours / 24))d"
    }

    private func percent(_ value: Double) -> String {
        "\(Int(value.rounded()))%"
    }

    private func format(_ value: Double) -> String {
        value == value.rounded() ? "\(Int(value))" : String(format: "%.1f", value)
    }
}

struct MetricTile: View {
    let title: String
    let value: String
    let detail: String
    let systemImage: String

    var body: some View {
        HStack(spacing: 9) {
            Image(systemName: systemImage)
                .foregroundStyle(.tint)
                .frame(width: 22)
            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                Text(value)
                    .font(.subheadline.weight(.semibold))
                    .lineLimit(1)
                    .minimumScaleFactor(0.75)
                Text(detail)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                    .minimumScaleFactor(0.75)
            }
            Spacer(minLength: 0)
        }
        .padding(11)
        .frame(maxWidth: .infinity, minHeight: 70)
        .background(.background.opacity(0.72), in: RoundedRectangle(cornerRadius: 8, style: .continuous))
    }
}

struct MessageBanner: View {
    let text: String
    let level: HealthRisk.Level

    var body: some View {
        Label(text, systemImage: level.symbol)
            .font(.callout)
            .foregroundStyle(level.color)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(12)
            .background(level.color.opacity(0.12), in: RoundedRectangle(cornerRadius: 8, style: .continuous))
    }
}

struct RiskLine: View {
    let risk: HealthRisk

    var body: some View {
        Label {
            VStack(alignment: .leading, spacing: 2) {
                Text(risk.title)
                    .font(.caption.weight(.semibold))
                Text(risk.advice)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
        } icon: {
            Image(systemName: risk.level.symbol)
                .foregroundStyle(risk.level.color)
        }
    }
}
