// T1 班级概览：KPI → 趋势 / 误区 Top5 → 热力图节选 / 需要关注的学生 → 题目速览
import { Button, Segmented } from 'antd'
import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { qs, useT, type Heatmap, type Overview as OV } from '../../api/teacher'
import { ErrorState, Loading } from '../../components/Common'
import EChart from '../../components/EChart'
import { colors } from '../../theme/tokens'
import { useTeacher } from './TeacherLayout'
import { HeatmapChart, GROUP_OPTIONS } from './Heatmap'

const pct = (v: number | null | undefined) => (v === null || v === undefined ? '—' : `${Math.round(v * 100)}%`)
const num = (v: number | null | undefined, d = 2) => (v === null || v === undefined ? '—' : v.toFixed(d))
/** 平均用时：从第一次打开题目到第一次通过；跨天的按小时、天显示 */
export function duration(minutes: number | null | undefined): string {
  if (minutes === null || minutes === undefined) return '—'
  if (minutes < 120) return `${Math.round(minutes)} 分钟`
  if (minutes < 48 * 60) return `${(minutes / 60).toFixed(1)} 小时`
  return `${(minutes / 1440).toFixed(1)} 天`
}

function Delta({ value, prev, kind, lowerBetter = false }: { value: number | null; prev: number | null;
  kind: 'pct' | 'num' | 'count'; lowerBetter?: boolean }) {
  if (value === null || prev === null) return <span className="muted">上周无数据</span>
  const d = value - prev
  const tiny = kind === 'pct' ? Math.abs(d) < 0.005 : kind === 'num' ? Math.abs(d) < 0.005 : d === 0
  if (tiny) return <span className="muted">与上周持平</span>
  const good = lowerBetter ? d < 0 : d > 0
  const text = kind === 'pct' ? `${Math.abs(Math.round(d * 100))}%` : kind === 'count' ? `${Math.abs(d)} 人` : Math.abs(d).toFixed(2)
  return <span className={good ? 'delta-good' : 'delta-bad'}>{d > 0 ? '↑' : '↓'} {text}{lowerBetter ? '（越低越好）' : ''}</span>
}

export default function Overview() {
  const { cid, anonymous, who } = useTeacher()
  const navigate = useNavigate()
  const [group, setGroup] = useState<string>('')
  const q = useT<OV>(['t-overview', cid, group, anonymous], `/api/teacher/classes/${cid}/overview${qs({ group, anonymous })}`)
  const heat = useT<Heatmap>(['t-heat', cid, group, anonymous, 'all'], `/api/teacher/classes/${cid}/heatmap${qs({ group, anonymous })}`)
  const trendOption = useMemo(() => {
    const t = q.data?.trend ?? []
    return {
      grid: { left: 40, right: 40, top: 36, bottom: 28 },
      legend: { top: 0, left: 0, itemWidth: 14, itemHeight: 4, textStyle: { fontSize: 12, color: colors.text } },
      tooltip: { trigger: 'axis' },
      xAxis: { type: 'category', data: t.map((w) => `${Number(w.week.slice(5, 7))}/${Number(w.week.slice(8, 10))}`),
        axisLabel: { color: colors.text2, fontSize: 11 }, axisLine: { lineStyle: { color: colors.border } } },
      yAxis: { type: 'value', min: 0, max: 1, axisLabel: { color: colors.text2, fontSize: 11 }, splitLine: { lineStyle: { color: '#F1F2F4' } } },
      series: [
        { name: '预测准确率', type: 'line', data: t.map((w) => w.pred_accuracy), connectNulls: true,
          lineStyle: { width: 2.2, color: colors.primary }, itemStyle: { color: colors.primary } },
        { name: 'F 值（越低越好）', type: 'line', data: t.map((w) => w.class_f), connectNulls: true,
          lineStyle: { width: 2.2, color: '#D97706', type: [5, 4] }, itemStyle: { color: '#D97706' } },
      ],
    }
  }, [q.data])
  if (q.isLoading) return <Loading rows={10} />
  if (q.error || !q.data) return <ErrorState error={q.error} onRetry={() => q.refetch()} />
  const d = q.data
  const k = d.kpis
  const maxMis = Math.max(1, ...d.misconceptions.map((m) => m.students))
  return (
    <div data-testid="t-overview" className={q.isPlaceholderData || heat.isPlaceholderData ? 'stale on' : 'stale'}>
      <div className="page-h"><h1>班级概览</h1>
        <Segmented value={group} onChange={(v) => setGroup(String(v))} options={GROUP_OPTIONS} data-testid="group-filter" /></div>
      <div className="grid g5">
        <div className="card kpi" data-testid="kpi-active"><div className="kpi-t">本周活跃</div>
          <div className="kpi-n">{k.active.value}<small>/ {k.active.total}</small></div>
          <div className="kpi-d"><Delta value={k.active.value} prev={k.active.prev} kind="count" /></div></div>
        <div className="card kpi" data-testid="kpi-completion"><div className="kpi-t">作业完成率</div>
          <div className="kpi-n">{pct(k.completion.value)}</div>
          <div className="kpi-d"><Delta value={k.completion.value} prev={k.completion.prev} kind="pct" /></div></div>
        <div className="card kpi" data-testid="kpi-pred"><div className="kpi-t">全班预测准确率</div>
          <div className="kpi-n">{pct(k.pred_accuracy.value)}</div>
          <div className="kpi-d"><Delta value={k.pred_accuracy.value} prev={k.pred_accuracy.prev} kind="pct" /></div></div>
        <div className="card kpi" data-testid="kpi-f"><div className="kpi-t">全班 F 值（脆弱率）</div>
          <div className="kpi-n">{num(k.class_f.value)}</div>
          <div className="kpi-d"><Delta value={k.class_f.value} prev={k.class_f.prev} kind="num" lowerBetter /></div></div>
        <div className="card kpi" data-testid="kpi-hint"><div className="kpi-t">平均提示等级</div>
          <div className="kpi-n">{num(k.avg_hint.value, 1)}</div>
          <div className="kpi-d"><Delta value={k.avg_hint.value} prev={k.avg_hint.prev} kind="num" lowerBetter /></div></div>
      </div>

      <div className="grid g-5-7" style={{ marginTop: 16 }}>
        <div className="card"><div className="card-h">近 8 周趋势 <small>{group === 'control' ? '对照组没有预测' : '按北京时间自然周'}</small></div>
          <div className="card-b"><EChart option={trendOption} height={230} label="近 8 周趋势" testId="t-trend" /></div></div>
        <div className="card"><div className="card-h">常见误区 Top 5 <small><span className="src p">预测误区</span><span className="src j">裁判标签</span></small></div>
          <div className="card-b" data-testid="t-mis-top">
            {d.misconceptions.length === 0 && <div className="muted">还没有误区记录</div>}
            {d.misconceptions.map((m) => (
              <div key={m.code} className="hbar" onClick={() => navigate(`/teacher/classes/${cid}/misconceptions?code=${m.code}`)}>
                <span>{m.label}<span className={`src ${m.source === 'prediction' ? 'p' : 'j'}`}>{m.source === 'prediction' ? '预测' : '裁判'}</span></span>
                <span className="track"><i style={{ width: `${(m.students / maxMis) * 100}%`, background: m.source === 'prediction' ? 'var(--q-fragile)' : 'var(--c-primary)' }} /></span>
                <span style={{ textAlign: 'right' }}>{m.students} 人</span>
              </div>
            ))}
          </div></div>
      </div>

      <div className="grid g-7-5" style={{ marginTop: 16 }}>
        <div className="card"><div className="card-h">学情热力图（节选） <Button type="link" size="small" onClick={() => navigate(`/teacher/classes/${cid}/heatmap`)}>查看全部 →</Button></div>
          <div className="card-b">{heat.data && <HeatmapChart data={{ ...heat.data, rows: heat.data.rows.slice(0, 12) }} who={who} height={316} compact />}</div></div>
        <div className="card list risk"><div className="card-h">需要关注的学生 <small>{d.alerts.length} 人</small></div>
          <div className="card-b" data-testid="t-alerts" style={{ maxHeight: 360, overflow: 'auto' }}>
            {d.alerts.length === 0 && <div className="muted">暂时没有需要特别关注的学生</div>}
            {d.alerts.map((a) => (
              <div className="row" key={a.user_id}>
                <span className="dot" style={{ background: a.reasons[0].rule === 3 ? '#D1D5DB' : a.reasons[0].rule === 4 ? 'var(--c-error)' : a.reasons[0].rule === 2 ? 'var(--q-concept)' : 'var(--q-fragile)' }} />
                <div className="main"><b>{who(a)}</b><span>{a.reasons.map((r) => r.text).join('；')}</span></div>
                <Button size="small" onClick={() => navigate(`/teacher/classes/${cid}/students/${a.user_id}`)}>查看详情</Button>
              </div>
            ))}
          </div></div>
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <div className="card-h">题目速览 <small>作业中的题目</small></div>
        <table className="tbl" data-testid="t-problems">
          <thead><tr><th>题目</th><th>知识点</th><th className="r">通过率</th><th className="r">F 值</th><th className="r">盲改率</th>
            <th className="r">平均提示等级</th><th className="r">平均用时</th></tr></thead>
          <tbody>{d.problems.map((p) => (
            <tr key={p.problem_id} className="click" onClick={() => navigate(`/teacher/classes/${cid}/problems/${p.problem_id}`)}>
              <td>{p.title}</td><td>{p.knowledge_points.slice(0, 2).map((x) => <span key={x} className="chip" style={{ marginRight: 4 }}>{x}</span>)}</td>
              <td className="r">{pct(p.pass_rate)}</td>
              <td className={`r ${p.f_value !== null && p.f_value >= 0.35 ? 'warn' : ''}`}>{num(p.f_value)}</td>
              <td className="r">{pct(p.blind_rate)}</td><td className="r">{num(p.avg_hint_level, 1)}</td>
              <td className="r">{duration(p.avg_minutes)}</td>
            </tr>))}</tbody>
        </table>
      </div>
    </div>
  )
}
