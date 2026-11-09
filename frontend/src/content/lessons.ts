// 新手入门课：给完全没学过 Verilog / FPGA 的同学。每节 5–10 分钟：讲解 → 可以点的电路示意 → 小测 → 动手练习
// 小测答案只在前端判对错（只用于自学，不计入学情指标）；打开课程和答题会记事件 lesson.open / lesson.quiz

export interface QuizQ { q: string; options: string[]; answer: number; explain: string }
export interface DemoInput { name: string; values: number[] }
/** 可以点的电路示意：点输入格子切换 0/1，输出按 compute 重新算（是示意动画，不是 iverilog 仿真） */
export interface Demo {
  title: string; clocked: boolean; inputs: DemoInput[]; outputs: string[]
  compute: 'and' | 'mux' | 'dff_en' | 'blink' | 'parallel'
  note: string
}
export type Section = { kind: 'md'; text: string } | { kind: 'demo'; demo: Demo } | { kind: 'quiz'; quiz: QuizQ[] }
export interface Lesson {
  id: string; title: string; minutes: number; summary: string; sections: Section[]
  practice?: { problemId: string; title: string; why: string }
}

export const LESSONS: Lesson[] = [
  {
    id: 'what-is-fpga', title: '第 1 课 · FPGA 和 Verilog 是什么', minutes: 6,
    summary: '写代码，得到的是一块电路，而不是一个程序',
    sections: [
      { kind: 'md', text: `## 从“写程序”到“画电路”
学 C 语言时，你写的代码会被编译成**一条一条的指令**，CPU 按顺序执行。

**FPGA** 是一种特殊的芯片：里面有成千上万个小“积木”——**查找表（LUT）**和**触发器**，以及把它们连起来的导线开关。你告诉它“积木怎么连”，它就**变成**你想要的电路。改一下描述、重新下载，又能变成另一个电路。

**Verilog** 就是用来描述“积木怎么连”的语言，叫**硬件描述语言（HDL）**。

## 从代码到电路的四步
1. **写代码**：用 Verilog 描述电路
2. **仿真**：在电脑上给电路加测试输入，看输出对不对（本平台用 iverilog 真实地仿真）
3. **综合**：工具把代码翻译成门电路和触发器（本平台用 yosys，并统计用了几个触发器）
4. **下载**：把结果写进 FPGA，电路就在芯片里真实运行了

本平台帮你练前三步。真实开发也是先仿真、确认没问题，再上板。` },
      { kind: 'quiz', quiz: [
        { q: 'Verilog 代码最终会变成什么？', options: ['一串让 CPU 按顺序执行的指令', 'FPGA 里连接好的电路', '一张图片'], answer: 1,
          explain: 'Verilog 描述的是电路结构，综合后变成 FPGA 里的查找表、触发器和连线。' },
        { q: '在本平台上点“仿真”时发生了什么？', options: ['大模型猜一个结果', 'iverilog 真实地编译、运行你的代码', '直接下载到开发板'], answer: 1,
          explain: '对错只由仿真工具判定。大模型只负责把结果翻译成提示。' },
      ] },
    ],
  },
  {
    id: 'not-c', title: '第 2 课 · 和 C 语言最大的不同：硬件是同时工作的', minutes: 7,
    summary: '每一行描述的电路都在同时工作，没有“先执行哪一行”',
    sections: [
      { kind: 'md', text: `## C 语言：一行一行地执行
\`\`\`c
x = a + b;   // 先算这一行
y = x * 2;   // 再算这一行
\`\`\`

## Verilog：每一行都是一块同时工作的电路
\`\`\`verilog
assign x = a & b;   // 一个与门，一直在工作
assign y = x | c;   // 一个或门，也一直在工作
\`\`\`
这两行描述的是**两个门电路和它们之间的导线**。交换它们的先后，电路完全一样——就像在电路板上，先焊哪个元件不影响电路怎么工作。

> 记住：Verilog 写的是“电路长什么样”，不是“按什么顺序做事”。

所以学 Verilog 时，要不断问自己：**这一句会变成什么硬件？** 是一根导线、一个门，还是一个能记住数据的触发器？` },
      { kind: 'demo', demo: { title: '两个门同时工作：x = a & b，y = x | c', clocked: false,
        inputs: [{ name: 'a', values: [0, 1, 1, 0, 1, 1] }, { name: 'b', values: [0, 0, 1, 1, 1, 0] }, { name: 'c', values: [0, 0, 0, 1, 0, 1] }],
        outputs: ['x', 'y'], compute: 'parallel', note: '点一下输入格子切换 0 / 1：输入一变，x 和 y 在同一时刻就跟着变，没有“先后”。' } },
      { kind: 'quiz', quiz: [
        { q: '把上面两条 assign 交换先后，电路会变吗？', options: ['会，先写的先执行', '不会，它们描述的是同时工作的两块电路'], answer: 1,
          explain: 'assign 描述的是连线关系，顺序不影响电路。' },
        { q: '学 Verilog 时最该问自己的问题是？', options: ['这一行先执行还是后执行', '这一句会变成什么硬件'], answer: 1,
          explain: '从“它是什么电路”去理解代码，就不会把 C 语言的习惯带进来。' },
      ] },
    ],
  },
  {
    id: 'module', title: '第 3 课 · 模块和端口：电路的外壳', minutes: 6,
    summary: 'module 是一块带引脚的电路；input / output 是引脚，[3:0] 是有几根线',
    sections: [
      { kind: 'md', text: `## 一个模块长这样
\`\`\`verilog
module top_module (
    input  wire       a,     // 1 根输入线
    input  wire [3:0] b,     // 4 根输入线：b[3] b[2] b[1] b[0]
    output wire       y      // 1 根输出线
);
    assign y = a & b[0];
endmodule
\`\`\`
- \`module … endmodule\`：一块电路，像一个芯片
- 括号里是**端口**（引脚）：\`input\` 是输入，\`output\` 是输出
- \`[3:0]\` 是**位宽**：这个信号有 4 根线，能表示 0–15
- 本平台每道题都要写一个叫 **top_module** 的模块，端口名要和题目说明完全一致

## wire 还是 reg？
- 用 \`assign\` 驱动的信号，声明成 **wire**
- 在 \`always\` 块里赋值的信号，声明成 **reg**

这是初学者最常见的编译错误之一。注意：reg 只是语法上的规定，**不一定**会变成寄存器（第 5 课会讲什么时候才会）。` },
      { kind: 'quiz', quiz: [
        { q: '`input wire [7:0] data` 表示 data 有几根线？', options: ['7', '8', '1'], answer: 1, explain: '[7:0] 是第 7 位到第 0 位，一共 8 位。' },
        { q: '在 always 块里赋值的输出，应该声明成？', options: ['wire', 'reg'], answer: 1, explain: 'always 里赋值的信号声明成 reg；assign 驱动的声明成 wire。' },
      ] },
    ],
    practice: { problemId: 'b1_and_gate', title: '入门 1：第一个电路——与门', why: '读一个最小的模块，预测它的输出' },
  },
  {
    id: 'comb', title: '第 4 课 · 组合逻辑：输出只看当前输入', minutes: 8,
    summary: 'assign 和 always @(*)；输入一变输出立刻变；漏写分支会生成锁存器',
    sections: [
      { kind: 'md', text: `## 组合逻辑 = 没有记忆
输出**只由当前输入**决定。常用运算：

| 写法 | 含义 |
|---|---|
| \`a & b\` | 与：都为 1 才是 1 |
| \`a \\| b\` | 或：有一个 1 就是 1 |
| \`~a\` | 非：取反 |
| \`a ^ b\` | 异或：不同为 1 |
| \`s ? b : a\` | 选择：s 为 1 取 b，否则取 a |

## 两种写法
\`\`\`verilog
assign y = sel ? b : a;      // 简单的用 assign

always @(*) begin            // 复杂一点的用 always @(*)
    if (sel) y = b;          // 组合块里用 =
    else     y = a;          // 每种情况都要赋值！
end
\`\`\`
\`always @(*)\` 里如果**漏掉某种情况**没给输出赋值，电路就只好“记住旧值”，生成一个**锁存器**——这通常是 bug。养成习惯：**if 一定配 else，case 一定写 default**，或者在开头先给一个默认值。` },
      { kind: 'demo', demo: { title: '二选一选择器：y = sel ? b : a', clocked: false,
        inputs: [{ name: 'a', values: [1, 1, 0, 0, 1, 0] }, { name: 'b', values: [0, 0, 1, 1, 1, 0] }, { name: 'sel', values: [0, 1, 1, 0, 1, 1] }],
        outputs: ['y'], compute: 'mux', note: '把 sel 切成 0 或 1，看 y 跟着 a 还是 b 走。' } },
      { kind: 'quiz', quiz: [
        { q: '下面哪种写法会生成锁存器？', options: ['always @(*) if (s) y = b; else y = a;', 'always @(*) if (s) y = b;', 'assign y = s ? b : a;'], answer: 1,
          explain: 's 为 0 时 y 没有赋值，电路只好记住旧值，变成锁存器。' },
        { q: '组合 always 块里应该用哪种赋值？', options: ['=（阻塞赋值）', '<=（非阻塞赋值）'], answer: 0, explain: '组合逻辑用 =，算出的中间结果马上能被后面的语句用到。' },
      ] },
    ],
    practice: { problemId: 'b2_mux2', title: '入门 2：二选一选择器', why: '改一行代码，让 sel 起作用' },
  },
  {
    id: 'seq', title: '第 5 课 · 时序逻辑：时钟、触发器和 <=', minutes: 9,
    summary: '只在时钟上升沿更新、其余时间保持——电路有了记忆',
    sections: [
      { kind: 'md', text: `## 时钟：电路的节拍器
时钟 \`clk\` 是一个不停 0、1 交替的信号。**时序逻辑**只在时钟**上升沿**（从 0 变 1 的瞬间）更新，其余时间保持不变。

\`\`\`verilog
always @(posedge clk) begin
    if (rst)     q <= 1'b0;   // 复位
    else if (en) q <= d;      // 使能时记下 d
end                           // 否则 q 保持原值
\`\`\`
- \`always @(posedge clk)\`：每个时钟上升沿执行一次
- \`<=\`（**非阻塞赋值**）：同一个时钟沿里，所有右边先读**旧值**，最后一起更新。时序逻辑里一律用它
- 这样被赋值的 \`q\` 综合后就是一个**触发器**：能记住 1 位数据

时序块里“没赋值”是正常的，表示保持，**不会**生成锁存器（和组合块不一样）。

## 怎么读时序电路的波形
本平台的波形里，每个 STEP 是一个时钟周期：**先给输入 → 上升沿到来 → 再采样输出**。所以某一步看到的 q，是这一步的上升沿**之后**的值。` },
      { kind: 'demo', demo: { title: '带使能的 D 触发器：en = 1 时记下 d', clocked: true,
        inputs: [{ name: 'rst', values: [1, 0, 0, 0, 0, 0, 0, 0] }, { name: 'en', values: [0, 1, 0, 0, 1, 0, 1, 0] }, { name: 'd', values: [0, 1, 0, 1, 0, 1, 1, 0] }],
        outputs: ['q'], compute: 'dff_en', note: '看 en = 0 的那几步：d 变来变去，q 一动不动——这就是“记忆”。点格子改 en 或 d 试试。' } },
      { kind: 'quiz', quiz: [
        { q: 'always @(posedge clk) 里被赋值的信号，综合后通常是什么？', options: ['导线', '触发器', '锁存器'], answer: 1, explain: '时钟沿触发的赋值会生成触发器（寄存器）。' },
        { q: '时序 always 块里应该用哪种赋值？', options: ['=', '<='], answer: 1, explain: '用 <=：所有触发器在同一个时钟沿一起更新，和语句先后无关。' },
        { q: 'en = 0 时，d 从 0 变成 1，q 会怎样？', options: ['马上变成 1', '保持原来的值'], answer: 1, explain: 'en = 0 时不记新值，q 保持。' },
      ] },
    ],
    practice: { problemId: 'b3_dff_en', title: '入门 3：会记忆的寄存器', why: '预测触发器什么时候变、什么时候不变' },
  },
  {
    id: 'debug', title: '第 6 课 · 计数器、分频和看波形调试', minutes: 9,
    summary: '用计数器让 LED 闪烁；用“预测 → 仿真 → 找第一个对不上的格子”来调试',
    sections: [
      { kind: 'md', text: `## 计数器：时序逻辑最常见的用法
\`\`\`verilog
reg [1:0] cnt;                     // 内部信号：不是端口，写在模块里面
always @(posedge clk) begin
    if (rst) cnt <= 2'd0;
    else     cnt <= cnt + 2'd1;    // 每个时钟沿加 1：0 1 2 3 0 1 ……
end
\`\`\`
开发板的时钟每秒有 5000 万个上升沿，直接拿去点 LED，人眼看不出闪。**数够 N 个周期才翻转一次**，LED 就慢下来了，这叫**分频**。

## 本平台的做题流程
1. **预测**：运行前，先在波形里填你认为的输出（猜错没关系）
2. **运行**：iverilog 真实仿真，把你的预测、你的电路、期望结果放在一起对照
3. **探究**：找出**第一个对不上的格子**，再在代码里点出决定它的那一行
4. **修改 / 创作**：改代码，或者自己写测试激励

调试的诀窍：**只看第一个对不上的周期**。后面的错误往往是它带出来的。那一步之前的输入是什么？你的代码在那个时钟沿做了什么？` },
      { kind: 'demo', demo: { title: '计数分频：每 4 个周期 LED 翻转一次', clocked: true,
        inputs: [{ name: 'rst', values: [1, 0, 0, 0, 0, 0, 0, 0, 0, 0] }],
        outputs: ['cnt', 'led'], compute: 'blink', note: '数一数：cnt 从 3 回到 0 的那个时钟沿，led 翻转。把中间某一步的 rst 点成 1，看看会怎样。' } },
      { kind: 'quiz', quiz: [
        { q: '调试时应该先看哪里？', options: ['最后一个对不上的周期', '第一个对不上的周期', '随便哪个'], answer: 1, explain: '第一个对不上的地方最接近 bug 的源头。' },
        { q: '两位的计数器 cnt 能数到几？', options: ['2', '3', '4'], answer: 1, explain: '两位能表示 0–3，3 再加 1 回到 0。' },
      ] },
    ],
    practice: { problemId: 'b4_led_blink', title: '入门 4：让 LED 闪起来', why: '第一次从零写出一个时序电路' },
  },
]

/** 示意电路：根据输入算输出（每一步一个时钟周期） */
export function computeDemo(kind: Demo['compute'], inputs: Record<string, number[]>, steps: number): Record<string, (number | string)[]> {
  const out: Record<string, (number | string)[]> = {}
  const v = (n: string, i: number) => inputs[n]?.[i] ?? 0
  if (kind === 'and') out.y = Array.from({ length: steps }, (_, i) => v('a', i) & v('b', i))
  if (kind === 'parallel') {
    out.x = Array.from({ length: steps }, (_, i) => v('a', i) & v('b', i))
    out.y = Array.from({ length: steps }, (_, i) => (v('a', i) & v('b', i)) | v('c', i))
  }
  if (kind === 'mux') out.y = Array.from({ length: steps }, (_, i) => (v('sel', i) ? v('b', i) : v('a', i)))
  if (kind === 'dff_en') {
    let q: number | string = 'x'
    out.q = Array.from({ length: steps }, (_, i) => {
      if (v('rst', i)) q = 0
      else if (v('en', i)) q = v('d', i)
      return q
    })
  }
  if (kind === 'blink') {
    let cnt: number | string = 'x'
    let led: number | string = 'x'
    out.cnt = []
    out.led = []
    for (let i = 0; i < steps; i++) {
      if (v('rst', i)) { cnt = 0; led = 0 } else if (typeof cnt === 'number' && typeof led === 'number') {
        if (cnt === 3) led = led ? 0 : 1
        cnt = (cnt + 1) % 4
      }
      out.cnt.push(cnt)
      out.led.push(led)
    }
  }
  return out
}
