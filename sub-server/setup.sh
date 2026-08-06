#!/usr/bin/env bash
set -uo pipefail

readonly NC='\033[0m'
readonly GREEN='\033[0;32m'
readonly CYAN='\033[0;36m'
readonly YELLOW='\033[0;33m'
readonly RED='\033[0;31m'

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly DOCKER_COMPOSE_FILE="$SCRIPT_DIR/working/docker-compose/docker-compose.yml"

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
    docker compose -f "$DOCKER_COMPOSE_FILE" --project-directory "$SCRIPT_DIR" "$@"
}

is_valid_domain() {
    local domain="$1"
    [[ ${#domain} -le 253 ]] &&
        [[ "$domain" =~ ^[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?(\.[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$ ]]
}

check_root() {
    [[ $EUID -eq 0 ]] || die "Скрипт должен запускаться от root."
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
        info "Docker не найден. Устанавливаю Docker."
        if command -v pacman &>/dev/null; then
            pacman -S --noconfirm docker docker-compose || die "Не удалось установить Docker."
        else
            curl -fsSL https://get.docker.com | sh || die "Не удалось установить Docker."
        fi
    fi

    if command -v systemctl &>/dev/null; then
        systemctl is-active --quiet docker || systemctl start docker || die "Не удалось запустить Docker."
        systemctl is-enabled --quiet docker || systemctl enable docker
    fi

    docker compose version &>/dev/null || die "Плагин docker compose недоступен."
    success "Docker доступен."
}

install_missing_deps() {
    section "Проверка окружения"
    local missing=()
    for cmd in curl; do
        command -v "$cmd" &>/dev/null || missing+=("$cmd")
    done

    if [[ ${#missing[@]} -gt 0 ]]; then
        local pm
        pm=$(get_package_manager)
        case "$pm" in
            apt)     apt-get update && apt-get install -y curl iproute2 || die "Не удалось установить зависимости." ;;
            dnf|yum) $pm install -y curl iproute || die "Не удалось установить зависимости." ;;
            pacman)  pacman -Sy --noconfirm curl iproute2 || die "Не удалось установить зависимости." ;;
            *)       die "Не удалось определить менеджер пакетов." ;;
        esac
    fi

    install_docker
}

reset_working_dir() {
    info "Подготавливаю рабочую директорию ./working."
    if [[ -f "$DOCKER_COMPOSE_FILE" ]]; then
        compose down
    fi
    rm -rf "$SCRIPT_DIR/working" && mkdir -p "$SCRIPT_DIR/working"
    success "Рабочая директория подготовлена."
}

prompt_domain() {
    while :; do
        read -r -p "$(echo -e "${CYAN}[..]${NC} Введите домен (например sub.example.com): ")" DOMAIN
        if is_valid_domain "$DOMAIN"; then
            break
        fi
        warn "Некорректный домен, попробуйте снова."
    done
}

prompt_sub_path() {
    local default="subs"
    read -r -p "$(echo -e "${CYAN}[..]${NC} Путь-префикс (по умолчанию $default): ")" SECRET_SUB_PATH
    SECRET_SUB_PATH="${SECRET_SUB_PATH:-$default}"
    SECRET_SUB_PATH="${SECRET_SUB_PATH#/}"
    SECRET_SUB_PATH="${SECRET_SUB_PATH%/}"
}

prompt_subscription_urls() {
    RUSSIAN_SUB_URL=""
    FOREIGN_SUB_URL=""
    read -r -p "$(echo -e "${CYAN}[..]${NC} Есть ли русская нода? (y/N): ")" has_ru
    if [[ "$has_ru" =~ ^[YyДд]$ ]]; then
        read -r -p "$(echo -e "${CYAN}[..]${NC} URL подписок русской ноды: ")" RUSSIAN_SUB_URL
        RUSSIAN_SUB_URL="${RUSSIAN_SUB_URL%/}"
    fi
    read -r -p "$(echo -e "${CYAN}[..]${NC} URL подписок нерусской ноды: ")" FOREIGN_SUB_URL
    FOREIGN_SUB_URL="${FOREIGN_SUB_URL%/}"
    [[ -n "$RUSSIAN_SUB_URL" || -n "$FOREIGN_SUB_URL" ]] || die "Не указан ни один URL подписок."
}

apply_template_values() {
    local target_path="$1"
    sed -i \
       -e "s|{{DOMAIN}}|${DOMAIN}|g" \
       -e "s|{{SECRET_SUB_PATH}}|${SECRET_SUB_PATH}|g" \
       -e "s|{{RUSSIAN_SUB_URL}}|${RUSSIAN_SUB_URL}|g" \
       -e "s|{{FOREIGN_SUB_URL}}|${FOREIGN_SUB_URL}|g" \
       "$target_path"
}

generate_config() {
    local template_dir="$1"
    local target_dir="$2"
    local source_path relative_path target_relative target_path

    [[ -d "$template_dir" ]] || die "Шаблоны не найдены: $template_dir"
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

    success "Конфиги сгенерированы в $target_dir"
}

process_templates() {
    section "Генерация конфигов"
    generate_config "$SCRIPT_DIR/templates" "$SCRIPT_DIR/working"
}

start_containers() {
    section "Запуск контейнеров"
    compose up -d --build
}

wait_for_ssl() {
    local cert_timeout=300 cert_counter=0
    section "Ожидание SSL-сертификата"

    while ! curl -s --connect-timeout 2 --max-time 5 --resolve "${DOMAIN}:443:127.0.0.1" "https://${DOMAIN}:443" -o /dev/null; do
        if [[ "$cert_counter" -ge "$cert_timeout" ]]; then
            warn "Проверьте логи: docker compose -f $DOCKER_COMPOSE_FILE logs caddy"
            die "SSL-сертификат не получен за $cert_timeout секунд."
        fi
        printf "\r${YELLOW}[..]${NC} Проверка SSL-сертификата %s %s/%s" "$(show_spinner "$cert_counter")" "$cert_counter" "$cert_timeout"
        sleep 1
        ((cert_counter++))
    done
    echo
    success "SSL-сертификат получен."
}

show_spinner() {
    local counter=$1
    local spin_chars="/-\|"
    echo -ne "${spin_chars:$((counter % 4)):1}"
}

print_results() {
    section "Готово"
    echo "Подписки доступны по адресу:"
    echo "  https://${DOMAIN}/${SECRET_SUB_PATH}/<username>"
    echo "  http://${DOMAIN}/${SECRET_SUB_PATH}/<username>"
    echo
    echo "Список клиентов (proxy/freedom): $SCRIPT_DIR/subs.yml"
    echo "После правки subs.yml перезапустите: docker compose -f $DOCKER_COMPOSE_FILE restart subs-server"
}

main() {
    check_root
    install_missing_deps
    reset_working_dir

    prompt_domain
    prompt_sub_path
    prompt_subscription_urls

    process_templates
    start_containers

    wait_for_ssl
    print_results
}

main