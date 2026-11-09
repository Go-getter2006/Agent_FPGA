#!/usr/bin/env bash
# 备份数据库：pg_dump 自定义格式（压缩、可单表恢复），存到 backups/ 下，并自动删除超过 KEEP_DAYS 天的旧备份。
#   deploy/backup.sh                    # 在仓库根目录或任意目录运行都可以
#   BACKUP_DIR=/mnt/nas/agent KEEP_DAYS=60 deploy/backup.sh
# 建议用 cron 每天跑一次，例如：  30 2 * * *  /opt/agent_fpga/deploy/backup.sh >> /var/log/agent_backup.log 2>&1
# 只备份数据库：判题日志和研究导出都能从数据库重新生成。
set -euo pipefail
cd "$(dirname "$0")/.."
BACKUP_DIR="${BACKUP_DIR:-backups}"
KEEP_DAYS="${KEEP_DAYS:-30}"
mkdir -p "$BACKUP_DIR"
file="$BACKUP_DIR/db-$(date +%Y%m%d-%H%M%S).dump"

docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$file.part"
# 自检：能读出目录说明备份文件完整，再改成正式文件名
docker compose exec -T db pg_restore --list < "$file.part" > /dev/null
mv "$file.part" "$file"
find "$BACKUP_DIR" -name 'db-*.dump' -mtime +"$KEEP_DAYS" -delete
echo "备份完成：$file（$(du -h "$file" | cut -f1)）"
