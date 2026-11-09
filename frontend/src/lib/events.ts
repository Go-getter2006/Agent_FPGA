// 界面事件批量上报（docs/learner-model.md 第 7 节）：每 5 秒或满 20 条发一次；提交代码前先发完
import { post } from '../api/client'

export type ClientEventType = 'page.view' | 'step.enter' | 'problem.open' | 'waveform.view' | 'waveform.cell_click'

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
    if (this.timer === null) this.timer = setInterval(() => void this.flush(), this.intervalMs)
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
