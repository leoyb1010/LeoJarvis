import Foundation

// SSE 流式对话客户端：连 /api/agent/chat/stream，逐行解析 `data: {json}` 事件，
// 把增量 token / 思考 / 工具 / 最终答复 / 错误回调出去，让对话气泡逐字呈现（首字亚秒可见）。
// 后端事件契约（leojarvis/agent/loop.py）：
//   {type:"token", text}        增量答复文本
//   {type:"thought", text}      推理步骤
//   {type:"tool_start", tool, args}
//   {type:"tool_result", tool, status, result}
//   {type:"final", reply, steps} 终态答复
//   {type:"error", message}
// SSE 末帧：`data: [DONE]`。

/// 流式对话过程中回调给上层的语义事件（已从原始 SSE 事件归一）。
enum ChatStreamEvent: Equatable {
    case token(String)          // 追加到当前 assistant 气泡
    case thought(String)        // 轻量状态行（思考）
    case tool(name: String, status: String)  // 工具开始/结果的状态行
    case final(reply: String)   // 终态完整答复（用于校正/兜底）
    case failed(String)         // 错误
}

enum ChatStreamError: LocalizedError {
    case invalidBaseURL
    case http(Int)

    var errorDescription: String? {
        switch self {
        case .invalidBaseURL: return "Jarvis 地址无效。"
        case .http(let code): return "Jarvis 流式对话返回 \(code)。"
        }
    }
}

struct ChatStreamClient {
    let baseURL: String
    let token: String

    /// 发起一次流式对话。逐事件经 `onEvent` 回调；回调被强约束在主线程执行
    /// （`bytes.lines` 迭代在后台 actor，事件投递前显式 hop 到 MainActor，安全更新 @Published）。
    /// 整个流正常结束（收到 [DONE] 或连接自然关闭）后返回；中途抛错代表连接/HTTP 层失败，
    /// 上层应回退到非流式 /agent/chat。
    func stream(messages: [ChatMessage], onEvent: @escaping @MainActor (ChatStreamEvent) -> Void) async throws {
        let api = JarvisAPIClient(baseURL: baseURL, token: token)
        let root = api.normalizedBaseURL
        guard !root.isEmpty else { throw ChatStreamError.invalidBaseURL }
        let apiRoot = root.hasSuffix("/api") ? root : root + "/api"
        guard let url = URL(string: apiRoot + "/agent/chat/stream") else { throw ChatStreamError.invalidBaseURL }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.timeoutInterval = 120
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("text/event-stream", forHTTPHeaderField: "Accept")
        request.setValue("LeoJarvis-iOS/1.0", forHTTPHeaderField: "User-Agent")
        let clean = token.trimmingCharacters(in: .whitespacesAndNewlines)
        if !clean.isEmpty {
            request.setValue("Bearer \(clean)", forHTTPHeaderField: "Authorization")
        }
        request.httpBody = try JSONEncoder().encode(AgentChatRequest(messages: messages))

        let (bytes, response) = try await URLSession.shared.bytes(for: request)
        guard let http = response as? HTTPURLResponse else { throw ChatStreamError.http(-1) }
        guard (200..<300).contains(http.statusCode) else { throw ChatStreamError.http(http.statusCode) }

        for try await line in bytes.lines {
            // SSE：事件行以 "data:" 开头；空行是事件分隔；其余（注释/event:）忽略。
            guard line.hasPrefix("data:") else { continue }
            let payload = line.dropFirst(5).trimmingCharacters(in: .whitespaces)
            if payload.isEmpty { continue }
            if payload == "[DONE]" { break }
            guard let data = payload.data(using: .utf8),
                  let event = try? JSONDecoder().decode(RawStreamEvent.self, from: data) else { continue }
            if let mapped = event.mapped() {
                await MainActor.run { onEvent(mapped) }
            }
        }
    }
}

/// 原始 SSE 事件解码体；字段按需可选（不同 type 带不同字段）。
private struct RawStreamEvent: Decodable {
    let type: String
    let text: String?
    let reply: String?
    let tool: String?
    let status: String?
    let message: String?

    func mapped() -> ChatStreamEvent? {
        switch type {
        case "token":
            guard let text, !text.isEmpty else { return nil }
            return .token(text)
        case "thought":
            guard let text, !text.isEmpty else { return nil }
            return .thought(text)
        case "tool_start":
            return .tool(name: tool ?? "工具", status: "运行中")
        case "tool_result":
            return .tool(name: tool ?? "工具", status: status ?? "完成")
        case "final":
            return .final(reply: reply ?? "")
        case "error":
            return .failed(message ?? "流式对话出错")
        default:
            return nil
        }
    }
}
