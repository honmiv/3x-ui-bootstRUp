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
        prompt_input "$prompt" value
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
        prompt_input "$prompt" value
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

        if [[ "$already_chosen" -eq 1 || "$(is_port_busy "$port")" ]]; then
            ((port++))
            [[ "$port" -gt 65535 ]] && port=49152
        else
            break
        fi
    done
    USED_PORTS+=("$port")
    echo "$port"
}

apply_template_values() {
    local target_path="$1"
    sed -i \
       -e "s|{{DOMAIN}}|${DOMAIN}|g" \
       -e "s|{{XUI_WEB_BASE_PATH}}|${XUI_WEB_BASE_PATH}|g" \
       -e "s|{{XUI_SUB_PATH}}|${XUI_SUB_PATH}|g" \
       -e "s|{{XUI_WEB_PORT}}|${XUI_WEB_PORT}|g" \
       -e "s|{{XUI_SUB_PORT}}|${XUI_SUB_PORT}|g" \
       -e "s|{{CADDY_GLOBAL_INTERNAL_PORT}}|${CADDY_GLOBAL_INTERNAL_PORT}|g" \
       -e "s|{{TCP_REALITY_INBOUND_PORT}}|${TCP_REALITY_INBOUND_PORT}|g" \
       -e "s|{{XHTTP_REALITY_INBOUND_PORT}}|${XHTTP_REALITY_INBOUND_PORT}|g" \
       -e "s|{{TCP_REALITY_PRIVATE_KEY}}|${TCP_REALITY_PRIVATE_KEY}|g" \
       -e "s|{{TCP_REALITY_PUBLIC_KEY}}|${TCP_REALITY_PUBLIC_KEY}|g" \
       -e "s|{{TCP_REALITY_SHORT_IDS_JSON_ARRAY}}|${TCP_REALITY_SHORT_IDS_JSON_ARRAY}|g" \
       -e "s|{{XHTTP_REALITY_PRIVATE_KEY}}|${XHTTP_REALITY_PRIVATE_KEY}|g" \
       -e "s|{{XHTTP_REALITY_PUBLIC_KEY}}|${XHTTP_REALITY_PUBLIC_KEY}|g" \
       -e "s|{{XHTTP_REALITY_SHORT_IDS_JSON_ARRAY}}|${XHTTP_REALITY_SHORT_IDS_JSON_ARRAY}|g" \
       "$target_path"
}

generate_config() {
    local template_dir="$1"
    local target_dir="$2"
    local source_path relative_path target_relative target_path

    [[ -d "$template_dir" ]] || die "${MSG_CONFIG_ERR} $template_dir"
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

    success "$(printf "$MSG_CONFIG_SUCCESS" "$target_dir")"
}

show_spinner() {
    local counter=$1
    local spin_chars="/-\|"
    echo -ne "${spin_chars:$((counter % 4)):1}"
}

check_root() {
    [[ $EUID -eq 0 ]] || die "$MSG_NOT_ROOT"
}

get_package_manager() {
    if command -v apt-get &>/dev/null; then echo "apt";
    elif command -v dnf &>/dev/null; then echo "dnf";
    elif command -v yum &>/dev/null; then echo "yum";
    elif command -v pacman &>/dev/null; then echo "pacman";
    else echo "unknown"; fi
}

wait_for_lock() {
    local pm="$1"
    case "$pm" in
        apt)
            while pgrep -f "apt-get|dpkg" &>/dev/null; do
                warn "$MSG_APT_LOCKED"
                sleep 5
            done
            ;;
        dnf|yum)
            while pgrep -f "$pm|rpm" &>/dev/null; do
                warn "$MSG_DNF_LOCKED"
                sleep 5
            done
            ;;
        pacman)
            while [[ -f /var/lib/pacman/db.lck ]]; do
                warn "$MSG_PACMAN_LOCKED"
                sleep 5
            done
            ;;
    esac
}

install_packages() {
    local pm="$1"
    local packages="$2"
    info "$(printf "$MSG_DEPS_INSTALLING" "$pm" "$packages")"
    wait_for_lock "$pm"

    case "$pm" in
        apt)
            apt-get update && apt-get install -y curl jq openssl qrencode iproute2 procps coreutils gawk grep sed || die "$MSG_DEP_ERR"
            ;;
        dnf|yum)
            if ! $pm repolist | grep -q "epel"; then
                $pm install -y epel-release || true
                $pm makecache || true
            fi
            $pm install -y curl jq openssl qrencode iproute procps-ng coreutils gawk grep sed || die "$MSG_DEP_ERR"
            ;;
        pacman)
            pacman -Sy --noconfirm curl jq openssl qrencode iproute2 procps-ng coreutils gawk grep sed || die "$MSG_DEP_ERR"
            ;;
        *)
            die "$(printf "$MSG_UNSUPPORTED_PM" "${REQUIRED_CMDS[*]}")"
            ;;
    esac

    success "$MSG_DEPS_READY"
}

install_docker() {
    if ! command -v docker &>/dev/null; then
        info "$MSG_DOCKER_INSTALLING"
        if command -v pacman &>/dev/null; then
            pacman -S --noconfirm docker docker-compose || die "$MSG_DOCKER_ERR"
        else
            curl -fsSL https://get.docker.com | sh || die "$MSG_DOCKER_ERR"
        fi
    fi

    if command -v systemctl &>/dev/null; then
        systemctl is-active --quiet docker || systemctl start docker || die "$MSG_DOCKER_START_ERR"
        systemctl is-enabled --quiet docker || systemctl enable docker
    fi

    echo -e "${YELLOW}${MSG_DOCKER_MIRRORS}${NC}"
    mkdir -p /etc/docker && echo '{"registry-mirrors": ["https://dh-mirror.gitverse.ru"]}' | sudo tee /etc/docker/daemon.json > /dev/null

    success "$MSG_DOCKER_READY"
}

install_missing_deps() {
    section "$MSG_STEP_PREFLIGHT"

    local missing=()
    for cmd in "${REQUIRED_CMDS[@]}"; do
        command -v "$cmd" &>/dev/null || missing+=("$cmd")
    done

    if [[ ${#missing[@]} -gt 0 ]]; then
        local pm
        pm=$(get_package_manager)
        install_packages "$pm" "${missing[*]}"
    else
        success "$MSG_DEPS_READY"
    fi

    install_docker
}

reset_working_dir() {
    info "$MSG_WORKDIR_RESET"
    if [[ -f "$DOCKER_COMPOSE_FILE" ]]; then
        compose down
    fi
    rm -rf ./working && mkdir -p ./working
    success "$MSG_WORKDIR_READY"
}

select_language() {
    echo -e "${CYAN}== Language / Язык ==${NC}"
    prompt_choice "Choose language / Выберите язык [RU/en, Enter = RU]: " \
        "Invalid input. Enter RU, en, or press Enter. / Неверный ввод. Введите RU, en или нажмите Enter." \
        '^$|^[Rr][Uu]$|^[Ee][Nn]$' \
        LANG_CHOICE
    if [[ "$LANG_CHOICE" =~ ^[Ee][Nn]$ ]]; then LANG="EN"; else LANG="RU"; fi
}

load_messages() {
    if [[ "$LANG" == "RU" ]]; then
        MSG_DOCKER_MIRRORS="Настройка российского зеркала реестра Docker (резерв) из-за известных проблем с доступом к Docker Hub в России. Если у вас есть другое предпочтительное зеркало, вы можете изменить его в /root/3x-ui-bootstRUp/docker/daemon.json и повторно запустить установку"
        MSG_STEP_PREFLIGHT="Проверка окружения"
        MSG_DEPS_INSTALLING="Устанавливаю системные зависимости через %s: %s"
        MSG_DEPS_READY="Системные зависимости доступны."
        MSG_DOCKER_INSTALLING="Docker не найден. Устанавливаю Docker."
        MSG_DOCKER_READY="Docker доступен и служба запущена."
        MSG_WORKDIR_RESET="Подготавливаю рабочую директорию ./working."
        MSG_WORKDIR_READY="Рабочая директория подготовлена."
        MSG_API_START="Настройки панели"
        MSG_API_FETCHING="Получаю текущие настройки панели."
        MSG_API_FETCH_ERR="Не удалось получить текущие настройки панели."
        MSG_API_SENDING="Применяю адреса панели и подписок."
        MSG_API_UPDATE_ERR="Не удалось обновить настройки панели через API."
        MSG_API_UPDATE_SUCCESS="Настройки панели обновлены."
        MSG_SUB_FETCHING="Получаю ссылки клиента из подписки."
        MSG_SUB_FETCH_SUCCESS="Ссылки клиента получены."
        MSG_SUB_FETCH_ERR="Не удалось получить или декодировать данные подписки."
        MSG_SUB_EXTRACT_ERR="Не удалось извлечь TCP или XHTTP ссылку из подписки."
        MSG_NOT_ROOT="Запустите скрипт от имени root: sudo ./setup.sh"
        MSG_SUB_URL_TITLE="Подписка:"
        MSG_VLESS_TCP_URL_TITLE="VLESS TCP Reality:"
        MSG_VLESS_XHTTP_URL_TITLE="VLESS XHTTP Reality:"
        MSG_CLIENT_ERR="Не удалось добавить клиента в панель."
        MSG_APT_LOCKED="apt/dpkg занят другим процессом. Жду освобождения блокировки."
        MSG_DNF_LOCKED="dnf/rpm занят другим процессом. Жду освобождения блокировки."
        MSG_PACMAN_LOCKED="pacman заблокирован файлом db.lck. Жду освобождения блокировки."
        MSG_DEP_ERR="Не удалось установить системные зависимости."
        MSG_DOCKER_ERR="Не удалось установить Docker."
        MSG_DOCKER_START_ERR="Не удалось запустить службу Docker."
        MSG_UNSUPPORTED_PM="Неподдерживаемый пакетный менеджер. Установите вручную: %s"
        MSG_CLIENT_EMPTY="Имя клиента не может быть пустым."
        MSG_USERS_FILE_FOUND="Найден templates/users.yml. Создаю VPN-клиентов из файла."
        MSG_CLIENT_TITLE="Клиент:"
        MSG_CRED_TITLE="Учетные данные панели"
        MSG_REQ_LOGIN="Логин панели [Enter = admin]: "
        MSG_REQ_PASSWORD="Пароль панели [Enter = admin]: "
        MSG_REQ_CLIENT="Имя VPN-клиента: "
        MSG_SETUP_TITLE="Домен"
        MSG_DOMAIN_REQ="Введите ваше доменное имя (например, example.duckdns.org): "
        MSG_DOMAIN_EMPTY="Домен не может быть пустым."
        MSG_DOMAIN_INVALID="Некорректный домен: %s. Используйте ASCII-домен без протокола: латинские буквы, цифры, дефисы и точки."
        MSG_SEC_SECRET_TITLE="Секретная фраза"
        MSG_SEC_SECRET_DESC="Секретная фраза используется для генерации скрытых путей панели и подписок.\nEnter оставит случайную строку. Своя фраза нужна, если вы хотите получить те же endpoints\nдля панели и подписок на другом инстансе 3x-ui, например на другом сервере.\nИтоговые URL будут показаны в конце.\nВведите собственную фразу или примите случайно сгенерированную."
        MSG_SUGGEST_SECRET="Секретная фраза [Enter = %s]: "
        MSG_PORTS_GENERATING="Подбираю свободные внутренние порты."
        MSG_PORTS_SELECTED="Порты выбраны: панель %s, подписки %s, Caddy %s, TCP Reality %s, XHTTP Reality %s."
        MSG_KEYS_GENERATING="Генерирую Reality-ключи."
        MSG_KEYS_READY="Reality-ключи сгенерированы."
        MSG_PROCESSING="Генерация конфигурации"
        MSG_CONFIG_SUCCESS="Создан файл: %s"
        MSG_CONFIG_ERR="Шаблон не найден:"
        MSG_START_PANEL="Запуск панели 3x-ui"
        MSG_WAIT_3XUI="Жду готовности 3x-ui: %s"
        MSG_3XUI_WAIT_PROGRESS="[%s] 3x-ui: %ds / %ds"
        MSG_3XUI_TIMEOUT="3x-ui не ответил на %s за %d секунд."
        MSG_3XUI_READY="3x-ui ответил на %s за %d сек."
        MSG_FINAL_LAUNCH="Запуск Caddy"
        MSG_WAIT_SSL="Ожидание HTTPS-сертификата"
        MSG_SSL_TIMEOUT="Сертификат не стал доступен за %d секунд."
        MSG_SSL_LOGS_HINT="Проверьте логи Caddy с помощью: docker compose -f $DOCKER_COMPOSE_FILE --project-directory . logs caddy"
        MSG_SSL_VALIDATING="[%s] HTTPS на 443: %ds / %ds"
        MSG_SSL_SUCCESS="HTTPS-сертификат активен за %d сек."
        MSG_PANEL_USER_CONFIGURING="Настраиваю пользователя панели."
        MSG_PANEL_USER_READY="Пользователь панели настроен."
        MSG_INBOUND_ADDING="Добавляю входящее подключение: %s."
        MSG_CLIENT_ADDING="Добавляю VPN-клиента."
        MSG_CLIENT_READY="VPN-клиент добавлен."
        MSG_RESULTS_TITLE="Готово"
        MSG_SETUP_DONE="Установка завершена."
        MSG_CRED_PANEL="3x-UI панель доступна на:"
        MSG_QR_SUB="QR-код подписки"
        MSG_QR_TCP="QR-код VLESS TCP Reality"
        MSG_QR_XHTTP="QR-код VLESS XHTTP Reality"
        MSG_CASCADE_TITLE="Настройка каскада"
        MSG_CASCADE_REQ="Вы настраиваете каскад? [y/N, Enter = N]: "
        MSG_CASCADE_ERR="Неверный ввод. Введите y/n или нажмите Enter."
        MSG_NODE_TYPE_TITLE="Тип ноды"
        MSG_NODE_TYPE_REQ="Устанавливается ли панель НА зарубежную (1/freedom) или местную (2/proxy) ноду? [1/2, Enter = 1]: "
        MSG_NODE_TYPE_ERR="Неверный ввод. Введите 1, 2, freedom, proxy или нажмите Enter."
        MSG_XRAY_ROUTING_UPDATING="Настраиваю маршрутизацию XRay для зарубежной ноды (freedom)."
        MSG_FOREIGN_SUB_TITLE="Подписка зарубежной ноды"
        MSG_FOREIGN_SUB_REQ="Введите URL подписки (Subscription URL) с вашей зарубежной (Freedom) ноды (например: https://example.duckdns.org/subscriptions_path/client_name): "
        MSG_FOREIGN_SUB_ERR="URL подписки не может быть пустым. Введите корректный URL (начинающийся с http:// или https://):"
        MSG_XRAY_OUTBOUND_SUB_UPDATING="Добавляю подписку зарубежной ноды в XRay outbound subscriptions."
        MSG_XRAY_OUTBOUND_SUB_SUCCESS="Подписка зарубежной ноды успешно добавлена."
        MSG_XRAY_OUTBOUND_SUB_ERR="Не удалось добавить подписку зарубежной ноды."
    else
        MSG_DOCKER_MIRRORS="Configuring Russian Docker registry mirror (fallback) due to known issues with Docker Hub access in Russia. If you have a different preferred mirror, you can change it in /root/3x-ui-bootstRUp/docker/daemon.json and re-run installation"
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
        MSG_SEC_SECRET_DESC="The secret phrase is used to generate hidden panel and subscription paths.\nPress Enter to keep the generated random value. Enter your own phrase if you want the same\npanel and subscription endpoints on another 3x-ui instance, for example on another server.\nFinal URLs will be shown at the end.\nEnter a custom phrase or accept the randomly generated one."
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
        MSG_FOREIGN_SUB_REQ="Enter the subscription URL from your foreign (Freedom) node (e.g., https://example.duckdns.org/subscriptions_path/client_name): "
        MSG_FOREIGN_SUB_ERR="Subscription URL cannot be empty. Please enter a valid URL (starting with http:// or https://):"
        MSG_XRAY_OUTBOUND_SUB_UPDATING="Adding foreign node subscription to XRay outbound subscriptions."
        MSG_XRAY_OUTBOUND_SUB_SUCCESS="Foreign node outbound subscription added successfully."
        MSG_XRAY_OUTBOUND_SUB_ERR="Failed to add foreign node outbound subscription."
    fi
}

prompt_domain() {
    section "$MSG_SETUP_TITLE"
    DOMAIN=""
    while true; do
        prompt_required "$MSG_DOMAIN_REQ" "$MSG_DOMAIN_EMPTY" DOMAIN
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
    DEFAULT_SECRET_PHRASE=$(tr -dc '0-9' < /dev/urandom | head -c 16)
    section "$MSG_SEC_SECRET_TITLE"
    echo -e "${YELLOW}${MSG_SEC_SECRET_DESC}${NC}"
    prompt_secret_with_default "$(printf "$MSG_SUGGEST_SECRET" "$DEFAULT_SECRET_PHRASE")" "$DEFAULT_SECRET_PHRASE" SECRET_PHRASE
}

prompt_panel_credentials() {
    section "$MSG_CRED_TITLE"
    prompt_with_default "$MSG_REQ_LOGIN" "admin" USERNAME
    prompt_secret_with_default "$MSG_REQ_PASSWORD" "admin" USER_PASSWORD
    echo
}

prompt_client_name() {
    prompt_required "$MSG_REQ_CLIENT" "$MSG_CLIENT_EMPTY" CLIENT_EMAIL
}

read_users_file() {
    local users_file="./templates/users.yml"
    [[ -f "$users_file" ]] || return 0

    local section="" line name
    while IFS= read -r line || [[ -n "$line" ]]; do
        if [[ "$line" =~ ^[[:space:]]*([[:alpha:]][[:alnum:]_-]*):[[:space:]]*$ ]]; then
            section="${BASH_REMATCH[1]}"
        elif [[ "$line" =~ ^[[:space:]]*-[[:space:]]+(.*)$ ]]; then
            name="${BASH_REMATCH[1]}"
            name=$(printf '%s' "$name" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')
            [[ -z "$name" ]] && continue
            case "$section" in
                xhttp) XHTTP_CLIENTS+=("$name") ;;
                tcp)   TCP_CLIENTS+=("$name") ;;
            esac
        fi
    done < "$users_file"
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
    success "$MSG_KEYS_READY"
}

process_templates() {
    section "$MSG_PROCESSING"
    generate_config "./templates" "./working"
}

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

wait_for_3xui_tcp() {
    local port="$1"
    local target="tcp://127.0.0.1:${port}"
    wait_for_3xui_ready "$target" panel_exec bash -c "true >/dev/tcp/127.0.0.1/${port}"
}

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
    local payload
    payload=$(echo "$current_settings" | jq -r \
        --arg webPort "$XUI_WEB_PORT" \
        --arg webBasePath "/${XUI_WEB_BASE_PATH}/" \
        --arg subPort "$XUI_SUB_PORT" \
        --arg subPath "/${XUI_SUB_PATH}/" \
        --arg subURI "$sub_url_value" \
        '.obj
         | .webPort = ($webPort | tonumber)
         | .webBasePath = $webBasePath
         | .subPort = ($subPort | tonumber)
         | .subPath = $subPath
         | .subURI = $subURI
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

        local xray_json
        xray_json=$(jq -c . << 'EOF'
{
  "inbounds": [
    {
      "listen": "127.0.0.1",
      "port": 62789,
      "protocol": "tunnel",
      "settings": {
        "rewriteAddress": "127.0.0.1"
      },
      "tag": "api"
    }
  ],
  "outbounds": [
    {
      "tag": "direct",
      "protocol": "freedom",
      "settings": {
        "domainStrategy": "AsIs",
        "finalRules": [
          {
            "action": "block",
            "ip": [
              "geoip:private"
            ]
          },
          {
            "action": "allow"
          }
        ]
      }
    },
    {
      "tag": "blocked",
      "protocol": "blackhole",
      "settings": {}
    }
  ],
  "routing": {
    "rules": [
      {
        "type": "field",
        "inboundTag": [
          "api"
        ],
        "outboundTag": "api"
      },
      {
        "type": "field",
        "ip": [
          "geoip:private"
        ],
        "outboundTag": "blocked"
      },
      {
        "type": "field",
        "enabled": true,
        "protocol": [
          "bittorrent"
        ],
        "outboundTag": "blocked"
      },
      {
        "type": "field",
        "enabled": true,
        "ip": [
          "geoip:ru"
        ],
        "outboundTag": "blocked"
      },
      {
        "type": "field",
        "enabled": true,
        "domain": [
          "geosite:category-ru"
        ],
        "outboundTag": "blocked"
      }
    ],
    "domainStrategy": "AsIs"
  },
  "log": {
    "access": "none",
    "dnsLog": false,
    "error": "",
    "loglevel": "warning",
    "maskAddress": ""
  },
  "policy": {
    "system": {
      "statsInboundDownlink": true,
      "statsInboundUplink": true,
      "statsOutboundDownlink": false,
      "statsOutboundUplink": false
    },
    "levels": {
      "0": {
        "statsUserDownlink": true,
        "statsUserUplink": true
      }
    }
  },
  "api": {
    "services": [
      "HandlerService",
      "LoggerService",
      "StatsService",
      "RoutingService"
    ],
    "tag": "api"
  },
  "metrics": {
    "listen": "127.0.0.1:11111",
    "tag": "metrics_out"
  },
  "stats": {}
}
EOF
)
        echo "$xray_json" > ./working/xray_template.json
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
                sub_outbound_tag="sub1-vless-xhttp-reality-russian-node"
            fi

            local xray_proxy_json
            xray_proxy_json=$(jq -c \
                --arg xhttp_in "in-${XHTTP_REALITY_INBOUND_PORT}-xhttp" \
                --arg tcp_in "in-${TCP_REALITY_INBOUND_PORT}-tcp" \
                --arg sub_tag "$sub_outbound_tag" \
                '.routing.rules = [
                  {
                    "type": "field",
                    "inboundTag": ["api"],
                    "outboundTag": "api"
                  },
                  {
                    "type": "field",
                    "ip": ["geoip:private"],
                    "outboundTag": "blocked"
                  },
                  {
                    "type": "field",
                    "enabled": true,
                    "protocol": ["bittorrent"],
                    "outboundTag": "blocked"
                  },
                  {
                    "type": "field",
                    "enabled": true,
                    "ip": ["geoip:ru"],
                    "outboundTag": "direct"
                  },
                  {
                    "type": "field",
                    "enabled": true,
                    "domain": ["geosite:category-ru"],
                    "outboundTag": "direct"
                  },
                  {
                    "type": "field",
                    "enabled": true,
                    "inboundTag": [$tcp_in],
                    "outboundTag": $sub_tag
                  },
                  {
                    "type": "field",
                    "enabled": true,
                    "inboundTag": [$xhttp_in],
                    "outboundTag": $sub_tag
                  }
                ]' << 'EOF'
{
  "inbounds": [
    {
      "listen": "127.0.0.1",
      "port": 62789,
      "protocol": "tunnel",
      "settings": {
        "rewriteAddress": "127.0.0.1"
      },
      "tag": "api"
    }
  ],
  "outbounds": [
    {
      "tag": "direct",
      "protocol": "freedom",
      "settings": {
        "domainStrategy": "AsIs",
        "finalRules": [
          {
            "action": "block",
            "ip": [
              "geoip:private"
            ]
          },
          {
            "action": "allow"
          }
        ]
      }
    },
    {
      "tag": "blocked",
      "protocol": "blackhole",
      "settings": {}
    }
  ],
  "routing": {
    "rules": [],
    "domainStrategy": "AsIs"
  },
  "log": {
    "access": "none",
    "dnsLog": false,
    "error": "",
    "loglevel": "warning",
    "maskAddress": ""
  },
  "policy": {
    "system": {
      "statsInboundDownlink": true,
      "statsInboundUplink": true,
      "statsOutboundDownlink": false,
      "statsOutboundUplink": false
    },
    "levels": {
      "0": {
        "statsUserDownlink": true,
        "statsUserUplink": true
      }
    }
  },
  "api": {
    "services": [
      "HandlerService",
      "LoggerService",
      "StatsService",
      "RoutingService"
    ],
    "tag": "api"
  },
  "metrics": {
    "listen": "127.0.0.1:11111",
    "tag": "metrics_out"
  },
  "stats": {}
}
EOF
            )

            echo "$xray_proxy_json" > ./working/xray_template.json
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
    compose down "$service"
    compose up -d "$service"
}

start_3xui() {
    section "$MSG_START_PANEL"
    start_container "$PANEL_CONTAINER"
}

start_caddy() {
    section "$MSG_FINAL_LAUNCH"
    start_container "caddy"
}

wait_for_ssl() {
    local cert_timeout=300 cert_counter=0
    section "$MSG_WAIT_SSL"

    while ! curl -s --connect-timeout 2 --max-time 5 --resolve "${DOMAIN}:443:127.0.0.1" "https://${DOMAIN}:443" -o /dev/null; do
        if [[ "$cert_counter" -ge "$cert_timeout" ]]; then
            warn "$MSG_SSL_LOGS_HINT"
            die "$(printf "$MSG_SSL_TIMEOUT" "$cert_timeout")"
        fi
        printf "\r${YELLOW}${MSG_SSL_VALIDATING}${NC}" "$(show_spinner "$cert_counter")" "$cert_counter" "$cert_timeout"
        sleep 1
        ((cert_counter++))
    done

    printf "\r\033[K"
    success "$(printf "$MSG_SSL_SUCCESS" "$cert_counter")"
    echo
}

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

add_clients_from_file() {
    info "$MSG_USERS_FILE_FOUND"
    local email
    for email in "${XHTTP_CLIENTS[@]}"; do
        add_client "$email" "[2]"
        CREATED_CLIENTS+=("$email")
    done
    for email in "${TCP_CLIENTS[@]}"; do
        add_client "$email" "[1]"
        CREATED_CLIENTS+=("$email")
    done
}

build_sub_and_connect_urls() {
    local client_name_enc
    client_name_enc=$(url_encode "$CLIENT_EMAIL")

    CLIENT_SUBSCRIPTION_URL="https://${DOMAIN}/${XUI_SUB_PATH}/${client_name_enc}"

    info "$MSG_SUB_FETCHING"

    local raw_sub_data
    raw_sub_data=$(curl -sL -k -H "User-Agent: go-http-client/1.1" "$CLIENT_SUBSCRIPTION_URL" | base64 -d 2>/dev/null)

    if [[ -z "$raw_sub_data" ]]; then
        die "$MSG_SUB_FETCH_ERR"
    fi

    CLIENT_VLESS_TCP_URL=$(echo "$raw_sub_data" | grep "type=tcp" || true)
    CLIENT_VLESS_XHTTP_URL=$(echo "$raw_sub_data" | grep "type=xhttp" || true)

    if [[ -z "$CLIENT_VLESS_TCP_URL" && -z "$CLIENT_VLESS_XHTTP_URL" ]]; then
        die "$MSG_SUB_EXTRACT_ERR"
    fi

    success "$MSG_SUB_FETCH_SUCCESS"
}

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
    local email
    for email in "${CREATED_CLIENTS[@]}"; do
        CLIENT_EMAIL="$email"
        build_sub_and_connect_urls
        RESULTS_CLIENTS+=("$CLIENT_EMAIL")
        RESULTS_SUB_URLS+=("$CLIENT_SUBSCRIPTION_URL")
        RESULTS_TCP_URLS+=("$CLIENT_VLESS_TCP_URL")
        RESULTS_XHTTP_URLS+=("$CLIENT_VLESS_XHTTP_URL")
    done
}

print_results() {
    section "$MSG_RESULTS_TITLE"
    success "$MSG_SETUP_DONE"

    echo -e "\n${CYAN}${MSG_CRED_PANEL}${NC}"
    echo -e "  ${YELLOW}https://${DOMAIN}/${XUI_WEB_BASE_PATH}/${NC}"

    local i
    for i in "${!RESULTS_CLIENTS[@]}"; do
        echo -e "\n${CYAN}${MSG_CLIENT_TITLE}${NC} ${RESULTS_CLIENTS[$i]}"

        echo -e "\n${CYAN}${MSG_SUB_URL_TITLE}${NC}"
        echo -e "  ${YELLOW}${RESULTS_SUB_URLS[$i]}${NC}"
        echo -e "${CYAN}${MSG_QR_SUB}${NC}"
        qrencode -t ANSIUTF8 "${RESULTS_SUB_URLS[$i]}"

        if [[ -n "${RESULTS_TCP_URLS[$i]}" ]]; then
            echo -e "\n${CYAN}${MSG_VLESS_TCP_URL_TITLE}${NC}"
            echo -e "  ${YELLOW}${RESULTS_TCP_URLS[$i]}${NC}"
            echo -e "${CYAN}${MSG_QR_TCP}${NC}"
            qrencode -t ANSIUTF8 "${RESULTS_TCP_URLS[$i]}"
            echo
        fi

        if [[ -n "${RESULTS_XHTTP_URLS[$i]}" ]]; then
            echo -e "\n${CYAN}${MSG_VLESS_XHTTP_URL_TITLE}${NC}"
            echo -e "  ${YELLOW}${RESULTS_XHTTP_URLS[$i]}${NC}"
            echo -e "${CYAN}${MSG_QR_XHTTP}${NC}"
            qrencode -t ANSIUTF8 "${RESULTS_XHTTP_URLS[$i]}"
            echo
        fi
    done
}

main() {
    select_language
    load_messages
    check_root
    install_missing_deps
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
    read_users_file
    if [[ ${#XHTTP_CLIENTS[@]} -gt 0 || ${#TCP_CLIENTS[@]} -gt 0 ]]; then
        add_clients_from_file
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
