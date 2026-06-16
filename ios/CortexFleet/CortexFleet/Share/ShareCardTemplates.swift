import SwiftUI

/// What a share card renders. Either an intel article or a personal note.
enum ShareCardPayload {
    case article(IntelItem)
    case note(Note)
    case quote(text: String, source: String)

    var title: String {
        switch self {
        case .article(let i): return i.displayTitle
        case .note(let n): return n.displayTitle
        case .quote(_, let s): return s
        }
    }
    var body: String {
        switch self {
        case .article(let i): return i.displaySummary ?? ""
        case .note(let n): return n.content
        case .quote(let t, _): return t
        }
    }
    var source: String {
        switch self {
        case .article(let i): return i.sourceName
        case .note: return "个人记事"
        case .quote(_, let s): return s
        }
    }
    var link: String? {
        switch self {
        case .article(let i): return i.url
        default: return nil
        }
    }
}

/// Visual template choices.
enum ShareTemplate: String, CaseIterable, Identifiable {
    case news       // cover + title + summary + footer
    case quote      // big quote, minimal
    case poster     // bold gradient poster
    var id: String { rawValue }
    var label: String {
        switch self { case .news: return "资讯卡"; case .quote: return "语录卡"; case .poster: return "海报" }
    }
}

enum ShareTheme: String, CaseIterable, Identifiable {
    case arc, dark, light, gradient
    var id: String { rawValue }
    var label: String {
        switch self { case .arc: return "ARC"; case .dark: return "深色"; case .light: return "浅色"; case .gradient: return "渐变" }
    }

    var bg: AnyShapeStyle {
        switch self {
        case .arc: return AnyShapeStyle(RadialGradient(colors: [Brand.panel, Brand.void], center: .top, startRadius: 0, endRadius: 700))
        case .light: return AnyShapeStyle(Color(white: 0.98))
        case .dark: return AnyShapeStyle(Color(white: 0.10))
        case .gradient: return AnyShapeStyle(LinearGradient(colors: [.blue, .indigo, .purple],
                                                            startPoint: .topLeading, endPoint: .bottomTrailing))
        }
    }
    var isArc: Bool { self == .arc }
    var accent: Color { self == .arc ? Brand.accent : .white }
    var fg: Color { self == .light ? .black : (self == .arc ? Brand.hudText : .white) }
    var secondary: Color {
        if self == .arc { return Brand.accent.opacity(0.7) }
        return (self == .light ? Color.black : Color.white).opacity(0.6)
    }
}

enum ShareSize: String, CaseIterable, Identifiable {
    case square, portrait, story
    var id: String { rawValue }
    var label: String { self == .square ? "方图" : self == .portrait ? "竖图" : "故事图" }
    var dimensions: CGSize {
        switch self {
        case .square: return CGSize(width: 1080, height: 1080)
        case .portrait: return CGSize(width: 1080, height: 1350)
        case .story: return CGSize(width: 1080, height: 1920)
        }
    }
    /// Layout point size (rendered at scale 3 → above pixel dimensions).
    var points: CGSize { CGSize(width: dimensions.width / 3, height: dimensions.height / 3) }
}

/// The actual SwiftUI card rendered to an image. Brand watermark + date + optional QR.
struct ShareCard: View {
    let payload: ShareCardPayload
    let template: ShareTemplate
    let theme: ShareTheme
    let size: ShareSize
    var signature: String = "LeoJarvis"
    var showQR: Bool = true
    let dateText: String

    var body: some View {
        ZStack {
            Rectangle().fill(theme.bg)
            if theme.isArc {
                HUDGrid(spacing: 30).stroke(Brand.accent.opacity(0.07), lineWidth: 1)
            }
            VStack(alignment: .leading, spacing: 18) {
                header
                Spacer(minLength: 0)
                content
                Spacer(minLength: 0)
                footer
            }
            .padding(36)
            if theme.isArc { ArcCorners(color: Brand.accent.opacity(0.6), len: 18, lineWidth: 2).padding(14) }
        }
        .frame(width: size.points.width, height: size.points.height)
    }

    @ViewBuilder private var header: some View {
        HStack {
            Image(systemName: "sparkles")
                .font(.title2).foregroundStyle(theme.accent)
            Text("J.A.R.V.I.S 今日精选").font(theme.isArc ? .hudDisplay(18, .bold) : .headline).foregroundStyle(theme.fg)
            Spacer()
            Text(dateText).font(theme.isArc ? .hudMono(13) : .subheadline).foregroundStyle(theme.secondary)
        }
    }

    @ViewBuilder private var content: some View {
        switch template {
        case .quote:
            VStack(alignment: .leading, spacing: 16) {
                Text("“").font(.system(size: 80, weight: .black)).foregroundStyle(theme.fg.opacity(0.3))
                Text(payload.body.isEmpty ? payload.title : payload.body)
                    .font(.system(size: 30, weight: .bold)).foregroundStyle(theme.fg).lineLimit(8)
            }
        case .poster:
            VStack(alignment: .leading, spacing: 14) {
                Text(payload.source.uppercased()).font(.caption.weight(.heavy)).foregroundStyle(theme.secondary)
                Text(payload.title).font(.system(size: 36, weight: .black)).foregroundStyle(theme.fg).lineLimit(5)
                if !payload.body.isEmpty {
                    Text(payload.body).font(.title3).foregroundStyle(theme.fg.opacity(0.85)).lineLimit(6)
                }
            }
        case .news:
            VStack(alignment: .leading, spacing: 14) {
                if let cover = articleCover, !cover.isEmpty {
                    CoverImage(url: cover, height: 200, corner: 16)
                }
                Text(payload.title).font(.system(size: 28, weight: .bold)).foregroundStyle(theme.fg).lineLimit(4)
                if !payload.body.isEmpty {
                    Text(payload.body).font(.title3).foregroundStyle(theme.fg.opacity(0.82)).lineLimit(6)
                }
            }
        }
    }

    @ViewBuilder private var footer: some View {
        HStack(alignment: .bottom) {
            VStack(alignment: .leading, spacing: 2) {
                Text(signature).font(.headline.weight(.bold)).foregroundStyle(theme.fg)
                Text(payload.source).font(.caption).foregroundStyle(theme.secondary)
            }
            Spacer()
            if showQR, let link = payload.link, let qr = QRCode.image(from: link) {
                Image(uiImage: qr).resizable().interpolation(.none)
                    .frame(width: 64, height: 64)
                    .background(Color.white).clipShape(RoundedRectangle(cornerRadius: 8))
            }
        }
    }

    private var articleCover: String? {
        if case .article(let i) = payload { return i.coverURL }
        return nil
    }
}
