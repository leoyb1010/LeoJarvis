import SwiftUI

// Shared building blocks used across the device, detail, settings and overview
// screens. (Previously these lived in FleetDashboardView.swift.)

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
        .background(.background.opacity(0.72), in: RoundedRectangle(cornerRadius: Brand.tileCorner, style: .continuous))
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
            .background(level.color.opacity(0.12), in: RoundedRectangle(cornerRadius: Brand.tileCorner, style: .continuous))
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

/// Local iPhone/iPad hero card with expandable detail. Now surfaces the extra
/// open APIs (network, brightness, dark mode, available memory).
struct LocalDeviceCard: View {
    let snapshot: LocalDeviceSnapshot
    @State private var isExpanded = false

    private var tone: HealthTone { .local(health: snapshot.health) }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Button {
                withAnimation(.snappy(duration: 0.2)) { isExpanded.toggle() }
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
            HStack(spacing: 10) {
                MetricTile(title: "网络", value: snapshot.networkType, detail: snapshot.networkExpensive ? "计费网络" : "正常", systemImage: "wifi")
                MetricTile(title: "温控", value: snapshot.thermalState, detail: snapshot.lowPowerMode ? "低电量模式" : "正常功耗", systemImage: "thermometer.medium")
            }

            if isExpanded {
                HStack(spacing: 10) {
                    MetricTile(title: "可用内存", value: availableMemoryText, detail: "App 可用", systemImage: "memorychip")
                    MetricTile(title: "内存", value: "\(format(snapshot.memoryTotalGB))G", detail: "物理内存", systemImage: "memorychip.fill")
                }
                HStack(spacing: 10) {
                    MetricTile(title: "可清理空间", value: "\(format(snapshot.storageAvailableOpportunisticGB))G", detail: "系统评估", systemImage: "arrow.triangle.2.circlepath")
                    MetricTile(title: "CPU", value: "\(snapshot.activeProcessorCount)/\(snapshot.processorCount)", detail: "活跃/总核心", systemImage: "cpu")
                }
                HStack(spacing: 10) {
                    MetricTile(title: "屏幕", value: snapshot.screenDescription, detail: screenDetail, systemImage: "display")
                    MetricTile(title: "亮度", value: "\(Int((snapshot.screenBrightness * 100).rounded()))%", detail: snapshot.darkMode ? "深色模式" : "浅色模式", systemImage: "sun.max")
                }
                HStack(spacing: 10) {
                    MetricTile(title: "电池健康", value: snapshot.batteryHealth, detail: snapshot.batteryHealthDetail, systemImage: "heart.text.square")
                    MetricTile(title: "运行时间", value: uptimeText, detail: "本次开机", systemImage: "clock")
                }
                HStack(spacing: 10) {
                    MetricTile(title: "地区", value: snapshot.localeIdentifier, detail: snapshot.timeZoneIdentifier, systemImage: "globe.asia.australia")
                    MetricTile(title: "刷新率", value: "\(snapshot.maxFramesPerSecond)Hz", detail: "\(format(snapshot.screenScale))x", systemImage: "speedometer")
                }

                ForEach(snapshot.risks.prefix(3)) { risk in
                    RiskLine(risk: risk)
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(Brand.cardPadding)
        .background(.thinMaterial, in: RoundedRectangle(cornerRadius: Brand.corner, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: Brand.corner, style: .continuous)
                .stroke(tone.color.opacity(0.25), lineWidth: 1)
        )
    }

    private var batteryText: String {
        guard let value = snapshot.batteryPercent else { return "-" }
        return "\(Int(value.rounded()))%"
    }

    private var availableMemoryText: String {
        guard let value = snapshot.availableMemoryGB else { return "-" }
        return "\(format(value))G"
    }

    private var screenDetail: String {
        "\(snapshot.maxFramesPerSecond)Hz · \(format(snapshot.screenScale))x"
    }

    private var uptimeText: String {
        if snapshot.uptimeHours < 24 { return "\(format(snapshot.uptimeHours))h" }
        return "\(format(snapshot.uptimeHours / 24))d"
    }

    private func percent(_ value: Double) -> String { "\(Int(value.rounded()))%" }

    private func format(_ value: Double) -> String {
        value == value.rounded() ? "\(Int(value))" : String(format: "%.1f", value)
    }
}
