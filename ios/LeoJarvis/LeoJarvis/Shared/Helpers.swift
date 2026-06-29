import Foundation

// 全局通用小工具：去首尾空白后返回非空字符串，否则 nil。
// 原在 Views.swift 内为 file-private，拆分后多个 feature 文件共用，提为 internal。
func nonEmpty(_ value: String?) -> String? {
    guard let clean = value?.trimmingCharacters(in: .whitespacesAndNewlines), !clean.isEmpty else {
        return nil
    }
    return clean
}
