// 做题工作台（docs/pages.md S4）：PRIMM 五步 预测 → 运行 → 探究 → 修改 → 创作
import { Alert, Button, Input, Progress, Segmented, Splitter, Switch, Tour, message, type TourProps } from 'antd'
import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { post, ApiError } from '../../api/client'
import { useAttempt, useInvalidate, useProblem, useTbSubmission } from '../../api/hooks'
import type { AttemptDetail, ProblemDetail, Step } from '../../api/types'
import CodeEditor from '../../components/CodeEditor'
import ChatPanel from '../../components/ChatPanel'
import { ErrorState, Loading, QuadrantBadge } from '../../components/Common'
import { HardwareCompare, HardwarePredict, regCandidates, type HardwareAnswers } from '../../components/HardwarePanel'
import { Term } from '../../components/Glossary'
import HintLadder, { AnswerCard } from '../../components/HintLadder'
import ShuffleExperiment from '../../components/ShuffleExperiment'
import StepBar from '../../components/StepBar'
import WaveformView from '../../components/WaveformView'
import { reporter } from '../../lib/events'
import { QUADRANT_HINT, TAG_LABEL, percent } from '../../lib/format'
import Markdown from '../../lib/markdown'
import './Workbench.css'

type Phase = 'predicting' | 'ready' | 'running' | 'investigating' | 'make' | 'done'
const CONFIDENCE_LABEL: Record<number, string> = { 1: '没把握', 2: '有点把握', 3: '很有把握' }
type Dock = 'wave' | 'hw' | 'shuffle' | 'errors'
const RUNNING = new Set(['queued', 'running'])
const EMPTY_HW: HardwareAnswers = { ff_count: null, latch: null, ff_signals: [] }

function useWideEnough() {
  const [wide, setWide] = useState(() => window.innerWidth >= 1024)
  useEffect(() => {
    const on = () => setWide(window.innerWidth >= 1024)
    window.addEventListener('resize', on)
    return () => window.removeEventListener('resize', on)
  }, [])
  return wide
}

function phaseOf(p: ProblemDetail, a: AttemptDetail | undefined, repredict: boolean): Phase {
  const step = p.progress.step
  const pending = p.pending_prediction.length > 0
  if (a && RUNNING.has(a.status)) return 'running'
  if (pending) return 'ready'
  if (!p.flags.predict_step && (step === 'run' || step === 'predict' || step === 'modify')) return 'ready'
  if (step === 'predict' || step === 'run' || step === 'modify' || repredict) return 'predicting'
  if (step === 'investigate') return 'investigating'
  if (step === 'make') return 'make'
  return 'done'
}

export default function Workbench() {
  const { pid = '' } = useParams()
  const wide = useWideEnough()
  const problemQ = useProblem(pid)
  if (!wide) {
    return <div className="ws-narrow" data-testid="narrow">请在电脑上做题（窗口宽度至少 1024 像素）</div>
  }
  if (problemQ.isLoading) return <Loading rows={12} />
  if (problemQ.error || !problemQ.data) return <ErrorState error={problemQ.error} onRetry={() => problemQ.refetch()} />
  // key：换了一道题就重新挂载，代码、预测、提示等状态都从这道题重新开始
  return <WorkbenchInner key={problemQ.data.id} p={problemQ.data} />
}

function WorkbenchInner({ p }: { p: ProblemDetail }) {
  const navigate = useNavigate()
  const invalidate = useInvalidate()
  const [viewAttemptId, setViewAttemptId] = useState<number | null>(null)
  const attemptId = viewAttemptId ?? p.latest_attempt_id
  const attemptQ = useAttempt(attemptId)
  const a = attemptQ.data
  const [repredict, setRepredict] = useState(false)
  const phase = phaseOf(p, a, repredict)
  const step = p.progress.step

  const [code, setCode] = useState(p.code)
  const [tbCode, setTbCode] = useState(p.latest_tb?.code ?? p.tb_template ?? '')
  const [editorTab, setEditorTab] = useState<'design' | 'tb'>(step === 'make' ? 'tb' : 'design')
  const [pred, setPred] = useState<Record<string, string | null>>({})
  const [hw, setHw] = useState<HardwareAnswers>(EMPTY_HW)
  const [confidence, setConfidence] = useState<number | null>(null)   // 预测把握程度 1–3
  const [dock, setDock] = useState<Dock>('wave')
  const [radix, setRadix] = useState<'hex' | 'bin'>('hex')
  const [diffView, setDiffView] = useState(false)
  const [selected, setSelected] = useState<string | null>(null)
  const [hoverLine, setHoverLine] = useState<number | null>(null)
  const [explain, setExplain] = useState('')
  const [feedback, setFeedback] = useState<{ step?: string; line?: string }>({})
  const [busy, setBusy] = useState(false)
  const [hintErr, setHintErr] = useState<string | null>(null)
  const [hintBusy, setHintBusy] = useState(false)
  const [tbSubId, setTbSubId] = useState<number | null>(p.latest_tb?.id ?? null)
  const tbQ = useTbSubmission(tbSubId)
  const lastStep = useRef<string | null>(null)

  const clocked = p.skeleton.inputs.some((i) => i.name === 'rst' || i.name === 'clk')
  const predictCells = useMemo(() => p.predict_points.flatMap((pt) => pt.steps.map((s) => ({ signal: pt.signal, step: s }))), [p])
  const pendingWave = p.pending_prediction.find((x) => x.kind === 'waveform')
  const pendingHw = p.pending_prediction.find((x) => x.kind === 'hardware')
  const judge = a?.status === 'done' ? a.judge : null
  const compiled = !!judge?.compile.ok
  const inv = a?.investigation ?? null
  const showShuffle = p.flags.shuffle && p.knowledge_points.some((k) => k.code === 'parallel')

  // 打开题目、进入步骤、查看波形：界面事件
  useEffect(() => {
    reporter.track('problem.open', { problem_id: p.id })
  }, [p.id])
  useEffect(() => {
    if (lastStep.current !== step) {
      reporter.track('step.enter', { problem_id: p.id, payload: { step } })
      lastStep.current = step
    }
  }, [step, p.id])
  useEffect(() => {
    if (a && a.status === 'done' && compiled && dock === 'wave') {
      reporter.track('waveform.view', { problem_id: p.id, attempt_id: a.id })
    }
  }, [a?.id, a?.status, dock]) // eslint-disable-line react-hooks/exhaustive-deps

  // 判完之后刷新题目进度；编译没通过时切到报错页
  const prevStatus = useRef(a?.status)
  useEffect(() => {
    if (prevStatus.current && RUNNING.has(prevStatus.current) && a?.status === 'done') {
      void invalidate(['problem', p.id])
      setDock(a.judge?.compile.ok ? 'wave' : 'errors')
      setRepredict(false)
      setFeedback({})
    }
    prevStatus.current = a?.status
  }, [a?.status]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (tbQ.data && tbQ.data.status === 'done') void invalidate(['problem', p.id])
  }, [tbQ.data?.status]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (step === 'make') setEditorTab('tb') }, [step])

  const editable = (phase === 'predicting' && (p.editable || repredict)) && p.primm_type !== 'predict'
  const predictedFromAttempt = useMemo(() => {
    const w = a?.predictions.find((x) => x.kind === 'waveform')
    const map: Record<string, string> = {}
    for (const c of w?.answers?.cells ?? []) map[`${c.signal}@${c.step}`] = c.value
    return map
  }, [a])
  const pendingMap = useMemo(() => {
    const map: Record<string, string> = {}
    for (const c of pendingWave?.answers?.cells ?? []) map[`${c.signal}@${c.step}`] = c.value
    return map
  }, [pendingWave])

  // 联动：选中信号 → 驱动行；悬停代码行 → 这一行赋值的信号
  const drivers = judge?.drivers ?? {}
  const lineBlocked = phase === 'investigating' && !!inv?.locate_line.required && !inv.locate_line.done
  const driverLines = !lineBlocked && selected ? drivers[selected] ?? [] : []
  const hoverSignals = hoverLine && !lineBlocked
    ? Object.entries(drivers).filter(([, lines]) => lines.includes(hoverLine)).map(([s]) => s) : []
  const linkedSignals = [...new Set([...(selected && !lineBlocked ? [selected] : []), ...hoverSignals])]

  const allPredicted = predictCells.every((c) => pred[`${c.signal}@${c.step}`]) &&
    (!p.hardware_questions.includes('ff_count') || hw.ff_count !== null) &&
    (!p.hardware_questions.includes('latch') || hw.latch !== null) && confidence !== null

  async function act<T>(fn: () => Promise<T>): Promise<T | undefined> {
    setBusy(true)
    try {
      return await fn()
    } catch (e) {
      message.warning(e instanceof ApiError ? e.message : '操作没有成功，请重试')
      return undefined
    } finally {
      setBusy(false)
    }
  }

  async function lockPrediction() {
    await act(async () => {
      const cells = predictCells.map((c) => ({ ...c, value: pred[`${c.signal}@${c.step}`] }))
      await post(`/api/student/problems/${p.id}/predictions`, {
        waveform: { cells }, hardware: p.hardware_questions.length ? hw : undefined, confidence,
      })
      setRepredict(false)
      await invalidate(['problem', p.id])
      message.success('预测已锁定，可以运行仿真了')
    })
  }

  async function runSim() {
    await act(async () => {
      await reporter.flush()       // 先把界面事件发完，盲改率依赖事件顺序
      const r = await post<{ attempt_id: number }>(`/api/student/problems/${p.id}/attempts`, { code })
      setViewAttemptId(r.attempt_id)
      setPred({})
      setHw(EMPTY_HW)
      setConfidence(null)
      setSelected(null)
      await invalidate(['problem', p.id])
    })
  }

  async function locate(kind: 'locate_step' | 'locate_line', chosen: Record<string, unknown>) {
    if (!a) return
    const r = await act(() => post<{ correct: boolean; message: string }>(`/api/student/attempts/${a.id}/investigations`, { kind, chosen }))
    if (!r) return
    setFeedback((f) => ({ ...f, [kind === 'locate_step' ? 'step' : 'line']: r.message }))
    await invalidate(['attempt', a.id], ['problem', p.id])
  }

  async function submitExplain() {
    if (!a) return
    await act(async () => {
      await post(`/api/student/attempts/${a.id}/explanations`, { text: explain })
      setExplain('')
      await invalidate(['attempt', a.id], ['problem', p.id])
    })
  }

  async function requestHint() {
    if (!a || hintBusy) return                 // 连点两下只发一次，避免同一级提示生成两条
    setHintErr(null)
    setHintBusy(true)
    try {
      await post(`/api/student/attempts/${a.id}/hints`)
      await invalidate(['attempt', a.id])
    } catch (e) {
      setHintErr(e instanceof ApiError ? e.message : '暂时拿不到提示')
    } finally {
      setHintBusy(false)
    }
  }

  async function runShuffle(prediction: 'change' | 'same') {
    if (!a) return
    await act(async () => {
      await post(`/api/student/attempts/${a.id}/shuffle`, { prediction })
      await invalidate(['attempt', a.id])
    })
  }

  async function submitTb() {
    await act(async () => {
      const r = await post<{ tb_submission_id: number }>(`/api/student/problems/${p.id}/testbench`, { code: tbCode })
      setTbSubId(r.tb_submission_id)
    })
  }

  function onCellClick(signal: string, s: number, row: string, isMismatch: boolean) {
    if (!a) return
    reporter.track('waveform.cell_click', { problem_id: p.id, attempt_id: a.id, payload: { step: s, signal, row, is_mismatch: isMismatch } })
    if (phase === 'investigating' && inv?.locate_step.required && !inv.locate_step.done && (row === 'actual')) {
      void locate('locate_step', { step: s, signal })
      return
    }
    setSelected(signal === selected ? null : signal)
  }

  function onLineClick(line: number) {
    if (phase === 'investigating' && inv?.locate_line.required && !inv.locate_line.done) {
      void locate('locate_line', { line })
    }
  }

  // ---------------------------------------------------------------- 顶栏按钮
  let primary: { label: string; onClick: () => void; disabled?: boolean; testId: string } | null = null
  let secondary: { label: string; onClick: () => void; testId: string } | null = null
  if (phase === 'predicting') primary = { label: '锁定我的预测', onClick: lockPrediction, disabled: !allPredicted, testId: 'btn-lock' }
  if (phase === 'ready') primary = { label: '仿真', onClick: runSim, disabled: !code.trim() && p.primm_type === 'make', testId: 'btn-run' }
  if (phase === 'running') primary = { label: '仿真中…', onClick: () => undefined, disabled: true, testId: 'btn-running' }
  if (phase === 'investigating') primary = { label: '提交解释', onClick: submitExplain, disabled: explain.trim().length < 4 || !!inv?.explanation.done, testId: 'btn-explain' }
  if (phase === 'make') primary = { label: '提交 testbench 打分', onClick: submitTb, disabled: !tbCode.trim() || (tbQ.data ? RUNNING.has(tbQ.data.status) : false), testId: 'btn-tb' }
  if (phase === 'done') primary = { label: '回到题目列表', onClick: () => navigate('/student/problems'), testId: 'btn-back' }
  if (p.primm_type === 'make' && (phase === 'investigating' || phase === 'make' || phase === 'done') && !repredict) {
    secondary = { label: '重新预测并仿真', onClick: () => { setRepredict(true); setEditorTab('design') }, testId: 'btn-repredict' }
  }

  // ---------------------------------------------------------------- 下一步做什么（高亮闪烁）
  const hwAnswered = (!p.hardware_questions.includes('ff_count') || hw.ff_count !== null) &&
    (!p.hardware_questions.includes('latch') || hw.latch !== null)
  const waveFilled = predictCells.every((c) => pred[`${c.signal}@${c.step}`])
  const next = nextStep({ p, phase, a, inv, editable, code, waveFilled, hwAnswered, explain, compiled: !!judge && compiled,
    judged: !!judge, step, tbOk: !!tbQ.data?.result?.ok, confidence })
  const pulse = (t: Target) => (next.target === t ? ' pulse-box' : '')
  const waveTabPulse = (next.target === 'wave' && dock !== 'wave') || (next.target === 'hw' && dock !== 'hw')

  // ---------------------------------------------------------------- 分步引导（第一次进入做题页时自动打开）
  const refs = {
    steps: useRef<HTMLDivElement>(null), left: useRef<HTMLDivElement>(null), editor: useRef<HTMLDivElement>(null),
    dock: useRef<HTMLDivElement>(null), hints: useRef<HTMLDivElement>(null), chat: useRef<HTMLDivElement>(null),
    primary: useRef<HTMLDivElement>(null), next: useRef<HTMLDivElement>(null),
  }
  const [tourOpen, setTourOpen] = useState(() => !readStore(TOUR_KEY))
  const closeTour = (finished: boolean) => {
    if (!tourOpen) return                 // antd 结束时 onFinish、onClose 都会触发，只记一次
    setTourOpen(false)
    writeStore(TOUR_KEY, '1')
    reporter.track('tour.done', { problem_id: p.id, payload: { finished } })
  }
  const tourSteps: TourProps['steps'] = [
    { title: '欢迎来到做题页', description: '每道题按“预测 → 运行 → 探究 → 修改 / 创作”几步走。上面这条是步骤条，当前在哪一步一目了然。', target: () => refs.steps.current! },
    { title: '下一步做什么，看这里', description: '这条提示会一直告诉你下一步该做什么；该点的地方会一闪一闪。', target: () => refs.next.current! },
    { title: '左边：任务和题目说明', description: '当前步骤的任务清单、题目说明（端口、举例）都在这里，内容多时可以上下滚动。中间的分隔条可以拖动调宽。', target: () => refs.left.current! },
    { title: '中间上方：代码编辑器', description: 'Verilog 代码写在这里。注意：你写的是“电路长什么样”，不是一步一步执行的程序。', target: () => refs.editor.current! },
    { title: '中间下方：波形和硬件', description: '运行前在“波形预测”里填你猜的输出，在“硬件”里猜会综合出几个触发器；运行后在这里对照真实仿真结果。', target: () => refs.dock.current! },
    { title: '右上：提示', description: '卡住了就要提示：1 级讲思路，2 级指出问题在哪，3 级给代码框架。实在不会，满足条件后还可以看参考答案。', target: () => refs.hints.current! },
    { title: '右下：问助教', description: '有任何不懂都可以问，比如“always 是什么意思”。点“放大”可以在大窗口里聊。', target: () => refs.chat.current! },
    { title: '主按钮', description: '每一步要点的主按钮都在右上角：锁定预测、仿真、提交解释……', target: () => refs.primary.current! },
  ]

  // ---------------------------------------------------------------- 渲染
  const waveProps = {
    steps: p.skeleton.steps, inputs: p.skeleton.inputs, outputs: p.skeleton.outputs, clocked, radix,
    linkedSignals, predictCells,
  }
  let wave: JSX.Element
  if (phase === 'predicting' || phase === 'ready') {
    wave = <WaveformView mode="predict" {...waveProps} predicted={phase === 'ready' ? pendingMap : pred}
      onPredict={phase === 'predicting' ? (signal, s, v) => setPred((x) => ({ ...x, [`${signal}@${s}`]: v })) : undefined} />
  } else if (phase === 'running') {
    wave = <div className="ws-running" data-testid="running"><Progress percent={a?.status === 'running' ? 60 : 20} status="active" showInfo={false} />
      <div className="muted">{a?.status === 'running' ? '编译 → 仿真 → 综合 → 静态检查…' : '排队中…'}</div></div>
  } else if (judge && compiled && judge.sim.trace.length) {
    const diff = diffView && a?.previous
    wave = diff
      ? <WaveformView mode="diff" {...waveProps} expected={a!.previous!.trace} actual={judge.sim.trace} diffLabels={['修改前', '修改后']} />
      : <WaveformView mode="compare" {...waveProps} actual={judge.sim.trace} expected={a?.expected ?? []}
          predicted={predictedFromAttempt} firstMismatchStep={judge.sim.first_mismatch?.step ?? null}
          pickedCell={inv?.locate_step.done ? inv.locate_step.chosen : null} onCellClick={onCellClick} />
  } else if (judge && judge.sim.timeout) {
    wave = <Alert type="warning" showIcon style={{ margin: 12 }} message="仿真超时" description="10 秒内没有跑完，可能有组合环路（信号自己驱动自己）或死循环。" />
  } else {
    wave = <div className="muted" style={{ padding: 16 }}>{judge && !compiled ? '编译没通过，先看“编译报错”。' : '还没有仿真结果。'}</div>
  }

  const compileErrors = (judge && !compiled ? judge.compile.errors : []).filter((e) => e.file === 'student.v' && e.line)
    .map((e) => ({ line: e.line!, message: e.message }))
  const editorValue = editorTab === 'tb' ? tbCode : (phase === 'investigating' || phase === 'done' || phase === 'make') && a && !repredict ? a.code : code
  const sizes = readSizes()

  return (
    <div className="ws" data-testid="workbench">
      <header className="ws-top">
        <Link className="back" to="/student/problems">← 题目</Link>
        <div className="ws-title" title={p.title}>{p.title}</div>
        {p.stage === 'beginner' && <span className="chip green">入门</span>}
        {p.knowledge_points.slice(0, 2).map((k) => <span key={k.code} className="chip kp-chip">{k.name.replace(/（.*）/, '')}</span>)}
        <span className="chip blue">{p.primm_label}</span>
        <div ref={refs.steps} className="steps-wrap"><StepBar steps={p.steps} current={step} completed={step === 'done' ? p.steps : p.progress.completed} /></div>
        <Button type="text" size="small" onClick={() => setTourOpen(true)} data-testid="btn-tour">操作指引</Button>
        {secondary && <Button onClick={secondary.onClick} data-testid={secondary.testId}>{secondary.label}</Button>}
        <div ref={refs.primary}>
          {primary && <Button type="primary" onClick={primary.onClick} disabled={primary.disabled || busy} loading={busy && phase !== 'running'}
            className={next.target === 'primary' && !primary.disabled ? 'pulse' : undefined} data-testid={primary.testId}>{primary.label}</Button>}
        </div>
      </header>
      <div className="next-bar" ref={refs.next} data-testid="next-step"><i className="dot" /><b>下一步：</b><span>{next.text}</span></div>

      <div className="ws-body">
        <Splitter onResizeEnd={(s) => saveSizes('h', s)}>
          <Splitter.Panel defaultSize={sizes.h?.[0] ?? '24%'} min="14%" max="50%" collapsible>
            <aside className="pane-scroll col" data-testid="col-left" ref={refs.left}>
              <TaskCard p={p} a={a} phase={phase} allPredicted={allPredicted} inv={inv} feedback={feedback}
                explain={explain} setExplain={setExplain} tb={tbQ.data} repredict={repredict} explainPulse={next.target === 'explain'}
                confidence={confidence} setConfidence={setConfidence} confidencePulse={next.target === 'confidence'} />
              <SpecCard p={p} />
              <PredictionCard p={p} a={a} phase={phase} />
            </aside>
          </Splitter.Panel>

          <Splitter.Panel min="28%">
            <section className="col center" data-testid="col-center">
              <Splitter layout="vertical" onResizeEnd={(s) => saveSizes('c', s)}>
                <Splitter.Panel defaultSize={sizes.c?.[0] ?? '52%'} min="15%">
                  <div className={'card editor' + pulse('editor')} ref={refs.editor}>
                    <div className="ed-h">
                      <button className={editorTab === 'design' ? 'ed-tab on' : 'ed-tab'} onClick={() => setEditorTab('design')}>top_module.v</button>
                      {p.primm_type === 'make' && (step === 'make' || step === 'done') &&
                        <button className={(editorTab === 'tb' ? 'ed-tab on' : 'ed-tab') + (next.target === 'tb' && editorTab !== 'tb' ? ' pulse' : '')}
                          onClick={() => setEditorTab('tb')} data-testid="tab-tb">我的 testbench</button>}
                      <span className="muted">{editorTab === 'tb' ? '写激励，让错误的电路暴露出来' : editable ? '可以编辑' : '只读'}</span>
                      {driverLines.length > 0 && editorTab === 'design' &&
                        <span className="drv-note">黄底：驱动 {selected} 的代码（第 {driverLines.join('、')} 行）</span>}
                      {lineBlocked && <span className="drv-note">在代码里点出决定 {inv?.target.signal} 的那一行</span>}
                    </div>
                    <CodeEditor value={editorValue}
                      onChange={editorTab === 'tb' ? setTbCode : setCode}
                      readOnly={editorTab === 'tb' ? phase !== 'make' : !editable}
                      driverLines={editorTab === 'design' ? driverLines : []}
                      pickedLine={editorTab === 'design' && inv?.locate_line.done ? inv.locate_line.chosen?.line ?? null : null}
                      errors={editorTab === 'design' ? compileErrors : []}
                      onLineClick={editorTab === 'design' ? onLineClick : undefined}
                      onLineHover={editorTab === 'design' ? setHoverLine : undefined} />
                  </div>
                </Splitter.Panel>
                <Splitter.Panel min="15%">
                  <div className={'card dock' + (next.target === 'wave' && dock === 'wave' ? ' pulse-box' : next.target === 'hw' && dock === 'hw' ? ' pulse-box' : '')} ref={refs.dock}>
                    <div className="dock-tabs" role="tablist">
                      <button role="tab" aria-selected={dock === 'wave'} className={(dock === 'wave' ? 'on' : '') + (waveTabPulse && next.target === 'wave' ? ' pulse' : '')}
                        onClick={() => setDock('wave')} data-testid="dock-wave">
                        {phase === 'predicting' || phase === 'ready' ? '波形预测' : '波形对照'}</button>
                      <button role="tab" aria-selected={dock === 'hw'} className={(dock === 'hw' ? 'on' : '') + (waveTabPulse && next.target === 'hw' ? ' pulse' : '')}
                        onClick={() => setDock('hw')} data-testid="dock-hw">硬件</button>
                      {showShuffle && <button role="tab" aria-selected={dock === 'shuffle'} className={dock === 'shuffle' ? 'on' : ''} onClick={() => setDock('shuffle')} data-testid="dock-shuffle">顺序打乱实验</button>}
                      {judge && !compiled && <button role="tab" aria-selected={dock === 'errors'} className={dock === 'errors' ? 'on bad' : 'bad'} onClick={() => setDock('errors')}>编译报错</button>}
                      <span className="right">
                        {a?.previous && compiled && phase !== 'predicting' && phase !== 'ready' && dock === 'wave' &&
                          <label className="mini-switch"><Switch size="small" checked={diffView} onChange={setDiffView} /> 修改前后对比</label>}
                        <label className="mini-switch"><Switch size="small" checked={radix === 'bin'} onChange={(v) => setRadix(v ? 'bin' : 'hex')} /> 二进制</label>
                        <span>真实仿真：iverilog · 每个 <Term k="STEP" /> 一个时钟周期</span>
                      </span>
                    </div>
                    <div className="dock-body">
                      {dock === 'wave' && <div className="wave-wrap">{wave}{phase !== 'predicting' && phase !== 'ready' && compiled && <WaveLegend />}</div>}
                      {dock === 'hw' && (
                        <div style={{ padding: 16 }}>
                          {phase === 'predicting'
                            ? <HardwarePredict questions={p.hardware_questions} value={hw} onChange={setHw} candidates={regCandidates(code || p.starter || '')} />
                            : phase === 'ready'
                              ? <HardwarePredict questions={p.hardware_questions} value={{ ...EMPTY_HW, ...(pendingHw?.answers ?? {}) }} onChange={() => undefined} candidates={[]} disabled />
                              : <HardwareCompare items={a?.evaluation?.hardware.items ?? null} hardware={judge?.hardware ?? null} questions={p.hardware_questions} />}
                        </div>
                      )}
                      {dock === 'shuffle' && <ShuffleExperiment attempt={a ?? null} skeleton={p.skeleton} onRun={runShuffle} clocked={clocked}
                        running={!!a?.shuffle && RUNNING.has(a.shuffle.status)} />}
                      {dock === 'errors' && judge && !compiled && (
                        <div style={{ padding: 16 }} data-testid="compile-errors">
                          {judge.compile.errors.map((e, i) => (
                            <div key={i} className="err-row"><b>{e.file === 'tb.v' ? 'testbench' : e.line ? `第 ${e.line} 行` : ''}</b> {e.message}</div>
                          ))}
                          <div className="muted" style={{ marginTop: 8 }}>改好代码后，重新预测再运行。看不懂报错？可以要提示或问助教。</div>
                        </div>
                      )}
                    </div>
                  </div>
                </Splitter.Panel>
              </Splitter>
            </section>
          </Splitter.Panel>

          <Splitter.Panel defaultSize={sizes.h?.[2] ?? '28%'} min="18%" max="55%" collapsible>
            <aside className="col right-col" data-testid="col-right">
              <Splitter layout="vertical" onResizeEnd={(s) => saveSizes('r', s)}>
                <Splitter.Panel defaultSize={sizes.r?.[0] ?? '50%'} min="12%">
                  <div className="pane-scroll">
                    <div className="card">
                      <div className="card-h">本题状态 {p.attempts.length > 0 && <small>第 {a?.attempt_no ?? p.attempts.length} 次提交</small>}</div>
                      <div className="card-b">
                        <QuadrantBadge quadrant={a?.status === 'done' ? a.quadrant : null} />
                        <p className="status-text muted">{a?.status === 'done' && a.quadrant && a.quadrant !== 'none'
                          ? QUADRANT_HINT[a.quadrant] : a?.status === 'done' && !compiled ? '编译没通过，这次不判定象限。' : '运行之后，这里会显示本题状态。'}</p>
                        {a?.status === 'done' && (a.judge?.tags ?? []).filter((t) => t !== 'sim_mismatch').map((t) =>
                          <div key={t} className="tag-row">· {TAG_LABEL[t] ?? t}</div>)}
                        {a?.misconceptions.map((m) => <div key={m.code} className="tag-row warn">· {m.label}</div>)}
                        {a?.status === 'done' && a.confident_miss && (
                          <div className="conf-note miss" data-testid="confident-miss">你选了“很有把握”，但预测没对上。这往往说明有一个自己没意识到的误区——
                            对照波形找找第一个预测错的格子，弄明白它，比做对一道新题更有收获。</div>)}
                        {a?.status === 'done' && a.under_confident && (
                          <div className="conf-note ok" data-testid="under-confident">你选了“没把握”，其实预测对了。你比自己以为的更懂，下次可以更有信心一点。</div>)}
                      </div>
                    </div>
                    <div className="card" ref={refs.hints}>
                      <div className="card-h">提示 <small>一次解锁一级</small></div>
                      <div className="card-b">
                        {a?.status === 'done'
                          ? <HintLadder hints={a.hints} onRequest={requestHint} error={hintErr} loading={hintBusy} highlight={next.target === 'hint'} />
                          : <div className="muted">运行一次之后可以要提示。还没开始写？可以先问下面的助教“这道题要我做什么”。</div>}
                        <AnswerCard problemId={p.id} status={p.answer} onChanged={() => void invalidate(['problem', p.id])} />
                      </div>
                    </div>
                  </div>
                </Splitter.Panel>
                <Splitter.Panel min="22%">
                  <div className="chat-wrap" ref={refs.chat}>
                    <ChatPanel problemId={p.id} attemptId={a?.id ?? null} enabled={p.flags.chat} />
                  </div>
                </Splitter.Panel>
              </Splitter>
            </aside>
          </Splitter.Panel>
        </Splitter>
      </div>
      <Tour open={tourOpen} steps={tourSteps} onClose={() => closeTour(false)} onFinish={() => closeTour(true)}
        indicatorsRender={(cur, total) => <span className="muted">{cur + 1} / {total}</span>} />
    </div>
  )
}

// ---------------------------------------------------------------- 下一步

type Target = 'editor' | 'wave' | 'hw' | 'confidence' | 'primary' | 'explain' | 'tb' | 'hint' | 'none'

function nextStep(x: {
  p: ProblemDetail; phase: Phase; a: AttemptDetail | undefined; inv: AttemptDetail['investigation']; editable: boolean
  code: string; waveFilled: boolean; hwAnswered: boolean; explain: string; compiled: boolean; judged: boolean
  step: Step; tbOk: boolean; confidence: number | null
}): { text: string; target: Target } {
  const { p, phase, a, inv } = x
  const signals = p.predict_points.map((pt) => pt.signal).join('、')
  if (phase === 'running') return { text: '正在编译、仿真和综合，稍等几秒……', target: 'none' }
  if (phase === 'predicting') {
    if (x.judged && !x.compiled && x.editable) {
      return { text: '代码没有编译通过：看下方“编译报错”和代码里的红线，改好后重新填预测再运行。看不懂报错可以要提示或问助教。', target: 'editor' }
    }
    if (x.editable && !x.code.trim()) {
      return { text: '先在中间的代码编辑器里，按左边的题目说明写出 top_module。不知道从哪写起？可以问右下角的助教“给我一个代码框架”。', target: 'editor' }
    }
    if (!x.waveFilled) {
      return { text: `在下方“波形预测”里，把 ${signals} 的每个 ? 格填上你预测的值（单比特点一下切换 0/1，多位的点一下输入数字；波形可以左右滚动）。`, target: 'wave' }
    }
    if (!x.hwAnswered && p.hardware_questions.length) {
      return { text: '切到“硬件”页，猜一猜：这段代码会综合出几个触发器？有没有锁存器？', target: 'hw' }
    }
    if (x.confidence === null) {
      return { text: '在左边选一下：你对这些预测有多大把握？照实选就行，没有对错，也不影响成绩。', target: 'confidence' }
    }
    return { text: '预测都填好了，点右上角闪烁的“锁定我的预测”。锁定之后就不能再改了。', target: 'primary' }
  }
  if (phase === 'ready') return { text: '点右上角闪烁的“仿真”，看看电路实际是怎么运行的。', target: 'primary' }
  if (phase === 'investigating' && inv) {
    if (inv.locate_step.required && !inv.locate_step.done) {
      return { text: '在下方波形里，点出第一个对不上的格子（“你的电路”那一行）。红底的格子表示和期望不一样。', target: 'wave' }
    }
    if (inv.locate_line.required && !inv.locate_line.done) {
      return { text: `在代码编辑器里，点出决定 ${inv.target.signal ?? '这个信号'} 的那一行（点行号左边）。`, target: 'editor' }
    }
    if (!inv.explanation.done) {
      return x.explain.trim().length < 4
        ? { text: '在左边的输入框里，用一句话写下你认为的原因（写错也没关系）。', target: 'explain' }
        : { text: '写好了，点右上角闪烁的“提交解释”。', target: 'primary' }
    }
  }
  if (phase === 'make') {
    return x.tbOk ? { text: '打分完成，可以看看哪些错误电路没被抓住，改进激励再提交。', target: 'none' }
      : { text: '最后一步：在“我的 testbench”里写测试激励，然后点右上角“提交 testbench 打分”。', target: 'tb' }
  }
  if (phase === 'done') {
    if (a?.status === 'done' && a.sim_ok === false) return { text: '仿真还没对上：先要提示或问助教，改好后点“重新预测并仿真”。', target: 'hint' }
    return { text: '这道题完成了！点右上角回到题目列表，做下一题。', target: 'primary' }
  }
  return { text: '按左边的任务清单一步一步来。', target: 'none' }
}

// ---------------------------------------------------------------- 小工具：浏览器本地存储（只存界面偏好，失败就用默认值）

const TOUR_KEY = 'tour.workbench.v1'
const SIZES_KEY = 'ws.sizes.v1'

function readStore(key: string): string | null {
  try { return window.localStorage.getItem(key) } catch { return null }
}
function writeStore(key: string, value: string) {
  try { window.localStorage.setItem(key, value) } catch { /* 隐私模式等：忽略 */ }
}
function readSizes(): Record<string, string[]> {
  try { return JSON.parse(readStore(SIZES_KEY) ?? '{}') } catch { return {} }
}
function saveSizes(which: string, px: number[]) {
  const total = px.reduce((s, x) => s + x, 0)
  if (!total) return
  writeStore(SIZES_KEY, JSON.stringify({ ...readSizes(), [which]: px.map((x) => `${((x / total) * 100).toFixed(1)}%`) }))
}

function WaveLegend() {
  return (
    <div className="legend">
      <span><b style={{ background: 'var(--c-error-bg)', border: '1px solid var(--c-error)' }} />你的电路与期望不同</span>
      <span><b style={{ background: 'var(--c-success)' }} />预测对 ✓</span>
      <span><b style={{ background: 'var(--c-warning)' }} />预测没对上 ✗</span>
      <span><b style={{ background: 'var(--c-error)', width: 3 }} />第一个对不上的周期</span>
      <span><b style={{ background: 'var(--c-link)' }} />与选中代码联动的信号</span>
    </div>
  )
}

// ---------------------------------------------------------------- 左栏卡片

function Tick({ done, n }: { done: boolean; n: number | string }) {
  return <div className={done ? 'tick y' : 'tick n'}>{done ? '✓' : n}</div>
}

function TaskCard({ p, a, phase, allPredicted, inv, feedback, explain, setExplain, tb, repredict, explainPulse,
  confidence, setConfidence, confidencePulse }: {
  p: ProblemDetail; a: AttemptDetail | undefined; phase: Phase; allPredicted: boolean
  inv: AttemptDetail['investigation']; feedback: { step?: string; line?: string }
  explain: string; setExplain: (v: string) => void; tb: ReturnType<typeof useTbSubmission>['data']; repredict: boolean
  explainPulse?: boolean
  confidence: number | null; setConfidence: (v: number) => void; confidencePulse?: boolean
}) {
  const step = p.progress.step
  const stepNo: Record<Step, string> = { predict: '①', run: '②', investigate: '③', modify: '④', make: '⑤', done: '✓' }
  const name: Record<Step, string> = { predict: '预测', run: '运行', investigate: '探究', modify: '修改', make: '创作', done: '完成' }
  let title = `第 ${stepNo[step]} 步 · ${name[step]}`
  let body: JSX.Element
  if (phase === 'predicting' || phase === 'ready' || phase === 'running') {
    const isModify = step === 'modify'
    if (repredict) title = '重新预测并仿真'
    body = (
      <ul>
        {isModify && <li><Tick done={false} n="·" /><div><b>修改目标：</b>{p.modify_goal}</div></li>}
        {p.primm_type === 'make' && (step === 'predict' || repredict) &&
          <li><Tick done={phase !== 'predicting'} n={1} /><div>按题目说明，在编辑器里写出 top_module
            <div className="ans">写的是“电路长什么样”：每条 assign / always 描述的硬件都是同时工作的</div></div></li>}
        {p.primm_type !== 'make' && !isModify && <li><Tick done={phase !== 'predicting'} n={1} /><div>读懂起始代码（只读）
          <div className="ans">逐行看：每个输出是由哪条语句决定的？</div></div></li>}
        <li><Tick done={phase !== 'predicting'} n={2} /><div>{isModify ? '改完先预测变化：' : ''}在“<Term k="波形">波形</Term><Term k="预测">预测</Term>”里填出 {p.predict_points.map((x) => x.signal).join('、')} 的 ? 格
          <div className="ans">每个 <Term k="STEP" /> 是一个<Term k="时钟">时钟</Term>周期；单比特点击切换 0/1，多位的点击后输入二进制或 0x 开头的十六进制</div></div></li>
        {p.hardware_questions.length > 0 && <li><Tick done={phase !== 'predicting'} n={3} /><div>在“硬件”里回答：会<Term k="综合">综合</Term>出几个<Term k="触发器">触发器</Term>、有没有<Term k="锁存器">锁存器</Term>
          <div className="ans">纯<Term k="组合逻辑">组合逻辑</Term>没有触发器；always @(posedge clk) 里赋值的信号会变成触发器</div></div></li>}
        {p.flags.predict_step && (
          <li data-testid="task-confidence"><Tick done={phase !== 'predicting' || confidence !== null} n={4} /><div>你对这些预测有多大把握？
            {phase === 'predicting'
              ? <div className={confidencePulse ? 'conf-pick pulse-box' : 'conf-pick'}>
                  <Segmented size="small" value={confidence ?? undefined} onChange={(v) => setConfidence(Number(v))} data-testid="confidence"
                    options={[{ label: '没把握', value: 1 }, { label: '有点把握', value: 2 }, { label: '很有把握', value: 3 }]} /></div>
              : <div className="ans">{CONFIDENCE_LABEL[p.pending_prediction[0]?.confidence ?? a?.confidence ?? 0] ?? '—'}</div>}
            <div className="ans">照实选就行：猜错又很有把握的地方，正是最值得弄懂的地方</div></div></li>
        )}
        <li><Tick done={phase === 'running'} n={5} /><div>{phase === 'predicting' ? (allPredicted ? '都填好了，点右上角“锁定我的预测”' : '锁定预测后才能运行') : '预测已锁定，点“仿真”'}</div></li>
      </ul>
    )
  } else if (phase === 'investigating' && inv) {
    const done = [inv.locate_step, inv.locate_line].filter((t) => t.required && t.done).length + (inv.explanation.done ? 1 : 0)
    const total = [inv.locate_step, inv.locate_line].filter((t) => t.required).length + 1
    const target = inv.target
    const what = target.kind === 'sim' ? '第一个对不上的格子' : '第一个你没预测对的格子'
    body = (
      <>
        <small className="task-count" data-testid="task-count">{done} / {total} 已完成</small>
        <ul>
          {inv.locate_step.required && (
            <li data-testid="task-locate-step"><Tick done={inv.locate_step.done} n={1} /><div>在波形里点出{what}（“你的电路”那一行）
              <div className="ans">{inv.locate_step.done ? `你选的：STEP ${inv.locate_step.chosen.step} · ${inv.locate_step.chosen.signal} ✓` : feedback.step ?? ''}</div></div></li>
          )}
          {inv.locate_line.required && (
            <li data-testid="task-locate-line"><Tick done={inv.locate_line.done} n={2} /><div>在代码里点出决定 {target.signal} 的那一行
              <div className="ans">{inv.locate_line.done ? `你选的：第 ${inv.locate_line.chosen.line} 行 ✓` : feedback.line ?? ''}</div></div></li>
          )}
          <li data-testid="task-explain"><Tick done={inv.explanation.done} n={3} /><div>
            {target.kind === 'sim' ? `用一句话解释：为什么第 ${target.step} 步的 ${target.signal} 和期望对不上？`
              : target.kind === 'pred' ? `用一句话解释：为什么第 ${target.step} 步的 ${target.signal} 实际是这个值？`
                : `用一句话解释：${target.signal} 的值是怎么来的？`}
            {!inv.explanation.done && <Input.TextArea aria-label="一句话解释" value={explain} onChange={(e) => setExplain(e.target.value)}
              autoSize={{ minRows: 3, maxRows: 5 }} maxLength={500} data-testid="explain-input" style={{ marginTop: 6 }}
              className={explainPulse ? 'pulse-box' : undefined} placeholder="例如：我把 = 写成了 <=，所以输出晚了一拍" />}
            {inv.explanation.done && <div className="ans">已提交 ✓</div>}
          </div></li>
        </ul>
      </>
    )
  } else if (phase === 'make') {
    const r = tb?.result
    body = (
      <ul>
        <li><Tick done n="✓" /><div>设计已经仿真通过</div></li>
        <li><Tick done={!!r} n={2} /><div>在“我的 testbench”里写激励：要让每一种可能的错误电路都和正确电路输出不同
          <div className="ans">每个采样点按“STEP 序号 | 输入 | 输出”打印一行</div></div></li>
        <li><Tick done={tb?.status === 'done' && !!r?.ok} n={3} /><div>提交打分
          {tb && RUNNING.has(tb.status) && <div className="ans">打分中…</div>}
          {r && !r.ok && <div className="ans bad">{r.message}</div>}
        </div></li>
      </ul>
    )
  } else {
    const r = tb?.result
    body = (
      <div data-testid="task-done">
        <p>这道题的步骤都完成了。</p>
        {r?.ok && <p style={{ marginTop: 8 }} data-testid="tb-score">你的激励抓住了 {r.caught.length}/{r.caught.length + r.missed.length} 个 bug</p>}
        {tb?.missed_types?.length ? <div className="ans">没抓住的：{tb.missed_types.join('；')}</div> : null}
        {a?.status === 'done' && a.sim_ok === false && <p className="muted">最近一次仿真还没通过，可以“重新预测并仿真”。</p>}
      </div>
    )
  }
  return (
    <div className="card task" data-testid="task-card">
      <div className="card-h">{title}</div>
      <div className="card-b">{body}
        {phase !== 'done' && tb?.result?.ok && phase === 'make' &&
          <div className="tb-result" data-testid="tb-score">你的激励抓住了 {tb.result.caught.length}/{tb.result.caught.length + tb.result.missed.length} 个 bug
            {tb.missed_types?.length ? <div className="ans">没抓住的：{tb.missed_types.join('；')}</div> : null}</div>}
      </div>
    </div>
  )
}

function SpecCard({ p }: { p: ProblemDetail }) {
  return (
    <div className="card spec" data-testid="spec-card">
      <div className="card-h">题目说明</div>
      <div className="card-b spec-body"><Markdown text={p.spec} skipTitle /></div>
    </div>
  )
}

function PredictionCard({ p, a, phase }: { p: ProblemDetail; a: AttemptDetail | undefined; phase: Phase }) {
  const ev = a?.status === 'done' ? a.evaluation : null
  if (phase === 'predicting' || !ev) {
    return (
      <div className="card">
        <div className="card-h">我的预测 <small>{p.pending_prediction.length ? '已锁定' : '运行前要先锁定'}</small></div>
        <div className="card-b muted">{p.pending_prediction.length ? '预测已锁定，运行之后在这里对照。' : '预测锁定后不能再改。'}</div>
      </div>
    )
  }
  const cells = ev.waveform.cells
  const label: Record<string, string> = { ff_count: '会综合出几个触发器', latch: '有没有锁存器', ff_signals: '哪些信号成了触发器' }
  const show = (q: string, v: any) => q === 'latch' ? (v ? '有' : '无') : Array.isArray(v) ? (v.join('、') || '（无）') : v ?? '—'
  return (
    <div className="card" data-testid="prediction-card">
      <div className="card-h">我的预测 <small>运行前已锁定</small></div>
      <div className="card-b">
        <div className="kv">
          <div className="it"><span className="lb">波形预测（{cells.length} 个格子）</span>
            <span>对了 {ev.waveform.hits} 个：{cells.map((c) => `STEP ${c.step}${c.correct === null ? ' ?' : c.correct ? ' ✓' : ' ✗'}`).join(' · ')}</span></div>
          {ev.hardware.items.map((it) => (
            <div className="it" key={it.question}><span className="lb">{label[it.question]}</span>
              <span>你预测 {show(it.question, it.value)} · 实际 {show(it.question, it.actual)} {it.correct === null ? '?' : it.correct ? <b className="ok">✓</b> : <b className="bad">✗</b>}</span></div>
          ))}
        </div>
        <div style={{ marginTop: 12, fontSize: 12 }} className="muted" data-testid="pred-accuracy">
          预测准确率 {ev.hits} / {ev.total} = {percent(ev.accuracy)}</div>
        <div className="bar"><i style={{ width: `${(ev.accuracy ?? 0) * 100}%` }} /></div>
      </div>
    </div>
  )
}

