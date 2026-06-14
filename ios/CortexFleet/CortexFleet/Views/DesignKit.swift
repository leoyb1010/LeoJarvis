import SwiftUI

// ═══════════════════════════════════════════════════════════════════
//  DesignKit.swift  ·  ARC REACTOR HUD 换肤版
//  公开 API（Brand / jarvisCard / SectionHeader / CollapsibleSection /
//  IntelKind / IntelPriority / IntelCard / NewsCard / RelativeTime /
//  CoverImage / NewsCardSkeleton / EmptyHint）全部保持不变，
//  仅替换视觉实现 —— 整个 App 一次性换肤，其余文件无需改动。
// ═══════════════════════════════════════════════════════════════════

// MARK: - Design tokens

enum Brand {
    static let corner: CGFloat = 14
    static let tileCorner: CGFloat = 10
    static let cardPadding: CGFloat = 16
    static let stack: CGFloat = 14

    // ARC REACTOR 配色
    static let accent = Color(red: 0.216, green: 0.878, blue: 1.0)   // #37E0FF 青
    static let gold   = Color(red: 1.0,   green: 0.776, blue: 0.345) // #FFC658 金
    static let vital  = Color(red: 0.373, green: 1.0,   blue: 0.729) // #5FFFBA 生命绿
    static let void   = Color(red: 0.016, green: 0.031, blue: 0.059) // #04080F 底
    static let panel  = Color(red: 0.078, green: 0.18,  blue: 0.267) // 面板高光
    static let hudText = Color(red: 0.84, green: 0.93,  blue: 0.98)

    static let hairline = accent.opacity(0.18)
}

extension Font {
    /// 等宽字体 —— 数据 / 标签 / 遥测（SF Mono，无需打包字体）
    static func hudMono(_ size: CGFloat, _ weight: Font.Weight = .regular) -> Font {
        .system(size: size, weight: weight, design: .monospaced)
    }
    /// 圆角字体 —— 大号显示 / 数值（接近 Rajdhani 的科技感）
    static func hudDisplay(_ size: CGFloat, _ weight: Font.Weight = .bold) -> Font {
        .system(size: size, weight: weight, design: .rounded)
    }
}

// MARK: - HUD 基础构件

/// 卡片四角准星
struct ArcCorners: View {
    var color: Color = Brand.accent
    var len: CGFloat = 9
    var lineWidth: CGFloat = 1.2

    var body: some View {
        GeometryReader { geo in
            let w = geo.size.width, h = geo.size.height
            Path { p in
                p.move(to: .init(x: 0, y: len)); p.addLine(to: .init(x: 0, y: 0)); p.addLine(to: .init(x: len, y: 0))
                p.move(to: .init(x: w - len, y: 0)); p.addLine(to: .init(x: w, y: 0)); p.addLine(to: .init(x: w, y: len))
                p.move(to: .init(x: w, y: h - len)); p.addLine(to: .init(x: w, y: h)); p.addLine(to: .init(x: w - len, y: h))
                p.move(to: .init(x: len, y: h)); p.addLine(to: .init(x: 0, y: h)); p.addLine(to: .init(x: 0, y: h - len))
            }
            .stroke(color, lineWidth: lineWidth)
        }
        .allowsHitTesting(false)
    }
}

/// 背景网格（用于全局 HUD 底）
struct HUDGrid: Shape {
    var spacing: CGFloat = 34
    func path(in rect: CGRect) -> Path {
        var p = Path()
        var x: CGFloat = 0
        while x <= rect.width { p.move(to: .init(x: x, y: 0)); p.addLine(to: .init(x: x, y: rect.height)); x += spacing }
        var y: CGFloat = 0
        while y <= rect.height { p.move(to: .init(x: 0, y: y)); p.addLine(to: .init(x: rect.width, y: y)); y += spacing }
        return p
    }
}

/// 全局 HUD 背景：能量底色 + 淡网格
struct HUDBackground: View {
    var body: some View {
        ZStack {
            RadialGradient(colors: [Color(red: 0.05, green: 0.135, blue: 0.21), Brand.void],
                           center: .top, startRadius: 0, endRadius: 760)
            HUDGrid().stroke(Brand.accent.opacity(0.06), lineWidth: 1)
        }
        .ignoresSafeArea()
    }
}

/// 旋转能量核心环 —— 可复用于健康分 / 头像 / 加载
struct ArcRing: View {
    var progress: Double          // 0...1
    var size: CGFloat = 64
    var color: Color = Brand.accent
    var label: String? = nil

    var body: some View {
        ZStack {
            Circle().stroke(color.opacity(0.16), style: .init(lineWidth: 1.4, dash: [2, 4]))
            Circle()
                .trim(from: 0, to: max(0.02, min(1, progress)))
                .stroke(color, style: .init(lineWidth: 2.4, lineCap: .round))
                .shadow(color: color.opacity(0.7), radius: 5)
                .rotationEffect(.degrees(-90))
            Circle().fill(color.opacity(0.18)).frame(width: size * 0.42, height: size * 0.42).blur(radius: 4)
            if let label {
                Text(label).font(.hudDisplay(size * 0.26, .bold)).foregroundStyle(Brand.hudText)
            }
        }
        .frame(width: size, height: size)
    }
}

// MARK: - HUD 表面

extension View {
    /// HUD 面板表面：暗色玻璃渐变 + 青色描边 + 四角准星
    func hudSurface(corner: CGFloat = Brand.corner, stroke: Color = Brand.hairline, brackets: Bool = true) -> some View {
        self
            .background(
                LinearGradient(colors: [Brand.panel.opacity(0.5), Brand.void.opacity(0.42)],
                               startPoint: .top, endPoint: .bottom),
                in: RoundedRectangle(cornerRadius: corner, style: .continuous)
            )
            .overlay(
                RoundedRectangle(cornerRadius: corner, style: .continuous)
                    .stroke(stroke, lineWidth: 1)
            )
            .overlay { if brackets { ArcCorners(color: Brand.accent.opacity(0.7)).padding(5) } }
    }

    /// 标准卡片（兼容旧 API）
    func jarvisCard(stroke: Color = Brand.hairline, corner: CGFloat = Brand.corner) -> some View {
        self.padding(Brand.cardPadding).hudSurface(corner: corner, stroke: stroke)
    }

    /// 给 Form / List 套上 HUD 底（透明列背景 + 能量底 + 青色 tint），
    /// 用于设置、编辑器、SSH、Notebook 等表单页一键 HUD 化。
    func hudFormBackground() -> some View {
        self
            .scrollContentBackground(.hidden)
            .background(HUDBackground())
            .tint(Brand.accent)
    }

    /// HUD 列表行底（半透明面板）
    func hudRow() -> some View {
        self.listRowBackground(Brand.panel.opacity(0.18))
    }
}

// MARK: - SectionHeader

struct SectionHeader: View {
    let title: String
    var subtitle: String?
    var systemImage: String?
    var trailing: AnyView?

    init(title: String, subtitle: String? = nil, systemImage: String? = nil, trailing: AnyView? = nil) {
        self.title = title; self.subtitle = subtitle; self.systemImage = systemImage; self.trailing = trailing
    }

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 8) {
            if let systemImage {
                Image(systemName: systemImage)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(Brand.accent)
            }
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(.hudDisplay(19, .bold)).foregroundStyle(Brand.hudText)
                if let subtitle {
                    Text(subtitle).font(.hudMono(11)).foregroundStyle(Brand.accent.opacity(0.75))
                }
            }
            Spacer(minLength: 0)
            if let trailing { trailing }
        }
        .padding(.top, 4)
    }
}

// MARK: - CollapsibleSection

struct CollapsibleSection<Content: View>: View {
    let title: String
    var systemImage: String
    var count: Int?
    var accent: Color
    var defaultExpanded: Bool
    let storageKey: String
    @ViewBuilder var content: () -> Content

    @AppStorage private var expanded: Bool

    init(title: String, systemImage: String = "square.stack.3d.up", count: Int? = nil,
         accent: Color = Brand.accent, defaultExpanded: Bool = true, storageKey: String,
         @ViewBuilder content: @escaping () -> Content) {
        self.title = title; self.systemImage = systemImage; self.count = count
        self.accent = accent; self.defaultExpanded = defaultExpanded; self.storageKey = storageKey
        self.content = content
        _expanded = AppStorage(wrappedValue: defaultExpanded, "collapse.\(storageKey)")
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Button {
                withAnimation(.snappy(duration: 0.22)) { expanded.toggle() }
            } label: {
                HStack(spacing: 10) {
                    Image(systemName: systemImage).font(.subheadline.weight(.semibold))
                        .foregroundStyle(accent).frame(width: 22)
                    Text(title).font(.hudDisplay(17, .semibold)).foregroundStyle(Brand.hudText)
                    if let count {
                        Text("\(count)").font(.hudMono(11, .bold)).foregroundStyle(accent)
                            .padding(.horizontal, 7).padding(.vertical, 2)
                            .background(accent.opacity(0.14), in: Capsule())
                            .overlay(Capsule().stroke(accent.opacity(0.4), lineWidth: 0.8))
                    }
                    Spacer(minLength: 0)
                    Image(systemName: "chevron.down").font(.caption.weight(.bold))
                        .foregroundStyle(accent.opacity(0.7))
                        .rotationEffect(.degrees(expanded ? 0 : -90))
                }
                .padding(.vertical, 12).padding(.horizontal, 14)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)

            if expanded {
                VStack(alignment: .leading, spacing: 10) { content() }
                    .padding(.horizontal, 14).padding(.bottom, 14)
                    .transition(.opacity.combined(with: .move(edge: .top)))
            }
        }
        .hudSurface(corner: Brand.corner, stroke: accent.opacity(0.18))
    }
}

// MARK: - IntelKind / IntelPriority

enum IntelKind: String {
    case news, github, x, mail, life
    var label: String {
        switch self {
        case .news: return "资讯"; case .github: return "GitHub"; case .x: return "社媒"
        case .mail: return "邮件"; case .life: return "生活"
        }
    }
    var symbol: String {
        switch self {
        case .news: return "newspaper"; case .github: return "chevron.left.forwardslash.chevron.right"
        case .x: return "at"; case .mail: return "envelope"; case .life: return "leaf"
        }
    }
    var tint: Color {
        switch self {
        case .news: return Brand.accent
        case .github: return Color(red: 0.72, green: 0.55, blue: 1.0)   // 霓虹紫
        case .x: return Brand.vital
        case .mail: return Brand.gold
        case .life: return Color(red: 0.45, green: 0.95, blue: 0.6)
        }
    }
}

extension IntelItem {
    var intelKind: IntelKind {
        switch kind {
        case "github_repo": return .github
        case "x_post": return .x
        case "email": return .mail
        default: return domain == "life" ? .life : .news
        }
    }
}

enum IntelPriority {
    case high, medium, watch
    var label: String {
        switch self { case .high: return "高优先"; case .medium: return "中优先"; case .watch: return "观察" }
    }
    var tint: Color {
        switch self { case .high: return Brand.gold; case .medium: return Brand.accent; case .watch: return Brand.hudText.opacity(0.5) }
    }
    init(scoreText: String?) {
        switch scoreText {
        case "高优先": self = .high
        case "中优先": self = .medium
        default: self = .watch
        }
    }
}

// MARK: - IntelCard

struct IntelCard: View {
    let kind: IntelKind
    let title: String
    var summary: String?
    var meta: String?
    var priority: IntelPriority?
    var tags: [String] = []

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 6) {
                Label(kind.label, systemImage: kind.symbol)
                    .font(.hudMono(10, .semibold)).foregroundStyle(kind.tint)
                    .padding(.horizontal, 7).padding(.vertical, 3)
                    .background(kind.tint.opacity(0.12), in: Capsule())
                    .overlay(Capsule().stroke(kind.tint.opacity(0.4), lineWidth: 0.7))
                if let priority {
                    Text(priority.label).font(.hudMono(10, .bold)).foregroundStyle(priority.tint)
                    if priority.label == "高优先" {
                        Circle().fill(Brand.gold).frame(width: 5, height: 5).shadow(color: Brand.gold, radius: 3)
                    }
                }
                Spacer(minLength: 0)
                if let meta { Text(meta).font(.hudMono(10)).foregroundStyle(Brand.hudText.opacity(0.45)).lineLimit(1) }
            }
            Text(title).font(.subheadline.weight(.semibold)).foregroundStyle(Brand.hudText).lineLimit(2)
            if let summary, !summary.isEmpty {
                Text(summary).font(.caption).foregroundStyle(Brand.hudText.opacity(0.6)).lineLimit(3)
            }
            if !tags.isEmpty {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 6) {
                        ForEach(tags.prefix(6), id: \.self) { tag in
                            Text(tag).font(.hudMono(10)).foregroundStyle(Brand.accent.opacity(0.8))
                                .padding(.horizontal, 7).padding(.vertical, 3)
                                .background(Brand.accent.opacity(0.08), in: Capsule())
                        }
                    }
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(12)
        .hudSurface(corner: Brand.tileCorner, stroke: kind.tint.opacity(0.3))
    }
}

// MARK: - Relative time

enum RelativeTime {
    static func string(_ date: Date?) -> String {
        guard let date else { return "" }
        let interval = Date().timeIntervalSince(date)
        if interval < 60 { return "刚刚" }
        if interval < 3600 { return "\(Int(interval / 60)) 分钟前" }
        if interval < 86400 { return "\(Int(interval / 3600)) 小时前" }
        if interval < 86400 * 7 { return "\(Int(interval / 86400)) 天前" }
        return date.formatted(.dateTime.month().day())
    }
}

// MARK: - Cover image

struct CoverImage: View {
    let url: String?
    var height: CGFloat = 180
    var corner: CGFloat = 10

    var body: some View {
        Group {
            if let url, let u = URL(string: url) {
                AsyncImage(url: u, transaction: .init(animation: .easeOut(duration: 0.25))) { phase in
                    switch phase {
                    case .success(let image): image.resizable().aspectRatio(contentMode: .fill)
                    case .failure: placeholder
                    case .empty: ZStack { placeholder; ProgressView().tint(Brand.accent) }
                    @unknown default: placeholder
                    }
                }
            } else { placeholder }
        }
        .frame(height: height).frame(maxWidth: .infinity).clipped()
        .clipShape(RoundedRectangle(cornerRadius: corner, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: corner, style: .continuous).stroke(Brand.accent.opacity(0.18), lineWidth: 1))
    }

    private var placeholder: some View {
        LinearGradient(colors: [Brand.panel.opacity(0.6), Brand.void], startPoint: .topLeading, endPoint: .bottomTrailing)
            .overlay(Image(systemName: "photo").font(.title).foregroundStyle(Brand.accent.opacity(0.35)))
    }
}

// MARK: - NewsCard

struct NewsCard: View {
    let channel: Channel
    let title: String
    var summary: String?
    var source: String
    var date: Date?
    var coverURL: String?
    var priority: IntelPriority?
    var isRead: Bool = false
    var isFavorite: Bool = false
    var large: Bool = false

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            if let coverURL, !coverURL.isEmpty {
                CoverImage(url: coverURL, height: large ? 200 : 150, corner: Brand.corner)
                    .padding(.bottom, 2)
            }
            VStack(alignment: .leading, spacing: 7) {
                HStack(spacing: 6) {
                    Label(channel.title, systemImage: channel.symbol)
                        .font(.hudMono(10, .semibold)).foregroundStyle(channel.tint)
                        .padding(.horizontal, 7).padding(.vertical, 3)
                        .background(channel.tint.opacity(0.12), in: Capsule())
                        .overlay(Capsule().stroke(channel.tint.opacity(0.4), lineWidth: 0.7))
                    if let priority, priority.label == "高优先" {
                        Text("热").font(.hudMono(10, .bold)).foregroundStyle(Brand.void)
                            .padding(.horizontal, 6).padding(.vertical, 2)
                            .background(Brand.gold, in: Capsule())
                    }
                    Spacer(minLength: 0)
                    if isFavorite { Image(systemName: "star.fill").font(.caption2).foregroundStyle(Brand.gold) }
                }
                Text(title)
                    .font(large ? .hudDisplay(20, .bold) : .subheadline.weight(.semibold))
                    .foregroundStyle(isRead ? Brand.hudText.opacity(0.5) : Brand.hudText)
                    .lineLimit(large ? 3 : 2)
                if let summary, !summary.isEmpty {
                    Text(summary).font(.caption).foregroundStyle(Brand.hudText.opacity(0.6)).lineLimit(large ? 3 : 2)
                }
                HStack(spacing: 6) {
                    Text(source).font(.hudMono(10)).foregroundStyle(Brand.hudText.opacity(0.45))
                    if let date {
                        Text("·").font(.hudMono(10)).foregroundStyle(Brand.hudText.opacity(0.3))
                        Text(RelativeTime.string(date)).font(.hudMono(10)).foregroundStyle(Brand.hudText.opacity(0.45))
                    }
                }
            }
            .padding(coverURL?.isEmpty == false ? 12 : 14)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .hudSurface(corner: Brand.corner, stroke: channel.tint.opacity(0.28))
    }
}

struct NewsCardSkeleton: View {
    @State private var shimmer = false
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            RoundedRectangle(cornerRadius: 10).fill(Brand.accent.opacity(0.1)).frame(height: 140)
            RoundedRectangle(cornerRadius: 4).fill(Brand.accent.opacity(0.1)).frame(height: 14).frame(maxWidth: .infinity)
            RoundedRectangle(cornerRadius: 4).fill(Brand.accent.opacity(0.07)).frame(height: 10).frame(maxWidth: 200)
        }
        .padding(12)
        .hudSurface(corner: Brand.corner, brackets: false)
        .opacity(shimmer ? 0.5 : 1)
        .onAppear { withAnimation(.easeInOut(duration: 0.9).repeatForever(autoreverses: true)) { shimmer = true } }
    }
}

// MARK: - EmptyHint

struct EmptyHint: View {
    let text: String
    var systemImage: String = "tray"
    var body: some View {
        Label(text, systemImage: systemImage)
            .font(.hudMono(12)).foregroundStyle(Brand.hudText.opacity(0.55))
            .frame(maxWidth: .infinity, alignment: .center).padding(.vertical, 14)
    }
}
