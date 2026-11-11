// T3 误区分析：标签分布（区分裁判标签与预测误区）；点某个标签 → 说明、涉及学生、典型代码片段（匿名）、相关题目
import { Segmented } from 'antd'
import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { qs, useT, type Misconception } from '../../api/teacher'
import { Empty, ErrorState, Loading } from '../../components/Common'
import { useTeacher } from './TeacherLayout'
import { GROUP_OPTIONS } from './Heatmap'

const EXPLAIN: Record<string, string> = {
  latch_inferred: '组合 always 块里有路径没给信号赋值，综合出锁存器。', blocking_in_seq: '时序 always 块里用了阻塞赋值 =。',
  nonblocking_in_comb: '组合 always 块里用了非阻塞赋值 <=。', width_mismatch: '赋值或运算两边的位宽不一致，发生了截断或扩展。',
  multi_driven: '同一个信号在多个 always 块或 assign 里被驱动。', non_synthesizable: '用了只能仿真、不能综合成电路的写法。',
  race_order_sensitive: '交换 always 块的先后，仿真结果就变了。', fragile_pass: '仿真通过，但电路描述有锁存器、多驱动或不可综合等隐患。',
  pred_ff_confusion: '预测“哪些信号成了触发器”或触发器个数时出错。', pred_off_by_one_cycle: '预测的输出序列和实际整体错开一拍。',
  pred_latch_blind: '实际生成了锁存器，学生却预测“没有”。', pred_order_belief: '对“结果是否依赖代码先后”的判断与实验结果相反。',
}

export default function Misconceptions() {
  const { cid, anonymous, who } = useTeacher()
  const [params, setParams] = useSearchParams()
  const [group, setGroup] = useState('')
  const code = params.get('code')
  const list = useT<{ items: Misconception[] }>(['t-mis', cid, group], `/api/teacher/classes/${cid}/misconceptions${qs({ group })}`)
  const detail = useT<any>(['t-mis-d', cid, code, group, anonymous],
    `/api/teacher/classes/${cid}/misconceptions/${code}${qs({ group, anonymous })}`, !!code)
  if (list.isLoading) return <Loading />
  if (list.error || !list.data) return <ErrorState error={list.error} onRetry={() => list.refetch()} />
  const items = list.data.items
  const max = Math.max(1, ...items.map((m) => m.students))
  return (
    <div data-testid="t-misconceptions" className={list.isPlaceholderData ? 'stale on' : 'stale'}>
      <div className="page-h"><h1>误区分析</h1><Segmented value={group} onChange={(v) => setGroup(String(v))} options={GROUP_OPTIONS} /></div>
      <div className="grid g-5-7">
        <div className="card"><div className="card-h">标签分布 <small><span className="src j">裁判标签</span>代码层面 <span className="src p">预测误区</span>理解层面</small></div>
          <div className="card-b">
            {items.length === 0 && <Empty title="还没有误区记录" />}
            {items.map((m) => (
              <div key={m.code} className="hbar" onClick={() => setParams({ code: m.code })} data-testid={`mis-${m.code}`}
                style={code === m.code ? { background: 'var(--c-primary-bg)', borderRadius: 6 } : undefined}>
                <span>{m.label}<span className={`src ${m.source === 'prediction' ? 'p' : 'j'}`}>{m.source === 'prediction' ? '预测' : '裁判'}</span></span>
                <span className="track"><i style={{ width: `${(m.students / max) * 100}%`, background: m.source === 'prediction' ? 'var(--q-fragile)' : 'var(--c-primary)' }} /></span>
                <span style={{ textAlign: 'right' }}>{m.students} 人</span>
              </div>
            ))}
          </div></div>
        <div className="card"><div className="card-h">{detail.data ? detail.data.label : '点左边的标签查看详情'}
          {detail.data && <small>{detail.data.students.length} 名学生 · 出现 {detail.data.occurrences} 次</small>}</div>
          <div className={detail.isPlaceholderData ? 'card-b stale on' : 'card-b stale'} data-testid="mis-detail">
            {!code && <Empty title="还没选标签" />}
            {detail.isLoading && code && <Loading rows={4} />}
            {detail.data && (
              <>
                <p>{EXPLAIN[detail.data.code] ?? ''}</p>
                <h4 style={{ margin: '12px 0 6px' }}>相关题目</h4>
                <div>{detail.data.problems.map((p: any) => <span key={p.problem_id} className="chip" style={{ marginRight: 6 }}>{p.title} × {p.count}</span>)}</div>
                <h4 style={{ margin: '12px 0 6px' }}>典型代码片段（匿名）</h4>
                {detail.data.examples.map((ex: any) => (
                  <div key={ex.attempt_id} style={{ marginBottom: 12 }}>
                    <div className="muted" style={{ fontSize: 12, marginBottom: 4 }}>{ex.title} · {ex.alias}</div>
                    <pre className="snippet">{ex.lines.map((l: string, i: number) => (
                      <span key={i} className={`ln ${ex.focus.includes(ex.start + i) ? 'hit' : ''}`}><span className="no">{ex.start + i}</span>{l}</span>))}</pre>
                  </div>
                ))}
                <h4 style={{ margin: '12px 0 6px' }}>涉及学生</h4>
                <div>{detail.data.students.map((s: any) => <span key={s.user_id} className="chip" style={{ marginRight: 4, marginBottom: 4 }}>{who(s)}</span>)}</div>
              </>
            )}
          </div></div>
      </div>
    </div>
  )
}
