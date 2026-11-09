// 教师端布局：左侧菜单 220px + 顶栏（班级选择器、分组人数、匿名显示开关）+ 内容区
import { Alert, Select, Switch } from 'antd'
import { createContext, useContext, useEffect, useState } from 'react'
import { NavLink, Navigate, Outlet, useNavigate, useParams } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { post } from '../../api/client'
import { useClasses, useStatus } from '../../api/teacher'
import { ErrorState, Loading } from '../../components/Common'
import './Teacher.css'

interface Ctx { cid: number; anonymous: boolean; who: (r: { alias: string; name?: string | null }) => string }
const TeacherCtx = createContext<Ctx>({ cid: 0, anonymous: true, who: (r) => r.alias })
export const useTeacher = () => useContext(TeacherCtx)

export function TeacherIndex() {
  const q = useClasses()
  if (q.isLoading) return <Loading />
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />
  const first = q.data?.classes[0]
  if (!first) return <div className="page"><Alert type="info" showIcon message="还没有班级" description="请联系管理员创建班级后再来。" /></div>
  return <Navigate to={`/teacher/classes/${first.id}`} replace />
}

const MENU: (string | [string, string, string])[] = [
  ['', '▦', '班级概览'], ['heatmap', '▤', '学情热力图'], ['misconceptions', '◎', '误区分析'],
  ['problems', '▥', '题目分析'], ['students', '☰', '学生详情'],
  '教学', ['assignments', '✎', '作业与题库'], ['roster', '☷', '班级管理'],
  '研究', ['research', '⚗', '实验分组与导出'],
]

export default function TeacherLayout() {
  const { cid = '' } = useParams()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const classes = useClasses()
  const status = useStatus()
  const [anonymous, setAnonymous] = useState(true)
  useEffect(() => { setAnonymous(true) }, [cid])
  const cls = classes.data?.classes.find((c) => String(c.id) === cid)
  const toggle = async (on: boolean) => {
    await post(`/api/teacher/classes/${cid}/anonymity`, { anonymous: on })   // 关闭匿名要写一条事件
    setAnonymous(on)
    await qc.invalidateQueries()
  }
  const who = (r: { alias: string; name?: string | null }) => (!anonymous && r.name ? `${r.name}（${r.alias}）` : r.alias)
  const groups = cls?.groups ?? {}
  return (
    <TeacherCtx.Provider value={{ cid: Number(cid), anonymous, who }}>
      <div className="t-wrap" data-testid="teacher">
        <aside className="side" aria-label="教师端菜单">
          <div className="brand"><span className="logo">V</span>教师端</div>
          {MENU.map((m) => typeof m === 'string'
            ? <div key={m} className="grp">{m}</div>
            : <NavLink key={m[0]} to={`/teacher/classes/${cid}${m[0] ? `/${m[0]}` : ''}`} end={m[0] === ''}>
                <i aria-hidden="true">{m[1]}</i>{m[2]}</NavLink>)}
        </aside>
        <div className="t-main">
          <header className="t-top">
            <Select value={cls?.id} style={{ minWidth: 220 }} aria-label="选择班级" data-testid="class-select"
              options={(classes.data?.classes ?? []).map((c) => ({ value: c.id, label: `${c.name} · ${c.term}` }))}
              onChange={(v) => navigate(`/teacher/classes/${v}`)} />
            <span className="muted" style={{ fontSize: 13 }}>
              {groups.treatment ? `实验组 ${groups.treatment} 人` : ''}{groups.treatment && groups.control ? ' · ' : ''}
              {groups.control ? `对照组 ${groups.control} 人` : ''}{groups.none ? `${groups.treatment || groups.control ? ' · ' : ''}未分组 ${groups.none} 人` : ''}
            </span>
            <label className="switch">匿名显示 <Switch checked={anonymous} onChange={toggle} data-testid="anonymous-switch" /></label>
            <button className="t-logout" onClick={async () => { await post('/api/auth/logout'); qc.clear(); navigate('/login') }}>退出</button>
          </header>
          {status.data?.llm.budget_exceeded && (
            <Alert banner type="warning" message={`今日大模型费用已达预算（${status.data.llm.spent_today_cny.toFixed(2)} / ${status.data.llm.daily_budget_cny} 元），学生端今天剩余时间改用规则提示`} />
          )}
          <main className="page t-page"><Outlet /></main>
        </div>
      </div>
    </TeacherCtx.Provider>
  )
}
