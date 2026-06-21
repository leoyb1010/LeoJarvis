import Foundation
import whisper

enum LocalWhisperError: LocalizedError {
    case modelMissing
    case contextInitFailed
    case invalidWave
    case unsupportedWave
    case transcriptionFailed

    var errorDescription: String? {
        switch self {
        case .modelMissing:
            return "iPhone 本地 Whisper 模型未打包。"
        case .contextInitFailed:
            return "iPhone 本地 Whisper 初始化失败。"
        case .invalidWave:
            return "录音文件不是有效 WAV。"
        case .unsupportedWave:
            return "录音格式不是 16kHz 单声道 16-bit PCM。"
        case .transcriptionFailed:
            return "iPhone 本地 Whisper 转写失败。"
        }
    }
}

actor LocalWhisperTranscriber {
    static let shared = LocalWhisperTranscriber()
    static let bundledModelName = "ggml-base"

    private var context: OpaquePointer?

    deinit {
        if let context {
            whisper_free(context)
        }
    }

    static func bundledModelURL(in bundle: Bundle = .main) -> URL? {
        bundle.url(forResource: bundledModelName, withExtension: "bin", subdirectory: "models")
            ?? bundle.url(forResource: bundledModelName, withExtension: "bin")
    }

    static var isBundledModelAvailable: Bool {
        bundledModelURL() != nil
    }

    static func bundledModelSizeMB(in bundle: Bundle = .main) -> Double? {
        guard let url = bundledModelURL(in: bundle),
              let size = try? FileManager.default.attributesOfItem(atPath: url.path)[.size] as? NSNumber
        else {
            return nil
        }
        return Double(size.int64Value) / 1024 / 1024
    }

    func transcribe(wavURL: URL, language: String = "auto") async throws -> String {
        let started = Date()
        let samples = try Self.decodePCM16Wave(url: wavURL)
        let context = try loadContext()
        let text = try runWhisper(context: context, samples: samples, language: language)
        let elapsedMs = Int(Date().timeIntervalSince(started) * 1000)
        print("LocalWhisperTranscriber: transcribed \(samples.count) samples in \(elapsedMs)ms")
        return text.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private func loadContext() throws -> OpaquePointer {
        if let context {
            return context
        }
        guard let modelURL = Self.bundledModelURL() else {
            throw LocalWhisperError.modelMissing
        }
        var params = whisper_context_default_params()
        #if targetEnvironment(simulator)
        params.use_gpu = false
        #else
        params.flash_attn = true
        #endif
        guard let context = whisper_init_from_file_with_params(modelURL.path, params) else {
            throw LocalWhisperError.contextInitFailed
        }
        self.context = context
        return context
    }

    private func runWhisper(context: OpaquePointer, samples: [Float], language: String) throws -> String {
        let selectedLanguage = language.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? "auto" : language
        return try selectedLanguage.withCString { languagePointer in
            var params = whisper_full_default_params(WHISPER_SAMPLING_GREEDY)
            params.print_realtime = false
            params.print_progress = false
            params.print_timestamps = false
            params.print_special = false
            params.translate = false
            params.language = languagePointer
            params.n_threads = Int32(max(2, min(6, ProcessInfo.processInfo.processorCount - 2)))
            params.offset_ms = 0
            params.no_context = true
            params.single_segment = false

            whisper_reset_timings(context)
            let result = samples.withUnsafeBufferPointer { buffer -> Int32 in
                guard let baseAddress = buffer.baseAddress else { return -1 }
                return whisper_full(context, params, baseAddress, Int32(buffer.count))
            }
            guard result == 0 else {
                throw LocalWhisperError.transcriptionFailed
            }

            var output = ""
            for index in 0..<whisper_full_n_segments(context) {
                if let segment = whisper_full_get_segment_text(context, index) {
                    output += String(cString: segment)
                }
            }
            return output
        }
    }

    private static func decodePCM16Wave(url: URL) throws -> [Float] {
        let data = try Data(contentsOf: url)
        guard data.count > 44 else { throw LocalWhisperError.invalidWave }
        guard ascii(data, 0, 4) == "RIFF", ascii(data, 8, 4) == "WAVE" else {
            throw LocalWhisperError.invalidWave
        }

        var offset = 12
        var audioFormat: UInt16 = 0
        var channelCount: UInt16 = 0
        var sampleRate: UInt32 = 0
        var bitsPerSample: UInt16 = 0
        var pcmDataRange: Range<Int>?

        while offset + 8 <= data.count {
            let chunkID = ascii(data, offset, 4)
            let chunkSize = Int(readUInt32LE(data, offset + 4))
            let chunkStart = offset + 8
            let chunkEnd = min(chunkStart + chunkSize, data.count)
            if chunkID == "fmt ", chunkStart + 16 <= chunkEnd {
                audioFormat = readUInt16LE(data, chunkStart)
                channelCount = readUInt16LE(data, chunkStart + 2)
                sampleRate = readUInt32LE(data, chunkStart + 4)
                bitsPerSample = readUInt16LE(data, chunkStart + 14)
            } else if chunkID == "data" {
                pcmDataRange = chunkStart..<chunkEnd
            }
            offset = chunkEnd + (chunkSize % 2)
        }

        guard audioFormat == 1, channelCount == 1, sampleRate == 16_000, bitsPerSample == 16,
              let range = pcmDataRange
        else {
            throw LocalWhisperError.unsupportedWave
        }

        var samples: [Float] = []
        samples.reserveCapacity(range.count / 2)
        var cursor = range.lowerBound
        while cursor + 1 < range.upperBound {
            let value = Int16(bitPattern: readUInt16LE(data, cursor))
            samples.append(max(-1, min(1, Float(value) / 32768.0)))
            cursor += 2
        }
        return samples
    }

    private static func ascii(_ data: Data, _ offset: Int, _ count: Int) -> String {
        guard offset + count <= data.count else { return "" }
        return String(decoding: data[offset..<(offset + count)], as: UTF8.self)
    }

    private static func readUInt16LE(_ data: Data, _ offset: Int) -> UInt16 {
        guard offset + 2 <= data.count else { return 0 }
        return UInt16(data[offset]) | (UInt16(data[offset + 1]) << 8)
    }

    private static func readUInt32LE(_ data: Data, _ offset: Int) -> UInt32 {
        guard offset + 4 <= data.count else { return 0 }
        return UInt32(data[offset])
            | (UInt32(data[offset + 1]) << 8)
            | (UInt32(data[offset + 2]) << 16)
            | (UInt32(data[offset + 3]) << 24)
    }
}
