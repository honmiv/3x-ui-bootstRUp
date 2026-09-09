if [ -f "$COMPOSE_FILE" ] && grep -qE 'context:[[:space:]]+\./templates' "$COMPOSE_FILE" 2>/dev/null \
   && [ -d panel/templates ] && [ ! -e templates ]; then
  ln -s panel/templates templates
fi
