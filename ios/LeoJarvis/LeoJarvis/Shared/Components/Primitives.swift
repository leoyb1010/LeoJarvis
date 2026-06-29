import SwiftUI

// 基础 UI 原件：标题、徽标、筛选 pill、设置行、加载条、空状态、错误/信息横幅。
// 跨 feature 共享，从 Views.swift 拆出。

struct SectionTitle: View {
    let title: String
    let icon: String

    var body: some View {
        Label(title, systemImage: icon)
            .font(.system(size: 15, weight: .heavy))
            .foregroundStyle(AppTheme.ink)
    }
}

struct StatusPill: View {
    let title: String
    let icon: String?
    let tint: Color
    var filled = false

    var body: some View {
        HStack(spacing: 4) {
            if let icon {
                Image(systemName: icon)
                    .font(.system(size: 10, weight: .heavy))
            }
            Text(title)
                .font(.system(size: 10, weight: .heavy))
                .lineLimit(1)
                .minimumScaleFactor(0.75)
        }
        .foregroundStyle(filled ? AppTheme.onAccent : tint)
        .padding(.horizontal, 8)
        .padding(.vertical, 5)
        .background((filled ? tint : tint.opacity(0.12)), in: Capsule())
    }
}

struct FilterPill<Value: Hashable>: View {
    let title: String
    let value: Value
    @Binding var selection: Value

    var body: some View {
        Button {
            Haptics.selection()
            withAnimation(.snappy) { selection = value }
        } label: {
            Text(title)
                .font(.system(size: 12, weight: .heavy))
                .foregroundStyle(selection == value ? AppTheme.onAccent : AppTheme.ink)
                .frame(maxWidth: .infinity)
                .frame(height: 34)
                .background(selection == value ? AppTheme.accent : AppTheme.elevated, in: Capsule())
                .overlay(Capsule().stroke(selection == value ? Color.clear : AppTheme.line, lineWidth: 1))
        }
        .buttonStyle(.plain)
    }
}

struct SettingsLine: View {
    let label: String
    let value: String

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            Text(label)
                .font(.system(size: 12, weight: .heavy))
                .foregroundStyle(AppTheme.muted)
                .frame(width: 58, alignment: .leading)
            Text(value)
                .font(.system(size: 13, weight: .semibold))
                .foregroundStyle(AppTheme.ink)
                .lineLimit(3)
                .truncationMode(.middle)
            Spacer(minLength: 0)
        }
    }
}

struct LoadingStrip: View {
    let text: String

    var body: some View {
        HStack(spacing: 10) {
            ProgressView()
                .tint(AppTheme.accent)
            Text(text)
                .font(.system(size: 13, weight: .heavy))
                .foregroundStyle(AppTheme.muted)
            Spacer()
        }
        .compactPanel()
        .shimmer()
    }
}

struct EmptyState: View {
    let text: String
    let systemImage: String

    var body: some View {
        VStack(spacing: 10) {
            Image(systemName: systemImage)
                .font(.system(size: 24, weight: .heavy))
                .foregroundStyle(AppTheme.faint)
            Text(text)
                .font(.system(size: 13, weight: .semibold))
                .foregroundStyle(AppTheme.muted)
                .multilineTextAlignment(.center)
                .lineSpacing(3)
        }
        .frame(maxWidth: .infinity, minHeight: 120)
    }
}

struct ErrorBanner: View {
    enum Tone { case error, info }
    let message: String
    var tone: Tone = .error

    private var icon: String { tone == .error ? "exclamationmark.triangle.fill" : "info.circle.fill" }
    private var fg: Color { tone == .error ? AppTheme.onAccent : AppTheme.ink }

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: icon)
                .font(.system(size: 13, weight: .heavy))
                .foregroundStyle(tone == .error ? AppTheme.onAccent : AppTheme.accent)
            Text(message)
                .font(.system(size: 12, weight: .semibold))
                .lineLimit(2)
            Spacer()
        }
        .foregroundStyle(fg)
        .padding(12)
        .background {
            if tone == .error {
                RoundedRectangle(cornerRadius: 13, style: .continuous).fill(AppTheme.danger)
            } else {
                // 非红：玻璃面板 + 细边，安静告知不惊吓
                RoundedRectangle(cornerRadius: 13, style: .continuous)
                    .fill(AppTheme.panel)
                    .overlay(RoundedRectangle(cornerRadius: 13, style: .continuous).stroke(AppTheme.line, lineWidth: 1))
            }
        }
        .shadow(color: AppTheme.shadow, radius: 10, y: 5)
    }
}
