import SwiftUI
import PhotosUI
import UIKit

// 感知接入（移动专属重定义）：放弃 iOS 沙盒不可用的文件夹/屏幕感知，改用手机原生强项，
// 经 /personal-data/ingest 与笔记附件投喂给 Jarvis 记忆：
//   · 剪贴板记一笔 —— UIPasteboard 仅用户主动读，一键存为记忆/笔记
//   · 拍照投喂     —— 选/拍图 → 附件导入（后端 OCR 名片/白板 → 进笔记）
//   · Siri 快捷    —— App Intents 暴露短语（在「快捷指令」里编排）
// 顶部显示记忆层条数（Jarvis 记了多少），底部说明被遗忘权在 Mac/Web 端。
struct SenseView: View {
    @EnvironmentObject private var store: JarvisStore
    @State private var clipboardPreview: String = ""
    @State private var photoItem: PhotosPickerItem?
    @State private var busy = false
    @State private var notice: String = ""
    @State private var layers: [String: Int] = [:]

    var body: some View {
        ScreenScaffold(
            title: "感知接入",
            subtitle: reachableSubtitle,
            systemImage: "sparkles.rectangle.stack"
        ) {
            if !notice.isEmpty {
                ErrorBanner(message: notice, tone: .info)
                    .appearLift(delay: 0.02)
            }
            memoryLayersCard.appearLift(delay: 0.04)
            pendingMemoriesCard.appearLift(delay: 0.06)
            clipboardCard.appearLift(delay: 0.08)
            photoCard.appearLift(delay: 0.12)
            siriCard.appearLift(delay: 0.16)
            privacyNote.appearLift(delay: 0.20)
        }
        .task { await loadStatus() }
        .onChange(of: photoItem) { _, item in
            guard let item else { return }
            Task { await ingestPhoto(item) }
        }
    }

    private var reachableSubtitle: String {
        store.isMacReachable ? "把手机处境投喂给 Jarvis" : "Mac 离线 · 投喂需在线"
    }

    // MARK: - 记忆层统计

    private var memoryLayersCard: some View {
        VStack(alignment: .leading, spacing: 10) {
            SectionTitle(title: "Jarvis 已记住", icon: "brain.head.profile")
            if layers.isEmpty {
                Text(store.isMacReachable ? "暂无记忆层数据" : "连接在线 Mac 后查看")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(AppTheme.muted)
            } else {
                HStack(spacing: 8) {
                    ForEach(layerOrder, id: \.self) { key in
                        if let count = layers[key] {
                            MetricTile(
                                title: layerLabel(key),
                                value: "\(count)",
                                subtitle: "条",
                                icon: layerIcon(key),
                                tint: AppTheme.accent
                            )
                        }
                    }
                }
            }
        }
        .panel()
    }

    // MARK: - 待确认记忆

    @ViewBuilder private var pendingMemoriesCard: some View {
        if !store.pendingMemories.isEmpty {
            VStack(alignment: .leading, spacing: 10) {
                HStack {
                    SectionTitle(title: "待确认记忆", icon: "checkmark.bubble")
                    Spacer()
                    StatusPill(title: "\(store.pendingMemories.count)", icon: nil, tint: AppTheme.violet)
                }
                Text("Jarvis 想记住这些，确认后才进入长期记忆。")
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(AppTheme.muted)
                ForEach(Array(store.pendingMemories.prefix(8))) { memory in
                    VStack(alignment: .leading, spacing: 8) {
                        Text(memory.displayText)
                            .font(.system(size: 13, weight: .semibold))
                            .foregroundStyle(AppTheme.ink)
                            .lineLimit(3)
                        HStack(spacing: 8) {
                            memoryButton("记住", icon: "checkmark", tint: AppTheme.success) {
                                Task { await store.decideMemory(memory, decision: "accept") }
                            }
                            memoryButton("以后", icon: "clock", tint: AppTheme.muted) {
                                Task { await store.decideMemory(memory, decision: "later") }
                            }
                            memoryButton("忘掉", icon: "xmark", tint: AppTheme.danger) {
                                Task { await store.decideMemory(memory, decision: "reject") }
                            }
                        }
                    }
                    .padding(.vertical, 4)
                    if memory.id != store.pendingMemories.prefix(8).last?.id { Divider() }
                }
            }
            .panel()
        }
    }

    private func memoryButton(_ title: String, icon: String, tint: Color, action: @escaping () -> Void) -> some View {
        Button {
            Haptics.lightImpact()
            action()
        } label: {
            Label(title, systemImage: icon)
                .font(.system(size: 12, weight: .heavy))
                .foregroundStyle(tint)
                .frame(maxWidth: .infinity)
                .frame(height: 34)
                .background(tint.opacity(0.10), in: Capsule())
        }
        .buttonStyle(PressScaleButtonStyle())
    }

    private let layerOrder = ["fact", "episode", "pattern", "entity"]
    private func layerLabel(_ k: String) -> String {
        ["fact": "事实", "episode": "情景", "pattern": "规律", "entity": "实体"][k] ?? k
    }
    private func layerIcon(_ k: String) -> String {
        ["fact": "checkmark.seal", "episode": "clock", "pattern": "waveform.path.ecg", "entity": "person.2"][k] ?? "circle"
    }

    // MARK: - 剪贴板记一笔

    private var clipboardCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            SectionTitle(title: "剪贴板记一笔", icon: "doc.on.clipboard")
            Text("读取当前剪贴板文本，一键存为 Jarvis 记忆。仅在你点击时读取，不后台偷读。")
                .font(.system(size: 12, weight: .semibold))
                .foregroundStyle(AppTheme.muted)
            if !clipboardPreview.isEmpty {
                Text(clipboardPreview)
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(AppTheme.ink)
                    .lineLimit(4)
                    .padding(12)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(AppTheme.elevated, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
            }
            HStack(spacing: 10) {
                Button {
                    readClipboard()
                } label: {
                    Label("读取剪贴板", systemImage: "arrow.down.doc")
                        .font(.system(size: 14, weight: .heavy))
                        .frame(maxWidth: .infinity)
                        .frame(height: 44)
                        .background(AppTheme.elevated, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                        .foregroundStyle(AppTheme.ink)
                }
                .buttonStyle(PressScaleButtonStyle())

                Button {
                    Task { await ingestClipboard() }
                } label: {
                    Label("投喂", systemImage: "tray.and.arrow.down")
                        .font(.system(size: 14, weight: .heavy))
                        .frame(maxWidth: .infinity)
                        .frame(height: 44)
                        .background(canIngestClipboard ? AppTheme.accent : AppTheme.faint, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                        .foregroundStyle(AppTheme.onAccent)
                }
                .buttonStyle(PressScaleButtonStyle())
                .disabled(!canIngestClipboard || busy)
            }
        }
        .panel()
    }

    private var canIngestClipboard: Bool {
        !clipboardPreview.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && store.isMacReachable
    }

    private func readClipboard() {
        Haptics.lightImpact()
        let text = UIPasteboard.general.string ?? ""
        clipboardPreview = String(text.prefix(2000))
        if clipboardPreview.isEmpty { notice = "剪贴板没有文本。" }
    }

    private func ingestClipboard() async {
        busy = true; defer { busy = false }
        let ok = await store.ingestText(clipboardPreview, kind: "work", layer: "episode", sourceRef: "ios:clipboard")
        if ok {
            notice = "已投喂剪贴板内容到 Jarvis 记忆。"
            clipboardPreview = ""
            await loadStatus()
        }
    }

    // MARK: - 拍照投喂

    private var photoCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            SectionTitle(title: "拍照投喂", icon: "camera.viewfinder")
            Text("选一张照片（名片/白板/海报）→ 上传，Mac 端 OCR 提取文字并进笔记。")
                .font(.system(size: 12, weight: .semibold))
                .foregroundStyle(AppTheme.muted)
            PhotosPicker(selection: $photoItem, matching: .images) {
                Label(busy ? "上传中…" : "选择照片", systemImage: "photo.badge.plus")
                    .font(.system(size: 14, weight: .heavy))
                    .frame(maxWidth: .infinity)
                    .frame(height: 44)
                    .background(store.isMacReachable ? AppTheme.accent : AppTheme.faint, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                    .foregroundStyle(AppTheme.onAccent)
            }
            .disabled(!store.isMacReachable || busy)
        }
        .panel()
    }

    private func ingestPhoto(_ item: PhotosPickerItem) async {
        busy = true; defer { busy = false; photoItem = nil }
        guard let data = try? await item.loadTransferable(type: Data.self) else {
            notice = "读取照片失败。"
            return
        }
        let resp = await store.importAttachment(
            fileName: "sense-\(Int(Date().timeIntervalSince1970)).jpg",
            mimeType: "image/jpeg",
            data: data,
            noteID: nil
        )
        if resp != nil {
            notice = "照片已上传，Mac 端正在 OCR 并存为笔记。"
        }
    }

    // MARK: - Siri / 快捷指令

    private var siriCard: some View {
        VStack(alignment: .leading, spacing: 8) {
            SectionTitle(title: "Siri 快捷", icon: "mic.circle")
            Text("在「快捷指令」App 里可调用：跑早报 / 记一笔 / 问 Jarvis。对 Siri 说出对应短语即可触发。")
                .font(.system(size: 12, weight: .semibold))
                .foregroundStyle(AppTheme.muted)
            FlowTags(tags: ["嘿 Siri 跑早报", "嘿 Siri 记一笔", "嘿 Siri 问 Jarvis"], tint: AppTheme.violet)
        }
        .panel()
    }

    private var privacyNote: some View {
        Text("感知数据只在你主动触发时采集并投喂。被遗忘权（删除某来源的全部记忆）在 Mac/Web 端的隐私设置里操作。")
            .font(.system(size: 11, weight: .semibold))
            .foregroundStyle(AppTheme.faint)
            .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func loadStatus() async {
        if let status = await store.fetchPersonalDataStatus() {
            layers = status.memory_layers ?? [:]
        }
        await store.refreshPendingMemories()
    }
}
