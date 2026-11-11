// 硬件面板：触发器个数、锁存器、哪些信号成了触发器（你的预测 / 实际并排）
// 每个问题旁边写着怎么判断；运行之后逐个信号解释“为什么”，点一下在代码里高亮对应的行
import { InputNumber, Popover, Radio, Select } from 'antd'
import { CodeBlock } from '../lib/markdown'
import type { EvalItem, Judge } from '../api/types'

export interface HardwareAnswers { ff_count: number | null; latch: boolean | null; ff_signals: string[] }

const Q_LABEL: Record<string, string> = {
  ff_count: '会综合出几个触发器', latch: '有没有锁存器', ff_signals: '哪些信号成了触发器',
}

// 怎么判断：一句话规则 + 一个最小例子（和第 5 课的内容一致）
const Q_HOW: Record<string, { rule: string; example: string }> = {
  ff_count: {
    rule: '数一数 always @(posedge clk) 里被赋值的信号：每一位是一个触发器。assign 和 always @(*) 不产生触发器。',
    example: 'reg [3:0] q;\nalways @(posedge clk) q <= q + 1;   // q 有 4 位 → 4 个触发器\nassign y = a & b;                  // 与门 → 0 个触发器',
  },
  latch: {
    rule: '看 always @(*)：有没有哪种情况没给信号赋值（if 少了 else、case 少了 default）？有，就会生成锁存器（通常是 bug）。',
    example: 'always @(*) begin\n    if (en) y = a;      // en = 0 时 y 没赋值\nend                     // → 锁存器\n\nalways @(*) begin\n    y = 0;              // 先给默认值\n    if (en) y = a;      // → 没有锁存器\nend',
  },
  ff_signals: {
    rule: '声明成 reg 不一定是触发器：只有在 always @(posedge clk) 里赋值的才是；always @(*) 里的 reg 只是一根导线。',
    example: 'reg q, y;\nalways @(posedge clk) q <= d;   // q：触发器\nalways @(*)          y = a & b; // y：组合逻辑，不是触发器',
  },
}

function How({ q }: { q: string }) {
  const h = Q_HOW[q]
  if (!h) return null
  return (
    <div className="hw-how">{h.rule}
      <Popover title="例子" content={<div style={{ width: 420 }}><CodeBlock code={h.example} title="示例" /></div>}>
        <button type="button" className="link-btn" data-testid={`hw-how-${q}`}>看例子</button>
      </Popover>
    </div>
  )
}

function Mark({ ok }: { ok: boolean | null }) {
  if (ok === null) return <b className="muted">?</b>
  return ok ? <b className="ok" aria-label="预测对">✓</b> : <b className="bad" aria-label="预测没对上">✗</b>
}

export function HardwarePredict({ questions, value, onChange, candidates, disabled }: {
  questions: string[]; value: HardwareAnswers; onChange: (v: HardwareAnswers) => void
  candidates: string[]; disabled?: boolean
}) {
  return (
    <div className="hw-grid" data-testid="hardware-predict">
      {questions.includes('ff_count') && (
        <div className="hw-q">
          <div className="hw-l">{Q_LABEL.ff_count}</div>
          <InputNumber min={0} max={512} value={value.ff_count ?? undefined} disabled={disabled}
            aria-label={Q_LABEL.ff_count} data-testid="hw-ff-count"
            onChange={(v) => onChange({ ...value, ff_count: v === null ? null : Number(v) })} />
          <How q="ff_count" />
        </div>
      )}
      {questions.includes('latch') && (
        <div className="hw-q">
          <div className="hw-l">{Q_LABEL.latch}</div>
          <Radio.Group value={value.latch} disabled={disabled} aria-label={Q_LABEL.latch}
            onChange={(e) => onChange({ ...value, latch: e.target.value })}>
            <Radio.Button value={true} data-testid="hw-latch-yes">有</Radio.Button>
            <Radio.Button value={false} data-testid="hw-latch-no">无</Radio.Button>
          </Radio.Group>
          <How q="latch" />
        </div>
      )}
      {questions.includes('ff_signals') && (
        <div className="hw-q wide">
          <div className="hw-l">{Q_LABEL.ff_signals}</div>
          <Select mode="tags" value={value.ff_signals} disabled={disabled} style={{ minWidth: 200, width: '100%' }}
            placeholder="选择或输入信号名；都不是就留空" aria-label={Q_LABEL.ff_signals} data-testid="hw-ff-signals"
            options={candidates.map((c) => ({ value: c, label: c }))}
            onChange={(v) => onChange({ ...value, ff_signals: v })} />
          <How q="ff_signals" />
        </div>
      )}
    </div>
  )
}

export function HardwareCompare({ items, hardware, questions, code, drivers, outputs, onSelect, selected }: {
  items: EvalItem[] | null; hardware: Judge['hardware'] | null; questions: string[]
  code?: string; drivers?: Record<string, number[]>; outputs?: string[]
  onSelect?: (signal: string) => void; selected?: string | null
}) {
  const byQ = new Map((items ?? []).map((i) => [i.question, i]))
  const hw = hardware
  const fmt = (q: string, v: any) => {
    if (v === null || v === undefined) return '—'
    if (q === 'latch') return v ? '有' : '无'
    if (q === 'ff_signals') return null
    return String(v)
  }
  const actualOf = (q: string) => q === 'ff_count' ? hw?.ff_count : q === 'latch' ? (hw?.latch_signals ? hw.latch_signals.length > 0 : null) : hw?.ff_signals
  return (
    <div data-testid="hardware-compare">
      <div className="hw-grid">
        {questions.map((q) => {
          const it = byQ.get(q)
          const actual = actualOf(q)
          return (
            <div className="hw-q" key={q}>
              <div className="hw-l">{Q_LABEL[q]}</div>
              {q === 'ff_signals' ? (
                <div className="hw-v">
                  <div><span className="muted">你预测</span> {it ? <Chips names={it.value ?? []} actual={(actual as string[]) ?? []} /> : '—'}</div>
                  <div><span className="muted">实际</span> {actual ? <Chips names={actual as string[]} actual={actual as string[]} /> : '—'}</div>
                </div>
              ) : (
                <div className="hw-v">
                  <span className="muted">你预测</span> {it ? fmt(q, it.value) : '—'} · <span className="muted">实际</span> {fmt(q, actual)}
                </div>
              )}
              {it && <Mark ok={it.correct} />}
            </div>
          )
        })}
      </div>
      {hw && hw.latch_signals && hw.latch_signals.length > 0 &&
        <div className="hw-note warn">锁存器信号：{hw.latch_signals.join('、')}</div>}
      <div className="hw-note muted">以上由 Yosys 综合后统计{hw?.lut_count !== null && hw?.lut_count !== undefined ? `；另用了 ${hw.lut_count} 个查找表（LUT）` : ''}</div>
      {hw && code && <WhyList hardware={hw} code={code} drivers={drivers ?? {}} outputs={outputs ?? []}
        onSelect={onSelect} selected={selected ?? null} />}
    </div>
  )
}

/** 为什么：每个信号综合成了什么，和它在代码里的写法对应起来 */
export function explainSignals(hw: NonNullable<Judge['hardware']>, code: string, drivers: Record<string, number[]>,
  outputs: string[]): { signal: string; kind: 'ff' | 'latch' | 'comb'; width: number | null; lines: number[]; text: string }[] {
  const lines = code.split('\n')
  const widths = declWidths(code)
  const ff = new Set(hw.ff_signals ?? [])
  const latch = new Set(hw.latch_signals ?? [])
  const names = [...new Set([...ff, ...latch, ...outputs, ...Object.keys(drivers)])]
  const fmt = (ls: number[]) => ls.length ? `第 ${ls.join('、')} 行` : '代码里'
  return names.filter((n) => drivers[n]?.length || ff.has(n) || latch.has(n)).map((n) => {
    const ls = drivers[n] ?? []
    const w = widths[n] ?? null
    const how = blockKind(lines, ls[0])
    if (ff.has(n)) {
      return { signal: n, kind: 'ff' as const, width: w, lines: ls,
        text: `在${fmt(ls)}的 always @(posedge clk) 里赋值 → 每个时钟上升沿才更新一次、其余时间保持，综合成${w ? ` ${w} 个` : ''}触发器` }
    }
    if (latch.has(n)) {
      return { signal: n, kind: 'latch' as const, width: w, lines: ls,
        text: `在${fmt(ls)}的 always @(*) 里赋值，但有情况没给它赋值 → 电路只好记住旧值，综合成了锁存器（通常要改掉）` }
    }
    return { signal: n, kind: 'comb' as const, width: w, lines: ls,
      text: `由${fmt(ls)}的 ${how === 'assign' ? 'assign' : how === 'comb' ? 'always @(*)' : '组合逻辑'} 决定 → 输入一变就立刻跟着变，是组合逻辑，没有触发器` }
  })
}

function WhyList({ hardware, code, drivers, outputs, onSelect, selected }: {
  hardware: NonNullable<Judge['hardware']>; code: string; drivers: Record<string, number[]>; outputs: string[]
  onSelect?: (signal: string) => void; selected: string | null
}) {
  const rows = explainSignals(hardware, code, drivers, outputs)
  if (!rows.length) return null
  const ffBits = rows.filter((r) => r.kind === 'ff').reduce((s, r) => s + (r.width ?? 0), 0)
  const known = rows.filter((r) => r.kind === 'ff').every((r) => r.width !== null)
  return (
    <div className="hw-why" data-testid="hw-why">
      <div className="hw-why-t">为什么？每个信号和代码的对应关系{onSelect ? '（点信号名，代码里会高亮这几行）' : ''}</div>
      {rows.map((r) => (
        <div key={r.signal} className={`hw-why-row ${r.kind}`}>
          <button type="button" className={selected === r.signal ? 'sig-chip on' : 'sig-chip'} onClick={() => onSelect?.(r.signal)}
            disabled={!onSelect} data-testid={`why-${r.signal}`}>{r.signal}{r.width && r.width > 1 ? ` [${r.width - 1}:0]` : ''}</button>
          <span className={`kind ${r.kind}`}>{r.kind === 'ff' ? '触发器' : r.kind === 'latch' ? '锁存器' : '组合逻辑'}</span>
          <span>{r.text}</span>
        </div>
      ))}
      {known && hardware.ff_count !== null && ffBits !== hardware.ff_count && (
        <div className="hw-note muted">按位宽加起来是 {ffBits} 个，综合结果是 {hardware.ff_count} 个：综合工具会把一直不变、或者没被用到的位优化掉。</div>
      )}
    </div>
  )
}

/** 从声明里读出信号位宽：reg [3:0] q → 4；没写位宽 → 1 */
function declWidths(code: string): Record<string, number> {
  const clean = code.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/.*$/gm, '')
  const out: Record<string, number> = {}
  const re = /\b(?:input|output|inout|reg|wire)\b\s*(?:(?:wire|reg|signed)\s+)*(\[\s*(\d+)\s*:\s*(\d+)\s*\])?\s*([A-Za-z_][\w$]*(?:\s*,\s*[A-Za-z_][\w$]*)*)/g
  let m: RegExpExecArray | null
  while ((m = re.exec(clean))) {
    const w = m[1] ? Math.abs(Number(m[2]) - Number(m[3])) + 1 : 1
    for (const n of m[4].split(',').map((x) => x.trim())) {
      if (n && !['wire', 'reg', 'signed', 'input', 'output'].includes(n)) out[n] = w
    }
  }
  return out
}

/** 某一行属于哪种写法：assign / always @(*) / always @(posedge …) */
function blockKind(lines: string[], line: number | undefined): 'assign' | 'comb' | 'seq' | null {
  if (!line) return null
  if (/\bassign\b/.test(lines[line - 1] ?? '')) return 'assign'
  for (let i = line - 1; i >= 0; i--) {
    const t = lines[i] ?? ''
    if (/\balways\b/.test(t)) return /posedge|negedge/.test(t) ? 'seq' : 'comb'
    if (/\bendmodule\b|\bmodule\b/.test(t)) break
  }
  return null
}

function Chips({ names, actual }: { names: string[]; actual: string[] }) {
  if (!names.length) return <span className="muted">（无）</span>
  return <>{names.map((n) => <span key={n} className={`sig-chip ${actual.includes(n) ? '' : 'wrong'}`}>{n}</span>)}</>
}

/** 从代码里找出 reg 信号名，作为“哪些信号成了触发器”的候选 */
export function regCandidates(code: string): string[] {
  const clean = code.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/.*$/gm, '')
  const names = new Set<string>()
  const re = /\breg\b([^;)]*)/g
  let m: RegExpExecArray | null
  while ((m = re.exec(clean))) {
    re.lastIndex = m.index + 3            // 下一次从这个 reg 之后接着找，端口表里的多个 output reg 都能找到
    const seg = m[1].split(/\b(?:input|output|inout)\b/)[0].replace(/\[[^\]]*\]/g, ' ')
    for (const part of seg.split(',')) {
      const name = part.replace(/=.*$/, '').trim().replace(/^signed\s+/, '').match(/^[A-Za-z_][\w$]*/)?.[0]
      if (name && name !== 'signed') names.add(name)
    }
  }
  return [...names]
}
