import SwiftUI
import CoreImage.CIFilterBuiltins
import UIKit

/// Generates a QR code image from a string (for the share card's footer link).
enum QRCode {
    static func image(from string: String) -> UIImage? {
        let context = CIContext()
        let filter = CIFilter.qrCodeGenerator()
        filter.message = Data(string.utf8)
        filter.correctionLevel = "M"
        guard let output = filter.outputImage?.transformed(by: CGAffineTransform(scaleX: 6, y: 6)),
              let cg = context.createCGImage(output, from: output.extent) else { return nil }
        return UIImage(cgImage: cg)
    }
}

/// Renders a `ShareCard` SwiftUI view to a UIImage via `ImageRenderer`. Fully
/// on-device; no network. Used by the share sheet's export/share actions.
@MainActor
enum ShareRenderer {
    static func render(_ card: ShareCard, scale: CGFloat = 3) -> UIImage? {
        let renderer = ImageRenderer(content: card)
        renderer.scale = scale
        renderer.isOpaque = true
        return renderer.uiImage
    }
}

/// The share editor: pick template / theme / size, live preview, then export.
struct ShareCardSheet: View {
    let payload: ShareCardPayload
    @Environment(\.dismiss) private var dismiss

    @State private var template: ShareTemplate = .news
    @State private var theme: ShareTheme = .gradient
    @State private var size: ShareSize = .portrait
    @State private var signature = UserDefaults.standard.string(forKey: "share.signature") ?? "LeoJarvis"
    @State private var showQR = true
    @State private var rendered: UIImage?

    private var dateText: String { Date().formatted(.dateTime.year().month().day()) }

    private var card: ShareCard {
        ShareCard(payload: payload, template: template, theme: theme, size: size,
                  signature: signature, showQR: showQR, dateText: dateText)
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 16) {
                    // Live preview, scaled down to fit.
                    card
                        .scaleEffect(previewScale)
                        .frame(width: size.points.width * previewScale, height: size.points.height * previewScale)
                        .clipShape(RoundedRectangle(cornerRadius: 12))
                        .shadow(radius: 8)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 8)

                    picker("模板", ShareTemplate.allCases, $template) { $0.label }
                    picker("主题", ShareTheme.allCases, $theme) { $0.label }
                    picker("尺寸", ShareSize.allCases, $size) { $0.label }

                    Toggle("显示原文二维码", isOn: $showQR).disabled(payload.link == nil)
                    HStack {
                        Text("署名").font(.subheadline)
                        TextField("署名/水印", text: $signature)
                            .textFieldStyle(.roundedBorder)
                            .onChange(of: signature) { _, v in UserDefaults.standard.set(v, forKey: "share.signature") }
                    }
                }
                .padding()
            }
            .navigationTitle("生成分享图").navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("关闭") { dismiss() } }
                ToolbarItem(placement: .primaryAction) {
                    if let img = rendered {
                        ShareLink(item: Image(uiImage: img), preview: SharePreview("Jarvis 分享图", image: Image(uiImage: img))) {
                            Image(systemName: "square.and.arrow.up")
                        }
                    } else {
                        Button { rendered = ShareRenderer.render(card) } label: { Text("生成") }
                    }
                }
            }
            .onChange(of: template) { _, _ in rendered = nil }
            .onChange(of: theme) { _, _ in rendered = nil }
            .onChange(of: size) { _, _ in rendered = nil }
        }
    }

    private var previewScale: CGFloat {
        // Fit the card width into ~300pt preview.
        min(1, 300 / size.points.width)
    }

    private func picker<T: Identifiable & Hashable>(_ title: String, _ all: [T], _ sel: Binding<T>, _ label: @escaping (T) -> String) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title).font(.subheadline.weight(.semibold))
            Picker(title, selection: sel) {
                ForEach(all) { Text(label($0)).tag($0) }
            }.pickerStyle(.segmented)
        }
    }
}
