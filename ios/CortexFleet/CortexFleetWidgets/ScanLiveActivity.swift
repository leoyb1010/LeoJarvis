import WidgetKit
import SwiftUI
import ActivityKit

/// Dynamic Island + lock-screen presentation for the intel scan Live Activity.
@available(iOS 16.1, *)
struct ScanLiveActivityWidget: Widget {
    var body: some WidgetConfiguration {
        ActivityConfiguration(for: ScanActivityAttributes.self) { context in
            // Lock screen / banner — ARC REACTOR energy core scanning state.
            HStack(spacing: 14) {
                HUDRing(progress: context.state.done ? 1 : 0.35, size: 40,
                        color: context.state.done ? HUD.vital : HUD.accent,
                        label: context.state.done ? "✓" : nil)
                VStack(alignment: .leading, spacing: 2) {
                    Text(context.attributes.title).font(HUD.display(14, .bold)).foregroundStyle(HUD.text)
                    Text(context.state.phase).font(HUD.mono(10)).foregroundStyle(HUD.accent.opacity(0.8))
                }
                Spacer()
                if context.state.found > 0 {
                    Text("\(context.state.found)").font(HUD.display(22, .bold)).foregroundStyle(HUD.gold)
                        + Text(" 条").font(HUD.mono(10)).foregroundStyle(HUD.text.opacity(0.6))
                }
            }
            .padding()
            .activityBackgroundTint(HUD.void.opacity(0.85))
            .activitySystemActionForegroundColor(HUD.accent)
        } dynamicIsland: { context in
            DynamicIsland {
                DynamicIslandExpandedRegion(.leading) {
                    HUDRing(progress: context.state.done ? 1 : 0.35, size: 34,
                            color: context.state.done ? HUD.vital : HUD.accent)
                }
                DynamicIslandExpandedRegion(.center) {
                    VStack(spacing: 2) {
                        Text(context.attributes.title).font(HUD.mono(11, .semibold)).foregroundStyle(HUD.text)
                        Text(context.state.phase).font(HUD.mono(9)).foregroundStyle(HUD.accent.opacity(0.8))
                    }
                }
                DynamicIslandExpandedRegion(.trailing) {
                    if context.state.found > 0 {
                        Text("\(context.state.found)").font(HUD.display(20, .bold)).foregroundStyle(HUD.gold)
                    }
                }
            } compactLeading: {
                HUDRing(progress: context.state.done ? 1 : 0.35, size: 18,
                        color: context.state.done ? HUD.vital : HUD.accent)
            } compactTrailing: {
                if context.state.found > 0 { Text("\(context.state.found)").font(HUD.mono(12, .bold)).foregroundStyle(HUD.gold) }
            } minimal: {
                HUDRing(progress: 0.6, size: 18, color: HUD.accent)
            }
        }
    }
}
