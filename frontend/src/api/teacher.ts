// 教师端接口
import { useQuery } from '@tanstack/react-query'
import { get } from './client'

export interface TClass { id: number; name: string; term: string; students: number; groups: Record<string, number> }
export interface Kpi { value: number | null; prev: number | null; total?: number }
export interface ProblemRow {
  problem_id: string; title: string; knowledge_points: string[]; attempted: number; passed: number
  pass_rate: number | null; avg_submissions: number | null; f_value: number | null; blind_rate: number | null
  avg_hint_level: number | null; avg_minutes: number | null
}
export interface Misconception { code: string; label: string; source: 'judge' | 'prediction'; students: number;
  occurrences: number; problems: [string, number][] }
export interface Overview {
  kpis: { active: Kpi; completion: Kpi; pred_accuracy: Kpi; class_f: Kpi; avg_hint: Kpi }
  trend: { week: string; pred_accuracy: number | null; class_f: number | null }[]
  misconceptions: Misconception[]
  alerts: { user_id: number; alias: string; name: string | null; group: string; reasons: { rule: number; text: string }[] }[]
  problems: ProblemRow[]; groups: Record<string, number>
}
export interface HeatCell { level: 'mastered' | 'fragile' | 'learning' | 'not_started'; attempts: number;
  f_value: number | null; r_code: number | null; r_pred: number | null }
export interface Heatmap { knowledge_points: { code: string; name: string }[]
  rows: { user_id: number; alias: string; name: string | null; group: string; cells: Record<string, HeatCell> }[] }

export const qs = (o: Record<string, string | number | boolean | null | undefined>) => {
  const p = new URLSearchParams()
  for (const [k, v] of Object.entries(o)) if (v !== null && v !== undefined && v !== '') p.set(k, String(v))
  const s = p.toString()
  return s ? `?${s}` : ''
}

export const useClasses = () => useQuery({ queryKey: ['t-classes'], queryFn: () => get<{ classes: TClass[] }>('/api/teacher/classes') })
export const useStatus = () => useQuery({ queryKey: ['t-status'], queryFn: () => get<{ llm: { available: boolean; reason: string | null;
  spent_today_cny: number; daily_budget_cny: number; budget_exceeded: boolean } }>('/api/teacher/status'), refetchInterval: 60_000 })
export const useT = <T,>(key: unknown[], url: string, enabled = true) =>
  useQuery({ queryKey: key, queryFn: () => get<T>(url), enabled })
