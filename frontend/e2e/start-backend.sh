#!/usr/bin/env bash
# 给端到端测试启动后端：全新数据库、演示数据、worker 进程、API 服务
set -euo pipefail
cd "$(dirname "$0")/../.."
E2E_DIR="${E2E_DIR:-/tmp/agent_fpga_e2e}"
rm -rf "$E2E_DIR" && mkdir -p "$E2E_DIR"
export DATABASE_URL="sqlite:///$E2E_DIR/e2e.db"
export ANON_SALT="e2e-salt"
export JUDGE_LOG_PATH="$E2E_DIR/judge.jsonl"
export DEMO_PASSWORD="${DEMO_PASSWORD:-e2e-pass-123}"
export HINT_INTERVAL_SECONDS=1
python3 -m backend.scripts.seed_demo --students 6
# 教师端：2 组 × 30 名虚拟学生 × 20 次尝试
python3 -m backend.scripts.gen_test_data --teacher-login TGEN --teacher-password "$DEMO_PASSWORD"
python3 -m backend.worker --workers 2 > "$E2E_DIR/worker.log" 2>&1 &
WORKER=$!
trap 'kill $WORKER 2>/dev/null || true' EXIT
python3 -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
