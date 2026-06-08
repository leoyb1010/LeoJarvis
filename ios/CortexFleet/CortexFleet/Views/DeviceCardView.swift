import SwiftUI

struct DeviceCardView: View {
    let snapshot: HostSnapshot

    private var tone: HealthTone {
        .remote(isOnline: snapshot.isOnline, health: snapshot.health, status: snapshot.status)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(alignment: .top, spacing: 12) {
                Image(systemName: tone.symbol)
                    .font(.title3)
                    .foregroundStyle(tone.color)
                    .frame(width: 28, height: 28)

                VStack(alignment: .leading, spacing: 3) {
                    Text(snapshot.name)
                        .font(.headline)
                        .foregroundStyle(.primary)
                        .lineLimit(1)
                    Text(snapshot.address)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }

                Spacer()

                VStack(alignment: .trailing, spacing: 2) {
                    Text(snapshot.isOnline ? "\(Int(snapshot.health.rounded()))" : "-")
                        .font(.system(.title2, design: .rounded, weight: .bold))
                        .foregroundStyle(tone.color)
                    Text(snapshot.status)
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(.secondary)
                }
            }

            HStack(spacing: 10) {
                MetricTile(title: "CPU", value: percent(snapshot.metrics.cpuLoadPct), detail: cpuDetail, systemImage: "cpu")
                MetricTile(title: "RAM", value: percent(snapshot.metrics.ramUsedPct), detail: ramDetail, systemImage: "memorychip")
            }

            HStack(spacing: 10) {
                MetricTile(title: "Disk", value: percent(snapshot.metrics.diskUsedPct), detail: diskDetail, systemImage: "externaldrive")
                MetricTile(title: "服务", value: "\(snapshot.services.online)/\(snapshot.services.total)", detail: "本机端口", systemImage: "point.3.connected.trianglepath.dotted")
            }

            if let risk = snapshot.risks.first {
                RiskLine(risk: risk)
            } else if snapshot.isOnline {
                RiskLine(risk: .init(title: "暂无风险项", advice: "最近一次 SSH 探测未发现异常。", level: .good))
            }
        }
        .padding(14)
        .background(.background, in: RoundedRectangle(cornerRadius: 8, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 8, style: .continuous)
                .stroke(tone.color.opacity(0.24), lineWidth: 1)
        )
    }

    private var cpuDetail: String {
        if let load = snapshot.metrics.cpuLoad, let cores = snapshot.metrics.cpuCores {
            return "\(format(load)) / \(format(cores)) 核"
        }
        return "负载"
    }

    private var ramDetail: String {
        if let used = snapshot.metrics.ramUsedGB, let total = snapshot.metrics.ramTotalGB {
            return "\(format(used))G / \(format(total))G"
        }
        return "内存"
    }

    private var diskDetail: String {
        if let free = snapshot.metrics.diskFreeGB {
            return "剩余 \(format(free))G"
        }
        return "磁盘"
    }

    private func percent(_ value: Double?) -> String {
        guard let value else { return "-" }
        return "\(Int(value.rounded()))%"
    }

    private func format(_ value: Double) -> String {
        value == value.rounded() ? "\(Int(value))" : String(format: "%.1f", value)
    }
}
