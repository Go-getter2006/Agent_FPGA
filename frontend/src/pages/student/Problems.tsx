// S3 题目列表（/student/problems）：左侧筛选（知识点 / 状态）；入门题排在最前。
// 切换筛选时保留上一次的列表（变淡），新结果到了再替换，页面不会闪
import { Radio } from 'antd'
import { Link, useSearchParams } from 'react-router-dom'
import { useProblems } from '../../api/hooks'
import { Empty, ErrorState, Loading } from '../../components/Common'
import { STATUS_LABEL, beijingTime } from '../../lib/format'
import './Student.css'

export default function Problems() {
  const [params, setParams] = useSearchParams()
  const filter = { kp: params.get('kp') ?? undefined, status: params.get('status') ?? undefined }
  const q = useProblems(filter)
  const hasDue = !!q.data?.items.some((p) => p.due_at)       // 教师布置了作业才显示“截止”列
  const set = (k: string, v: string) => {
    const next = new URLSearchParams(params)
    if (v) next.set(k, v); else next.delete(k)
    setParams(next)
  }
  return (
    <div className="page problems" data-testid="problems">
      <div className="page-h"><h1>题目</h1><span className="muted">按知识点由浅入深排列</span></div>
      <div className="problems-grid">
        <aside className="card filters">
          <div className="card-b">
            <div className="f-t">知识点</div>
            <Radio.Group value={filter.kp ?? ''} onChange={(e) => set('kp', e.target.value)}>
              <Radio value="">全部</Radio>
              {q.data?.knowledge_points.map((k) => <Radio key={k.code} value={k.code}>{k.name}</Radio>)}
            </Radio.Group>
            <div className="f-t">状态</div>
            <Radio.Group value={filter.status ?? ''} onChange={(e) => set('status', e.target.value)}>
              <Radio value="">全部</Radio>
              {Object.entries(STATUS_LABEL).map(([k, v]) => <Radio key={k} value={k}>{v}</Radio>)}
            </Radio.Group>
          </div>
        </aside>
        <div className={q.isPlaceholderData ? 'card stale on' : 'card stale'} aria-busy={q.isFetching}>
          {q.isLoading && <Loading />}
          {q.error && <ErrorState error={q.error} onRetry={() => q.refetch()} />}
          {q.data && q.data.items.length === 0 && <Empty title="没有符合条件的题目">换一个知识点或状态试试</Empty>}
          {q.data && q.data.items.length > 0 && (
            <table className="tbl">
              <thead><tr><th>题目</th><th>知识点</th><th>类型</th><th>难度</th><th>状态</th>{hasDue && <th>截止</th>}</tr></thead>
              <tbody>
                {q.data.items.map((p) => (
                  <tr key={p.id} data-testid={`problem-row-${p.id}`}>
                    <td>{p.stage === 'beginner' && <span className="chip green" style={{ marginRight: 6 }}>入门</span>}<Link to={`/student/problems/${p.id}`}>{p.title}</Link></td>
                    <td>{p.knowledge_points.map((k) => <span key={k.code} className="chip" style={{ marginRight: 4 }}>{k.name.replace(/（.*）/, '')}</span>)}</td>
                    <td><span className="chip blue">{p.primm_label}</span></td>
                    <td aria-label={`难度 ${p.difficulty}`}>{'●'.repeat(p.difficulty)}<span className="muted">{'●'.repeat(3 - p.difficulty)}</span></td>
                    <td><span className={`status st-${p.status}`}>{STATUS_LABEL[p.status]}</span></td>
                    {hasDue && <td className="muted">{p.due_at ? beijingTime(p.due_at) : '—'}</td>}
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  )
}
