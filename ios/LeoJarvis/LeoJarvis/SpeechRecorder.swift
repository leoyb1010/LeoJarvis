import AVFoundation
import Foundation

@MainActor
final class SpeechRecorder: ObservableObject {
    @Published private(set) var isRecording = false
    @Published private(set) var isTranscribing = false

    private var recorder: AVAudioRecorder?
    private var fileURL: URL?

    func toggle(client: JarvisAPIClient, prompt: String = "") async throws -> String {
        if isRecording {
            return try await stopAndTranscribe(client: client, prompt: prompt)
        }
        try await start()
        return ""
    }

    func start() async throws {
        let session = AVAudioSession.sharedInstance()
        let granted = await withCheckedContinuation { continuation in
            AVAudioApplication.requestRecordPermission { allowed in
                continuation.resume(returning: allowed)
            }
        }
        guard granted else { throw SpeechRecorderError.permissionDenied }

        try session.setCategory(.playAndRecord, mode: .spokenAudio, options: [.defaultToSpeaker, .allowBluetoothHFP])
        try session.setActive(true, options: [])
        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent("leojarvis-voice-\(UUID().uuidString)")
            .appendingPathExtension("wav")
        let settings: [String: Any] = [
            AVFormatIDKey: kAudioFormatLinearPCM,
            AVSampleRateKey: 16_000,
            AVNumberOfChannelsKey: 1,
            AVLinearPCMBitDepthKey: 16,
            AVLinearPCMIsFloatKey: false,
            AVLinearPCMIsBigEndianKey: false
        ]
        let recorder = try AVAudioRecorder(url: url, settings: settings)
        recorder.isMeteringEnabled = true
        guard recorder.record() else { throw SpeechRecorderError.startFailed }
        self.recorder = recorder
        self.fileURL = url
        self.isRecording = true
    }

    func stopAndTranscribe(client: JarvisAPIClient, prompt: String = "") async throws -> String {
        guard let recorder, let url = fileURL else { return "" }
        recorder.stop()
        self.recorder = nil
        self.fileURL = nil
        isRecording = false
        isTranscribing = true
        defer {
            isTranscribing = false
            try? FileManager.default.removeItem(at: url)
            try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
        }
        do {
            let localText = try await LocalWhisperTranscriber.shared.transcribe(wavURL: url)
            if !localText.isEmpty {
                return localText
            }
        } catch {
            print("Local Whisper fallback to Mac: \(error.localizedDescription)")
        }

        let data = try Data(contentsOf: url)
        let response: SpeechTranscribeResponse = try await client.post(
            "/speech/transcribe",
            body: SpeechTranscribeRequest(
                data_base64: data.base64EncodedString(),
                mime_type: "audio/wav",
                file_name: "ios-voice.wav",
                model: "base",
                language: "auto",
                prompt: prompt
            )
        )
        return (response.text ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
    }
}

enum SpeechRecorderError: LocalizedError {
    case permissionDenied
    case startFailed

    var errorDescription: String? {
        switch self {
        case .permissionDenied:
            return "没有麦克风权限。"
        case .startFailed:
            return "录音启动失败。"
        }
    }
}
