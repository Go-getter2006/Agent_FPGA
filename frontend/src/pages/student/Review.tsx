// S6 复习（/student/review）：预测类（波形 / 硬件）提交后立即对照；误区复盘（find_bug）看代码选出它的问题
import { Alert, Button } from 'antd'
import { useState } from 'react'
import { ApiError, post } from '../../api/client'
import { useInvalidate, useReview } from '../../api/hooks'
import type { Evaluation, ReviewData } from '../../api/types'
import { Empty, ErrorState, Loading } from '../../components/Common'
import { CodeBlock } from '../../lib/markdown'
import { HardwarePredict, regCandidates, type HardwareAnswers } from '../../components/HardwarePanel'
import WaveformView from '../../components/WaveformView'
import './Student.css'

export default function Review() {
  const q = useReview()
  if (q.isLoading) return <Loading />
  if (q.error || !q.data) return <ErrorState error={q.error} onRetry={() => q.refetch()} />
  const d = q.data
  return (
    <div className="page review" data-testid="review">
      <div className="page-h"><h1>复习</h1><span className="muted">今天还剩 {d.remaining_today} 条 · 每条 1–3 分钟</span></div>
      {d.items.length === 0 && <div className="card"><Empty title="今天没有要复习的">落在“会写但没把握”或“概念未通”的题，以及你踩过的坑，会在第二天出现在这里</Empty></div>}
      {d.items.map((item) => item.question.kind === 'find_bug'
        ? <FindBugCard key={item.id} item={item} />
        : <ReviewItemCard key={item.id} item={item} />)}
    </div>
  )
}

function ReviewItemCard({ item }: { item: ReviewData['items'][number] }) {
  const qn = item.question
  const invalidate = useInvalidate()
  const [pred, setPred] = useState<Record<string, string | null>>({})
  const [hw, setHw] = useState<HardwareAnswers>({ ff_count: null, latch: null, ff_signals: [] })
  const [result, setResult] = useState<{ correct: boolean; box: number; evaluation: Evaluation } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const cells = qn.predict_points.flatMap((p) => p.steps.map((s) => ({ signal: p.signal, step: s })))
  const ready = qn.kind === 'waveform' ? cells.every((c) => pred[`${c.signal}@${c.step}`]) : hw.ff_count !== null && hw.latch !== null
  const submit = async () => {
    setError(null)
    try {
      const body = qn.kind === 'waveform'
        ? { waveform: { cells: cells.map((c) => ({ ...c, value: pred[`${c.signal}@${c.step}`] })) } }
        : { hardware: hw }
      setResult(await post(`/api/student/review/${item.id}/answer`, body))
      void invalidate(['home'], ['report'])
    } catch (e) {
      setError(e instanceof ApiError ? e.message : '提交没有成功')
    }
  }
  const clocked = qn.skeleton.inputs.some((i) => i.name === 'rst')
  return (
    <div className="card" style={{ marginBottom: 16 }} data-testid={`review-item-${item.id}`}>
      <div className="card-h">{item.title} <small>{item.knowledge_point.name} · 第 {item.box} 轮 · {qn.kind === 'waveform' ? '预测波形' : '预测硬件'}</small></div>
      <div className="card-b review-body">
        <pre className="review-code" aria-label="要预测的代码">{qn.code.split('\n').map((l, i) => <div key={i}><span className="no">{i + 1}</span>{l}</div>)}</pre>
        <div style={{ minWidth: 0 }}>
          {qn.kind === 'waveform' ? (
            <WaveformView mode="predict" steps={qn.skeleton.steps} inputs={qn.skeleton.inputs} outputs={qn.skeleton.outputs}
              predictCells={cells} predicted={pred} clocked={clocked}
              onPredict={result ? undefined : (signal, s, v) => setPred((x) => ({ ...x, [`${signal}@${s}`]: v }))} />
          ) : (
            <HardwarePredict questions={qn.hardware_questions} value={hw} onChange={setHw} candidates={regCandidates(qn.code)} disabled={!!result} />
          )}
          {result && qn.kind === 'waveform' && (
            <div className="review-cells">{result.evaluation.waveform.cells.map((c) => (
              <span key={`${c.signal}${c.step}`} className={c.correct ? 'ok' : 'warn'}>{c.signal} 第 {c.step} 步：实际 {c.actual}，你预测 {c.value} {c.correct ? '✓' : '✗'}</span>
            ))}</div>
          )}
          {result && qn.kind === 'hardware' && (
            <div className="review-cells">{result.evaluation.hardware.items.map((it) => (
              <span key={it.question} className={it.correct ? 'ok' : 'warn'}>{it.question}：实际 {JSON.stringify(it.actual)}，你预测 {JSON.stringify(it.value)} {it.correct ? '✓' : '✗'}</span>
            ))}</div>
          )}
          {result && <Alert style={{ marginTop: 12 }} type={result.correct ? 'success' : 'warning'} showIcon
            message={result.correct ? `答对了，进入第 ${result.box} 轮` : '这次没对上，明天再来一次'} />}
          {error && <Alert style={{ marginTop: 12 }} type="warning" message={error} />}
          {!result && <Button type="primary" style={{ marginTop: 12 }} disabled={!ready} onClick={submit}>锁定我的预测</Button>}
        </div>
      </div>
    </div>
  )
}

/** 误区复盘：别的题里有同样问题的一段代码，选出它的问题；提交后给出答案和说明 */
function FindBugCard({ item }: { item: ReviewData['items'][number] }) {
  const qn = item.question
  const invalidate = useInvalidate()
  const [choice, setChoice] = useState<string | null>(null)
  const [result, setResult] = useState<{ correct: boolean; box: number
    evaluation: { answer: { code: string; label: string }[]; explain: string } } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const submit = async () => {
    setError(null)
    try {
      setResult(await post(`/api/student/review/${item.id}/answer`, { choice }))
      void invalidate(['home'], ['report'])
    } catch (e) {
      setError(e instanceof ApiError ? e.message : '提交没有成功')
    }
  }
  const right = new Set(result?.evaluation.answer.map((a) => a.code) ?? [])
  return (
    <div className="card" style={{ marginBottom: 16 }} data-testid={`review-item-${item.id}`}>
      <div className="card-h">误区复盘：这段代码有什么问题？ <small>来自「{item.title}」· 第 {item.box} 轮 · 你之前也遇到过这类问题</small></div>
      <div className="card-b review-body">
        <div style={{ minWidth: 0 }}>
          {qn.task && <p className="muted" style={{ fontSize: 13, marginBottom: 6 }}>这段代码想实现：{qn.task}</p>}
          <CodeBlock code={qn.code} title="同学写的 top_module.v" />
        </div>
        <div className="find-bug" data-testid="find-bug">
          <div className="opts-v">
            {(qn.options ?? []).map((o) => {
              const cls = result ? (right.has(o.code) ? 'opt right' : o.code === choice ? 'opt wrong' : 'opt') : choice === o.code ? 'opt on' : 'opt'
              return <button key={o.code} className={cls} disabled={!!result} onClick={() => setChoice(o.code)} data-testid="bug-option">{o.label}</button>
            })}
          </div>
          {result && (
            <Alert style={{ marginTop: 12 }} type={result.correct ? 'success' : 'warning'} showIcon
              message={result.correct ? `答对了，进入第 ${result.box} 轮` : `正确答案：${result.evaluation.answer.map((a) => a.label).join('；')}。明天再来一次`}
              description={result.evaluation.explain} />
          )}
          {error && <Alert style={{ marginTop: 12 }} type="warning" message={error} />}
          {!result && <Button type="primary" style={{ marginTop: 12 }} disabled={!choice} onClick={submit} data-testid="bug-submit">就是这个问题</Button>}
        </div>
      </div>
    </div>
  )
}
