// 通用小组件：象限徽章、页面四种状态、KPI 卡、掌握图
import { Button, Result, Skeleton, Tooltip } from 'antd'
import type { ReactNode } from 'react'
import { levelStyle, quadrantStyle } from '../theme/tokens'
import { QUADRANT_HINT } from '../lib/format'
import type { Level, MasteryItem, Quadrant } from '../api/types'
import { ApiError } from '../api/client'

export function QuadrantBadge({ quadrant, withHint = true }: { quadrant: Quadrant | null; withHint?: boolean }) {
  if (!quadrant || quadrant === 'none') {
    return <span className="qbadge q-none" data-testid="quadrant-badge">未判定 ?</span>
  }
  const q = quadrantStyle[quadrant]
  const badge = (
    <span className="qbadge" data-testid="quadrant-badge" data-quadrant={quadrant}
      style={{ background: q.bg, color: q.color }} aria-label={`本题状态：${q.name}`}>
      <i style={{ fontStyle: 'normal' }}>{q.icon}</i>{q.name}
    </span>
  )
  return withHint ? <Tooltip title={QUADRANT_HINT[quadrant]}>{badge}</Tooltip> : badge
}

export function Loading({ rows = 6 }: { rows?: number }) {
  return <div style={{ padding: 24 }} aria-busy="true"><Skeleton active paragraph={{ rows }} /></div>
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const message = error instanceof ApiError ? error.message : '页面加载失败了'
  return (
    <Result status="warning" title="出了点问题" subTitle={message}
      extra={onRetry && <Button type="primary" onClick={onRetry}>重试</Button>} />
  )
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div style={{ padding: '32px 16px', textAlign: 'center', color: 'var(--c-text-2)' }} data-testid="empty">
      <div style={{ fontSize: 15, color: 'var(--c-text)', marginBottom: 8 }}>{title}</div>
      {children}
    </div>
  )
}

export function KpiCard({ title, value, unit, foot, icon, iconBg, iconColor, testId }: {
  title: string; value: ReactNode; unit?: string; foot?: ReactNode; icon?: string; iconBg?: string; iconColor?: string
  testId?: string
}) {
  return (
    <div className="card kpi" data-testid={testId}>
      {icon && <span className="kpi-icon" style={{ background: iconBg, color: iconColor }} aria-hidden="true">{icon}</span>}
      <div className="kpi-t">{title}</div>
      <div className="kpi-n">{value}{unit && <small>{unit}</small>}</div>
      {foot && <div className="kpi-d">{foot}</div>}
    </div>
  )
}

export function LevelLabel({ level }: { level: Level }) {
  const l = levelStyle[level]
  return <span className="lvl">{l.icon} {l.name}</span>
}

export function MasteryMap({ items, compact = false }: { items: MasteryItem[]; compact?: boolean }) {
  return (
    <div className={compact ? 'mmap compact' : 'mmap'} data-testid="mastery-map">
      {items.map((m) => (
        <Tooltip key={m.code} title={m.attempts ? `最近 ${m.attempts} 次带预测的尝试` : '还没有带预测的尝试'}>
          <div className={`kp ${levelStyle[m.level].className}`} data-level={m.level} aria-label={`${m.name}：${levelStyle[m.level].name}`}>
            <div className="name">{m.name}</div>
            <LevelLabel level={m.level} />
          </div>
        </Tooltip>
      ))}
    </div>
  )
}

export const MASTERY_LEGEND = (
  <div className="mlegend">
    <span>● 真掌握：写对且预测对</span><span>◐ 会写但没把握：写对了，但预测不准</span>
    <span>◌ 学习中</span><span>– 未开始</span>
  </div>
)
