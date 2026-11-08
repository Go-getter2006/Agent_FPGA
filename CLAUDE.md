# Verilog 个性化辅导智能体（研究原型）

面向数字电路 / FPGA 实验课的 Verilog 学习平台，服务于 AI+教育方向的论文研究。核心想法：
- 正误只由工具判定（iverilog / yosys / verilator）；大模型只负责把诊断翻译成提示和对话
- 训练学生把“代码 ↔ 仿真波形 ↔ 综合出的硬件”对应起来：先预测自己代码的行为，再仿真对照
- 学习流程按 PRIMM 组织：预测 → 运行 → 探究 → 修改 → 创作
- 学生端帮学生学；教师端看全班学情、做研究分析。两端追踪和展示的内容不同
- 本系统的学情数据和知识点体系与 C 语言系统完全分开，只可复用代码框架

## 文档索引（开始每个阶段前，先读对应文档）
| 文档 | 内容 | 阶段 |
|---|---|---|
| docs/judge.md | 仿真裁判：题目目录、诊断流程、JSON 格式、标签、扩展功能 | 1、2 |
| docs/pages.md | 学生端、教师端的页面与交互流程 | 3、5 |
| docs/ui-design.md | UI 设计规范：参考页面、颜色、字号、间距、组件、波形组件 | 3、5 |
| docs/ui-prototype.html | 静态视觉原型：做页面时对照它的布局和配色 | 3、5 |
| docs/learner-model.md | 学情指标定义、两端各自追踪的内容、事件日志、分组、隐私 | 3、4、5 |
| docs/llm-deepseek.md | DeepSeek 接入方式、提示词、输出校验、容错、成本、评测 | 4 |
| docs/data-api.md | 数据表、任务队列、REST 接口、权限、导出格式 | 3–6 |

## 全局硬性规则
1. 判对错、算学情指标只用工具和确定性代码；大模型的输出不能作为任何学情指标的依据。
2. 面向学生的大模型输出不能包含正确代码；校验规则见 docs/llm-deepseek.md 5.3 节，不通过就降级为规则提示。
3. 每个关键操作写一条事件日志（docs/learner-model.md 第 7 节）；事件只追加，不修改、不删除。
4. API Key、匿名盐等密钥只从环境变量读取，不进仓库；`.env.example` 只写变量名和默认值。
5. 研究导出只含已同意的学生，一律用匿名 ID。
6. 未经我同意，不修改 `problems/` 下的参考答案和 testbench，不改裁判输出 JSON 的字段名，不改已发布的提示词版本文件。
7. 遇到设计取舍，先用两三句话说明方案，等我确认后再写；不要自行扩大范围或提前做后面阶段的内容。

## 技术栈
- 裁判：Python 3.10+ 标准库 + PyYAML + iverilog / yosys / verilator
- 后端：Python + FastAPI + SQLAlchemy 2 + Alembic；开发用 SQLite，部署用 PostgreSQL
- 任务队列：jobs 表 + worker 进程池；不引入 Redis 等新组件，除非我同意
- 前端：React + TypeScript + Vite；组件库 Ant Design（中文语言包）；图表 ECharts；代码编辑器 Monaco Editor；数据请求 TanStack Query；波形组件自研（SVG）
- 大模型：DeepSeek API（OpenAI 兼容），模型名用环境变量配置，默认 `deepseek-flash`
- 测试：后端 pytest；前端 Vitest；关键流程用 Playwright 做端到端测试和截图检查
- 云端会话的 setup script：`apt-get update && apt-get install -y iverilog yosys verilator`，Node 和 Python 依赖按各自的锁文件安装

## 目录结构
```text
judge/                 仿真裁判（Python 包，可命令行，也可被后端导入）
problems/<题目ID>/      题目（problem.yaml、spec.md、ref.v、tb.v、starter.v、cases/）
backend/
  app/api/             路由（student、teacher、auth、jobs）
  app/models/          数据表
  app/services/        judge_runner、learner_model、review_scheduler、llm、hint_guard、fallback_hints、exports
  app/data/            knowledge_points.yaml
  prompts/             提示词文件（带版本号）
  eval/                提示质量评测脚本
  worker.py            任务进程
  tests/
frontend/
  src/pages/student/   S1–S6
  src/pages/teacher/   T1–T8
  src/components/      WaveformView、CodeEditor、StepBar、HintLadder、QuadrantBadge……
  src/theme/           设计变量（与 docs/ui-design.md 第 3 节一致）
docs/
logs/                  运行日志（.gitignore）
```

## 开发阶段与验收
每个阶段结束时：测试全部通过，并用三五句话向我汇报做了什么、还有什么没做、有哪些需要我决定的问题。

### 阶段 1：仿真裁判核心
按 docs/judge.md 第 1–8 节。先做 1 道题跑通，把输出 JSON 给我确认，再扩到 5 道。

### 阶段 2：裁判扩展
信号→代码行映射、顺序打乱实验、testbench 打分，按 docs/judge.md 第 9 节。9.1 和 9.2 都有“先试验、再汇报”的要求。

### 阶段 3：后端 + 学生端 MVP
- 账号与班级、题目同步、做题工作台的五步流程、预测输入、提交仿真、结果对照、探究检查、规则提示（先不接大模型）、我的学情、复习
- 验收：一名学生能从登录走完一道创作题的全部步骤；每一步都有事件日志；学情指标与手算一致（为 docs/learner-model.md 第 4 节每个公式各写一个单元测试）；Playwright 端到端测试通过，三个关键页面的截图与 docs/ui-prototype.html 的布局一致

### 阶段 4：接入 DeepSeek
- llm 封装、分级提示、对话（SSE）、输出校验、容错与熔断、预算控制、调用日志、提示质量评测脚本
- 验收：断网或 Key 无效时，学生端仍能正常做题并拿到规则提示；评测脚本能对全部错误样本生成 CSV；校验器对一组“故意泄露代码”的样例全部拦截

### 阶段 5：教师端
- T1–T8 全部页面、分组与功能开关、导出、ICAP 编码与人工抽检
- 验收：用脚本生成 2 个分组、各 30 名虚拟学生、每人 20 次尝试的测试数据，教师端各页面数据与 SQL 直接统计一致；越权访问测试全部被拒绝

### 阶段 6：试点准备
- 部署配置（Docker Compose：后端、worker、前端静态文件、PostgreSQL）、数据库备份脚本、并发测试（60 名学生同时提交）、知情同意文本定稿
- 验收：60 个并发提交在 2 分钟内全部判完；备份可以恢复

## 工作方式
- 每完成一步先跑测试，再提交；提交说明用中文
- 代码标识符用英文；注释、文档、界面文案用中文
- 新增依赖要先说明理由
- 写前端页面时，同时打开 docs/ui-design.md 和 docs/ui-prototype.html 对照
