// S1 登录（/login）
import { Button, Form, Input } from 'antd'
import { useNavigate } from 'react-router-dom'
import { useState } from 'react'
import { ApiError } from '../api/client'
import { useLogin } from '../api/hooks'
import { Brand } from '../components/StudentLayout'
import './Login.css'

export function homeFor(me: { user: { role: string }; consent: { required: boolean } | null }) {
  if (me.user.role === 'student') return me.consent?.required ? '/student/consent' : '/student'
  return '/teacher'
}

export default function Login() {
  const navigate = useNavigate()
  const login = useLogin()
  const [error, setError] = useState<string | null>(null)
  const onFinish = async (v: { login_name: string; password: string }) => {
    setError(null)
    try {
      const me = await login.mutateAsync(v)
      navigate(homeFor(me), { replace: true })
    } catch (e) {
      setError(e instanceof ApiError ? e.message : '登录失败，请重试')
    }
  }
  return (
    <div className="login-wrap">
      <div className="card login-card">
        <Brand />
        <h1>登录</h1>
        <Form layout="vertical" onFinish={onFinish} requiredMark={false}>
          <Form.Item label="学号 / 工号" name="login_name" rules={[{ required: true, message: '请输入学号或工号' }]}>
            <Input autoComplete="username" data-testid="login-name" />
          </Form.Item>
          <Form.Item label="密码" name="password" rules={[{ required: true, message: '请输入密码' }]}>
            <Input.Password autoComplete="current-password" data-testid="login-password" />
          </Form.Item>
          {error && <div className="login-err" role="alert">{error}</div>}
          <Button type="primary" htmlType="submit" block loading={login.isPending} data-testid="login-submit">登录</Button>
        </Form>
        <p className="muted login-foot">忘记密码请联系任课教师重置</p>
      </div>
    </div>
  )
}
