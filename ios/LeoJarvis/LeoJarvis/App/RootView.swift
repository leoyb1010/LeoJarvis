import SwiftUI

enum AppTab: String, CaseIterable, Hashable, Identifiable {
    case today      // 驾驶舱
    case intel      // 情报（从今日页提级为一级 tab）
    case notes      // 笔记
    case jarvis     // Jarvis 对话
    case mine       // 我的（设备舰队 + 感知 + Agent 入口 + 设置）

    var id: String { rawValue }

    var title: String {
        switch self {
        case .today: return "驾驶舱"
        case .intel: return "情报"
        case .notes: return "笔记"
        case .jarvis: return "Jarvis"
        case .mine: return "我的"
        }
    }

    var icon: String {
        switch self {
        case .today: return "sparkles"
        case .intel: return "antenna.radiowaves.left.and.right"
        case .notes: return "note.text"
        case .jarvis: return "message"
        case .mine: return "person.crop.circle"
        }
    }

    var selectedIcon: String {
        switch self {
        case .today: return "sparkles"
        case .intel: return "antenna.radiowaves.left.and.right"
        case .notes: return "note.text"
        case .jarvis: return "message.fill"
        case .mine: return "person.crop.circle.fill"
        }
    }
}

extension NotifyDeepLink {
    /// 通知深链 → tab 映射。.mine 涵盖设备/感知/设置。
    var tab: AppTab {
        switch self {
        case .today: return .today
        case .intel: return .intel
        case .notes: return .notes
        case .jarvis: return .jarvis
        case .mine: return .mine
        }
    }
}

struct RootView: View {
    @EnvironmentObject private var store: JarvisStore
    @State private var selectedTab: AppTab = .today

    var body: some View {
        ZStack(alignment: .top) {
            VStack(spacing: 0) {
                selectedContent
                    .frame(maxWidth: .infinity, maxHeight: .infinity)

                JarvisTabBar(selection: $selectedTab)
                    .padding(.horizontal, 16)
                    .padding(.top, 8)
                    .padding(.bottom, 8)
                    .background(AppTheme.panel)
            }

            VStack {
                if let message = store.errorMessage {
                    ErrorBanner(message: message, tone: .error)
                        .padding(.horizontal, 16)
                        .padding(.top, 8)
                        .transition(.move(edge: .top).combined(with: .opacity))
                } else if let notice = store.infoNotice {
                    ErrorBanner(message: notice, tone: .info)
                        .padding(.horizontal, 16)
                        .padding(.top, 8)
                        .transition(.move(edge: .top).combined(with: .opacity))
                }
                Spacer()
            }
            .animation(.snappy, value: store.errorMessage)
            .animation(.snappy, value: store.infoNotice)
            .task(id: store.infoNotice) {
                // 轻提示自动消失，不长期占顶（红错不自动消，留待用户处理或下次刷新清除）。
                guard store.infoNotice != nil else { return }
                try? await Task.sleep(nanoseconds: 4_000_000_000)
                if !Task.isCancelled { store.infoNotice = nil }
            }
        }
        .onAppear {
            // 点击本地通知 → 按 deepLink 切到对应 tab。
            NotificationManager.shared.onOpenDeepLink = { link in
                withAnimation(.snappy) { selectedTab = link.tab }
            }
        }
    }

    @ViewBuilder private var selectedContent: some View {
        switch selectedTab {
        case .today:
            HomeView()
        case .intel:
            IntelView()
        case .notes:
            NotesView()
        case .jarvis:
            JarvisChatView()
        case .mine:
            MineView()
        }
    }
}

struct JarvisTabBar: View {
    @Binding var selection: AppTab
    @Namespace private var selectionNamespace
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        GlassGroup(spacing: 12) {
            HStack(spacing: 4) {
                ForEach(AppTab.allCases) { tab in
                    Button {
                        Haptics.selection()
                        withAnimation(.spring(response: 0.34, dampingFraction: 0.78)) { selection = tab }
                    } label: {
                        VStack(spacing: 4) {
                            tabIcon(tab)
                            Text(tab.title)
                                .font(.system(size: 10, weight: .heavy))
                                .lineLimit(1)
                                .minimumScaleFactor(0.8)
                        }
                        .foregroundStyle(selection == tab ? AppTheme.accent : AppTheme.ink)
                        .frame(maxWidth: .infinity)
                        .frame(height: 54)
                        .background {
                            if selection == tab {
                                Capsule()
                                    .fill(AppTheme.accentSoft)
                                    .matchedGeometryEffect(id: "tab-selection", in: selectionNamespace)
                            }
                        }
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(PressScaleButtonStyle())
                    .accessibilityLabel(tab.title)
                    .accessibilityAddTraits(selection == tab ? [.isSelected] : [])
                }
            }
            .padding(6)
            .adaptiveGlass(cornerRadius: 34, interactive: true)
            .overlay(Capsule().stroke(AppTheme.glassStroke, lineWidth: 1))
            .shadow(color: AppTheme.shadow, radius: 10, x: 0, y: 4)
        }
    }

    @ViewBuilder
    private func tabIcon(_ tab: AppTab) -> some View {
        let icon = Image(systemName: selection == tab ? tab.selectedIcon : tab.icon)
            .font(.system(size: 17, weight: .heavy))
            .frame(height: 18)
        if reduceMotion {
            icon
        } else {
            icon
                .contentTransition(.symbolEffect(.replace))
                .symbolEffect(.bounce, value: selection == tab)
        }
    }
}

struct ScreenScaffold<Content: View, Trailing: View>: View {
    let title: String
    let subtitle: String
    let systemImage: String
    let trailing: Trailing
    @ViewBuilder let content: Content

    init(
        title: String,
        subtitle: String,
        systemImage: String,
        @ViewBuilder trailing: () -> Trailing,
        @ViewBuilder content: () -> Content
    ) {
        self.title = title
        self.subtitle = subtitle
        self.systemImage = systemImage
        self.trailing = trailing()
        self.content = content()
    }

    var body: some View {
        ZStack {
            AppBackground()
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 14) {
                    screenHeader
                    content
                }
                .padding(.horizontal, 16)
                .padding(.top, 34)
                .padding(.bottom, 24)
            }
            .scrollIndicators(.hidden)
            .scrollDismissesKeyboard(.interactively)
        }
    }

    private var screenHeader: some View {
        HStack(alignment: .center, spacing: 12) {
            ZStack {
                RoundedRectangle(cornerRadius: 11, style: .continuous)
                    .fill(AppTheme.accentSoft)
                if title == "LeoJarvis" || title == "Jarvis" {
                    Image("JarvisLogo")
                        .resizable()
                        .scaledToFill()
                        .clipShape(RoundedRectangle(cornerRadius: 11, style: .continuous))
                        .overlay(
                            RoundedRectangle(cornerRadius: 11, style: .continuous)
                                .stroke(AppTheme.line, lineWidth: 1)
                        )
                } else {
                    Image(systemName: systemImage)
                        .font(.system(size: 18, weight: .heavy))
                        .foregroundStyle(AppTheme.accent)
                }
            }
            .frame(width: 44, height: 44)

            VStack(alignment: .leading, spacing: 3) {
                Text(title)
                    .font(.system(size: 27, weight: .heavy, design: .rounded))
                    .foregroundStyle(AppTheme.ink)
                    .lineLimit(1)
                    .minimumScaleFactor(0.72)
                Text(subtitle)
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(AppTheme.muted)
                    .lineLimit(1)
                    .truncationMode(.middle)
            }
            Spacer(minLength: 8)
            trailing
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .appearLift()
    }
}

extension ScreenScaffold where Trailing == EmptyView {
    init(
        title: String,
        subtitle: String,
        systemImage: String,
        @ViewBuilder content: () -> Content
    ) {
        self.init(
            title: title,
            subtitle: subtitle,
            systemImage: systemImage,
            trailing: { EmptyView() },
            content: content
        )
    }
}
