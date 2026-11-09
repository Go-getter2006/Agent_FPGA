import { fireEvent, render, screen } from '@testing-library/react'
import WaveformView, { normalizePredictInput } from '../components/WaveformView'
import type { TraceRow } from '../api/types'

const steps = [0, 1, 2, 3]
const inputs = [{ name: 'in', width: 1, values: ['0', '1', '0', '1'] }]
const outputs = [{ name: 'out', width: 1 }, { name: 'q', width: 4 }]
const trace = (outs: string[], qs: string[]): TraceRow[] =>
  steps.map((s, i) => ({ step: s, inputs: { in: inputs[0].values[i] }, outputs: { out: outs[i], q: qs[i] } }))

describe('WaveformView', () => {
  it('predict 模式：只在预测格显示“?”，单比特点击依次填 0、1', () => {
    const onPredict = vi.fn()
    render(<WaveformView mode="predict" steps={steps} inputs={inputs} outputs={outputs}
      predictCells={[{ signal: 'out', step: 1 }, { signal: 'out', step: 3 }]} predicted={{ 'out@3': '0' }} onPredict={onPredict} />)
    expect(screen.getByLabelText('out，第 1 步，待预测')).toBeInTheDocument()
    expect(screen.getByLabelText('out，第 3 步，你的预测 0')).toBeInTheDocument()
    expect(screen.queryByTestId('predict-out-0')).toBeNull()
    fireEvent.click(screen.getByTestId('predict-out-1'))
    expect(onPredict).toHaveBeenLastCalledWith('out', 1, '0')
    fireEvent.click(screen.getByTestId('predict-out-3'))
    expect(onPredict).toHaveBeenLastCalledWith('out', 3, '1')
  })

  it('predict 模式：键盘可以用 0 / 1 直接填格子', () => {
    const onPredict = vi.fn()
    render(<WaveformView mode="predict" steps={steps} inputs={inputs} outputs={outputs}
      predictCells={[{ signal: 'out', step: 2 }]} onPredict={onPredict} />)
    fireEvent.keyDown(screen.getByTestId('predict-out-2'), { key: '1' })
    expect(onPredict).toHaveBeenCalledWith('out', 2, '1')
  })

  it('compare 模式：期望和你的电路各一行，不同的格子标“对不上”，预测带 ✓ / ✗', () => {
    render(<WaveformView mode="compare" steps={steps} inputs={inputs} outputs={outputs}
      expected={trace(['0', '0', '1', '0'], ['0000', '0001', '0010', '0011'])}
      actual={trace(['0', '0', '0', '0'], ['0000', '0001', '0010', '0011'])}
      predictCells={[{ signal: 'out', step: 2 }, { signal: 'out', step: 3 }]}
      predicted={{ 'out@2': '1', 'out@3': '0' }} firstMismatchStep={2} />)
    const mm = screen.getByTestId('cell-actual-out-2')
    expect(mm.getAttribute('aria-label')).toBe('out，第 2 步，你的电路，值 0，你的预测 1，对不上，预测没对上')
    expect(screen.getByTestId('cell-actual-out-3').getAttribute('aria-label')).toContain('对得上，预测对')
    expect(screen.getByTestId('cell-expected-out-2')).toBeInTheDocument()
    expect(screen.getByTestId('first-mismatch')).toHaveTextContent('第一个对不上的周期')
    expect(screen.getByText('你预测 1')).toBeInTheDocument()
  })

  it('总线默认显示十六进制，可以切换二进制', () => {
    const { rerender } = render(<WaveformView mode="result" steps={steps} inputs={inputs} outputs={outputs}
      actual={trace(['0', '0', '0', '0'], ['1010', '1010', '1111', '1111'])} />)
    expect(screen.getByText('A')).toBeInTheDocument()
    expect(screen.getByText('F')).toBeInTheDocument()
    rerender(<WaveformView mode="result" steps={steps} inputs={inputs} outputs={outputs} radix="bin"
      actual={trace(['0', '0', '0', '0'], ['1010', '1010', '1111', '1111'])} />)
    expect(screen.getByText('1010')).toBeInTheDocument()
  })

  it('点击格子回调带上是否对不上', () => {
    const onCellClick = vi.fn()
    render(<WaveformView mode="compare" steps={steps} inputs={inputs} outputs={outputs} onCellClick={onCellClick}
      expected={trace(['0', '1', '0', '0'], ['0', '0', '0', '0'].map(() => '0000'))}
      actual={trace(['0', '0', '0', '0'], ['0', '0', '0', '0'].map(() => '0000'))} />)
    fireEvent.click(screen.getByTestId('cell-actual-out-1'))
    expect(onCellClick).toHaveBeenCalledWith('out', 1, 'actual', true)
  })
})

describe('normalizePredictInput', () => {
  it('二进制、十六进制、超出位宽', () => {
    expect(normalizePredictInput('101', 4)).toBe('0101')
    expect(normalizePredictInput('0xA', 4)).toBe('1010')
    expect(normalizePredictInput('h3', 4)).toBe('0011')
    expect(normalizePredictInput('10000', 4)).toBeNull()
    expect(normalizePredictInput('9', 4)).toBeNull()
  })
})
