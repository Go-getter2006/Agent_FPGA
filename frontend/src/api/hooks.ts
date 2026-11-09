import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { get, post } from './client'
import type { AttemptDetail, HomeData, Me, ProblemDetail, ProblemListItem, KP, ReportData, ReviewData,
  TbSubmission } from './types'

const RUNNING = new Set(['queued', 'running'])

export const useMe = () => useQuery({ queryKey: ['me'], queryFn: () => get<Me>('/api/auth/me'), retry: false })
export const useHome = () => useQuery({ queryKey: ['home'], queryFn: () => get<HomeData>('/api/student/home') })
export const useReport = () => useQuery({ queryKey: ['report'], queryFn: () => get<ReportData>('/api/student/report') })
export const useReview = () => useQuery({ queryKey: ['review'], queryFn: () => get<ReviewData>('/api/student/review') })

export const useProblems = (params: Record<string, string | undefined>) => {
  const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v) as [string, string][]).toString()
  return useQuery({
    queryKey: ['problems', qs],
    queryFn: () => get<{ items: ProblemListItem[]; assignments: { id: number; title: string; due_at: string }[];
      knowledge_points: KP[] }>(`/api/student/problems${qs ? `?${qs}` : ''}`),
  })
}

export const useProblem = (pid: string) =>
  useQuery({ queryKey: ['problem', pid], queryFn: () => get<ProblemDetail>(`/api/student/problems/${pid}`) })

// 尝试在排队或运行中时每秒轮询一次（docs/data-api.md 第 2 节：前端先实现轮询，间隔 1 秒）
export const useAttempt = (aid: number | null | undefined) =>
  useQuery({
    queryKey: ['attempt', aid],
    enabled: !!aid,
    queryFn: () => get<AttemptDetail>(`/api/student/attempts/${aid}`),
    refetchInterval: (q) => {
      const d = q.state.data
      if (!d) return false
      if (RUNNING.has(d.status)) return 1000
      if (d.shuffle && RUNNING.has(d.shuffle.status)) return 1000
      return false
    },
  })

export const useTbSubmission = (sid: number | null | undefined) =>
  useQuery({
    queryKey: ['tb', sid],
    enabled: !!sid,
    queryFn: () => get<TbSubmission>(`/api/student/testbench/${sid}`),
    refetchInterval: (q) => (q.state.data && RUNNING.has(q.state.data.status) ? 1000 : false),
  })

export function useInvalidate() {
  const qc = useQueryClient()
  return (...keys: unknown[][]) => Promise.all(keys.map((k) => qc.invalidateQueries({ queryKey: k })))
}

export const useLogin = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { login_name: string; password: string }) => post<Me>('/api/auth/login', body),
    onSuccess: (me) => qc.setQueryData(['me'], me),
  })
}
