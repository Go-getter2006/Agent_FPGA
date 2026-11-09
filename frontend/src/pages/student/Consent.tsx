// S1 知情同意（/student/consent）。正文和版本号来自后端 backend/app/data/consent.md（GET /api/auth/consent）
import { Alert, Button, Skeleton } from 'antd'
import { useNavigate } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { get, post } from '../../api/client'
import { useMe } from '../../api/hooks'
import type { Me } from '../../api/types'
import { Brand } from '../../components/StudentLayout'
import Markdown from '../../lib/markdown'
import '../Login.css'

export default function Consent() {
  const me = useMe()
  const text = useQuery({ queryKey: ['consent-text'], queryFn: () => get<{ version: string; markdown: string }>('/api/auth/consent') })
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [busy, setBusy] = useState(false)
  const previous = me.data?.consent
  const choose = async (accept: boolean) => {
    if (!text.data) return
    setBusy(true)
    try {
      const next = await post<Me>('/api/auth/consent', { accept, version: text.data.version })
      qc.setQueryData(['me'], next)
      navigate('/student', { replace: true })
    } catch {
      // 版本在阅读期间更新了：重新拉取正文
      await text.refetch()
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="card consent" data-testid="consent">
      <Brand />
      {previous && previous.status !== 'pending' && previous.version && (
        <Alert type="info" showIcon style={{ marginTop: 16 }} data-testid="consent-updated"
          message="知情同意书有更新，请重新阅读并选择"
          description={`你之前在版本 ${previous.version} 上的选择是“${previous.status === 'accepted' ? '同意' : '暂不参与'}”。`} />
      )}
      {text.data ? (
        <>
          <Markdown text={text.data.markdown} />
          <p className="muted">版本 {text.data.version}</p>
        </>
      ) : <Skeleton active paragraph={{ rows: 10 }} style={{ marginTop: 20 }} />}
      <div className="consent-actions">
        <Button type="primary" onClick={() => choose(true)} loading={busy} disabled={!text.data} data-testid="consent-accept">同意并开始</Button>
        <Button onClick={() => choose(false)} disabled={busy || !text.data} data-testid="consent-decline">暂不参与研究</Button>
      </div>
    </div>
  )
}
