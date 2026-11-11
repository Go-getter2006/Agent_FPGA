// 接口返回的数据结构（与 backend/app/api 保持一致）
export type Quadrant = 'mastered' | 'fragile' | 'design_gap' | 'concept_gap' | 'none'
export type Level = 'mastered' | 'fragile' | 'learning' | 'not_started'
export type Step = 'predict' | 'run' | 'investigate' | 'modify' | 'make' | 'done'
export type PrimmType = 'predict' | 'modify' | 'make'

export interface Me {
  user: { id: number; role: 'student' | 'teacher' | 'admin'; login_name: string; display_name: string }
  classes: { id: number; name: string; term: string; group: string }[]
  group: string | null
  flags: Record<string, boolean>
  consent: { status: string; version: string | null; current_version: string; required: boolean } | null
  app_version: string
}

export interface KP { code: string; name: string }

export interface TraceRow { step: number; inputs: Record<string, string>; outputs: Record<string, string> }

export interface Skeleton {
  steps: number[]
  inputs: { name: string; width: number; values: string[] }[]
  outputs: { name: string; width: number }[]
}

export interface PredictPoint { signal: string; steps: number[] }

export interface AttemptSummary {
  id: number; attempt_no: number; step: string; status: string; created_at: string
  sim_ok: boolean | null; quadrant: Quadrant | null; pred_accuracy: number | null; tags: string[]
}

export interface TbSubmission {
  id: number; status: string; score: number | null; created_at: string; code: string
  result: { ok: boolean; steps: number; score: number | null; caught: string[]; missed: string[];
            excluded: string[]; message: string | null; errors: CompileError[] } | null
  missed_types?: string[]
}

export interface ProblemDetail {
  id: string; title: string; primm_type: PrimmType; primm_label: string; difficulty: number
  knowledge_points: KP[]; spec: string; starter: string | null; modify_goal: string
  predict_points: PredictPoint[]; hardware_questions: string[]; skeleton: Skeleton
  tb_template: string | null; steps: Step[]
  progress: { step: Step; completed: Step[]; investigated: boolean; passed: boolean;
              modify_phase: boolean; tb_done: boolean }
  editable: boolean; code: string
  attempts: AttemptSummary[]; latest_attempt_id: number | null
  pending_prediction: { id: number; kind: 'waveform' | 'hardware'; answers: any; locked_at: string; confidence: number | null }[]
  latest_tb: TbSubmission | null
  flags: Record<string, boolean>
  stage: string
  answer: AnswerStatus
}

export interface CompileError { file: string | null; line: number | null; message: string }

export interface Judge {
  problem: string
  compile: { ok: boolean; errors: CompileError[] }
  sim: { ok: boolean; timeout: boolean; trace: TraceRow[];
         first_mismatch: { step: number; signal: string; expected: string | null; actual: string | null;
                           inputs: Record<string, string> } | null }
  synth: { ok: boolean | null; timeout: boolean; messages: string[] }
  hardware: { ff_signals: string[] | null; latch_signals: string[] | null; ff_count: number | null; lut_count: number | null }
  lint: { code: string; line: number | null; message: string }[]
  drivers: Record<string, number[]>
  drivers_granularity: 'statement' | 'block' | null
  tags: string[]
}

export interface EvalCell { signal: string; step: number; value: string | null; actual: string | null; correct: boolean | null }
export interface EvalItem { question: string; value: any; actual: any; correct: boolean | null }
export interface Evaluation {
  waveform: { cells: EvalCell[]; hits: number; total: number; accuracy: number | null }
  hardware: { items: EvalItem[]; hits: number; total: number; accuracy: number | null }
  hits: number; total: number; accuracy: number | null
}

export interface InvestigationTask { required: boolean; tries: number; done: boolean; chosen: any }
export interface InvestigationStatus {
  target: { kind: 'sim' | 'pred' | 'none'; step: number | null; signal: string | null }
  locate_step: InvestigationTask; locate_line: InvestigationTask
  explanation: { required: boolean; done: boolean }; complete: boolean
}

export interface Hint {
  id: number; level: number; source: 'llm' | 'fallback'; created_at: string
  focus: { step: number | null; signal: string | null; lines: number[] }
  message: string; question: string; concept_tags: string[]; tag?: string; code?: string
  fallback_reason?: string | null; prompt_version?: string; model?: string
}

/** 第 4 级提示“参考答案”的解锁状态（backend/app/services/answer.py） */
export interface AnswerStatus {
  available: boolean; unlocked: boolean; revealed: boolean; failed: number; fails_needed: number
  code_hint_seen: boolean; message: string
}

export interface ChatMessage {
  id: number | string; role: 'user' | 'assistant' | 'notice'; content: string
  source?: 'llm' | 'fallback' | null; flagged?: boolean; created_at?: string
}

export interface ShuffleResult {
  ok: boolean; order_sensitive: boolean | null; blocks: number; block_lines: number[][]
  variants: { order: number[]; first_diff: { step: number; signal: string; base: string; variant: string } | null;
              timeout: boolean; errors: CompileError[]; trace: TraceRow[] }[]
  message: string | null; base_trace: TraceRow[]
}

export interface AttemptDetail extends AttemptSummary {
  problem_id: string; code: string; finished_at: string | null
  judge: Judge | null; expected: TraceRow[] | null; evaluation: Evaluation | null
  predictions: { id: number; kind: string; answers: any; accuracy: number | null }[]
  confidence: number | null; confident_miss: boolean; under_confident: boolean
  misconceptions: { code: string; label: string }[]
  investigation: InvestigationStatus | null
  hints: Hint[]
  shuffle: { id: number; status: string; prediction: string | null; result: ShuffleResult | null } | null
  previous: { id: number; attempt_no: number; trace: TraceRow[] } | null
}

export interface MasteryItem { code: string; name: string; level: Level; r_code: number | null;
  r_pred: number | null; f_value: number | null; attempts: number }

export interface HomeData {
  user: { display_name: string }
  assignments: { id: number; title: string; open_at: string; due_at: string; done: number; total: number;
                 problems: { id: string; title: string; status: string }[] }[]
  continue: { problem_id: string; title: string; step: Step } | null
  review_due: number; review_remaining_today: number
  mastery: MasteryItem[]
  last_feedback: { problem_id: string; title: string; attempt_id: number; sim_ok: boolean | null;
                   quadrant: Quadrant | null; tags: string[]; created_at: string } | null
}

export interface ProblemListItem {
  id: string; title: string; primm_type: PrimmType; primm_label: string; difficulty: number
  knowledge_points: KP[]; status: 'not_started' | 'in_progress' | 'passed' | 'mastered'; due_at: string | null; stage?: string
}

export interface ReportData {
  kpis: { mastered: number; fragile: number; total_kps: number; waveform_accuracy: number | null
          waveform_accuracy_delta: number | null
          tb: { problem_id: string; title: string; score: number | null; caught: number; total: number } | null }
  mastery: MasteryItem[]
  calibration: { overconfidence: number | null; bias: number | null; n: number
                 confident_misses: { attempt_id: number; problem_id: string; title: string; pred_accuracy: number | null; created_at: string }[] }
  trend: { week: string; waveform: number | null; hardware: number | null }[]
  fragile_list: { problem_id: string; title: string; reason: string; attempt_id: number }[]
  misconceptions: { code: string; label: string; count: number; latest_problem: string;
                    practice_problem_id: string; source: 'judge' | 'prediction' }[]
  badges: { code: string; label: string }[]
  hints: { id: number; problem_id: string; title: string; level: number; message: string; question: string; created_at: string }[]
  review_upcoming: { id: number; title: string; box: number; due_at: string; kind: string }[]
}

export interface ReviewQuestion {
  source: string; kind: 'waveform' | 'hardware' | 'find_bug'; code: string
  predict_points: PredictPoint[]; hardware_questions: string[]; skeleton: Skeleton
  // 误区复盘（find_bug）：看代码选出它的问题
  tag?: string; task?: string; options?: { code: string; label: string }[]
}

export interface ReviewData {
  remaining_today: number
  items: { id: number; problem_id: string; title: string; knowledge_point: KP; box: number; due_at: string;
           question: ReviewQuestion }[]
  upcoming: { id: number; title: string; box: number; due_at: string; kind: string }[]
}
