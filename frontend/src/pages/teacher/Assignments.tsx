// T6 作业与题库：题库来自仓库 problems/ 目录（只读，可预览）；新建作业：选题、选范围、开始与截止时间
import { Button, DatePicker, Drawer, Form, Input, Modal, Select, message } from 'antd'
import { useState } from 'react'
import { post, ApiError } from '../../api/client'
import { useT } from '../../api/teacher'
import { useInvalidate } from '../../api/hooks'
import { ErrorState, Loading } from '../../components/Common'
import { beijingTime } from '../../lib/format'
import Markdown from '../../lib/markdown'
import { useTeacher } from './TeacherLayout'

const TYPE = { predict: '预测题', modify: '修改题', make: '创作题' } as Record<string, string>
const SCOPE = { all: '全班', treatment: '实验组', control: '对照组' } as Record<string, string>

export default function Assignments() {
  const { cid } = useTeacher()
  const asg = useT<{ assignments: any[] }>(['t-asg', cid], `/api/teacher/classes/${cid}/assignments`)
  const bank = useT<{ problems: any[] }>(['t-bank'], '/api/teacher/problems')
  const [preview, setPreview] = useState<any>(null)
  const [creating, setCreating] = useState(false)
  const [form] = Form.useForm()
  const invalidate = useInvalidate()
  if (asg.isLoading || bank.isLoading) return <Loading />
  if (asg.error || bank.error) return <ErrorState error={asg.error ?? bank.error} onRetry={() => { asg.refetch(); bank.refetch() }} />
  const titles = Object.fromEntries((bank.data?.problems ?? []).map((p) => [p.id, p.title]))
  const create = async () => {
    const v = await form.validateFields()
    try {
      await post(`/api/teacher/classes/${cid}/assignments`, { title: v.title, problem_ids: v.problem_ids, group_scope: v.group_scope,
        open_at: v.range[0].format('YYYY-MM-DDTHH:mm:00'), due_at: v.range[1].format('YYYY-MM-DDTHH:mm:00') })
      message.success('作业已布置')
      setCreating(false)
      form.resetFields()
      await invalidate(['t-asg', cid])
    } catch (e) { message.warning(e instanceof ApiError ? e.message : '没有保存成功') }
  }
  return (
    <div data-testid="t-assignments">
      <div className="page-h"><h1>作业与题库</h1><Button type="primary" onClick={() => setCreating(true)} data-testid="new-assignment">新建作业</Button></div>
      <div className="card"><div className="card-h">本班作业</div>
        <table className="tbl"><thead><tr><th>作业</th><th>范围</th><th>题目</th><th>开始</th><th>截止</th></tr></thead>
          <tbody>{asg.data!.assignments.map((a) => (
            <tr key={a.id}><td>{a.title}</td><td>{SCOPE[a.group_scope]}</td><td>{a.problem_ids.map((p: string) => titles[p] ?? p).join('、')}</td>
              <td>{beijingTime(a.open_at)}</td><td>{beijingTime(a.due_at)}</td></tr>))}</tbody></table></div>
      <div className="card" style={{ marginTop: 16 }}><div className="card-h">题库 <small>来自仓库 problems/ 目录，只读</small></div>
        <table className="tbl"><thead><tr><th>题目</th><th>类型</th><th>知识点</th><th>难度</th><th /></tr></thead>
          <tbody>{bank.data!.problems.map((p) => (
            <tr key={p.id}><td>{p.title}</td><td><span className="chip blue">{TYPE[p.primm_type]}</span></td><td>{p.knowledge_points.join('、')}</td>
              <td>{'●'.repeat(p.difficulty)}</td><td><Button size="small" onClick={() => setPreview(p)}>预览</Button></td></tr>))}</tbody></table></div>
      <Drawer open={!!preview} onClose={() => setPreview(null)} width={640} title={preview?.title}>
        {preview && (
          <>
            <Markdown text={preview.spec} skipTitle />
            {preview.modify_goal && <p style={{ marginTop: 8 }}><b>修改目标：</b>{preview.modify_goal}</p>}
            <p style={{ marginTop: 8 }}><b>预测点：</b>{preview.predict_points.map((x: any) => `${x.signal} 第 ${x.steps.join('、')} 步`).join('；')}</p>
            {preview.starter && <><h4>起始代码</h4><pre className="snippet">{preview.starter.split('\n').map((l: string, i: number) => <span key={i} className="ln"><span className="no">{i + 1}</span>{l}</span>)}</pre></>}
          </>
        )}
      </Drawer>
      <Modal open={creating} title="新建作业" onCancel={() => setCreating(false)} onOk={create} okText="布置" cancelText="取消">
        <Form form={form} layout="vertical" initialValues={{ group_scope: 'all' }}>
          <Form.Item name="title" label="作业名称" rules={[{ required: true, message: '请填写作业名称' }]}><Input /></Form.Item>
          <Form.Item name="problem_ids" label="题目" rules={[{ required: true, message: '至少选一道题' }]}>
            <Select mode="multiple" options={bank.data!.problems.map((p) => ({ value: p.id, label: `${p.title}（${TYPE[p.primm_type]}）` }))} /></Form.Item>
          <Form.Item name="group_scope" label="范围"><Select options={Object.entries(SCOPE).map(([v, l]) => ({ value: v, label: l }))} /></Form.Item>
          <Form.Item name="range" label="开始与截止时间（北京时间）" rules={[{ required: true, message: '请选择时间' }]}>
            <DatePicker.RangePicker showTime={{ format: 'HH:mm' }} format="YYYY-MM-DD HH:mm" /></Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
