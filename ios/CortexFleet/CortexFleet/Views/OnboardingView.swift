import SwiftUI
import SwiftData

/// First-launch onboarding: pick interest channels (tunes which feeds stay
/// enabled) and a nudge to configure the AI endpoint. Shown once.
struct OnboardingView: View {
    @Environment(\.modelContext) private var context
    @EnvironmentObject private var llmConfig: LLMConfigStore
    @Binding var done: Bool

    @State private var picked: Set<Channel> = [.recommended, .ai, .tech, .world, .finance, .china]
    @State private var page = 0

    private let pickable: [Channel] = [.ai, .tech, .world, .finance, .china, .engineering, .science, .github]

    var body: some View {
        VStack(spacing: 0) {
            TabView(selection: $page) {
                welcome.tag(0)
                channelPicker.tag(1)
            }
            .tabViewStyle(.page(indexDisplayMode: .always))

            Button {
                if page == 0 { withAnimation { page = 1 } } else { finish() }
            } label: {
                Text(page == 0 ? "开始" : "进入 J.A.R.V.I.S")
                    .font(.hudDisplay(17, .bold)).foregroundStyle(Brand.void)
                    .frame(maxWidth: .infinity).padding()
                    .background(LinearGradient(colors: [Brand.accent, Color(red: 0.1, green: 0.66, blue: 0.84)],
                                               startPoint: .leading, endPoint: .trailing),
                                in: Capsule())
                    .shadow(color: Brand.accent.opacity(0.6), radius: 12)
            }
            .padding()
        }
    }

    private var welcome: some View {
        VStack(spacing: 22) {
            Spacer()
            ArcRing(progress: 0.78, size: 130, color: Brand.accent, label: "J")
            Text("J.A.R.V.I.S").font(.hudDisplay(36, .bold)).foregroundStyle(Brand.hudText)
                .tracking(4)
            Text("你的本地智能资讯与助理：\n多频道资讯、AI 整理笔记、全能助手，全部在 iPhone 上运行。")
                .font(.hudMono(12)).multilineTextAlignment(.center)
                .foregroundStyle(Brand.hudText.opacity(0.6)).padding(.horizontal, 32)
            Spacer()
        }
    }

    private var channelPicker: some View {
        VStack(spacing: 16) {
            Text("选择你感兴趣的频道").font(.hudDisplay(22, .bold)).foregroundStyle(Brand.hudText).padding(.top, 40)
            Text("// 据此调整首页和信源").font(.hudMono(11)).foregroundStyle(Brand.accent.opacity(0.7))
            LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 12) {
                ForEach(pickable) { ch in
                    let on = picked.contains(ch)
                    Button { if on { picked.remove(ch) } else { picked.insert(ch) } } label: {
                        HStack {
                            Image(systemName: ch.symbol)
                            Text(ch.title).font(.hudMono(13, .medium))
                            Spacer()
                            if on { Image(systemName: "checkmark.circle.fill") }
                        }
                        .foregroundStyle(on ? Brand.void : ch.tint)
                        .padding()
                        .background(on ? AnyShapeStyle(ch.tint) : AnyShapeStyle(Brand.panel.opacity(0.35)), in: RoundedRectangle(cornerRadius: 12))
                        .overlay(RoundedRectangle(cornerRadius: 12).stroke(ch.tint.opacity(on ? 0 : 0.4), lineWidth: 1))
                    }.buttonStyle(.plain)
                }
            }.padding(.horizontal)
            if !llmConfig.hasKey {
                Label("进入后到「设置 → AI 录入接口」填 Key 即可扫描资讯。", systemImage: "info.circle")
                    .font(.hudMono(10)).foregroundStyle(Brand.hudText.opacity(0.5)).padding(.horizontal)
            }
            Spacer()
        }
    }

    private func finish() {
        // Disable feeds whose channel wasn't picked (keep at least the picked set).
        let feeds = (try? context.fetch(FetchDescriptor<FeedSource>())) ?? []
        let pickedIDs = Set(picked.map(\.rawValue))
        for f in feeds { f.enabled = pickedIDs.contains(f.channel) }
        try? context.save()
        UserDefaults.standard.set(true, forKey: "onboarding.done")
        withAnimation { done = true }
    }
}
