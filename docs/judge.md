# 仿真裁判（judge）说明

裁判是整个系统里唯一判定对错的部件：给定学生代码和题目，用仿真器和综合工具产出**可复现的结构化诊断**。它不调用任何大模型。学情指标、提示、教师看板都以它的输出为依据。

## 1. 规则
1. 正误只由 iverilog / yosys / verilator 的结果决定。
2. 同一输入多次运行，标准输出的 JSON 必须完全一致（时间戳只写进日志）。
3. 学生代码在临时目录中编译运行；每个外部命令设超时（默认 10 秒）。超时记为 `"timeout": true`，程序不能崩溃。
4. 未经我同意，不修改 `problems/` 下的 `ref.v`、`tb.v`，不改输出 JSON 的字段名。
5. 裁判既能命令行调用，也能被后端当 Python 库调用：`from judge import diagnose, shuffle_test, score_testbench`。
6. 依赖：Python 3.10+ 标准库，外加 PyYAML（读 problem.yaml），不引入别的库。

## 2. 环境
- 系统工具：iverilog、vvp、yosys、verilator
- 云端会话在环境的 setup script 中安装：`apt-get update && apt-get install -y iverilog yosys verilator`

## 3. 题目目录
```text
problems/<题目ID>/
  problem.yaml  题目元数据（见下）
  spec.md       题目说明（中文），写明输入、输出信号
  ref.v         参考答案，顶层模块名固定为 top_module
  tb.v          testbench：实例化 top_module，按第 4 节格式打印采样结果
  starter.v     起始代码（预测题、修改题才有）
  cases/        人工构造的错误样本，文件第一行写预期标签，如 // expect: latch_inferred, fragile_pass
```

problem.yaml 示例：
```yaml
id: seq_detector_101
title: 序列检测器（101）
knowledge_points: [fsm, nonblocking, sequential]   # 取值见 docs/learner-model.md 知识点表
primm_type: make            # predict | modify | make
difficulty: 2               # 1–3
starter: null               # 预测题、修改题填 starter.v
predict_points:             # 学生要预测的格子：输出信号 × STEP
  - {signal: out, steps: [1, 3, 4, 8]}
hardware_questions: [ff_count, latch, ff_signals]
expected_ff_count: 2        # 参考答案应有的触发器位数（参考答案的 out 是组合输出）
expected_drivers:           # 阶段 2 用：ref.v 里驱动各输出的源码行
  out: [23]
modify_goal: ""             # 修改题的目标说明
```

## 4. testbench 打印格式
每个采样点一行：`STEP <序号> | <输入名>=<值> ... | <输出名>=<值> ...`
- 值用二进制（%b），X/Z 原样输出
- 时序电路在时钟下降沿采样，避免与上升沿竞争；组合电路在激励改变后 #1 再采样
- 结束时调用 $finish
- 内部信号（如 state）需要展示时，也按 `<名字>=<值>` 打印在输出区，并在 spec.md 里注明“仅供观察”

## 5. 诊断流程（diagnose）
1. 编译：iverilog 编译学生代码 + tb.v。失败则记录错误（行号 + 原始信息），跳过仿真
2. 仿真：ref.v 和学生代码分别与同一个 tb.v 仿真。保存学生代码的完整轨迹（解析每一行 STEP），并与参考答案逐行比较，记录第一个不一致的 STEP、信号、期望值、实际值和该 STEP 的输入
3. 综合检查：yosys 读入学生代码，`synth -top top_module`；综合报错记为 non_synthesizable（初版只认 yosys 报错，规则以后再补）
4. 硬件统计（综合失败时 hardware 各字段为 null）：
   - 在 `proc` 之后，从 `$dff` 类单元的 Q 端读出被综合成触发器的信号，从 `$dlatch` 类单元读出锁存器信号
   - 用 `synth_xilinx -top top_module` 后 `stat`，统计触发器和 LUT 数量（目标器件先按 Xilinx 7 系列，课程板卡确定后再改）
5. 静态检查：`verilator --lint-only -Wall`。只把第 7 节表中有对应标签的告警映射成标签，其余原样放进 lint 字段
6. 生成标签，并向 logs/judge.jsonl 追加一行（含时间戳、题目 ID、学生 ID、完整诊断）

## 6. 输出 JSON
`python -m judge <学生代码.v> <题目ID> [--student <匿名ID>]`，向标准输出打印：

```json
{
  "problem": "seq_detector_101",
  "compile": {"ok": true, "errors": []},
  "sim": {"ok": false, "timeout": false,
          "trace": [{"step": 0, "inputs": {"rst": "1", "in": "0"}, "outputs": {"out": "0"}}],
          "first_mismatch": {"step": 3, "signal": "out", "expected": "1", "actual": "0",
                             "inputs": {"rst": "0", "in": "1"}}},
  "synth": {"ok": true, "messages": []},
  "hardware": {"ff_signals": ["state", "out"], "latch_signals": [],
               "ff_count": 3, "lut_count": 4},
  "lint": [{"code": "WIDTHTRUNC", "line": 12, "message": "..."}],
  "drivers": {"out": [24, 25], "state": [13, 15, 16, 17, 18]},
  "tags": ["sim_mismatch"]
}
```
- `sim.trace` 是学生代码自己的仿真结果（示例只列了一行），不是参考答案的。预测题的标准答案就从这里取
- `drivers` 是阶段 2 新增字段，阶段 1 输出 `{}` 即可

## 7. 标签
| 标签 | 判定依据 | 阶段 |
|---|---|---|
| compile_error | iverilog 编译失败 | 1 |
| sim_mismatch | 与参考答案的仿真输出不一致 | 1 |
| latch_inferred | `hardware.latch_signals` 非空 | 1 |
| non_synthesizable | yosys 综合报错 | 1 |
| multi_driven | 同一信号有多个驱动（yosys 或 verilator 报告） | 1 |
| blocking_in_seq | 时序 always 块中用阻塞赋值（verilator BLKSEQ） | 1 |
| nonblocking_in_comb | 组合 always 块中用非阻塞赋值（verilator COMBDLY） | 1 |
| width_mismatch | 位宽不匹配（verilator WIDTH 类告警） | 1 |
| fragile_pass | 仿真通过，同时带有 latch_inferred / non_synthesizable / multi_driven 任一标签 | 1 |
| race_order_sensitive | 顺序打乱实验中，仿真结果随 always 块顺序改变 | 2 |

## 8. 阶段 1 完成标准
- 先做 1 道题把流程跑通，把输出 JSON 给我确认，再扩到 5 道：组合 2、时序 2、状态机 1
- 每道题至少 4 个错误样本，覆盖不同标签，其中至少 1 个是 fragile_pass
- `pytest` 全部通过：
  - 每个样本的 tags 包含其预期标签（多出的标签在测试输出里列出，供我检查）；ref.v 自身的 tags 为空
  - 每道题 ref.v 的 `hardware.ff_count` 与 problem.yaml 的 `expected_ff_count` 一致

## 9. 阶段 2：裁判扩展

### 9.1 信号 → 代码行映射（drivers）
- 用途：前端把“波形里对不上的格子”和“编辑器里的代码行”联动起来，这是训练“代码 ↔ 仿真”对应能力的核心交互
- 做法：读入学生代码，`proc` 之后遍历驱动各信号的单元和连续赋值，读取它们的 `src` 属性（形如 `student.v:24.5-24.30`），得到每个信号由哪些源码行驱动；行号升序去重
- 先试验：动手前用 2 道题看 yosys 能给到什么粒度。如果只能拿到整个 always 块的行范围，就返回整个范围，并在 JSON 里加 `"drivers_granularity": "block"`（否则为 `"statement"`）。把试验结果告诉我再继续
- 验收：每道题 ref.v 的 drivers 与 problem.yaml 的 `expected_drivers` 一致

### 9.2 顺序打乱实验（shuffle_test）
- 目的：检验代码是否依赖“仿真器执行 always 块的先后顺序”。真实硬件没有先后，结果随顺序变化，说明代码描述的不是真正并行的硬件（竞争）
- 做法：找出模块内顶层 always 块，生成最多 6 种排列（块数 ≤ 3 时穷举），每种排列和原 tb.v 仿真，比较轨迹。只重排整块，不改块内语句；变体里的行号要能映射回原文件行号
- 先验证：在 `tests/fixtures/` 放两个经典例子：
  - `race_blocking.v`：两个 always 块在同一时钟沿用阻塞赋值互相读写（y1 = y2; y2 = y1 这一类）
  - `race_nonblocking.v`：同样结构改成非阻塞赋值
  确认 iverilog 下交换块顺序会改变前者的结果、不改变后者的结果。**如果交换源码顺序不能改变 iverilog 的执行顺序，停下来告诉我，不要自行换方案**
- 输出：
```json
{"order_sensitive": true, "blocks": 3,
 "variants": [{"order": [2, 1, 3],
               "first_diff": {"step": 4, "signal": "y1", "base": "1", "variant": "0"}}]}
```
- order_sensitive 为真时，在该次诊断的 tags 里加 race_order_sensitive

### 9.3 testbench 打分（score_testbench）
- 学生提交自己的 testbench（必须实例化 top_module，并按第 4 节格式打印）
- 先用 ref.v 跑学生 tb：编译失败或一行 STEP 都没有，返回中文错误说明
- 再用 cases/ 里每个错误样本跑同一个 tb：输出轨迹与 ref.v 的轨迹不同，就算“抓住”这个 bug
- 不计入的样本：预期标签含 fragile_pass 的（仿真输出与参考答案相同，任何激励都抓不到），以及预期标签含 compile_error 的（任何激励下都编译不过，总会被“抓住”，计入等于白送分）。阶段 2 起改为这样
- 得分：

$$S_{\text{tb}}=\frac{|\mathcal{C}|}{|\mathcal{M}|-|\mathcal{E}|}$$

其中，$\mathcal{M}$ 为该题全部错误样本的集合，$\mathcal{E}$ 为不计入的样本（预期标签含 fragile_pass 或 compile_error），$\mathcal{C}$ 为被学生 testbench 抓住的样本；$|\cdot|$ 表示集合中的元素个数。

- 输出：
```json
{"ok": true, "steps": 24, "score": 0.67,
 "caught": ["c1_latch.v", "c4_width.v"], "missed": ["c3_reset.v"], "excluded": ["c2_fragile.v"]}
```
- 验收：把题目自带的 tb.v 当作“学生 tb”提交时，得分必须为 1.0。这同时检验题目质量：自带 tb 必须能抓住所有可抓的样本

## 10. 实现约定（阶段 1 定下，后续阶段沿用）
1. **语言标准**：三个工具都按 Verilog-2005（iverilog `-g2005`、yosys 默认、verilator `--default-language 1364-2005`）。tb 的顶层模块名固定为 `tb`，编译时用 `-s tb`
2. **JSON 补充字段**（只增不改）：
   - `compile.errors` 每项为 `{file, line, message}`，`file` 区分报错在 `student.v` 还是 `tb.v`
   - `synth.timeout`：综合超时时为 true，此时不打 non_synthesizable
   - 编译失败时：`sim.trace` 为空，`synth.ok` 为 null（未运行），`hardware` 各字段为 null，`lint` 为空，标签只有 compile_error
3. **仿真超时**：轨迹为空、`first_mismatch` 为 null、`sim.timeout` 为 true，并打 sim_mismatch（不新增标签；前端据 timeout 提示“可能有组合环路或死循环”）
4. **触发器信号与个数**：
   - `ff_signals` / `latch_signals`：`proc; flatten; opt_clean` 之后读 RTLIL 中触发器 / 锁存器单元 Q 端连接的信号名。加 `opt_clean` 是为了去掉输出没人用的单元，否则 for 循环变量、块内临时变量也会被算成触发器
   - `ff_count` / `lut_count`：`synth_xilinx -flatten -nosrl` 之后 `stat`。综合前给所有信号加 `fsm_encoding="none"`，不让 yosys 把状态机改成独热码，触发器个数与代码里写的状态位宽一致；`-nosrl` 防止移位寄存器被映射成 SRL16E
5. **lint 与标签**：`lint` 列出 verilator 的全部告警（含已映射成标签的）；`-Wno-DECLFILENAME`（文件名由裁判固定）。WIDTHEXPAND 中被扩展的一方只有 1 位时（如 `a + b + cin`、`count + en`）不打 width_mismatch，多位扩展和所有截断仍然打
6. **multi_driven**：yosys 综合日志中出现 “multiple conflicting drivers”，或 verilator 报 MULTIDRIVEN
7. **错误样本**：除 fragile_pass 外，每个样本都必须让题目自带的 tb 仿真失败（9.3 节自带 tb 得分 1.0 的前提）。只触发 blocking_in_seq / nonblocking_in_comb、仿真却正确的写法不放进 `cases/`，放在 `judge/tests/fixtures/` 里测试
8. **内部信号**：problem.yaml 暂时没有字段标记“仅供观察、不参与比较”的信号，现有题目的 tb 都不打印内部信号
9. **日志**：`logs/judge.jsonl` 每行 `{ts, type, problem, student, diagnosis}`（testbench 打分记录用 `result` 代替 `diagnosis`），路径可用环境变量 `JUDGE_LOG_PATH` 覆盖；题目目录可用 `JUDGE_PROBLEMS_DIR` 覆盖
10. **testbench 打分**（9.3 节）：
    - 命令行：`python -m judge <学生tb.v> <题目ID> --testbench`
    - 学生 tb 的模块名不限，由 iverilog 自动找顶层；源码里（去掉注释后）必须有 `top_module` 的实例
    - 输出在 9.3 节字段之外补充 `message`（失败时的中文说明，成功时为 null）和 `errors`（tb 编译报错，格式同 `compile.errors`）；失败时 `score` 为 null
    - 错误样本在学生 tb 下编译失败、仿真超时或轨迹与参考答案不同，都算“抓住”
    - `score` 保留 4 位小数；可计入的样本数为 0 时为 null
    - 所有仿真都带 `vvp -none`，tb 里的 `$dumpvars` 不会写波形文件
11. **日志记录类型**：`logs/judge.jsonl` 每行带 `type`（`diagnose` / `score_testbench`）
12. **信号 → 代码行（9.1 节）**：
    - 试验结论（yosys 0.33）：`proc` 之后，连续赋值和运算符单元的 src 能精确到行；组合 always 块里的 if / case 只给到整条 if / case 语句的范围；时序块里寄存器的触发器单元 src 是整个 always 块；赋常数的语句（如 `q <= 0`）没有任何单元记录
    - 做法：先用 yosys 从信号出发、沿内部连线往回找驱动单元，得到候选行范围；再用 `judge/vparse.py` 的词法扫描，在候选范围内只保留这个信号出现在赋值号左边的行。连续赋值（`assign`、`wire` 声明赋值）不受候选范围限制；子模块例化的输出取例化语句所在行；yosys 读不进的代码（如不可综合的 while）只用词法扫描结果
    - 扫描失败或某个信号一行都找不到时，退回 yosys 的候选范围，`drivers_granularity` 记为 `"block"`，否则为 `"statement"`；编译失败时 `drivers` 为 `{}`、`drivers_granularity` 为 null
    - `drivers` 包含除输入端口外的所有具名信号（输出、内部 reg / wire），键按字母序
13. **顺序打乱实验（9.2 节）**：
    - 试验结论（iverilog 12）：交换源码里 always 块的先后会改变 iverilog 的执行顺序；`race_blocking.v` 结果随之改变，`race_nonblocking.v` 不变
    - 命令行：`python -m judge <学生代码.v> <题目ID> --shuffle`；库：`shuffle_test(code, problem_id)`，`apply_shuffle(diagnosis, shuffle)` 在顺序相关时给诊断加上 race_order_sensitive
    - 块数 ≤ 3 时穷举全部排列；更多时取倒序、左移、右移、两两交换和固定种子的随机排列，含原顺序共 6 种
    - 输出在 9.2 节字段之外补充：`ok`、`message`（失败或无需实验时的中文说明）、`block_lines`（各 always 块在原文件中的起止行，`order` 里的编号即对应这里的下标 +1）、`base_trace`（原顺序的仿真轨迹）；`variants` 每项补充 `timeout`、`errors`（变体编译报错，行号已映射回原文件）和 `trace`（该排列的仿真轨迹，前端 diff 模式用）。变体超时或编译失败也算顺序相关
    - 原代码编译失败或仿真超时时 `ok` 为 false、`order_sensitive` 为 null
14. **资源限制（阶段 6）**：Linux 上每个外部命令经 `prlimit` 限制 CPU 时间（超时秒数 + 5）、内存（`JUDGE_MEMORY_MB`，默认 2048）、写文件大小（`JUDGE_OUTPUT_MB`，默认 32）；工具输出先写临时文件，所以输出量也受这个上限约束。超出 CPU 或输出上限按超时处理（`sim.timeout` 为 true，与第 3 条一致），输出 JSON 字段不变。`JUDGE_RLIMITS=0` 关闭；没有 prlimit 的系统自动不加限制。详见 docs/deploy.md 第 5 节
15. **题目目录的可选内容（2026-11）**：`skeleton.v` 是给学生看的代码框架（`____` 处留空），第 3 级规则提示会用到；`problem.yaml` 可加 `order`（题目列表里的顺序，默认 100，入门题是 1–4）和 `stage: beginner`（入门题）。这三项都不影响裁判输出。入门题 4 道：`b1_and_gate`、`b2_mux2`、`b3_dff_en`、`b4_led_blink`，样本要求与其他题相同
16. **电路图网表（2026-11）**：`judge.schematic(code)` 用 yosys `read_verilog; prep -top top_module; opt_clean -purge; write_json` 生成 RTL 级网表（加法器、比较器、选择器、触发器这一级），给前端用 netlistsvg 画电路图。
    每个单元带 src 行号（`src_lines` 解析 `student.v:16.13-16.26|…`）和它驱动的有名字的信号（`outputs`；触发器的 src 覆盖整个 always 块，前端按输出信号对应到赋值行）。
    只用于展示，不参与判对错，也不改 `diagnose` 的输出。后端接口 `GET /api/student/attempts/{aid}/schematic`，第一次生成后缓存在 `attempts.analysis.schematic`
