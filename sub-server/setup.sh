#!/usr/bin/env bash
set -uo pipefail

readonly NC='\033[0m'
readonly GREEN='\033[0;32m'
readonly CYAN='\033[0;36m'
readonly YELLOW='\033[0;33m'
readonly RED='\033[0;31m'

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly DOCKER_COMPOSE_FILE="./working/docker-compose/docker-compose.yml"

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

check_root() {
    [[ $EUID -eq 0 ]] || die "Script must be run as root: sudo ./setup.sh"
}

get_package_manager() {
    if command -v apt-get &>/dev/null; then echo "apt";
    elif command -v dnf &>/dev/null; then echo "dnf";
    elif command -v yum &>/dev/null; then echo "yum";
    elif command -v pacman &>/dev/null; then echo "pacman";
    else echo "unknown"; fi
}

install_docker() {
    if ! command -v docker &>/dev/null; then
        info "Docker not found. Installing Docker."
        if command -v pacman &>/dev/null; then
            pacman -S --noconfirm docker docker-compose || die "Failed to install Docker."
        else
            curl -fsSL https://get.docker.com | sh || die "Failed to install Docker."
        fi
    fi

    if command -v systemctl &>/dev/null; then
        systemctl is-active --quiet docker || systemctl start docker || die "Failed to start Docker service."
        systemctl is-enabled --quiet docker || systemctl enable docker
    fi

    docker compose version &>/dev/null || die "Docker compose plugin unavailable."
    success "Docker is ready."
}

install_missing_deps() {
    section "Environment check"
    local missing=()
    for cmd in curl; do
        command -v "$cmd" &>/dev/null || missing+=("$cmd")
    done

    if [[ ${#missing[@]} -gt 0 ]]; then
        local pm
        pm=$(get_package_manager)
        case "$pm" in
            apt)     apt-get update && apt-get install -y curl ca-certificates iproute2 || die "Failed to install system dependencies." ;;
            dnf|yum) $pm install -y curl ca-certificates iproute || die "Failed to install system dependencies." ;;
            pacman)  pacman -Sy --noconfirm curl ca-certificates iproute2 || die "Failed to install system dependencies." ;;
            *)       die "Could not determine package manager." ;;
        esac
    fi

    install_docker
}

reset_working_dir() {
    info "Preparing ./working directory."
    if [[ -f "$DOCKER_COMPOSE_FILE" ]]; then
        compose down
    fi
    rm -rf "./working" && mkdir -p "./working"
    success "Working directory ready."
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
        value=$(sed -n 's/^      ADMIN_USER: "\(.*\)"/\1/p' "$compose_file" | head -n1)
        [[ -n "${ADMIN_USER:-}" || -z "$value" ]] || ADMIN_USER="$value"
        value=$(sed -n 's/^      ADMIN_PASSWORD: "\(.*\)"/\1/p' "$compose_file" | head -n1)
        [[ -n "${ADMIN_PASSWORD:-}" || -z "$value" ]] || ADMIN_PASSWORD="$value"
    fi
    if [[ -f "$caddy_file" && -z "${DOMAIN:-}" ]]; then
        DOMAIN=$(sed -n 's/^http:\/\/\([^ ]*\) {.*/\1/p' "$caddy_file" | head -n1)
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
    local default="subs"
    read -r -p "$(echo -e "${CYAN}[..]${NC} Path prefix [default: $default]: ")" SECRET_SUB_PATH
    SECRET_SUB_PATH="${SECRET_SUB_PATH:-$default}"
    SECRET_SUB_PATH="${SECRET_SUB_PATH#/}"
    SECRET_SUB_PATH="${SECRET_SUB_PATH%/}"
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

    build_node() {
        local node_id="$1" node_name="$2" node_url="$3" node_clients="$4"
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
        entries+=("$(printf '{"id": "%s", "name": "%s", "url": "%s", "clients": %s}' \
            "$(json_escape "$node_id")" "$(json_escape "$node_name")" "$(json_escape "$node_url")" "$clients_json")")
    }

    build_node "proxy" "Proxy (РФ)" "${RUSSIAN_SUB_URL:-}" "${PROXY_CLIENTS:-}"
    build_node "freedom" "Freedom (зарубежье)" "${FOREIGN_SUB_URL:-}" "${FREEDOM_CLIENTS:-}"

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
    local domain sub_path ru_url foreign_url admin_user admin_pass
    domain="$(sed_escape_replacement "${DOMAIN}")"
    sub_path="$(sed_escape_replacement "${SECRET_SUB_PATH}")"
    ru_url="$(sed_escape_replacement "${RUSSIAN_SUB_URL}")"
    foreign_url="$(sed_escape_replacement "${FOREIGN_SUB_URL}")"
    admin_user="$(sed_escape_replacement "${ADMIN_USER}")"
    admin_pass="$(sed_escape_replacement "${ADMIN_PASSWORD}")"
    sed -i \
       -e "s|{{DOMAIN}}|${domain}|g" \
       -e "s|{{SECRET_SUB_PATH}}|${sub_path}|g" \
       -e "s|{{RUSSIAN_SUB_URL}}|${ru_url}|g" \
       -e "s|{{FOREIGN_SUB_URL}}|${foreign_url}|g" \
       -e "s|{{ADMIN_USER}}|${admin_user}|g" \
       -e "s|{{ADMIN_PASSWORD}}|${admin_pass}|g" \
       "$target_path"
}

generate_config() {
    local template_dir="$1"
    local target_dir="$2"
    local source_path relative_path target_relative target_path

    [[ -d "$template_dir" ]] || die "Templates not found: $template_dir"
    rm -rf "$target_dir"
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

process_templates() {
    section "Generating configuration"
    generate_config "./sub-server/templates" "./working"
}

start_containers() {
    section "Starting containers"
    compose up -d --build
}

wait_for_ssl() {
    local cert_timeout=300 cert_counter=0
    section "Waiting for SSL certificate"

    while ! curl -s --connect-timeout 2 --max-time 5 --resolve "${DOMAIN}:443:127.0.0.1" "https://${DOMAIN}:443" -o /dev/null; do
        if [[ "$cert_counter" -ge "$cert_timeout" ]]; then
            warn "Check logs: docker compose -f $DOCKER_COMPOSE_FILE logs caddy"
            die "SSL certificate was not obtained within $cert_timeout seconds."
        fi
        printf "\r${YELLOW}[..]${NC} Validating SSL certificate %s %s/%s" "$(show_spinner "$cert_counter")" "$cert_counter" "$cert_timeout"
        sleep 1
        ((cert_counter++))
    done
    echo
    success "SSL certificate is active."
}

show_spinner() {
    local counter=$1
    local spin_chars="/-\|"
    echo -ne "${spin_chars:$((counter % 4)):1}"
}

print_results() {
    section "Done"
    echo "Subscriptions available at:"
    echo "  https://${DOMAIN}/${SECRET_SUB_PATH}/<username>"
    echo "  http://${DOMAIN}/${SECRET_SUB_PATH}/<username>"
    echo
    echo "Panel: https://${DOMAIN}/${SECRET_SUB_PATH}"
    echo "  Admin login: ${ADMIN_USER}"
    echo "  Admin password: ${ADMIN_PASSWORD}"
    echo
    echo "Node registry (clients): $SCRIPT_DIR/nodes.json"
    echo "After editing nodes.json restart: docker compose -f $DOCKER_COMPOSE_FILE restart subs-server"
}

main() {
    check_root
    install_missing_deps
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

    process_templates
    start_containers

    wait_for_ssl
    print_results
}

main
