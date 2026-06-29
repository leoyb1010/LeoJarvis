import XCTest
@testable import LeoJarvis

/// NotifyChannel / SSE 的纯函数测试：WS URL 推导、事件解析。
final class RealtimeTests: XCTestCase {

    // MARK: - WebSocket URL 推导

    func testWebSocketURLFromHTTPSUsesWSS() {
        let url = NotifyChannel.makeWebSocketURL(httpRoot: "https://jarvis.example.com", token: "")
        XCTAssertEqual(url?.absoluteString, "wss://jarvis.example.com/ws/notify")
    }

    func testWebSocketURLFromHTTPUsesWS() {
        let url = NotifyChannel.makeWebSocketURL(httpRoot: "http://127.0.0.1:8787", token: "")
        XCTAssertEqual(url?.absoluteString, "ws://127.0.0.1:8787/ws/notify")
    }

    func testWebSocketURLInjectsToken() {
        let url = NotifyChannel.makeWebSocketURL(httpRoot: "https://jarvis.example.com", token: "secret123")
        XCTAssertEqual(url?.absoluteString, "wss://jarvis.example.com/ws/notify?token=secret123")
    }

    func testWebSocketURLStripsTrailingSlash() {
        let url = NotifyChannel.makeWebSocketURL(httpRoot: "https://jarvis.example.com/", token: "")
        XCTAssertEqual(url?.absoluteString, "wss://jarvis.example.com/ws/notify")
    }

    func testWebSocketURLEmptyRootReturnsNil() {
        XCTAssertNil(NotifyChannel.makeWebSocketURL(httpRoot: "", token: "t"))
    }

    // MARK: - NotifyEvent 解析

    func testNotifyEventParsesSystemAlert() {
        let dict: [String: JSONValue] = [
            "type": .string("notify"),
            "source": .string("SystemGuard"),
            "urgent": .bool(true),
            "body": .string("磁盘告警")
        ]
        let event = NotifyChannel.makeEvent(from: dict)
        XCTAssertEqual(event.type, "notify")
        XCTAssertEqual(event.source, "SystemGuard")
        XCTAssertTrue(event.urgent)
        XCTAssertEqual(event.body, "磁盘告警")
        XCTAssertNil(event.delivery)
    }

    func testNotifyEventDigestDeliveryParsed() {
        let dict: [String: JSONValue] = [
            "type": .string("notify"),
            "delivery": .string("digest")
        ]
        let event = NotifyChannel.makeEvent(from: dict)
        XCTAssertEqual(event.delivery, "digest")
        XCTAssertFalse(event.urgent)
    }

    func testNotifyEventFallsBackBodyFromMessageOrSummary() {
        let fromMessage = NotifyChannel.makeEvent(from: ["message": .string("来自 message")])
        XCTAssertEqual(fromMessage.body, "来自 message")
        let fromSummary = NotifyChannel.makeEvent(from: ["summary": .string("来自 summary")])
        XCTAssertEqual(fromSummary.body, "来自 summary")
    }

    func testNotifyEventDefaultsTypeToNotify() {
        let event = NotifyChannel.makeEvent(from: ["source": .string("X")])
        XCTAssertEqual(event.type, "notify")
    }

    // MARK: - 本地通知渲染

    func testRenderSystemGuardAlertGoesToToday() {
        let event = NotifyEvent(type: "notify", source: "SystemGuard", urgent: true,
                                delivery: nil, title: nil, body: "磁盘 95%", raw: [:])
        let (title, body, link) = NotificationManager.render(event)
        XCTAssertEqual(title, "系统告警")
        XCTAssertEqual(body, "磁盘 95%")
        XCTAssertEqual(link, .today)
    }

    func testRenderIntelHitGoesToIntel() {
        let event = NotifyEvent(type: "notify", source: "IntelScanner", urgent: false,
                                delivery: nil, title: nil, body: "新 GitHub 趋势", raw: [:])
        let (title, _, link) = NotificationManager.render(event)
        XCTAssertEqual(title, "情报命中")
        XCTAssertEqual(link, .intel)
    }

    func testRenderScheduleReminderGoesToToday() {
        let event = NotifyEvent(type: "remind", source: "schedule", urgent: false,
                                delivery: nil, title: nil, body: "10 分钟后开会", raw: [:])
        let (title, _, link) = NotificationManager.render(event)
        XCTAssertEqual(title, "日程提醒")
        XCTAssertEqual(link, .today)
    }

    func testRenderUnknownSourceFallsBack() {
        let event = NotifyEvent(type: "notify", source: nil, urgent: false,
                                delivery: nil, title: nil, body: "x", raw: [:])
        let (title, _, link) = NotificationManager.render(event)
        XCTAssertEqual(title, "LeoJarvis")
        XCTAssertEqual(link, .today)
    }
}
