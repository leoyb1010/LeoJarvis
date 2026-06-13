import Foundation

enum LLMError: LocalizedError {
    case notConfigured
    case invalidURL
    case http(Int, String)
    case emptyResponse
    case transport(String)

    var errorDescription: String? {
        switch self {
        case .notConfigured:
            return "还没配置 AI 录入接口。请在「设置 → AI 录入接口」填入 base_url、模型和 API Key。"
        case .invalidURL:
            return "AI 接口地址无效。"
        case let .http(code, body):
            return "AI 接口返回 HTTP \(code)：\(body.prefix(160))"
        case .emptyResponse:
            return "AI 接口返回了空内容。"
        case let .transport(message):
            return "AI 接口请求失败：\(message)"
        }
    }
}

struct LLMMessage: Codable {
    let role: String   // system | user | assistant
    let content: String
}

/// Minimal OpenAI-compatible chat client. Works against DeepSeek, OpenAI,
/// Moonshot, and any compatible `/chat/completions` endpoint. No SDK needed.
struct LLMClient {
    let baseURL: String
    let apiKey: String
    let model: String

    func chat(
        _ messages: [LLMMessage],
        temperature: Double = 0.3,
        maxTokens: Int? = nil,
        timeout: TimeInterval = 30
    ) async throws -> String {
        guard !apiKey.isEmpty else { throw LLMError.notConfigured }
        guard let url = URL(string: baseURL + "/chat/completions") else { throw LLMError.invalidURL }

        var body: [String: Any] = [
            "model": model,
            "messages": messages.map { ["role": $0.role, "content": $0.content] },
            "temperature": temperature,
            "stream": false,
        ]
        if let maxTokens { body["max_tokens"] = maxTokens }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.timeoutInterval = timeout
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("Bearer \(apiKey)", forHTTPHeaderField: "Authorization")
        request.httpBody = try JSONSerialization.data(withJSONObject: body)

        do {
            let (data, response) = try await URLSession.shared.data(for: request)
            guard let http = response as? HTTPURLResponse else {
                throw LLMError.transport("没有收到 HTTP 响应")
            }
            guard (200..<300).contains(http.statusCode) else {
                throw LLMError.http(http.statusCode, String(data: data, encoding: .utf8) ?? "")
            }
            let decoded = try JSONDecoder().decode(ChatResponse.self, from: data)
            let text = decoded.choices.first?.message.content?
                .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            guard !text.isEmpty else { throw LLMError.emptyResponse }
            return text
        } catch let error as LLMError {
            throw error
        } catch {
            throw LLMError.transport(error.localizedDescription)
        }
    }

    /// Convenience: single-turn prompt with an optional system instruction.
    func complete(system: String? = nil, user: String, temperature: Double = 0.3) async throws -> String {
        var messages: [LLMMessage] = []
        if let system, !system.isEmpty { messages.append(.init(role: "system", content: system)) }
        messages.append(.init(role: "user", content: user))
        return try await chat(messages, temperature: temperature)
    }

    private struct ChatResponse: Decodable {
        struct Choice: Decodable {
            struct Message: Decodable { let content: String? }
            let message: Message
        }
        let choices: [Choice]
    }
}
