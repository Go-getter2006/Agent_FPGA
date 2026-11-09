// 时间一律按北京时间显示
const fmt = new Intl.DateTimeFormat('zh-CN', {
  timeZone: 'Asia/Shanghai', month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false,
})

export function beijingTime(iso: string | null | undefined): string {
  if (!iso) return ''
  const d = new Date(/[zZ]|[+-]\d\d:\d\d$/.test(iso) ? iso : `${iso}Z`)
  return fmt.format(d)
}

export function percent(v: number | null | undefined, digits = 0): string {
  return v === null || v === undefined ? '—' : `${(v * 100).toFixed(digits)}%`
}

export function binToHex(bin: string): string {
  if (!/^[01]+$/.test(bin)) return bin.toUpperCase()
  return parseInt(bin, 2).toString(16).toUpperCase()
}

export const STEP_LABEL: Record<string, string> = {
  predict: '预测', run: '运行', investigate: '探究', modify: '修改', make: '创作', done: '完成',
}

export const STATUS_LABEL: Record<string, string> = {
  not_started: '未开始', in_progress: '进行中', passed: '已通过', mastered: '真掌握',
}

export const TAG_LABEL: Record<string, string> = {
  compile_error: '编译没通过',
  sim_mismatch: '仿真和期望对不上',
  latch_inferred: '组合逻辑没写全，生成了锁存器',
  blocking_in_seq: '时序逻辑里用了 =（阻塞赋值）',
  nonblocking_in_comb: '组合逻辑里用了 <=',
  width_mismatch: '位宽对不上',
  multi_driven: '同一个信号被多处赋值',
  non_synthesizable: '写了不能综合成电路的语句',
  race_order_sensitive: '结果依赖 always 块的先后顺序',
  fragile_pass: '仿真对了，但电路描述有隐患',
}

export const QUADRANT_HINT: Record<string, string> = {
  mastered: '写对了，也知道它为什么对。',
  fragile: '代码对了，但你的预测没对上，说明还没完全想清楚它为什么对。',
  design_gap: '你读懂了自己的代码，问题出在设计思路上，回到题目说明对照期望波形。',
  concept_gap: '写出来的电路和你预想的不一样，先弄清代码实际做了什么。',
}
