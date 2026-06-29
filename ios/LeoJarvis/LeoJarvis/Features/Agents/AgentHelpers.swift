import Foundation

func agentHasAuth(_ agent: CLIAgent) -> Bool {
    guard let auth = nonEmpty(agent.auth)?.lowercased() else { return false }
    return auth.contains("present") || auth.contains("ok") || auth.contains("ready")
}

func agentCanRun(_ agent: CLIAgent) -> Bool {
    guard agent.installed, let run = nonEmpty(agent.run_supported)?.lowercased() else { return false }
    return !run.contains("false") && !run.contains("unsupported") && !run.contains("no")
}
