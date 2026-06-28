// 浏览器感知采集器（WorkDock 合并 M1）。
// 移植自 WorkDock src/lib/sensing/adapters.ts 的「真实 Web API」逻辑：
// File System Access 选文件夹读清单 / 屏幕单帧 / 剪贴板 / 地理位置 / 设备环境 / 通知。
// 全部 feature-detect + try/catch，不支持或被拒绝时优雅降级，绝不崩溃。
// 所有读取均由用户手势触发（面板里的按钮），并经系统权限弹窗。
// 与 WorkDock 的区别：去掉 lucide/Next/IndexedDB 依赖；connect 成功后把感知到的
// 文本摘要投喂到 LeoJarvis 已有的 /personal-data/ingest（过隐私闸门），而非本地 mock。

const BASE = (() => {
  if (typeof window === "undefined") return "/api";
  return window.location.port === "5173" ? "http://127.0.0.1:8787/api" : "/api";
})();

export type SenseStatus = "connected" | "available" | "unsupported" | "denied";

export interface SenseResult {
  status: SenseStatus;
  summary?: string;
  details?: string[];
  thumb?: string; // 屏幕感知缩略图 dataURL
  reason?: string;
}

export interface SenseChannel {
  id: string;
  name: string;
  desc: string;
  icon: string; // 在 CommandCenter 里映射成 inline SVG（不引入图标库）
  reads: string; // 透明告知会读取什么
  domain: "local" | "personal";
  isSupported: () => boolean;
  connect: () => Promise<SenseResult>;
}

// --- 非标准 API 的最小类型 ---
interface DirEntryHandle {
  kind: "file" | "directory";
  getFile?: () => Promise<File>;
}
interface DirHandle {
  name: string;
  entries: () => AsyncIterableIterator<[string, DirEntryHandle]>;
}
type WindowFS = Window & { showDirectoryPicker?: (opts?: unknown) => Promise<DirHandle> };
type BatteryNav = Navigator & {
  getBattery?: () => Promise<{ level: number; charging: boolean }>;
  deviceMemory?: number;
};
type ConnNav = Navigator & {
  connection?: { effectiveType?: string; downlink?: number; rtt?: number; saveData?: boolean; type?: string };
};

// --- 本地文件夹（File System Access API）---
const fileSystem: SenseChannel = {
  id: "fs-folder",
  name: "本地文件夹",
  desc: "选一个文件夹，读取其中的文件清单（名称/大小/类型）",
  icon: "folder",
  reads: "你选定文件夹内的文件名、大小、类型（不读文件内容）",
  domain: "local",
  isSupported: () => typeof window !== "undefined" && "showDirectoryPicker" in window,
  connect: async (): Promise<SenseResult> => {
    try {
      const picker = (window as WindowFS).showDirectoryPicker;
      if (!picker) return { status: "unsupported", reason: "此浏览器不支持，建议改用桌面代理" };
      const dir = await picker();
      const details: string[] = [];
      let count = 0;
      for await (const [name, handle] of dir.entries()) {
        count++;
        if (details.length < 14) {
          if (handle.kind === "file" && handle.getFile) {
            try {
              const f = await handle.getFile();
              details.push(`${name} · ${(f.size / 1024).toFixed(1)} KB`);
            } catch {
              details.push(name);
            }
          } else {
            details.push(`${name}/`);
          }
        }
      }
      return { status: "connected", summary: `读取了「${dir.name}」文件夹，共 ${count} 个条目`, details };
    } catch (e) {
      const err = e as DOMException;
      if (err?.name === "AbortError") return { status: "available", reason: "你取消了选择" };
      return { status: "denied", reason: "无法访问该文件夹（权限被拒绝）" };
    }
  },
};

// --- 屏幕感知（getDisplayMedia，只截一帧）---
const screen: SenseChannel = {
  id: "screen",
  name: "屏幕感知",
  desc: "经你确认，截取当前屏幕一帧用于上下文感知（不持续录屏）",
  icon: "monitor",
  reads: "你选定的屏幕/窗口单帧画面，截取后立即停止，不持续录制",
  domain: "personal",
  isSupported: () =>
    typeof navigator !== "undefined" &&
    !!navigator.mediaDevices &&
    typeof navigator.mediaDevices.getDisplayMedia === "function",
  connect: async (): Promise<SenseResult> => {
    let stream: MediaStream | null = null;
    try {
      stream = await navigator.mediaDevices.getDisplayMedia({ video: true });
      const video = document.createElement("video");
      video.srcObject = stream;
      await video.play();
      await new Promise((r) => setTimeout(r, 220));
      const w = 320;
      const h = Math.round((w * (video.videoHeight || 9)) / (video.videoWidth || 16));
      const canvas = document.createElement("canvas");
      canvas.width = w;
      canvas.height = h;
      canvas.getContext("2d")?.drawImage(video, 0, 0, w, h);
      const thumb = canvas.toDataURL("image/jpeg", 0.55);
      return { status: "connected", summary: "感知到当前屏幕（已截一帧，未持续录屏）", thumb };
    } catch (e) {
      const err = e as DOMException;
      if (err?.name === "NotAllowedError" || err?.name === "AbortError")
        return { status: "available", reason: "你取消了屏幕共享" };
      return { status: "denied", reason: "无法获取屏幕画面" };
    } finally {
      stream?.getTracks().forEach((t) => t.stop());
    }
  },
};

// --- 剪贴板 ---
const clipboard: SenseChannel = {
  id: "clipboard",
  name: "剪贴板",
  desc: "读取当前剪贴板文本，便于把你刚复制的内容转成记忆/任务",
  icon: "clipboard",
  reads: "你点击时剪贴板里的纯文本（一次性，不监听）",
  domain: "personal",
  isSupported: () =>
    typeof navigator !== "undefined" &&
    !!navigator.clipboard &&
    typeof navigator.clipboard.readText === "function",
  connect: async (): Promise<SenseResult> => {
    try {
      const text = await navigator.clipboard.readText();
      if (!text) return { status: "connected", summary: "读取了剪贴板：当前为空" };
      return {
        status: "connected",
        summary: `读取了剪贴板（${text.length} 字）`,
        details: [text.slice(0, 140) + (text.length > 140 ? "…" : "")],
      };
    } catch {
      return { status: "denied", reason: "剪贴板读取被拒绝（需要权限或用户手势）" };
    }
  },
};

// --- 地理位置 ---
const geo: SenseChannel = {
  id: "geo",
  name: "地理位置",
  desc: "经你授权读取当前位置，用于「在公司/在家」等情境感知",
  icon: "pin",
  reads: "你授权时的一次性地理坐标（不持续追踪）",
  domain: "personal",
  isSupported: () => typeof navigator !== "undefined" && "geolocation" in navigator,
  connect: () =>
    new Promise<SenseResult>((resolve) => {
      try {
        navigator.geolocation.getCurrentPosition(
          (pos) =>
            resolve({
              status: "connected",
              summary: "感知到当前位置",
              details: [`纬度 ${pos.coords.latitude.toFixed(3)}，经度 ${pos.coords.longitude.toFixed(3)}`],
            }),
          (err) => resolve({ status: "denied", reason: err.message || "位置权限被拒绝" }),
          { timeout: 8000, maximumAge: 60000 },
        );
      } catch {
        resolve({ status: "denied", reason: "无法读取地理位置" });
      }
    }),
};

// --- 设备环境（真实、免授权）---
const environment: SenseChannel = {
  id: "env",
  name: "设备环境",
  desc: "在线状态、平台、CPU、内存、电量等环境上下文（无需授权）",
  icon: "cpu",
  reads: "浏览器公开的环境信息：在线/平台/语言/CPU 核数/内存/电量",
  domain: "local",
  isSupported: () => typeof navigator !== "undefined",
  connect: async (): Promise<SenseResult> => {
    const nav = navigator as BatteryNav;
    const bits: string[] = [
      `在线：${navigator.onLine ? "是" : "否"}`,
      `平台：${navigator.platform || "未知"}`,
      `语言：${navigator.language}`,
      `CPU 核数：${navigator.hardwareConcurrency ?? "未知"}`,
    ];
    if (nav.deviceMemory) bits.push(`内存：约 ${nav.deviceMemory} GB`);
    try {
      const b = await nav.getBattery?.();
      if (b) bits.push(`电量：${Math.round(b.level * 100)}%${b.charging ? "（充电中）" : ""}`);
    } catch {
      /* battery API optional */
    }
    return { status: "connected", summary: "已感知设备环境", details: bits };
  },
};

// --- 网络信息（Network Information API）---
const network: SenseChannel = {
  id: "network",
  name: "网络状况",
  desc: "当前网络类型、估算带宽与延迟（无需授权）",
  icon: "network",
  reads: "浏览器公开的网络信息：连接类型、下行带宽、RTT、省流模式",
  domain: "local",
  isSupported: () => typeof navigator !== "undefined" && ("connection" in navigator || "onLine" in navigator),
  connect: async (): Promise<SenseResult> => {
    const c = (navigator as ConnNav).connection;
    const bits: string[] = [`在线：${navigator.onLine ? "是" : "否"}`];
    if (c) {
      if (c.effectiveType) bits.push(`网络等级：${c.effectiveType}`);
      if (typeof c.downlink === "number") bits.push(`下行带宽：约 ${c.downlink} Mb/s`);
      if (typeof c.rtt === "number") bits.push(`往返延迟：约 ${c.rtt} ms`);
      if (c.saveData) bits.push("省流模式：开");
    } else {
      bits.push("浏览器未暴露详细网络信息");
    }
    return { status: "connected", summary: "已感知网络状况", details: bits };
  },
};

// --- 媒体设备清单（enumerateDevices，只数数量，不取流）---
const mediaDevices: SenseChannel = {
  id: "media-devices",
  name: "媒体设备",
  desc: "有几个摄像头/麦克风/扬声器（只清点数量，不开启）",
  icon: "devices",
  reads: "媒体输入输出设备的数量与种类（不访问画面或声音）",
  domain: "local",
  isSupported: () => typeof navigator !== "undefined" && !!navigator.mediaDevices?.enumerateDevices,
  connect: async (): Promise<SenseResult> => {
    try {
      const list = await navigator.mediaDevices.enumerateDevices();
      const n = (k: string) => list.filter((d) => d.kind === k).length;
      const bits = [
        `摄像头：${n("videoinput")} 个`,
        `麦克风：${n("audioinput")} 个`,
        `扬声器：${n("audiooutput")} 个`,
      ];
      // 标签是否可读 → 反映是否已授权过媒体权限（不主动请求）。
      const labeled = list.some((d) => d.label);
      bits.push(labeled ? "设备名称：可读（曾授权）" : "设备名称：未授权（仅计数）");
      return { status: "connected", summary: "已清点媒体设备", details: bits };
    } catch (e) {
      return { status: "denied", reason: String(e) };
    }
  },
};

// --- 语言 & 时区（Intl + navigator.languages，无需授权）---
const locale: SenseChannel = {
  id: "locale",
  name: "语言时区",
  desc: "首选语言、时区与本地时间偏好（无需授权）",
  icon: "locale",
  reads: "浏览器语言列表、时区、24/12 小时制等地区设置",
  domain: "local",
  isSupported: () => typeof Intl !== "undefined" && typeof navigator !== "undefined",
  connect: async (): Promise<SenseResult> => {
    const dt = Intl.DateTimeFormat().resolvedOptions();
    const bits = [
      `首选语言：${navigator.language}`,
      `语言列表：${(navigator.languages || [navigator.language]).join(", ")}`,
      `时区：${dt.timeZone || "未知"}`,
      `本地日历：${dt.calendar || "gregory"} · ${dt.numberingSystem || "latn"}`,
    ];
    return { status: "connected", summary: "已感知语言与时区", details: bits };
  },
};

// --- 桌面通知授权（Notification.requestPermission，授权后 Jarvis 能主动提醒）---
const notify: SenseChannel = {
  id: "notify",
  name: "桌面通知",
  desc: "授权后 Jarvis 可在重要事项时弹系统通知",
  icon: "bell",
  reads: "通知权限状态（不读取任何已有通知内容）",
  domain: "local",
  isSupported: () => typeof window !== "undefined" && "Notification" in window,
  connect: async (): Promise<SenseResult> => {
    try {
      const perm = await Notification.requestPermission();
      if (perm === "granted") return { status: "connected", summary: "已开启桌面通知", details: ["权限：已授权", "Jarvis 可在重要事项时主动提醒"] };
      if (perm === "denied") return { status: "denied", reason: "通知权限被拒绝（可在浏览器站点设置里改）" };
      return { status: "available", reason: "尚未授权" };
    } catch (e) {
      return { status: "unsupported", reason: String(e) };
    }
  },
};

export const SENSE_CHANNELS: SenseChannel[] = [fileSystem, screen, clipboard, geo, network, mediaDevices, locale, notify, environment];

// ---- 感知状态持久化(问题9):首页与感知 tab 共享同一份状态,切页不丢授权记录 ----
const _SENSE_KEY = "cx-sense-state";
export type SenseSaved = { status: SenseStatus; fed?: string; summary?: string; details?: string[]; ts: number };

export function loadSenseState(): Record<string, SenseSaved> {
  try { return JSON.parse(localStorage.getItem(_SENSE_KEY) || "{}"); } catch { return {}; }
}
export function saveSenseStatus(id: string, v: SenseSaved): Record<string, SenseSaved> {
  const all = loadSenseState();
  all[id] = v;
  try { localStorage.setItem(_SENSE_KEY, JSON.stringify(all)); } catch { /* ignore */ }
  // 跨组件即时同步(同一标签页内 storage 事件不触发,用自定义事件)。
  try { window.dispatchEvent(new CustomEvent("cx-sense-change", { detail: all })); } catch { /* ignore */ }
  return all;
}

// connect 成功后，把感知到的文本摘要投喂到 LeoJarvis（过隐私闸门）。
// 屏幕缩略图不投喂（留本地）；只投喂结构化文本（清单/环境/坐标/剪贴板）。
export async function ingestSensed(ch: SenseChannel, r: SenseResult): Promise<{ ok: boolean; accepted?: number; reason?: string }> {
  if (r.status !== "connected") return { ok: false, reason: r.reason };
  const lines = [r.summary || "", ...(r.details || [])].filter(Boolean);
  const text = lines.join("\n").slice(0, 4000);
  if (!text.trim()) return { ok: false, reason: "无可投喂内容" };
  try {
    const resp = await fetch(BASE + "/personal-data/ingest/text", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        text,
        kind: "behavior",
        layer: "episode",
        source_ref: `sensing:${ch.id}`,
        subject: ch.name,
      }),
    });
    if (!resp.ok) return { ok: false, reason: `投喂失败 ${resp.status}` };
    const data = await resp.json();
    return { ok: true, accepted: data.accepted };
  } catch (e) {
    return { ok: false, reason: String(e) };
  }
}
