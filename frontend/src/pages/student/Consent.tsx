// S1 知情同意（/student/consent）。文本版本见后端 CONSENT_VERSION；阶段 6 定稿
import { Button } from 'antd'
import { useNavigate } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { post } from '../../api/client'
import { useMe } from '../../api/hooks'
import type { Me } from '../../api/types'
import { Brand } from '../../components/StudentLayout'
import '../Login.css'

export default function Consent() {
  const me = useMe()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [busy, setBusy] = useState(false)
  const version = me.data?.consent?.current_version ?? 'v1-draft'
  const choose = async (accept: boolean) => {
    setBusy(true)
    try {
      const next = await post<Me>('/api/auth/consent', { accept, version })
      qc.setQueryData(['me'], next)
      navigate('/student', { replace: true })
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="card consent" data-testid="consent">
      <Brand />
      <h1 style={{ marginTop: 20 }}>参与研究的知情同意</h1>
      <p className="muted">版本 {version}（草案）</p>
      <h2>收集哪些数据</h2>
      <p>你在平台上的操作记录：提交的代码、仿真结果、你填写的预测、查看波形和提示的记录、探究步骤里写的解释。</p>
      <h2>用于什么研究</h2>
      <p>研究“先预测、再仿真对照”的学习方式能否帮助大家理解 Verilog 代码与真实电路的对应关系，以及智能提示的效果。</p>
      <h2>如何匿名</h2>
      <ul>
        <li>研究导出的数据只用随机生成的匿名编号，不含姓名和学号</li>
        <li>不做排名，也不和同学比较</li>
      </ul>
      <h2>你的选择</h2>
      <p>是否参与研究完全自愿，不影响课程成绩。选择“暂不参与研究”也可以照常使用全部功能，只是你的数据不会进入研究导出。之后可以随时联系任课教师撤回同意。</p>
      <div className="consent-actions">
        <Button type="primary" onClick={() => choose(true)} loading={busy} data-testid="consent-accept">同意并开始</Button>
        <Button onClick={() => choose(false)} disabled={busy} data-testid="consent-decline">暂不参与研究</Button>
      </div>
    </div>
  )
}
