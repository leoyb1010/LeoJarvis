import Foundation
import UserNotifications

// 本地通知管理：把 /ws/notify 的实时事件落成本地通知（前台横幅 + 后台通知中心）。
// 诚实边界：前台/挂起未杀时实时；App 被杀则收不到（本地通知 vs APNs 的本质差别，
// 设置页会注明）。点击通知按 deepLink 跳对应 tab。同一事件去重 + 限频，避免轰炸。

/// 通知点击后的深链目标（跳哪个 tab）。
enum NotifyDeepLink: String {
    case today, intel, notes, jarvis, mine
}

@MainActor
final class NotificationManager: NSObject {
    static let shared = NotificationManager()

    /// 点击通知的回调（RootView 订阅 → 切 tab）。
    var onOpenDeepLink: ((NotifyDeepLink) -> Void)?

    private var authorized = false
    // 去重：最近已通知的事件指纹（内存，限频窗口）。
    private var recentKeys: [String: Date] = [:]
    private let dedupeWindow: TimeInterval = 60

    private override init() { super.init() }

    /// 请求通知授权（首次打开「我的」感知/通知区或 bootstrap 时调用）。
    func requestAuthorization() async {
        let center = UNUserNotificationCenter.current()
        center.delegate = self
        do {
            authorized = try await center.requestAuthorization(options: [.alert, .sound, .badge])
        } catch {
            authorized = false
        }
    }

    /// 当前授权状态（用于设置页显示）。
    func currentStatus() async -> UNAuthorizationStatus {
        await UNUserNotificationCenter.current().notificationSettings().authorizationStatus
    }

    /// 把一个实时事件落成本地通知。digest（安静投递）不弹；去重窗口内重复事件不弹。
    func present(_ event: NotifyEvent) {
        guard authorized else { return }
        guard event.delivery != "digest" else { return }

        let (title, body, link) = Self.render(event)
        guard !body.isEmpty else { return }

        // 去重指纹：source + body 前 40 字。限频窗口内同指纹只弹一次。
        let key = "\(event.source ?? "")|\(body.prefix(40))"
        let now = Date()
        pruneRecent(now: now)
        if let last = recentKeys[key], now.timeIntervalSince(last) < dedupeWindow { return }
        recentKeys[key] = now

        let content = UNMutableNotificationContent()
        content.title = title
        content.body = body
        content.sound = event.urgent ? .defaultCritical : .default
        content.userInfo = ["deepLink": link.rawValue]

        let request = UNNotificationRequest(
            identifier: UUID().uuidString,
            content: content,
            trigger: nil   // 立即投递
        )
        UNUserNotificationCenter.current().add(request)
    }

    private func pruneRecent(now: Date) {
        recentKeys = recentKeys.filter { now.timeIntervalSince($0.value) < dedupeWindow }
    }

    // MARK: - 纯函数（可单测）

    /// 把事件渲染成 (标题, 正文, 深链)。按 source/type 归类。
    nonisolated static func render(_ event: NotifyEvent) -> (title: String, body: String, link: NotifyDeepLink) {
        let body = event.body ?? ""
        let source = (event.source ?? "").lowercased()
        // 来源/类型 → 标题 + 跳转目标
        if source.contains("system") || source.contains("guard") {
            return (event.urgent ? "系统告警" : "系统提示", body, .today)
        }
        if source.contains("intel") || source.contains("brief") || event.type.contains("intel") {
            return ("情报命中", body, .intel)
        }
        if source.contains("schedule") || source.contains("remind") || event.type.contains("remind") {
            return ("日程提醒", body, .today)
        }
        if source.contains("mail") || source.contains("email") {
            return ("邮件", body, .today)
        }
        if source.contains("inbox") || source.contains("task") {
            return ("待办", body, .today)
        }
        return ("LeoJarvis", body, .today)
    }
}

extension NotificationManager: UNUserNotificationCenterDelegate {
    // 前台也展示横幅 + 声音（默认前台不弹）。
    nonisolated func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        willPresent notification: UNNotification,
        withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void
    ) {
        completionHandler([.banner, .sound, .list])
    }

    // 点击通知 → 解析 deepLink → 跳 tab。
    nonisolated func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        didReceive response: UNNotificationResponse,
        withCompletionHandler completionHandler: @escaping () -> Void
    ) {
        let userInfo = response.notification.request.content.userInfo
        let linkRaw = userInfo["deepLink"] as? String
        Task { @MainActor in
            if let linkRaw, let link = NotifyDeepLink(rawValue: linkRaw) {
                self.onOpenDeepLink?(link)
            }
            completionHandler()
        }
    }
}
