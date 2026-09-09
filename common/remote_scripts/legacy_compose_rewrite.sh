if [ -f "$COMPOSE_FILE" ] && grep -qE 'context:[[:space:]]+\./templates' "$COMPOSE_FILE" 2>/dev/null; then
  echo "[INFO] Legacy caddy build context found in compose; using image ghcr.io/honmiv/caddy-l4:latest..."
  awk '
    /^[[:space:]]*caddy:[[:space:]]*$/ { print; print "    image: ghcr.io/honmiv/caddy-l4:latest"; next }
    /^[[:space:]]*build:[[:space:]]*$/ || /^[[:space:]]*context:[[:space:]]*\.\/templates/ || /^[[:space:]]*dockerfile:[[:space:]]*Dockerfile-caddy-l4/ { next }
    { print }
  ' "$COMPOSE_FILE" > "$COMPOSE_FILE.tmp" && mv "$COMPOSE_FILE.tmp" "$COMPOSE_FILE"
fi
