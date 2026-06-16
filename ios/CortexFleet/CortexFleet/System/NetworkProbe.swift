import Foundation
import Network

/// Lightweight always-on network path observer. Provides a synchronous snapshot
/// of the current connection type for the local device card.
final class NetworkProbe: @unchecked Sendable {
    static let shared = NetworkProbe()

    private let monitor = NWPathMonitor()
    private let queue = DispatchQueue(label: "com.leo.cortexfleet.network")
    private let lock = NSLock()
    private var _type = "未知"
    private var _expensive = false

    private init() {
        monitor.pathUpdateHandler = { [weak self] path in
            guard let self else { return }
            self.lock.lock()
            defer { self.lock.unlock() }
            if path.status != .satisfied {
                self._type = "离线"
            } else if path.usesInterfaceType(.wifi) {
                self._type = "Wi-Fi"
            } else if path.usesInterfaceType(.cellular) {
                self._type = "蜂窝"
            } else if path.usesInterfaceType(.wiredEthernet) {
                self._type = "有线"
            } else {
                self._type = "其他"
            }
            self._expensive = path.isExpensive
        }
        monitor.start(queue: queue)
    }

    var currentType: String {
        lock.lock(); defer { lock.unlock() }
        return _type
    }

    var isExpensive: Bool {
        lock.lock(); defer { lock.unlock() }
        return _expensive
    }
}

struct NetworkLatencySnapshot: Equatable {
    var latencyMs: Int?
    var measuredAt: Date?
    var error: String?

    static let empty = NetworkLatencySnapshot()

    var valueText: String {
        if let latencyMs {
            return "\(latencyMs)ms"
        }
        return "--ms"
    }

    var detailText: String {
        if NetworkProbe.shared.currentType == "离线" {
            return "离线"
        }
        if let measuredAt {
            return RelativeTime.string(measuredAt)
        }
        if let error, !error.isEmpty {
            return "失败"
        }
        return "待探测"
    }
}

enum NetworkLatencyProbe {
    static func measure(timeout: TimeInterval = 5) async -> NetworkLatencySnapshot {
        guard NetworkProbe.shared.currentType != "离线" else {
            return NetworkLatencySnapshot(latencyMs: nil, measuredAt: Date(), error: "offline")
        }
        guard let url = URL(string: "https://captive.apple.com/hotspot-detect.html") else {
            return NetworkLatencySnapshot(latencyMs: nil, measuredAt: Date(), error: "bad-url")
        }
        var request = URLRequest(url: url)
        request.cachePolicy = .reloadIgnoringLocalAndRemoteCacheData
        request.timeoutInterval = timeout
        request.setValue("LeoJarvis-iOS/1.0 (+network-latency)", forHTTPHeaderField: "User-Agent")

        let started = Date()
        do {
            let (_, response) = try await URLSession.shared.data(for: request)
            guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
                return NetworkLatencySnapshot(latencyMs: nil, measuredAt: Date(), error: "http")
            }
            let elapsed = max(Date().timeIntervalSince(started), 0.001)
            return NetworkLatencySnapshot(latencyMs: Int((elapsed * 1000).rounded()), measuredAt: Date(), error: nil)
        } catch {
            return NetworkLatencySnapshot(latencyMs: nil, measuredAt: Date(), error: error.localizedDescription)
        }
    }
}
