// 学生端顶部导航：学习首页 / 题目 / 复习 / 我的学情
import { Dropdown } from 'antd'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useEffect } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { post } from '../api/client'
import { useMe, useReview } from '../api/hooks'
import { reporter } from '../lib/events'
import './StudentLayout.css'

export function Brand() {
  return <div className="brand"><span className="logo">V</span>数字电路 · Verilog 学习平台</div>
}

export default function StudentLayout() {
  const me = useMe()
  const review = useReview()
  const location = useLocation()
  const navigate = useNavigate()
  const qc = useQueryClient()
  useEffect(() => { reporter.track('page.view', { payload: { route: location.pathname } }) }, [location.pathname])
  const name = me.data?.user.display_name ?? ''
  const due = review.data?.items.length ?? 0
  const logout = async () => {
    await reporter.flush()
    await post('/api/auth/logout')
    qc.clear()
    navigate('/login')
  }
  return (
    <div className="student">
      <header className="topnav">
        <Brand />
        <nav aria-label="学生端导航">
          <NavLink to="/student" end>学习首页</NavLink>
          <NavLink to="/student/problems">题目</NavLink>
          <NavLink to="/student/review">复习{due > 0 && <span className="chip blue nav-count">{due}</span>}</NavLink>
          <NavLink to="/student/report">我的学情</NavLink>
        </nav>
        <Dropdown menu={{ items: [{ key: 'out', label: '退出登录', onClick: logout }] }}>
          <button className="me" aria-label="账号菜单"><span className="avatar">{name.slice(0, 1)}</span>{name}</button>
        </Dropdown>
      </header>
      <Outlet />
    </div>
  )
}
