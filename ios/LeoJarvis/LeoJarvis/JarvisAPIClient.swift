import Foundation

enum APIClientError: LocalizedError {
    case invalidBaseURL
    case invalidResponse
    case http(Int, String)

    var errorDescription: String? {
        switch self {
        case .invalidBaseURL:
            return "Jarvis 地址无效。"
        case .invalidResponse:
            return "Jarvis 没有返回有效 HTTP 响应。"
        case .http(let code, let body):
            return "Jarvis 返回 \(code)：\(body.prefix(180))"
        }
    }
}

/// 网络客户端抽象：只暴露 4 个 HTTP 动词，供 store 注入 mock 做单测（Phase 2/5 可测性前置）。
/// 视图层仍直接用 JarvisAPIClient 具体类型做 URL 推导（normalizedBaseURL/isRemoteHTTPS/absoluteURL），
/// 那部分不走这个协议。默认参数与具体实现保持一致，确保经 `any JarvisAPI` 调用时签名匹配。
protocol JarvisAPI {
    func get<T: Decodable>(_ path: String, timeout: TimeInterval) async throws -> T
    func post<T: Decodable, Body: Encodable>(_ path: String, body: Body, timeout: TimeInterval) async throws -> T
    func patch<T: Decodable, Body: Encodable>(_ path: String, body: Body) async throws -> T
    func delete<T: Decodable>(_ path: String) async throws -> T
}

extension JarvisAPI {
    // 便利重载：补回具体实现里的默认 timeout，让调用方 client.get("/x") 仍可省略 timeout。
    func get<T: Decodable>(_ path: String) async throws -> T {
        try await get(path, timeout: 20)
    }
    func post<T: Decodable, Body: Encodable>(_ path: String, body: Body) async throws -> T {
        try await post(path, body: body, timeout: 60)
    }
}

struct JarvisAPIClient: JarvisAPI {
    let baseURL: String
    let token: String

    var normalizedBaseURL: String {
        var raw = baseURL.trimmingCharacters(in: .whitespacesAndNewlines)
        if raw.isEmpty { return "" }
        if !raw.lowercased().hasPrefix("http://") && !raw.lowercased().hasPrefix("https://") {
            let lower = raw.lowercased()
            let isLocal = lower.hasPrefix("127.") || lower.hasPrefix("localhost") || lower.hasPrefix("[::1]") || lower.hasPrefix("::1")
            raw = (isLocal ? "http://" : "https://") + raw
        }
        return raw.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
    }

    var isPrivateNetworkEndpoint: Bool {
        guard let host = URL(string: normalizedBaseURL)?.host?.lowercased() else { return false }
        if host == "localhost" || host == "::1" || host == "[::1]" || host.hasSuffix(".local") { return true }
        if host.hasPrefix("127.") || host.hasPrefix("10.") || host.hasPrefix("192.168.") { return true }
        let parts = host.split(separator: ".").compactMap { Int($0) }
        if parts.count == 4, parts[0] == 172, (16...31).contains(parts[1]) { return true }
        if parts.count == 4, parts[0] == 100, (64...127).contains(parts[1]) { return true }
        return false
    }

    var isRemoteHTTPS: Bool {
        guard let url = URL(string: normalizedBaseURL) else { return false }
        return url.scheme?.lowercased() == "https" && !isPrivateNetworkEndpoint
    }

    func apiURL(_ path: String) throws -> URL {
        guard !normalizedBaseURL.isEmpty else { throw APIClientError.invalidBaseURL }
        let apiRoot = normalizedBaseURL.hasSuffix("/api") ? normalizedBaseURL : normalizedBaseURL + "/api"
        let cleanPath = path.hasPrefix("/") ? path : "/" + path
        guard let url = URL(string: apiRoot + cleanPath) else { throw APIClientError.invalidBaseURL }
        return url
    }

    func absoluteURL(_ path: String?) -> URL? {
        guard let path, !path.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return nil }
        if let url = URL(string: path), url.scheme != nil {
            return url
        }
        let cleanPath = path.hasPrefix("/") ? path : "/" + path
        let root = normalizedBaseURL
        guard !root.isEmpty else { return nil }
        if cleanPath.hasPrefix("/api/") {
            return URL(string: root + cleanPath)
        }
        return try? apiURL(cleanPath)
    }

    func get<T: Decodable>(_ path: String, timeout: TimeInterval = 20) async throws -> T {
        var request = URLRequest(url: try apiURL(path))
        request.timeoutInterval = timeout
        applyHeaders(&request)
        return try await send(request)
    }

    func post<T: Decodable, Body: Encodable>(_ path: String, body: Body, timeout: TimeInterval = 60) async throws -> T {
        var request = URLRequest(url: try apiURL(path))
        request.httpMethod = "POST"
        request.timeoutInterval = timeout
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        applyHeaders(&request)
        request.httpBody = try JSONEncoder().encode(body)
        return try await send(request)
    }

    func patch<T: Decodable, Body: Encodable>(_ path: String, body: Body) async throws -> T {
        var request = URLRequest(url: try apiURL(path))
        request.httpMethod = "PATCH"
        request.timeoutInterval = 60
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        applyHeaders(&request)
        request.httpBody = try JSONEncoder().encode(body)
        return try await send(request)
    }

    func delete<T: Decodable>(_ path: String) async throws -> T {
        var request = URLRequest(url: try apiURL(path))
        request.httpMethod = "DELETE"
        request.timeoutInterval = 20
        applyHeaders(&request)
        return try await send(request)
    }

    private func applyHeaders(_ request: inout URLRequest) {
        request.setValue("LeoJarvis-iOS/1.0", forHTTPHeaderField: "User-Agent")
        let clean = token.trimmingCharacters(in: .whitespacesAndNewlines)
        if !clean.isEmpty {
            request.setValue("Bearer \(clean)", forHTTPHeaderField: "Authorization")
        }
    }

    private func send<T: Decodable>(_ request: URLRequest) async throws -> T {
        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse else { throw APIClientError.invalidResponse }
        guard (200..<300).contains(http.statusCode) else {
            throw APIClientError.http(http.statusCode, String(data: data, encoding: .utf8) ?? "")
        }
        return try JSONDecoder().decode(T.self, from: data)
    }
}
