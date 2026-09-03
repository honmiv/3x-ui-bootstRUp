#!/usr/bin/env bash
set -uo pipefail

readonly NC='\033[0m'
readonly GREEN='\033[0;32m'
readonly CYAN='\033[0;36m'
readonly YELLOW='\033[0;33m'
readonly RED='\033[0;31m'

readonly REQUIRED_CMDS=("curl" "jq" "openssl" "ss" "qrencode" "pgrep" "base64" "md5sum" "awk" "grep" "sed")
readonly DOCKER_COMPOSE_FILE="./working/docker-compose/docker-compose.yml"
readonly PANEL_CONTAINER="3xui"
readonly PANEL_API_PORT="2053"
readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

source "$SCRIPT_DIR/../common/setup.sh"

declare -a USED_PORTS=()
declare -a XHTTP_CLIENTS=() TCP_CLIENTS=() CREATED_CLIENTS=()
declare -a RESULTS_CLIENTS=() RESULTS_SUB_URLS=() RESULTS_TCP_URLS=() RESULTS_XHTTP_URLS=()

die() {
    echo -e "${RED}[ERROR]${NC} $*" >&2
    exit 1
}

section() {
    echo -e "\n${CYAN}== $* ==${NC}"
}

info() {
    echo -e "${CYAN}[..]${NC} $*"
}

success() {
    echo -e "${GREEN}[OK]${NC} $*"
}

warn() {
    echo -e "${YELLOW}[WARN]${NC} $*"
}

compose() {
    docker compose -f "$DOCKER_COMPOSE_FILE" --project-directory . "$@"
}

panel_exec() {
    compose exec -T "$PANEL_CONTAINER" "$@"
}

url_encode() {
    jq -rn --arg v "$1" '$v|@uri'
}

is_valid_domain() {
    local domain="$1"
    [[ ${#domain} -le 253 ]] &&
        [[ "$domain" =~ ^[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?(\.[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$ ]]
}

flush_stdin() {
    [[ -t 0 ]] || return
    while IFS= read -r -s -n 1 -t 0.01 _; do
        :
    done
}

prompt_input() {
    local prompt="$1"
    local res_var="$2"
    flush_stdin
    read -r -p "$prompt" "$res_var"
}

prompt_with_default() {
    local prompt="$1"
    local default="$2"
    local res_var="$3"
    local value=""
    prompt_input "$prompt" value
    printf -v "$res_var" "%s" "${value:-$default}"
}

prompt_required() {
    local prompt="$1"
    local error_message="$2"
    local res_var="$3"
    local value=""

    while [[ -z "$value" ]]; do
        prompt_input "$prompt" value || die "Unexpected end of input (EOF)."
        [[ -z "$value" ]] && warn "$error_message"
    done

    printf -v "$res_var" "%s" "$value"
}

prompt_choice() {
    local prompt="$1"
    local error_message="$2"
    local allowed_pattern="$3"
    local res_var="$4"
    local value=""

    while true; do
        prompt_input "$prompt" value || die "Unexpected end of input (EOF)."
        if [[ "$value" =~ $allowed_pattern ]]; then
            printf -v "$res_var" "%s" "$value"
            return
        fi
        warn "$error_message"
    done
}

read_secret() {
    local prompt="$1"
    local res_var="$2"
    local result=""
    flush_stdin
    echo -n "$prompt"
    while IFS= read -r -s -n 1 CHAR; do
        if [[ -z "$CHAR" ]]; then
            echo ""
            break
        fi
        if [[ "$(printf '%d' "'$CHAR")" -eq 127 || "$(printf '%d' "'$CHAR")" -eq 8 ]]; then
            if [[ ${#result} -gt 0 ]]; then
                printf "\b \b"
                result="${result%?}"
            fi
        else
            result+="$CHAR"
            printf "*"
        fi
    done
    printf -v "$res_var" "%s" "$result"
}

prompt_secret_with_default() {
    local prompt="$1"
    local default="$2"
    local res_var="$3"
    local value=""
    read_secret "$prompt" value
    printf -v "$res_var" "%s" "${value:-$default}"
}

is_port_busy() {
    local port="$1"
    ss -tlnp | grep -q ":$port " &>/dev/null || (true &>/dev/null </dev/tcp/127.0.0.1/"$port") 2>/dev/null
}

get_unique_random_port() {
    local port=$((RANDOM % (65535 - 49152 + 1) + 49152))
    while true; do
        local already_chosen=0
        for used in "${USED_PORTS[@]}"; do
            if [[ "$used" -eq "$port" ]]; then
                already_chosen=1
                break
            fi
        done

        if [[ "$already_chosen" -eq 1 ]] || is_port_busy "$port"; then
            ((port++))
            [[ "$port" -gt 65535 ]] && port=49152
        else
            break
        fi
    done
    USED_PORTS+=("$port")
    echo "$port"
}

sed_escape_replacement() {
    local value="$1"
    value="${value//\\/\\\\}"
    value="${value//&/\\&}"
    value="${value//|/\\|}"
    printf '%s' "$value"
}

apply_template_values() {
    local target_path="$1"
    local xui_ver domain web_base sub_path web_port sub_port caddy_port tcp_port xhttp_port
    local tcp_priv tcp_pub tcp_sids xhttp_priv xhttp_pub xhttp_sids
    xui_ver="${XUI_VERSION:-}"
    [[ -n "$xui_ver" ]] || die "XUI_VERSION is required."
    xui_ver="$(sed_escape_replacement "$xui_ver")"
    domain="$(sed_escape_replacement "${DOMAIN}")"
    web_base="$(sed_escape_replacement "${XUI_WEB_BASE_PATH}")"
    sub_path="$(sed_escape_replacement "${XUI_SUB_PATH}")"
    web_port="$(sed_escape_replacement "${XUI_WEB_PORT}")"
    sub_port="$(sed_escape_replacement "${XUI_SUB_PORT}")"
    caddy_port="$(sed_escape_replacement "${CADDY_GLOBAL_INTERNAL_PORT}")"
    tcp_port="$(sed_escape_replacement "${TCP_REALITY_INBOUND_PORT}")"
    xhttp_port="$(sed_escape_replacement "${XHTTP_REALITY_INBOUND_PORT}")"
    tcp_priv="$(sed_escape_replacement "${TCP_REALITY_PRIVATE_KEY}")"
    tcp_pub="$(sed_escape_replacement "${TCP_REALITY_PUBLIC_KEY}")"
    tcp_sids="$(sed_escape_replacement "${TCP_REALITY_SHORT_IDS_JSON_ARRAY}")"
    xhttp_priv="$(sed_escape_replacement "${XHTTP_REALITY_PRIVATE_KEY}")"
    xhttp_pub="$(sed_escape_replacement "${XHTTP_REALITY_PUBLIC_KEY}")"
    xhttp_sids="$(sed_escape_replacement "${XHTTP_REALITY_SHORT_IDS_JSON_ARRAY}")"
    sed -i \
       -e "s|{{XUI_VERSION}}|${xui_ver}|g" \
       -e "s|{{DOMAIN}}|${domain}|g" \
       -e "s|{{XUI_WEB_BASE_PATH}}|${web_base}|g" \
       -e "s|{{XUI_SUB_PATH}}|${sub_path}|g" \
       -e "s|{{XUI_WEB_PORT}}|${web_port}|g" \
       -e "s|{{XUI_SUB_PORT}}|${sub_port}|g" \
       -e "s|{{CADDY_GLOBAL_INTERNAL_PORT}}|${caddy_port}|g" \
       -e "s|{{TCP_REALITY_INBOUND_PORT}}|${tcp_port}|g" \
       -e "s|{{XHTTP_REALITY_INBOUND_PORT}}|${xhttp_port}|g" \
       -e "s|{{TCP_REALITY_PRIVATE_KEY}}|${tcp_priv}|g" \
       -e "s|{{TCP_REALITY_PUBLIC_KEY}}|${tcp_pub}|g" \
       -e "s|{{TCP_REALITY_SHORT_IDS_JSON_ARRAY}}|${tcp_sids}|g" \
       -e "s|{{XHTTP_REALITY_PRIVATE_KEY}}|${xhttp_priv}|g" \
       -e "s|{{XHTTP_REALITY_PUBLIC_KEY}}|${xhttp_pub}|g" \
       -e "s|{{XHTTP_REALITY_SHORT_IDS_JSON_ARRAY}}|${xhttp_sids}|g" \
       "$target_path"
}

generate_config() {
    local template_dir="$1"
    local target_dir="$2"
    local source_path relative_path target_relative target_path

    [[ -d "$template_dir" ]] || die "${MSG_CONFIG_ERR} $template_dir"
    mkdir -p "$target_dir"

    while IFS= read -r -d '' source_path; do
        relative_path="${source_path#"$template_dir"/}"
        target_relative="${relative_path%.template}"
        target_path="${target_dir}/${target_relative}"

        mkdir -p "$(dirname "$target_path")"
        cp "$source_path" "$target_path"

        if [[ "$source_path" == *.template ]]; then
            apply_template_values "$target_path"
        fi
    done < <(find "$template_dir" -type f -print0)

    success "$(printf "$MSG_CONFIG_SUCCESS" "$target_dir")"
}

show_spinner() {
    local counter=$1
    local spin_chars="/-\|"
    echo -ne "${spin_chars:$((counter % 4)):1}"
}

reset_working_dir() {
    info "$MSG_WORKDIR_RESET"
    # Clean up any orphaned containers to ensure a clean slate in case of crash-loops or interrupted deployments
    docker rm -f "$PANEL_CONTAINER" caddy nginx-decoy 2>/dev/null || true
    if [[ -f "$DOCKER_COMPOSE_FILE" ]]; then
        compose down 2>/dev/null || true
    fi
    rm -rf ./working && mkdir -p ./working
    success "$MSG_WORKDIR_READY"
}

load_messages() {
    MSG_DOCKER_MIRRORS="Configuring Docker registry mirror fallback"
    MSG_STEP_PREFLIGHT="Environment check"
    MSG_DEPS_INSTALLING="Installing system dependencies with %s: %s"
    MSG_DEPS_READY="System dependencies are available."
    MSG_DOCKER_INSTALLING="Docker is not installed. Installing Docker."
    MSG_DOCKER_READY="Docker is available and running."
    MSG_WORKDIR_RESET="Preparing ./working directory."
    MSG_WORKDIR_READY="Working directory is ready."
    MSG_API_START="Panel settings"
    MSG_API_FETCHING="Reading current panel settings."
    MSG_API_FETCH_ERR="Failed to read current panel settings."
    MSG_API_SENDING="Applying panel and subscription URLs."
    MSG_API_UPDATE_ERR="Failed to update panel settings via API."
    MSG_API_UPDATE_SUCCESS="Panel settings updated."
    MSG_SUB_FETCHING="Fetching client links from subscription."
    MSG_SUB_FETCH_SUCCESS="Client links fetched."
    MSG_SUB_FETCH_ERR="Failed to fetch or decode subscription data."
    MSG_SUB_EXTRACT_ERR="Failed to extract TCP or XHTTP link from subscription."
    MSG_NOT_ROOT="Run this script as root: sudo ./setup.sh"
    MSG_SUB_URL_TITLE="Subscription:"
    MSG_VLESS_TCP_URL_TITLE="VLESS TCP Reality:"
    MSG_VLESS_XHTTP_URL_TITLE="VLESS XHTTP Reality:"
    MSG_CLIENT_ERR="Failed to add client to the panel."
    MSG_APT_LOCKED="apt/dpkg is locked by another process. Waiting."
    MSG_DNF_LOCKED="dnf/rpm is locked by another process. Waiting."
    MSG_PACMAN_LOCKED="pacman is locked by db.lck. Waiting."
    MSG_DEP_ERR="Failed to install system dependencies."
    MSG_DOCKER_ERR="Failed to install Docker."
    MSG_DOCKER_START_ERR="Failed to start Docker service."
    MSG_DOCKER_RESTART_ERR="Failed to restart Docker service to apply registry mirror."
    MSG_DOCKER_COMPOSE_ERR="Docker compose plugin unavailable."
    MSG_UNSUPPORTED_PM="Unsupported package manager. Install manually: %s"
    MSG_CLIENT_EMPTY="Client name cannot be empty."
    MSG_USERS_FILE_FOUND="Found templates/users.yml. Creating VPN clients from the file."
    MSG_CLIENT_TITLE="Client:"
    MSG_CRED_TITLE="Panel credentials"
    MSG_REQ_LOGIN="Panel username [Enter = admin]: "
    MSG_REQ_PASSWORD="Panel password [Enter = admin]: "
    MSG_REQ_CLIENT="VPN client name: "
    MSG_SETUP_TITLE="Domain"
    MSG_DOMAIN_REQ="Enter your domain name (e.g., example.duckdns.org): "
    MSG_DOMAIN_EMPTY="Domain cannot be empty."
    MSG_DOMAIN_INVALID="Invalid domain: %s. Use an ASCII domain without protocol: letters, digits, hyphens, and dots."
    MSG_SEC_SECRET_TITLE="Secret phrase"
    MSG_SEC_SECRET_DESC="The secret phrase is used to generate hidden panel and subscription paths."
    MSG_SUGGEST_SECRET="Secret phrase [Enter = %s]: "
    MSG_PORTS_GENERATING="Selecting free internal ports."
    MSG_PORTS_SELECTED="Selected ports: panel %s, subscription %s, Caddy %s, TCP Reality %s, XHTTP Reality %s."
    MSG_KEYS_GENERATING="Generating Reality keys."
    MSG_KEYS_READY="Reality keys generated."
    MSG_PROCESSING="Generating configuration"
    MSG_CONFIG_SUCCESS="Created file: %s"
    MSG_CONFIG_ERR="Template not found:"
    MSG_START_PANEL="Starting 3x-ui panel"
    MSG_WAIT_3XUI="Waiting for 3x-ui readiness: %s"
    MSG_3XUI_WAIT_PROGRESS="[%s] 3x-ui: %ds / %ds"
    MSG_3XUI_TIMEOUT="3x-ui did not respond at %s within %d seconds."
    MSG_3XUI_READY="3x-ui responded at %s in %d sec."
    MSG_FINAL_LAUNCH="Starting Caddy"
    MSG_WAIT_SSL="Waiting for HTTPS certificate"
    MSG_SSL_TIMEOUT="Certificate was not available within %d seconds."
    MSG_SSL_LOGS_HINT="Check Caddy logs using: docker compose -f $DOCKER_COMPOSE_FILE --project-directory . logs caddy"
    MSG_SSL_VALIDATING="[%s] HTTPS on 443: %ds / %ds"
    MSG_SSL_SUCCESS="HTTPS certificate is active in %d sec."
    MSG_PANEL_USER_CONFIGURING="Configuring panel user."
    MSG_PANEL_USER_READY="Panel user configured."
    MSG_INBOUND_ADDING="Adding inbound: %s."
    MSG_INBOUND_ERR="Failed to add inbound to 3x-UI panel."
    MSG_CLIENT_ADDING="Adding VPN client."
    MSG_CLIENT_READY="VPN client added."
    MSG_RESULTS_TITLE="Done"
    MSG_SETUP_DONE="Installation completed."
    MSG_CRED_PANEL="3x-UI panel is available at:"
    MSG_QR_SUB="Subscription QR code"
    MSG_QR_TCP="VLESS TCP Reality QR code"
    MSG_QR_XHTTP="VLESS XHTTP Reality QR code"
    MSG_CASCADE_TITLE="Cascade Setup"
    MSG_CASCADE_REQ="Are you configuring a cascade? [y/N, Enter = N]: "
    MSG_CASCADE_ERR="Invalid input. Enter y/n or press Enter."
    MSG_NODE_TYPE_TITLE="Node Type"
    MSG_NODE_TYPE_REQ="Is the panel installed ON a foreign (1/freedom) or local (2/proxy) node? [1/2, Enter = 1]: "
    MSG_NODE_TYPE_ERR="Invalid input. Enter 1, 2, freedom, proxy or press Enter."
    MSG_XRAY_ROUTING_UPDATING="Configuring XRay routing for foreign node (freedom)."
    MSG_FOREIGN_SUB_TITLE="Foreign Node Subscription"
    MSG_FOREIGN_SUB_REQ="Enter the subscription URL from your foreign (Freedom) node: "
    MSG_FOREIGN_SUB_ERR="Subscription URL cannot be empty. Please enter a valid URL (starting with http:// or https://):"
    MSG_XRAY_OUTBOUND_SUB_UPDATING="Adding foreign node subscription to XRay outbound subscriptions."
    MSG_XRAY_OUTBOUND_SUB_SUCCESS="Foreign node outbound subscription added successfully."
    MSG_XRAY_OUTBOUND_SUB_ERR="Failed to add foreign node outbound subscription."
}

prompt_domain() {
    section "$MSG_SETUP_TITLE"
    DOMAIN=$(echo "${DOMAIN:-}" | tr -d '[:space:]')
    if [[ -n "$DOMAIN" ]] && is_valid_domain "$DOMAIN"; then
        success "Domain: $DOMAIN"
        return 0
    fi
    while true; do
        if [[ -z "$DOMAIN" ]]; then
            prompt_required "$MSG_DOMAIN_REQ" "$MSG_DOMAIN_EMPTY" DOMAIN
            DOMAIN=$(echo "$DOMAIN" | tr -d '[:space:]')
        fi
        if ! is_valid_domain "$DOMAIN"; then
            warn "$(printf "$MSG_DOMAIN_INVALID" "$DOMAIN")"
            DOMAIN=""
            continue
        fi
        break
    done
}

prompt_node_type() {
    section "$MSG_CASCADE_TITLE"
    if [[ -n "${CASCADE_CHOICE:-}" ]]; then
        if [[ "$CASCADE_CHOICE" =~ ^[Yy]$|^[Yy][Ee][Ss]$ ]]; then
            if [[ -z "${NODE_TYPE_CHOICE:-}" || "$NODE_TYPE_CHOICE" =~ ^1$|^[Ff][Rr][Ee][Ee][Dd][Oo][Mm]$ ]]; then
                NODE_TYPE="freedom"
            else
                NODE_TYPE="proxy"
                FOREIGN_SUB_URL="${FOREIGN_SUB_URL:-}"
            fi
        else
            NODE_TYPE="custom"
        fi
        success "Cascade Node Type: $NODE_TYPE"
        return 0
    fi

    prompt_choice "$MSG_CASCADE_REQ" \
        "$MSG_CASCADE_ERR" \
        '^$|^[YyNn]$|^[Yy][Ee][Ss]$|^[Nn][Oo]$' \
        CASCADE_CHOICE

    if [[ "$CASCADE_CHOICE" =~ ^[Yy]$|^[Yy][Ee][Ss]$ ]]; then
        section "$MSG_NODE_TYPE_TITLE"
        prompt_choice "$MSG_NODE_TYPE_REQ" \
            "$MSG_NODE_TYPE_ERR" \
            '^$|^[12]$|^[Ff][Rr][Ee][Ee][Dd][Oo][Mm]$|^[Pp][Rr][Oo][Xx][Yy]$' \
            NODE_TYPE_CHOICE
            
        if [[ -z "$NODE_TYPE_CHOICE" || "$NODE_TYPE_CHOICE" =~ ^1$|^[Ff][Rr][Ee][Ee][Dd][Oo][Mm]$ ]]; then
            NODE_TYPE="freedom"
        else
            NODE_TYPE="proxy"
            section "$MSG_FOREIGN_SUB_TITLE"
            while true; do
                read -r -p "$MSG_FOREIGN_SUB_REQ" FOREIGN_SUB_URL
                FOREIGN_SUB_URL=$(echo "$FOREIGN_SUB_URL" | tr -d '[:space:]')
                if [[ -n "$FOREIGN_SUB_URL" && "$FOREIGN_SUB_URL" =~ ^https?:// ]]; then
                    break
                else
                    echo -e "${RED}${MSG_FOREIGN_SUB_ERR}${NC}"
                fi
            done
        fi
    else
        NODE_TYPE="custom"
    fi
}


prompt_secret_phrase() {
    if [[ -n "${SECRET_PHRASE:-}" ]]; then
        success "Secret phrase provided via environment."
        return 0
    fi
    if [[ ! -t 0 ]]; then
        die "SECRET_PHRASE is required in non-interactive mode."
    fi
    DEFAULT_SECRET_PHRASE=$(tr -dc '0-9' < /dev/urandom | head -c 16)
    section "$MSG_SEC_SECRET_TITLE"
    echo -e "${YELLOW}${MSG_SEC_SECRET_DESC}${NC}"
    prompt_secret_with_default "$(printf "$MSG_SUGGEST_SECRET" "$DEFAULT_SECRET_PHRASE")" "$DEFAULT_SECRET_PHRASE" SECRET_PHRASE
}

prompt_panel_credentials() {
    section "$MSG_CRED_TITLE"
    if [[ -n "${USERNAME:-}" && -n "${USER_PASSWORD:-}" ]]; then
        success "Panel credentials provided via environment."
        return 0
    fi
    if [[ ! -t 0 ]]; then
        die "USERNAME and USER_PASSWORD are required in non-interactive mode."
    fi
    prompt_with_default "$MSG_REQ_LOGIN" "admin" USERNAME
    prompt_secret_with_default "$MSG_REQ_PASSWORD" "admin" USER_PASSWORD
    echo
}

prompt_client_name() {
    if [[ -n "${CLIENT_EMAIL:-}" ]]; then
        return 0
    fi
    if [[ -n "${USERNAME:-}" ]]; then
        CLIENT_EMAIL="$USERNAME"
        return 0
    fi
    prompt_required "$MSG_REQ_CLIENT" "$MSG_CLIENT_EMPTY" CLIENT_EMAIL
}



generate_ports() {
    info "$MSG_PORTS_GENERATING"
    XUI_WEB_PORT=$(get_unique_random_port)
    XUI_SUB_PORT=$(get_unique_random_port)
    CADDY_GLOBAL_INTERNAL_PORT=$(get_unique_random_port)
    TCP_REALITY_INBOUND_PORT=$(get_unique_random_port)
    XHTTP_REALITY_INBOUND_PORT=$(get_unique_random_port)
    success "$(printf "$MSG_PORTS_SELECTED" "$XUI_WEB_PORT" "$XUI_SUB_PORT" "$CADDY_GLOBAL_INTERNAL_PORT" "$TCP_REALITY_INBOUND_PORT" "$XHTTP_REALITY_INBOUND_PORT")"
}

generate_paths() {
    XUI_WEB_BASE_PATH=$(echo -n "${SECRET_PHRASE}-panel" | md5sum | awk '{print $1}' | cut -c 1-16)
    XUI_SUB_PATH=$(echo -n "${SECRET_PHRASE}-sub"   | md5sum | awk '{print $1}' | cut -c 1-16)
}

generate_reality_keys() {
    info "$MSG_KEYS_GENERATING"
    local tcp_keys
    tcp_keys=$(docker run --rm ghcr.io/xtls/xray-core x25519)
    TCP_REALITY_PRIVATE_KEY=$(echo "$tcp_keys" | grep "PrivateKey:"          | awk '{print $2}' | tr -d '\r')
    TCP_REALITY_PUBLIC_KEY=$(echo  "$tcp_keys" | grep "Password (PublicKey):" | awk '{print $3}' | tr -d '\r')
    TCP_REALITY_SHORT_IDS_JSON_ARRAY="[\"$(openssl rand -hex 2)\", \"$(openssl rand -hex 2)\", \"$(openssl rand -hex 2)\", \"$(openssl rand -hex 2)\"]"

    local xhttp_keys
    xhttp_keys=$(docker run --rm ghcr.io/xtls/xray-core x25519)
    XHTTP_REALITY_PRIVATE_KEY=$(echo "$xhttp_keys" | grep "PrivateKey:"          | awk '{print $2}' | tr -d '\r')
    XHTTP_REALITY_PUBLIC_KEY=$(echo  "$xhttp_keys" | grep "Password (PublicKey):" | awk '{print $3}' | tr -d '\r')
    XHTTP_REALITY_SHORT_IDS_JSON_ARRAY="[\"$(openssl rand -hex 2)\", \"$(openssl rand -hex 2)\", \"$(openssl rand -hex 2)\", \"$(openssl rand -hex 2)\"]"

    if [[ -z "$TCP_REALITY_PRIVATE_KEY" || -z "$TCP_REALITY_PUBLIC_KEY" || -z "$XHTTP_REALITY_PRIVATE_KEY" || -z "$XHTTP_REALITY_PUBLIC_KEY" ]]; then
        die "Failed to generate Reality keypairs from XRay core."
    fi
    success "$MSG_KEYS_READY"
}

source "${SCRIPT_DIR}/process_templates.sh"

wait_for_3xui_ready() {
    local target="$1" timeout=60 counter=0
    shift
    info "$(printf "$MSG_WAIT_3XUI" "$target")"

    while ! "$@" &>/dev/null; do
        if [[ "$counter" -ge "$timeout" ]]; then
            compose down
            die "$(printf "$MSG_3XUI_TIMEOUT" "$target" "$timeout")"
        fi
        printf "\r${YELLOW}${MSG_3XUI_WAIT_PROGRESS}${NC}" "$(show_spinner "$counter")" "$counter" "$timeout"
        sleep 1
        ((counter++))
    done
    printf "\r\033[K"
    success "$(printf "$MSG_3XUI_READY" "$target" "$counter")"
    echo
}

wait_for_3xui_http() {
    local port="$1" path="${2:-/}"
    local url="http://127.0.0.1:${port}${path}"
    wait_for_3xui_ready "$url" panel_exec curl -fsSL "$url" -o /dev/null
}

source "${SCRIPT_DIR}/wait_for_3xui_tcp.sh"

panel_api_request() {
    local endpoint="$1"
    local out_file="$2"
    local extra_args=("${@:3}")

    local curl_args=""
    for arg in "${extra_args[@]}"; do
        curl_args+=" '$(echo "$arg" | sed "s/'/'\\\\''/g")'"
    done

    panel_exec bash -c "
        curl -s \
            -b /tmp/cookie.txt \
            -c /tmp/cookie.txt \
            -H 'accept: application/json, text/plain, */*' \
            ${curl_args} \
            \"http://127.0.0.1:${PANEL_API_PORT}/${endpoint}\"
    " > "$out_file"
}

update_panel_settings_api() {
    section "$MSG_API_START"

    local image_version
    image_version=$(docker ps -f name=3xui --format "{{.Image}}" | awk -F: '{print $2}' | tr -d '[:space:]')

    local api_path="panel/api/setting"

    local current_settings
    info "$MSG_API_FETCHING"
    current_settings=$(panel_exec bash -c "
        curl -s -X POST \
            -b /tmp/cookie.txt \
            -c /tmp/cookie.txt \
            -H 'accept: application/json, text/plain, */*' \
            -H 'x-csrf-token: ${CSRF_TOKEN}' \
            'http://127.0.0.1:${PANEL_API_PORT}/${api_path}/all'
    ")

    if [[ -z "$current_settings" || $(echo "$current_settings" | jq -r '.success') != "true" ]]; then
        die "$MSG_API_FETCH_ERR"
    fi

    local sub_url_value="https://${DOMAIN}/${XUI_SUB_PATH}/"
    local happ_routing_file=""
    if [[ -f "./working/3x-ui/happ-routing.json" ]]; then
        happ_routing_file="./working/3x-ui/happ-routing.json"
    elif [[ -f "${SCRIPT_DIR}/templates/3x-ui/happ-routing.json" ]]; then
        happ_routing_file="${SCRIPT_DIR}/templates/3x-ui/happ-routing.json"
    elif [[ -f "./panel/templates/3x-ui/happ-routing.json" ]]; then
        happ_routing_file="./panel/templates/3x-ui/happ-routing.json"
    fi

    local sub_routing_rules=""
    if [[ -n "$happ_routing_file" && -f "$happ_routing_file" ]]; then
        local encoded_rules
        encoded_rules=$(jq -c . "$happ_routing_file" | base64 | tr -d '\r\n')
        sub_routing_rules="happ://routing/onadd/${encoded_rules}"
    fi

    local payload
    payload=$(echo "$current_settings" | jq -r \
        --arg webPort "$XUI_WEB_PORT" \
        --arg webBasePath "/${XUI_WEB_BASE_PATH}/" \
        --arg subPort "$XUI_SUB_PORT" \
        --arg subPath "/${XUI_SUB_PATH}/" \
        --arg subURI "$sub_url_value" \
        --arg subJsonPath "/${XUI_SUB_PATH}/json/" \
        --arg subJsonURI "${sub_url_value}json/" \
        --arg subRoutingRules "$sub_routing_rules" \
        '.obj
         | .webPort = ($webPort | tonumber)
         | .webBasePath = $webBasePath
         | .subPort = ($subPort | tonumber)
         | .subPath = $subPath
         | .subURI = $subURI
         | .subJsonEnable = true
         | .subJsonPath = $subJsonPath
         | .subJsonURI = $subJsonURI
         | .subUpdates = 1
         | .subEnableRouting = (if ($subRoutingRules != "") then true else (.subEnableRouting // false) end)
         | .subRoutingRules = (if ($subRoutingRules != "") then $subRoutingRules else (.subRoutingRules // "") end)
         | to_entries
         | map("\(.key)=\(.value | tostring | @uri)")
         | join("&")')

    info "$MSG_API_SENDING"

    panel_api_request "${api_path}/update" "./working/update_result.json" \
        -H 'content-type: application/x-www-form-urlencoded; charset=UTF-8' \
        -H "x-csrf-token: ${CSRF_TOKEN}" \
        --data-raw "$payload"

    if ! grep -q '"success":true' ./working/update_result.json; then
        warn "Failed to update panel settings via API. Response details:"
        cat ./working/update_result.json 2>/dev/null || true
        echo
        die "$MSG_API_UPDATE_ERR"
    fi
    success "$MSG_API_UPDATE_SUCCESS"
}

update_xray_routing() {
    local image_version
    image_version=$(docker ps -f name=3xui --format "{{.Image}}" | awk -F: '{print $2}' | tr -d '[:space:]')

    local api_path="panel/xray"
    if [[ -n "$image_version" ]] && [[ "$(printf '%s\n%s' "3.3.1" "$image_version" | sort -V | head -n1)" == "3.3.1" ]]; then
        api_path="panel/api/xray"
    fi

    if [[ "$NODE_TYPE" == "freedom" ]]; then
        info "$MSG_XRAY_ROUTING_UPDATING"

        compose cp ./working/3x-ui/xray-freedom.json 3xui:/tmp/xray_template.json

        panel_api_request "${api_path}/update" "./working/xray_update_result.json" \
            -H 'content-type: application/x-www-form-urlencoded; charset=UTF-8' \
            -H "x-csrf-token: ${CSRF_TOKEN}" \
            --data-urlencode "xraySetting@/tmp/xray_template.json"

        if grep -q '"success":true' ./working/xray_update_result.json; then
            panel_api_request "${api_path}/" "./working/xray_restart_result.json" \
                -X POST \
                -H "x-csrf-token: ${CSRF_TOKEN}"
        else
            warn "Failed to update XRay routing. Details:"
            cat ./working/xray_update_result.json 2>/dev/null || true
            echo
        fi
    elif [[ "$NODE_TYPE" == "proxy" ]]; then
        info "$MSG_XRAY_OUTBOUND_SUB_UPDATING"

        local encoded_url
        encoded_url=$(jq -rn --arg url "$FOREIGN_SUB_URL" '$url | @uri')

        local payload="remark=&url=${encoded_url}&tagPrefix=&updateInterval=600&enabled=true&allowPrivate=false&allowInsecure=false&prepend=false"

        panel_api_request "${api_path}/outbound-subs" "./working/outbound_sub_result.json" \
            -H 'content-type: application/x-www-form-urlencoded; charset=UTF-8' \
            -H "x-csrf-token: ${CSRF_TOKEN}" \
            -d "$payload"

        if grep -q '"success":true' ./working/outbound_sub_result.json; then
            success "$MSG_XRAY_OUTBOUND_SUB_SUCCESS"
            local sub_id
            sub_id=$(jq -r '.obj.id // empty' ./working/outbound_sub_result.json 2>/dev/null || true)
            if [[ -z "$sub_id" || "$sub_id" == "null" ]]; then
                sub_id=1
            fi
            panel_api_request "${api_path}/outbound-subs/${sub_id}/refresh" "./working/outbound_sub_refresh.json" \
                -X POST \
                -H "x-csrf-token: ${CSRF_TOKEN}"

            local sub_outbound_tag=""
            panel_api_request "${api_path}/" "./working/xray_current_setting.json"
            sub_outbound_tag=$(jq -r '.obj | try fromjson catch {} | .outbounds[]? | select(.tag | startswith("sub1-")) | .tag' ./working/xray_current_setting.json 2>/dev/null | head -n 1 || true)

            if [[ -z "$sub_outbound_tag" ]]; then
                sub_outbound_tag=$(jq -r '.obj[]? | select(.tag | startswith("sub1-")) | .tag' ./working/outbound_sub_refresh.json 2>/dev/null | head -n 1 || true)
            fi

            if [[ -z "$sub_outbound_tag" ]]; then
                sub_outbound_tag="sub1-vless-xhttp-reality-local-proxy-node-client"
            fi

            sed "s/{{SUB_OUTBOUND_TAG}}/${sub_outbound_tag}/g" ./working/3x-ui/xray-proxy.json > ./working/xray_template.json
            compose cp ./working/xray_template.json 3xui:/tmp/xray_template.json

            panel_api_request "${api_path}/update" "./working/xray_update_result.json" \
                -H 'content-type: application/x-www-form-urlencoded; charset=UTF-8' \
                -H "x-csrf-token: ${CSRF_TOKEN}" \
                --data-urlencode "xraySetting@/tmp/xray_template.json"

            if grep -q '"success":true' ./working/xray_update_result.json; then
                panel_api_request "${api_path}/" "./working/xray_restart_result.json" \
                    -X POST \
                    -H "x-csrf-token: ${CSRF_TOKEN}"
            else
                warn "Failed to update XRay routing for proxy node. Details:"
                cat ./working/xray_update_result.json 2>/dev/null || true
                echo
            fi
        else
            warn "$MSG_XRAY_OUTBOUND_SUB_ERR Details:"
            cat ./working/outbound_sub_result.json 2>/dev/null || true
            echo
        fi
    fi
}

start_container() {
    local service="$1"
    compose rm -sf "$service" 2>/dev/null
    compose up -d "$service"
}

start_3xui() {
    section "$MSG_START_PANEL"
    start_container "$PANEL_CONTAINER"
}

start_caddy() {
    section "$MSG_FINAL_LAUNCH"
    compose up -d
}

source "${SCRIPT_DIR}/wait_for_ssl.sh"

panel_login() {
    local enc_user enc_pass
    enc_user=$(url_encode "$1")
    enc_pass=$(url_encode "$2")

    panel_api_request "login" "/dev/null" \
        -H 'content-type: application/x-www-form-urlencoded; charset=UTF-8' \
        -H "x-csrf-token: ${CSRF_TOKEN:-}" \
        --data-raw "username=${enc_user}&password=${enc_pass}"
}

get_csrf_token() {
    local html_file="$1"
    grep -oP 'csrf-token"\s+content="\K[^"]+' "$html_file" || echo ""
}

fetch_panel_page() {
    panel_api_request "panel/" "$1" -L
}

configure_panel_user() {
    info "$MSG_PANEL_USER_CONFIGURING"

    local enc_old_user enc_old_pass enc_new_user enc_new_pass
    enc_old_user=$(url_encode "admin")
    enc_old_pass=$(url_encode "admin")
    enc_new_user=$(url_encode "$USERNAME")
    enc_new_pass=$(url_encode "$USER_PASSWORD")

    panel_api_request "" "./working/index.html"
    CSRF_TOKEN=$(get_csrf_token ./working/index.html)

    panel_login "admin" "admin"

    fetch_panel_page "./working/panel.html"
    CSRF_TOKEN=$(get_csrf_token ./working/panel.html)

    panel_api_request "panel/api/setting/updateUser" "/dev/null" \
        -H 'content-type: application/x-www-form-urlencoded; charset=UTF-8' \
        -H "x-csrf-token: ${CSRF_TOKEN}" \
        --data-raw "oldUsername=${enc_old_user}&oldPassword=${enc_old_pass}&newUsername=${enc_new_user}&newPassword=${enc_new_pass}"

    panel_login "$USERNAME" "$USER_PASSWORD"

    fetch_panel_page "./working/panel.html"
    CSRF_TOKEN=$(get_csrf_token ./working/panel.html)
    success "$MSG_PANEL_USER_READY"
}

add_inbound() {
    local config_name="$1"
    local payload
    info "$(printf "$MSG_INBOUND_ADDING" "$config_name")"
    payload=$(jq -r --arg filename "$config_name" '
      { up: 0, down: 0, total: 0, remark: $filename, enable: true, expiryTime: 0, trafficReset: "never", lastTrafficResetTime: 0, tag: .tag } + . | to_entries | map("\(.key)=\(if (.value | type) == "object" then (.value | tojson | @uri) else (.value | tostring | @uri) end)") | join("&")
    ' "./working/3x-ui/$config_name")

    panel_api_request "panel/api/inbounds/add" "./working/add-inbound-response.json" \
        -H 'content-type: application/x-www-form-urlencoded; charset=UTF-8' \
        -H "x-csrf-token: ${CSRF_TOKEN}" \
        --data-raw "$payload"

    grep -q '"success":true' ./working/add-inbound-response.json || die "$MSG_INBOUND_ERR"
}

add_client() {
    local email="$1"
    local inbound_ids="$2"
    info "$MSG_CLIENT_ADDING"
    local client_uuid
    client_uuid=$(cat /proc/sys/kernel/random/uuid)

    local client_payload
    client_payload=$(jq -n \
        --arg email "$email" \
        --arg subId "$email" \
        --arg id "$client_uuid" \
        --argjson inboundIds "$inbound_ids" \
        '{ client: { email: $email, subId: $subId, id: $id, password: "", auth: "", flow: "xtls-rprx-vision", security: "auto", totalGB: 0, expiryTime: 0, reset: 0, limitIp: 0, tgId: 0, group: "", comment: "", enable: true }, inboundIds: $inboundIds }')

    panel_api_request "panel/api/clients/add" "./working/add-client-response.json" \
        -H 'content-type: application/json' \
        -H "x-csrf-token: ${CSRF_TOKEN}" \
        --data-raw "${client_payload}"

    grep -q '"success":true' ./working/add-client-response.json || die "$MSG_CLIENT_ERR"
    success "$MSG_CLIENT_READY"
}

add_interactive_client() {
    prompt_client_name
    add_client "$CLIENT_EMAIL" "[1,2]"
    CREATED_CLIENTS+=("$CLIENT_EMAIL")
}



source "${SCRIPT_DIR}/build_sub_and_connect_urls.sh"

install_ssh_login_notice() {
    cat > /etc/profile.d/3x-ui.sh <<EOF
#!/usr/bin/env bash

case "\$-" in
    *i*) ;;
    *) return 0 2>/dev/null || exit 0 ;;
esac

[[ -n "\${SSH_CONNECTION:-}" || -n "\${SSH_TTY:-}" ]] || return 0 2>/dev/null || exit 0

cat <<'MSG'

${MSG_CRED_PANEL}
  https://${DOMAIN}/${XUI_WEB_BASE_PATH}/

MSG
EOF

    chmod 644 /etc/profile.d/3x-ui.sh
}

collect_results() {
    RESULTS_CLIENTS=()
    RESULTS_SUB_URLS=()
    RESULTS_TCP_URLS=()
    RESULTS_XHTTP_URLS=()

    local client_name
    for client_name in "${CREATED_CLIENTS[@]}"; do
        CLIENT_EMAIL="$client_name"
        if build_sub_and_connect_urls; then
            RESULTS_CLIENTS+=("$client_name")
            RESULTS_SUB_URLS+=("$CLIENT_SUBSCRIPTION_URL")
            RESULTS_TCP_URLS+=("${CLIENT_VLESS_TCP_URL:-}")
            RESULTS_XHTTP_URLS+=("${CLIENT_VLESS_XHTTP_URL:-}")
        fi
    done
}

print_json_results() {
    echo "===RESULT_JSON_START==="
    local clients_items=()
    local i
    for i in "${!RESULTS_CLIENTS[@]}"; do
        clients_items+=("$(jq -n \
            --arg name "${RESULTS_CLIENTS[$i]}" \
            --arg sub "${RESULTS_SUB_URLS[$i]}" \
            --arg tcp "${RESULTS_TCP_URLS[$i]:-}" \
            --arg xhttp "${RESULTS_XHTTP_URLS[$i]:-}" \
            '{name: $name, sub_url: $sub, tcp_url: $tcp, xhttp_url: $xhttp}')")
    done
    
    local clients_payload="[]"
    if [ ${#clients_items[@]} -gt 0 ]; then
        clients_payload=$(printf '%s\n' "${clients_items[@]}" | jq -s '.')
    fi
    
    jq -n \
        --arg url "https://${DOMAIN}/${XUI_WEB_BASE_PATH}/" \
        --argjson clients "${clients_payload}" \
        '{panel_url: $url, clients: $clients}'
    echo "===RESULT_JSON_END==="
}

print_results() {
    section "$MSG_RESULTS_TITLE"
    echo -e "${GREEN}${MSG_SETUP_DONE}${NC}\n"
    echo -e "${CYAN}${MSG_CRED_PANEL}${NC}"
    echo -e "  ${YELLOW}https://${DOMAIN}/${XUI_WEB_BASE_PATH}/${NC}"

    local i
    for i in "${!RESULTS_CLIENTS[@]}"; do
        echo -e "\nClient: ${RESULTS_CLIENTS[$i]}"

        echo -e "\nSubscription:"
        echo -e "  ${RESULTS_SUB_URLS[$i]}"
        echo -e "Subscription QR Code:"
        qrencode -t ANSIUTF8 "${RESULTS_SUB_URLS[$i]}"

        if [[ -n "${RESULTS_TCP_URLS[$i]}" ]]; then
            echo -e "\nVLESS TCP Reality:"
            echo -e "  ${RESULTS_TCP_URLS[$i]}"
            echo -e "VLESS TCP QR Code:"
            qrencode -t ANSIUTF8 "${RESULTS_TCP_URLS[$i]}"
            echo
        fi

        if [[ -n "${RESULTS_XHTTP_URLS[$i]}" ]]; then
            echo -e "\nVLESS XHTTP Reality:"
            echo -e "  ${RESULTS_XHTTP_URLS[$i]}"
            echo -e "VLESS XHTTP QR Code:"
            qrencode -t ANSIUTF8 "${RESULTS_XHTTP_URLS[$i]}"
            echo
        fi
    done

    print_json_results
}

main() {
    load_messages
    check_root
    install_missing_deps \
        "${REQUIRED_CMDS[*]}" \
        "curl ca-certificates jq openssl qrencode iproute2 procps coreutils gawk grep sed" \
        "curl ca-certificates jq openssl qrencode iproute procps-ng coreutils gawk grep sed" \
        "curl ca-certificates jq openssl qrencode iproute2 procps-ng coreutils gawk grep sed"
    reset_working_dir

    prompt_domain
    prompt_node_type
    prompt_secret_phrase
    generate_ports

    generate_paths
    generate_reality_keys
    process_templates
    prompt_panel_credentials
    start_3xui
    wait_for_3xui_http "$PANEL_API_PORT"
    configure_panel_user
    add_inbound vless-tcp-reality
    add_inbound vless-xhttp-reality
    if [[ -n "${CLIENTS_TCP_LIST:-}" || -n "${CLIENTS_XHTTP_LIST:-}" ]]; then
        local tcp_names=" ${CLIENTS_TCP_LIST:-} "
        local xhttp_names=" ${CLIENTS_XHTTP_LIST:-} "
        local all_names
        all_names=$(echo "${CLIENTS_TCP_LIST:-} ${CLIENTS_XHTTP_LIST:-}" | tr ' ' '\n' | sort -u | grep -v '^$')

        local name
        for name in $all_names; do
            local in_tcp=0
            local in_xhttp=0
            [[ "$tcp_names" =~ [[:space:]]"$name"[[:space:]] ]] && in_tcp=1
            [[ "$xhttp_names" =~ [[:space:]]"$name"[[:space:]] ]] && in_xhttp=1

            if [[ $in_tcp -eq 1 && $in_xhttp -eq 1 ]]; then
                add_client "$name" "[1,2]"
            elif [[ $in_tcp -eq 1 ]]; then
                add_client "$name" "[1]"
            elif [[ $in_xhttp -eq 1 ]]; then
                add_client "$name" "[2]"
            fi
            CREATED_CLIENTS+=("$name")
        done
    else
        add_interactive_client
    fi
    update_panel_settings_api
    update_xray_routing


    start_3xui
    wait_for_3xui_tcp "$TCP_REALITY_INBOUND_PORT"
    start_caddy

    wait_for_ssl

    collect_results
    install_ssh_login_notice
    print_results
}

main
