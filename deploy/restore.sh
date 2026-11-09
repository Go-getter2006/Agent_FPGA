#!/usr/bin/env bash
# 从备份恢复数据库，会覆盖当前数据。恢复期间暂停后端和判题进程，结束后自动启动。
#   deploy/restore.sh backups/db-20261109-023000.dump
#   YES=1 deploy/restore.sh <备份文件>       # 不再询问（脚本里用）
set -euo pipefail
file="${1:?用法：deploy/restore.sh <备份文件>}"
[ -f "$file" ] || { echo "找不到备份文件：$file" >&2; exit 1; }
file="$(cd "$(dirname "$file")" && pwd)/$(basename "$file")"
cd "$(dirname "$0")/.."

if [ "${YES:-}" != "1" ]; then
  read -r -p "将用 $file 覆盖当前数据库。继续？[y/N] " answer
  case "$answer" in y|Y) ;; *) echo "已取消"; exit 1 ;; esac
fi

running="$(docker compose ps --services --status running | grep -Ex 'api|worker' || true)"
[ -n "$running" ] && docker compose stop $running
docker compose exec -T db sh -c \
  'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner --single-transaction' < "$file"
[ -n "$running" ] && docker compose start $running
echo "恢复完成：$file"
