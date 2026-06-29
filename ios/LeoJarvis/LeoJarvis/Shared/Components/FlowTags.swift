import SwiftUI

// 流式标签网格（自适应列），最多展示 8 个。Notes/Intel 共用，从 Views.swift 拆出。
struct FlowTags: View {
    let tags: [String]
    let tint: Color

    var body: some View {
        if !tags.isEmpty {
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 78), spacing: 6)], alignment: .leading, spacing: 6) {
                ForEach(tags.prefix(8), id: \.self) { tag in
                    Text(tag)
                        .font(.system(size: 10, weight: .heavy))
                        .foregroundStyle(tint)
                        .lineLimit(1)
                        .minimumScaleFactor(0.72)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 5)
                        .frame(maxWidth: .infinity)
                        .background(tint.opacity(0.11), in: Capsule())
                }
            }
        }
    }
}
