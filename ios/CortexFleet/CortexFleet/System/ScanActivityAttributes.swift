import Foundation
import ActivityKit

/// Live Activity attributes for an intel scan in progress. Shared between the
/// app (which starts/updates/ends the activity) and the widget extension (which
/// renders the Dynamic Island / lock-screen presentation).
struct ScanActivityAttributes: ActivityAttributes {
    public struct ContentState: Codable, Hashable {
        var phase: String       // e.g. "扫描 RSS…" / "GitHub 雷达…" / "完成"
        var found: Int
        var done: Bool
    }
    var title: String
}

/// App-side controller to start / update / end the scan Live Activity.
@available(iOS 16.1, *)
@MainActor
final class ScanActivityController {
    static let shared = ScanActivityController()
    private var activity: Activity<ScanActivityAttributes>?

    func start(title: String = "Jarvis 信源扫描") {
        guard ActivityAuthorizationInfo().areActivitiesEnabled, activity == nil else { return }
        let attributes = ScanActivityAttributes(title: title)
        let initial = ScanActivityAttributes.ContentState(phase: "准备扫描…", found: 0, done: false)
        activity = try? Activity.request(
            attributes: attributes,
            content: .init(state: initial, staleDate: nil)
        )
    }

    func update(phase: String, found: Int) async {
        guard let activity else { return }
        await activity.update(.init(state: .init(phase: phase, found: found, done: false), staleDate: nil))
    }

    func finish(found: Int) async {
        guard let activity else { return }
        await activity.end(.init(state: .init(phase: "完成", found: found, done: true), staleDate: nil),
                           dismissalPolicy: .after(Date().addingTimeInterval(4)))
        self.activity = nil
    }
}
