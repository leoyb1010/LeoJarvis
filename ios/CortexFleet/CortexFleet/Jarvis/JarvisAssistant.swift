import Foundation
import SwiftData
#if canImport(UIKit)
import UIKit
#endif

/// A turn in the Jarvis conversation transcript.
struct JarvisTurn: Identifiable {
    enum Kind { case user, assistant, toolResult, pending }
    let id = UUID()
    var kind: Kind
    var text: String
    var pending: PendingAction?
}

/// A high-risk action awaiting user confirmation.
struct PendingAction: Identifiable {
    let id = UUID()
    let tool: String
    let args: [String: Any]
    let reason: String
}

/// The all-capability Jarvis assistant. Natural-language → LLM plans a tool call
/// using a JSON action protocol (ported from `agent/loop.py`), the action gate
/// (`gate.py`) decides auto vs confirm, and `JarvisTools` executes against iOS
/// capabilities (notes, calendar, reminders, alarms, maps, intel RAG).
@MainActor
final class JarvisAssistant: ObservableObject {
    @Published private(set) var turns: [JarvisTurn] = []
    @Published private(set) var busy = false

    private let tools: JarvisTools
    private let llmConfig: LLMConfigStore
    private var history: [LLMMessage] = []

    private let maxSteps = 5

    init(context: ModelContext, llmConfig: LLMConfigStore) {
        self.tools = JarvisTools(context: context, llmConfig: llmConfig)
        self.llmConfig = llmConfig
    }

    static let suggestions = [
        "记一条笔记：…",
        "明天上午9点提醒我交周报",
        "今天有什么重点情报",
        "导航到最近的咖啡店",
        "在日历里加一个下午3点的会议",
    ]

    func reset() { turns = []; history = [] }

    // MARK: - Send

    func send(_ text: String, speakReply: ((String) -> Void)? = nil) async {
        let content = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !content.isEmpty, !busy else { return }
        turns.append(JarvisTurn(kind: .user, text: content))
        history.append(LLMMessage(role: "user", content: content))
        busy = true
        defer { busy = false }

        guard let client = llmConfig.makeClient() else {
            appendAssistant(LLMError.notConfigured.localizedDescription, speak: speakReply)
            return
        }

        var convo: [LLMMessage] = [LLMMessage(role: "system", content: Self.systemPrompt())]
        convo += history

        for _ in 0..<maxSteps {
            let raw: String
            do { raw = try await client.chat(convo, temperature: 0.2) }
            catch { appendAssistant("出错了：\(error.localizedDescription)", speak: speakReply); return }

            let action = Self.parseAction(raw)

            // Final answer.
            if let final = action["final"] as? String, action["action"] == nil {
                appendAssistant(final, speak: speakReply)
                history.append(LLMMessage(role: "assistant", content: final))
                return
            }

            guard let act = action["action"] as? [String: Any],
                  let tool = act["tool"] as? String, !tool.isEmpty else {
                let fallback = (action["final"] as? String) ?? (action["thought"] as? String) ?? raw
                appendAssistant(fallback, speak: speakReply)
                return
            }
            let args = (act["args"] as? [String: Any]) ?? [:]

            // Action gate.
            if JarvisTools.risk(of: tool) == .confirm {
                let thought = (action["thought"] as? String) ?? "我准备执行 \(tool)，这属于需要确认的操作。"
                turns.append(JarvisTurn(kind: .assistant, text: thought))
                turns.append(JarvisTurn(kind: .pending, text: "",
                    pending: PendingAction(tool: tool, args: args, reason: "对外/写系统，按策略需你确认")))
                return
            }

            // Auto: execute immediately, feed observation back to the model.
            let result = await tools.invoke(tool, args: args)
            turns.append(JarvisTurn(kind: .toolResult, text: result.message))
            if let url = result.openURL { await openExternal(url) }
            convo.append(LLMMessage(role: "assistant", content: raw))
            convo.append(LLMMessage(role: "user", content: "[工具 \(tool) 结果]\n\(result.message)"))
            history.append(LLMMessage(role: "assistant", content: "[执行 \(tool)] \(result.message)"))
        }
        appendAssistant("（已到最大步数，先停下。你可以让我继续。）", speak: speakReply)
    }

    /// Execute a confirmed pending action.
    func confirm(_ pending: PendingAction, approve: Bool) async {
        turns.removeAll { $0.kind == .pending && $0.pending?.id == pending.id }
        guard approve else {
            turns.append(JarvisTurn(kind: .toolResult, text: "已取消，未执行。"))
            return
        }
        busy = true
        let result = await tools.invoke(pending.tool, args: pending.args)
        busy = false
        turns.append(JarvisTurn(kind: .toolResult, text: result.message))
        if let url = result.openURL { await openExternal(url) }
        history.append(LLMMessage(role: "assistant", content: "[已确认执行 \(pending.tool)] \(result.message)"))
    }

    // MARK: - Helpers

    private func appendAssistant(_ text: String, speak: ((String) -> Void)?) {
        turns.append(JarvisTurn(kind: .assistant, text: text))
        speak?(text)
    }

    private func openExternal(_ url: URL) async {
        await UIApplicationOpener.open(url)
    }

    static func systemPrompt() -> String {
        """
        你是 Jarvis，运行在用户 iPhone 上的全能个人助理。你可以调用本机工具来真正动手。
        每次只输出一个 JSON 对象，二选一：
        1) 需要动手：{"thought":"简述","action":{"tool":"工具名","args":{...}}}
        2) 直接回答：{"final":"给用户的中文回复"}
        不要输出 JSON 以外的任何文字，不要用代码块包裹。

        可用工具：
        \(JarvisTools.describe())

        规则：
        - 用户要记笔记 → write_note；问情报/资讯 → ask_intel；查笔记 → search_notes。
        - 安排日程 → create_calendar_event；提醒事项 → create_reminder；定时叫我 → create_alarm。
        - 找地点/导航 → open_maps。
        - 时间统一用 ISO8601（如 2026-06-14T09:00:00），按用户本地时区推断具体日期。
        - 工具执行后会把结果回给你，你据此给出简洁的中文 final 回复。
        - 信息不足时先用 final 追问，不要瞎调用工具。
        """
    }

    /// Tolerant JSON extraction from the model output (ported from loop.py `_parse_action`).
    static func parseAction(_ raw: String) -> [String: Any] {
        let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        if let start = trimmed.firstIndex(of: "{"), let end = trimmed.lastIndex(of: "}"), start < end {
            let chunk = String(trimmed[start...end])
            if let data = chunk.data(using: .utf8),
               let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
                return obj
            }
        }
        return ["final": trimmed.isEmpty ? "（我没有产生有效回复）" : trimmed]
    }
}

/// Small main-actor helper to open a URL without importing UIKit everywhere.
enum UIApplicationOpener {
    @MainActor static func open(_ url: URL) async {
        #if canImport(UIKit)
        await UIApplication.shared.open(url)
        #endif
    }
}
