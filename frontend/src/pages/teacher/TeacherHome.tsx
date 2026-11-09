// 教师端在阶段 5 实现；这里先给一个占位页
import { Button, Result } from 'antd'
import { useNavigate } from 'react-router-dom'
import { post } from '../../api/client'

export default function TeacherHome() {
  const navigate = useNavigate()
  return (
    <Result status="info" title="教师端即将开放" subTitle="班级概览、学情热力图等页面在下一阶段完成。"
      extra={<Button onClick={async () => { await post('/api/auth/logout'); navigate('/login') }}>退出登录</Button>} />
  )
}
