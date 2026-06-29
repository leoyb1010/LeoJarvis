import SwiftUI

// 状态/信号可视化原子组件：在线脉冲点、呼吸光晕、延迟条、百分比进度条。
// 跨 feature 共享（Home/Agents/Devices/Chat 都用），从 Views.swift 拆出。

struct AnimatedStatusDot: View {
    let online: Bool
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var pulsing = false

    var body: some View {
        ZStack {
            if online {
                Circle()
                    .stroke(AppTheme.success.opacity(pulsing ? 0.0 : 0.42), lineWidth: 2)
                    .frame(width: 15, height: 15)
                    .scaleEffect(pulsing ? 1.6 : 1)
                    .animation(
                        reduceMotion ? nil : .easeOut(duration: 1.4).repeatForever(autoreverses: false),
                        value: pulsing
                    )
            }
            Circle()
                .fill(online ? AppTheme.success : AppTheme.warn)
                .frame(width: 8, height: 8)
        }
        .onAppear { if online && !reduceMotion { pulsing = true } }
        .onChange(of: online) { _, isOnline in pulsing = isOnline && !reduceMotion }
    }
}

struct LiveHalo: View {
    let online: Bool
    let tint: Color
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var breathing = false

    var body: some View {
        ZStack {
            ForEach(0..<3, id: \.self) { index in
                Circle()
                    .stroke(tint.opacity(online ? 0.20 : 0.10), lineWidth: 1.2)
                    .scaleEffect(CGFloat(0.72 + Double(index) * 0.16) * (breathing ? 1.08 : 1))
                    .opacity((online ? 0.36 : 0.18) * (breathing ? 0.7 : 1))
                    .animation(
                        reduceMotion || !online ? nil :
                            .easeInOut(duration: 1.8)
                            .repeatForever(autoreverses: true)
                            .delay(Double(index) * 0.22),
                        value: breathing
                    )
            }
            Circle()
                .fill(tint.opacity(online ? 0.16 : 0.12))
            Image(systemName: online ? "antenna.radiowaves.left.and.right" : "wifi.exclamationmark")
                .font(.system(size: 18, weight: .heavy))
                .foregroundStyle(tint)
        }
        .onAppear { if online && !reduceMotion { breathing = true } }
        .onChange(of: online) { _, isOnline in breathing = isOnline && !reduceMotion }
    }
}

struct LatencyBars: View {
    let latencyMs: Int?
    let online: Bool

    var body: some View {
        HStack(alignment: .bottom, spacing: 2) {
            ForEach(0..<4, id: \.self) { index in
                Capsule()
                    .fill(barTint(index))
                    .frame(width: 4, height: CGFloat(5 + index * 3))
                    .opacity(isLit(index) ? 1 : 0.22)
            }
        }
        .frame(height: 16)
        .accessibilityLabel(latencyMs.map { "延迟 \($0) 毫秒" } ?? "尚未测速")
    }

    private func isLit(_ index: Int) -> Bool {
        guard online, let latencyMs else { return false }
        if latencyMs <= 180 { return true }
        if latencyMs <= 420 { return index < 3 }
        if latencyMs <= 900 { return index < 2 }
        return index == 0
    }

    private func barTint(_ index: Int) -> Color {
        guard online, let latencyMs else { return AppTheme.faint }
        if latencyMs <= 180 { return AppTheme.success }
        if latencyMs <= 650 { return AppTheme.warn }
        return index == 0 ? AppTheme.danger : AppTheme.warn
    }
}

struct MetricBar: View {
    let value: Double?
    let tint: Color

    var body: some View {
        GeometryReader { proxy in
            ZStack(alignment: .leading) {
                Capsule()
                    .fill(AppTheme.line)
                Capsule()
                    .fill(tint)
                    .frame(width: proxy.size.width * CGFloat(value ?? 0))
                    .animation(AppMotion.spring, value: value ?? 0)
            }
        }
        .frame(height: 4)
        .opacity(value == nil ? 0 : 1)
    }
}
