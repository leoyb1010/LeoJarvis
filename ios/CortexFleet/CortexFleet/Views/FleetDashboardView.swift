import SwiftUI
import SwiftData
import Charts

/// Device page (第四页). iPhone-first: the local device is the hero card with a
/// trend chart; SSH hosts are a collapsible, manually-probed section (no more
/// 30s auto-refresh). All remote "capability" cards are gone — iOS is self-contained.
struct FleetDashboardView: View {
    @EnvironmentObject private var store: FleetStore
    @Environment(\.modelContext) private var context

    @Query(sort: [SortDescriptor(\DeviceSample.timestamp, order: .forward)])
    private var samples: [DeviceSample]

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Brand.stack) {
                LocalDeviceCard(snapshot: store.localSnapshot)

                if recentSamples.count >= 2 {
                    DeviceTrendCard(samples: recentSamples)
                }

                CollapsibleSection(
                    title: "SSH 主机",
                    systemImage: "server.rack",
                    count: store.hosts.count,
                    accent: .indigo,
                    defaultExpanded: false,
                    storageKey: "device.sshHosts"
                ) {
                    sshSectionBody
                }

                if let message = store.errorMessage {
                    MessageBanner(text: message, level: .bad)
                } else if let message = store.noticeMessage {
                    MessageBanner(text: message, level: .good)
                }
            }
            .padding(16)
        }
        .navigationTitle("设备")
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Button { store.refreshLocal(); recordSample() } label: {
                    Image(systemName: "arrow.clockwise")
                }
                .accessibilityLabel("刷新本机")
            }
        }
        .refreshable {
            store.refreshLocal()
            recordSample()
        }
        .task {
            store.refreshLocal()
            recordSample()
        }
    }

    @ViewBuilder
    private var sshSectionBody: some View {
        if store.hosts.isEmpty {
            EmptyHint(text: "没有配置 SSH 主机。可在设置页添加直连主机后手动探测。", systemImage: "terminal")
        } else {
            HStack {
                Text("\(store.remoteOnlineCount)/\(store.hosts.count) 在线")
                    .font(.caption).foregroundStyle(.secondary)
                Spacer()
                Button {
                    Task { await store.refreshAll() }
                } label: {
                    Label(store.isRefreshing ? "探测中…" : "探测全部", systemImage: "bolt.horizontal.circle")
                        .font(.caption.weight(.semibold))
                }
                .disabled(store.isRefreshing)
            }
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

    private var recentSamples: [DeviceSample] {
        Array(samples.suffix(48))
    }

    /// Record a lightweight metric sample (throttled to ~once per 10 min) for the trend chart.
    private func recordSample() {
        let snap = store.localSnapshot
        if let last = samples.last, Date().timeIntervalSince(last.timestamp) < 600 { return }
        let sample = DeviceSample(
            batteryPercent: snap.batteryPercent,
            storageUsedPercent: snap.storageUsedPercent,
            memoryUsedPercent: nil,
            thermal: snap.thermalState
        )
        context.insert(sample)
        // Keep only the most recent ~200 samples.
        if samples.count > 200 {
            for old in samples.prefix(samples.count - 200) { context.delete(old) }
        }
        try? context.save()
    }
}

private struct DeviceTrendCard: View {
    let samples: [DeviceSample]

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            SectionHeader(title: "本机趋势", subtitle: "电量与存储占用", systemImage: "chart.xyaxis.line")
            Chart {
                ForEach(samples) { s in
                    if let battery = s.batteryPercent {
                        LineMark(
                            x: .value("时间", s.timestamp),
                            y: .value("电量", battery)
                        )
                        .foregroundStyle(by: .value("指标", "电量%"))
                        .interpolationMethod(.catmullRom)
                    }
                    LineMark(
                        x: .value("时间", s.timestamp),
                        y: .value("存储", s.storageUsedPercent)
                    )
                    .foregroundStyle(by: .value("指标", "存储占用%"))
                    .interpolationMethod(.catmullRom)
                }
            }
            .chartYScale(domain: 0...100)
            .chartForegroundStyleScale(["电量%": Color.green, "存储占用%": Color.orange])
            .frame(height: 160)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .jarvisCard()
    }
}
