export function readBlobDataUrl(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(blob);
  });
}

export function encodePcm16Wav(samples: Float32Array, sampleRate: number) {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);
  const writeString = (offset: number, value: string) => {
    for (let i = 0; i < value.length; i += 1) view.setUint8(offset + i, value.charCodeAt(i));
  };
  writeString(0, "RIFF");
  view.setUint32(4, 36 + samples.length * 2, true);
  writeString(8, "WAVE");
  writeString(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeString(36, "data");
  view.setUint32(40, samples.length * 2, true);
  let offset = 44;
  for (let i = 0; i < samples.length; i += 1, offset += 2) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return new Blob([view], { type: "audio/wav" });
}

export async function audioBlobToWav(blob: Blob, targetRate = 16000) {
  const AudioContextCtor = window.AudioContext || (window as any).webkitAudioContext;
  const ctx = new AudioContextCtor();
  try {
    const decoded = await ctx.decodeAudioData(await blob.arrayBuffer());
    const ratio = decoded.sampleRate / targetRate;
    const length = Math.max(1, Math.floor(decoded.duration * targetRate));
    const channelCount = Math.max(1, decoded.numberOfChannels);
    const mono = new Float32Array(length);
    for (let i = 0; i < length; i += 1) {
      const sourceIndex = Math.min(decoded.length - 1, Math.floor(i * ratio));
      let sum = 0;
      for (let ch = 0; ch < channelCount; ch += 1) sum += decoded.getChannelData(ch)[sourceIndex] || 0;
      mono[i] = sum / channelCount;
    }
    return encodePcm16Wav(mono, targetRate);
  } finally {
    void ctx.close?.();
  }
}
