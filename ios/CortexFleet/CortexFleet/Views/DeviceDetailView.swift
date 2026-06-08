import SwiftUI

struct DeviceDetailView: View {
    @EnvironmentObject private var store: FleetStore

    let hostID: String

    private var snapshot: HostSnapshot {
        if let snapshot = store.snapshots[hostID] {
            return snapshot
        }
        if let host = store.hosts.first(where: { $0.id == hostID }) {
            return .pending(for: host)
        }
        return .pending(for: MonitoredHost(id: hostID, name: "主机", host: "-", port: 22, username: "-", enabled: false))
    }

    private var tone: HealthTone {
        .remote(isOnline: snapshot.isOnline, health: snapshot.health, status: snapshot.status)
    }

    private var serviceRows: [HostServiceStatus] {
        snapshot.services.items.sorted {
            if $0.isRunning != $1.isRunning { return $0.isRunning && !$1.isRunning }
            if $0.kind != $1.kind { return $0.kind < $1.kind }
            return $0.name < $1.name
        }
    }

    private var cliRows: [HostCLIStatus] {
        snapshot.cliTools.sorted {
            if $0.isRunning != $1.isRunning { return $0.isRunning && !$1.isRunning }
            if $0.isAvailable != $1.isAvailable { return $0.isAvailable && !$1.isAvailable }
            return $0.name < $1.name
        }
    }

    var body: some View {
        List {
            Section {
                VStack(alignment: .leading, spacing: 12) {
                    HStack {
                        Label(snapshot.status, systemImage: tone.symbol)
                            .font(.headline)
                            .foregroundStyle(tone.color)
                        Spacer()
                        Text(snapshot.isOnline ? "\(Int(snapshot.health.rounded()))" : "-")
                            .font(.system(size: 38, weight: .bold, design: .rounded))
                            .foregroundStyle(tone.color)
                    }
                    Text(snapshot.address)
                        .font(.callout)
                        .foregroundStyle(.secondary)
                    Text(snapshot.privacy)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                .padding(.vertical, 6)
            }

            Section("系统") {
                DetailRow(title: "OS", value: snapshot.os, detail: "")
                DetailRow(title: "架构", value: snapshot.model, detail: "")
                DetailRow(title: "运行时间", value: uptimeText, detail: "")
            }

            Section("核心指标") {
                DetailRow(title: "CPU", value: percent(snapshot.metrics.cpuLoadPct), detail: cpuDetail)
                DetailRow(title: "RAM", value: percent(snapshot.metrics.ramUsedPct), detail: ramDetail)
                DetailRow(title: "Disk", value: percent(snapshot.metrics.diskUsedPct), detail: diskDetail)
                DetailRow(title: "服务", value: "\(snapshot.services.online)/\(snapshot.services.total)", detail: "运行中")
            }

            Section("服务状态") {
                if serviceRows.isEmpty {
                    Text(snapshot.isOnline ? "暂无服务数据" : "主机在线后显示服务数据")
                        .foregroundStyle(.secondary)
                } else {
                    ForEach(serviceRows) { service in
                        ServiceStatusRow(service: service)
                    }
                }
            }

            Section("编程 CLI") {
                if cliRows.isEmpty {
                    Text(snapshot.isOnline ? "暂无 CLI 数据" : "主机在线后显示 CLI 数据")
                        .foregroundStyle(.secondary)
                } else {
                    ForEach(cliRows) { cli in
                        CLIStatusRow(cli: cli)
                    }
                }
            }

            Section("高占用进程") {
                if snapshot.topProcesses.isEmpty {
                    Text("暂无进程数据")
                        .foregroundStyle(.secondary)
                } else {
                    ForEach(snapshot.topProcesses) { process in
                        VStack(alignment: .leading, spacing: 3) {
                            Text(process.command)
                                .font(.body.weight(.semibold))
                            Text("pid \(process.pid) · CPU \(process.cpu)% · MEM \(process.mem)%")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    }
                }
            }

            Section("风险") {
                if snapshot.risks.isEmpty {
                    RiskLine(risk: .init(title: "暂无风险项", advice: "最近一次 SSH 探测未发现异常。", level: .good))
                } else {
                    ForEach(snapshot.risks) { risk in
                        RiskLine(risk: risk)
                            .padding(.vertical, 3)
                    }
                }
            }
        }
        .navigationTitle(snapshot.name)
        .toolbar {
            Button {
                Task { await store.refreshHost(hostID) }
            } label: {
                Image(systemName: "arrow.clockwise")
            }
            .disabled(store.isRefreshing)
            .accessibilityLabel("刷新此主机")
        }
        .refreshable {
            await store.refreshHost(hostID)
        }
    }

    private var cpuDetail: String {
        if let load = snapshot.metrics.cpuLoad, let cores = snapshot.metrics.cpuCores {
            return "\(format(load)) / \(format(cores)) 核"
        }
        return ""
    }

    private var ramDetail: String {
        if let used = snapshot.metrics.ramUsedGB, let total = snapshot.metrics.ramTotalGB {
            return "\(format(used))G / \(format(total))G"
        }
        return ""
    }

    private var diskDetail: String {
        if let free = snapshot.metrics.diskFreeGB {
            return "剩余 \(format(free))G"
        }
        return ""
    }

    private var uptimeText: String {
        guard let hours = snapshot.metrics.uptimeHours else { return "-" }
        if hours < 24 { return "\(format(hours))h" }
        return "\(format(hours / 24))d"
    }

    private func percent(_ value: Double?) -> String {
        guard let value else { return "-" }
        return "\(Int(value.rounded()))%"
    }

    private func format(_ value: Double) -> String {
        value == value.rounded() ? "\(Int(value))" : String(format: "%.1f", value)
    }
}

private struct ServiceStatusRow: View {
    let service: HostServiceStatus

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: service.isRunning ? "checkmark.circle.fill" : "circle")
                .foregroundStyle(service.isRunning ? Color.green : Color.secondary)
                .frame(width: 22)

            VStack(alignment: .leading, spacing: 3) {
                Text(service.name)
                    .font(.body.weight(.semibold))
                    .lineLimit(1)
                    .minimumScaleFactor(0.8)
                Text(detailText)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
                    .minimumScaleFactor(0.8)
            }

            Spacer(minLength: 12)

            Text(service.status)
                .font(.caption.weight(.semibold))
                .foregroundStyle(service.isRunning ? Color.green : Color.secondary)
                .padding(.horizontal, 8)
                .padding(.vertical, 4)
                .background((service.isRunning ? Color.green : Color.secondary).opacity(0.12), in: Capsule())
        }
        .padding(.vertical, 3)
    }

    private var detailText: String {
        let prefix = service.port.map { "\(service.kind) · :\($0)" } ?? service.kind
        return service.detail.isEmpty ? prefix : "\(prefix) · \(service.detail)"
    }
}

private struct CLIStatusRow: View {
    let cli: HostCLIStatus

    private var color: Color {
        if cli.isRunning { return .green }
        if cli.isAvailable { return .blue }
        return .secondary
    }

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: cli.isAvailable ? "terminal.fill" : "terminal")
                .foregroundStyle(color)
                .frame(width: 22)

            VStack(alignment: .leading, spacing: 3) {
                Text(cli.name)
                    .font(.body.weight(.semibold))
                Text(cli.version ?? cli.detail)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
                    .minimumScaleFactor(0.8)
                if cli.version != nil, !cli.detail.isEmpty {
                    Text(cli.detail)
                        .font(.caption2)
                        .foregroundStyle(.tertiary)
                        .lineLimit(1)
                        .minimumScaleFactor(0.8)
                }
            }

            Spacer(minLength: 12)

            Text(cli.status)
                .font(.caption.weight(.semibold))
                .foregroundStyle(color)
                .padding(.horizontal, 8)
                .padding(.vertical, 4)
                .background(color.opacity(0.12), in: Capsule())
        }
        .padding(.vertical, 3)
    }
}

struct DetailRow: View {
    let title: String
    let value: String
    let detail: String

    var body: some View {
        HStack {
            Text(title)
            Spacer(minLength: 16)
            VStack(alignment: .trailing, spacing: 2) {
                Text(value)
                    .fontWeight(.semibold)
                    .multilineTextAlignment(.trailing)
                    .lineLimit(2)
                    .minimumScaleFactor(0.8)
                if !detail.isEmpty {
                    Text(detail)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .multilineTextAlignment(.trailing)
                        .lineLimit(2)
                        .minimumScaleFactor(0.8)
                }
            }
        }
    }
}
