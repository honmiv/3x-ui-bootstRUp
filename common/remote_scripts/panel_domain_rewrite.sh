#!/usr/bin/env bash
set -e

: "${RECOVERY_OLD_DOMAIN:?RECOVERY_OLD_DOMAIN is required}"
: "${RECOVERY_NEW_DOM:?RECOVERY_NEW_DOM is required}"
PANEL_USER="${RECOVERY_PANEL_USER:-admin}"
PANEL_PASS="${RECOVERY_PANEL_PASS:-admin}"

if [ "$RECOVERY_OLD_DOMAIN" = "$RECOVERY_NEW_DOM" ]; then
    echo "[INFO] Domain unchanged ($RECOVERY_OLD_DOMAIN); skipping 3x-ui API rewrite."
    exit 0
fi

cd /opt/3x-ui-bootstRUp
CADDY_FILE="working/caddy/Caddyfile"
if [ ! -f "$CADDY_FILE" ]; then
    echo "[ERROR] Caddyfile not found in recovered backup."
    exit 1
fi

WEB_BASE=$(grep -oE '@web_base_path path /[A-Za-z0-9_-]+' "$CADDY_FILE" | head -n 1 | awk '{print $3}' | tr -d '/' || true)
SUB_PATH=$(grep -oE '@sub_path path /[A-Za-z0-9_-]+' "$CADDY_FILE" | head -n 1 | awk '{print $3}' | tr -d '/' || true)
WEB_PORT=$(grep -oE 'reverse_proxy @web_base_path 3xui:[0-9]+' "$CADDY_FILE" | head -n 1 | sed 's/.*://' || true)

if [ -z "$WEB_PORT" ]; then
    echo "[ERROR] Could not determine 3x-ui web port from Caddyfile."
    exit 1
fi
echo "[INFO] Panel internal web port: ${WEB_PORT} (base path: /${WEB_BASE}/)"

COOKIE=/tmp/recovery_xui_cookie.txt

echo "[INFO] Waiting for 3x-ui panel to become ready..."
ready=""
for i in $(seq 1 90); do
    if docker exec 3xui sh -c "curl -s -o /dev/null http://127.0.0.1:${WEB_PORT}/" 2>/dev/null; then
        ready="1"
        break
    fi
    sleep 2
done
if [ -z "$ready" ]; then
    echo "[ERROR] 3x-ui panel did not become ready within 180s."
    exit 1
fi

docker exec 3xui sh -c "rm -f $COOKIE"

API_PREFIX=""
LOGIN_HTML=""
for prefix in "/${WEB_BASE}" ""; do
    LOGIN_HTML=$(docker exec 3xui sh -c "curl -fsS -c $COOKIE http://127.0.0.1:${WEB_PORT}${prefix}/" 2>/dev/null || true)
    if [ -n "$LOGIN_HTML" ]; then
        API_PREFIX="$prefix"
        break
    fi
done
if [ -z "$API_PREFIX" ]; then
    echo "[ERROR] Could not reach the 3x-ui login page inside the container."
    exit 1
fi
API_BASE="http://127.0.0.1:${WEB_PORT}${API_PREFIX}"
echo "[INFO] Reached panel at ${API_BASE}"

CSRF=$(printf '%s' "$LOGIN_HTML" | grep -oP 'csrf-token"\s+content="\K[^"]+' | head -n 1 || true)
if [ -z "$CSRF" ]; then
    echo "[ERROR] Could not obtain CSRF token from the login page."
    exit 1
fi

ENC_U=$(jq -rn --arg v "$PANEL_USER" '$v | @uri')
ENC_P=$(jq -rn --arg v "$PANEL_PASS" '$v | @uri')

docker exec 3xui sh -c "curl -fsS -b $COOKIE -c $COOKIE -H 'content-type: application/x-www-form-urlencoded; charset=UTF-8' -H 'x-csrf-token: $CSRF' --data 'username=${ENC_U}&password=${ENC_P}' ${API_BASE}/login" >/dev/null 2>&1 || true

PANEL_HTML=$(docker exec 3xui sh -c "curl -fsS -b $COOKIE -c $COOKIE ${API_BASE}/panel/" 2>/dev/null || true)
CSRF=$(printf '%s' "$PANEL_HTML" | grep -oP 'csrf-token"\s+content="\K[^"]+' | head -n 1 || true)
if [ -z "$CSRF" ]; then
    echo "[ERROR] 3x-ui panel login failed. Provide the panel admin credentials from the original deployment (default: admin/admin)."
    exit 1
fi
echo "[INFO] Authenticated to the 3x-ui panel."

# --- Update subURI (subscription base URL) ---
if [ -n "$SUB_PATH" ]; then
    echo "[INFO] Updating panel subURI -> https://${RECOVERY_NEW_DOM}/${SUB_PATH}/"
    SETTINGS=$(docker exec 3xui sh -c "curl -fsS -X POST -b $COOKIE -c $COOKIE -H 'accept: application/json' -H 'x-csrf-token: $CSRF' ${API_BASE}/panel/api/setting/all")
    SETTINGS_PAYLOAD=$(printf '%s' "$SETTINGS" | jq -r --arg uri "https://${RECOVERY_NEW_DOM}/${SUB_PATH}/" '.obj | .subURI = $uri | to_entries | map("\(.key)=\(.value | tostring | @uri)") | join("&")')
    printf '%s' "$SETTINGS_PAYLOAD" | docker exec -i 3xui sh -c 'cat > /tmp/recovery_setting_payload.txt'
    UPDATE_RESP=$(docker exec 3xui sh -c "curl -fsS -b $COOKIE -c $COOKIE -H 'content-type: application/x-www-form-urlencoded; charset=UTF-8' -H 'x-csrf-token: $CSRF' --data @/tmp/recovery_setting_payload.txt ${API_BASE}/panel/api/setting/update" 2>/dev/null || true)
    if printf '%s' "$UPDATE_RESP" | grep -q '"success":true'; then
        echo "[INFO] Panel settings updated (subURI)."
    else
        echo "[WARN] Panel settings update response: $UPDATE_RESP"
    fi
fi

# --- Rewrite domain in all inbounds (serverName / client add / externalProxy) ---
INBOUNDS=$(docker exec 3xui sh -c "curl -fsS -b $COOKIE -c $COOKIE -H 'accept: application/json' -H 'x-csrf-token: $CSRF' ${API_BASE}/panel/api/inbounds/list" 2>/dev/null || true)
INBOUND_COUNT=$(printf '%s' "$INBOUNDS" | jq -r '.obj | length' 2>/dev/null || echo 0)
if [ -n "$INBOUND_COUNT" ] && [ "$INBOUND_COUNT" -gt 0 ] 2>/dev/null; then
    echo "[INFO] Rewriting domain in ${INBOUND_COUNT} inbound(s)."
    i=0
    while [ "$i" -lt "$INBOUND_COUNT" ]; do
        OBJ=$(printf '%s' "$INBOUNDS" | jq -c --arg old "$RECOVERY_OLD_DOMAIN" --arg new "$RECOVERY_NEW_DOM" '.obj['"$i"'] | (def rec: if type == "object" then with_entries(.value |= rec) elif type == "array" then map(rec) elif type == "string" then (split($old) | join($new)) else . end; rec)')
        ID=$(printf '%s' "$OBJ" | jq -r '.id // empty')
        if [ -z "$ID" ]; then
            echo "[WARN] Inbound #$i has no id; skipped."
            i=$((i+1))
            continue
        fi
        PAYLOAD=$(printf '%s' "$OBJ" | jq -r 'to_entries | map("\(.key)=\(if (.value | type) == "object" or (.value | type) == "array" then (.value | tojson | @uri) else (.value | tostring | @uri) end)") | join("&")')
        printf '%s' "$PAYLOAD" | docker exec -i 3xui sh -c 'cat > /tmp/recovery_inbound_payload.txt'
        UPD_RESP=$(docker exec 3xui sh -c "curl -fsS -b $COOKIE -c $COOKIE -H 'content-type: application/x-www-form-urlencoded; charset=UTF-8' -H 'x-csrf-token: $CSRF' --data @/tmp/recovery_inbound_payload.txt ${API_BASE}/panel/api/inbounds/update/$ID" 2>/dev/null || true)
        if printf '%s' "$UPD_RESP" | grep -q '"success":true'; then
            echo "[INFO] Inbound $ID updated (serverName / client add / externalProxy)."
        else
            echo "[WARN] Inbound $ID update response: $UPD_RESP"
        fi
        i=$((i+1))
    done
else
    echo "[WARN] No inbounds found via API to update."
fi

# --- Restart Xray so the new config takes effect ---
echo "[INFO] Restarting Xray to apply the new domain..."
XRAY_OK=""
for XRAY_API in "panel/api/xray" "panel/xray"; do
    XR_RESP=$(docker exec 3xui sh -c "curl -fsS -X POST -b $COOKIE -c $COOKIE -H 'x-csrf-token: $CSRF' ${API_BASE}/${XRAY_API}/" 2>/dev/null || true)
    if printf '%s' "$XR_RESP" | grep -q '"success":true'; then
        XRAY_OK="1"
        break
    fi
done
if [ -n "$XRAY_OK" ]; then
    echo "[INFO] Xray restarted successfully."
else
    echo "[WARN] Could not restart Xray via API; a manual restart in the panel may be required."
fi

echo "[OK] Domain rewrite completed: $RECOVERY_OLD_DOMAIN -> $RECOVERY_NEW_DOM"
