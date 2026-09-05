#!/usr/bin/env bash
set -uo pipefail

readonly NC='\033[0m'
readonly GREEN='\033[0;32m'
readonly CYAN='\033[0;36m'
readonly YELLOW='\033[0;33m'
readonly RED='\033[0;31m'

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly DOCKER_COMPOSE_FILE="./working/docker-compose/docker-compose.yml"
readonly DECOY_HTML_BACKUP="/tmp/sub-server-decoy-html.bak"

source "$SCRIPT_DIR/../common/setup.sh"

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

is_valid_domain() {
    local domain="$1"
    [[ ${#domain} -le 253 ]] &&
        [[ "$domain" =~ ^[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?(\.[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$ ]]
}

reset_working_dir() {
    info "Preparing ./working directory."
    # Clean up any orphaned containers to ensure a clean slate in case of crash-loops or interrupted deployments
    docker rm -f subs-server sub-caddy caddy sub-nginx-decoy nginx-decoy 2>/dev/null || true

    # Preserve the currently deployed decoy site across update_sub unless a new
    # decoy template was explicitly requested (UPDATE_SUB_DECOY=1). Working/
    # is regenerated from the synced templates below, so without this the decoy
    # always falls back to the builtin one on every bare update.
    if [[ "${UPDATE_SUB_SERVER:-0}" == "1" && "${UPDATE_SUB_DECOY:-0}" != "1" && -d "./working/nginx-decoy/html" ]]; then
        rm -rf "$DECOY_HTML_BACKUP"
        cp -r ./working/nginx-decoy/html "$DECOY_HTML_BACKUP"
        info "Update mode: preserving current decoy site (no new template selected)."
    fi

    # Clean state files only on fresh deployment, preserve them on update_sub
    if [[ "${UPDATE_SUB_SERVER:-0}" != "1" ]]; then
        rm -f "$SCRIPT_DIR/nodes.json" "$SCRIPT_DIR/force-subs.yml" "$SCRIPT_DIR/sub-server.log"
    fi

    # Docker Engine might have recreated missing host paths as directories while crash-looping
    for f in "$SCRIPT_DIR/nodes.json" "$SCRIPT_DIR/force-subs.yml" "$SCRIPT_DIR/sub-server.log"; do
        if [[ -d "$f" ]]; then
            rm -rf "$f"
        fi
    done

    if [[ -f "$DOCKER_COMPOSE_FILE" ]]; then
        compose down 2>/dev/null || true
    fi
    rm -rf "./working" && mkdir -p "./working"
    success "Working directory ready."
}

ensure_state_files() {
    # Bind-mount targets must exist as files on the host, otherwise Docker
    # creates directories and the container fails to write to them.
    [[ -f "$SCRIPT_DIR/force-subs.yml" ]] || touch "$SCRIPT_DIR/force-subs.yml"
    [[ -f "$SCRIPT_DIR/nodes.json" ]] || touch "$SCRIPT_DIR/nodes.json"
    [[ -f "$SCRIPT_DIR/sub-server.log" ]] || touch "$SCRIPT_DIR/sub-server.log"
}

validate_update_state() {
    [[ "${UPDATE_SUB_SERVER:-0}" == "1" ]] || return 0
    [[ -f "$SCRIPT_DIR/nodes.json" ]] || die "Cannot update Subscription Server: nodes.json is missing."
    [[ -f "$SCRIPT_DIR/force-subs.yml" ]] || touch "$SCRIPT_DIR/force-subs.yml"
    info "Update mode: preserving nodes.json and force-subs.yml."
}

load_existing_update_values() {
    [[ "${UPDATE_SUB_SERVER:-0}" == "1" ]] || return 0
    local compose_file="./working/docker-compose/docker-compose.yml"
    local caddy_file="./working/caddy/Caddyfile"
    local value

    if [[ -f "$compose_file" ]]; then
        value=$(sed -n 's/^      SECRET_SUB_PATH: "\(.*\)"/\1/p' "$compose_file" | head -n1)
        [[ -n "${SECRET_SUB_PATH:-}" || -z "$value" ]] || SECRET_SUB_PATH="$value"
        value=$(sed -n 's/^      RUSSIAN_SUB_URL: "\(.*\)"/\1/p' "$compose_file" | head -n1)
        [[ -n "${RUSSIAN_SUB_URL:-}" || -z "$value" ]] || RUSSIAN_SUB_URL="$value"
        value=$(sed -n 's/^      FOREIGN_SUB_URL: "\(.*\)"/\1/p' "$compose_file" | head -n1)
        [[ -n "${FOREIGN_SUB_URL:-}" || -z "$value" ]] || FOREIGN_SUB_URL="$value"
        value=$(sed -n 's/^      PROXY_DOMAIN: "\(.*\)"/\1/p' "$compose_file" | head -n1)
        [[ -n "${PROXY_DOMAIN:-}" || -z "$value" ]] || PROXY_DOMAIN="$value"
        value=$(sed -n 's/^      FREEDOM_DOMAIN: "\(.*\)"/\1/p' "$compose_file" | head -n1)
        [[ -n "${FREEDOM_DOMAIN:-}" || -z "$value" ]] || FREEDOM_DOMAIN="$value"
        value=$(sed -n 's/^      ADMIN_USER: "\(.*\)"/\1/p' "$compose_file" | head -n1)
        [[ -n "${ADMIN_USER:-}" || -z "$value" ]] || ADMIN_USER="$value"
        value=$(sed -n 's/^      ADMIN_PASSWORD: "\(.*\)"/\1/p' "$compose_file" | head -n1)
        [[ -n "${ADMIN_PASSWORD:-}" || -z "$value" ]] || ADMIN_PASSWORD="$value"
    fi
    if [[ -f "$caddy_file" && -z "${DOMAIN:-}" ]]; then
        DOMAIN=$(sed -n 's/.*redir https:\/\/\([^/{]*\).*/\1/p' "$caddy_file" | head -n1)
        [[ -n "$DOMAIN" ]] || DOMAIN=$(grep -E '^[a-zA-Z0-9.-]+ \{' "$caddy_file" | head -n1 | awk '{print $1}')
    fi
}

prompt_domain() {
    if [[ -n "${DOMAIN:-}" ]] && is_valid_domain "$DOMAIN"; then
        info "Using domain from environment: $DOMAIN"
        return
    fi
    while :; do
        read -r -p "$(echo -e "${CYAN}[..]${NC} Enter domain (e.g. sub.example.com): ")" DOMAIN
        if is_valid_domain "$DOMAIN"; then
            break
        fi
        warn "Invalid domain, please try again."
    done
}

prompt_sub_path() {
    if [[ -n "${SECRET_SUB_PATH:-}" ]]; then
        SECRET_SUB_PATH="${SECRET_SUB_PATH#/}"
        SECRET_SUB_PATH="${SECRET_SUB_PATH%/}"
        info "Using secret sub path from environment: $SECRET_SUB_PATH"
        return
    fi
    if [[ -n "${SECRET_PHRASE:-}" ]]; then
        SECRET_SUB_PATH=$(echo -n "${SECRET_PHRASE}" | md5sum | awk '{print $1}' | cut -c 1-16)
        info "Using secret sub path derived from SECRET_PHRASE: $SECRET_SUB_PATH"
        return
    fi
    if [[ ! -t 0 ]]; then
        die "SECRET_SUB_PATH or SECRET_PHRASE is required in non-interactive mode."
    fi
    local default_phrase
    default_phrase=$(tr -dc '0-9' < /dev/urandom | head -c 16)
    read -r -p "$(echo -e "${CYAN}[..]${NC} Secret phrase [default: $default_phrase]: ")" user_phrase
    user_phrase="${user_phrase:-$default_phrase}"
    SECRET_SUB_PATH=$(echo -n "${user_phrase}" | md5sum | awk '{print $1}' | cut -c 1-16)
}

prompt_subscription_urls() {
    if [[ -n "${RUSSIAN_SUB_URL:-}" || -n "${FOREIGN_SUB_URL:-}" ]]; then
        RUSSIAN_SUB_URL="${RUSSIAN_SUB_URL:-}"
        RUSSIAN_SUB_URL="${RUSSIAN_SUB_URL%/}"
        FOREIGN_SUB_URL="${FOREIGN_SUB_URL:-}"
        FOREIGN_SUB_URL="${FOREIGN_SUB_URL%/}"
        info "Using subscription URLs from environment."
        return
    fi
    RUSSIAN_SUB_URL=""
    FOREIGN_SUB_URL=""
    read -r -p "$(echo -e "${CYAN}[..]${NC} Configure Russian node? (y/N): ")" has_ru
    if [[ "$has_ru" =~ ^[Yy]$ ]]; then
        read -r -p "$(echo -e "${CYAN}[..]${NC} Russian node subscription URL: ")" RUSSIAN_SUB_URL
        RUSSIAN_SUB_URL="${RUSSIAN_SUB_URL%/}"
    fi
    read -r -p "$(echo -e "${CYAN}[..]${NC} Foreign node subscription URL: ")" FOREIGN_SUB_URL
    FOREIGN_SUB_URL="${FOREIGN_SUB_URL%/}"
    [[ -n "$RUSSIAN_SUB_URL" || -n "$FOREIGN_SUB_URL" ]] || die "At least one subscription URL must be specified."
}

json_escape() {
    local s="$1"
    s="${s//\\/\\\\}"
    s="${s//\"/\\\"}"
    s="${s//$'\t'/\\t}"
    s="${s//$'\n'/\\n}"
    s="${s//$'\r'/\\r}"
    printf '%s' "$s"
}

create_nodes_json() {
    info "Configuring nodes.json registry."
    local entries=()
    local group_url group_clients items clients_json item client

    extract_domain() {
        local u="$1"
        u="${u#*://}"
        u="${u%%/*}"
        u="${u%%:*}"
        printf '%s' "$u"
    }

    build_node() {
        local node_id="$1" node_type="$2" node_name="$3" node_url="$4" node_clients="${5:-}"
        if [[ -z "$node_url" ]]; then
            warn "No subscription URL for '${node_id}' node, skipping it."
            return
        fi
        items=()
        if [[ -n "$node_clients" ]]; then
            for client in $node_clients; do
                items+=("$(printf '"%s"' "$(json_escape "$client")")")
            done
        fi
        if [[ ${#items[@]} -gt 0 ]]; then
            clients_json="$(IFS=','; printf '[%s]' "${items[*]}")"
        else
            clients_json="[]"
        fi
        entries+=("$(printf '{"id": "%s", "type": "%s", "name": "%s", "url": "%s", "clients": %s, "supports_json": true}' \
            "$(json_escape "$node_id")" "$(json_escape "$node_type")" "$(json_escape "$node_name")" "$(json_escape "$node_url")" "$clients_json")")
    }

    local ru_domain="${PROXY_DOMAIN:-${RUSSIAN_NODE_DOMAIN:-}}"
    [[ -n "$ru_domain" ]] || ru_domain="$(extract_domain "${RUSSIAN_SUB_URL:-}")"
    [[ -n "$ru_domain" ]] || ru_domain="proxy"

    local fr_domain="${FREEDOM_DOMAIN:-${FREEDOM_NODE_DOMAIN:-}}"
    [[ -n "$fr_domain" ]] || fr_domain="$(extract_domain "${FOREIGN_SUB_URL:-}")"
    [[ -n "$fr_domain" ]] || fr_domain="freedom"

    build_node "proxy" "proxy" "$ru_domain" "${RUSSIAN_SUB_URL:-}" "${PROXY_CLIENTS:-}"
    build_node "freedom" "freedom" "$fr_domain" "${FOREIGN_SUB_URL:-}" "${FREEDOM_CLIENTS:-}"

    if [[ ${#entries[@]} -eq 0 ]]; then
        die "At least one node with a subscription URL is required."
    fi

    printf '[%s]\n' "$(IFS=','; printf '%s' "${entries[*]}")" > "$SCRIPT_DIR/nodes.json"
    success "Node registry written to nodes.json."
}

prompt_admin() {
    if [[ -n "${ADMIN_USER:-}" && -n "${ADMIN_PASSWORD:-}" ]]; then
        info "Using panel admin credentials from environment."
        return
    fi
    if [[ ! -t 0 ]]; then
        die "ADMIN_USER and ADMIN_PASSWORD are required in non-interactive mode."
    fi
    ADMIN_USER="${ADMIN_USER:-admin}"
    read -r -p "$(echo -e "${CYAN}[..]${NC} Panel admin login [default: $ADMIN_USER]: ")" ADMIN_USER
    ADMIN_USER="${ADMIN_USER:-admin}"
    if [[ -z "${ADMIN_PASSWORD:-}" ]]; then
        ADMIN_PASSWORD="$(tr -dc 'A-Za-z0-9' < /dev/urandom | head -c 12)"
        read -r -p "$(echo -e "${CYAN}[..]${NC} Panel admin password [default: auto-generated]: ")" ADMIN_PASSWORD
        ADMIN_PASSWORD="${ADMIN_PASSWORD:-$ADMIN_PASSWORD}"
    fi
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
    local domain sub_path ru_url foreign_url proxy_domain freedom_domain admin_user admin_pass
    domain="$(sed_escape_replacement "${DOMAIN}")"
    sub_path="$(sed_escape_replacement "${SECRET_SUB_PATH}")"
    ru_url="$(sed_escape_replacement "${RUSSIAN_SUB_URL}")"
    foreign_url="$(sed_escape_replacement "${FOREIGN_SUB_URL}")"
    proxy_domain="$(sed_escape_replacement "${PROXY_DOMAIN:-}")"
    freedom_domain="$(sed_escape_replacement "${FREEDOM_DOMAIN:-}")"
    admin_user="$(sed_escape_replacement "${ADMIN_USER}")"
    admin_pass="$(sed_escape_replacement "${ADMIN_PASSWORD}")"
    sed -i \
       -e "s|{{DOMAIN}}|${domain}|g" \
       -e "s|{{SECRET_SUB_PATH}}|${sub_path}|g" \
       -e "s|{{RUSSIAN_SUB_URL}}|${ru_url}|g" \
       -e "s|{{FOREIGN_SUB_URL}}|${foreign_url}|g" \
       -e "s|{{PROXY_DOMAIN}}|${proxy_domain}|g" \
       -e "s|{{FREEDOM_DOMAIN}}|${freedom_domain}|g" \
       -e "s|{{ADMIN_USER}}|${admin_user}|g" \
       -e "s|{{ADMIN_PASSWORD}}|${admin_pass}|g" \
       "$target_path"
}

generate_config() {
    local template_dir="$1"
    local target_dir="$2"
    local source_path relative_path target_relative target_path

    [[ -d "$template_dir" ]] || die "Templates not found: $template_dir"
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

    success "Configurations generated in $target_dir"
}


source "${SCRIPT_DIR}/process_templates.sh"

start_containers() {
    section "Starting containers"
    compose up -d --build
}

source "${SCRIPT_DIR}/wait_for_ssl.sh"

show_spinner() {
    local counter=$1
    local spin_chars="/-\|"
    echo -ne "${spin_chars:$((counter % 4)):1}"
}

print_results() {
    section "Done"
    echo "Subscriptions available at:"
    echo "  https://${DOMAIN}/${SECRET_SUB_PATH}/<username>"
    echo
    echo "Panel: https://${DOMAIN}/${SECRET_SUB_PATH}"
    echo "  Admin login: ${ADMIN_USER}"
    echo
    echo "Node registry (clients): $SCRIPT_DIR/nodes.json"
    echo "After editing nodes.json restart: docker compose -f $DOCKER_COMPOSE_FILE restart subs-server"
}

main() {
    check_root
    install_missing_deps "curl" "curl ca-certificates iproute2" "curl ca-certificates iproute" "curl ca-certificates iproute2"
    validate_update_state
    load_existing_update_values
    reset_working_dir

    prompt_domain
    prompt_sub_path
    prompt_subscription_urls
    prompt_admin
    if [[ "${UPDATE_SUB_SERVER:-0}" == "1" ]]; then
        info "Keeping existing client and node configuration."
    else
        create_nodes_json
    fi

    ensure_state_files

    process_templates

    # Restore the previously deployed decoy site after templates regenerate
    # ./working (n/a when a new decoy template was selected).
    if [[ -d "$DECOY_HTML_BACKUP" ]]; then
        rm -rf ./working/nginx-decoy/html
        cp -r "$DECOY_HTML_BACKUP" ./working/nginx-decoy/html
        rm -rf "$DECOY_HTML_BACKUP"
        success "Restored current decoy site across the update."
    fi

    start_containers

    wait_for_ssl
    print_results
}

main
