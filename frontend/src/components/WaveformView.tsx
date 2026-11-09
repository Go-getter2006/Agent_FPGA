// 自研 SVG 波形组件（docs/ui-design.md 第 6 节）。数据只来自裁判 JSON 的 sim.trace，前端不推算任何值
import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react'
import { binToHex } from '../lib/format'
import type { TraceRow } from '../api/types'

export type WaveMode = 'predict' | 'result' | 'compare' | 'diff'
type RowKind = 'clock' | 'input' | 'expected' | 'actual' | 'predict' | 'base' | 'variant'

export interface WaveSignal { name: string; width: number }

export interface WaveformProps {
  mode: WaveMode
  steps: number[]
  inputs: (WaveSignal & { values: string[] })[]
  outputs: WaveSignal[]
  /** 学生电路（result / compare）或 diff 的第二条轨迹 */
  actual?: TraceRow[]
  /** 参考答案（compare）或 diff 的第一条轨迹 */
  expected?: TraceRow[]
  diffLabels?: [string, string]
  /** 预测格：predict 模式下可编辑；compare 模式下显示徽标 */
  predictCells?: { signal: string; step: number }[]
  predicted?: Record<string, string | null>       // key = `${signal}@${step}`
  onPredict?: (signal: string, step: number, value: string | null) => void
  clocked?: boolean
  firstMismatchStep?: number | null
  linkedSignals?: string[]
  pickedCell?: { signal: string; step: number } | null
  onCellClick?: (signal: string, step: number, row: RowKind, isMismatch: boolean) => void
  radix?: 'hex' | 'bin'
}

const NAME_W = 140
const CW = 44
const RH = 32
const HEAD = 22
const BADGE_GAP = 14     // 有预测徽标的行下方留出写“你预测 x”的空间
const FOOT = 30

const key = (signal: string, step: number) => `${signal}@${step}`

interface Row {
  id: string
  kind: RowKind
  name: string
  note?: string
  width: number
  values: (string | null)[]
  compareTo?: (string | null)[]   // 与这一行比较，不同的格子标红
  badges?: boolean
  y: number
  h: number
}

function valuesOf(trace: TraceRow[] | undefined, steps: number[], name: string): (string | null)[] {
  const map = new Map((trace ?? []).map((r) => [r.step, r.outputs[name] ?? r.inputs[name]]))
  return steps.map((s) => map.get(s) ?? null)
}

function display(v: string, width: number, radix: 'hex' | 'bin') {
  if (width === 1 || radix === 'bin') return v
  return binToHex(v)
}

export function normalizePredictInput(raw: string, width: number): string | null {
  const t = raw.trim().toLowerCase().replace(/_/g, '')
  if (!t) return null
  let n: number
  if (/^(0x|h|'h)[0-9a-f]+$/.test(t)) n = parseInt(t.replace(/^(0x|'h|h)/, ''), 16)
  else if (/^(0b|b|'b)?[01]+$/.test(t)) n = parseInt(t.replace(/^(0b|'b|b)/, ''), 2)
  else return null
  if (!Number.isFinite(n) || n >= 2 ** width) return null
  return n.toString(2).padStart(width, '0')
}

export default function WaveformView(props: WaveformProps) {
  const {
    mode, steps, inputs, outputs, actual, expected, predictCells = [], predicted = {}, onPredict,
    clocked = false, firstMismatchStep = null, linkedSignals = [], pickedCell = null, onCellClick,
    radix = 'hex', diffLabels = ['原顺序', '打乱后'],
  } = props
  const [focus, setFocus] = useState<string | null>(null)
  const [editing, setEditing] = useState<{ signal: string; step: number; text: string; error?: string } | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  const predictSet = useMemo(() => new Set(predictCells.map((c) => key(c.signal, c.step))), [predictCells])

  const rows = useMemo<Row[]>(() => {
    const out: Omit<Row, 'y' | 'h'>[] = []
    if (clocked) out.push({ id: 'clk', kind: 'clock', name: 'clk', width: 1, values: steps.map(() => null) })
    for (const sig of inputs) {
      out.push({ id: `in-${sig.name}`, kind: 'input', name: sig.name, width: sig.width, values: sig.values })
    }
    for (const sig of outputs) {
      if (mode === 'predict') {
        out.push({ id: `p-${sig.name}`, kind: 'predict', name: sig.name, width: sig.width,
          values: steps.map((s) => predicted[key(sig.name, s)] ?? null) })
      } else if (mode === 'result') {
        out.push({ id: `a-${sig.name}`, kind: 'actual', name: sig.name, width: sig.width,
          values: valuesOf(actual, steps, sig.name) })
      } else {
        const first = valuesOf(expected, steps, sig.name)
        const second = valuesOf(actual, steps, sig.name)
        const isCompare = mode === 'compare'
        out.push({ id: `e-${sig.name}`, kind: isCompare ? 'expected' : 'base', name: sig.name, width: sig.width,
          note: isCompare ? '期望' : diffLabels[0], values: first })
        out.push({ id: `a-${sig.name}`, kind: isCompare ? 'actual' : 'variant', name: sig.name, width: sig.width,
          note: isCompare ? '你的电路' : diffLabels[1], values: second, compareTo: first,
          badges: isCompare && predictCells.some((c) => c.signal === sig.name) })
      }
    }
    let y = HEAD
    return out.map((r) => {
      const h = RH + (r.badges ? BADGE_GAP : 0)
      const row = { ...r, y, h }
      y += h
      return row
    })
  }, [mode, steps, inputs, outputs, actual, expected, predicted, predictCells, clocked, diffLabels])

  const height = (rows.length ? rows[rows.length - 1].y + rows[rows.length - 1].h : HEAD) + FOOT
  const width = steps.length * CW
  const stepIndex = (s: number) => steps.indexOf(s)

  // 第一个对不上的周期滚动到可见位置
  useEffect(() => {
    if (firstMismatchStep === null || !scrollRef.current) return
    const i = stepIndex(firstMismatchStep)
    if (i < 0) return
    const el = scrollRef.current
    const x = i * CW
    if (x < el.scrollLeft || x > el.scrollLeft + el.clientWidth - CW * 2) el.scrollLeft = Math.max(0, x - CW * 3)
  }, [firstMismatchStep, steps]) // eslint-disable-line react-hooks/exhaustive-deps

  const predictOrder = useMemo(() => {
    const order: { signal: string; step: number }[] = []
    for (const sig of outputs) for (const s of steps) if (predictSet.has(key(sig.name, s))) order.push({ signal: sig.name, step: s })
    return order
  }, [outputs, steps, predictSet])

  function cyclePredict(signal: string, step: number, w: number) {
    if (!onPredict) return
    if (w === 1) {
      const cur = predicted[key(signal, step)]
      onPredict(signal, step, cur === '0' ? '1' : '0')
    } else {
      const cur = predicted[key(signal, step)]
      setEditing({ signal, step, text: cur ? (radix === 'hex' ? `0x${binToHex(cur)}` : cur) : '' })
    }
  }

  function onPredictKey(e: KeyboardEvent, signal: string, step: number, w: number) {
    const idx = predictOrder.findIndex((c) => c.signal === signal && c.step === step)
    const move = (to: number) => {
      const next = predictOrder[Math.max(0, Math.min(predictOrder.length - 1, to))]
      if (next) setFocus(key(next.signal, next.step))
    }
    if (e.key === 'ArrowRight') { e.preventDefault(); move(idx + 1) }
    else if (e.key === 'ArrowLeft') { e.preventDefault(); move(idx - 1) }
    else if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault()
      const sigs = [...new Set(predictOrder.map((c) => c.signal))]
      const si = sigs.indexOf(signal) + (e.key === 'ArrowDown' ? 1 : -1)
      const target = predictOrder.find((c) => c.signal === sigs[si])
      if (target) setFocus(key(target.signal, target.step))
    } else if (e.key === ' ' && w === 1) { e.preventDefault(); cyclePredict(signal, step, w) }
    else if (e.key === 'Enter') { e.preventDefault(); cyclePredict(signal, step, w) }
    else if (w === 1 && (e.key === '0' || e.key === '1')) { e.preventDefault(); onPredict?.(signal, step, e.key) }
  }

  // 聚焦到当前格（roving tabindex）
  const timelineRef = useRef<SVGSVGElement>(null)
  useEffect(() => {
    if (!focus || !timelineRef.current) return
    const el = timelineRef.current.querySelector<SVGGElement>(`[data-cell="${CSS.escape(focus)}"]`)
    el?.focus()
  }, [focus])

  function commitEdit() {
    if (!editing) return
    const sig = outputs.find((o) => o.name === editing.signal)
    const v = normalizePredictInput(editing.text, sig?.width ?? 1)
    if (v === null) { setEditing({ ...editing, error: '用二进制（如 0101）或 0x 开头的十六进制' }); return }
    onPredict?.(editing.signal, editing.step, v)
    setEditing(null)
    setFocus(key(editing.signal, editing.step))
  }

  const fmLine = firstMismatchStep !== null && stepIndex(firstMismatchStep) >= 0 ? stepIndex(firstMismatchStep) * CW : null
  const lastRowBottom = rows.length ? rows[rows.length - 1].y + rows[rows.length - 1].h : HEAD

  return (
    <div className="wave" style={{ display: 'flex', position: 'relative', fontFamily: 'var(--mono)' }}>
      {/* 左侧信号名列：140px，等宽字体右对齐 */}
      <svg width={NAME_W} height={height} style={{ flex: 'none' }} aria-hidden="true">
        <text x={8} y={14} fontSize={11} fill="var(--c-text-2)" fontFamily="var(--font)">STEP</text>
        {rows.map((r) => {
          const linked = linkedSignals.includes(r.name) && r.kind !== 'clock'
          const mid = r.y + RH / 2
          return (
            <g key={r.id}>
              {linked && <rect x={2} y={r.y + 4} width={NAME_W - 8} height={RH - 8} rx={4} fill="var(--c-link)" />}
              {r.note && <text x={8} y={mid + 1} dominantBaseline="middle" fontSize={10.5} fill="var(--c-text-2)" fontFamily="var(--font)">{r.note}</text>}
              <text x={NAME_W - 12} y={mid + 1} textAnchor="end" dominantBaseline="middle" fontSize={12.5}
                fontWeight={600} fill="var(--c-text)">{r.name}</text>
            </g>
          )
        })}
      </svg>
      <div ref={scrollRef} style={{ overflowX: 'auto', overflowY: 'hidden', flex: 1, minWidth: 0 }}
        data-testid="wave-scroll">
        <svg ref={timelineRef} width={Math.max(width, 1)} height={height} role="group"
          aria-label={mode === 'predict' ? '波形预测' : mode === 'compare' ? '波形对照' : '波形'}>
          {steps.map((s, i) => (
            <text key={`h${s}`} x={i * CW + CW / 2} y={14} textAnchor="middle" fontSize={11} fill="var(--c-text-2)">{s}</text>
          ))}
          {steps.map((s, i) => (
            <line key={`g${s}`} x1={i * CW} y1={HEAD - 2} x2={i * CW} y2={lastRowBottom} stroke="#F1F2F4" />
          ))}
          {rows.map((r) => (
            <g key={r.id}>
              {linkedSignals.includes(r.name) && r.kind !== 'clock' &&
                <rect x={0} y={r.y + 2} width={width} height={RH - 4} fill="var(--c-link)" opacity={0.35} />}
              <RowCells row={r} steps={steps} radix={radix} predictSet={predictSet} predicted={predicted}
                focus={focus} pickedCell={pickedCell} mode={mode}
                onFocusCell={setFocus}
                onActivate={(signal, step) => {
                  if (r.kind === 'predict') cyclePredict(signal, step, r.width)
                }}
                onKey={onPredictKey}
                onCellClick={onCellClick} />
            </g>
          ))}
          {fmLine !== null && (
            <g data-testid="first-mismatch">
              <line x1={fmLine} y1={HEAD - 4} x2={fmLine} y2={lastRowBottom + 6} stroke="var(--c-error)" strokeWidth={2} />
              <rect x={fmLine + 2} y={lastRowBottom + 6} width={124} height={20} rx={4} fill="var(--c-error)" />
              <text x={fmLine + 64} y={lastRowBottom + 17} textAnchor="middle" dominantBaseline="middle" fontSize={11}
                fill="#fff" fontWeight={600} fontFamily="var(--font)">第一个对不上的周期</text>
            </g>
          )}
        </svg>
      </div>
      {editing && (() => {
        const r = rows.find((x) => x.kind === 'predict' && x.name === editing.signal)
        const i = stepIndex(editing.step)
        if (!r || i < 0) return null
        const left = NAME_W + i * CW - (scrollRef.current?.scrollLeft ?? 0)
        return (
          <div style={{ position: 'absolute', left, top: r.y + RH, zIndex: 5, background: '#fff', padding: 6,
            borderRadius: 6, boxShadow: 'var(--shadow-pop)', width: 180, fontFamily: 'var(--font)' }}>
            <input autoFocus aria-label={`${editing.signal} 第 ${editing.step} 步的预测值`} value={editing.text}
              onChange={(e) => setEditing({ ...editing, text: e.target.value, error: undefined })}
              onKeyDown={(e) => { if (e.key === 'Enter') commitEdit(); if (e.key === 'Escape') setEditing(null) }}
              placeholder="如 0101 或 0x5" style={{ width: '100%', height: 28, border: '1px solid var(--c-primary)',
                borderRadius: 6, padding: '0 8px', fontFamily: 'var(--mono)' }} />
            {editing.error && <div style={{ color: 'var(--c-error)', fontSize: 12, marginTop: 4 }}>{editing.error}</div>}
            <div style={{ display: 'flex', gap: 6, marginTop: 6 }}>
              <button type="button" onClick={commitEdit} className="wave-btn primary">确定</button>
              <button type="button" onClick={() => setEditing(null)} className="wave-btn">取消</button>
            </div>
          </div>
        )
      })()}
    </div>
  )
}

interface RowCellsProps {
  row: Row
  steps: number[]
  radix: 'hex' | 'bin'
  mode: WaveMode
  predictSet: Set<string>
  predicted: Record<string, string | null>
  focus: string | null
  pickedCell: { signal: string; step: number } | null
  onFocusCell: (k: string) => void
  onActivate: (signal: string, step: number) => void
  onKey: (e: KeyboardEvent, signal: string, step: number, w: number) => void
  onCellClick?: WaveformProps['onCellClick']
}

function RowCells({ row, steps, radix, mode, predictSet, predicted, focus, pickedCell, onFocusCell, onActivate,
  onKey, onCellClick }: RowCellsProps) {
  const top = row.y
  const hi = top + 8
  const lo = top + RH - 8
  const mid = (hi + lo) / 2
  const parts: JSX.Element[] = []

  if (row.kind === 'clock') {
    let d = ''
    steps.forEach((_, i) => {
      const x = i * CW
      d += `${i === 0 ? `M${x},${lo}` : ` L${x},${lo}`} L${x},${hi} L${x + CW / 2},${hi} L${x + CW / 2},${lo} L${x + CW},${lo}`
      parts.push(<path key={`ar${i}`} d={`M${x - 3},${hi + 6} L${x},${hi} L${x + 3},${hi + 6}`} fill="none"
        stroke="var(--c-text)" strokeWidth={1.2} />)
    })
    parts.push(<path key="clk" d={d} fill="none" stroke="var(--c-text)" strokeWidth={1.5} />)
    return <>{parts}</>
  }

  // 与比较行不同的格子：浅红底红框
  row.values.forEach((v, i) => {
    if (row.compareTo && row.compareTo[i] !== null && v !== row.compareTo[i]) {
      parts.push(<rect key={`mm${i}`} x={i * CW + 1} y={top + 3} width={CW - 2} height={RH - 6} rx={3}
        fill="var(--c-error-bg)" stroke="var(--c-error)" strokeWidth={1} />)
    }
  })

  if (row.kind === 'predict') {
    steps.forEach((s, i) => {
      const k = key(row.name, s)
      if (!predictSet.has(k)) return
      const v = predicted[k]
      const focused = focus === k
      parts.push(
        <g key={`pc${s}`} data-cell={k} data-testid={`predict-${row.name}-${s}`} tabIndex={focused || (!focus && i === 0) ? 0 : -1}
          role="button" aria-label={`${row.name}，第 ${s} 步，${v ? `你的预测 ${v}` : '待预测'}`}
          onFocus={() => onFocusCell(k)} onClick={() => { onFocusCell(k); onActivate(row.name, s) }}
          onKeyDown={(e) => onKey(e, row.name, s, row.width)} style={{ cursor: 'pointer', outline: 'none' }}>
          <rect x={i * CW + 3} y={top + 4} width={CW - 6} height={RH - 8} rx={4}
            fill={v ? 'var(--c-primary-bg)' : '#fff'} stroke="var(--c-primary)"
            strokeWidth={focused ? 2 : 1} strokeDasharray={focused ? undefined : '4 3'} />
          <text x={i * CW + CW / 2} y={mid + 1} textAnchor="middle" dominantBaseline="middle"
            fontSize={v ? 12 : 13} fontWeight={600} fill={v ? 'var(--c-primary)' : 'var(--c-text-2)'}>
            {v ? display(v, row.width, radix) : '?'}
          </text>
        </g>,
      )
    })
    return <>{parts}</>
  }

  // 单比特：折线；总线：六边形值框
  if (row.width === 1) {
    let d = ''
    let pen = false
    row.values.forEach((v, i) => {
      const x = i * CW
      if (v === '1' || v === '0') {
        const y = v === '1' ? hi : lo
        d += `${pen ? ' L' : ' M'}${x},${y} L${x + CW},${y}`
        pen = true
      } else {
        pen = false
        if (v === 'x') parts.push(<XCell key={`x${i}`} x={x} top={top} />)
        if (v === 'z') parts.push(<line key={`z${i}`} x1={x} y1={mid} x2={x + CW} y2={mid} stroke="#9CA3AF" strokeDasharray="3 3" strokeWidth={1.5} />)
      }
    })
    if (d) parts.push(<path key="bit" d={d.trim()} fill="none" stroke="var(--c-text)" strokeWidth={1.5} />)
  } else {
    let start = 0
    for (let i = 1; i <= row.values.length; i++) {
      if (i === row.values.length || row.values[i] !== row.values[start]) {
        const v = row.values[start]
        const xa = start * CW + 1
        const xb = i * CW - 1
        if (v !== null && /[xz]/.test(v)) {
          for (let j = start; j < i; j++) parts.push(<XCell key={`bx${j}`} x={j * CW} top={top} />)
        } else if (v !== null) {
          const k = 5
          parts.push(<path key={`bus${start}`} d={`M${xa},${mid} L${xa + k},${hi} L${xb - k},${hi} L${xb},${mid} L${xb - k},${lo} L${xa + k},${lo} Z`}
            fill="var(--c-primary-bg)" stroke="#6366F1" strokeWidth={1} />)
          parts.push(<text key={`bt${start}`} x={(xa + xb) / 2} y={mid + 1} textAnchor="middle" dominantBaseline="middle"
            fontSize={11.5} fill="#3730A3">{display(v, row.width, radix)}</text>)
        }
        start = i
      }
    }
  }

  // 可点击的透明格子（探究：点出第一个对不上的格子；联动：点格子高亮代码行）
  steps.forEach((s, i) => {
    const v = row.values[i]
    const isMismatch = !!row.compareTo && row.compareTo[i] !== null && v !== row.compareTo[i]
    const picked = pickedCell && pickedCell.signal === row.name && pickedCell.step === s && (row.kind === 'actual' || row.kind === 'variant')
    const pk = key(row.name, s)
    const pred = row.badges && predictSet.has(pk) ? predicted[pk] : undefined
    const predOk = pred !== undefined && pred !== null ? pred === v : null
    const label = [`${row.name}`, `第 ${s} 步`, row.note ?? '', `值 ${v ?? '无'}`,
      pred ? `你的预测 ${pred}` : '', isMismatch ? '对不上' : (row.compareTo ? '对得上' : ''),
      predOk === null ? '' : (predOk ? '预测对' : '预测没对上')].filter(Boolean).join('，')
    parts.push(
      <rect key={`hit${s}`} x={i * CW} y={top} width={CW} height={RH} fill="transparent"
        data-testid={`cell-${row.kind}-${row.name}-${s}`} aria-label={label} role={onCellClick ? 'button' : undefined}
        style={{ cursor: onCellClick ? 'pointer' : 'default' }}
        onClick={() => onCellClick?.(row.name, s, row.kind, isMismatch)} />,
    )
    if (picked) {
      parts.push(<rect key={`pick${s}`} x={i * CW + 1} y={top + 2} width={CW - 2} height={RH - 4} rx={4} fill="none"
        stroke="var(--c-primary)" strokeWidth={2} pointerEvents="none" />)
    }
    if (predOk !== null && mode === 'compare') {
      const cx = i * CW + CW - 8
      const cy = top + 8
      parts.push(
        <g key={`badge${s}`} pointerEvents="none">
          <circle cx={cx} cy={cy} r={7} fill={predOk ? 'var(--c-success)' : 'var(--c-warning)'} />
          <text x={cx} y={cy + 0.5} textAnchor="middle" dominantBaseline="middle" fontSize={9} fill="#fff" fontWeight={700}>
            {predOk ? '✓' : '✗'}
          </text>
          {!predOk && <text x={i * CW + CW / 2} y={top + RH + 10} textAnchor="middle" fontSize={10.5}
            fill="var(--c-warning)" fontWeight={600} fontFamily="var(--font)">你预测 {display(pred!, row.width, radix)}</text>}
        </g>,
      )
    }
  })
  return <>{parts}</>
}

function XCell({ x, top }: { x: number; top: number }) {
  const lines: JSX.Element[] = []
  for (let k = 0; k < 4; k++) {
    const x0 = x + 4 + k * 10
    lines.push(<line key={k} x1={x0} y1={top + RH - 8} x2={x0 + 8} y2={top + 8} stroke="var(--c-error)" strokeWidth={1.2} />)
  }
  return <g aria-hidden="true">{lines}<rect x={x + 1} y={top + 8} width={CW - 2} height={RH - 16} fill="none" stroke="var(--c-error)" strokeWidth={0.8} /></g>
}
