#!/usr/bin/env bash
set -euo pipefail

backup_dir="${1:-./backup}"

rm -rf "$backup_dir"
mkdir -p "$backup_dir"

if [[ -d "working/3xui" ]]; then
  cp -r working/3xui "$backup_dir/3xui"
fi

if [[ -d "working/docker-compose" ]]; then
  cp -r working/docker-compose "$backup_dir/docker-compose"
fi
