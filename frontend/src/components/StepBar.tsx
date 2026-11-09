// PRIMM 五步条：完成 ✓、当前（主色实心）、未到（灰）；本题没有的步骤写“本题无”
import type { Step } from '../api/types'

const ALL: { step: Step; label: string; n: number }[] = [
  { step: 'predict', label: '预测', n: 1 }, { step: 'run', label: '运行', n: 2 },
  { step: 'investigate', label: '探究', n: 3 }, { step: 'modify', label: '修改', n: 4 }, { step: 'make', label: '创作', n: 5 },
]

export default function StepBar({ steps, current, completed }: { steps: Step[]; current: Step; completed: Step[] }) {
  return (
    <ol className="steps" aria-label="PRIMM 五步">
      {ALL.map((s, i) => {
        const applicable = steps.includes(s.step)
        const done = completed.includes(s.step) && s.step !== current
        const cur = s.step === current
        const cls = !applicable ? 'skip' : cur ? 'cur' : done ? 'done' : ''
        return (
          <li key={s.step} className={cls} data-step={s.step} aria-current={cur ? 'step' : undefined}>
            {i > 0 && <span className="sep" aria-hidden="true">›</span>}
            <span className="num">{done ? '✓' : s.n}</span>{s.label}
            {!applicable && <em>本题无</em>}
          </li>
        )
      })}
    </ol>
  )
}
