import { useEffect, useRef, useState } from "react";
import { transcribeSpeech } from "./cc/live";
import { audioBlobToWav, readBlobDataUrl } from "./audioWav";

type RecorderOptions = {
  prompt: string;
  onText: (text: string) => void;
  onError?: (message: string) => void;
};

export function useWhisperRecorder({ prompt, onText, onError }: RecorderOptions) {
  const [recording, setRecording] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);

  // 卸载时释放麦克风：组件在录音中被卸载（如关闭 Jarvis 对话浮层）时，
  // 若不停止 recorder/stream，系统麦克风指示灯会一直亮、音频流泄漏。
  useEffect(() => {
    return () => {
      try {
        recorderRef.current?.stop();
      } catch {
        /* ignore */
      }
      streamRef.current?.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
      recorderRef.current = null;
    };
  }, []);

  async function transcribe(blob: Blob) {
    setTranscribing(true);
    try {
      const wav = await audioBlobToWav(blob);
      const data_base64 = await readBlobDataUrl(wav);
      const res = await transcribeSpeech({
        data_base64,
        mime_type: "audio/wav",
        file_name: "jarvis-voice.wav",
        model: "base",
        language: "auto",
        prompt,
      });
      const text = (res.text || "").trim();
      if (!text) throw new Error("没有识别到文字。");
      onText(text);
    } catch (err) {
      onError?.(err instanceof Error ? err.message : String(err));
    } finally {
      setTranscribing(false);
    }
  }

  async function toggle() {
    if (recording && recorderRef.current) {
      recorderRef.current.stop();
      setRecording(false);
      return;
    }
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      onError?.("当前浏览器不支持录音。");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
      });
      streamRef.current = stream;
      const recorder = new MediaRecorder(stream);
      const chunks: BlobPart[] = [];
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunks.push(event.data);
      };
      recorder.onstop = () => {
        streamRef.current?.getTracks().forEach((track) => track.stop());
        streamRef.current = null;
        recorderRef.current = null;
        const sourceBlob = new Blob(chunks, { type: recorder.mimeType || "audio/webm" });
        void transcribe(sourceBlob);
      };
      recorderRef.current = recorder;
      recorder.start();
      setRecording(true);
    } catch (err) {
      setRecording(false);
      onError?.(err instanceof Error ? err.message : String(err));
    }
  }

  return { recording, transcribing, toggle };
}
