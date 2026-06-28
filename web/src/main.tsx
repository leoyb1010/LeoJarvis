import React from "react";
import ReactDOM from "react-dom/client";
// 字体自托管(@fontsource):构建期打进 bundle,零外部请求 —— 本地助理离线/隐私优先,
// 不再依赖 Google Fonts CDN。字重对齐代码里实际用到的 400/500/600/700。
import "@fontsource/space-grotesk/400.css";
import "@fontsource/space-grotesk/500.css";
import "@fontsource/space-grotesk/600.css";
import "@fontsource/space-grotesk/700.css";
import "@fontsource/ibm-plex-mono/400.css";
import "@fontsource/ibm-plex-mono/500.css";
import "@fontsource/ibm-plex-mono/600.css";
import "@fontsource/ibm-plex-mono/700.css";
import CommandCenter from "./cc/CommandCenter";
import "./cc/theme.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <CommandCenter />
  </React.StrictMode>,
);
