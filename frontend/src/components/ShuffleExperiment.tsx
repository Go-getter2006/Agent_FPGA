// 顺序打乱实验：一个主按钮 + 结论条 + diff 波形
import { Alert, Button, Collapse, Radio } from 'antd'
import { useState } from 'react'
import WaveformView from './WaveformView'
import type { AttemptDetail, Skeleton } from '../api/types'

export default function ShuffleExperiment({ attempt, skeleton, onRun, running, clocked }: {
  attempt: AttemptDetail | null; skeleton: Skeleton; onRun: (prediction: 'change' | 'same') => void
  running: boolean; clocked: boolean
}) {
  const [prediction, setPrediction] = useState<'change' | 'same' | null>(null)
  const run = attempt?.shuffle
  const result = run?.result
  if (!attempt || !attempt.judge?.compile.ok) {
    return <div className="muted" style={{ padding: 16 }}>先运行一次仿真，再来做顺序打乱实验。</div>
  }
  const variant = result?.variants.find((v) => v.first_diff) ?? null
  return (
    <div style={{ padding: '12px 16px' }} data-testid="shuffle-panel">
      <div style={{ marginBottom: 8 }}>真实电路里所有 always 块同时工作；仿真器却要一个一个地执行。先预测：
        把 always 块换个先后顺序，仿真结果会变吗？</div>
      <Radio.Group value={prediction} onChange={(e) => setPrediction(e.target.value)} disabled={running}>
        <Radio value="change" data-testid="shuffle-predict-change">会变</Radio>
        <Radio value="same" data-testid="shuffle-predict-same">不会变</Radio>
      </Radio.Group>
      <Button type="primary" style={{ marginLeft: 12 }} disabled={!prediction || running} loading={running}
        onClick={() => prediction && onRun(prediction)} data-testid="shuffle-run">打乱 always 块的顺序，再仿真一次</Button>
      {result && !result.ok && <Alert style={{ marginTop: 12 }} type="info" showIcon message={result.message} />}
      {result && result.ok && result.order_sensitive === false && (
        <Alert style={{ marginTop: 12 }} type="success" showIcon data-testid="shuffle-same"
          message={result.message ?? '你的电路与执行顺序无关，和真实硬件一致'}
          description={run?.prediction === 'change' ? '你预测会变，但结果没变：用非阻塞赋值时，同一个时钟沿先读旧值、再统一更新。' : undefined} />
      )}
      {result && result.ok && result.order_sensitive && variant && (
        <div style={{ marginTop: 12 }} data-testid="shuffle-diff">
          <Alert type="warning" showIcon message={`换成顺序 ${variant.order.join(' → ')} 之后，第 ${variant.first_diff!.step} 步的 ${variant.first_diff!.signal} 变了`}
            description="真实电路里这两个块谁先谁后？" />
          <div style={{ marginTop: 8 }}>
            <WaveformView mode="diff" steps={skeleton.steps} inputs={skeleton.inputs} outputs={skeleton.outputs}
              expected={result.base_trace} actual={variant.trace} diffLabels={['原顺序', '打乱后']} clocked={clocked}
              firstMismatchStep={variant.first_diff!.step} />
          </div>
        </div>
      )}
      <Collapse ghost style={{ marginTop: 8 }} items={[{
        key: 'why', label: '讲解：为什么顺序会影响仿真？',
        children: <p style={{ fontSize: 13 }}>仿真器是一个顺序执行的程序，要用它模拟并行的硬件。
          阻塞赋值（=）执行到哪一句就立刻更新，后执行的块会读到先执行的块刚写的新值；
          非阻塞赋值（&lt;=）先把所有右边算好，等这一时刻的块都执行完再统一更新左边，所以和块的先后无关。</p>,
      }]} />
    </div>
  )
}
