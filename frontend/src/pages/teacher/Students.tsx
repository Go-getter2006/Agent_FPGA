// T5 学生详情：时间线（每次尝试一行，点开看代码、波形对照、提示原文、对话记录）；侧栏：掌握等级、F、盲改率、testbench、顺序打乱实验、ICAP、备注
import { Button, Input, Select, message } from 'antd'
import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { post } from '../../api/client'
import { qs, useT, type Heatmap } from '../../api/teacher'
import { useInvalidate } from '../../api/hooks'
import { ErrorState, Loading, QuadrantBadge } from '../../components/Common'
import WaveformView from '../../components/WaveformView'
import { beijingTime, percent, TAG_LABEL } from '../../lib/format'
import { levelStyle } from '../../theme/tokens'
import { useTeacher } from './TeacherLayout'

export default function Students() {
  const { cid, anonymous, who } = useTeacher()
  const { uid } = useParams()
  const navigate = useNavigate()
  const list = useT<Heatmap>(['t-heat', cid, '', anonymous, 'all'], `/api/teacher/classes/${cid}/heatmap${qs({ anonymous })}`)
  const current = uid ? Number(uid) : list.data?.rows[0]?.user_id
  const q = useT<any>(['t-student', current, anonymous], `/api/teacher/students/${current}${qs({ anonymous })}`, !!current)
  const [open, setOpen] = useState<number | null>(null)
  const [note, setNote] = useState('')
  const invalidate = useInvalidate()
  if (list.isLoading) return <Loading />
  return (
    <div data-testid="t-student">
      <div className="page-h"><h1>学生详情</h1>
        <Select showSearch value={current} style={{ minWidth: 220 }} optionFilterProp="label" data-testid="student-select"
          onChange={(v) => navigate(`/teacher/classes/${cid}/students/${v}`)}
          options={(list.data?.rows ?? []).map((r) => ({ value: r.user_id, label: `${who(r)} · ${r.group === 'treatment' ? '实验组' : r.group === 'control' ? '对照组' : '未分组'}` }))} /></div>
      {q.isLoading && <Loading />}
      {q.error && <ErrorState error={q.error} onRetry={() => q.refetch()} />}
      {q.data && (
        <div className="grid" style={{ gridTemplateColumns: 'minmax(0, 8fr) minmax(0, 4fr)' }}>
          <div className="card timeline"><div className="card-h">时间线 <small>{q.data.timeline.length} 次尝试</small></div>
            {q.data.timeline.map((t: any) => (
              <div key={t.attempt_id}>
                <div className={`tl-row ${open === t.attempt_id ? 'on' : ''}`} onClick={() => setOpen(open === t.attempt_id ? null : t.attempt_id)} data-testid="tl-row">
                  <span className="muted">{beijingTime(t.created_at)}</span>
                  <span>{t.title} <span className="muted">#{t.attempt_no}</span></span>
                  <span style={{ fontSize: 12 }}><QuadrantBadge quadrant={t.quadrant} withHint={false} />
                    <span className="muted" style={{ marginLeft: 6 }}>{t.tags.filter((x: string) => x !== 'sim_mismatch').map((x: string) => TAG_LABEL[x] ?? x).join('；')}</span></span>
                  <span>预测 {percent(t.pred_accuracy)}</span>
                  <span>{t.max_hint_level >= 4 ? '看过参考答案' : `提示 ${t.max_hint_level} 级`}</span>
                </div>
                {open === t.attempt_id && <AttemptDetail aid={t.attempt_id} />}
              </div>
            ))}
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            <div className="card"><div className="card-h">{who(q.data)} <small>{q.data.group === 'treatment' ? '实验组' : q.data.group === 'control' ? '对照组' : '未分组'} · {q.data.consent === 'accepted' ? '已同意研究' : q.data.consent === 'declined' ? '不参与研究' : '未选择'}</small></div>
              <div className="card-b">
                <div className="kv-row"><span>盲改率</span><b>{percent(q.data.blind_rate)}</b><span className="muted">（{q.data.resubmissions} 次重复提交）</span></div>
                <div className="kv-row"><span>提示依赖度 H</span><b>{q.data.hint_dependence === null ? '—' : q.data.hint_dependence.toFixed(1)}</b></div>
                <div className="kv-row"><span>testbench</span><b>{q.data.tb.map((t: any) => `${t.title} ${Math.round((t.score ?? 0) * 100)}%`).join('；') || '—'}</b></div>
                <div className="kv-row"><span>顺序打乱实验</span><b>{q.data.shuffle.length ? `${q.data.shuffle.filter((s: any) => s.order_sensitive).length} 次顺序相关 / 共 ${q.data.shuffle.length} 次` : '—'}</b></div>
              </div></div>
            <div className="card"><div className="card-h">知识点</div>
              <table className="tbl"><thead><tr><th>知识点</th><th>等级</th><th className="r">F</th></tr></thead>
                <tbody>{q.data.knowledge_points.map((k: any) => (
                  <tr key={k.code}><td>{k.name.replace(/（.*）/, '')}</td><td><span className={`lvl-chip ${levelStyle[k.level as keyof typeof levelStyle].className}`}>{levelStyle[k.level as keyof typeof levelStyle].icon} {levelStyle[k.level as keyof typeof levelStyle].name}</span></td>
                    <td className="r">{k.f_value === null ? '—' : k.f_value.toFixed(2)}</td></tr>))}</tbody></table></div>
            <div className="card"><div className="card-h">ICAP 编码 <small>AI 编码，待人工抽检</small></div>
              <div className="card-b" style={{ maxHeight: 260, overflow: 'auto' }}>
                {q.data.icap.length === 0 && <div className="muted">还没有编码结果</div>}
                {q.data.icap.map((x: any) => (
                  <div key={x.id} style={{ marginBottom: 8, fontSize: 13 }}><span className="icap-chip">{x.label}</span> {x.text}
                    <div className="muted" style={{ fontSize: 12 }}>{x.context} · {x.rationale} · {x.note}</div></div>))}
              </div></div>
            <div className="card"><div className="card-h">教师备注 <small>只有教师可见</small></div>
              <div className="card-b">
                <Input.TextArea value={note} onChange={(e) => setNote(e.target.value)} autoSize={{ minRows: 2 }} placeholder="记录这名学生的情况" />
                <Button style={{ marginTop: 8 }} disabled={!note.trim()} onClick={async () => {
                  await post(`/api/teacher/students/${current}/notes`, { text: note })
                  setNote(''); message.success('已保存'); await invalidate(['t-student', current, anonymous])
                }}>保存备注</Button>
                {q.data.notes.map((n: any) => <div key={n.id} style={{ marginTop: 8, fontSize: 13 }}>{n.text}<div className="muted" style={{ fontSize: 12 }}>{beijingTime(n.created_at)}</div></div>)}
              </div></div>
          </div>
        </div>
      )}
    </div>
  )
}

function AttemptDetail({ aid }: { aid: number }) {
  const q = useT<any>(['t-attempt', aid], `/api/teacher/attempts/${aid}`)
  if (q.isLoading) return <Loading rows={3} />
  if (!q.data) return null
  const d = q.data
  const predicted: Record<string, string> = {}
  for (const p of d.predictions.filter((x: any) => x.kind === 'waveform')) for (const c of p.answers.cells) predicted[`${c.signal}@${c.step}`] = c.value
  const cells = d.predict_points.flatMap((p: any) => p.steps.map((s: number) => ({ signal: p.signal, step: s })))
  return (
    <div style={{ padding: '8px 12px 16px', background: '#FAFAFB' }} data-testid="attempt-detail">
      <div className="grid" style={{ gridTemplateColumns: 'minmax(0, 5fr) minmax(0, 7fr)', gap: 12 }}>
        <pre className="snippet" style={{ maxHeight: 320 }}>{d.code.split('\n').map((l: string, i: number) => <span key={i} className="ln"><span className="no">{i + 1}</span>{l}</span>)}</pre>
        <div style={{ minWidth: 0 }}>
          {d.judge?.compile.ok && d.judge.sim.trace.length > 0
            ? <WaveformView mode="compare" steps={d.skeleton.steps} inputs={d.skeleton.inputs} outputs={d.skeleton.outputs}
                actual={d.judge.sim.trace} expected={d.expected} predicted={predicted} predictCells={cells}
                firstMismatchStep={d.judge.sim.first_mismatch?.step ?? null} clocked={d.skeleton.inputs.some((i: any) => i.name === 'rst')} />
            : <div className="muted">编译没通过：{d.judge?.compile.errors.map((e: any) => e.message).join('；')}</div>}
          {d.explanations.length > 0 && <div style={{ marginTop: 8, fontSize: 13 }}><b>一句话解释：</b>{d.explanations.join('；')}</div>}
          {d.hints.map((h: any) => <div key={h.level} style={{ marginTop: 6, fontSize: 13 }}><b>{h.level >= 4 ? '看了参考答案' : `${h.level} 级提示（${h.source === 'llm' ? 'DeepSeek' : '规则'}）`}：</b>{h.level >= 4 ? '' : h.message} <span className="muted">{h.question}</span></div>)}
          {d.chat.length > 0 && <div style={{ marginTop: 8 }}><b style={{ fontSize: 13 }}>对话记录</b>
            {d.chat.map((m: any, i: number) => <div key={i} style={{ fontSize: 13, marginTop: 4 }}>{m.role === 'user' ? '学生' : '助教'}：{m.content}{m.flagged && <span className="bad">（拦截了代码）</span>}</div>)}</div>}
        </div>
      </div>
    </div>
  )
}
