#!/usr/bin/env bash
set -euo pipefail

backup_dir="${1:-./backup}"

rm -rf "$backup_dir"
mkdir -p "$backup_dir"

if [[ -d "working/3x-ui" ]]; then
  cp -r working/3x-ui "$backup_dir/3x-ui"
fi

if [[ -d "working/3xui" ]]; then
  cp -r working/3xui "$backup_dir/3xui"
fi

if [[ -d "working/docker-compose" ]]; then
  cp -r working/docker-compose "$backup_dir/docker-compose"
fi

if [[ -d "working/nginx-decoy" ]]; then
  cp -r working/nginx-decoy "$backup_dir/nginx-decoy"
fi

if [[ -d "working/caddy" ]]; then
  cp -r working/caddy "$backup_dir/caddy"
fi
