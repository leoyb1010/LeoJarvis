import Foundation

/// User-configurable "AI 录入接口" — an OpenAI-compatible endpoint. The key lives
/// in the Keychain; base URL / model / engine label live in UserDefaults so they
/// can be read without unlocking secure storage. Mirrors the backend
/// `config/models.toml` (DeepSeek by default) but fully on-device.
struct LLMSettings: Codable, Equatable {
    var baseURL: String
    var model: String
    var engineLabel: String
    var temperature: Double
    var allowTranslation: Bool
    var allowBriefingLLM: Bool

    static let defaultBaseURL = "https://api.deepseek.com"
    static let defaultModel = "deepseek-chat"

    init(
        baseURL: String = LLMSettings.defaultBaseURL,
        model: String = LLMSettings.defaultModel,
        engineLabel: String = "DeepSeek",
        temperature: Double = 0.3,
        allowTranslation: Bool = true,
        allowBriefingLLM: Bool = true
    ) {
        self.baseURL = baseURL
        self.model = model
        self.engineLabel = engineLabel
        self.temperature = temperature
        self.allowTranslation = allowTranslation
        self.allowBriefingLLM = allowBriefingLLM
    }

    var normalizedBaseURL: String {
        baseURL.trimmingCharacters(in: .whitespacesAndNewlines)
            .trimmingCharacters(in: CharacterSet(charactersIn: "/"))
    }

    /// Common preset engines (all OpenAI-compatible). The user can also type any host.
    static let presets: [LLMSettings] = [
        LLMSettings(baseURL: "https://api.deepseek.com", model: "deepseek-chat", engineLabel: "DeepSeek"),
        LLMSettings(baseURL: "https://api.openai.com/v1", model: "gpt-4o-mini", engineLabel: "OpenAI"),
        LLMSettings(baseURL: "https://api.anthropic.com/v1", model: "claude-3-5-haiku-latest", engineLabel: "Claude"),
        LLMSettings(baseURL: "https://api.moonshot.cn/v1", model: "moonshot-v1-8k", engineLabel: "Moonshot"),
    ]
}

/// Persists `LLMSettings` (UserDefaults) and the API key (Keychain).
@MainActor
final class LLMConfigStore: ObservableObject {
    @Published private(set) var settings: LLMSettings
    @Published private(set) var hasKey: Bool

    private let defaults: UserDefaults
    private let key = "leojarvis.llmSettings.v1"
    private let keychain: KeychainVault

    init(defaults: UserDefaults = .standard, keychain: KeychainVault = KeychainVault()) {
        self.defaults = defaults
        self.keychain = keychain
        if let data = defaults.data(forKey: key),
           let decoded = try? JSONDecoder().decode(LLMSettings.self, from: data) {
            self.settings = decoded
        } else {
            self.settings = LLMSettings()
        }
        self.hasKey = keychain.hasLLMKey()
    }

    func save(_ next: LLMSettings, key apiKey: String?) {
        settings = next
        if let data = try? JSONEncoder().encode(next) {
            defaults.set(data, forKey: self.key)
        }
        if let apiKey, !apiKey.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            try? keychain.saveLLMKey(apiKey.trimmingCharacters(in: .whitespacesAndNewlines))
            hasKey = true
        }
    }

    func currentKey() -> String? {
        try? keychain.llmKey()
    }

    /// Build a client from the current configuration, or nil if unconfigured.
    func makeClient() -> LLMClient? {
        guard hasKey, let apiKey = currentKey(), !apiKey.isEmpty else { return nil }
        return LLMClient(baseURL: settings.normalizedBaseURL, apiKey: apiKey, model: settings.model)
    }
}
