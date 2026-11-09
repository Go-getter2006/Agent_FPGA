// 助教对话（docs/pages.md S4 助教面板）：流式输出；学生消息靠右，助教消息靠左，助教回复按 Markdown 渲染。
// 可以“放大”到大窗口里聊；新手可以点常用问题直接发送
import { useQuery } from '@tanstack/react-query'
import { Modal } from 'antd'
import { useEffect, useRef, useState } from 'react'
import { get } from '../api/client'
import type { ChatMessage } from '../api/types'
import Markdown from '../lib/markdown'

interface ChatData { session_id: number; enabled: boolean; messages: ChatMessage[] }

/** 解析 SSE 文本块里的 data: 行；返回解析出的事件和剩余未完成的文本 */
export function parseSse(buffer: string): { events: Record<string, any>[]; rest: string } {
  const parts = buffer.split('\n\n')
  const rest = parts.pop() ?? ''
  const events = parts.flatMap((block) => block.split('\n').filter((l) => l.startsWith('data: '))
    .map((l) => { try { return JSON.parse(l.slice(6)) } catch { return null } }).filter(Boolean))
  return { events, rest }
}

const QUICK = ['这道题要我做什么？', '我下一步该做什么？', 'Verilog 和 C 语言有什么不同？', '给我一个代码框架']
const WELCOME = '有哪里想不通都可以问我，比如“这道题要我做什么”“第 3 步为什么对不上”“always 是什么意思”。' +
  '我会一步一步讲思路，也可以给代码框架。'

export default function ChatPanel({ problemId, attemptId, enabled = true }: {
  problemId: string; attemptId?: number | null; enabled?: boolean
}) {
  const q = useQuery({ queryKey: ['chat', problemId], queryFn: () => get<ChatData>(`/api/student/problems/${problemId}/chat`) })
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [simplified, setSimplified] = useState(false)
  const [big, setBig] = useState(false)

  useEffect(() => { if (q.data) setMessages(q.data.messages) }, [q.data])
  const on = enabled && (q.data?.enabled ?? true)

  async function send(raw?: string) {
    const text = (raw ?? input).trim()
    if (!text || streaming) return
    if (raw === undefined) setInput('')
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

  const body = (
    <ChatBody messages={messages} streaming={streaming} on={on} input={input} setInput={setInput}
      send={send} showQuick={messages.length < 2} />
  )
  return (
    <div className="card chat" data-testid="chat-panel">
      <div className="card-h">问助教
        <small>{simplified ? '当前为简化提示，不影响仿真和判定' : 'DeepSeek'}
          <button className="link-btn" onClick={() => setBig(true)} data-testid="chat-expand" title="在大窗口里聊">⤢ 放大</button></small></div>
      {big ? <div className="msgs muted" style={{ fontSize: 13 }}>对话已在大窗口中打开</div> : body}
      <Modal open={big} onCancel={() => setBig(false)} footer={null} width="min(960px, 92vw)" title="问助教"
        className="chat-modal" destroyOnClose={false}>
        <div className="chat big">{body}</div>
      </Modal>
    </div>
  )
}

function ChatBody({ messages, streaming, on, input, setInput, send, showQuick }: {
  messages: ChatMessage[]; streaming: boolean; on: boolean; input: string; setInput: (v: string) => void
  send: (raw?: string) => Promise<void>; showQuick: boolean
}) {
  const box = useRef<HTMLDivElement>(null)
  useEffect(() => { box.current?.scrollTo({ top: box.current.scrollHeight }) }, [messages])
  return (
    <>
      <div className="msgs" ref={box} aria-live="polite">
        {messages.length === 0 && <div className="msg ai">{WELCOME}</div>}
        {messages.map((m) => (
          <div key={m.id} className={m.role === 'user' ? 'msg me' : m.role === 'notice' ? 'msg notice' : 'msg ai'}
            data-testid={m.role === 'assistant' ? 'chat-reply' : undefined}>
            {m.role === 'assistant'
              ? (m.content ? <Markdown text={m.content} /> : (streaming ? '…' : ''))
              : m.content}
          </div>
        ))}
      </div>
      <div className="chat-in">
        {on && showQuick && (
          <div className="quick">{QUICK.map((t) => (
            <button key={t} disabled={streaming} onClick={() => void send(t)} data-testid="chat-quick">{t}</button>))}</div>
        )}
        <div className="tip">{on ? '助教会讲思路、给代码框架；实在不会可以在提示区看参考答案' : '本班当前没有开放助教对话'}</div>
        <div className="box">
          <input placeholder="问助教……（回车发送）" aria-label="问助教" value={input} disabled={!on || streaming} maxLength={500}
            onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') void send() }}
            data-testid="chat-input" />
          <button className="wave-btn primary" disabled={!on || streaming || !input.trim()} onClick={() => void send()}
            data-testid="chat-send">发送</button>
        </div>
      </div>
    </>
  )
}
