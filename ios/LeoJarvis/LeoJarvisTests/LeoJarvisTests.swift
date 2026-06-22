import XCTest
@testable import LeoJarvis

final class LeoJarvisTests: XCTestCase {
    func testAPIClientNormalizesHostWithoutScheme() throws {
        let client = JarvisAPIClient(baseURL: "127.0.0.1:8787", token: "")
        XCTAssertEqual(try client.apiURL("/health").absoluteString, "http://127.0.0.1:8787/api/health")
    }

    func testAPIClientDefaultsPublicHostToHTTPS() throws {
        let client = JarvisAPIClient(baseURL: "jarvis-mbp.example.com", token: "")
        XCTAssertEqual(try client.apiURL("/health").absoluteString, "https://jarvis-mbp.example.com/api/health")
    }

    func testAPIClientAcceptsAPIBase() throws {
        let client = JarvisAPIClient(baseURL: "http://jarvis.local:8787/api", token: "")
        XCTAssertEqual(try client.apiURL("/health").absoluteString, "http://jarvis.local:8787/api/health")
    }

    func testAPIClientBuildsDeviceDeleteURL() throws {
        let client = JarvisAPIClient(baseURL: "http://jarvis.local:8787", token: "")
        XCTAssertEqual(try client.apiURL("/devices/mac-abc123").absoluteString, "http://jarvis.local:8787/api/devices/mac-abc123")
    }

    func testAPIClientAcceptsPathWithoutLeadingSlash() throws {
        let client = JarvisAPIClient(baseURL: "https://jarvis-mbp.example.com", token: "")
        XCTAssertEqual(try client.apiURL("health").absoluteString, "https://jarvis-mbp.example.com/api/health")
    }

    func testAPIClientRejectsEmptyBaseURL() {
        let client = JarvisAPIClient(baseURL: "", token: "")
        XCTAssertThrowsError(try client.apiURL("/health"))
    }

    func testAPIClientDetectsPrivateNetworkEndpoints() {
        XCTAssertTrue(JarvisAPIClient(baseURL: "127.0.0.1:8787", token: "").isPrivateNetworkEndpoint)
        XCTAssertTrue(JarvisAPIClient(baseURL: "http://192.168.1.10:8787", token: "").isPrivateNetworkEndpoint)
        XCTAssertTrue(JarvisAPIClient(baseURL: "http://jarvis.local:8787", token: "").isPrivateNetworkEndpoint)
        XCTAssertTrue(JarvisAPIClient(baseURL: "https://100.81.83.56", token: "").isPrivateNetworkEndpoint)
        XCTAssertFalse(JarvisAPIClient(baseURL: "https://jarvis-mbp.example.com", token: "").isPrivateNetworkEndpoint)
    }

    func testAPIClientRequiresRemoteHTTPSForPublicEndpoint() {
        XCTAssertTrue(JarvisAPIClient(baseURL: "https://jarvis-mbp.example.com", token: "").isRemoteHTTPS)
        XCTAssertFalse(JarvisAPIClient(baseURL: "http://jarvis-mbp.example.com", token: "").isRemoteHTTPS)
        XCTAssertFalse(JarvisAPIClient(baseURL: "https://192.168.1.10:8787", token: "").isRemoteHTTPS)
        XCTAssertFalse(JarvisAPIClient(baseURL: "https://100.81.83.56", token: "").isRemoteHTTPS)
    }

    @MainActor
    func testBuiltInMacTargetsUsePublicHTTPSEndpoints() {
        XCTAssertEqual(JarvisStore.remoteMacTargets.count, 3)
        XCTAssertEqual(
            JarvisStore.remoteMacTargets.map(\.endpoint),
            [
                "https://leoyuanmacbook-pro.tail23de22.ts.net",
                "https://leomac-studio.tail23de22.ts.net",
                "https://mac-mini-cortex.tail23de22.ts.net"
            ]
        )
        XCTAssertTrue(JarvisStore.remoteMacTargets.allSatisfy {
            JarvisAPIClient(baseURL: $0.endpoint, token: "").isRemoteHTTPS
        })
    }

    @MainActor
    func testStoreMigratesLocalSavedEndpointToPublicDefault() {
        UserDefaults.standard.set("http://127.0.0.1:8787", forKey: "leojarvis.mobile.endpoint")
        defer {
            UserDefaults.standard.removeObject(forKey: "leojarvis.mobile.endpoint")
            UserDefaults.standard.removeObject(forKey: "leojarvis.mobile.macTargets")
        }

        let store = JarvisStore()
        XCTAssertEqual(store.endpoint, "https://leoyuanmacbook-pro.tail23de22.ts.net")
        XCTAssertFalse(JarvisAPIClient(baseURL: store.endpoint, token: "").isPrivateNetworkEndpoint)
    }

    @MainActor
    func testRefreshErrorIsSuppressedWhenOnlineContentExists() {
        XCTAssertTrue(JarvisStore.shouldSuppressRefreshError(
            healthOK: true,
            hasBriefing: true,
            hasCockpit: false,
            hasAgents: false,
            hasDevices: false
        ))
        XCTAssertTrue(JarvisStore.shouldSuppressRefreshError(
            healthOK: true,
            hasBriefing: false,
            hasCockpit: true,
            hasAgents: false,
            hasDevices: false
        ))
        XCTAssertFalse(JarvisStore.shouldSuppressRefreshError(
            healthOK: true,
            hasBriefing: false,
            hasCockpit: false,
            hasAgents: false,
            hasDevices: false
        ))
        XCTAssertFalse(JarvisStore.shouldSuppressRefreshError(
            healthOK: false,
            hasBriefing: true,
            hasCockpit: true,
            hasAgents: true,
            hasDevices: true
        ))
    }

    @MainActor
    func testStoreSuppressesCancelledErrorMessages() {
        XCTAssertNil(JarvisStore.cleanErrorMessage("cancelled"))
        XCTAssertNil(JarvisStore.cleanErrorMessage("The operation was canceled."))
        XCTAssertNil(JarvisStore.userFacingErrorMessage(CancellationError()))
        XCTAssertNil(JarvisStore.userFacingErrorMessage(NSError(domain: NSURLErrorDomain, code: NSURLErrorCancelled)))
        XCTAssertEqual(JarvisStore.cleanErrorMessage("健康：cancelled；系统：连接超时"), "系统：连接超时")

        let store = JarvisStore()
        store.errorMessage = "健康：cancelled；系统：连接超时"
        XCTAssertEqual(store.errorMessage, "系统：连接超时")
        store.errorMessage = "cancelled"
        XCTAssertNil(store.errorMessage)
    }

    @MainActor
    func testStoreBootstrapsFromCachedRemoteSnapshot() {
        RemoteSnapshotCache.clear()
        defer { RemoteSnapshotCache.clear() }
        let snapshot = makeRemoteSnapshot(savedAt: Date())
        RemoteSnapshotCache.save(snapshot)

        let store = JarvisStore()

        XCTAssertEqual(store.notes.first?.id, "pytest-note-cache")
        XCTAssertEqual(store.briefing?.items?.first?.event_id, "pytest-briefing-cache")
        XCTAssertEqual(store.agents.first?.name, "codex")
        XCTAssertTrue(store.isUsingCachedRemoteData)
        XCTAssertNil(store.health)
    }

    func testRemoteSnapshotCacheExpiresOldSnapshots() {
        let defaults = UserDefaults(suiteName: "leojarvis-tests-\(UUID().uuidString)")!
        defer { RemoteSnapshotCache.clear(defaults: defaults) }
        let now = Date()
        RemoteSnapshotCache.save(makeRemoteSnapshot(savedAt: now.addingTimeInterval(-8 * 24 * 60 * 60)), defaults: defaults)

        XCTAssertNil(RemoteSnapshotCache.load(defaults: defaults, now: now))
        XCTAssertFalse(RemoteSnapshotCache.hasUsableSnapshot(defaults: defaults, now: now))
    }

    func testChatMessageEncodesWithoutLocalID() throws {
        let message = ChatMessage(role: "user", content: "ping")
        let json = String(data: try JSONEncoder().encode(message), encoding: .utf8) ?? ""
        XCTAssertTrue(json.contains("\"role\":\"user\""))
        XCTAssertTrue(json.contains("\"content\":\"ping\""))
        XCTAssertFalse(json.contains("id"))
    }

    func testShortDateHandlesMillisecondTimestamps() {
        let milliseconds = DisplayFormat.shortDate(1_781_966_520_000)
        let seconds = DisplayFormat.shortDate(1_781_966_520)

        XCTAssertEqual(milliseconds, seconds)
        XCTAssertTrue(milliseconds.hasPrefix("6/20"), milliseconds)
    }

    func testInfoPlistEnablesProMotionRefreshRates() {
        let enabled = Bundle.main.object(forInfoDictionaryKey: "CADisableMinimumFrameDurationOnPhone") as? Bool

        XCTAssertEqual(enabled, true)
    }

    func testAppBundleIdentifierIsLeoJarvis() {
        // V2 起 App 由 CortexFleet 改名为 LeoJarvis，bundle id 随之更新。
        // 旧的 com.leo.cortexfleet 是不同 bundle 的历史 App，需手动删除（见 README）。
        XCTAssertEqual(Bundle.main.bundleIdentifier, "com.leo.leojarvis.ios")
    }

    func testChineseFallbackAvoidsHalfTranslatedSocialSecurityTitle() {
        let title = ChineseLocalizer.fallback(
            "How to work in retirement without seeing your Social Security checks slashed",
            prefix: "中文标题",
            maxLength: 140
        )

        XCTAssertFalse(title.localizedCaseInsensitiveContains("Social 安全"), title)
        XCTAssertFalse(title.localizedCaseInsensitiveContains("Social Security"), title)
        XCTAssertTrue(title.contains("社会保障") || title.contains("退休"), title)
        XCTAssertFalse(ChineseLocalizer.needsChinese(title), title)
    }

    func testChineseFallbackHandlesPersonalFinanceMarketWatchTitles() {
        let retire = ChineseLocalizer.fallback(
            "‘I’m realist’: I’m 50 $6.5 million saved. Should I quit my $200,000 job and retire early?",
            prefix: "中文标题",
            maxLength: 160
        )
        let giving = ChineseLocalizer.fallback(
            "‘Money can make you happy’: My wife and I no heirs, but we’re making world better place by giving it away",
            prefix: "中文标题",
            maxLength: 160
        )
        let children = ChineseLocalizer.fallback(
            "‘We habitually frugal’: My wife and I money. How do we help children without ruining their independence?",
            prefix: "中文标题",
            maxLength: 160
        )

        XCTAssertTrue(retire.contains("提前退休"), retire)
        XCTAssertTrue(giving.contains("捐赠"), giving)
        XCTAssertTrue(children.contains("帮助子女"), children)
        XCTAssertFalse(ChineseLocalizer.needsChinese(retire), retire)
        XCTAssertFalse(ChineseLocalizer.needsChinese(giving), giving)
        XCTAssertFalse(ChineseLocalizer.needsChinese(children), children)
    }

    func testChineseFallbackRemovesEnglishStopwordFragments() {
        let title = ChineseLocalizer.fallback(
            "A new agentic workflow automation benchmark for AI coding agents",
            prefix: "中文标题",
            maxLength: 160
        )

        XCTAssertFalse(title.localizedCaseInsensitiveContains("A new"), title)
        XCTAssertFalse(title.localizedCaseInsensitiveContains("for AI coding"), title)
        XCTAssertTrue(title.contains("基准测试"), title)
        XCTAssertFalse(ChineseLocalizer.needsChinese(title), title)
    }

    func testChineseFallbackDetectsMixedChineseEnglishTitle() {
        let title = ChineseLocalizer.fallback(
            "大语言模型 Are Complicated Now（重复）",
            prefix: "中文标题",
            maxLength: 120
        )

        XCTAssertFalse(title.localizedCaseInsensitiveContains("Are Complicated Now"), title)
        XCTAssertFalse(title.localizedCaseInsensitiveContains("Are"), title)
        XCTAssertTrue(title.contains("大语言模型"), title)
        XCTAssertFalse(ChineseLocalizer.needsChinese(title), title)
    }

    func testChineseDetectionAllowsTechnicalProperNounsInChineseTitle() {
        let title = "NASA 测试新一代月球 / 火星探测车原型 ERNEST：含主动悬挂与 AI 强化自主系统"

        XCTAssertFalse(ChineseLocalizer.needsChinese(title), title)
    }

    func testLocalIntelDisplayTitleUsesChineseSafeFallback() {
        let now = Date()
        let item = LocalIntelItem(
            id: "pytest-marketwatch-social-security",
            title: "How to work in retirement without seeing your Social Security checks slashed",
            summary: "Claiming benefits before full retirement age can trigger Social Security withholdings.",
            url: "https://example.com/social-security",
            source: "MarketWatch",
            channel: "财经",
            category: "财经",
            priority: "新",
            score: 0.44,
            tags: ["财经"],
            publishedAt: now,
            collectedAt: now,
            rawContent: nil
        )

        let title = ChineseLocalizer.displayTitle(for: item)

        XCTAssertFalse(title.localizedCaseInsensitiveContains("Social 安全"), title)
        XCTAssertFalse(title.localizedCaseInsensitiveContains("Social Security"), title)
        XCTAssertTrue(title.contains("社会保障") || title.contains("退休"), title)
        XCTAssertFalse(ChineseLocalizer.needsChinese(title), title)
    }

    func testChineseLocalizerDetectsGenericSyntheticTitles() {
        XCTAssertTrue(ChineseLocalizer.isGenericSyntheticTitle("AI 与开发者工具资讯：AI"))
        XCTAssertTrue(ChineseLocalizer.isGenericSyntheticTitle("海外资讯：Mac"))
        XCTAssertTrue(ChineseLocalizer.isGenericSyntheticTitle("海外资讯：Claude"))
        XCTAssertTrue(ChineseLocalizer.isGenericSyntheticTitle("TechCrunch 资讯"))
        XCTAssertTrue(ChineseLocalizer.isGenericSyntheticTitle("Hacker News Front Page资讯"))
        XCTAssertTrue(ChineseLocalizer.isGenericSyntheticTitle("Claude"))
        XCTAssertTrue(ChineseLocalizer.isGenericSyntheticTitle("AI 相关动态"))
        XCTAssertTrue(ChineseLocalizer.isGenericSyntheticTitle("Hacker News Front Page：AI相关资讯"))
        XCTAssertFalse(ChineseLocalizer.isGenericSyntheticTitle("谷歌 Gemini 联席负责人转投 OpenAI"))
        XCTAssertFalse(ChineseLocalizer.isGenericSyntheticTitle("Cloudflare 为 AI Agent 推出临时账户"))
    }

    func testChineseLocalizerCleansBackendTranslationLabels() {
        let clean = ChineseLocalizer.cleanDisplayText(
            "标题：StartupWiki：免费初创企业数据库  \n摘要：我一直在构建 StartupWiki，这是一个免费的初创企业数据库。"
        )

        XCTAssertFalse(clean.contains("标题："), clean)
        XCTAssertFalse(clean.contains("摘要："), clean)
        XCTAssertTrue(clean.contains("免费初创企业数据库"), clean)
    }

    func testLocalIntelDisplayTitleKeepsSpecificEnglishWhenChineseFallbackCannotInfer() {
        let now = Date()
        let item = LocalIntelItem(
            id: "pytest-specific-english",
            title: "Show HN: My Windows XP portfolio with working Game Boy and iPod",
            summary: "A detailed personal portfolio project with retro interactive UI.",
            url: nil,
            source: "Hacker News Front Page",
            channel: "科技",
            category: "科技",
            priority: "高时效",
            score: 0.72,
            tags: ["科技"],
            publishedAt: now,
            collectedAt: now,
            rawContent: nil
        )

        let title = ChineseLocalizer.displayTitle(for: item)

        XCTAssertTrue(title.contains("Windows XP"), title)
        XCTAssertTrue(title.contains("作品集"), title)
        XCTAssertFalse(title.localizedCaseInsensitiveContains("portfolio"), title)
        XCTAssertFalse(title.contains("相关资讯"), title)
        XCTAssertFalse(ChineseLocalizer.needsChinese(title), title)
    }

    func testLocalIntelDisplayTitleLocalizesShowHNProjectTitles() {
        let now = Date()
        let item = LocalIntelItem(
            id: "pytest-show-hn-startupwiki",
            title: "Show HN: StartupWiki – Free Alternative Crunchbase",
            summary: "A free startup database for founders and investors.",
            url: nil,
            source: "Hacker News Front Page",
            channel: "科技",
            category: "科技",
            priority: "高时效",
            score: 0.72,
            tags: ["科技"],
            publishedAt: now,
            collectedAt: now,
            rawContent: nil
        )

        let title = ChineseLocalizer.displayTitle(for: item)

        XCTAssertTrue(title.contains("Show HN 项目"), title)
        XCTAssertTrue(title.contains("StartupWiki"), title)
        XCTAssertTrue(title.contains("免费"), title)
        XCTAssertTrue(title.contains("Crunchbase"), title)
        XCTAssertFalse(title.contains("相关资讯"), title)
    }

    func testLocalIntelDisplayTitleLocalizesCommonEnglishNewsTitles() {
        let now = Date()
        let roth = LocalIntelItem(
            id: "pytest-roth-401k",
            title: "I’m 55 and retiring in 6 years. Should I be switching Roth 401(k) contributions now?",
            summary: "Retirement planning question about Roth 401(k) contributions.",
            url: nil,
            source: "MarketWatch",
            channel: "财经",
            category: "财经",
            priority: "高时效",
            score: 0.64,
            tags: ["财经"],
            publishedAt: now,
            collectedAt: now,
            rawContent: nil
        )
        let bigTech = LocalIntelItem(
            id: "pytest-big-tech-uk",
            title: "Big Tech stoking unrest in UK. Why?",
            summary: "A Hacker News discussion about large technology companies and UK policy.",
            url: nil,
            source: "Hacker News Front Page",
            channel: "科技",
            category: "科技",
            priority: "高时效",
            score: 0.61,
            tags: ["科技"],
            publishedAt: now,
            collectedAt: now,
            rawContent: nil
        )

        let rothTitle = ChineseLocalizer.displayTitle(for: roth)
        let techTitle = ChineseLocalizer.displayTitle(for: bigTech)

        XCTAssertTrue(rothTitle.contains("退休"), rothTitle)
        XCTAssertTrue(rothTitle.contains("Roth 401(k)"), rothTitle)
        XCTAssertFalse(rothTitle.localizedCaseInsensitiveContains("Should I"), rothTitle)
        XCTAssertTrue(techTitle.contains("大型科技公司"), techTitle)
        XCTAssertTrue(techTitle.contains("英国"), techTitle)
        XCTAssertFalse(techTitle.localizedCaseInsensitiveContains("Why"), techTitle)
    }

    func testLocalIntelDisplayTitleLocalizesVisibleHackerNewsFallbacks() {
        let now = Date()
        let pdf = LocalIntelItem(
            id: "pytest-show-hn-pdf",
            title: "Show HN: Make PDFs look scanned (CLI or in browser via WASM)",
            summary: "A tool for making PDF files look like scanned documents.",
            url: nil,
            source: "Hacker News Front Page",
            channel: "科技",
            category: "科技",
            priority: "高时效",
            score: 0.58,
            tags: ["科技"],
            publishedAt: now,
            collectedAt: now,
            rawContent: nil
        )
        let dos = LocalIntelItem(
            id: "pytest-dos-reversing",
            title: "DOS Game \"F-15 Strike Eagle II\" reversing project needs DOS test pilots",
            summary: "A reverse engineering project is asking for people who can test the game in DOS.",
            url: nil,
            source: "Hacker News Front Page",
            channel: "科技",
            category: "科技",
            priority: "高时效",
            score: 0.57,
            tags: ["科技"],
            publishedAt: now,
            collectedAt: now,
            rawContent: nil
        )

        let pdfTitle = ChineseLocalizer.displayTitle(for: pdf)
        let dosTitle = ChineseLocalizer.displayTitle(for: dos)

        XCTAssertTrue(pdfTitle.contains("扫描件效果"), pdfTitle)
        XCTAssertFalse(pdfTitle.localizedCaseInsensitiveContains("look scanned"), pdfTitle)
        XCTAssertFalse(ChineseLocalizer.needsChinese(pdfTitle), pdfTitle)
        XCTAssertTrue(dosTitle.contains("逆向项目"), dosTitle)
        XCTAssertTrue(dosTitle.contains("测试玩家"), dosTitle)
        XCTAssertFalse(dosTitle.localizedCaseInsensitiveContains("reversing project"), dosTitle)
        XCTAssertFalse(ChineseLocalizer.needsChinese(dosTitle), dosTitle)
    }

    func testGitHubProjectDescriptionLocalizesForDetailContext() {
        let detail = ChineseLocalizer.fallback(
            "Makes PDFs look scanned (CLI or in the browser via WASM)",
            prefix: "中文摘要",
            maxLength: 180
        )

        XCTAssertTrue(detail.contains("PDF"), detail)
        XCTAssertTrue(detail.contains("扫描件效果"), detail)
        XCTAssertTrue(detail.contains("命令行") || detail.contains("CLI"), detail)
        XCTAssertFalse(ChineseLocalizer.needsChinese(detail), detail)
        XCTAssertEqual(
            LocalIntelSourceExtractor.githubRepositoryName(from: "https://github.com/overflowy/make-look-scanned"),
            "overflowy/make-look-scanned"
        )
    }

    func testLocalIntelDisplayTitleLocalizesScienceHackerNewsTitle() {
        let now = Date()
        let item = LocalIntelItem(
            id: "pytest-science-hn",
            title: "ability regrow body parts dormant in mammals, not lost",
            summary: "Researchers say mammals may retain dormant regenerative ability.",
            url: nil,
            source: "Hacker News Front Page",
            channel: "科技",
            category: "科技",
            priority: "新",
            score: 0.58,
            tags: ["科技"],
            publishedAt: now,
            collectedAt: now,
            rawContent: nil
        )

        let title = ChineseLocalizer.displayTitle(for: item)

        XCTAssertTrue(title.contains("哺乳动物") || title.contains("再生"), title)
        XCTAssertFalse(ChineseLocalizer.needsChinese(title), title)
    }

    func testLocalIntelDisplayTitleLocalizesPostgresBenchmarkTitle() {
        let now = Date()
        let item = LocalIntelItem(
            id: "pytest-postgresbench",
            title: "PostgresBench: Reproducible benchmark for Postgres services",
            summary: "A benchmark suite for repeatable database service tests.",
            url: nil,
            source: "Hacker News Front Page",
            channel: "科技",
            category: "科技",
            priority: "高时效",
            score: 0.68,
            tags: ["benchmark"],
            publishedAt: now,
            collectedAt: now,
            rawContent: nil
        )

        let title = ChineseLocalizer.displayTitle(for: item)

        XCTAssertTrue(title.contains("可复现"), title)
        XCTAssertTrue(title.contains("服务基准测试"), title)
        XCTAssertFalse(title.localizedCaseInsensitiveContains("Reproducible benchmark"), title)
        XCTAssertFalse(ChineseLocalizer.needsChinese(title), title)

        let variant = ChineseLocalizer.fallback(
            "PostgresBench: Reproducible benchmark Postgres Services",
            prefix: "中文标题",
            maxLength: 120
        )
        XCTAssertEqual(variant, "PostgresBench：可复现的 Postgres 服务基准测试")
    }

    func testLocalIntelDisplayTitleLocalizesVisibleMarketWatchFallbacks() {
        let now = Date()
        let item = LocalIntelItem(
            id: "pytest-fed-wall-street",
            title: "Fed forcing Wall Street do heavy lifting. Use these benchmarks find footing.",
            summary: "MarketWatch article about the Federal Reserve, Wall Street and benchmarks.",
            url: nil,
            source: "MarketWatch",
            channel: "财经",
            category: "财经",
            priority: "高时效",
            score: 0.57,
            tags: ["财经", "benchmark"],
            publishedAt: now,
            collectedAt: now,
            rawContent: nil
        )

        let title = ChineseLocalizer.displayTitle(for: item)

        XCTAssertTrue(title.contains("美联储"), title)
        XCTAssertTrue(title.contains("华尔街"), title)
        XCTAssertTrue(title.contains("市场方向"), title)
        XCTAssertFalse(title.localizedCaseInsensitiveContains("Wall Street"), title)
        XCTAssertFalse(ChineseLocalizer.needsChinese(title), title)
    }

    func testLocalRSSParserKeepsCleanRawContentFromCDATA() {
        let xml = """
        <?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0"><channel><item>
        <title>硬氪首发|AI陪伴机器人完成融资</title>
        <link><![CDATA[https://36kr.com/p/example?f=rss]]></link>
        <pubDate>2026-06-19 18:01:25  +0800</pubDate>
        <description><![CDATA[
          <p>硬氪获悉，AI-Native科技潮玩品牌近日完成数千万元Pre-A轮融资，资金将用于大模型迭代和硬件产品扩建。</p>
          <p>团队表示，陪伴机器人不只是会聊天的电子宠物，而是要把AI、潮玩与IP世界观结合。</p>
        ]]></description>
        </item></channel></rss>
        """

        let items = LocalFeedXMLParser().parse(Data(xml.utf8))

        XCTAssertEqual(items.count, 1)
        XCTAssertEqual(items[0].link, "https://36kr.com/p/example?f=rss")
        XCTAssertNotNil(items[0].publishedAt)
        XCTAssertTrue(items[0].rawContent.contains("AI-Native科技潮玩品牌"))
        XCTAssertFalse(items[0].rawContent.contains("<p>"))
        XCTAssertFalse(items[0].summary.contains("<p>"))
    }

    func testLocalIntelPreferenceTagsDropBrowserNoiseTerms() {
        let now = Date()
        let source = LocalFeedSource(
            name: "Hacker News Front Page",
            url: "https://hnrss.org/frontpage",
            channel: "科技",
            category: "科技",
            limit: 10
        )
        let entry = LocalFeedEntry(
            title: "Show HN: API design tool for AI product teams",
            link: "https://example.com/api-design",
            summary: "The post mentions id and it and api design, but only meaningful preferences should become visible tags.",
            publishedAt: now,
            rawContent: "The post mentions id and it and api design, but only meaningful preferences should become visible tags."
        )

        let item = LocalIntelScanner.makeItem(
            entry: entry,
            source: source,
            now: now,
            preferenceTerms: ["id", "it", "and", "api", "design", "ai"]
        )

        XCTAssertFalse(item.tags.contains("id"))
        XCTAssertFalse(item.tags.contains("it"))
        XCTAssertFalse(item.tags.contains("and"))
        XCTAssertTrue(item.tags.contains("api"))
        XCTAssertTrue(item.tags.contains("design"))
    }

    func testLocalIntelPreferenceTagsRequireWordBoundaries() {
        let now = Date()
        let source = LocalFeedSource(
            name: "MarketWatch",
            url: "https://feeds.marketwatch.com/marketwatch/topstories/",
            channel: "财经",
            category: "财经",
            limit: 8
        )
        let entry = LocalFeedEntry(
            title: "Should I quit my job and retire early? Money can make you happy.",
            link: "https://example.com/retire-early",
            summary: "Personal finance advice about early retirement.",
            publishedAt: now,
            rawContent: "Personal finance advice about early retirement."
        )

        let item = LocalIntelScanner.makeItem(
            entry: entry,
            source: source,
            now: now,
            preferenceTerms: ["ui", "app", "money"]
        )

        XCTAssertFalse(item.tags.contains("ui"))
        XCTAssertFalse(item.tags.contains("app"))
        XCTAssertTrue(item.tags.contains("money"))
    }

    func testLocalIntelSignalTermsRequireWordBoundaries() {
        let now = Date()
        let source = LocalFeedSource(
            name: "MarketWatch",
            url: "https://feeds.marketwatch.com/marketwatch/topstories/",
            channel: "财经",
            category: "财经",
            limit: 8
        )
        let entry = LocalFeedEntry(
            title: "This paid retirement plan is not about artificial intelligence",
            link: "https://example.com/paid-retirement",
            summary: "Personal finance advice with paid accounts.",
            publishedAt: now,
            rawContent: "Personal finance advice with paid accounts."
        )

        let item = LocalIntelScanner.makeItem(entry: entry, source: source, now: now)

        XCTAssertFalse(item.tags.contains("ai"))
    }

    func testLocalIntelCatalogMatchesRequestedNewsAITechScope() {
        let blockedCategories = Set(["财经", "世界", "科学", "产品"])
        let blockedNames = Set(["MarketWatch", "CNBC Finance", "WSJ Markets", "NPR News", "Product Hunt", "Quanta Magazine", "Nature News"])

        XCTAssertFalse(LocalIntelCatalog.sources.contains { blockedCategories.contains($0.category) })
        XCTAssertFalse(LocalIntelCatalog.sources.contains { blockedNames.contains($0.name) })
        XCTAssertTrue(LocalIntelCatalog.sources.contains { $0.category == "AI" })
        XCTAssertTrue(LocalIntelCatalog.sources.contains { $0.category == "科技" })
        XCTAssertTrue(LocalIntelCatalog.sources.contains { $0.category == "工程" })
        XCTAssertTrue(LocalIntelCatalog.sources.contains { $0.category == "中文" })
    }

    func testLocalIntelSortPurgesCachedOutOfScopeItems() {
        let now = Date()
        let finance = LocalIntelItem(
            id: "pytest-cached-marketwatch",
            title: "Money can make you happy",
            summary: "Personal finance advice.",
            url: "https://example.com/money",
            source: "MarketWatch",
            channel: "财经",
            category: "财经",
            priority: "高时效",
            score: 0.92,
            tags: ["财经"],
            publishedAt: now,
            collectedAt: now,
            rawContent: nil
        )
        let ai = LocalIntelItem(
            id: "pytest-openai-news",
            title: "OpenAI releases a new developer model",
            summary: "OpenAI ships an API and developer workflow update.",
            url: "https://example.com/openai-model",
            source: "OpenAI News",
            channel: "AI",
            category: "AI",
            priority: "高时效",
            score: 0.82,
            tags: ["AI", "api"],
            publishedAt: now,
            collectedAt: now,
            rawContent: nil
        )

        XCTAssertEqual(LocalIntelCache.sorted([finance, ai]).map(\.id), ["pytest-openai-news"])
    }

    func testLocalIntelStrictSourcesDropLowSignalNoiseButKeepDevTools() {
        let now = Date()
        let source = LocalFeedSource(
            name: "Hacker News Front Page",
            url: "https://hnrss.org/frontpage",
            channel: "科技",
            category: "科技",
            limit: 10
        )
        let noisy = LocalIntelScanner.makeItem(
            entry: LocalFeedEntry(
                title: "Show HN: My Windows XP portfolio with working Game Boy and iPod",
                link: "https://example.com/retro-portfolio",
                summary: "A personal portfolio project with nostalgic visuals.",
                publishedAt: now,
                rawContent: ""
            ),
            source: source,
            now: now
        )
        let devTool = LocalIntelScanner.makeItem(
            entry: LocalFeedEntry(
                title: "Show HN: PostgresBench: Reproducible benchmark for Postgres services",
                link: "https://github.com/example/postgresbench",
                summary: "A developer tool and benchmark suite for database services.",
                publishedAt: now,
                rawContent: "A developer tool and benchmark suite for database services."
            ),
            source: source,
            now: now
        )

        XCTAssertFalse(LocalIntelScanner.shouldKeepItem(noisy))
        XCTAssertTrue(LocalIntelScanner.shouldKeepItem(devTool))
    }

    func testLocalIntelDropsVisibleScreenshotNoise() {
        let now = Date()
        let hn = LocalFeedSource(
            name: "Hacker News Front Page",
            url: "https://hnrss.org/frontpage",
            channel: "科技",
            category: "科技",
            limit: 10
        )
        let tiny = LocalIntelScanner.makeItem(
            entry: LocalFeedEntry(
                title: "Show HN: Tiny",
                link: "https://example.com/tiny",
                summary: "Small personal project.",
                publishedAt: now,
                rawContent: "Small personal project."
            ),
            source: hn,
            now: now,
            preferenceTerms: ["github"]
        )
        let alice = LocalIntelScanner.makeItem(
            entry: LocalFeedEntry(
                title: "Alice impatient",
                link: "https://news.ycombinator.com/item?id=123",
                summary: "Discussion thread.",
                publishedAt: now,
                rawContent: "Discussion thread."
            ),
            source: hn,
            now: now
        )
        let placeholder = LocalIntelItem(
            id: "pytest-techcrunch-placeholder",
            title: "TechCrunch 资讯",
            summary: "来源提到科技，移动端已保留原始链接，可打开查看完整上下文。",
            url: "https://techcrunch.com/example",
            source: "TechCrunch",
            channel: "科技",
            category: "科技",
            priority: "高时效",
            score: 0.82,
            tags: ["科技"],
            publishedAt: now,
            collectedAt: now,
            rawContent: nil
        )
        let real = LocalIntelItem(
            id: "pytest-real-ai-news",
            title: "OpenAI 发布新的开发者模型能力",
            summary: "OpenAI 面向开发者发布模型和 API 更新，包含工具调用、性能改进和移动端工作流支持。",
            url: "https://example.com/openai",
            source: "OpenAI News",
            channel: "AI",
            category: "AI",
            priority: "高时效",
            score: 0.86,
            tags: ["AI", "OpenAI"],
            publishedAt: now,
            collectedAt: now,
            rawContent: nil
        )

        let sorted = LocalIntelCache.sorted([tiny, alice, placeholder, real])

        XCTAssertEqual(sorted.map(\.id), ["pytest-real-ai-news"])
    }

    func testLocalIntelSortDeduplicatesCrossSourceSameStory() {
        let now = Date()
        let hn = LocalIntelItem(
            id: "pytest-hn-postgresbench",
            title: "Show HN: PostgresBench: Reproducible benchmark for Postgres services",
            summary: "HN discussion for a database benchmark.",
            url: "https://news.ycombinator.com/item?id=123",
            source: "Hacker News Front Page",
            channel: "科技",
            category: "科技",
            priority: "高时效",
            score: 0.72,
            tags: ["benchmark"],
            publishedAt: now,
            collectedAt: now,
            rawContent: nil
        )
        let direct = LocalIntelItem(
            id: "pytest-direct-postgresbench",
            title: "PostgresBench: Reproducible benchmark for Postgres services",
            summary: "A benchmark suite for repeatable database service tests.",
            url: "https://github.com/example/postgresbench",
            source: "GitHub 高星项目",
            channel: "GitHub",
            category: "GitHub",
            priority: "高时效",
            score: 0.84,
            tags: ["GitHub", "benchmark"],
            publishedAt: now,
            collectedAt: now,
            rawContent: "项目：example/postgresbench\n介绍：A reproducible benchmark suite for Postgres services."
        )

        let sorted = LocalIntelCache.sorted([hn, direct])

        XCTAssertEqual(sorted.filter { $0.title.localizedCaseInsensitiveContains("PostgresBench") }.count, 1)
        XCTAssertEqual(sorted.first?.id, "pytest-direct-postgresbench")
        XCTAssertEqual(sorted.first?.rawContent, direct.rawContent)
    }

    func testGitHubHighStarProjectScannerBuildsScopedItems() throws {
        let now = Date()
        let query = "stars:>80 pushed:>2026-06-01 ai"
        let requestURL = try XCTUnwrap(GitHubHighStarProjectScanner.requestURL(query: query))

        XCTAssertEqual(requestURL.host, "api.github.com")
        XCTAssertTrue(requestURL.absoluteString.contains("/search/repositories"))
        XCTAssertTrue(requestURL.absoluteString.contains("per_page=8"))

        let repo = GitHubRepoSearchItem(
            full_name: "example/agent-cli",
            html_url: "https://github.com/example/agent-cli",
            description: "AI agent CLI for developer workflows",
            stargazers_count: 420,
            language: "Swift",
            topics: ["ai", "agent", "cli"],
            homepage: nil,
            created_at: now.addingTimeInterval(-36 * 3600),
            pushed_at: now.addingTimeInterval(-2 * 3600),
            fork: false,
            archived: false
        )
        let item = try XCTUnwrap(GitHubHighStarProjectScanner.makeItem(repo: repo, query: query, now: now))

        XCTAssertEqual(item.source, "GitHub 高星项目")
        XCTAssertEqual(item.category, "GitHub")
        XCTAssertEqual(item.priority, "高时效")
        XCTAssertTrue(item.tags.contains("高星项目"))
        XCTAssertTrue(LocalIntelScanner.shouldKeepItem(item))
    }

    func testLocalIntelSourceExtractorUsesMetaDescription() {
        let html = """
        <html><head>
        <meta property="og:description" content="这是一段来自原始网页的情报详情，包含足够的信息用于移动端离线展示和快速判断。">
        </head><body><p>备用正文段落。</p></body></html>
        """

        let excerpt = LocalIntelSourceExtractor.extractExcerpt(from: html)

        XCTAssertEqual(excerpt, "这是一段来自原始网页的情报详情，包含足够的信息用于移动端离线展示和快速判断。")
    }

    func testLocalIntelReaderExtractorRemovesBoilerplate() {
        let markdown = """
        Title: Example
        URL Source: https://example.com/post
        Warning: This is a cached snapshot of the original page.
        Markdown Content:

        # Example

        [OpenAI 发布新的开发者工具](https://example.com/post) 正在改变移动端情报处理流程，这段内容足够长，可以作为详情页的正文摘录展示。

        Subscribe to our newsletter
        """

        let excerpt = LocalIntelSourceExtractor.extractReaderExcerpt(from: markdown)

        XCTAssertNotNil(excerpt)
        XCTAssertTrue(excerpt?.contains("移动端情报处理流程") ?? false)
        XCTAssertFalse(excerpt?.contains("URL Source") ?? true)
        XCTAssertFalse(excerpt?.contains("Subscribe") ?? true)
    }

    func testLocalIntelCacheMergesFetchedDetailForOfflineReuse() {
        let now = Date()
        let item = LocalIntelItem(
            id: "pytest-detail-cache",
            title: "OpenAI 发布新的开发者工具",
            summary: "来源提到AI，移动端已保留原始链接，可打开查看完整上下文。",
            url: "https://example.com/openai",
            source: "OpenAI News",
            channel: "AI",
            category: "AI",
            priority: "高时效",
            score: 0.82,
            tags: ["AI"],
            publishedAt: now,
            collectedAt: now,
            rawContent: nil
        )
        let detail = "OpenAI 面向开发者发布新的工具链能力，包含移动端可快速阅读的详情、API 更新和工作流改进。"

        let merged = LocalIntelCache.mergingDetail(itemID: item.id, excerpt: detail, into: [item])

        XCTAssertEqual(merged.first?.rawContent, detail)
        XCTAssertEqual(ChineseLocalizer.displayBodyExcerpt(for: try XCTUnwrap(merged.first)), detail)
    }

    func testLocalIntelDetailExcerptUsesFastLocalFallback() async {
        let excerpt = await ChineseLocalizer.localizeDetailExcerpt(
            "The ability to regrow body parts is dormant in mammals, not lost. Researchers say this changes regenerative medicine priorities.",
            client: nil,
            maxLength: 240
        )

        XCTAssertNotNil(excerpt)
        XCTAssertFalse(ChineseLocalizer.needsChinese(excerpt), excerpt ?? "")
        XCTAssertTrue(excerpt?.contains("哺乳动物") ?? false, excerpt ?? "")
    }

    func testLocalIntelScanReportCountsDegradedSources() {
        let report = LocalIntelScanReport(
            items: [],
            attemptedCount: 3,
            succeededCount: 1,
            failedSources: ["A：TLS 连接失败"],
            emptySources: ["B"]
        )

        XCTAssertEqual(report.degradedCount, 2)
    }

    func testLocalIntelScannerFetchesPrimarySourcesWhenNetworkEnabled() async throws {
        #if LEOJARVIS_NETWORK_TEST
        let enabled = true
        #else
        let env = ProcessInfo.processInfo.environment
        let enabled = env["LEOJARVIS_RUN_IOS_NETWORK_TEST"] == "1"
            || env["TEST_RUNNER_LEOJARVIS_RUN_IOS_NETWORK_TEST"] == "1"
        #endif
        guard enabled else {
            throw XCTSkip("Set LEOJARVIS_RUN_IOS_NETWORK_TEST=1 to run live RSS/Atom scanner validation.")
        }

        let report = await LocalIntelScanner.scanWithReport(
            existing: [],
            timeout: 10,
            preferenceTerms: ["openai", "agent", "ios", "mac"]
        )

        XCTAssertGreaterThanOrEqual(report.succeededCount, 20, "failed: \(report.failedSources)")
        XCTAssertGreaterThanOrEqual(report.items.count, 30)
        XCTAssertTrue(report.items.contains { !$0.isTavilySupplement })
    }

    func testLocalFeedParserHandlesFractionalISODate() {
        let xml = """
        <feed>
          <entry>
            <title>OpenAI ships an iOS agent update</title>
            <link href="https://example.com/openai-ios-agent"/>
            <summary>Developers can use the updated mobile workflow.</summary>
            <updated>2026-06-20T12:34:56.789Z</updated>
          </entry>
        </feed>
        """

        let entries = LocalFeedXMLParser().parse(Data(xml.utf8))

        XCTAssertEqual(entries.count, 1)
        XCTAssertNotNil(entries.first?.publishedAt)
    }

    func testFreshLowSignalFinanceDoesNotBecomeHighPriority() {
        let now = Date()
        let source = LocalFeedSource(
            name: "MarketWatch",
            url: "https://feeds.marketwatch.com/marketwatch/topstories/",
            channel: "财经",
            category: "财经",
            limit: 8
        )
        let entry = LocalFeedEntry(
            title: "How to work in retirement without seeing your Social Security checks slashed",
            link: "https://example.com/social-security",
            summary: "Claiming benefits before full retirement age can trigger Social Security withholdings.",
            publishedAt: now,
            rawContent: ""
        )

        let item = LocalIntelScanner.makeItem(entry: entry, source: source, now: now)

        XCTAssertNotEqual(item.priority, "高时效")
        XCTAssertLessThan(item.score, 0.68)
    }

    func testOldHighSignalLocalIntelDoesNotBecomeHighPriority() {
        let now = Date()
        let source = LocalFeedSource(
            name: "OpenAI News",
            url: "https://openai.com/news/rss.xml",
            channel: "AI",
            category: "AI",
            limit: 8
        )
        let entry = LocalFeedEntry(
            title: "OpenAI releases a new multimodal agent model for developers",
            link: "https://example.com/old-openai-agent",
            summary: "The model release includes agents, benchmarks, API updates, developer tooling and multimodal capabilities.",
            publishedAt: now.addingTimeInterval(-80 * 3600),
            rawContent: ""
        )

        let item = LocalIntelScanner.makeItem(entry: entry, source: source, now: now)

        XCTAssertEqual(item.priority, "观察")
    }

    func testLocalIntelSortKeepsTavilyAsTailFallback() {
        let now = Date()
        let primary = LocalIntelItem(
            id: "pytest-primary",
            title: "OpenAI 发布新的开发者工具",
            summary: "OpenAI 面向开发者工具链发布更新。",
            url: nil,
            source: "OpenAI News",
            channel: "AI",
            category: "AI",
            priority: "高时效",
            score: 0.74,
            tags: ["AI"],
            publishedAt: now.addingTimeInterval(-3 * 3600),
            collectedAt: now,
            rawContent: nil
        )
        let tavily = LocalIntelItem(
            id: "pytest-tavily",
            title: "Tavily paid search result",
            summary: "Paid search fallback result.",
            url: nil,
            source: "搜索补充·iPhone",
            channel: "Tavily",
            category: "搜索补充",
            priority: "搜索补充",
            score: 0.66,
            tags: ["搜索补充"],
            publishedAt: now,
            collectedAt: now,
            rawContent: nil
        )

        let sorted = LocalIntelCache.sorted([tavily, primary])

        XCTAssertEqual(sorted.first?.id, "pytest-primary")
    }

    func testLocalIntelSortRemovesTavilyWhenPrimarySourcesAreEnough() {
        let now = Date()
        let primaries = (0..<4).map { index in
            LocalIntelItem(
                id: "pytest-primary-\(index)",
                title: "OpenAI 发布开发者模型能力 \(index)",
                summary: "OpenAI 面向开发者发布模型和 API 更新，包含工具调用、性能改进和移动端工作流支持。",
                url: nil,
                source: "RSS",
                channel: "AI",
                category: "AI",
                priority: "新",
                score: 0.54,
                tags: ["AI"],
                publishedAt: now.addingTimeInterval(TimeInterval(-index * 600)),
                collectedAt: now,
                rawContent: nil
            )
        }
        let tavily = LocalIntelItem(
            id: "pytest-tavily",
            title: "Tavily paid search result",
            summary: "Paid search fallback result.",
            url: nil,
            source: "搜索补充·iPhone",
            channel: "Tavily",
            category: "搜索补充",
            priority: "搜索补充",
            score: 0.66,
            tags: ["搜索补充"],
            publishedAt: now,
            collectedAt: now,
            rawContent: nil
        )

        let sorted = LocalIntelCache.sorted(primaries + [tavily])

        XCTAssertEqual(sorted.map(\.id), ["pytest-primary-0", "pytest-primary-1", "pytest-primary-2", "pytest-primary-3"])
    }

    func testLocalIntelSortAllowsOneTavilyFallbackWhenOnlyStalePrimaryExists() {
        let now = Date()
        let stalePrimaries = (0..<4).map { index in
            LocalIntelItem(
                id: "pytest-stale-primary-\(index)",
                title: "旧主信源 \(index)",
                summary: "超过 24 小时的旧 RSS/Atom 主信源。",
                url: nil,
                source: "RSS",
                channel: "科技",
                category: "科技",
                priority: "观察",
                score: 0.50,
                tags: ["科技"],
                publishedAt: now.addingTimeInterval(-30 * 3600 - TimeInterval(index)),
                collectedAt: now,
                rawContent: nil
            )
        }
        let tavily = LocalIntelItem(
            id: "pytest-tavily-stale-primary-fallback",
            title: "OpenAI 发布企业级智能体 API 控制台",
            summary: "OpenAI 发布面向企业开发者的智能体 API 控制台，包含管理员策略、审计日志和开发流程更新。",
            url: nil,
            source: "搜索补充·iPhone",
            channel: "Tavily",
            category: "搜索补充",
            priority: "搜索补充",
            score: 0.66,
            tags: ["搜索补充"],
            publishedAt: now,
            collectedAt: now,
            rawContent: nil
        )

        let sorted = LocalIntelCache.sorted(stalePrimaries + [tavily])

        XCTAssertEqual(sorted.last?.id, "pytest-tavily-stale-primary-fallback")
        XCTAssertEqual(sorted.filter(\.isTavilySupplement).count, 1)
    }

    func testLocalIntelSortDropsGenericSyntheticLocalTitles() {
        let now = Date()
        let generic = LocalIntelItem(
            id: "pytest-generic",
            title: "海外资讯：Claude",
            summary: "来源提到AI，移动端已保留原始链接。",
            url: nil,
            source: "海外资讯",
            channel: "科技",
            category: "科技",
            priority: "新",
            score: 0.71,
            tags: ["AI"],
            publishedAt: now,
            collectedAt: now,
            rawContent: nil
        )
        let real = LocalIntelItem(
            id: "pytest-real",
            title: "谷歌 Gemini 联席负责人转投 OpenAI",
            summary: "管理层变动会影响模型产品节奏。",
            url: nil,
            source: "TechCrunch",
            channel: "科技",
            category: "科技",
            priority: "高时效",
            score: 0.82,
            tags: ["AI"],
            publishedAt: now,
            collectedAt: now,
            rawContent: nil
        )

        XCTAssertEqual(LocalIntelCache.sorted([generic, real]).map(\.id), ["pytest-real"])
    }

    func testLocalIntelPreviewSummaryHidesLowInformationFallback() {
        let now = Date()
        let item = LocalIntelItem(
            id: "pytest-low-info-summary",
            title: "蔚来补上“智驾课”，任少卿总结：智驾技术创新将重构竞争",
            summary: "来源提到智能体、AI、大语言模型、模型，移动端已保留原始链接，可打开查看完整上下文。",
            url: nil,
            source: "36氪",
            channel: "中文",
            category: "中文",
            priority: "高时效",
            score: 0.82,
            tags: ["AI"],
            publishedAt: now,
            collectedAt: now,
            rawContent: nil
        )

        XCTAssertNil(ChineseLocalizer.displayPreviewSummary(for: item))
        XCTAssertNil(ChineseLocalizer.displayBodyExcerpt(for: item))
        XCTAssertFalse(ChineseLocalizer.displayTitle(for: item).contains("来源提到"))
    }

    func testLocalIntelDetailBodyPrefersRealRawContentOverLowInformationSummary() {
        let now = Date()
        let item = LocalIntelItem(
            id: "pytest-real-raw-content",
            title: "蔚来补上“智驾课”，任少卿总结：智驾技术创新将重构竞争",
            summary: "来源提到智能体、AI、大语言模型、模型，移动端已保留原始链接，可打开查看完整上下文。",
            url: nil,
            source: "36氪",
            channel: "中文",
            category: "中文",
            priority: "高时效",
            score: 0.82,
            tags: ["AI"],
            publishedAt: now,
            collectedAt: now,
            rawContent: "蔚来强化智能驾驶组织和算法路线，任少卿认为端到端模型、数据闭环和车端算力会成为下一阶段竞争焦点。"
        )

        let body = ChineseLocalizer.displayBodyExcerpt(for: item)
        XCTAssertEqual(body, item.rawContent)
        XCTAssertFalse(body?.contains("来源提到") ?? true)
        XCTAssertFalse(body?.contains("移动端已保留原始链接") ?? true)
    }

    func testLocalIntelSortUsesFreshnessWindowBeforeImportance() {
        let now = Date()
        let freshLow = LocalIntelItem(
            id: "pytest-fresh-low",
            title: "两小时内的普通新资讯",
            summary: "仍在最高时效窗口内。",
            url: nil,
            source: "OpenAI News",
            channel: "AI",
            category: "AI",
            priority: "新",
            score: 0.54,
            tags: ["AI"],
            publishedAt: now.addingTimeInterval(-2 * 3600),
            collectedAt: now,
            rawContent: nil
        )
        let sameWindowHigh = LocalIntelItem(
            id: "pytest-same-window-high",
            title: "五小时内的高信号开发者资讯",
            summary: "同一个 6 小时时效窗口内，重要性应该优先。",
            url: nil,
            source: "GitHub Blog",
            channel: "工程",
            category: "工程",
            priority: "高时效",
            score: 0.82,
            tags: ["工程", "AI"],
            publishedAt: now.addingTimeInterval(-5 * 3600),
            collectedAt: now,
            rawContent: nil
        )
        let olderHigh = LocalIntelItem(
            id: "pytest-older-high",
            title: "三十小时前的高分资讯",
            summary: "分数很高但已经不在 24 小时时效窗口。",
            url: nil,
            source: "TechCrunch",
            channel: "科技",
            category: "科技",
            priority: "高优先",
            score: 0.95,
            tags: ["科技"],
            publishedAt: now.addingTimeInterval(-30 * 3600),
            collectedAt: now,
            rawContent: nil
        )

        let sorted = LocalIntelCache.sorted([olderHigh, freshLow, sameWindowHigh])

        XCTAssertEqual(sorted.map(\.id), ["pytest-same-window-high", "pytest-fresh-low", "pytest-older-high"])
    }

    func testMCPSearchRequestMarksPaidFallbackPurpose() throws {
        let request = MCPSearchRequest(
            query: "latest AI news",
            limit: 2,
            include_answer: false,
            purpose: "intel_fallback"
        )
        let data = try JSONEncoder().encode(request)
        let json = String(data: data, encoding: .utf8) ?? ""

        XCTAssertTrue(json.contains("\"purpose\":\"intel_fallback\""), json)
        XCTAssertTrue(json.contains("\"limit\":2"), json)
    }

    // MARK: - 离线韧性（V4）

    @MainActor
    func testNetworkErrorTranslatedToChinese() {
        let cannotConnect = NSError(domain: NSURLErrorDomain, code: NSURLErrorCannotConnectToHost)
        let timedOut = NSError(domain: NSURLErrorDomain, code: NSURLErrorTimedOut)
        let dns = NSError(domain: NSURLErrorDomain, code: NSURLErrorCannotFindHost)
        // Mac 端错误必须中文化，不能再冒出 "Could not connect to the server." 这类生英文
        XCTAssertTrue(JarvisStore.networkErrorChinese(cannotConnect).contains("无法连接 Mac"))
        XCTAssertTrue(JarvisStore.networkErrorChinese(timedOut).contains("超时"))
        XCTAssertTrue(JarvisStore.networkErrorChinese(dns).contains("DNS"))
        // 走 userFacingErrorMessage 也应是中文，且取消类返回 nil
        XCTAssertEqual(JarvisStore.userFacingErrorMessage(cannotConnect)?.contains("无法连接 Mac"), true)
        let cancelled = NSError(domain: NSURLErrorDomain, code: NSURLErrorCancelled)
        XCTAssertNil(JarvisStore.userFacingErrorMessage(cancelled))
    }

    @MainActor
    func testDedupedFailureMessageCollapsesRepeats() {
        // 5 个接口对同一台死 Mac 报同一句 → 横幅不应重复显示
        let failures = ["健康：无法连接 Mac", "系统：无法连接 Mac", "简报：无法连接 Mac"]
        let msg = JarvisStore.dedupedFailureMessage(failures) ?? ""
        XCTAssertFalse(msg.isEmpty)
        // 去重后最多两条且彼此不同
        let parts = msg.components(separatedBy: "；")
        XCTAssertEqual(parts.count, Set(parts).count, "去重后不应有重复段：\(msg)")
    }

    func testBundledWhisperModelAvailableForOfflineSpeech() {
        let url = LocalWhisperTranscriber.bundledModelURL()
        XCTAssertNotNil(url)
        XCTAssertEqual(url?.lastPathComponent, "ggml-base.bin")
        let sizeMB = LocalWhisperTranscriber.bundledModelSizeMB()
        XCTAssertNotNil(sizeMB)
        XCTAssertGreaterThan(sizeMB ?? 0, 100)
        XCTAssertLessThan(sizeMB ?? 0, 180)
    }

    func testLocalWhisperTranscribesBundledSampleWhenEnabled() async throws {
        #if LEOJARVIS_WHISPER_TEST
        let enabled = true
        #else
        let env = ProcessInfo.processInfo.environment
        let enabled = env["LEOJARVIS_RUN_IOS_WHISPER_TEST"] == "1"
            || env["TEST_RUNNER_LEOJARVIS_RUN_IOS_WHISPER_TEST"] == "1"
        #endif
        guard enabled else {
            throw XCTSkip("Set LEOJARVIS_RUN_IOS_WHISPER_TEST=1 to run the on-device Whisper integration test.")
        }
        let sampleURL = Bundle.main.url(forResource: "jfk", withExtension: "wav", subdirectory: "samples")
            ?? Bundle.main.url(forResource: "jfk", withExtension: "wav")
        let url = try XCTUnwrap(sampleURL)
        let text = try await LocalWhisperTranscriber.shared.transcribe(wavURL: url, language: "en")
        XCTAssertTrue(text.localizedCaseInsensitiveContains("fellow Americans"), text)
    }

    private func makeRemoteSnapshot(savedAt: Date) -> RemoteSnapshot {
        let now = Date()
        let briefingItem = BriefingItem(
            event_id: "pytest-briefing-cache",
            title: "缓存情报可离线查看",
            original_title: nil,
            source: "RSS 资讯",
            source_raw: "rss:pytest",
            url: "https://example.com/cache",
            domain: nil,
            domain_label: nil,
            kind: "news",
            score: 0.8,
            priority: "高优先",
            take: "断网时仍应显示最近同步内容。",
            why_important: "验证 iPhone 离线读能力。",
            relation: "LeoJarvis 移动端",
            next_step: "联网后刷新。",
            tags: ["缓存"],
            detail: "缓存详情",
            content: "缓存正文",
            source_detail: "缓存来源正文",
            source_detail_raw: nil,
            source_detail_translated: true,
            source_detail_missing: false,
            triage: "notify",
            reasons: ["pytest"],
            ts: Int(now.timeIntervalSince1970),
            ingested_ts: Int(now.timeIntervalSince1970),
            repo_stars: nil,
            repo_speed: nil,
            channel: "RSS",
            category: "测试"
        )
        let briefing = BriefingData(
            generated_at: Int(now.timeIntervalSince1970),
            items: [briefingItem],
            mail: [],
            github: [],
            counts: BriefingCounts(business: 1, life: 0, total: 1, mail: 0, x: 0, github: 0, duplicates_removed: 0),
            summary: BriefingSummary(today_focus: "缓存情报可离线查看", why_it_matters: "弱网仍可读", next_action: "联网后刷新")
        )
        let note = PersonalNote(
            id: "pytest-note-cache",
            title: "缓存记事",
            content: "这条记事用于验证 iOS 离线可读。",
            excerpt: "离线可读",
            safe_excerpt: "离线可读",
            tags: ["iOS"],
            project_name: "LeoJarvis",
            source: "pytest",
            source_url: nil,
            source_title: nil,
            favorite: true,
            pinned: false,
            archived: false,
            sensitive: false,
            created_ts: Int(now.timeIntervalSince1970),
            updated_ts: Int(now.timeIntervalSince1970)
        )
        return RemoteSnapshot(
            cockpit: nil,
            briefing: briefing,
            notes: [note],
            agents: [
                CLIAgent(name: "codex", display: "Codex", installed: true, bin: "/usr/bin/codex", version: "pytest", auth: "ok", run_supported: "confirmed", docs: nil)
            ],
            sessions: [],
            devices: [],
            briefingDetails: ["pytest-briefing-cache": briefingItem],
            lastRefreshed: now,
            savedAt: savedAt
        )
    }
}
