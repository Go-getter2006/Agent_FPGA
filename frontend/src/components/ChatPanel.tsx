// 助教对话（docs/pages.md S4 助教面板）：流式输出；学生消息靠右，助教消息靠左；不渲染代码块
import { useQuery } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { get } from '../api/client'
import type { ChatMessage } from '../api/types'

interface ChatData { session_id: number; enabled: boolean; messages: ChatMessage[] }

/** 解析 SSE 文本块里的 data: 行；返回解析出的事件和剩余未完成的文本 */
export function parseSse(buffer: string): { events: Record<string, any>[]; rest: string } {
  const parts = buffer.split('\n\n')
  const rest = parts.pop() ?? ''
  const events = parts.flatMap((block) => block.split('\n').filter((l) => l.startsWith('data: '))
    .map((l) => { try { return JSON.parse(l.slice(6)) } catch { return null } }).filter(Boolean))
  return { events, rest }
}

export default function ChatPanel({ problemId, attemptId, enabled = true }: {
  problemId: string; attemptId?: number | null; enabled?: boolean
}) {
  const q = useQuery({ queryKey: ['chat', problemId], queryFn: () => get<ChatData>(`/api/student/problems/${problemId}/chat`) })
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [simplified, setSimplified] = useState(false)
  const box = useRef<HTMLDivElement>(null)

  useEffect(() => { if (q.data) setMessages(q.data.messages) }, [q.data])
  useEffect(() => { box.current?.scrollTo({ top: box.current.scrollHeight }) }, [messages])
  const on = enabled && (q.data?.enabled ?? true)

  async function send() {
    const text = input.trim()
    if (!text || streaming) return
    setInput('')
    setStreaming(true)
    const replyId = `r${Date.now()}`
    setMessages((m) => [...m, { id: `u${Date.now()}`, role: 'user', content: text },
      { id: replyId, role: 'assistant', content: '', source: 'llm' }])
    const patch = (fn: (msg: ChatMessage) => ChatMessage) =>
      setMessages((m) => m.map((x) => (x.id === replyId ? fn(x) : x)))
    try {
      const res = await fetch(`/api/student/problems/${problemId}/chat`, {
        method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text, attempt_id: attemptId ?? null }),
      })
      if (!res.ok || !res.body) {
        const err = await res.json().catch(() => null)
        setMessages((m) => m.filter((x) => x.id !== replyId).concat({ id: `n${Date.now()}`, role: 'notice',
          content: err?.error?.message ?? '暂时发不出去，请稍后再试' }))
        return
      }
      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      for (;;) {
        const { value, done } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const { events, rest } = parseSse(buffer)
        buffer = rest
        for (const ev of events) {
          if (ev.delta) patch((x) => ({ ...x, content: x.content + ev.delta, source: ev.source ?? x.source,
            flagged: x.flagged || !!ev.flagged }))
          if (ev.source === 'fallback') setSimplified(true)
          if (ev.done) patch((x) => ({ ...x, id: ev.message_id ?? x.id, source: ev.source, flagged: ev.flagged }))
        }
      }
    } catch {
      patch((x) => ({ ...x, content: x.content || '网络断开了，可以再问一次' }))
    } finally {
      setStreaming(false)
    }
  }

  return (
    <div className="card chat" data-testid="chat-panel">
      <div className="card-h">问助教 <small>{simplified ? '当前为简化提示，不影响仿真和判定' : 'DeepSeek · 不会直接给答案'}</small></div>
      <div className="msgs" ref={box} aria-live="polite">
        {messages.length === 0 && <div className="msg ai">有哪里想不通？可以问我“第几步为什么对不上”。我会给思路，但不会直接给代码。</div>}
        {messages.map((m) => (
          <div key={m.id} className={m.role === 'user' ? 'msg me' : m.role === 'notice' ? 'msg notice' : 'msg ai'}
            data-testid={m.role === 'assistant' ? 'chat-reply' : undefined}>
            {m.content || (streaming && m.role === 'assistant' ? '…' : '')}
          </div>
        ))}
      </div>
      <div className="chat-in">
        <div className="tip">{on ? '助教只给思路，不给代码' : '本班当前没有开放助教对话'}</div>
        <div className="box">
          <input placeholder="问助教……" aria-label="问助教" value={input} disabled={!on || streaming} maxLength={500}
            onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') void send() }}
            data-testid="chat-input" />
          <button className="wave-btn primary" disabled={!on || streaming || !input.trim()} onClick={() => void send()}
            data-testid="chat-send">发送</button>
        </div>
      </div>
    </div>
  )
}
