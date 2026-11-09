// 提示阶梯（第 2 版）：1 级思路 → 2 级定位 → 3 级代码提示，每次只能解锁下一级；
// 4 级参考答案按解锁条件开放（backend/app/services/answer.py），由系统直接展示，不经过大模型
import { Button, Modal } from 'antd'
import { useState } from 'react'
import { ApiError, post } from '../api/client'
import type { AnswerStatus, Hint } from '../api/types'
import Markdown, { CodeBlock } from '../lib/markdown'

export const LEVELS = [
  { level: 1, name: '思路', desc: '这道题背后的概念和方向' },
  { level: 2, name: '定位', desc: '指出该看的周期、信号和代码行' },
  { level: 3, name: '代码提示', desc: '关键写法或带空的代码框架' },
]

export default function HintLadder({ hints, onRequest, loading, error, disabled, highlight }: {
  hints: Hint[]; onRequest: () => void; loading?: boolean; error?: string | null; disabled?: boolean
  highlight?: boolean
}) {
  const next = hints.length + 1
  return (
    <div className="ladder" data-testid="hint-ladder">
      {LEVELS.map(({ level, name, desc }) => {
        const h = hints.find((x) => x.level === level)
        if (h) {
          return (
            <div className="lv open" key={level} data-testid={`hint-${level}`}>
              <div className="lv-h"><span>{level} 级 · {name}</span><span className="chip">已查看</span></div>
              <div className="lv-msg"><Markdown text={h.message} /></div>
              {h.code ? <CodeBlock code={h.code} title="代码提示（____ 处由你来填）" /> : null}
              {h.question && <div className="q">{h.question}</div>}
            </div>
          )
        }
        return (
          <div className="lv" key={level}>
            <div className="lv-h"><span>{level} 级 · {name}</span>
              {level > next ? <span className="lock">解锁 {level - 1} 级后可用</span> : <span className="lock">{desc}</span>}
            </div>
            {level === next && (
              <>
                <Button size="small" style={{ marginTop: 8 }} onClick={onRequest} loading={loading} disabled={disabled}
                  className={highlight ? 'pulse' : undefined} data-testid="hint-request">再给我一点提示（{level} 级·{name}）</Button>
                {error && <div className="lock" style={{ marginTop: 6 }}>{error}</div>}
              </>
            )}
          </div>
        )
      })}
      <HintSourceNote hints={hints} />
    </div>
  )
}

/** 4 级：参考答案。第一次查看前先确认；看过之后随时可以再看 */
export function AnswerCard({ problemId, status, onChanged }: {
  problemId: string; status: AnswerStatus; onChanged: () => void
}) {
  const [code, setCode] = useState<string | null>(null)
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  if (!status.available) return null

  async function open() {
    setBusy(true)
    setErr(null)
    try {
      const r = await post<{ code: string; note: string }>(`/api/student/problems/${problemId}/answer`)
      setCode(r.code)
      setNote(r.note)
      onChanged()
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : '暂时打不开参考答案')
    } finally {
      setBusy(false)
    }
  }
  function ask() {
    if (status.revealed) { void open(); return }
    Modal.confirm({
      title: '确定要看参考答案吗？',
      content: '看过参考答案之后，这道题再提交的结果不计入掌握度。建议看懂之后关掉答案，自己重新写一遍。',
      okText: '看参考答案', cancelText: '我再试试',
      onOk: () => open(),
    })
  }
  return (
    <div className={status.unlocked ? 'lv answer open' : 'lv answer'} data-testid="answer-card">
      <div className="lv-h"><span>4 级 · 参考答案</span>
        {status.revealed && <span className="chip">已查看</span>}</div>
      <div className="lock" style={{ marginTop: 4 }}>{status.message}</div>
      {!status.unlocked && (
        <div className="answer-progress">
          <span className={status.failed >= status.fails_needed ? 'ok' : ''}>提交没通过 {Math.min(status.failed, status.fails_needed)}/{status.fails_needed} 次</span>
          <span className={status.code_hint_seen ? 'ok' : ''}>{status.code_hint_seen ? '✓' : '·'} 看过 3 级代码提示</span>
        </div>
      )}
      {status.unlocked && (
        <Button size="small" style={{ marginTop: 8 }} onClick={ask} loading={busy} data-testid="answer-open">
          {status.revealed ? '再看一次参考答案' : '查看参考答案'}</Button>
      )}
      {err && <div className="lock warn" style={{ marginTop: 6 }}>{err}</div>}
      <Modal open={code !== null} onCancel={() => setCode(null)} footer={<Button type="primary" onClick={() => setCode(null)}>看懂了，我自己写一遍</Button>}
        title="参考答案" width={760} data-testid="answer-modal">
        <p className="muted" style={{ marginBottom: 8 }}>{note}</p>
        {code !== null && <CodeBlock code={code} title="top_module.v（参考答案，注释里有思路）" />}
      </Modal>
    </div>
  )
}

// 大模型不可用时：“当前为简化提示，不影响仿真和判定”（docs/ui-design.md 第 7 节）
const UNAVAILABLE = new Set(['no_key', 'breaker_open', 'budget', 'error', 'invalid'])

function HintSourceNote({ hints }: { hints: Hint[] }) {
  const last = hints[hints.length - 1]
  if (!last) return <div className="lock">提示依据仿真和综合结果生成；3 级会给代码框架</div>
  if (last.source === 'llm') return <div className="lock" data-testid="hint-source">由 DeepSeek 根据仿真结果生成</div>
  if (last.fallback_reason && UNAVAILABLE.has(last.fallback_reason)) {
    return <div className="lock warn" data-testid="hint-source">当前为简化提示，不影响仿真和判定</div>
  }
  return <div className="lock" data-testid="hint-source">规则提示：由仿真和综合结果生成</div>
}
