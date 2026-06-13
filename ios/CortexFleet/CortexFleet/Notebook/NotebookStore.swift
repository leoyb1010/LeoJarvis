import Foundation
import SwiftData
import NaturalLanguage

/// Notebook engine: CRUD, multi-source ingestion (URL via Jina, RSS item, pasted
/// text, voice transcript), batch AI transforms into Notes, and "chat with your
/// sources" RAG using NaturalLanguage for lightweight on-device retrieval.
@MainActor
final class NotebookStore: ObservableObject {
    private let context: ModelContext
    private let llmConfig: LLMConfigStore

    init(context: ModelContext, llmConfig: LLMConfigStore) {
        self.context = context
        self.llmConfig = llmConfig
    }

    // MARK: - Notebook CRUD

    @discardableResult
    func createNotebook(name: String, emoji: String = "📓") -> Notebook {
        let nb = Notebook(name: name, emoji: emoji)
        context.insert(nb)
        try? context.save()
        return nb
    }

    func delete(_ notebook: Notebook) { context.delete(notebook); try? context.save() }

    func notes(in notebook: Notebook) -> [Note] {
        let id = notebook.id
        let all = (try? context.fetch(FetchDescriptor<Note>())) ?? []
        return all.filter { $0.notebookID == id }.sorted { $0.updatedAt > $1.updatedAt }
    }

    // MARK: - Source ingestion

    @discardableResult
    func addTextSource(_ notebook: Notebook, title: String, text: String, kind: String = "text") -> NotebookSource {
        let src = NotebookSource(title: title.isEmpty ? String(text.prefix(24)) : title,
                                 kind: kind, content: text, excerpt: String(text.prefix(160)))
        src.notebook = notebook
        context.insert(src)
        notebook.updatedAt = Date()
        try? context.save()
        return src
    }

    /// Ingest a web page as a Source (Jina Reader full-text).
    @discardableResult
    func addURLSource(_ notebook: Notebook, url: String) async -> NotebookSource? {
        guard let article = await JinaReader.read(url) else { return nil }
        let src = NotebookSource(title: article.title, kind: "url", url: url,
                                 content: article.text, excerpt: String(article.text.prefix(160)))
        src.notebook = notebook
        context.insert(src)
        notebook.updatedAt = Date()
        try? context.save()
        return src
    }

    /// Add an intel/RSS item as a Source.
    @discardableResult
    func addIntelSource(_ notebook: Notebook, item: IntelItem) -> NotebookSource {
        let body = [item.displaySummary, item.summary, item.url].compactMap { $0 }.joined(separator: "\n")
        let src = NotebookSource(title: item.displayTitle, kind: "rss", url: item.url,
                                 content: body, excerpt: String(body.prefix(160)))
        src.notebook = notebook
        context.insert(src)
        notebook.updatedAt = Date()
        try? context.save()
        return src
    }

    func delete(source: NotebookSource) { context.delete(source); try? context.save() }

    // MARK: - Transform → Note

    /// Apply a transform template to selected sources, producing a new Note in
    /// the notebook.
    @discardableResult
    func transform(_ notebook: Notebook, sources: [NotebookSource], template: TransformTemplate) async throws -> Note {
        guard let client = llmConfig.makeClient() else { throw LLMError.notConfigured }
        let material = sources.map { "【\($0.title)】\n\($0.content.prefix(3000))" }.joined(separator: "\n\n")
        let result = try await client.complete(
            system: "你是中文研究助理。只输出整理结果，不要寒暄。",
            user: "\(template.instruction)\n\n资料：\n\(material.prefix(9000))",
            temperature: 0.2)
        let store = NoteStore(context: context, llmConfig: llmConfig)
        let note = store.create(title: "\(template.name)：\(notebook.name)", content: result,
                                tags: [template.name], projectName: notebook.name, source: "notebook-transform")
        note.notebookID = notebook.id
        try? context.save()
        return note
    }

    // MARK: - Chat with sources (RAG)

    /// Answer a question grounded in the notebook's sources. Uses NLEmbedding (or
    /// keyword fallback) to pick the most relevant source chunks, then the LLM.
    func chat(_ notebook: Notebook, question: String) async throws -> String {
        guard let client = llmConfig.makeClient() else { throw LLMError.notConfigured }
        let chunks = retrieve(question: question, from: notebook.sources, topK: 5)
        let contextText = chunks.isEmpty
            ? notebook.sources.prefix(3).map { $0.content.prefix(1500) }.joined(separator: "\n\n")
            : chunks.joined(separator: "\n\n")
        return try await client.complete(
            system: "你是中文研究助理。只依据提供的资料回答；资料不足就说明，不要编造。",
            user: "资料：\n\(contextText.prefix(8000))\n\n问题：\(question)")
    }

    /// Lightweight semantic retrieval: rank source paragraphs by NLEmbedding
    /// distance to the query, fall back to keyword overlap if embeddings absent.
    private func retrieve(question: String, from sources: [NotebookSource], topK: Int) -> [String] {
        var paragraphs: [(text: String, sourceTitle: String)] = []
        for s in sources {
            for para in s.content.components(separatedBy: "\n").filter({ $0.count > 40 }) {
                paragraphs.append((para, s.title))
            }
        }
        guard !paragraphs.isEmpty else { return [] }

        if let embedding = NLEmbedding.sentenceEmbedding(for: .simplifiedChinese)
            ?? NLEmbedding.sentenceEmbedding(for: .english),
           let qVec = embedding.vector(for: question) {
            let scored = paragraphs.compactMap { para -> (Double, String)? in
                guard let v = embedding.vector(for: String(para.text.prefix(200))) else { return nil }
                return (cosine(qVec, v), "【\(para.sourceTitle)】\(para.text)")
            }.sorted { $0.0 > $1.0 }
            if !scored.isEmpty { return scored.prefix(topK).map { $0.1 } }
        }
        // Keyword fallback.
        let qWords = Set(question.lowercased().split(whereSeparator: { !$0.isLetter && !$0.isNumber }).map(String.init))
        let scored = paragraphs.map { para -> (Int, String) in
            let pw = Set(para.text.lowercased().split(whereSeparator: { !$0.isLetter && !$0.isNumber }).map(String.init))
            return (qWords.intersection(pw).count, "【\(para.sourceTitle)】\(para.text)")
        }.sorted { $0.0 > $1.0 }
        return scored.prefix(topK).filter { $0.0 > 0 }.map { $0.1 }
    }

    private func cosine(_ a: [Double], _ b: [Double]) -> Double {
        guard a.count == b.count else { return 0 }
        var dot = 0.0, na = 0.0, nb = 0.0
        for i in 0..<a.count { dot += a[i]*b[i]; na += a[i]*a[i]; nb += b[i]*b[i] }
        return (na == 0 || nb == 0) ? 0 : dot / (na.squareRoot() * nb.squareRoot())
    }
}
