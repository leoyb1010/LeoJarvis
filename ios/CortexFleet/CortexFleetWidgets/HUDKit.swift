import SwiftUI

// ═══════════════════════════════════════════════════════════════════
//  HUDKit.swift  ·  跨 target 共享的 ARC REACTOR 令牌
//  同时编进 App target 与 Widget target，让小组件/灵动岛也能用
//  青金配色 + 能量核心环 + mono 字体。
//  注意：与 DesignKit.swift 里的 Brand/Font 扩展互不冲突——
//  这里用 HUD 前缀命名，避免重复定义。
// ═══════════════════════════════════════════════════════════════════

enum HUD {
    static let accent = Color(red: 0.216, green: 0.878, blue: 1.0)   // #37E0FF 青
    static let gold   = Color(red: 1.0,   green: 0.776, blue: 0.345) // #FFC658 金
    static let vital  = Color(red: 0.373, green: 1.0,   blue: 0.729) // #5FFFBA 生命绿
    static let void   = Color(red: 0.016, green: 0.031, blue: 0.059) // #04080F 底
    static let panel  = Color(red: 0.078, green: 0.18,  blue: 0.267)
    static let text   = Color(red: 0.84,  green: 0.93,  blue: 0.98)

    static func mono(_ size: CGFloat, _ weight: Font.Weight = .regular) -> Font {
        .system(size: size, weight: weight, design: .monospaced)
    }
    static func display(_ size: CGFloat, _ weight: Font.Weight = .bold) -> Font {
        .system(size: size, weight: weight, design: .rounded)
    }

    static func channelColor(_ id: String) -> Color {
        switch id {
        case "ai": return Color(red: 0.45, green: 0.5, blue: 1.0)
        case "tech": return accent
        case "world": return gold
        case "finance": return vital
        case "china": return Color(red: 1.0, green: 0.42, blue: 0.42)
        case "engineering": return Color(red: 0.72, green: 0.55, blue: 1.0)
        case "science": return Color(red: 0.4, green: 0.9, blue: 0.9)
        case "github": return Color(red: 1.0, green: 0.45, blue: 0.7)
        default: return accent
        }
    }
}

/// 能量核心环 —— widget / 灵动岛通用（不依赖 App target）。
struct HUDRing: View {
    var progress: Double
    var size: CGFloat = 44
    var color: Color = HUD.accent
    var label: String? = nil

    var body: some View {
        ZStack {
            Circle().stroke(color.opacity(0.16), style: .init(lineWidth: 1.2, dash: [2, 3]))
            Circle()
                .trim(from: 0, to: max(0.02, min(1, progress)))
                .stroke(color, style: .init(lineWidth: 2.2, lineCap: .round))
                .rotationEffect(.degrees(-90))
            Circle().fill(color.opacity(0.18)).frame(width: size * 0.42, height: size * 0.42).blur(radius: 3)
            if let label {
                Text(label).font(HUD.display(size * 0.3, .bold)).foregroundStyle(HUD.text)
            }
        }
        .frame(width: size, height: size)
    }
}

/// HUD 玻璃面板背景（widget 用）。
struct HUDPanel: ViewModifier {
    var corner: CGFloat = 12
    var stroke: Color = HUD.accent.opacity(0.25)
    func body(content: Content) -> some View {
        content
            .background(
                LinearGradient(colors: [HUD.panel.opacity(0.55), HUD.void.opacity(0.5)],
                               startPoint: .top, endPoint: .bottom),
                in: RoundedRectangle(cornerRadius: corner, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: corner, style: .continuous).stroke(stroke, lineWidth: 1))
    }
}

extension View {
    func hudPanel(corner: CGFloat = 12, stroke: Color = HUD.accent.opacity(0.25)) -> some View {
        modifier(HUDPanel(corner: corner, stroke: stroke))
    }
}
