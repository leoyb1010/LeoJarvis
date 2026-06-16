import { AgentConsole } from "./Agent";

function greeting(): string {
  const h = new Date().getHours();
  if (h < 6) return "夜深了";
  if (h < 11) return "早上好";
  if (h < 14) return "中午好";
  if (h < 18) return "下午好";
  return "晚上好";
}

// 中枢反转：对话即主页。第一屏只有一句问候 + 一个输入框（命令栏），
// 其余能力都由中枢按需调起，不再是并列的面板导航。
export function Home() {
  return (
    <div className="page home-view">
      <div className="page-head">
        <h1>{greeting()}，我是 Jarvis</h1>
        <p>跟我说一句话——我在这台 Mac 上替你查、替你做。低风险自动完成，高风险动作先停在确认卡片里。</p>
      </div>
      <AgentConsole hideHead />
    </div>
  );
}
