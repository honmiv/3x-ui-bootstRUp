#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$ROOT_DIR"
docker compose -f working/docker-compose/docker-compose.yml --project-directory . down && \
docker compose -f working/docker-compose/docker-compose.yml --project-directory . up -d --build