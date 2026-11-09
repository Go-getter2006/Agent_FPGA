// T8 班级管理：导入名单（CSV：学号、姓名）、重置密码、查看知情同意状态。教师端唯一默认显示真实姓名的页面
import { Button, Input, Modal, message } from 'antd'
import { useState } from 'react'
import { ApiError, post } from '../../api/client'
import { useT } from '../../api/teacher'
import { useInvalidate } from '../../api/hooks'
import { ErrorState, Loading } from '../../components/Common'
import { beijingTime } from '../../lib/format'
import { useTeacher } from './TeacherLayout'

const CONSENT: Record<string, string> = { accepted: '已同意', declined: '不参与研究', pending: '未选择' }
const GROUP: Record<string, string> = { treatment: '实验组', control: '对照组', none: '未分组' }

export default function Roster() {
  const { cid } = useTeacher()
  const q = useT<any>(['t-roster', cid], `/api/teacher/classes/${cid}/roster`)
  const invalidate = useInvalidate()
  const [csvText, setCsvText] = useState('')
  const [imported, setImported] = useState<any[] | null>(null)
  if (q.isLoading) return <Loading />
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />
  const doImport = async () => {
    try {
      const r = await post<{ imported: any[] }>(`/api/teacher/classes/${cid}/roster`, { csv: csvText })
      setImported(r.imported); setCsvText('')
      await invalidate(['t-roster', cid], ['t-classes'])
    } catch (e) { message.warning(e instanceof ApiError ? e.message : '导入失败') }
  }
  const reset = async (s: any) => {
    const r = await post<{ temp_password: string }>(`/api/teacher/students/${s.user_id}/reset_password`)
    Modal.info({ title: `${s.name} 的临时密码`, content: <div><b className="mono" style={{ fontSize: 18 }}>{r.temp_password}</b><p className="muted">只显示这一次，请转告学生。</p></div> })
  }
  return (
    <div data-testid="t-roster">
      <div className="page-h"><h1>班级管理</h1><span className="muted">本页显示真实姓名</span></div>
      <div className="grid g-7-5">
        <div className="card"><div className="card-h">名单 <small>{q.data.students.length} 人 · 知情同意书版本 {q.data.current_consent_version}</small></div>
          <table className="tbl"><thead><tr><th>代号</th><th>学号</th><th>姓名</th><th>分组</th><th>知情同意</th><th /></tr></thead>
            <tbody>{q.data.students.map((s: any) => (
              <tr key={s.user_id}><td className="mono">{s.alias}</td><td className="mono">{s.login_name}</td><td>{s.name}</td><td>{GROUP[s.group]}</td>
                <td>{CONSENT[s.consent_status]}{s.consent_at ? <span className="muted" style={{ fontSize: 12 }}> · {beijingTime(s.consent_at)}</span> : null}</td>
                <td><Button size="small" onClick={() => reset(s)}>重置密码</Button></td></tr>))}</tbody></table></div>
        <div className="card"><div className="card-h">导入名单</div>
          <div className="card-b">
            <div className="muted" style={{ fontSize: 12 }}>每行一名学生：学号,姓名[,分组]。新账号会生成临时密码，只显示一次。</div>
            <Input.TextArea value={csvText} onChange={(e) => setCsvText(e.target.value)} autoSize={{ minRows: 5, maxRows: 12 }}
              placeholder={'学号,姓名\nS2026101,张三'} style={{ marginTop: 8 }} data-testid="roster-csv" />
            <Button type="primary" style={{ marginTop: 8 }} disabled={!csvText.trim()} onClick={doImport} data-testid="roster-import">导入</Button>
            {imported && (
              <table className="tbl" style={{ marginTop: 12 }} data-testid="roster-result"><thead><tr><th>学号</th><th>姓名</th><th>临时密码</th></tr></thead>
                <tbody>{imported.map((x) => <tr key={x.login_name}><td>{x.login_name}</td><td>{x.name}</td><td className="mono">{x.temp_password ?? '（已有账号）'}</td></tr>)}</tbody></table>)}
          </div></div>
      </div>
    </div>
  )
}
