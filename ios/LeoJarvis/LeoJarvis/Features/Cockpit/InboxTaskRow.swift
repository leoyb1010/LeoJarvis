import SwiftUI

// 待办收件箱行：信息→任务，带确认/完成/忽略轻操作。高风险任务红色标注。
struct InboxTaskRow: View {
    let task: InboxTask
    let onConfirm: () -> Void
    let onDone: () -> Void
    let onIgnore: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .top, spacing: 8) {
                Image(systemName: task.isHighRisk ? "exclamationmark.triangle.fill" : actionIcon)
                    .font(.system(size: 14, weight: .heavy))
                    .foregroundStyle(task.isHighRisk ? AppTheme.danger : AppTheme.accent)
                    .frame(width: 26, height: 26)
                    .background((task.isHighRisk ? AppTheme.danger : AppTheme.accent).opacity(0.12),
                                in: RoundedRectangle(cornerRadius: 8, style: .continuous))
                VStack(alignment: .leading, spacing: 3) {
                    Text(task.displayTitle)
                        .font(.system(size: 14, weight: .heavy))
                        .foregroundStyle(AppTheme.ink)
                        .lineLimit(2)
                    if let preview = nonEmpty(task.context_preview) ?? nonEmpty(task.suggestion) {
                        Text(preview)
                            .font(.system(size: 12, weight: .semibold))
                            .foregroundStyle(AppTheme.muted)
                            .lineLimit(2)
                    }
                    HStack(spacing: 6) {
                        if let origin = nonEmpty(task.origin) {
                            StatusPill(title: originLabel(origin), icon: nil, tint: AppTheme.muted)
                        }
                        if let due = nonEmpty(task.due) {
                            StatusPill(title: due, icon: "clock", tint: AppTheme.warn)
                        }
                        if task.isHighRisk {
                            StatusPill(title: "高风险", icon: nil, tint: AppTheme.danger)
                        }
                    }
                }
                Spacer(minLength: 0)
            }
            HStack(spacing: 8) {
                actionButton(title: "确认", icon: "checkmark", tint: AppTheme.accent, action: onConfirm)
                actionButton(title: "完成", icon: "checkmark.circle", tint: AppTheme.success, action: onDone)
                actionButton(title: "忽略", icon: "xmark", tint: AppTheme.muted, action: onIgnore)
            }
        }
        .padding(.vertical, 4)
    }

    private var actionIcon: String {
        switch (task.action ?? "").lowercased() {
        case "reply": return "arrowshape.turn.up.left"
        case "review": return "doc.text.magnifyingglass"
        case "create": return "plus"
        case "follow_up": return "arrow.uturn.right"
        case "approve": return "checkmark.shield"
        default: return "circle"
        }
    }

    private func originLabel(_ o: String) -> String {
        switch o.lowercased() {
        case "email": return "邮件"
        case "im": return "消息"
        case "intel": return "情报"
        case "manual": return "手动"
        default: return o
        }
    }

    private func actionButton(title: String, icon: String, tint: Color, action: @escaping () -> Void) -> some View {
        Button {
            Haptics.lightImpact()
            action()
        } label: {
            Label(title, systemImage: icon)
                .font(.system(size: 12, weight: .heavy))
                .foregroundStyle(tint)
                .frame(maxWidth: .infinity)
                .frame(height: 34)
                .background(tint.opacity(0.10), in: Capsule())
        }
        .buttonStyle(PressScaleButtonStyle())
    }
}
