import Foundation
import BackgroundTasks
import SwiftData

/// Schedules periodic background intel scans (BGAppRefreshTask) and evaluates
/// high-priority intel + device-risk thresholds to fire local notifications.
/// Best-effort: iOS decides when background tasks actually run.
@MainActor
final class BackgroundRefresh {
    static let shared = BackgroundRefresh()
    static let taskID = "com.leo.cortexfleet.refresh"

    private weak var env: AppEnvironment?

    func register(env: AppEnvironment) {
        self.env = env
        BGTaskScheduler.shared.register(forTaskWithIdentifier: Self.taskID, using: nil) { task in
            guard let task = task as? BGAppRefreshTask else { return }
            Task { @MainActor in await self.handle(task) }
        }
    }

    func schedule() {
        let request = BGAppRefreshTaskRequest(identifier: Self.taskID)
        request.earliestBeginDate = Date(timeIntervalSinceNow: 60 * 60)  // ~hourly
        try? BGTaskScheduler.shared.submit(request)
    }

    private func handle(_ task: BGAppRefreshTask) async {
        schedule()  // chain the next one
        let op = Task { @MainActor in
            guard let env else { return }
            let before = highPriorityCount()
            await env.intel.scan()
            let after = highPriorityCount()
            if after > before {
                await JarvisNotifications.shared.notifyNow(
                    title: "Jarvis 情报",
                    body: "发现 \(after - before) 条新的高优先情报")
            }
        }
        task.expirationHandler = { op.cancel() }
        _ = await op.value
        task.setTaskCompleted(success: true)
    }

    private func highPriorityCount() -> Int {
        guard let env else { return 0 }
        let items = (try? env.container.mainContext.fetch(
            FetchDescriptorFactory.highPriorityToday())) ?? []
        return items.count
    }
}

enum FetchDescriptorFactory {
    static func highPriorityToday() -> FetchDescriptor<IntelItem> {
        var d = FetchDescriptor<IntelItem>(sortBy: [SortDescriptor(\.collectedAt, order: .reverse)])
        let cutoff = Calendar.current.date(byAdding: .day, value: -1, to: Date()) ?? Date.distantPast
        d.predicate = #Predicate { $0.collectedAt >= cutoff && $0.priority == "高优先" }
        return d
    }
}
