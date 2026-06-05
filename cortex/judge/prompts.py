JUDGE_SYSTEM = """你是 Leo 的私人参谋。你的任务不是复述信息，而是替 Leo 判断。
你了解 Leo 在乎什么（见画像）。对每条信息：
1) 打一个 0~1 的相关性分（与 Leo 的项目/持仓/关注的人事物/偏好有多相关）；
2) 用一句中文说“对 Leo 意味着什么”（机会/风险/纯背景？要不要行动？）；
3) 给出分诊：notify(重要,需实时知道) / digest(进简报即可) / ignore(噪音)。
只输出 JSON：{"score":0.x,"take":"...","triage":"notify|digest|ignore","reasons":["..."]}"""


def build_user_prompt(profile_text: str, recalled: str, item) -> str:
    return f"""## Leo 的画像
{profile_text}

## 相关历史记忆
{recalled or '（无）'}

## 待判断信息
来源: {item.source} | 域: {item.domain} | 类型: {item.kind}
标题: {item.title}
内容: {item.content[:1500]}
"""
