// 硬件面板：触发器个数、锁存器、哪些信号成了触发器（你的预测 / 实际并排）
import { InputNumber, Radio, Select } from 'antd'
import type { EvalItem, Judge } from '../api/types'

export interface HardwareAnswers { ff_count: number | null; latch: boolean | null; ff_signals: string[] }

const Q_LABEL: Record<string, string> = {
  ff_count: '会综合出几个触发器', latch: '有没有锁存器', ff_signals: '哪些信号成了触发器',
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
        </div>
      )}
      {questions.includes('ff_signals') && (
        <div className="hw-q wide">
          <div className="hw-l">{Q_LABEL.ff_signals}</div>
          <Select mode="tags" value={value.ff_signals} disabled={disabled} style={{ minWidth: 200, width: '100%' }}
            placeholder="选择或输入信号名；都不是就留空" aria-label={Q_LABEL.ff_signals} data-testid="hw-ff-signals"
            options={candidates.map((c) => ({ value: c, label: c }))}
            onChange={(v) => onChange({ ...value, ff_signals: v })} />
        </div>
      )}
    </div>
  )
}

export function HardwareCompare({ items, hardware, questions }: {
  items: EvalItem[] | null; hardware: Judge['hardware'] | null; questions: string[]
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
    </div>
  )
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
