// T4 题目分析：通过率、平均提交次数、F 值、盲改率、平均提示等级、平均用时；PRIMM 漏斗；常见的第一个对不上的格子；各级提示之后的通过率
import { Segmented, Select } from 'antd'
import { useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { qs, useT, type Overview } from '../../api/teacher'
import { Empty, ErrorState, KpiCard, Loading } from '../../components/Common'
import EChart from '../../components/EChart'
import { colors } from '../../theme/tokens'
import { useTeacher } from './TeacherLayout'
import { GROUP_OPTIONS } from './Heatmap'
import { duration } from './Overview'

const STEP_NAME: Record<string, string> = { predict: '① 预测', run: '② 运行', investigate: '③ 探究', modify: '④ 修改', make: '⑤ 创作' }
const pct = (v: number | null) => (v === null ? '—' : `${Math.round(v * 100)}%`)
const n2 = (v: number | null, d = 2) => (v === null ? '—' : v.toFixed(d))

export default function Problems() {
  const { cid } = useTeacher()
  const { pid } = useParams()
  const navigate = useNavigate()
  const [group, setGroup] = useState('')
  const list = useT<Overview>(['t-overview', cid, '', true], `/api/teacher/classes/${cid}/overview`)
  const current = pid ?? list.data?.problems[0]?.problem_id
  const q = useT<any>(['t-prob', cid, current, group], `/api/teacher/classes/${cid}/problems/${current}/analytics${qs({ group })}`, !!current)
  const funnel = useMemo(() => {
    const d = q.data
    if (!d) return null
    return {
      grid: { left: 80, right: 40, top: 8, bottom: 8 },
      xAxis: { type: 'value', show: false }, yAxis: { type: 'category', inverse: true, data: d.steps.map((s: string) => STEP_NAME[s]),
        axisLabel: { color: colors.text }, axisTick: { show: false }, axisLine: { show: false } },
      series: [{ type: 'bar', data: d.steps.map((s: string) => d.funnel[s]), barWidth: 18,
        itemStyle: { color: colors.primary, borderRadius: 4 }, label: { show: true, position: 'right', formatter: '{c} 人' } }],
    }
  }, [q.data])
  if (list.isLoading) return <Loading />
  if (!current) return <Empty title="还没有学生做题" />
  return (
    <div data-testid="t-problem" className={q.isPlaceholderData ? 'stale on' : 'stale'}>
      <div className="page-h"><h1>题目分析</h1>
        <Select value={current} style={{ minWidth: 220 }} onChange={(v) => navigate(`/teacher/classes/${cid}/problems/${v}`)}
          options={(list.data?.problems ?? []).map((p) => ({ value: p.problem_id, label: p.title }))} />
        <Segmented value={group} onChange={(v) => setGroup(String(v))} options={GROUP_OPTIONS} /></div>
      {q.isLoading && <Loading />}
      {q.error && <ErrorState error={q.error} onRetry={() => q.refetch()} />}
      {q.data && (
        <>
          <div className="metric-grid">
            <KpiCard title="通过率" value={pct(q.data.pass_rate)} foot={<span className="muted">{q.data.passed} / {q.data.attempted} 人</span>} />
            <KpiCard title="平均提交次数" value={n2(q.data.avg_submissions, 1)} />
            <KpiCard title="F 值" value={n2(q.data.f_value)} foot={<span className="muted">越低越好</span>} />
            <KpiCard title="盲改率" value={pct(q.data.blind_rate)} />
            <KpiCard title="平均提示等级" value={n2(q.data.avg_hint_level, 1)} />
            <KpiCard title="平均用时" value={duration(q.data.avg_minutes)} foot={<span className="muted">从打开题目到第一次通过</span>} />
          </div>
          <div className="grid g-5-7" style={{ marginTop: 16 }}>
            <div className="card"><div className="card-h">PRIMM 漏斗 <small>进入各步骤的人数</small></div>
              <div className="card-b">{funnel && <EChart option={funnel} height={200} label="PRIMM 漏斗" testId="funnel" />}</div></div>
            <div className="card"><div className="card-h">最常见的“第一个对不上的格子”</div>
              <table className="tbl"><thead><tr><th>STEP</th><th>信号</th><th className="r">次数</th></tr></thead>
                <tbody>{q.data.top_mismatch_cells.map((c: any) => <tr key={`${c.step}${c.signal}`}><td>{c.step}</td><td className="mono">{c.signal}</td><td className="r">{c.count}</td></tr>)}</tbody></table>
              {q.data.top_mismatch_cells.length === 0 && <Empty title="没有对不上的提交" />}</div>
          </div>
          <div className="card" style={{ marginTop: 16 }}><div className="card-h">各提示等级之后，下一次提交的通过率 <small>按提示词版本</small></div>
            <table className="tbl" data-testid="after-hint"><thead><tr><th>提示等级</th><th>提示词版本</th><th className="r">样本数</th><th className="r">下一次通过率</th></tr></thead>
              <tbody>{q.data.after_hint.map((r: any) => <tr key={`${r.level}${r.prompt_version}`}><td>{r.level >= 4 ? '参考答案' : `${r.level} 级`}</td><td>{r.prompt_version}</td><td className="r">{r.n}</td><td className="r">{pct(r.next_pass_rate)}</td></tr>)}</tbody></table>
            {q.data.after_hint.length === 0 && <Empty title="还没有提示记录" />}</div>
        </>
      )}
    </div>
  )
}
