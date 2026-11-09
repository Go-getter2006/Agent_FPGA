import { render, screen } from '@testing-library/react'
import { EventReporter } from '../lib/events'
import { regCandidates } from '../components/HardwarePanel'
import Markdown from '../lib/markdown'
import { beijingTime, binToHex } from '../lib/format'

describe('EventReporter：每 5 秒或满 20 条发一次', () => {
  it('满 20 条立即发送', async () => {
    const send = vi.fn().mockResolvedValue(undefined)
    const r = new EventReporter(send, 20, 5000)
    for (let i = 0; i < 19; i++) r.track('waveform.cell_click', { payload: { i } })
    expect(send).not.toHaveBeenCalled()
    r.track('waveform.cell_click')
    await Promise.resolve()
    expect(send).toHaveBeenCalledTimes(1)
    expect(send.mock.calls[0][0]).toHaveLength(20)
    expect(send.mock.calls[0][0][0]).toMatchObject({ type: 'waveform.cell_click', payload: { i: 0 } })
  })

  it('定时发送；网络失败时放回队列', async () => {
    vi.useFakeTimers()
    const send = vi.fn().mockRejectedValueOnce(new Error('offline')).mockResolvedValue(undefined)
    const r = new EventReporter(send, 20, 5000)
    r.start()
    r.track('page.view', { payload: { route: '/student' } })
    await vi.advanceTimersByTimeAsync(5000)
    expect(send).toHaveBeenCalledTimes(1)
    expect(r.pending()).toBe(1)
    await vi.advanceTimersByTimeAsync(5000)
    expect(send).toHaveBeenCalledTimes(2)
    expect(r.pending()).toBe(0)
    r.stop()
    vi.useRealTimers()
  })
})

describe('regCandidates：从代码里找 reg 信号名', () => {
  it('端口里的 output reg 与模块内的 reg 声明', () => {
    const code = `module top_module (input wire clk, output reg [3:0] q, output reg y, input wire d);
      reg [1:0] state, next_state;  // 注释里的 reg fake 不算
      reg signed [7:0] acc = 0;
      wire w;
    endmodule`
    expect(regCandidates(code).sort()).toEqual(['acc', 'next_state', 'q', 'state', 'y'])
  })
})

describe('Markdown', () => {
  it('表格、行内代码、粗体', () => {
    render(<Markdown text={'# 标题\n\n| 信号 | 说明 |\n|---|---|\n| `clk` | **时钟** |\n'} skipTitle />)
    expect(screen.queryByText('标题')).toBeNull()
    expect(screen.getByRole('table')).toBeInTheDocument()
    expect(screen.getByText('clk').tagName).toBe('CODE')
    expect(screen.getByText('时钟').tagName).toBe('B')
  })
})

describe('format', () => {
  it('北京时间、十六进制', () => {
    expect(beijingTime('2026-11-09T02:05:00+00:00')).toContain('10:05')
    expect(binToHex('1010')).toBe('A')
    expect(binToHex('1x10')).toBe('1X10')
  })
})

import { parseSse } from '../components/ChatPanel'

describe('parseSse：解析流式对话', () => {
  it('完整事件与半截事件', () => {
    const { events, rest } = parseSse('data: {"delta":"你好"}\n\ndata: {"delta":"，第 5 步"}\n\ndata: {"do')
    expect(events.map((e) => e.delta)).toEqual(['你好', '，第 5 步'])
    expect(rest).toBe('data: {"do')
    const next = parseSse(rest + 'ne":true,"source":"llm"}\n\n')
    expect(next.events).toEqual([{ done: true, source: 'llm' }])
  })
})

import { duration } from '../pages/teacher/Overview'

describe('教师端平均用时显示', () => {
  it('分钟、小时、天', () => {
    expect(duration(null)).toBe('—')
    expect(duration(26.4)).toBe('26 分钟')
    expect(duration(150)).toBe('2.5 小时')
    expect(duration(5662)).toBe('3.9 天')
  })
})
