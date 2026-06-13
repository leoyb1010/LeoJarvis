import Foundation

/// AI transformation templates applied to Notebook Sources, à la open-notebook's
/// "transformations". Built-in set covers summary / key points / action items /
/// questions / translation / podcast script; users can add custom ones (stored
/// in UserDefaults).
struct TransformTemplate: Identifiable, Codable, Hashable {
    var id: String
    var name: String
    var instruction: String
    var builtin: Bool

    static let builtins: [TransformTemplate] = [
        .init(id: "summary", name: "摘要", instruction: "用中文把这些资料浓缩成一段 3-5 句的摘要，保留关键事实。", builtin: true),
        .init(id: "keypoints", name: "要点", instruction: "用中文提炼 5-8 条要点，每条一行，用「• 」开头。", builtin: true),
        .init(id: "actions", name: "行动项", instruction: "用中文抽取可执行的行动项，每条用「- [ ] 」开头；无则回答“暂无明确行动项”。", builtin: true),
        .init(id: "questions", name: "问题清单", instruction: "用中文列出 5 个值得深入研究的问题。", builtin: true),
        .init(id: "translate", name: "翻译", instruction: "把这些资料翻译成通顺的中文，保留结构。", builtin: true),
        .init(id: "podcast", name: "播客脚本", instruction: "用中文写一段两人(主持人A/嘉宾B)对话播客脚本，自然口语，覆盖资料要点。", builtin: true),
    ]

    static let customKey = "notebook.customTransforms"

    static func custom() -> [TransformTemplate] {
        guard let data = UserDefaults.standard.data(forKey: customKey),
              let list = try? JSONDecoder().decode([TransformTemplate].self, from: data) else { return [] }
        return list
    }

    static func addCustom(name: String, instruction: String) {
        var list = custom()
        list.append(.init(id: UUID().uuidString, name: name, instruction: instruction, builtin: false))
        if let data = try? JSONEncoder().encode(list) { UserDefaults.standard.set(data, forKey: customKey) }
    }

    static func all() -> [TransformTemplate] { builtins + custom() }
}
