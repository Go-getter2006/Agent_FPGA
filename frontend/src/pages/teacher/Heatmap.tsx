// T2 学情热力图：行 = 学生，列 = 知识点，格子颜色 = 掌握等级；点格子看该生在该知识点上的最近尝试
import { Button, DatePicker, Drawer, Segmented } from 'antd'
import type { Dayjs } from 'dayjs'
import { useMemo, useRef, useState } from 'react'
import { qs, useT, type Heatmap as HM } from '../../api/teacher'
import { ErrorState, Loading, QuadrantBadge } from '../../components/Common'
import EChart, { type EChartHandle } from '../../components/EChart'
import { beijingTime, percent, TAG_LABEL } from '../../lib/format'
import { colors } from '../../theme/tokens'
import { useTeacher } from './TeacherLayout'

export const GROUP_OPTIONS = [{ label: '全部', value: '' }, { label: '实验组', value: 'treatment' }, { label: '对照组', value: 'control' }]
const LEVELS = ['not_started', 'learning', 'fragile', 'mastered'] as const
const LEVEL_NAME = { not_started: '未开始', learning: '学习中', fragile: '会写但没把握', mastered: '真掌握' }
const LEVEL_COLOR = { not_started: '#E5E7EB', learning: '#BFDBFE', fragile: '#D97706', mastered: '#2563EB' }
// 热力图列名用短名（与原型一致）
export const KP_SHORT: Record<string, string> = {
  comb_assign: '组合', comb_always: '组合always', blocking: '阻塞/非阻塞', sequential: '时序', reset: '复位',
  counter: '计数器', fsm: '状态机', width: '位宽', hierarchy: '例化', testbench: 'testbench', parallel: '并行',
}

export function HeatmapChart({ data, who, height, compact = false, onCell, chartRef }: {
  data: HM; who: (r: { alias: string; name?: string | null }) => string; height?: number; compact?: boolean
  onCell?: (row: HM['rows'][number], kp: string) => void; chartRef?: React.Ref<EChartHandle>
}) {
  const option = useMemo(() => {
    const kps = data.knowledge_points
    const rows = data.rows
    const values = rows.flatMap((r, y) => kps.map((k, x) => {
      const c = r.cells[k.code]
      return [x, y, LEVELS.indexOf(c.level), c.attempts, c.f_value]
    }))
    return {
      grid: { left: compact ? 52 : 120, right: 12, top: compact ? 26 : 40, bottom: 40 },
      tooltip: { formatter: (p: any) => {
        const [x, y, lv, n, f] = p.data
        return `${who(rows[y])} · ${kps[x].name}<br/>${LEVEL_NAME[LEVELS[lv]]}；带预测的尝试 ${n} 次；F ${f === null ? '—' : f.toFixed(2)}`
      } },
      xAxis: { type: 'category', data: kps.map((k) => (compact ? KP_SHORT[k.code] ?? k.name : k.name.replace(/（.*）/, ''))), position: 'top',
        axisLabel: { interval: 0, fontSize: 11, color: colors.text2, rotate: compact ? 0 : 30 },
        axisTick: { show: false }, axisLine: { show: false } },
      yAxis: { type: 'category', data: rows.map((r) => who(r)), inverse: true,
        axisLabel: { fontSize: 11.5, fontFamily: 'JetBrains Mono, monospace', color: colors.text }, axisTick: { show: false }, axisLine: { show: false } },
      visualMap: { type: 'piecewise', dimension: 2, orient: 'horizontal', bottom: 0, left: compact ? 52 : 120,
        pieces: LEVELS.map((l, i) => ({ value: i, label: LEVEL_NAME[l], color: LEVEL_COLOR[l] })).reverse(),
        textStyle: { fontSize: 11.5, color: colors.text2 }, itemWidth: 12, itemHeight: 12 },
      series: [{ type: 'heatmap', data: values, itemStyle: { borderColor: '#fff', borderWidth: 2, borderRadius: 3 },
        label: { show: true, fontSize: 10, color: '#fff', formatter: (p: any) => (p.data[2] === 2 ? '◐' : p.data[2] === 3 ? '●' : '') } }],
    }
  }, [data, who, compact])
  const onClick = useMemo(() => onCell ? (p: any) => onCell(data.rows[p.data[1]], data.knowledge_points[p.data[0]].code) : undefined, [data, onCell])
  const h = height ?? Math.max(240, data.rows.length * 28 + 110)
  return <EChart ref={chartRef} option={option} height={h} onClick={onClick} label="学情热力图" testId="heatmap-chart" />
}

export default function Heatmap() {
  const { cid, anonymous, who } = useTeacher()
  const [group, setGroup] = useState('')
  const [range, setRange] = useState<[Dayjs | null, Dayjs | null] | null>(null)
  const [cell, setCell] = useState<{ row: HM['rows'][number]; kp: string } | null>(null)
  const chart = useRef<EChartHandle>(null)
  const start = range?.[0]?.format('YYYY-MM-DDT00:00:00')
  const end = range?.[1]?.add(1, 'day').format('YYYY-MM-DDT00:00:00')
  const q = useT<HM>(['t-heat', cid, group, anonymous, start, end], `/api/teacher/classes/${cid}/heatmap${qs({ group, anonymous, start, end })}`)
  const detail = useT<{ attempts: any[] }>(['t-cell', cid, cell?.row.user_id, cell?.kp],
    `/api/teacher/classes/${cid}/heatmap/cell${qs({ user_id: cell?.row.user_id, kp: cell?.kp })}`, !!cell)
  const exportImage = () => {
    const url = chart.current?.toDataURL()
    if (!url) return
    const a = document.createElement('a')
    a.href = url
    a.download = `heatmap_class${cid}${anonymous ? '_anonymous' : ''}.svg`
    a.click()
  }
  return (
    <div data-testid="t-heatmap" className={q.isPlaceholderData ? 'stale on' : 'stale'}>
      <div className="page-h"><h1>学情热力图</h1><span className="muted">格子颜色 = 掌握等级；点格子看最近的尝试</span></div>
      <div className="card"><div className="card-h">
        <span className="filters"><Segmented value={group} onChange={(v) => setGroup(String(v))} options={GROUP_OPTIONS} />
          <DatePicker.RangePicker value={range as any} onChange={(v) => setRange(v as any)} placeholder={['开始日期', '结束日期']} /></span>
        <Button onClick={exportImage} data-testid="export-image">导出图片{anonymous ? '（匿名）' : ''}</Button></div>
        <div className="card-b">
          {q.isLoading && <Loading />}
          {q.error && <ErrorState error={q.error} onRetry={() => q.refetch()} />}
          {q.data && <HeatmapChart data={q.data} who={who} chartRef={chart} onCell={(row, kp) => setCell({ row, kp })} />}
        </div></div>
      <Drawer open={!!cell} onClose={() => setCell(null)} width={480}
        title={cell ? `${who(cell.row)} · ${q.data?.knowledge_points.find((k) => k.code === cell.kp)?.name}` : ''}>
        <div className={detail.isPlaceholderData ? 'stale on' : 'stale'}>
        {detail.data?.attempts.length === 0 && <div className="muted">这个知识点上还没有尝试</div>}
        {detail.data?.attempts.map((a) => (
          <div key={a.attempt_id} className="card" style={{ padding: 12, marginBottom: 8 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}><b>{a.title}</b><span className="muted">{beijingTime(a.created_at)}</span></div>
            <div style={{ marginTop: 6 }}><QuadrantBadge quadrant={a.quadrant} withHint={false} />
              <span className="muted" style={{ marginLeft: 8, fontSize: 12 }}>预测准确率 {percent(a.pred_accuracy)}</span></div>
            <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>{a.tags.map((t: string) => TAG_LABEL[t] ?? t).join('；') || '没有标签'}</div>
          </div>
        ))}
      </div>
      </Drawer>
    </div>
  )
}
