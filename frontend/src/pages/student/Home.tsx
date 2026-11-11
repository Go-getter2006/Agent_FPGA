// S2 学习首页（/student）
import { Button, Progress } from 'antd'
import { Link, useNavigate } from 'react-router-dom'
import { useHome, useProblems } from '../../api/hooks'
import { Empty, ErrorState, Loading, MasteryMap, QuadrantBadge } from '../../components/Common'
import { STATUS_LABEL, STEP_LABEL, TAG_LABEL, beijingTime } from '../../lib/format'
import './Student.css'

export default function Home() {
  const q = useHome()
  const all = useProblems({})                  // 没有布置作业时，按题目顺序推荐接下来做的题
  const navigate = useNavigate()
  if (q.isLoading) return <Loading />
  if (q.error || !q.data) return <ErrorState error={q.error} onRetry={() => q.refetch()} />
  const d = q.data
  return (
    <div className="page" data-testid="home">
      <div className="page-h"><h1>你好，{d.user.display_name}</h1><span className="muted">今天也来练一练</span></div>
      <div className="card beginner-banner" data-testid="beginner-banner">
        <div className="card-b">
          <div>
            <b>第一次学 Verilog 和 FPGA？</b>
            <div className="muted">先花半小时学完 6 节新手入门课，再按顺序做 4 道入门题：与门 → 选择器 → 寄存器 → 让 LED 闪起来。</div>
          </div>
          <div className="bb-actions">
            <Button type="primary" onClick={() => navigate('/student/learn')} data-testid="start-learn">开始入门课</Button>
            <Button onClick={() => navigate('/student/problems/b1_and_gate')}>直接做第 1 道入门题</Button>
          </div>
        </div>
      </div>
      <div className="grid home-grid responsive">
        <div className="card">
          <div className="card-h">{d.assignments.length ? '本周作业' : '接下来做'} {d.continue && <Button type="primary" size="small" onClick={() => navigate(`/student/problems/${d.continue!.problem_id}`)}
            data-testid="continue">继续上次：{d.continue.title} · {STEP_LABEL[d.continue.step]}</Button>}</div>
          <div className="card-b">
            {d.assignments.length === 0 && (
              <div className="assign" data-testid="next-problems">
                <div className="assign-items">
                  {(all.data?.items ?? []).filter((p) => p.status !== 'passed' && p.status !== 'mastered').slice(0, 6).map((p) => (
                    <Link key={p.id} to={`/student/problems/${p.id}`} className={`assign-item st-${p.status}`}>
                      {p.title}<span>{STATUS_LABEL[p.status]}</span></Link>
                  ))}
                </div>
                <div className="muted" style={{ marginTop: 8, fontSize: 12 }}>按题目列表的顺序推荐，入门题在前。<Link to="/student/problems">看全部题目</Link></div>
              </div>
            )}
            {d.assignments.map((a) => (
              <div key={a.id} className="assign">
                <div className="assign-h"><b>{a.title}</b><span className="muted">截止 {beijingTime(a.due_at)}</span></div>
                <Progress percent={a.total ? Math.round((a.done / a.total) * 100) : 0} size="small" format={() => `${a.done}/${a.total}`} />
                <div className="assign-items">
                  {a.problems.map((p) => (
                    <Link key={p.id} to={`/student/problems/${p.id}`} className={`assign-item st-${p.status}`}>
                      {p.title}<span>{STATUS_LABEL[p.status]}</span></Link>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
        <div className="col-stack">
          <div className="card">
            <div className="card-h">待复习</div>
            <div className="card-b review-box">
              <div><span className="big">{d.review_due}</span> 条今天到期</div>
              <Button type="primary" disabled={!d.review_due} onClick={() => navigate('/student/review')} data-testid="start-review">开始复习</Button>
            </div>
          </div>
          <div className="card">
            <div className="card-h">最近一次反馈</div>
            <div className="card-b">
              {!d.last_feedback && <Empty title="还没有提交过">做完第一道题，这里会显示结果</Empty>}
              {d.last_feedback && (
                <div>
                  <Link to={`/student/problems/${d.last_feedback.problem_id}`}><b>{d.last_feedback.title}</b></Link>
                  <span className="muted" style={{ marginLeft: 8, fontSize: 12 }}>{beijingTime(d.last_feedback.created_at)}</span>
                  <div style={{ marginTop: 8 }}><QuadrantBadge quadrant={d.last_feedback.quadrant} /></div>
                  <div className="muted" style={{ fontSize: 12, marginTop: 6 }}>
                    {d.last_feedback.sim_ok ? '仿真和期望一致' : '仿真和期望对不上'}
                    {d.last_feedback.tags.filter((t) => t !== 'sim_mismatch').map((t) => `；${TAG_LABEL[t] ?? t}`).join('')}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
      <div className="card" style={{ marginTop: 16 }}>
        <div className="card-h">知识点掌握图 <Link to="/student/report" style={{ fontSize: 13, fontWeight: 400 }}>查看我的学情 →</Link></div>
        <div className="card-b"><MasteryMap items={d.mastery} compact /></div>
      </div>
    </div>
  )
}
