# DeepSeek 接入说明

## 1. 结论：怎么用
**后端编排、单轮调用、不用函数调用。** 后端先跑裁判、算好学情，把结构化结果交给模型，模型只负责“把诊断翻译成提示和对话”。这样每次调用的输入都可以记录、复现，适合做研究。

| 场景 | 模型 | 思考模式 | 输出方式 | 主要参数 |
|---|---|---|---|---|
| 分级提示（学生端，实时） | deepseek-flash | 关闭 | JSON Output | temperature 0.3，max_tokens 800 |
| 助教对话（学生端，实时） | deepseek-flash | 关闭 | 流式文本 | temperature 0.5，max_tokens 600 |
| ICAP 编码、班级周报（教师端，离线） | deepseek-flash | 开启，reasoning_effort="high" | JSON Output | max_tokens 4000，放在闲时段跑 |

理由：
- 判对错由工具负责，模型不需要自己去跑仿真，所以 v1 不用函数调用（Tool Calls）
- 学生端要快，关闭思考模式；离线编码要准，打开思考模式
- 模型名只从环境变量读取（默认 `deepseek-flash`），以后换模型不改代码

## 2. 已核实的 API 要点（2026 年 10–11 月资料，以官方文档为准）
- 接口与 OpenAI 兼容：Python 用 `openai` SDK，`base_url="https://api.deepseek.com"`
- 当前模型名：`deepseek-flash`（DeepSeek-V4.1-Flash）和 `deepseek-v4-pro`。旧名 `deepseek-chat`、`deepseek-reasoner` 已于 2026-07-24 后退役，**不要再用**；`deepseek-v4-pro` 有下线消息，也不要用
- **思考模式默认开启**（默认强度 high）。关闭要显式传 `extra_body={"thinking": {"type": "disabled"}}`；强度用 `reasoning_effort`，可选 low / high / max
- 思考模式下 temperature、presence_penalty、frequency_penalty 不生效（不报错）
- JSON Output：设 `response_format={"type": "json_object"}`；提示词里必须出现“json”字样并给出输出样例；max_tokens 要留够，防止 JSON 被截断；官方说明偶尔会返回空 content，要有重试
- 不带 tools 的多轮对话，不需要把 reasoning_content 传回；**如果以后用了 tools，所有轮次的 reasoning_content 都必须传回，否则返回 400**
- 有上下文缓存：重复的前缀按缓存命中计费，便宜很多，所以提示词要把固定部分放在最前面（见第 4 节）
- 计价分高峰和闲时，闲时约为高峰的一半；批处理任务放到官方价格页标注的闲时段

## 3. 客户端封装（`backend/app/services/llm.py`）
环境变量（写进 `.env.example`，只写变量名和默认值）：
```text
DEEPSEEK_API_KEY=
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-flash
LLM_TIMEOUT_SECONDS=30
LLM_MAX_RETRIES=2
LLM_DAILY_BUDGET_CNY=20
```

三种调用方式：
```python
import os
from openai import OpenAI

client = OpenAI(
    api_key=os.environ["DEEPSEEK_API_KEY"],
    base_url=os.getenv("LLM_BASE_URL", "https://api.deepseek.com"),
    timeout=float(os.getenv("LLM_TIMEOUT_SECONDS", "30")),
    max_retries=0,  # 重试由我们自己控制，见第 7 节
)
MODEL = os.getenv("LLM_MODEL", "deepseek-flash")

# 1) 分级提示：关闭思考 + JSON Output
def call_hint(messages):
    return client.chat.completions.create(
        model=MODEL,
        messages=messages,
        response_format={"type": "json_object"},
        temperature=0.3,
        max_tokens=800,
        extra_body={"thinking": {"type": "disabled"}},
    )

# 2) 助教对话：关闭思考 + 流式
def stream_chat(messages):
    stream = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        stream=True,
        temperature=0.5,
        max_tokens=600,
        extra_body={"thinking": {"type": "disabled"}},
    )
    for chunk in stream:
        delta = chunk.choices[0].delta.content if chunk.choices else None
        if delta:
            yield delta

# 3) 离线编码：开启思考 + JSON Output
def call_analysis(messages):
    resp = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        response_format={"type": "json_object"},
        max_tokens=4000,
        reasoning_effort="high",
        extra_body={"thinking": {"type": "enabled"}},
    )
    # 业务结果只取 content；reasoning_content 只存调试日志，不当作结果
    return resp
```
每次调用后从响应读取 `model` 字段和 `usage`，写进 llm_calls 表（第 9 节）。usage 里如有 `prompt_cache_hit_tokens`、`prompt_cache_miss_tokens` 也一并记录。

## 4. 提示词组织（为缓存命中设计）
消息顺序固定为：
1. system：角色与规则（全站相同）
2. user 第一段：本题信息（同一道题的所有学生相同）
3. user 第二段：本次诊断、预测对照、学生状态（每次不同）

前两段构成稳定前缀，能吃到缓存。提示词以文件形式放在 `backend/prompts/`，文件名带版本号（如 `hint_system_v1.md`），每次调用都记录所用版本。改提示词必须新建版本文件，不能覆盖旧文件。

## 5. 分级提示

### 5.1 system（`hint_system_v1.md`）
```text
你是数字电路实验课的 Verilog 助教。你根据仿真工具给出的诊断，帮助学生自己找到问题，而不是替学生改代码。

必须遵守：
1. 只依据提供的诊断 json 判断对错；诊断里没有的结论不要说。
2. 绝不写出正确代码，也不给出可以直接替换的代码行；最多原样引用学生代码中已有的一行，并注明行号。
3. 一次只讲一个点。message 不超过 120 个汉字；question 是一个引导学生自己思考的问句。
4. 按要求的提示等级说话：
   1 级（定位）：只指出该看哪个 STEP、哪个信号、哪几行代码，不讲概念。
   2 级（概念）：点出相关概念（如非阻塞赋值在同一个时钟沿统一更新），用提问把概念和学生的代码联系起来。
   3 级（类比）：给一个与本题不同的小例子或反例帮助理解，不能是本题的答案。
5. 按学生本次所在象限调整策略：
   fragile（会写但没把握）：代码已经对了，不要让学生改代码；追问“为什么这样写是对的”，或让学生预测换一组输入后的波形。
   design_gap（设计偏差）：学生懂语义但设计不对，引导回到题目说明，对照期望波形找差别。
   concept_gap（概念未通）：先用一个最小的例子让学生预测，再回到本题。
   mastered（真掌握）：给一个进阶问题，例如能否少用一个触发器。
6. 用中文，语气平和；说“对不上”“再看看”，不说“错误”“你不会”。

只输出 json，格式如下：
{"level": 1, "focus": {"step": 3, "signal": "out", "lines": [24]}, "message": "……", "question": "……？", "concept_tags": ["sequential"]}
```

### 5.2 user（`hint_user_v1.md`，两段）
```text
【题目】{title}（知识点：{knowledge_points}）
【题目说明】{spec_summary}
```
```text
【学生代码（带行号）】
{code_with_line_numbers}
【诊断】{judge_json_compact}        ← compile、first_mismatch、hardware、tags、drivers，不含完整 trace
【预测对照】{prediction_diff}       ← 每个预测格：signal、step、预测值、实际值、是否一致
【学生状态】象限：{quadrant}；本题已用最高提示等级：{max_level}；最近误区：{recent_tags}
【请求】给出 {level} 级提示
```

### 5.3 输出校验（`backend/app/services/hint_guard.py`，确定性规则）
1. JSON 能解析，字段齐全；level 等于请求的等级
2. message ≤ 200 字符，question 以“？”结尾
3. 出现以下任一情况判为“泄露代码”：含 ``` ；同时含 `module` 和 `endmodule`；有 2 行及以上以 `assign`、`always`、`reg`、`wire`、`if`、`case` 开头或含 `<=` 的代码样式行
4. focus.lines 必须在学生代码的行号范围内，且优先落在 drivers 里
5. 不通过 → 在 user 末尾追加“上次输出违反规则：{原因}，请重新生成”，重试 1 次；仍不通过 → 用规则提示（第 8 节），并记录违规原因
6. content 为空 → 视为失败，按第 7 节重试

## 6. 助教对话
- system（`chat_system_v1.md`）：与 5.1 的第 1、2、6 条相同，另加“回答不超过 150 字；学生直接要答案时，改为给出下一级提示”
- 上下文：system + 本题信息 + 最近一次诊断摘要 + 学生象限 + 最近 8 轮对话
- 前端用 SSE 接收流式输出
- 服务端边收边查：一旦累计文本出现 ``` 或命中 5.3 第 3 条，立即停止转发，补一句“助教不能直接给出代码，换个问法试试看”，并记录违规
- 频率限制：每个学生每小时最多 30 条，超过后提示“先去波形里找找线索吧”

## 7. 容错与降级
- 超时 30 秒；遇到 429、5xx、超时、空 content 时重试，间隔 1 秒、3 秒，最多 2 次
- 熔断：连续 5 次失败后 2 分钟内不再请求，全部改用规则提示，界面显示“当前为简化提示，不影响仿真和判定”
- 预算：当天累计费用超过 `LLM_DAILY_BUDGET_CNY` 时，当天剩余时间只用规则提示，并在教师端顶部提示

## 8. 规则提示（`backend/app/services/fallback_hints.py`）
大模型不可用时使用，也作为对照组的基础反馈。按“标签 × 等级”写模板，变量从诊断里填，示例：
| 标签 | 等级 | 模板 |
|---|---|---|
| sim_mismatch | 1 | 先看第 {step} 步的 {signal}：期望 {expected}，实际 {actual}。这一步之前，{signal} 由第 {lines} 行决定，它们在这个时钟沿做了什么？ |
| latch_inferred | 1 | Yosys 说 {latch_signals} 被综合成了锁存器。在组合 always 块里，有没有哪种情况没给它赋值？ |
| latch_inferred | 2 | 组合逻辑的输出必须在每一种输入下都有确定的值；漏掉的分支会让电路“记住”旧值，这就是锁存器。你的 if 或 case 覆盖了所有情况吗？ |
| blocking_in_seq | 2 | 时序 always 块里用 = 时，后面的语句会马上读到新值；真实的触发器是在同一个时钟沿同时采样的。你觉得这里该用哪种赋值？ |
| race_order_sensitive | 2 | 交换 always 块的先后，结果就变了，而真实电路没有先后。哪两个块在同一个时钟沿读写了同一个信号？ |
其余标签和 3 级模板由你补全，补完给我过目。

## 9. 调用日志（llm_calls 表）
记录：时间、用途（hint / chat / icap / weekly_report）、提示词版本、响应中的 model、请求内容哈希、完整 messages（研究复现用，仅内部可见）、输出、输入与输出 token 数（含缓存命中 / 未命中）、耗时、校验结果、重试次数。API Key 不得出现在任何日志里。

## 10. 离线 ICAP 编码（`icap_system_v1.md` 要点）
- 定义四类并各给 2 个 Verilog 场景的例子：P 被动（只复述、只说“懂了”）、A 主动（复制、标记、按提示改一处）、C 建构（自己解释原因、提出假设，如“因为 out 在时钟沿后才更新，所以晚了一拍”）、I 互动（在 C 的基础上回应助教追问、修正自己的解释）
- 每次输入 20 条，输出 json：`{"items": [{"id": "...", "label": "C", "rationale": "不超过 40 字"}]}`
- 结果写入 analysis_labels 表，标注 model 和提示词版本

## 11. 成本估算
$$C=\frac{T_{\text{hit}}\,p_{\text{hit}}+T_{\text{miss}}\,p_{\text{miss}}+T_{\text{out}}\,p_{\text{out}}}{10^{6}}$$

其中，$C$ 为费用（元）；$T_{\text{hit}}$、$T_{\text{miss}}$ 分别为缓存命中与未命中的输入 token 数，$T_{\text{out}}$ 为输出 token 数；$p_{\text{hit}}$、$p_{\text{miss}}$、$p_{\text{out}}$ 为对应的每百万 token 单价（元）。

按 2026 年 10 月官方价格页 deepseek-flash 的**高峰价**（命中 0.04 元、未命中 2 元、输出 8 元）估算：60 名学生、每人每周 30 次提示或对话、每次输入 2500 token（70% 命中缓存）、输出 250 token，则 $T_{\text{hit}}=3.15\times10^6$，$T_{\text{miss}}=1.35\times10^6$，$T_{\text{out}}=0.45\times10^6$，$C\approx 6.4$ 元 / 周；闲时约减半。价格会变，上线前以官方价格页为准。

## 12. 提示质量评测（阶段 4 验收）
- 脚本：`python -m backend.eval.hints --problems problems/ --prompt hint_v1 --levels 1,2,3`
- 对每道题的每个错误样本，按 1–3 级各生成一条提示，导出 CSV：题目、样本、等级、提示原文、校验结果
- 人工按四项打 1–5 分：准确（与诊断一致）、不泄露答案、引导性、易懂；**不使用大模型给大模型打分**
- 汇总脚本输出各项均分和违规率；要比较的方案（如思考模式开 / 关、提示词 v1 / v2）各跑一遍，用同一套样本
