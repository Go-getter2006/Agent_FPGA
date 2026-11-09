// T7 实验分组与数据导出：分组、各组功能开关、导出（只含已同意的学生，匿名 ID）、离线 ICAP 编码与人工抽检（κ）
import { Alert, Button, Checkbox, DatePicker, Input, Radio, Select, Switch, message } from 'antd'
import type { Dayjs } from 'dayjs'
import { useEffect, useState } from 'react'
import { ApiError, api, get, post } from '../../api/client'
import { qs, useT } from '../../api/teacher'
import { useInvalidate } from '../../api/hooks'
import { ErrorState, Loading } from '../../components/Common'
import { useTeacher } from './TeacherLayout'

const FLAG_LABEL: Record<string, string> = { predict_step: '预测步骤', llm_hints: '智能提示', chat: '助教对话',
  shuffle: '顺序打乱实验', tb_scoring: 'testbench 打分', review: '复习' }
const GROUP_LABEL: Record<string, string> = { treatment: '实验组', control: '对照组', none: '未分组' }

async function waitJob(id: number): Promise<any> {
  for (;;) {
    const j = await get<any>(`/api/jobs/${id}`)
    if (j.status === 'done' || j.status === 'error') return j
    await new Promise((r) => setTimeout(r, 1000))
  }
}

export default function Research() {
  const { cid, anonymous, who } = useTeacher()
  const invalidate = useInvalidate()
  const groups = useT<any>(['t-groups', cid, anonymous], `/api/teacher/classes/${cid}/groups${qs({ anonymous })}`)
  const icap = useT<any>(['t-icap', cid], `/api/teacher/classes/${cid}/analysis/icap`)
  const [assign, setAssign] = useState<Record<number, string>>({})
  const [flags, setFlags] = useState<Record<string, Record<string, boolean>>>({})
  const [csvText, setCsvText] = useState('')
  const [kinds, setKinds] = useState<string[]>(['events', 'attempts', 'metrics'])
  const [exportJob, setExportJob] = useState<any>(null)
  const [icapBusy, setIcapBusy] = useState(false)
  const [range, setRange] = useState<[Dayjs | null, Dayjs | null] | null>(null)
  const [sample, setSample] = useState<any[] | null>(null)
  const [labels, setLabels] = useState<Record<number, string>>({})
  const [kappa, setKappa] = useState<any>(null)
  useEffect(() => { if (groups.data) setFlags(groups.data.flags) }, [groups.data])
  if (groups.isLoading) return <Loading />
  if (groups.error) return <ErrorState error={groups.error} onRetry={() => groups.refetch()} />
  const g = groups.data
  const save = async () => {
    try {
      await api('PUT', `/api/teacher/classes/${cid}/groups`, {
        assignments: Object.entries(assign).map(([user_id, group]) => ({ user_id: Number(user_id), group })),
        csv: csvText || undefined, flags })
      message.success('分组与功能开关已保存')
      setAssign({}); setCsvText('')
      await invalidate(['t-groups', cid], ['t-classes'])
    } catch (e) { message.warning(e instanceof ApiError ? e.message : '没有保存成功') }
  }
  const startExport = async () => {
    const r = await post<{ job_id: number }>(`/api/teacher/classes/${cid}/exports`, { kinds })
    setExportJob({ id: r.job_id, status: 'running' })
    setExportJob(await waitJob(r.job_id))
  }
  const startIcap = async () => {
    setIcapBusy(true)
    try {
      const r = await post<{ job_id: number }>(`/api/teacher/classes/${cid}/analysis/icap`, {
        start: range?.[0]?.format('YYYY-MM-DDT00:00:00'), end: range?.[1]?.add(1, 'day').format('YYYY-MM-DDT00:00:00') })
      const j = await waitJob(r.job_id)
      if (j.status === 'error') message.warning('编码没有完成：大模型不可用或调用失败')
      await invalidate(['t-icap', cid])
    } finally { setIcapBusy(false) }
  }
  const loadSample = async () => {
    const r = await get<{ items: any[] }>(`/api/teacher/classes/${cid}/analysis/icap/sample`)
    setSample(r.items)
    setLabels(Object.fromEntries(r.items.filter((x) => x.human_label).map((x) => [x.id, x.human_label])))
  }
  const submitLabels = async () => {
    const r = await api<any>('PUT', `/api/teacher/classes/${cid}/analysis/icap/sample`,
      { labels: Object.entries(labels).map(([id, human_label]) => ({ id: Number(id), human_label })) })
    setKappa(r)
    await invalidate(['t-icap', cid])
  }
  return (
    <div data-testid="t-research">
      <div className="page-h"><h1>实验分组与数据导出</h1></div>
      <div className="grid g-7-5">
        <div className="card"><div className="card-h">实验分组 <Button type="primary" size="small" onClick={save} data-testid="save-groups">保存</Button></div>
          <div className="card-b" style={{ maxHeight: 420, overflow: 'auto' }}>
            <table className="tbl"><thead><tr><th>学生</th><th>分组</th><th>研究同意</th></tr></thead>
              <tbody>{g.students.map((s: any) => (
                <tr key={s.user_id}><td>{who(s)}</td>
                  <td><Select size="small" value={assign[s.user_id] ?? s.group} style={{ width: 110 }}
                    onChange={(v) => setAssign((a) => ({ ...a, [s.user_id]: v }))}
                    options={Object.entries(GROUP_LABEL).map(([v, l]) => ({ value: v, label: l }))} /></td>
                  <td>{s.consent === 'accepted' ? '已同意' : s.consent === 'declined' ? '不参与' : '未选择'}</td></tr>))}</tbody></table>
            <div style={{ marginTop: 12 }}><div className="muted" style={{ fontSize: 12 }}>也可以粘贴 CSV（学号,分组；分组为 treatment / control / none）</div>
              <Input.TextArea value={csvText} onChange={(e) => setCsvText(e.target.value)} autoSize={{ minRows: 2, maxRows: 6 }} placeholder={'学号,分组\nS2026001,treatment'} /></div>
          </div></div>
        <div className="card"><div className="card-h">各组功能开关</div>
          <div className="card-b">
            <table className="tbl"><thead><tr><th>功能</th>{['treatment', 'control', 'none'].map((x) => <th key={x}>{GROUP_LABEL[x]}</th>)}</tr></thead>
              <tbody>{g.flag_names.map((f: string) => (
                <tr key={f}><td>{FLAG_LABEL[f]}</td>{['treatment', 'control', 'none'].map((x) => (
                  <td key={x}><Switch size="small" checked={flags[x]?.[f] ?? false} data-testid={`flag-${x}-${f}`}
                    onChange={(v) => setFlags((all) => ({ ...all, [x]: { ...all[x], [f]: v } }))} /></td>))}</tr>))}</tbody></table>
            <div className="muted" style={{ fontSize: 12, marginTop: 8 }}>默认对照组关闭预测步骤、智能提示、对话；实验结束后可为对照组打开全部功能。改完点左上“保存”。</div>
          </div></div>
      </div>

      <div className="grid g-5-7" style={{ marginTop: 16 }}>
        <div className="card"><div className="card-h">数据导出 <small>只含已同意的学生，全部用匿名 ID</small></div>
          <div className="card-b">
            <Checkbox.Group value={kinds} onChange={(v) => setKinds(v as string[])}
              options={[{ label: '事件日志 JSONL', value: 'events' }, { label: '尝试记录 CSV', value: 'attempts' }, { label: '指标 CSV', value: 'metrics' }]} />
            <div className="muted" style={{ fontSize: 12, margin: '8px 0' }}>每份导出都附带数据字典。</div>
            <Button type="primary" disabled={!kinds.length || exportJob?.status === 'running'} loading={exportJob?.status === 'running'} onClick={startExport} data-testid="start-export">开始导出</Button>
            {exportJob?.status === 'done' && (
              <div style={{ marginTop: 12 }} data-testid="export-done">
                已导出 {exportJob.result?.counts?.students} 名学生的数据。<a href={`/api/teacher/exports/${exportJob.id}/download`}>下载 zip</a>
              </div>)}
            {exportJob?.status === 'error' && <Alert type="warning" style={{ marginTop: 12 }} message="导出失败，请重试" />}
          </div></div>
        <div className="card"><div className="card-h">离线分析：ICAP 编码 <small>{icap.data?.prompt_version} · 结果不进入学生端</small></div>
          <div className="card-b">
            <div className="filters"><DatePicker.RangePicker value={range as any} onChange={(v) => setRange(v as any)} placeholder={['开始日期', '结束日期']} />
              <Button onClick={startIcap} loading={icapBusy} data-testid="start-icap">对这段时间的对话和解释编码</Button></div>
            {icap.data && (
              <div style={{ marginTop: 12, fontSize: 13 }} data-testid="icap-summary">
                共 {icap.data.total} 条：{['P', 'A', 'C', 'I'].map((k) => <span key={k} style={{ marginRight: 10 }}><span className="icap-chip">{k}</span> {icap.data.by_label[k]}</span>)}
                <div className="muted" style={{ marginTop: 4 }}>已抽检 {icap.data.human_labeled} / {icap.data.sampled} 条
                  {icap.data.agreement.kappa !== null && <>，κ = {icap.data.agreement.kappa.toFixed(2)}</>}</div>
                {icap.data.low_agreement && <Alert type="warning" showIcon style={{ marginTop: 8 }} message="一致性偏低，结论需谨慎" />}
              </div>)}
            <Button style={{ marginTop: 12 }} onClick={loadSample} disabled={!icap.data?.total} data-testid="load-sample">人工抽检（随机 10%）</Button>
            {sample && (
              <div style={{ marginTop: 12 }} data-testid="icap-sample">
                <div className="muted" style={{ fontSize: 12, marginBottom: 6 }}>标注时不显示 AI 的结果。P 被动 · A 主动 · C 建构 · I 互动</div>
                {sample.map((s) => (
                  <div key={s.id} style={{ borderBottom: '1px dashed var(--c-border)', padding: '8px 0' }}>
                    <div style={{ fontSize: 13 }}>{s.text}</div><div className="muted" style={{ fontSize: 12 }}>{s.context}</div>
                    <Radio.Group size="small" value={labels[s.id]} onChange={(e) => setLabels((l) => ({ ...l, [s.id]: e.target.value }))}
                      options={['P', 'A', 'C', 'I']} optionType="button" />
                  </div>))}
                <Button type="primary" style={{ marginTop: 8 }} disabled={!Object.keys(labels).length} onClick={submitLabels} data-testid="submit-labels">提交标注并计算 κ</Button>
                {kappa && <div style={{ marginTop: 8 }} data-testid="kappa">κ = {kappa.kappa === null ? '—' : kappa.kappa.toFixed(2)}（{kappa.n} 条，一致率 {Math.round((kappa.p_o ?? 0) * 100)}%）
                  {kappa.message && <span className="warn">。{kappa.message}</span>}</div>}
              </div>)}
          </div></div>
      </div>
    </div>
  )
}
