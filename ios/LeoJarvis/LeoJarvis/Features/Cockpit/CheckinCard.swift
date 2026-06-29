import SwiftUI

// 主动助理 check-in 卡片：一键跑早报/午间/晚结，展示助理回复。轻操作，需 Mac 在线。
struct CheckinCard: View {
    @EnvironmentObject private var store: JarvisStore
    @State private var running: String?      // 正在跑的 slot
    @State private var reply: String = ""
    @State private var replyTitle: String = ""

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                SectionTitle(title: "主动助理", icon: "sun.max")
                Spacer()
            }
            HStack(spacing: 8) {
                slotButton("早报", slot: "morning", icon: "sunrise")
                slotButton("午间", slot: "midday", icon: "sun.max")
                slotButton("晚结", slot: "evening", icon: "sunset")
            }
            if !reply.isEmpty {
                VStack(alignment: .leading, spacing: 6) {
                    if !replyTitle.isEmpty {
                        Text(replyTitle)
                            .font(.system(size: 13, weight: .heavy))
                            .foregroundStyle(AppTheme.accent)
                    }
                    Text(reply)
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundStyle(AppTheme.ink)
                        .lineSpacing(3)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(12)
                .background(AppTheme.elevated, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
            }
        }
        .panel()
    }

    private func slotButton(_ title: String, slot: String, icon: String) -> some View {
        Button {
            Task { await run(slot) }
        } label: {
            VStack(spacing: 4) {
                if running == slot {
                    ProgressView().tint(AppTheme.accent)
                } else {
                    Image(systemName: icon)
                        .font(.system(size: 16, weight: .heavy))
                }
                Text(title)
                    .font(.system(size: 12, weight: .heavy))
            }
            .foregroundStyle(store.isMacReachable ? AppTheme.accent : AppTheme.faint)
            .frame(maxWidth: .infinity)
            .frame(height: 56)
            .background(AppTheme.accentSoft, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
        }
        .buttonStyle(PressScaleButtonStyle())
        .disabled(!store.isMacReachable || running != nil)
    }

    private func run(_ slot: String) async {
        Haptics.lightImpact()
        running = slot; defer { running = nil }
        if let result = await store.runCheckin(slot: slot) {
            reply = result.reply ?? "（无内容）"
            replyTitle = result.title ?? ""
        }
    }
}
