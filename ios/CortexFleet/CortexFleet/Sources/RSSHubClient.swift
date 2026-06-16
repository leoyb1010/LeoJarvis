import Foundation

/// RSSHub integration. RSSHub ("everything is RSSible") turns Chinese platforms
/// (Weibo / Zhihu / Bilibili / WeChat 公众号 etc.) into RSS. We default to the
/// public instance `rsshub.app`; the user can point it at a self-hosted instance
/// in Settings. A curated set of popular routes can be one-tap subscribed.
enum RSSHubClient {
    static let instanceKey = "rsshub.instanceBase"
    static let defaultInstance = "https://rsshub.app"

    static var instanceBase: String {
        let raw = UserDefaults.standard.string(forKey: instanceKey) ?? defaultInstance
        return raw.trimmingCharacters(in: .whitespaces).trimmingCharacters(in: CharacterSet(charactersIn: "/"))
    }

    static func setInstance(_ base: String) {
        let clean = base.trimmingCharacters(in: .whitespaces)
        UserDefaults.standard.set(clean.isEmpty ? defaultInstance : clean, forKey: instanceKey)
    }

    /// A subscribable RSSHub route template.
    struct Route: Identifiable {
        let id: String          // route path, e.g. "/weibo/search/hot"
        let name: String
        let category: String
        let channel: Channel
        let domain: String
        var note: String = ""   // e.g. needs self-hosted instance / login
    }

    /// Popular routes covering Chinese platforms. WeChat 公众号 routes typically
    /// need a self-hosted instance (wewe-rss), flagged in `note`.
    static let popularRoutes: [Route] = [
        Route(id: "/weibo/search/hot", name: "微博热搜", category: "中文", channel: .china, domain: "life"),
        Route(id: "/zhihu/hotlist", name: "知乎热榜", category: "中文", channel: .china, domain: "life"),
        Route(id: "/bilibili/popular/all", name: "B站综合热门", category: "中文", channel: .china, domain: "life"),
        Route(id: "/36kr/news/latest", name: "36氪快讯", category: "中文", channel: .china, domain: "business"),
        Route(id: "/sspai/index", name: "少数派首页", category: "中文", channel: .china, domain: "life"),
        Route(id: "/juejin/category/ai", name: "掘金 · AI", category: "中文", channel: .ai, domain: "business"),
        Route(id: "/v2ex/topics/hot", name: "V2EX 热门", category: "中文", channel: .tech, domain: "life"),
        Route(id: "/xueqiu/today", name: "雪球今日话题", category: "财经", channel: .finance, domain: "business"),
        Route(id: "/cls/telegraph", name: "财联社电报", category: "财经", channel: .finance, domain: "business"),
        Route(id: "/thepaper/featured", name: "澎湃 · 要闻", category: "世界", channel: .world, domain: "business"),
        Route(id: "/github/trending/daily/any", name: "GitHub Trending", category: "工程", channel: .github, domain: "business"),
        Route(id: "/hackernews/best", name: "Hacker News Best", category: "科技", channel: .tech, domain: "business"),
        Route(id: "/wechat/ce/<id>", name: "公众号(需自建实例)", category: "中文", channel: .china, domain: "business",
              note: "公众号路由通常需要自建 RSSHub + wewe-rss，公共实例可能不可用。"),
    ]

    static func feedURL(for route: Route) -> String {
        instanceBase + route.id
    }

    /// Build a `FeedSource` from a route template, ready to insert into SwiftData.
    static func makeSource(from route: Route) -> FeedSource {
        FeedSource(
            name: route.name,
            url: feedURL(for: route),
            domain: route.domain,
            category: route.category,
            channel: route.channel.rawValue,
            origin: "rsshub",
            enabled: true,
            limit: 12
        )
    }
}
