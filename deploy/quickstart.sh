#!/usr/bin/env bash
# 一键部署，适合先看效果：生成 .env → 构建并启动 → 第一次运行时导入演示数据并打印账号。
#   deploy/quickstart.sh
# 需要：Docker（含 compose 插件）。再次运行只会按最新代码重新构建、重启，不会重复导入数据。
set -euo pipefail
cd "$(dirname "$0")/.."

command -v docker >/dev/null 2>&1 || { echo "没有找到 docker，请先安装 Docker" >&2; exit 1; }
docker compose version >/dev/null 2>&1 || { echo "没有找到 docker compose，请安装 Docker 的 compose 插件" >&2; exit 1; }
rand() { od -An -N16 -tx1 /dev/urandom | tr -d ' \n'; }

if [ ! -f .env ]; then
  cp .env.example .env
  sed -i.bak -e "s/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$(rand)/" -e "s/^ANON_SALT=.*/ANON_SALT=$(rand)/" .env
  rm -f .env.bak
  echo "已生成 .env（数据库密码和匿名盐是随机生成的）"
fi
port="$(sed -n 's/^WEB_PORT=//p' .env)"; port="${port:-8080}"

echo "构建并启动（第一次需要下载和编译，大约 5–15 分钟）……"
docker compose up -d --build

echo "等待服务就绪……"
for _ in $(seq 1 120); do
  curl -fsS "http://localhost:$port/api/health" >/dev/null 2>&1 && break
  sleep 2
done
curl -fsS "http://localhost:$port/api/health" >/dev/null || {
  echo "服务没有起来，查看日志：docker compose logs api" >&2; exit 1; }

users="$(docker compose exec -T db sh -c 'psql -qtA -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT count(*) FROM users"')"
if [ "$users" = "0" ]; then
  pass="${DEMO_PASSWORD:-demo-$(rand | cut -c1-8)}"
  echo "导入演示数据（大约 1–2 分钟）……"
  docker compose exec -T -e DEMO_PASSWORD="$pass" api python -m backend.scripts.seed_demo --students 5 >/dev/null
  docker compose exec -T api python -m backend.scripts.gen_test_data --teacher-login TGEN --teacher-password "$pass" >/dev/null
  cat <<MSG

演示账号（密码都是 $pass，只显示这一次）：
  学生    S2026001 – S2026005     做题
  教师    T001                    上面 5 名学生所在的班
  教师    TGEN                    60 名虚拟学生、8 周做题数据，教师端各页面都有内容
MSG
fi

grep -q '^DEEPSEEK_API_KEY=.\+' .env || echo "
提示：.env 里没有填 DEEPSEEK_API_KEY，提示用规则生成、助教对话不可用。填好后运行 docker compose up -d 即可生效。"
echo "
打开 http://localhost:$port （其他电脑访问时把 localhost 换成这台机器的 IP）"
