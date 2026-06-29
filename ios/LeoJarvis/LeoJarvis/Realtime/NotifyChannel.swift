import Foundation

// 实时通知通道：URLSessionWebSocketTask 连后端 /ws/notify（JSON 文本帧）。
// 后端事件形如 {type:"notify", source:"SystemGuard", urgent:true, delivery:"digest", ...}，
// 也有日程提醒等。本通道负责：连接保活（ping）、断线退避重连、token 注入、事件 fan-out。
// 鉴权口径与 JarvisAPIClient 一致：本机回环免 token；远程用 Bearer + ?token= 双保险。

/// 从 /ws/notify 收到并归一化的事件。payload 保留原始字段供上层按需取用。
struct NotifyEvent: Equatable {
    let type: String
    let source: String?
    let urgent: Bool
    let delivery: String?      // "digest" 表示安静展示、不弹打断式提示
    let title: String?
    let body: String?
    let raw: [String: JSONValue]
}

@MainActor
@Observable
final class NotifyChannel {
    enum State: Equatable {
        case idle
        case connecting
        case connected
        case retrying(attempt: Int)
    }

    private(set) var state: State = .idle

    /// 事件回调（主线程）。上层（JarvisStore / NotificationManager）订阅。
    var onEvent: ((NotifyEvent) -> Void)?

    private var task: URLSessionWebSocketTask?
    private var session: URLSession = .shared
    private var endpoint: String = ""
    private var token: String = ""
    private var reconnectAttempt = 0
    private var isActive = false          // 期望保持连接（disconnect 后为 false，阻止自动重连）
    private var reconnectWorkItem: Task<Void, Never>?
    private var pingTask: Task<Void, Never>?

    private let maxBackoff: TimeInterval = 30

    /// 连接到指定端点。重复调用（如切换 Mac）会先断开旧连接再连新的。
    func connect(endpoint: String, token: String) {
        let api = JarvisAPIClient(baseURL: endpoint, token: token)
        let root = api.normalizedBaseURL
        guard !root.isEmpty, let wsURL = Self.makeWebSocketURL(httpRoot: root, token: token) else {
            state = .idle
            return
        }
        // 端点未变且已在连接/已连，无需重连。
        if isActive, self.endpoint == endpoint, self.token == token,
           case .connected = state { return }

        disconnect()                  // 清理旧连接（不触发自动重连）
        self.endpoint = endpoint
        self.token = token
        isActive = true
        reconnectAttempt = 0
        openSocket(url: wsURL)
    }

    /// 主动断开，且不再自动重连（切端点 / 退出时调用）。
    func disconnect() {
        isActive = false
        reconnectWorkItem?.cancel(); reconnectWorkItem = nil
        pingTask?.cancel(); pingTask = nil
        task?.cancel(with: .goingAway, reason: nil)
        task = nil
        state = .idle
    }

    /// App 回前台时调用：立即重连并重置退避（系统会在挂起时断开 WS）。
    func resumeIfNeeded() {
        guard isActive else { return }
        if case .connected = state { return }
        reconnectAttempt = 0
        guard let wsURL = Self.makeWebSocketURL(httpRoot: JarvisAPIClient(baseURL: endpoint, token: token).normalizedBaseURL, token: token) else { return }
        reconnectWorkItem?.cancel(); reconnectWorkItem = nil
        openSocket(url: wsURL)
    }

    // MARK: - 内部

    private func openSocket(url: URL) {
        state = .connecting
        var request = URLRequest(url: url)
        request.timeoutInterval = 0   // WS 长连不设请求超时
        let clean = token.trimmingCharacters(in: .whitespacesAndNewlines)
        if !clean.isEmpty {
            request.setValue("Bearer \(clean)", forHTTPHeaderField: "Authorization")
            request.setValue(clean, forHTTPHeaderField: "X-LeoJarvis-Token")
        }
        let task = session.webSocketTask(with: request)
        self.task = task
        task.resume()
        state = .connected
        reconnectAttempt = 0
        startPing()
        receiveLoop()
    }

    private func receiveLoop() {
        task?.receive { [weak self] result in
            Task { @MainActor [weak self] in
                guard let self, self.isActive else { return }
                switch result {
                case .success(let message):
                    self.handle(message: message)
                    // 继续接收下一帧
                    if self.isActive { self.receiveLoop() }
                case .failure:
                    // 连接断开 → 退避重连
                    self.scheduleReconnect()
                }
            }
        }
    }

    private func handle(message: URLSessionWebSocketTask.Message) {
        let text: String?
        switch message {
        case .string(let s): text = s
        case .data(let d): text = String(data: d, encoding: .utf8)
        @unknown default: text = nil
        }
        guard let text, let data = text.data(using: .utf8) else { return }
        guard let dict = try? JSONDecoder().decode([String: JSONValue].self, from: data) else { return }
        let event = Self.makeEvent(from: dict)
        onEvent?(event)
    }

    private func startPing() {
        pingTask?.cancel()
        pingTask = Task { [weak self] in
            // 每 ~25s 发一次 ping 维持 NAT/隧道，断开则触发 receiveLoop 的失败分支重连。
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: 25_000_000_000)
                guard let self, self.isActive else { return }
                self.task?.sendPing { _ in }
            }
        }
    }

    private func scheduleReconnect() {
        guard isActive else { return }
        pingTask?.cancel(); pingTask = nil
        task = nil
        reconnectAttempt += 1
        state = .retrying(attempt: reconnectAttempt)
        // 退避 1→2→4…≤30s + 抖动，避免重连风暴。
        let base = min(maxBackoff, pow(2.0, Double(min(reconnectAttempt, 5))))
        let jitter = base * 0.2 * Double(reconnectAttempt % 3) / 2.0
        let delay = base + jitter
        reconnectWorkItem?.cancel()
        reconnectWorkItem = Task { [weak self] in
            try? await Task.sleep(nanoseconds: UInt64(delay * 1_000_000_000))
            guard let self, self.isActive, !Task.isCancelled else { return }
            guard let wsURL = Self.makeWebSocketURL(httpRoot: JarvisAPIClient(baseURL: self.endpoint, token: self.token).normalizedBaseURL, token: self.token) else { return }
            self.openSocket(url: wsURL)
        }
    }

    // MARK: - 纯函数（可单测）

    /// 由 http(s) root 推导 ws(s):// /ws/notify?token=… 。http→ws, https→wss。
    nonisolated static func makeWebSocketURL(httpRoot: String, token: String) -> URL? {
        guard !httpRoot.isEmpty else { return nil }
        var scheme = "wss"
        var rest = httpRoot
        if let range = httpRoot.range(of: "://") {
            let proto = httpRoot[httpRoot.startIndex..<range.lowerBound].lowercased()
            scheme = (proto == "http") ? "ws" : "wss"
            rest = String(httpRoot[range.upperBound...])
        }
        rest = rest.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        let clean = token.trimmingCharacters(in: .whitespacesAndNewlines)
        let query = clean.isEmpty ? "" : "?token=\(clean.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? clean)"
        return URL(string: "\(scheme)://\(rest)/ws/notify\(query)")
    }

    /// 从原始 JSON 字典归一化为 NotifyEvent。
    nonisolated static func makeEvent(from dict: [String: JSONValue]) -> NotifyEvent {
        func str(_ key: String) -> String? {
            if case .string(let s)? = dict[key] { return s }
            return nil
        }
        var urgent = false
        if case .bool(let b)? = dict["urgent"] { urgent = b }
        return NotifyEvent(
            type: str("type") ?? "notify",
            source: str("source"),
            urgent: urgent,
            delivery: str("delivery"),
            title: str("title"),
            body: str("body") ?? str("message") ?? str("summary"),
            raw: dict
        )
    }
}
