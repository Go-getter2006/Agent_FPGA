# Verilog 个性化辅导智能体（研究原型）

设计与开发规则见 [CLAUDE.md](CLAUDE.md)，各部分说明见 `docs/`。

## 本地运行
需要：Python 3.10+、Node 20+、iverilog、yosys、verilator。

```bash
# 依赖
sudo apt-get install -y iverilog yosys verilator
pip install -r backend/requirements.txt
(cd frontend && npm ci)

# 演示数据（1 名教师、1 个班、若干学生、1 份作业）
DEMO_PASSWORD=换成你的密码 python -m backend.scripts.seed_demo --students 5

# 三个进程
python -m uvicorn backend.app.main:app --port 8000   # 接口
python -m backend.worker                              # 判题任务
(cd frontend && npx vite)                             # 前端 http://localhost:5173
```
环境变量见 `.env.example`（只写变量名和默认值）。

## 测试
```bash
python -m pytest                       # 裁判 + 后端
(cd frontend && npx vitest run)        # 前端单元测试
(cd frontend && npx playwright test --trace off)   # 端到端（自动启动全新的后端和前端）
```

## 裁判命令行
```bash
python -m judge 学生代码.v seq_detector_101            # 诊断
python -m judge 学生代码.v swap_regs --shuffle         # 顺序打乱实验
python -m judge 学生tb.v seq_detector_101 --testbench  # testbench 打分
```
