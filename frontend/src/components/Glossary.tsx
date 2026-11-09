// 术语悬停解释：页面上出现的专业词，鼠标移上去显示通俗解释（新手入门课里也有完整的术语表）
import { Popover } from 'antd'
import type { ReactNode } from 'react'

export const GLOSSARY: Record<string, { short: string; long: string }> = {
  Verilog: { short: '一种“描述电路”的语言', long: '写的不是一步一步执行的程序，而是电路长什么样：有哪些导线、门电路和触发器，它们怎么连。' },
  FPGA: { short: '可以反复改写的芯片', long: '里面有大量查找表（LUT）和触发器，下载不同的配置，就能变成你描述的电路。改代码 → 重新综合 → 重新下载。' },
  模块: { short: 'module，一块电路', long: '像一个带引脚的芯片：input 是输入引脚，output 是输出引脚。本平台每道题都要写一个叫 top_module 的模块。' },
  端口: { short: '模块的引脚', long: 'input 从外面送进来，output 送出去。位宽 [3:0] 表示 4 根线。' },
  位宽: { short: '一个信号有几根线（几位）', long: '[3:0] 表示 4 位，能表示 0–15。结果位宽不够时，高位会被丢掉。' },
  组合逻辑: { short: '输出只看当前输入', long: '没有记忆：输入一变，输出马上跟着变。用 assign 或 always @(*) 来写，例如与门、加法器、选择器。' },
  时序逻辑: { short: '有记忆，按时钟节拍更新', long: '输出只在时钟上升沿那一刻更新，其余时间保持不变。用 always @(posedge clk) 来写，例如计数器、移位寄存器。' },
  时钟: { short: 'clk，电路的节拍器', long: '一个不停 0、1 交替的信号。时序电路只在它从 0 变 1 的那一刻（上升沿）更新。' },
  上升沿: { short: '时钟从 0 变成 1 的瞬间', long: 'posedge clk。触发器在这一瞬间“拍照”记下输入，然后一直保持到下一个上升沿。' },
  复位: { short: 'rst，让电路回到初始状态', long: '同步复位：rst 为 1 时，在时钟上升沿把寄存器清成初始值。' },
  触发器: { short: '能记住 1 位的元件', long: '在时钟上升沿记下输入，之后保持不变。always @(posedge clk) 里被赋值的信号，综合后就是触发器。' },
  锁存器: { short: '通常是写漏了分支造成的“意外记忆”', long: '组合 always 块里某种情况没给输出赋值，电路只好记住旧值，就生成了锁存器。它对毛刺敏感，一般要避免。' },
  阻塞赋值: { short: '=，立刻生效', long: '后面的语句马上能读到新值。用在组合逻辑 always @(*) 里。' },
  非阻塞赋值: { short: '<=，时钟沿统一更新', long: '同一个时钟沿里，所有 <= 右边先读旧值，最后一起更新。用在时序逻辑 always @(posedge clk) 里。' },
  仿真: { short: '在电脑上“假装”运行电路', long: '本平台用 iverilog 真实地编译、运行你的代码，给电路加上测试输入，记录每个时钟周期的输出。' },
  波形: { short: '信号随时间变化的图', long: '横轴是时间（STEP，每格一个时钟周期），纵轴是各个信号的值。看波形是调试电路最主要的方法。' },
  STEP: { short: '波形上的第几个采样点', long: '每个时钟周期采样一次（在时钟下降沿，这时上升沿的更新已经完成），从 0 开始编号。' },
  testbench: { short: '测试电路用的“测试台”', long: '另一段 Verilog 代码：给你的模块加输入、读输出、打印结果。它只用于仿真，不会变成电路。' },
  综合: { short: '把代码变成真实电路', long: '综合工具（本平台用 yosys）把代码翻译成门电路、查找表和触发器。能仿真的代码不一定能综合。' },
  LUT: { short: '查找表，FPGA 里实现组合逻辑的单元', long: '一个小存储器：把输入当地址，存好每种输入对应的输出，就能实现任意的小型组合逻辑。' },
  预测: { short: '运行前先猜结果', long: '先写下你认为电路会输出什么，再运行仿真对照。猜错的地方，就是最值得弄懂的地方。' },
  象限: { short: '代码对不对 × 预测准不准', long: '代码对、预测也对 = 真掌握；代码对、预测错 = 会写但没把握；代码错、预测对 = 设计偏差；都错 = 概念没通。' },
}

/** 包一个术语：显示原文，下面有虚线，鼠标移上去显示解释 */
export function Term({ k, children }: { k: keyof typeof GLOSSARY | string; children?: ReactNode }) {
  const g = GLOSSARY[k]
  if (!g) return <>{children ?? k}</>
  return (
    <Popover title={`${k}：${g.short}`} content={<div style={{ maxWidth: 300, fontSize: 13 }}>{g.long}</div>}
      mouseEnterDelay={0.2}>
      <span className="term" tabIndex={0} data-testid="term">{children ?? k}</span>
    </Popover>
  )
}
