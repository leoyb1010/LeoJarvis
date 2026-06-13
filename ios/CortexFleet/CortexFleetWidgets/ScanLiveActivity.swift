import WidgetKit
import SwiftUI
import ActivityKit

/// Dynamic Island + lock-screen presentation for the intel scan Live Activity.
@available(iOS 16.1, *)
struct ScanLiveActivityWidget: Widget {
    var body: some WidgetConfiguration {
        ActivityConfiguration(for: ScanActivityAttributes.self) { context in
            // Lock screen / banner.
            HStack(spacing: 12) {
                Image(systemName: context.state.done ? "checkmark.circle.fill" : "antenna.radiowaves.left.and.right")
                    .foregroundStyle(context.state.done ? .green : .blue)
                VStack(alignment: .leading) {
                    Text(context.attributes.title).font(.caption.weight(.semibold))
                    Text(context.state.phase).font(.caption2).foregroundStyle(.secondary)
                }
                Spacer()
                if context.state.found > 0 { Text("\(context.state.found) 条").font(.caption.weight(.bold)) }
            }
            .padding()
            .activityBackgroundTint(Color.black.opacity(0.2))
        } dynamicIsland: { context in
            DynamicIsland {
                DynamicIslandExpandedRegion(.leading) {
                    Image(systemName: "sparkles").foregroundStyle(.tint)
                }
                DynamicIslandExpandedRegion(.center) {
                    Text(context.state.phase).font(.caption)
                }
                DynamicIslandExpandedRegion(.trailing) {
                    if context.state.found > 0 { Text("\(context.state.found)").font(.caption.weight(.bold)) }
                }
            } compactLeading: {
                Image(systemName: context.state.done ? "checkmark" : "antenna.radiowaves.left.and.right")
            } compactTrailing: {
                if context.state.found > 0 { Text("\(context.state.found)") }
            } minimal: {
                Image(systemName: "sparkles")
            }
        }
    }
}
