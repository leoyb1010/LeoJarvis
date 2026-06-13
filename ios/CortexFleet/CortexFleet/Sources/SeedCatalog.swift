import Foundation
import SwiftUI

/// News channels shown as the top tab bar on the home page. `recommended` and
/// `github` are computed/virtual; the rest map to `FeedSource.channel`.
enum Channel: String, CaseIterable, Identifiable {
    case recommended, ai, tech, world, finance, china, engineering, science, github

    var id: String { rawValue }

    var title: String {
        switch self {
        case .recommended: return "推荐"
        case .ai: return "AI"
        case .tech: return "科技"
        case .world: return "国内外大事"
        case .finance: return "财经"
        case .china: return "中文"
        case .engineering: return "工程"
        case .science: return "科学"
        case .github: return "GitHub"
        }
    }

    var symbol: String {
        switch self {
        case .recommended: return "sparkles"
        case .ai: return "brain"
        case .tech: return "cpu"
        case .world: return "globe"
        case .finance: return "chart.line.uptrend.xyaxis"
        case .china: return "character.book.closed"
        case .engineering: return "wrench.and.screwdriver"
        case .science: return "atom"
        case .github: return "chevron.left.forwardslash.chevron.right"
        }
    }

    var tint: Color {
        switch self {
        case .recommended: return .blue
        case .ai: return .indigo
        case .tech: return .cyan
        case .world: return .orange
        case .finance: return .green
        case .china: return .red
        case .engineering: return .purple
        case .science: return .teal
        case .github: return .pink
        }
    }
}

/// The categorized default source catalog. Curated from awesome-tech-rss /
/// awesome-rss-feeds plus the original seed set, covering AI / tech / world /
/// finance / Chinese / engineering / science so the home page is full-spectrum.
enum SeedCatalog {
    struct Feed {
        let name: String; let url: String; let domain: String
        let category: String; let channel: Channel; let limit: Int
    }

    static let feeds: [Feed] = [
        // —— AI ——
        Feed(name: "OpenAI News", url: "https://openai.com/news/rss.xml", domain: "business", category: "AI", channel: .ai, limit: 10),
        Feed(name: "Google DeepMind", url: "https://deepmind.google/blog/rss.xml", domain: "business", category: "AI", channel: .ai, limit: 8),
        Feed(name: "Hugging Face Blog", url: "https://huggingface.co/blog/feed.xml", domain: "business", category: "AI", channel: .ai, limit: 8),
        Feed(name: "BAIR Berkeley", url: "https://bair.berkeley.edu/blog/feed.xml", domain: "business", category: "AI", channel: .ai, limit: 6),
        Feed(name: "Lilian Weng", url: "https://lilianweng.github.io/index.xml", domain: "business", category: "AI", channel: .ai, limit: 6),
        Feed(name: "Simon Willison", url: "https://simonwillison.net/atom/everything/", domain: "business", category: "AI", channel: .ai, limit: 10),
        // —— 科技 ——
        Feed(name: "Hacker News Best", url: "https://hnrss.org/best", domain: "business", category: "科技", channel: .tech, limit: 12),
        Feed(name: "TechCrunch", url: "https://techcrunch.com/feed/", domain: "business", category: "科技", channel: .tech, limit: 10),
        Feed(name: "The Verge", url: "https://www.theverge.com/rss/index.xml", domain: "business", category: "科技", channel: .tech, limit: 10),
        Feed(name: "Ars Technica", url: "https://feeds.arstechnica.com/arstechnica/index", domain: "business", category: "科技", channel: .tech, limit: 10),
        Feed(name: "Daring Fireball", url: "https://daringfireball.net/feeds/main", domain: "business", category: "科技", channel: .tech, limit: 8),
        Feed(name: "Engadget", url: "https://www.engadget.com/rss.xml", domain: "life", category: "科技", channel: .tech, limit: 8),
        // —— 国内外大事 / 世界新闻 ——
        Feed(name: "BBC World", url: "https://feeds.bbci.co.uk/news/world/rss.xml", domain: "business", category: "世界", channel: .world, limit: 12),
        Feed(name: "Reuters World", url: "https://www.reutersagency.com/feed/?best-topics=world&post_type=best", domain: "business", category: "世界", channel: .world, limit: 10),
        Feed(name: "NYT World", url: "https://rss.nytimes.com/services/xml/rss/nyt/World.xml", domain: "business", category: "世界", channel: .world, limit: 10),
        Feed(name: "Al Jazeera", url: "https://www.aljazeera.com/xml/rss/all.xml", domain: "business", category: "世界", channel: .world, limit: 10),
        // —— 财经 ——
        Feed(name: "WSJ Markets", url: "https://feeds.a.dj.com/rss/RSSMarketsMain.xml", domain: "business", category: "财经", channel: .finance, limit: 12),
        Feed(name: "CNBC Finance", url: "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000664", domain: "business", category: "财经", channel: .finance, limit: 10),
        Feed(name: "MarketWatch", url: "http://feeds.marketwatch.com/marketwatch/topstories/", domain: "business", category: "财经", channel: .finance, limit: 10),
        Feed(name: "FT Companies", url: "https://www.ft.com/companies?format=rss", domain: "business", category: "财经", channel: .finance, limit: 8),
        // —— 中文 ——
        Feed(name: "36氪", url: "https://36kr.com/feed", domain: "business", category: "中文", channel: .china, limit: 12),
        Feed(name: "少数派", url: "https://sspai.com/feed", domain: "life", category: "中文", channel: .china, limit: 10),
        Feed(name: "阮一峰周刊", url: "https://www.ruanyifeng.com/blog/atom.xml", domain: "life", category: "中文", channel: .china, limit: 6),
        Feed(name: "机器之心", url: "https://www.jiqizhixin.com/rss", domain: "business", category: "中文", channel: .china, limit: 10),
        Feed(name: "InfoQ 中文", url: "https://www.infoq.cn/feed", domain: "business", category: "中文", channel: .china, limit: 10),
        // —— 工程博客 ——
        Feed(name: "Stripe Blog", url: "https://stripe.com/blog/feed.rss", domain: "business", category: "工程", channel: .engineering, limit: 6),
        Feed(name: "Cloudflare Blog", url: "https://blog.cloudflare.com/rss/", domain: "business", category: "工程", channel: .engineering, limit: 8),
        Feed(name: "GitHub Engineering", url: "https://github.blog/engineering.atom", domain: "business", category: "工程", channel: .engineering, limit: 6),
        Feed(name: "Julia Evans", url: "https://jvns.ca/atom.xml", domain: "life", category: "工程", channel: .engineering, limit: 6),
        Feed(name: "Dan Luu", url: "https://danluu.com/atom.xml", domain: "life", category: "工程", channel: .engineering, limit: 6),
        // —— 科学 ——
        Feed(name: "Quanta Magazine", url: "https://api.quantamagazine.org/feed/", domain: "life", category: "科学", channel: .science, limit: 8),
        Feed(name: "MIT Tech Review", url: "https://www.technologyreview.com/feed/", domain: "business", category: "科学", channel: .science, limit: 8),
        Feed(name: "Nature News", url: "https://www.nature.com/nature.rss", domain: "life", category: "科学", channel: .science, limit: 8),
    ]
}
