#!/usr/bin/env bash
# Simple backup script for SQLite DB and credentials
set -euo pipefail
DATE=$(date +%F_%H-%M-%S)
BACKUP_DIR=${BACKUP_DIR:-/app/backups}
mkdir -p "$BACKUP_DIR"
# Files to backup (adjust if paths differ)
cp /app/data/botdata.db "$BACKUP_DIR/botdata-$DATE.db"
cp /app/credentials.json "$BACKUP_DIR/credentials-$DATE.json"
# Compress older plain DBs weekly via cron if desired
# Keep only last 30 backups
ls -1t "$BACKUP_DIR" | tail -n +31 | xargs -r -I {} rm "$BACKUP_DIR/{}"
