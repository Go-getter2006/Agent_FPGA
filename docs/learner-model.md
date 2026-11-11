# 学情模型与指标

本系统的学情数据与 C 语言系统完全分开，知识点体系也独立。所有指标都由确定性代码根据裁判结果和事件日志计算，**大模型的输出不参与任何指标**（离线 ICAP 编码单独存放，只供研究参考）。

## 1. 学生端与教师端追踪的内容
同一份数据，两端用途不同：学生端回答“我接下来练什么”，教师端回答“全班卡在哪、干预有没有效果”。

| 内容 | 学生端（帮自己学） | 教师端（看全班、做研究） |
|---|---|---|
| 知识点掌握 | 自己的四级掌握图 | 学生 × 知识点热力图，可按分组筛选 |
| 预测能力 | 自己的波形 / 硬件预测准确率趋势 | 全班分布、按题统计 |
| 脆弱知识 | “会写但没把握”清单 + 一键复习 | F 值（个人、知识点、全班）与高 F 预警 |
| 误区 | 最近遇到的误区（通俗说法 + 去练习） | 标签分布、典型代码片段、受影响学生 |
| 调试行为 | 不展示 | 盲改率、查看波形次数、定位第一个不一致格子的成功率 |
| 提示使用 | 自己用过的提示（可回看） | 提示依赖度、各级提示之后的通过率、按提示词版本对比 |
| 并行理解 | 顺序打乱实验徽章 | 全班通过率、仍依赖执行顺序的学生名单 |
| 仿真能力 | testbench 抓 bug 得分 | 全班 testbench 得分分布 |
| 思考投入 | 不展示 | 对话与解释的 ICAP 编码（AI 编码 + 人工抽检） |
| 进度与活跃 | 作业截止、待复习队列 | 完成率、活跃度、7 天未活跃名单 |
| 排名 | **不展示** | 不做排名；个人数据默认匿名显示 |

## 2. 知识点表（初版，存为 `backend/app/data/knowledge_points.yaml`，教师可增改）
| 代码 | 名称 |
|---|---|
| comb_assign | 组合逻辑与 assign |
| comb_always | always 组合块与完整赋值（锁存器） |
| blocking | 阻塞与非阻塞赋值 |
| sequential | 时序逻辑与触发器（时钟沿） |
| reset | 同步 / 异步复位 |
| counter | 计数器与分频 |
| fsm | 有限状态机 |
| width | 位宽、拼接与截断 |
| hierarchy | 模块例化与层次 |
| testbench | testbench 与激励设计 |
| parallel | 并行与竞争 |

## 3. 基本单位与四象限
- **尝试（attempt）**：一次提交仿真。代码是否通过记为 $c\in\{0,1\}$，取裁判的 `sim.ok`
- **预测（prediction）**：尝试之前锁定的预测，包括波形格和硬件问题（每个硬件问题算一格）

预测准确率：

$$A_{\text{pred}}=\frac{N_{\text{hit}}}{N_{\text{pred}}}$$

其中，$N_{\text{pred}}$ 为本次预测的总格数（波形格 + 硬件问题数），$N_{\text{hit}}$ 为与工具结果一致的格数。波形格以裁判 `sim.trace` 为准，硬件问题以 `hardware` 字段为准；“哪些信号成了触发器”这一问要求集合完全一致才算对。

预测达标：$p=1$ 当且仅当 $A_{\text{pred}}\ge\theta$，否则 $p=0$；阈值 $\theta$ 默认 0.8，可配置。

| $c$ | $p$ | 象限代码 | 学生端名称 | 含义 |
|---|---|---|---|---|
| 1 | 1 | mastered | 真掌握 | 写对了，也知道它为什么对 |
| 1 | 0 | fragile | 会写但没把握 | 碰对的，即脆弱知识 |
| 0 | 1 | design_gap | 设计偏差 | 语义懂了，设计思路有问题 |
| 0 | 0 | concept_gap | 概念未通 | 语义没弄懂，先补概念 |

编译失败的尝试不划象限（记为 `none`），也不计入下面的比率指标。

## 4. 指标定义

### 4.1 脆弱率 F
$$F_k=\frac{N_{k}^{\,c=1,\,p=0}}{N_{k}^{\,c=1}}$$

其中，$k$ 为知识点；统计范围是该学生在知识点 $k$ 上最近 $n$ 次带预测的尝试（默认 $n=5$）；$N_{k}^{\,c=1}$ 为其中代码通过的次数，$N_{k}^{\,c=1,\,p=0}$ 为代码通过但预测不达标的次数。分母为 0 时 $F_k$ 记为空，不显示。全班 F 值取所有学生、所有知识点上分子之和除以分母之和。

### 4.2 知识点掌握等级
$$R^{\text{code}}_k=\frac{1}{m}\sum_{i=1}^{m}c_i,\qquad R^{\text{pred}}_k=\frac{1}{m}\sum_{i=1}^{m}p_i$$

其中，$c_i$、$p_i$ 是该学生在知识点 $k$ 上最近 $m$ 次带预测尝试的代码通过与预测达标（0 或 1），$m$ 默认取 3，不足 3 次时取实际次数。

| 等级 | 规则（自上而下，命中即停） |
|---|---|
| 未开始 | 该知识点没有带预测的尝试 |
| 真掌握 | $R^{\text{code}}_k\ge 2/3$，$R^{\text{pred}}_k\ge 2/3$，且最近一次尝试为 mastered |
| 会写但没把握 | $R^{\text{code}}_k\ge 2/3$，但不满足真掌握 |
| 学习中 | 其余情况 |

一道题关联多个知识点时，这次尝试计入每个关联知识点。每次尝试判完后重算相关知识点，并写入 mastery_snapshots 表。

### 4.3 盲改率 B
$$B=\frac{N_{\text{blind}}}{N_{\text{resubmit}}}$$

其中，$N_{\text{resubmit}}$ 为重复提交次数（同一题的第 2 次及以后的提交），$N_{\text{blind}}$ 为其中“与上一次提交之间没有任何 `waveform.view`、`waveform.cell_click` 或 `investigate.*` 事件”的次数。盲改率高，说明学生在不看仿真结果的情况下反复试错，即没有把仿真和代码结合起来。

### 4.4 提示依赖度 H
$$H=\frac{1}{|P|}\sum_{j\in P}h_j$$

其中，$P$ 为该学生已通过的题目集合，$h_j$ 为通过题 $j$ 之前请求过的最高提示等级（0–4，没请求过记 0；4 表示看过参考答案，见 docs/llm-deepseek.md 5.4 节）。

看过某题参考答案之后提交的尝试，不计入任何知识点的掌握等级、F 值和 R 值。

### 4.5 testbench 得分
定义见 docs/judge.md 9.3 节的 $S_{\text{tb}}$，取每道创作题最近一次提交。

### 4.6 预测误区（确定性规则，不用大模型）
| 代码 | 学生端说法 | 判定规则 |
|---|---|---|
| pred_ff_confusion | 分不清哪些信号会变成触发器 | “哪些信号成了触发器”一问答错，或触发器个数预测偏差 ≥ 1 |
| pred_off_by_one_cycle | 输出时序差了一拍 | 某输出信号的预测序列与实际序列整体错开一个 STEP 后完全一致 |
| pred_latch_blind | 没意识到生成了锁存器 | 实际有锁存器，但预测“没有” |
| pred_order_belief | 以为结果取决于代码先后 | 顺序打乱实验前预测“会变”，但实际与顺序无关；或反过来 |

裁判标签（latch_inferred 等）的学生端说法：
| 标签 | 学生端说法 |
|---|---|
| latch_inferred | 组合逻辑没写全，生成了锁存器 |
| blocking_in_seq | 时序逻辑里用了 =（阻塞赋值） |
| nonblocking_in_comb | 组合逻辑里用了 <= |
| width_mismatch | 位宽对不上 |
| multi_driven | 同一个信号被多处赋值 |
| non_synthesizable | 写了不能综合成电路的语句 |
| race_order_sensitive | 结果依赖 always 块的先后顺序 |
| fragile_pass | 仿真对了，但电路描述有隐患 |

### 4.7 预测把握程度与校准（2026-11 加入）
锁定预测时，学生选一次把握程度 $c\in\{1,2,3\}$（没把握 / 有点把握 / 很有把握），对应主观概率 $q(1)=\tfrac13,\ q(2)=\tfrac23,\ q(3)=1$。
范围：该学生最近 $n=10$ 次带把握程度、编译通过、预测能判定的尝试（与 4.3 节的尝试集合相同，按时间取最后 10 次；看过参考答案之后的尝试同样不计入）。

**过度自信率**
$$O=\frac{N(c=3,\ p=0)}{N(c=3)}$$
分母为 0 时为空。$O$ 高说明学生常常“很有把握却猜错”——这是自己没意识到的误区，比“没把握也猜错”更需要干预。

**校准偏差**
$$\mathrm{Cal}=\frac{1}{|S|}\sum_{i\in S}\big(q(c_i)-A_{\text{pred},i}\big)$$
大于 0 表示高估自己，小于 0 表示低估自己，接近 0 表示对自己的估计准确。

每次尝试另记两个标记（`attempts.analysis`）：`confident_miss` = $c=3$ 且 $p=0$；`under_confident` = $c=1$ 且 $p=1$。学生端判完后据此给出不同的反馈；
把握程度只由学生自己选，不参与象限和掌握等级的计算，只用于校准指标（满足全局规则 1：没有大模型参与）。

## 5. 提取练习（复习）调度
- 触发：某次尝试落在 fragile 或 concept_gap，就把该题关联知识点的一道预测题加入复习队列（优先选同知识点的其他题）
- 间隔：采用 4 个盒子，间隔分别为 1、3、7、14 天。答对进入下一个盒子；答错回到第 1 个盒子；第 4 个盒子答对后移出队列
- 每天最多推送 5 条，到期越久越优先

## 6. 教师端预警规则（满足任一条即列入“需要关注的学生”）
1. 有 2 个及以上核心知识点（blocking、sequential、fsm、parallel）的 $F_k\ge 0.5$
2. 同一知识点连续 3 次尝试落在 concept_gap
3. 近 7 天没有任何事件
4. 近 10 次重复提交的盲改率 $B\ge 0.7$
5. 过度自信：最近 10 次带把握程度的尝试里至少 3 次选了“很有把握”，且 $O\ge 0.5$（4.7 节）

## 7. 事件日志
每条事件一行，只追加不修改：
```json
{"id": "uuid", "ts": "2026-11-09T14:03:21+08:00", "anon_id": "a1b2c3d4", "user_id": 42,
 "class_id": 3, "group": "treatment", "type": "predict.submit",
 "problem_id": "seq_detector_101", "attempt_id": null,
 "payload": {"kind": "waveform", "cells": 4, "accuracy": null}, "app_version": "0.3.0"}
```

| 类型 | payload 主要字段 |
|---|---|
| auth.login / consent.accept / consent.decline | version |
| page.view | route |
| problem.open | problem_id |
| step.enter | step（predict / run / investigate / modify / make） |
| predict.submit | kind（waveform / hardware）、cells、answers、confidence（1–3，没选为空） |
| code.submit | attempt_id、code_hash、lines |
| judge.done | attempt_id、sim_ok、tags、quadrant、pred_accuracy |
| waveform.view / waveform.cell_click | attempt_id；点击时加 step、signal、is_mismatch |
| investigate.locate_step / investigate.locate_line | attempt_id、chosen、correct |
| explain.submit | attempt_id、length |
| hint.request / hint.shown | attempt_id、level；shown 时加 source（llm / fallback）、hint_id |
| answer.reveal / answer.view | 第一次查看参考答案（hint_id、failed、passed_before）/ 之后再看 |
| lesson.open / lesson.quiz | 新手入门课：打开一节课（lesson）/ 答课内小测（lesson、question、choice、correct）；小测只用于自学，不计入学情指标 |
| tour.done | 看完或关掉做题页的分步引导（finished） |
| chat.send / chat.reply | session_id、length；reply 时加 llm_call_id |
| shuffle.run | attempt_id、order_sensitive |
| tb.submit | score、caught、missed |
| review.answer | item_id、correct、box |

前端产生的界面事件（波形查看、格子点击、入门课）批量上报，每 5 秒或满 20 条发一次；离开页面时用 sendBeacon 把剩下的发出去。

## 8. 实验分组与功能开关
- 每个学生在班级里属于一个分组：treatment（实验组）、control（对照组）或 none
- 功能开关按分组配置：`predict_step`、`llm_hints`、`chat`、`shuffle`、`tb_scoring`、`review`
- 默认对照组关闭 `predict_step`、`llm_hints`、`chat`，只保留仿真和基础结果；实验结束后教师可为对照组打开全部功能
- 对照组没有预测，所以只能比较代码通过率、提交次数、盲改率和前后测成绩；实验组额外有 F 值和预测准确率

## 9. 隐私与知情同意
- 匿名 ID：`anon_id = HMAC-SHA256(ANON_SALT, user_id)` 取前 8 位十六进制，盐只放环境变量
- 研究导出只含已同意的学生，只用 anon_id，不含姓名和学号
- 教师端除班级管理页外默认匿名显示；关闭匿名需要教师手动切换，并写一条事件
- 学生撤回同意后，其数据从之后的导出中排除

## 10. 离线 ICAP 编码（教师端，研究用）
- 对象：探究步骤的“一句话解释”和助教对话中学生的发言
- 标签：P（被动）、A（主动）、C（建构）、I（互动），定义和示例写在提示词里（见 docs/llm-deepseek.md）
- 结果存 analysis_labels 表，标注“AI 编码”，不进入任何学生端指标
- 人工抽检：随机抽 10% 由教师或研究者标注，计算一致性：

$$\kappa=\frac{p_o-p_e}{1-p_e}$$

其中，$p_o$ 为人工标注与 AI 标注一致的比例，$p_e$ 为按双方各自的标签分布算出的偶然一致概率，即对每个标签取双方使用该标签的比例之积再求和。$\kappa$ 低于 0.6 时，教师端在 ICAP 结果旁提示“一致性偏低，结论需谨慎”。

## 11. 教师端指标口径（阶段 5 实现时确定）
原文没有细说的地方，实现时按下面的口径计算；教师端各页面的数字都有测试与直接写 SQL 的统计逐项对照（`backend/tests/test_teacher.py`）。
- **本周 / 上周**：北京时间自然周（周一 0 点起）；趋势图取最近 8 个自然周
- **本周活跃**：本周内有任何事件的学生数
- **作业完成率**：已开放作业里（学生, 题目）对中，到该时刻已有仿真通过的比例；作业只对其范围内的分组计入。“上周”指截至本周一 0 点
- **全班预测准确率**：该周内带预测尝试的 A_pred 平均值（对照组没有预测，为空）
- **全班 F 值**：截至该时刻，所有学生、所有知识点上（各取最近 5 次带预测尝试）分子之和 / 分母之和；趋势图每周取周末时刻的值
- **平均提示等级**：该周内首次通过的（学生, 题目）对上，通过前在这道题上请求过的最高提示等级的平均值（没用提示记 0）
- **常见误区**：按“出现过该误区的学生数”排序；裁判标签（代码层面）与预测误区（理解层面）分开标注
- **题目速览**：通过率 = 通过人数 / 做过的人数；题目 F 值 = 每个学生在这道题上最近 5 次带预测尝试的分子之和 / 分母之和；盲改率按 4.3 节只统计这道题的重复提交；平均用时 = 从第一次打开题目（或第一次提交）到第一次通过
- **预警规则 4**：每个学生取最近 10 次重复提交（按时间）计算盲改率
- **热力图**：每个格子按 4.2 节的规则计算掌握等级；可按分组、时间范围筛选（只计入范围内的尝试）
- **匿名显示**：学生按选课顺序编号为 S01、S02……；除班级管理页外，接口默认不返回真实姓名；教师关闭匿名时写一条 `teacher.anonymity` 事件
