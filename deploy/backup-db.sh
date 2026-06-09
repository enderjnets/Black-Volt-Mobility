#!/usr/bin/env bash
# Daily Postgres backup for Black Volt Mobility (custom-format dump), with retention.
# Install on the VPS via cron (see deploy/vps-deploy.md):
#   crontab -e →  30 4 * * *  /home/enderj/Black-Volt-Mobility/deploy/backup-db.sh >> /home/enderj/blackvolt-backup.log 2>&1
set -euo pipefail

CONTAINER="${BV_DB_CONTAINER:-blackvolt-db}"
DB_USER="${POSTGRES_USER:-blackvolt}"
DB_NAME="${POSTGRES_DB:-blackvolt}"
OUT_DIR="${BV_BACKUP_DIR:-$HOME/blackvolt-backups}"
KEEP="${BV_BACKUP_KEEP:-14}"

mkdir -p "$OUT_DIR"
STAMP="$(date +%Y%m%d-%H%M%S)"
OUT="$OUT_DIR/blackvolt-$STAMP.dump"

# Custom-format dump (compressed, restorable with pg_restore).
docker exec "$CONTAINER" pg_dump -U "$DB_USER" -Fc "$DB_NAME" > "$OUT"
echo "$(date -Is) wrote $OUT ($(du -h "$OUT" | cut -f1))"

# Retention: keep the newest $KEEP dumps, delete older.
ls -1t "$OUT_DIR"/blackvolt-*.dump 2>/dev/null | tail -n +$((KEEP + 1)) | xargs -r rm -f
echo "$(date -Is) retention: kept newest $KEEP in $OUT_DIR"
