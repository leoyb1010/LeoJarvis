import SwiftUI
import UIKit

enum AppTheme {
    static let backgroundTop = dynamic(light: UIColor(hex: 0xF7FAFC), dark: UIColor(hex: 0x070B12))
    static let backgroundMid = dynamic(light: UIColor(hex: 0xEEF5F7), dark: UIColor(hex: 0x0D1420))
    static let backgroundBottom = dynamic(light: UIColor(hex: 0xE5EEF2), dark: UIColor(hex: 0x121923))
    static let panel = dynamic(light: UIColor(hex: 0xFFFFFF, alpha: 0.98), dark: UIColor(hex: 0x151E29, alpha: 0.98))
    static let panelStrong = dynamic(light: UIColor(hex: 0xFFFFFF), dark: UIColor(hex: 0x182231))
    static let elevated = dynamic(light: UIColor(hex: 0xF8FBFD), dark: UIColor(hex: 0x202A36))
    static let field = dynamic(light: UIColor(hex: 0xF4F8FA), dark: UIColor(hex: 0x111924))
    static let ink = dynamic(light: UIColor(hex: 0x0E1621), dark: UIColor(hex: 0xEEF4F8))
    static let muted = dynamic(light: UIColor(hex: 0x596576), dark: UIColor(hex: 0xA8B4C2))
    static let faint = dynamic(light: UIColor(hex: 0x9AA6B6), dark: UIColor(hex: 0x748294))
    static let line = dynamic(light: UIColor(hex: 0x0B1724, alpha: 0.12), dark: UIColor(hex: 0xFFFFFF, alpha: 0.16))
    static let glassStroke = dynamic(light: UIColor(hex: 0x0B1724, alpha: 0.08), dark: UIColor(hex: 0xFFFFFF, alpha: 0.14))
    static let shadow = dynamic(light: UIColor(hex: 0x07111E, alpha: 0.05), dark: UIColor(hex: 0x000000, alpha: 0.22))

    static let accent = dynamic(light: UIColor(hex: 0x0076B4), dark: UIColor(hex: 0x48B8F4))
    static let accentDeep = dynamic(light: UIColor(hex: 0x003F62), dark: UIColor(hex: 0x0B5A82))
    static let accentSoft = dynamic(light: UIColor(hex: 0xD6F0FA), dark: UIColor(hex: 0x12384D))
    static let success = dynamic(light: UIColor(hex: 0x09905A), dark: UIColor(hex: 0x43D18B))
    static let successSoft = dynamic(light: UIColor(hex: 0xDDF7ED), dark: UIColor(hex: 0x123D2C))
    static let warn = dynamic(light: UIColor(hex: 0xC06B0D), dark: UIColor(hex: 0xF2B454))
    static let warnSoft = dynamic(light: UIColor(hex: 0xFFF0CC), dark: UIColor(hex: 0x432C0E))
    static let danger = dynamic(light: UIColor(hex: 0xBC1D2A), dark: UIColor(hex: 0xFF6874))
    static let dangerSoft = dynamic(light: UIColor(hex: 0xFCE1E5), dark: UIColor(hex: 0x4B141D))
    static let violet = dynamic(light: UIColor(hex: 0x684CB8), dark: UIColor(hex: 0xA893FF))
    static let violetSoft = dynamic(light: UIColor(hex: 0xECE8FA), dark: UIColor(hex: 0x2D2548))
    static let onAccent = dynamic(light: .white, dark: .white)

    static let corner: CGFloat = 14
    static let tightCorner: CGFloat = 10

    private static func dynamic(light: UIColor, dark: UIColor) -> Color {
        Color(UIColor { traits in
            traits.userInterfaceStyle == .dark ? dark : light
        })
    }
}

enum AppMotion {
    static let quick = Animation.snappy(duration: 0.18)
    static let spring = Animation.spring(response: 0.32, dampingFraction: 0.88)
    static let softSpring = Animation.spring(response: 0.38, dampingFraction: 0.90)
}

enum Haptics {
    static func selection() {
        UISelectionFeedbackGenerator().selectionChanged()
    }

    static func success() {
        UINotificationFeedbackGenerator().notificationOccurred(.success)
    }

    static func lightImpact() {
        UIImpactFeedbackGenerator(style: .light).impactOccurred()
    }
}

struct AppBackground: View {
    var body: some View {
        ZStack {
            LinearGradient(
                colors: [
                    AppTheme.backgroundTop,
                    AppTheme.backgroundMid,
                    AppTheme.backgroundBottom
                ],
                startPoint: .top,
                endPoint: .bottom
            )

            LinearGradient(
                colors: [
                    AppTheme.accentSoft.opacity(0.20),
                    Color.clear,
                    AppTheme.violetSoft.opacity(0.12)
                ],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )

            LinearGradient(
                colors: [
                    AppTheme.line.opacity(0.12),
                    Color.clear,
                    AppTheme.line.opacity(0.08)
                ],
                startPoint: .top,
                endPoint: .bottom
            )

            LinearGradient(
                colors: [Color.clear, AppTheme.panel.opacity(0.12)],
                startPoint: .top,
                endPoint: .bottom
            )
        }
        .ignoresSafeArea()
    }
}

struct PanelModifier: ViewModifier {
    var padding: CGFloat = 14
    var radius: CGFloat = AppTheme.corner

    func body(content: Content) -> some View {
        content
            .padding(padding)
            .adaptiveGlass(cornerRadius: radius)
            .overlay(
                RoundedRectangle(cornerRadius: radius, style: .continuous)
                    .stroke(AppTheme.line, lineWidth: 1)
            )
            .shadow(color: AppTheme.shadow, radius: 10, x: 0, y: 5)
    }
}

struct GlassGroup<Content: View>: View {
    let spacing: CGFloat
    @ViewBuilder let content: Content

    init(spacing: CGFloat = 16, @ViewBuilder content: () -> Content) {
        self.spacing = spacing
        self.content = content()
    }

    var body: some View {
        if #available(iOS 26.0, *) {
            GlassEffectContainer(spacing: spacing) {
                content
            }
        } else {
            content
        }
    }
}

struct AppearLiftModifier: ViewModifier {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var appeared = false
    let delay: Double

    func body(content: Content) -> some View {
        content
            .opacity(appeared ? 1 : 0)
            .offset(y: reduceMotion ? 0 : (appeared ? 0 : 12))
            .onAppear {
                guard !appeared else { return }
                if reduceMotion {
                    appeared = true
                } else {
                    withAnimation(AppMotion.softSpring.delay(delay)) {
                        appeared = true
                    }
                }
            }
    }
}

struct ShimmerModifier: ViewModifier {
    func body(content: Content) -> some View {
        content
    }
}

extension View {
    @ViewBuilder
    func adaptiveGlass(cornerRadius: CGFloat = AppTheme.corner, interactive: Bool = false) -> some View {
        self.background(AppTheme.panel, in: RoundedRectangle(cornerRadius: cornerRadius, style: .continuous))
    }

    func panel(padding: CGFloat = 14, radius: CGFloat = AppTheme.corner) -> some View {
        modifier(PanelModifier(padding: padding, radius: radius))
    }

    func compactPanel() -> some View {
        panel(padding: 12, radius: AppTheme.tightCorner)
    }

    func softField() -> some View {
        padding(12)
            .background(AppTheme.field, in: RoundedRectangle(cornerRadius: AppTheme.tightCorner, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: AppTheme.tightCorner, style: .continuous)
                    .stroke(AppTheme.line, lineWidth: 1)
            )
    }

    func appearLift(delay: Double = 0) -> some View {
        modifier(AppearLiftModifier(delay: delay))
    }

    func shimmer() -> some View {
        modifier(ShimmerModifier())
    }
}

private extension UIColor {
    convenience init(hex: UInt32, alpha: CGFloat = 1) {
        self.init(
            red: CGFloat((hex >> 16) & 0xff) / 255,
            green: CGFloat((hex >> 8) & 0xff) / 255,
            blue: CGFloat(hex & 0xff) / 255,
            alpha: alpha
        )
    }
}

struct PressScaleButtonStyle: ButtonStyle {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .scaleEffect(reduceMotion ? 1 : (configuration.isPressed ? 0.96 : 1))
            .opacity(configuration.isPressed ? 0.82 : 1)
            .animation(reduceMotion ? nil : .snappy(duration: 0.18), value: configuration.isPressed)
    }
}
