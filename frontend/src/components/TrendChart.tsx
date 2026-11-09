// 预测准确率趋势（ECharts 折线图）
import * as echarts from 'echarts/core'
import { LineChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import { SVGRenderer } from 'echarts/renderers'
import { useEffect, useRef } from 'react'
import { colors } from '../theme/tokens'

echarts.use([LineChart, GridComponent, LegendComponent, TooltipComponent, SVGRenderer])

export default function TrendChart({ data }: { data: { week: string; waveform: number | null; hardware: number | null }[] }) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!ref.current) return
    const chart = echarts.init(ref.current, undefined, { renderer: 'svg' })
    const labels = data.map((d) => `${Number(d.week.slice(5, 7))}/${Number(d.week.slice(8, 10))} 周`)
    const pct = (v: number | null) => (v === null ? null : Math.round(v * 100))
    chart.setOption({
      grid: { left: 40, right: 20, top: 36, bottom: 28 },
      legend: { top: 0, left: 0, itemWidth: 14, itemHeight: 4, textStyle: { color: colors.text, fontSize: 12 } },
      tooltip: { trigger: 'axis', valueFormatter: (v: number) => (v === null ? '—' : `${v}%`) },
      xAxis: { type: 'category', data: labels, axisLine: { lineStyle: { color: colors.border } },
        axisLabel: { color: colors.text2, fontSize: 11 } },
      yAxis: { type: 'value', min: 0, max: 100, axisLabel: { formatter: '{value}%', color: colors.text2, fontSize: 11 },
        splitLine: { lineStyle: { color: '#F1F2F4' } } },
      series: [
        { name: '波形预测', type: 'line', data: data.map((d) => pct(d.waveform)), connectNulls: true,
          lineStyle: { width: 2.2, color: colors.primary }, itemStyle: { color: colors.primary }, symbolSize: 6 },
        { name: '硬件预测', type: 'line', data: data.map((d) => pct(d.hardware)), connectNulls: true,
          lineStyle: { width: 2.2, color: '#7C3AED', type: [5, 4] }, itemStyle: { color: '#7C3AED' }, symbolSize: 6 },
      ],
    })
    const ro = new ResizeObserver(() => chart.resize())
    ro.observe(ref.current)
    return () => { ro.disconnect(); chart.dispose() }
  }, [data])
  return <div ref={ref} style={{ width: '100%', height: 250 }} role="img" aria-label="预测准确率趋势" data-testid="trend-chart" />
}
