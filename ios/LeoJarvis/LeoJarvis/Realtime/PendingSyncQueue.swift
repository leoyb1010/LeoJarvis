import Foundation

// 离线待同步队列：Mac 不可达时把「记一笔」等本地写操作排队（UserDefaults 持久化），
// 联网/bootstrap 时自动 flush。首版只覆盖最高频的离线写：创建笔记。
// 纯数据 + 纯函数为主，便于单测。

/// 一条待同步的本地写操作。
struct PendingNote: Codable, Identifiable, Equatable {
    let id: String
    let title: String
    let content: String
    let createdAt: Double   // 入队毫秒时间戳（仅排序用，不参与逻辑分支）

    init(id: String, title: String, content: String, createdAt: Double) {
        self.id = id
        self.title = title
        self.content = content
        self.createdAt = createdAt
    }
}

enum PendingSyncQueue {
    private static let key = "leojarvis.mobile.pendingNotes.v1"
    private static let maxItems = 100

    /// 当前队列（按入队顺序）。
    static func load(defaults: UserDefaults = .standard) -> [PendingNote] {
        guard let data = defaults.data(forKey: key),
              let items = try? JSONDecoder().decode([PendingNote].self, from: data) else { return [] }
        return items
    }

    /// 入队一条（满了丢最旧的，避免无界增长）。返回更新后的队列。
    @discardableResult
    static func enqueue(_ note: PendingNote, defaults: UserDefaults = .standard) -> [PendingNote] {
        var items = load(defaults: defaults)
        items.append(note)
        if items.count > maxItems {
            items.removeFirst(items.count - maxItems)
        }
        save(items, defaults: defaults)
        return items
    }

    /// 移除一条（同步成功后）。返回更新后的队列。
    @discardableResult
    static func remove(id: String, defaults: UserDefaults = .standard) -> [PendingNote] {
        var items = load(defaults: defaults)
        items.removeAll { $0.id == id }
        save(items, defaults: defaults)
        return items
    }

    static func isEmpty(defaults: UserDefaults = .standard) -> Bool {
        load(defaults: defaults).isEmpty
    }

    static func count(defaults: UserDefaults = .standard) -> Int {
        load(defaults: defaults).count
    }

    static func clear(defaults: UserDefaults = .standard) {
        defaults.removeObject(forKey: key)
    }

    private static func save(_ items: [PendingNote], defaults: UserDefaults) {
        if let data = try? JSONEncoder().encode(items) {
            defaults.set(data, forKey: key)
        }
    }
}
