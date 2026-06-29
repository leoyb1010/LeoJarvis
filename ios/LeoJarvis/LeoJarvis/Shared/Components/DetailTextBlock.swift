import SwiftUI

// 带图标的文本块（标题 + 正文），用于详情页的判断链路/要点展示。从 Views.swift 拆出。
struct DetailTextBlock: View {
    let title: String
    let text: String
    let icon: String
    let tint: Color

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: icon)
                .font(.system(size: 14, weight: .heavy))
                .foregroundStyle(tint)
                .frame(width: 28, height: 28)
                .background(tint.opacity(0.13), in: RoundedRectangle(cornerRadius: 8, style: .continuous))
            VStack(alignment: .leading, spacing: 4) {
                Text(title)
                    .font(.system(size: 12, weight: .heavy))
                    .foregroundStyle(AppTheme.ink)
                Text(text)
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundStyle(AppTheme.muted)
                    .lineSpacing(4)
            }
        }
        .padding(12)
        .background(AppTheme.elevated, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
    }
}
