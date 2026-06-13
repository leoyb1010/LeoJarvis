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
