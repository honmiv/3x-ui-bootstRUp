#!/usr/bin/env bash
set -euo pipefail

backup_dir="./backup"
working_dir="./working"

if [[ ! -d "$backup_dir" ]]; then
  echo "Error: Backup directory '$backup_dir' does not exist." >&2
  exit 1
fi

cp -r "$backup_dir"/. "$working_dir"/

compose_file="$working_dir/docker-compose/docker-compose.yml"
if [[ -f "$compose_file" ]]; then
  docker compose -f "$compose_file" --project-directory . up -d
else
  echo "Warning: docker-compose.yml not found at $compose_file. Service was not restarted." >&2
fi

echo "Rollback completed successfully."