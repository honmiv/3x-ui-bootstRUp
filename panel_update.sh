#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 || -z "$1" ]]; then
  echo "Usage: $0 <version>" >&2
  exit 1
fi

version="$1"
compose_file="working/docker-compose/docker-compose.yml"

if [[ ! -f "$compose_file" ]]; then
  echo "File not found: $compose_file" >&2
  exit 1
fi

./panel_backup.sh

tmp_file=$(mktemp)
trap 'rm -f "$tmp_file"' EXIT

awk -v ver="$version" '
  function get_indent(line) {
    if (match(line, /^[[:space:]]*/))
      return RLENGTH
    return 0
  }

  /^[[:space:]]*3xui:[[:space:]]*$/ {
    in_3xui = 1
    indent = get_indent($0)
    print
    next
  }

  in_3xui && /^[[:space:]]*[^[:space:]]/ {
    if (get_indent($0) <= indent) {
      in_3xui = 0
    }
  }

  in_3xui && /^[[:space:]]*image:[[:space:]]*/ {
    sub(/ghcr\.io\/mhsanaei\/3x-ui:[^"\047 ]*/, "ghcr.io/mhsanaei/3x-ui:" ver)
  }

  { print }
' "$compose_file" > "$tmp_file"

mv "$tmp_file" "$compose_file"

docker compose -f "$compose_file" --project-directory . up -d 3xui