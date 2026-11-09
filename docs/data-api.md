# 数据模型与接口

后端：FastAPI + SQLAlchemy 2 + Alembic。开发用 SQLite，部署用 PostgreSQL；JSON 字段在 SQLite 里用 TEXT 存，在 PostgreSQL 里用 JSONB，统一通过 SQLAlchemy 的 JSON 类型访问。所有时间存 UTC，接口返回 ISO 8601 并带时区。

## 1. 数据表
| 表 | 主要字段 | 说明 |
|---|---|---|
| users | id, role(student/teacher/admin), login_name, display_name, password_hash, anon_id, created_at | login_name 为学号或工号；密码用 argon2 或 bcrypt |
| classes | id, name, term, teacher_id | |
| enrollments | class_id, user_id, group(treatment/control/none), consent_status, consent_version, consent_at | 一个学生在一个班只有一条 |
| feature_flags | class_id, group, flags(JSON) | 各分组的功能开关，见 docs/learner-model.md 第 8 节 |
| knowledge_points | code, name, description, sort_order | 从 knowledge_points.yaml 同步 |
| problems | id, title, knowledge_points(JSON), primm_type, difficulty, meta(JSON), synced_at | 从 problems/*/problem.yaml 同步，界面只读 |
| assignments | id, class_id, group_scope, problem_ids(JSON), open_at, due_at | |
| attempts | id, user_id, problem_id, step, code, code_hash, created_at, status(queued/running/done/error), judge(JSON), sim_ok, pred_accuracy, quadrant | judge 存裁判完整输出 |
| predictions | id, user_id, problem_id, attempt_id, kind(waveform/hardware), answers(JSON), accuracy, locked_at | 先建预测（attempt_id 为空），提交仿真时关联 |
| investigations | id, attempt_id, kind(locate_step/locate_line), chosen, correct, created_at | |
| explanations | id, attempt_id, text, created_at | 探究步骤的一句话解释 |
| hints | id, attempt_id, level, source(llm/fallback), content(JSON), llm_call_id, created_at | |
| chat_sessions / chat_messages | id, user_id, problem_id / id, session_id, role, content, llm_call_id, flagged, created_at | flagged 表示触发了泄露代码拦截 |
| shuffle_runs | id, attempt_id, result(JSON), created_at | |
| tb_submissions | id, user_id, problem_id, code, result(JSON), score, created_at | |
| review_items | id, user_id, knowledge_point, problem_id, box(1–4), due_at, last_result | 提取练习队列 |
| mastery_snapshots | id, user_id, knowledge_point, level, r_code, r_pred, f_value, computed_at | 每次判完重算后追加 |
| events | id, ts, anon_id, user_id, class_id, group, type, problem_id, attempt_id, payload(JSON), app_version | 只追加；按 (class_id, ts)、(user_id, ts) 建索引 |
| llm_calls | id, ts, purpose, prompt_version, model, request_hash, messages(JSON), output, tokens(JSON), latency_ms, status, validation, retries | 见 docs/llm-deepseek.md 第 9 节 |
| jobs | id, type(judge/shuffle/tb/export/icap), status, payload(JSON), result(JSON), error, created_at, started_at, finished_at | 任务队列 |
| analysis_labels | id, target_type, target_id, scheme(ICAP), label, rationale, model, prompt_version, human_label, human_labeler_id | |
| teacher_notes | id, teacher_id, student_id, text, created_at | |

## 2. 任务队列
- 判题、顺序打乱实验、testbench 打分、导出、ICAP 编码都走 jobs 表，由独立的 worker 进程取任务执行
- worker 用进程池，并发数取环境变量 `JUDGE_WORKERS`（默认 CPU 核数减 1）
- 每个学生同时最多 1 个运行中的判题任务；10 分钟内最多提交 20 次，超出返回中文提示
- 任务状态通过轮询（`GET /api/jobs/{id}`）或 SSE（`GET /api/jobs/{id}/stream`）获取；前端先实现轮询，间隔 1 秒

## 3. 接口（前缀 `/api`）
错误统一返回：`{"error": {"code": "RATE_LIMITED", "message": "提交太频繁了，稍等一会儿再试"}}`

### 3.1 认证
| 方法 | 路径 | 说明 |
|---|---|---|
| POST | /auth/login | 学号 / 工号 + 密码，写 httpOnly Cookie |
| POST | /auth/logout | |
| GET | /auth/me | 当前用户、角色、所在班级、分组、功能开关 |
| POST | /auth/consent | 同意或拒绝，带协议版本 |

### 3.2 学生端
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /student/home | 今日任务、待复习条数、掌握图摘要、最近反馈 |
| GET | /student/problems | 题目列表，支持按作业、知识点、状态筛选 |
| GET | /student/problems/{pid} | 题目说明、起始代码、预测点、硬件问题、当前步骤与历史尝试摘要 |
| POST | /student/problems/{pid}/predictions | 锁定预测，返回 prediction_id |
| POST | /student/problems/{pid}/attempts | 提交代码（带 prediction_id），返回 attempt_id 和 job_id |
| GET | /student/attempts/{aid} | 状态、裁判结果、预测对照、象限 |
| POST | /student/attempts/{aid}/investigations | 提交定位（step 或 line），返回是否正确 |
| POST | /student/attempts/{aid}/explanations | 提交一句话解释 |
| POST | /student/attempts/{aid}/hints | 请求下一级提示，返回提示内容与来源 |
| POST | /student/problems/{pid}/chat | 发送对话消息，SSE 流式返回 |
| POST | /student/attempts/{aid}/shuffle | 发起顺序打乱实验，返回 job_id |
| POST | /student/problems/{pid}/testbench | 提交 testbench，返回 job_id |
| GET | /student/report | 我的学情（见 docs/learner-model.md 第 1 节学生端一列） |
| GET | /student/review | 今日待复习条目 |
| POST | /student/review/{item_id}/answer | 提交复习答案 |
| POST | /student/events | 批量上报界面事件 |

### 3.3 教师端（只能访问自己的班级）
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /teacher/classes | 我的班级 |
| POST | /teacher/classes/{cid}/roster | 导入 CSV 名单 |
| GET | /teacher/classes/{cid}/overview | KPI、趋势、误区 Top5、预警、题目速览 |
| GET | /teacher/classes/{cid}/heatmap | 学生 × 知识点掌握等级，参数：group、from、to、anonymous |
| GET | /teacher/classes/{cid}/misconceptions | 标签分布与示例 |
| GET | /teacher/classes/{cid}/problems/{pid}/analytics | 题目分析 |
| GET | /teacher/students/{uid} | 学生详情时间线 |
| POST | /teacher/students/{uid}/notes | 教师备注 |
| POST | /teacher/classes/{cid}/assignments | 新建作业 |
| PUT | /teacher/classes/{cid}/groups | 设置分组与功能开关 |
| POST | /teacher/classes/{cid}/exports | 发起导出任务（events / attempts / metrics），返回 job_id |
| GET | /teacher/exports/{job_id}/download | 下载导出文件 |
| POST | /teacher/classes/{cid}/analysis/icap | 发起 ICAP 编码任务 |
| GET | /teacher/classes/{cid}/analysis/icap/sample | 抽检样本；PUT 提交人工标注，返回 κ |

## 4. 权限
- 学生只能读写自己的数据；教师只能访问自己班级的学生；admin 管理账号和班级
- 每个接口都写权限测试（pytest），覆盖“学生访问别人的尝试”“教师访问别班学生”两类越权

## 5. 导出格式
- events.jsonl：一行一条事件，字段同 docs/learner-model.md 第 7 节，但去掉 user_id
- attempts.csv：anon_id, group, problem_id, attempt_no, created_at, sim_ok, pred_accuracy, quadrant, tags, max_hint_level_before
- metrics.csv：anon_id, group, knowledge_point, level, r_code, r_pred, f_value, B, H, tb_score
- data_dictionary.md：每个字段的含义与取值
- 只含 consent_status 为已同意的学生

## 6. 阶段 3 实现补充（与上文的差异）
- 新增表：`sessions`（登录会话，库里只存令牌哈希）、`progress`（学生在每道题上的 PRIMM 步骤与状态）
- 字段补充：`attempts.attempt_no`、`attempts.finished_at`、`attempts.error`、`attempts.analysis`（预测逐格对照与预测误区）；`predictions.result`（判完后的逐格对照）；`shuffle_runs.prediction`（实验前的预测 change / same）与 `status`；`tb_submissions.status`；`review_items.status`、`source_attempt_id`、`question`（代码、预测格；标准答案只在服务端）；`assignments.title`；`jobs.user_id`
- 新增接口：`GET /student/testbench/{id}`（testbench 打分结果，`missed_types` 只用文字说明没抓住的 bug 类型，不给代码）、`GET /api/health`
- `POST /student/problems/{pid}/predictions` 一次锁定波形预测和硬件问题两部分，返回 `prediction_ids`
- 预测题、修改题在进入修改阶段之前，`POST .../attempts` 运行的一律是起始代码
- 事件：前端只能上报 `page.view`、`step.enter`、`problem.open`、`waveform.view`、`waveform.cell_click`；其余事件由后端在对应操作里写入
- 任务：测试时设 `JOBS_INLINE=1`，任务在请求里同步执行；正常运行用 `python -m backend.worker`

## 7. 阶段 4 实现补充
- 新增表：`llm_calls`（字段同 docs/llm-deepseek.md 第 9 节，另有 `cost_cny`、`error`、`user_id`）、`chat_sessions`（每个学生每道题一个）、`chat_messages`（另有 `source`、`attempt_id`）
- `GET /student/problems/{pid}/chat`：对话历史；`POST /student/problems/{pid}/chat`：SSE，事件为 `{"delta", "source"}` 若干条，最后一条 `{"done": true, "message_id", "source", "flagged"}`；超过每小时 30 条返回 429 `CHAT_LIMIT`
- 提示接口返回的提示带 `source`（llm / fallback）、`fallback_reason`、`prompt_version`、`model`

## 8. 阶段 5 实现补充
- 新增表：`analysis_labels`（另有 `class_id`、`llm_call_id`、`sampled`、`created_at`）、`teacher_notes`
- 教师端接口另有：`GET /teacher/status`（大模型可用性与当天费用，顶栏预算提示用）、`POST /teacher/classes/{cid}/anonymity`（关闭 / 打开匿名，写事件）、`GET /teacher/classes/{cid}/heatmap/cell`（热力图格子的最近尝试）、`GET /teacher/classes/{cid}/misconceptions/{code}`（误区详情）、`GET /teacher/attempts/{aid}`（尝试详情）、`GET /teacher/problems`（题库预览）、`GET /teacher/classes/{cid}/assignments`、`GET /teacher/classes/{cid}/groups`、`GET /teacher/classes/{cid}/analysis/icap`（编码汇总与 κ）、`GET /teacher/classes/{cid}/roster`、`POST /teacher/students/{uid}/reset_password`
- 越权：教师访问其他教师的班级或学生返回 403；导出文件只有发起导出的教师能下载；admin 可以访问全部
- 名单导入：CSV 每行“学号,姓名[,分组]”；新账号生成临时密码，只在导入结果里出现一次
- 测试数据：`python -m backend.scripts.gen_test_data` 生成 2 组 × 30 名虚拟学生 × 20 次尝试（裁判结果来自对参考答案、起始代码和错误样本的真实诊断）
