import SwiftUI
import SwiftData
import UIKit

// ═══════════════════════════════════════════════════════════════════
//  CortexFleetApp.swift  ·  ARC REACTOR HUD 换肤版
//  全局：暗黑配色 + 青色 tint + 透明深色导航/标签栏 + HUD 背景。
//  业务逻辑保持不变。
// ═══════════════════════════════════════════════════════════════════

@main
struct CortexFleetApp: App {
    @StateObject private var env = AppEnvironment()
    @StateObject private var store = FleetStore()
    @Environment(\.scenePhase) private var scenePhase

    init() {
        HUDAppearance.apply()
    }

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(store)
                .environmentObject(env)
                .environmentObject(env.llmConfig)
                .modelContainer(env.container)
                .tint(Brand.accent)
                .preferredColorScheme(.dark)
                .onOpenURL { url in store.applyBridgeConfigurationURL(url) }
                .task { BackgroundRefresh.shared.register(env: env) }
        }
        .onChange(of: scenePhase) { _, phase in
            if phase == .background { BackgroundRefresh.shared.schedule() }
        }
    }
}

struct RootView: View {
    @EnvironmentObject private var store: FleetStore
    @State private var onboarded = UserDefaults.standard.bool(forKey: "onboarding.done")

    var body: some View {
        ZStack {
            HUDBackground()
            if !onboarded {
                OnboardingView(done: $onboarded)
            } else {
                mainTabs
            }
        }
    }

    private var mainTabs: some View {
        TabView {
            NavigationStack { OverviewView() }
                .tabItem { Label("总览", systemImage: "sparkles") }

            NavigationStack { BriefingView() }
                .tabItem { Label("简报", systemImage: "newspaper") }

            NavigationStack { NotebookView() }
                .tabItem { Label("记事", systemImage: "note.text") }

            NavigationStack { FleetDashboardView() }
                .tabItem { Label("设备", systemImage: "gauge.with.dots.needle.33percent") }

            NavigationStack { SettingsView() }
                .tabItem { Label("设置", systemImage: "gearshape") }
        }
        .jarvisFloatingButton()
        .task { await store.refreshAll() }
    }
}

// MARK: - 全局 UIKit 外观（深色透明 + HUD 字体）

enum HUDAppearance {
    static func apply() {
        let voidColor = UIColor(Brand.void)

        // 导航栏
        let nav = UINavigationBarAppearance()
        nav.configureWithTransparentBackground()
        nav.backgroundColor = voidColor.withAlphaComponent(0.55)
        nav.shadowColor = UIColor(Brand.accent).withAlphaComponent(0.18)
        let white = UIColor.white
        nav.titleTextAttributes = [.foregroundColor: white]
        if let d = UIFont.systemFont(ofSize: 32, weight: .bold).fontDescriptor.withDesign(.rounded) {
            nav.largeTitleTextAttributes = [.foregroundColor: white, .font: UIFont(descriptor: d, size: 32)]
        } else {
            nav.largeTitleTextAttributes = [.foregroundColor: white]
        }
        UINavigationBar.appearance().standardAppearance = nav
        UINavigationBar.appearance().scrollEdgeAppearance = nav
        UINavigationBar.appearance().compactAppearance = nav
        UINavigationBar.appearance().tintColor = UIColor(Brand.accent)

        // 标签栏
        let tab = UITabBarAppearance()
        tab.configureWithTransparentBackground()
        tab.backgroundColor = voidColor.withAlphaComponent(0.7)
        tab.shadowColor = UIColor(Brand.accent).withAlphaComponent(0.18)
        UITabBar.appearance().standardAppearance = tab
        UITabBar.appearance().scrollEdgeAppearance = tab
        UITabBar.appearance().tintColor = UIColor(Brand.accent)
    }
}
