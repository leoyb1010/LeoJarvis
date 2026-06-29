import Foundation

// 时间/日期显示格式化：相对时间、短日期、秒数转文本。从 Views.swift 拆出。
enum DisplayFormat {
    private static let shortDateFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "zh_Hans_CN")
        formatter.dateFormat = "M/d HH:mm"
        return formatter
    }()

    static func relative(_ date: Date?) -> String {
        guard let date else { return "尚未刷新" }
        let seconds = max(0, Int(Date().timeIntervalSince(date)))
        if seconds < 5 { return "刚刚" }
        if seconds < 60 { return "\(seconds) 秒前" }
        let minutes = seconds / 60
        if minutes < 60 { return "\(minutes) 分钟前" }
        let hours = minutes / 60
        if hours < 24 { return "\(hours) 小时前" }
        return "\(hours / 24) 天前"
    }

    static func shortDate(_ timestamp: Int?) -> String {
        guard let timestamp else { return "" }
        let seconds = abs(timestamp) >= 10_000_000_000 ? TimeInterval(timestamp) / 1000 : TimeInterval(timestamp)
        let date = Date(timeIntervalSince1970: seconds)
        return shortDateFormatter.string(from: date)
    }

    static func secondsAgo(_ seconds: Int?) -> String {
        guard let seconds else { return "未知" }
        if seconds < 5 { return "刚刚" }
        if seconds < 60 { return "\(seconds) 秒前" }
        let minutes = seconds / 60
        if minutes < 60 { return "\(minutes) 分钟前" }
        let hours = minutes / 60
        if hours < 24 { return "\(hours) 小时前" }
        return "\(hours / 24) 天前"
    }
}
