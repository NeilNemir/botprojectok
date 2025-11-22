#!/usr/bin/env bash
set -euo pipefail

SERVICE=bot
DBSERVICE=db
COMPOSE_FILE=docker-compose.yml

echo "[update] Stopping containers..."
docker compose -f "$COMPOSE_FILE" down --remove-orphans || true

echo "[update] Building images (no cache)..."
docker compose -f "$COMPOSE_FILE" build --no-cache --pull

echo "[update] Starting database..."
docker compose -f "$COMPOSE_FILE" up -d "$DBSERVICE"

echo "[update] Waiting 25s for DB warm-up..."
sleep 25

echo "[update] Starting bot..."
docker compose -f "$COMPOSE_FILE" up -d "$SERVICE"

echo "[update] Showing status:"
docker compose -f "$COMPOSE_FILE" ps

echo "[update] Recent logs (bot):"
docker compose -f "$COMPOSE_FILE" logs --tail=60 "$SERVICE" || true

echo "[update] Done."
