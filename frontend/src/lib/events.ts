// 界面事件批量上报（docs/learner-model.md 第 7 节）：每 5 秒或满 20 条发一次；提交代码前先发完；
// 关闭或离开页面时用 sendBeacon 把剩下的发出去（否则跳转页面时队列里的事件会丢）
import { post } from '../api/client'

export type ClientEventType = 'page.view' | 'step.enter' | 'problem.open' | 'waveform.view' | 'waveform.cell_click'
  | 'lesson.open' | 'lesson.quiz' | 'tour.done' | 'schematic.view' | 'schematic.cell_click'

export interface ClientEvent {
  type: ClientEventType
  ts: string
  problem_id?: string
  attempt_id?: number
  payload?: Record<string, unknown>
}

type Sender = (events: ClientEvent[]) => Promise<unknown>

export class EventReporter {
  private queue: ClientEvent[] = []
  private timer: ReturnType<typeof setInterval> | null = null

  constructor(private send: Sender, private maxBatch = 20, private intervalMs = 5000) {}

  start() {
    if (this.timer === null) {
      this.timer = setInterval(() => void this.flush(), this.intervalMs)
      if (typeof window !== 'undefined') {
        window.addEventListener('pagehide', () => this.flushBeacon())
        document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'hidden') this.flushBeacon() })
      }
    }
  }

  /** 页面要关了：不等定时器，用 sendBeacon 发出去（浏览器保证在页面卸载后也会发送） */
  flushBeacon(url = '/api/student/events') {
    if (this.queue.length === 0 || typeof navigator === 'undefined' || !navigator.sendBeacon) return
    while (this.queue.length) {
      const batch = this.queue.splice(0, this.maxBatch)
      const ok = navigator.sendBeacon(url, new Blob([JSON.stringify({ events: batch })], { type: 'application/json' }))
      if (!ok) { this.queue.unshift(...batch); return }
    }
  }

  stop() {
    if (this.timer !== null) clearInterval(this.timer)
    this.timer = null
  }

  track(type: ClientEventType, data: Omit<ClientEvent, 'type' | 'ts'> = {}) {
    this.queue.push({ type, ts: new Date().toISOString(), ...data })
    if (this.queue.length >= this.maxBatch) void this.flush()
  }

  async flush() {
    if (this.queue.length === 0) return
    const batch = this.queue.splice(0, this.maxBatch)
    try {
      await this.send(batch)
    } catch {
      this.queue.unshift(...batch)   // 网络失败：放回队列，等下一次定时再发（不立即重试）
      return
    }
    if (this.queue.length) await this.flush()
  }

  pending() {
    return this.queue.length
  }
}

export const reporter = new EventReporter((events) => post('/api/student/events', { events }))
