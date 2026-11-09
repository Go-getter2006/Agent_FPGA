// 提示阶梯：1 级定位 → 2 级概念 → 3 级类比，每次只能解锁下一级
import { Button } from 'antd'
import type { Hint } from '../api/types'

const LEVELS = [
  { level: 1, name: '定位' }, { level: 2, name: '概念' }, { level: 3, name: '类比' },
]

export default function HintLadder({ hints, onRequest, loading, error, disabled }: {
  hints: Hint[]; onRequest: () => void; loading?: boolean; error?: string | null; disabled?: boolean
}) {
  const next = hints.length + 1
  return (
    <div className="ladder" data-testid="hint-ladder">
      {LEVELS.map(({ level, name }) => {
        const h = hints.find((x) => x.level === level)
        if (h) {
          return (
            <div className="lv open" key={level} data-testid={`hint-${level}`}>
              <div className="lv-h"><span>{level} 级 · {name}</span><span className="chip">已查看</span></div>
              <p>{h.message}</p>
              <div className="q">{h.question}</div>
            </div>
          )
        }
        return (
          <div className="lv" key={level}>
            <div className="lv-h"><span>{level} 级 · {name}</span>
              {level > next && <span className="lock">解锁 {level - 1} 级后可用</span>}
            </div>
            {level === next && (
              <>
                <Button size="small" style={{ marginTop: 8 }} onClick={onRequest} loading={loading} disabled={disabled}
                  data-testid="hint-request">再给我一点提示（{level} 级·{name}）</Button>
                {error && <div className="lock" style={{ marginTop: 6 }}>{error}</div>}
              </>
            )}
          </div>
        )
      })}
      <div className="lock">当前为规则提示：由仿真和综合结果生成，不会直接给出代码</div>
    </div>
  )
}
