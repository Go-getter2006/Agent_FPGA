// 新手入门：课程列表（/student/learn）和单节课（/student/learn/:id）
import { Button, Progress } from 'antd'
import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { GLOSSARY, Term } from '../../components/Glossary'
import { LESSONS, computeDemo, type Demo, type QuizQ } from '../../content/lessons'
import { reporter } from '../../lib/events'
import Markdown from '../../lib/markdown'
import './Learn.css'

// 学习进度只存在本浏览器里，用来显示“已学过”；研究用的记录是事件日志
const PROGRESS_KEY = 'learn.progress.v1'
function readProgress(): Record<string, { opened?: boolean; quiz?: number }> {
  try { return JSON.parse(window.localStorage.getItem(PROGRESS_KEY) ?? '{}') } catch { return {} }
}
function writeProgress(id: string, patch: { opened?: boolean; quiz?: number }) {
  try {
    const all = readProgress()
    window.localStorage.setItem(PROGRESS_KEY, JSON.stringify({ ...all, [id]: { ...all[id], ...patch } }))
  } catch { /* 隐私模式等：忽略 */ }
}

export function LearnIndex() {
  const progress = readProgress()
  const done = LESSONS.filter((l) => progress[l.id]?.opened).length
  return (
    <div className="page learn" data-testid="learn">
      <div className="page-h"><h1>新手入门</h1><span className="muted">没学过 Verilog 和 FPGA？从这里开始，6 节短课，每节 5–10 分钟</span></div>
      <div className="card learn-intro">
        <div className="card-b">
          <p>学完一节，就去做对应的<b>入门题</b>：先读懂代码、预测波形，再自己动手改、动手写。做题时遇到不懂的词，鼠标移到带虚线的词上就有解释，例如 <Term k="触发器" />、<Term k="仿真" />、<Term k="综合" />。</p>
          <Progress percent={Math.round((done / LESSONS.length) * 100)} format={() => `已学 ${done}/${LESSONS.length} 节`} />
        </div>
      </div>
      <div className="lesson-list">
        {LESSONS.map((l, i) => (
          <Link key={l.id} to={`/student/learn/${l.id}`} className="card lesson-item" data-testid={`lesson-${l.id}`}>
            <div className="num">{i + 1}</div>
            <div className="body">
              <div className="t">{l.title.replace(/^第 \d 课 · /, '')}</div>
              <div className="muted">{l.summary}</div>
              {l.practice && <div className="prac">练习：{l.practice.title}</div>}
            </div>
            <div className="meta">{progress[l.id]?.opened ? <span className="chip green">已学</span> : <span className="muted">{l.minutes} 分钟</span>}</div>
          </Link>
        ))}
      </div>
      <div className="card" style={{ marginTop: 16 }}>
        <div className="card-h">术语表</div>
        <div className="card-b glossary">
          {Object.entries(GLOSSARY).map(([k, g]) => (
            <div key={k} className="g-item"><b>{k}</b><span>{g.short}。{g.long}</span></div>
          ))}
        </div>
      </div>
    </div>
  )
}

export function LessonPage() {
  const { id = '' } = useParams()
  const navigate = useNavigate()
  const idx = LESSONS.findIndex((l) => l.id === id)
  const lesson = LESSONS[idx]
  useEffect(() => {
    if (!lesson) return
    writeProgress(lesson.id, { opened: true })
    reporter.track('lesson.open', { payload: { lesson: lesson.id } })
    window.scrollTo(0, 0)
  }, [lesson?.id]) // eslint-disable-line react-hooks/exhaustive-deps
  if (!lesson) return <div className="page"><p>找不到这节课。<Link to="/student/learn">回到课程列表</Link></p></div>
  const prev = LESSONS[idx - 1]
  const next = LESSONS[idx + 1]
  return (
    <div className="page learn lesson" data-testid="lesson">
      <div className="crumb"><Link to="/student/learn">← 新手入门</Link></div>
      <h1>{lesson.title}</h1>
      <p className="muted">{lesson.summary} · 约 {lesson.minutes} 分钟</p>
      {lesson.sections.map((s, i) => (
        <div key={i} className="card lesson-sec">
          <div className="card-b">
            {s.kind === 'md' && <Markdown text={s.text} />}
            {s.kind === 'demo' && <DemoView demo={s.demo} />}
            {s.kind === 'quiz' && <Quiz lessonId={lesson.id} items={s.quiz} />}
          </div>
        </div>
      ))}
      {lesson.practice && (
        <div className="card practice" data-testid="lesson-practice">
          <div className="card-b">
            <div><b>动手练习：{lesson.practice.title}</b><div className="muted">{lesson.practice.why}</div></div>
            <Button type="primary" onClick={() => navigate(`/student/problems/${lesson.practice!.problemId}`)}>去做这道题</Button>
          </div>
        </div>
      )}
      <div className="lesson-nav">
        {prev ? <Link to={`/student/learn/${prev.id}`}>← {prev.title}</Link> : <span />}
        {next ? <Link to={`/student/learn/${next.id}`} data-testid="lesson-next">{next.title} →</Link> : <Link to="/student/problems">去题目列表 →</Link>}
      </div>
    </div>
  )
}

function Quiz({ lessonId, items }: { lessonId: string; items: QuizQ[] }) {
  const [picked, setPicked] = useState<Record<number, number>>({})
  const correct = items.filter((q, i) => picked[i] === q.answer).length
  useEffect(() => {
    if (Object.keys(picked).length === items.length) writeProgress(lessonId, { quiz: correct })
  }, [picked]) // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <div className="quiz" data-testid="quiz">
      <h4 className="md-h">小测：答完马上看解析</h4>
      {items.map((q, i) => (
        <div key={i} className="quiz-q">
          <div className="qq">{i + 1}. <Markdown text={q.q} /></div>
          <div className="opts">
            {q.options.map((o, j) => {
              const chosen = picked[i] === j
              const show = picked[i] !== undefined
              const cls = show && j === q.answer ? 'opt right' : chosen ? 'opt wrong' : 'opt'
              return (
                <button key={j} className={cls} disabled={show} data-testid="quiz-option" onClick={() => {
                  setPicked((p) => ({ ...p, [i]: j }))
                  reporter.track('lesson.quiz', { payload: { lesson: lessonId, question: i, choice: j, correct: j === q.answer } })
                }}><code>{o}</code></button>
              )
            })}
          </div>
          {picked[i] !== undefined && (
            <div className={picked[i] === q.answer ? 'explain ok' : 'explain bad'}>
              {picked[i] === q.answer ? '✓ 答对了。' : '✗ 再想想：'}{q.explain}</div>
          )}
        </div>
      ))}
    </div>
  )
}

const CW = 44
const RH = 30
const NW = 56

/** 可以点的电路示意（SVG）：点输入格子切换 0/1，输出立刻按电路重新算 */
function DemoView({ demo }: { demo: Demo }) {
  const steps = demo.inputs[0].values.length
  const [vals, setVals] = useState<Record<string, number[]>>(() => Object.fromEntries(demo.inputs.map((x) => [x.name, [...x.values]])))
  const outs = useMemo(() => computeDemo(demo.compute, vals, steps), [vals, demo.compute, steps])
  const rows: { name: string; kind: 'clk' | 'in' | 'out'; values: (number | string)[] }[] = [
    ...(demo.clocked ? [{ name: 'clk', kind: 'clk' as const, values: [] }] : []),
    ...demo.inputs.map((x) => ({ name: x.name, kind: 'in' as const, values: vals[x.name] })),
    ...demo.outputs.map((n) => ({ name: n, kind: 'out' as const, values: outs[n] ?? [] })),
  ]
  const width = NW + steps * CW + 8
  const height = 22 + rows.length * RH
  const toggle = (name: string, i: number) => setVals((v) => ({ ...v, [name]: v[name].map((x, j) => (j === i ? (x ? 0 : 1) : x)) }))
  return (
    <div className="demo" data-testid="demo">
      <h4 className="md-h">{demo.title}</h4>
      <div className="demo-scroll">
        <svg width={width} height={height} role="img" aria-label={demo.title}>
          {Array.from({ length: steps }, (_, i) => (
            <g key={i}>
              <text x={NW + i * CW + CW / 2} y={14} textAnchor="middle" fontSize={11} fill="#6B7280">{i}</text>
              <line x1={NW + i * CW} x2={NW + i * CW} y1={20} y2={height} stroke="#EEF0F3" />
            </g>
          ))}
          {rows.map((r, ri) => {
            const y0 = 22 + ri * RH
            const hi = y0 + 6
            const lo = y0 + RH - 6
            return (
              <g key={r.name}>
                <text x={NW - 8} y={y0 + RH / 2 + 4} textAnchor="end" fontSize={12} fontFamily="var(--mono)"
                  fill={r.kind === 'out' ? '#1D4ED8' : '#111827'} fontWeight={r.kind === 'out' ? 700 : 400}>{r.name}</text>
                {r.kind === 'clk' && Array.from({ length: steps }, (_, i) => {
                  const x = NW + i * CW
                  return <path key={i} d={`M${x} ${lo} L${x + CW * 0.25} ${lo} L${x + CW * 0.25} ${hi} L${x + CW * 0.75} ${hi} L${x + CW * 0.75} ${lo} L${x + CW} ${lo}`}
                    fill="none" stroke="#9CA3AF" strokeWidth={1.5} />
                })}
                {r.kind !== 'clk' && r.values.map((v, i) => {
                  const x = NW + i * CW
                  const isBit = v === 0 || v === 1
                  const multi = r.name === 'cnt'
                  return (
                    <g key={i} onClick={r.kind === 'in' ? () => toggle(r.name, i) : undefined}
                      style={{ cursor: r.kind === 'in' ? 'pointer' : 'default' }} data-testid={r.kind === 'in' ? 'demo-cell' : undefined}>
                      <rect x={x + 1} y={y0 + 3} width={CW - 2} height={RH - 6} rx={3}
                        fill={r.kind === 'in' ? '#F8FAFF' : v === 'x' ? '#FEF2F2' : '#F0F9FF'} stroke={r.kind === 'in' ? '#E0E7FF' : 'transparent'} />
                      {isBit && !multi
                        ? <line x1={x + 2} x2={x + CW - 2} y1={v ? hi : lo} y2={v ? hi : lo} stroke={r.kind === 'out' ? '#1D4ED8' : '#374151'} strokeWidth={2} />
                        : null}
                      <text x={x + CW / 2} y={y0 + RH / 2 + 4} textAnchor="middle" fontSize={11} fontFamily="var(--mono)"
                        fill={v === 'x' ? '#B91C1C' : '#6B7280'}>{isBit && !multi ? '' : String(v)}</text>
                    </g>
                  )
                })}
              </g>
            )
          })}
        </svg>
      </div>
      <div className="demo-note">{demo.note}<span className="muted">（这是帮助理解的动画示意；做题时的波形才是 iverilog 的真实仿真结果）</span></div>
    </div>
  )
}
