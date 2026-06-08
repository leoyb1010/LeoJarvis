import SwiftUI

@main
struct CortexFleetApp: App {
    @StateObject private var store = FleetStore()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(store)
        }
    }
}

struct RootView: View {
    var body: some View {
        TabView {
            NavigationStack {
                FleetDashboardView()
            }
            .tabItem {
                Label("状态", systemImage: "gauge.with.dots.needle.33percent")
            }

            NavigationStack {
                SettingsView()
            }
            .tabItem {
                Label("主机", systemImage: "terminal")
            }
        }
    }
}
