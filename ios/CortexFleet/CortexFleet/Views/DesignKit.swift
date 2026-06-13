import SwiftUI

// MARK: - Design tokens

enum Brand {
    static let corner: CGFloat = 16
    static let tileCorner: CGFloat = 12
    static let cardPadding: CGFloat = 16
    static let stack: CGFloat = 14

    static let accent = Color.blue
    static let hairline = Color.blue.opacity(0.16)
}

extension View {
    /// Standard card surface used across every redesigned screen.
    func jarvisCard(stroke: Color = Brand.hairline, corner: CGFloat = Brand.corner) -> some View {
        self
            .padding(Brand.cardPadding)
            .background(.thinMaterial, in: RoundedRectangle(cornerRadius: corner, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: corner, style: .continuous)
                    .stroke(stroke, lineWidth: 1)
            )
    }
}

// MARK: - SectionHeader

struct SectionHeader: View {
    let title: String
    var subtitle: String?
    var systemImage: String?
    var trailing: AnyView?

    init(title: String, subtitle: String? = nil, systemImage: String? = nil, trailing: AnyView? = nil) {
        self.title = title
        self.subtitle = subtitle
        self.systemImage = systemImage
        self.trailing = trailing
    }

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 8) {
            if let systemImage {
                Image(systemName: systemImage)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(.tint)
            }
            VStack(alignment: .leading, spacing: 1) {
                Text(title)
                    .font(.headline)
                if let subtitle {
                    Text(subtitle)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            Spacer(minLength: 0)
            if let trailing { trailing }
        }
        .padding(.top, 4)
    }
}

// MARK: - CollapsibleSection

/// A titled, collapsible drawer. Expansion state is remembered per `storageKey`
/// via `@AppStorage`, so a section the user closed stays closed across launches.
/// This is the core component that replaces the old "wall of text" layout.
struct CollapsibleSection<Content: View>: View {
    let title: String
    var systemImage: String
    var count: Int?
    var accent: Color
    var defaultExpanded: Bool
    let storageKey: String
    @ViewBuilder var content: () -> Content

    @AppStorage private var expanded: Bool

    init(
        title: String,
        systemImage: String = "square.stack.3d.up",
        count: Int? = nil,
        accent: Color = Brand.accent,
        defaultExpanded: Bool = true,
        storageKey: String,
        @ViewBuilder content: @escaping () -> Content
    ) {
        self.title = title
        self.systemImage = systemImage
        self.count = count
        self.accent = accent
        self.defaultExpanded = defaultExpanded
        self.storageKey = storageKey
        self.content = content
        _expanded = AppStorage(wrappedValue: defaultExpanded, "collapse.\(storageKey)")
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Button {
                withAnimation(.snappy(duration: 0.22)) { expanded.toggle() }
            } label: {
                HStack(spacing: 10) {
                    Image(systemName: systemImage)
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(accent)
                        .frame(width: 22)
                    Text(title)
                        .font(.headline)
                        .foregroundStyle(.primary)
                    if let count {
                        Text("\(count)")
                            .font(.caption.weight(.bold))
                            .foregroundStyle(accent)
                            .padding(.horizontal, 7)
                            .padding(.vertical, 2)
                            .background(accent.opacity(0.14), in: Capsule())
                    }
                    Spacer(minLength: 0)
                    Image(systemName: "chevron.down")
                        .font(.caption.weight(.bold))
                        .foregroundStyle(.secondary)
                        .rotationEffect(.degrees(expanded ? 0 : -90))
                }
                .padding(.vertical, 12)
                .padding(.horizontal, 14)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)

            if expanded {
                VStack(alignment: .leading, spacing: 10) {
                    content()
                }
                .padding(.horizontal, 14)
                .padding(.bottom, 14)
                .transition(.opacity.combined(with: .move(edge: .top)))
            }
        }
        .background(.thinMaterial, in: RoundedRectangle(cornerRadius: Brand.corner, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: Brand.corner, style: .continuous)
                .stroke(accent.opacity(0.16), lineWidth: 1)
        )
    }
}

// MARK: - IntelKind (typed intelligence categories)

/// Visual identity for each intelligence item type, so the briefing/overview
/// reads as categorized cards instead of an undifferentiated text dump.
enum IntelKind: String {
    case news
    case github
    case x
    case mail
    case life

    var label: String {
        switch self {
        case .news: return "资讯"
        case .github: return "GitHub"
        case .x: return "社媒"
        case .mail: return "邮件"
        case .life: return "生活"
        }
    }

    var symbol: String {
        switch self {
        case .news: return "newspaper"
        case .github: return "chevron.left.forwardslash.chevron.right"
        case .x: return "at"
        case .mail: return "envelope"
        case .life: return "leaf"
        }
    }

    var tint: Color {
        switch self {
        case .news: return .blue
        case .github: return .purple
        case .x: return .teal
        case .mail: return .orange
        case .life: return .green
        }
    }
}

extension IntelItem {
    /// Visual category for the item, derived from its `kind`/`domain`.
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
        switch self {
        case .high: return "高优先"
        case .medium: return "中优先"
        case .watch: return "观察"
        }
    }

    var tint: Color {
        switch self {
        case .high: return .red
        case .medium: return .orange
        case .watch: return .secondary
        }
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

/// A single intelligence/briefing item, color- and icon-coded by type with a
/// clear visual hierarchy: type chip + priority, bold title, one-line summary,
/// optional tags. Replaces the cramped text rows in the old UI.
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
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(kind.tint)
                    .padding(.horizontal, 7)
                    .padding(.vertical, 3)
                    .background(kind.tint.opacity(0.12), in: Capsule())
                if let priority {
                    Text(priority.label)
                        .font(.caption2.weight(.bold))
                        .foregroundStyle(priority.tint)
                }
                Spacer(minLength: 0)
                if let meta {
                    Text(meta)
                        .font(.caption2)
                        .foregroundStyle(.tertiary)
                        .lineLimit(1)
                }
            }

            Text(title)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(.primary)
                .lineLimit(2)

            if let summary, !summary.isEmpty {
                Text(summary)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(3)
            }

            if !tags.isEmpty {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 6) {
                        ForEach(tags.prefix(6), id: \.self) { tag in
                            Text(tag)
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                                .padding(.horizontal, 7)
                                .padding(.vertical, 3)
                                .background(.background.opacity(0.6), in: Capsule())
                        }
                    }
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(12)
        .background(.background.opacity(0.72), in: RoundedRectangle(cornerRadius: Brand.tileCorner, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: Brand.tileCorner, style: .continuous)
                .stroke(kind.tint.opacity(0.18), lineWidth: 1)
        )
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

// MARK: - Cover image (AsyncImage with skeleton + graceful fallback)

struct CoverImage: View {
    let url: String?
    var height: CGFloat = 180
    var corner: CGFloat = 12

    var body: some View {
        Group {
            if let url, let u = URL(string: url) {
                AsyncImage(url: u, transaction: .init(animation: .easeOut(duration: 0.25))) { phase in
                    switch phase {
                    case .success(let image):
                        image.resizable().aspectRatio(contentMode: .fill)
                    case .failure:
                        placeholder
                    case .empty:
                        ZStack { placeholder; ProgressView() }
                    @unknown default:
                        placeholder
                    }
                }
            } else {
                placeholder
            }
        }
        .frame(height: height)
        .frame(maxWidth: .infinity)
        .clipped()
        .clipShape(RoundedRectangle(cornerRadius: corner, style: .continuous))
    }

    private var placeholder: some View {
        LinearGradient(colors: [.gray.opacity(0.16), .gray.opacity(0.06)],
                       startPoint: .topLeading, endPoint: .bottomTrailing)
            .overlay(Image(systemName: "photo").font(.title).foregroundStyle(.tertiary))
    }
}

// MARK: - News cards (magazine-style feed)

/// A news article card. Adapts layout to whether a cover image exists:
/// large hero card with cover, or compact text-forward card without.
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
                CoverImage(url: coverURL, height: large ? 200 : 150)
            }
            VStack(alignment: .leading, spacing: 7) {
                HStack(spacing: 6) {
                    Label(channel.title, systemImage: channel.symbol)
                        .font(.caption2.weight(.semibold)).foregroundStyle(channel.tint)
                        .padding(.horizontal, 7).padding(.vertical, 3)
                        .background(channel.tint.opacity(0.12), in: Capsule())
                    if let priority, priority.label == "高优先" {
                        Text("热").font(.caption2.weight(.bold)).foregroundStyle(.white)
                            .padding(.horizontal, 6).padding(.vertical, 2)
                            .background(Color.red, in: Capsule())
                    }
                    Spacer(minLength: 0)
                    if isFavorite { Image(systemName: "star.fill").font(.caption2).foregroundStyle(.yellow) }
                }
                Text(title)
                    .font(large ? .headline : .subheadline.weight(.semibold))
                    .foregroundStyle(isRead ? .secondary : .primary)
                    .lineLimit(large ? 3 : 2)
                if let summary, !summary.isEmpty {
                    Text(summary).font(.caption).foregroundStyle(.secondary).lineLimit(large ? 3 : 2)
                }
                HStack(spacing: 6) {
                    Text(source).font(.caption2).foregroundStyle(.tertiary)
                    if let date { Text("·").font(.caption2).foregroundStyle(.tertiary)
                        Text(RelativeTime.string(date)).font(.caption2).foregroundStyle(.tertiary) }
                }
            }
            .padding(coverURL?.isEmpty == false ? 12 : 14)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(.background.opacity(0.85), in: RoundedRectangle(cornerRadius: Brand.corner, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: Brand.corner, style: .continuous)
                .stroke(channel.tint.opacity(0.14), lineWidth: 1)
        )
    }
}

/// Skeleton placeholder row for the loading state.
struct NewsCardSkeleton: View {
    @State private var shimmer = false
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            RoundedRectangle(cornerRadius: 12).fill(.gray.opacity(0.15)).frame(height: 140)
            RoundedRectangle(cornerRadius: 4).fill(.gray.opacity(0.15)).frame(height: 14).frame(maxWidth: .infinity)
            RoundedRectangle(cornerRadius: 4).fill(.gray.opacity(0.12)).frame(height: 10).frame(maxWidth: 200)
        }
        .padding(12)
        .background(.background.opacity(0.6), in: RoundedRectangle(cornerRadius: Brand.corner))
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
            .font(.caption)
            .foregroundStyle(.secondary)
            .frame(maxWidth: .infinity, alignment: .center)
            .padding(.vertical, 14)
    }
}
