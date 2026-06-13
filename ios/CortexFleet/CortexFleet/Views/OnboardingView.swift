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
                Text(page == 0 ? "开始" : "进入 Jarvis")
                    .font(.headline).foregroundStyle(.white)
                    .frame(maxWidth: .infinity).padding()
                    .background(LinearGradient(colors: [.blue, .indigo], startPoint: .leading, endPoint: .trailing),
                                in: RoundedRectangle(cornerRadius: 14))
            }
            .padding()
        }
    }

    private var welcome: some View {
        VStack(spacing: 18) {
            Spacer()
            Image(systemName: "sparkles").font(.system(size: 64)).foregroundStyle(.tint)
            Text("Jarvis").font(.largeTitle.weight(.bold))
            Text("你的本地智能资讯与助理：\n多频道资讯、AI 整理笔记、全能助手，全部在 iPhone 上运行。")
                .multilineTextAlignment(.center).foregroundStyle(.secondary).padding(.horizontal, 32)
            Spacer()
        }
    }

    private var channelPicker: some View {
        VStack(spacing: 16) {
            Text("选择你感兴趣的频道").font(.title2.weight(.bold)).padding(.top, 40)
            Text("我们会据此调整首页和信源").font(.caption).foregroundStyle(.secondary)
            LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 12) {
                ForEach(pickable) { ch in
                    let on = picked.contains(ch)
                    Button { if on { picked.remove(ch) } else { picked.insert(ch) } } label: {
                        HStack {
                            Image(systemName: ch.symbol)
                            Text(ch.title).font(.subheadline.weight(.medium))
                            Spacer()
                            if on { Image(systemName: "checkmark.circle.fill") }
                        }
                        .foregroundStyle(on ? .white : .primary)
                        .padding()
                        .background(on ? AnyShapeStyle(ch.tint) : AnyShapeStyle(.thinMaterial), in: RoundedRectangle(cornerRadius: 12))
                    }.buttonStyle(.plain)
                }
            }.padding(.horizontal)
            if !llmConfig.hasKey {
                Label("进入后到「设置 → AI 录入接口」填 Key 即可扫描资讯。", systemImage: "info.circle")
                    .font(.caption).foregroundStyle(.secondary).padding(.horizontal)
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
