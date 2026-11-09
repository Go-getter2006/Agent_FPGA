// S5 我的学情（/student/report）。只显示自己的数据，不显示排名、不和同学比较
import { Button } from 'antd'
import { Link, useNavigate } from 'react-router-dom'
import { useReport } from '../../api/hooks'
import { Empty, ErrorState, KpiCard, Loading, MASTERY_LEGEND, MasteryMap } from '../../components/Common'
import TrendChart from '../../components/TrendChart'
import { beijingTime, percent } from '../../lib/format'
import './Student.css'

export default function Report() {
  const q = useReport()
  const navigate = useNavigate()
  if (q.isLoading) return <Loading />
  if (q.error || !q.data) return <ErrorState error={q.error} onRetry={() => q.refetch()} />
  const d = q.data
  const delta = d.kpis.waveform_accuracy_delta
  return (
    <div className="page" data-testid="report">
      <div className="page-h"><h1>我的学情</h1><span className="muted">近两周 · 只显示你自己的数据</span></div>
      <div className="grid g4 responsive">
        <KpiCard testId="kpi-mastered" title="真掌握的知识点" value={d.kpis.mastered} unit={`/ ${d.kpis.total_kps}`} icon="●" iconBg="#DBEAFE" iconColor="#2563EB"
          foot={<span className="muted">写得对，也能预测对</span>} />
        <KpiCard testId="kpi-fragile" title="会写但没把握" value={d.kpis.fragile} unit="个知识点" icon="◐" iconBg="#FEF3C7" iconColor="#B45309"
          foot={<Link to="/student/review">去复习 →</Link>} />
        <KpiCard testId="kpi-accuracy" title="波形预测准确率" value={percent(d.kpis.waveform_accuracy)} icon="∿" iconBg="#DCFCE7" iconColor="#16A34A"
          foot={delta === null ? <span className="muted">近两周</span> : <span className={delta >= 0 ? 'ok' : 'warn'}>{delta >= 0 ? '↑' : '↓'} {percent(Math.abs(delta))} 比上两周</span>} />
        <KpiCard testId="kpi-tb" title="testbench 抓 bug" value={d.kpis.tb ? d.kpis.tb.caught : '—'} unit={d.kpis.tb ? `/ ${d.kpis.tb.total}` : undefined}
          icon="⚑" iconBg="#EDE9FE" iconColor="#7C3AED" foot={<span className="muted">{d.kpis.tb ? `最近一道创作题：${d.kpis.tb.title}` : '完成创作题后显示'}</span>} />
      </div>

      <div className="grid g-7-5 responsive" style={{ marginTop: 16 }}>
        <div className="card">
          <div className="card-h">知识点掌握图 <small>按课程顺序</small></div>
          <div className="card-b"><MasteryMap items={d.mastery} />{MASTERY_LEGEND}</div>
        </div>
        <div className="card">
          <div className="card-h">预测准确率趋势 <small>按周</small></div>
          <div className="card-b">{d.trend.length ? <TrendChart data={d.trend} /> : <Empty title="还没有预测记录">做题时先预测，再运行，这里会画出你的进步</Empty>}</div>
        </div>
      </div>

      <div className="grid g-5-4-4 responsive" style={{ marginTop: 16 }}>
        <div className="card list">
          <div className="card-h">会写但没把握 <small>代码对了，预测没对上</small></div>
          <div className="card-b" data-testid="fragile-list">
            {d.fragile_list.length === 0 && <Empty title="暂时没有">代码对、预测也对，继续保持</Empty>}
            {d.fragile_list.map((f) => (
              <div className="row" key={f.problem_id}><span className="dot" style={{ background: 'var(--q-fragile)' }} />
                <div className="main"><b>{f.title}</b><span>{f.reason}</span></div>
                <Button size="small" onClick={() => navigate('/student/review')}>去复习</Button></div>
            ))}
          </div>
        </div>
        <div className="card list">
          <div className="card-h">待复习 <small>间隔 1 / 3 / 7 / 14 天</small></div>
          <div className="card-b">
            {d.review_upcoming.length === 0 && <Empty title="复习队列是空的">落在“会写但没把握”或“概念未通”的题会自动加进来</Empty>}
            {d.review_upcoming.map((r) => (
              <div className="row" key={r.id}><span className="dot" style={{ background: 'var(--c-primary)' }} />
                <div className="main"><b>预测：{r.title}{r.kind === 'hardware' ? '（硬件）' : '（波形）'}</b>
                  <span>{beijingTime(r.due_at)} 到期 · 第 {r.box} 轮</span></div></div>
            ))}
          </div>
        </div>
        <div className="card list">
          <div className="card-h">最近遇到的误区</div>
          <div className="card-b" data-testid="misconceptions">
            {d.misconceptions.length === 0 && <Empty title="还没有发现误区" />}
            {d.misconceptions.map((m) => (
              <div className="row" key={m.code}><div className="main"><b>{m.label}</b>
                <span>出现 {m.count} 次 · 最近：{m.latest_problem}</span></div>
                <Button type="link" size="small" onClick={() => navigate(`/student/problems/${m.practice_problem_id}`)}>去练习</Button></div>
            ))}
            {d.badges.length > 0 && (
              <div className="badges" style={{ marginTop: 12 }} data-testid="badges">
                {d.badges.map((b) => <div className="badge" key={b.code}><span className="ic">✓</span>{b.label}</div>)}
              </div>
            )}
          </div>
        </div>
      </div>
      <p className="note">这里不显示排名，也不和同学比较。</p>
    </div>
  )
}
