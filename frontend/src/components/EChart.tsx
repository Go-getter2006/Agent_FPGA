// 通用 ECharts 容器（SVG 渲染，随容器尺寸自适应）
import * as echarts from 'echarts/core'
import { BarChart, FunnelChart, HeatmapChart, LineChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent, VisualMapComponent } from 'echarts/components'
import { SVGRenderer } from 'echarts/renderers'
import { forwardRef, useEffect, useImperativeHandle, useRef } from 'react'

echarts.use([LineChart, BarChart, HeatmapChart, FunnelChart, GridComponent, LegendComponent, TooltipComponent,
  VisualMapComponent, SVGRenderer])

export interface EChartHandle { toDataURL: () => string | undefined }

const EChart = forwardRef<EChartHandle, { option: echarts.EChartsCoreOption; height: number; testId?: string;
  onClick?: (params: any) => void; label?: string }>(function EChart({ option, height, testId, onClick, label }, ref) {
  const el = useRef<HTMLDivElement>(null)
  const chart = useRef<echarts.ECharts | null>(null)
  useImperativeHandle(ref, () => ({ toDataURL: () => chart.current?.getDataURL({ type: 'svg' }) }))
  useEffect(() => {
    if (!el.current) return
    const c = echarts.init(el.current, undefined, { renderer: 'svg' })
    chart.current = c
    const ro = new ResizeObserver(() => c.resize())
    ro.observe(el.current)
    return () => { ro.disconnect(); c.dispose(); chart.current = null }
  }, [])
  useEffect(() => { chart.current?.setOption(option, true) }, [option])
  useEffect(() => {
    const c = chart.current
    if (!c || !onClick) return
    c.on('click', onClick)
    return () => { c.off('click', onClick) }
  }, [onClick])
  return <div ref={el} style={{ width: '100%', height }} data-testid={testId} role="img" aria-label={label} />
})

export default EChart
