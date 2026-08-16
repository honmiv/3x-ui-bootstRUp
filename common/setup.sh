#!/usr/bin/env bash
# Shared remote bootstrap helpers, sourced by panel/setup.sh and sub-server/setup.sh.
#
# These functions run on the remote VPS. All user-facing strings read
# ${MSG_*:-default-en} so a consumer can override them for localization
# (panel/setup.sh sets MSG_* in load_messages(); sub-server/setup.sh keeps
# the English defaults). Logging helpers (die/info/success/warn/section) and
# the color variables must be provided by the sourcing script.

check_root() {
    [[ $EUID -eq 0 ]] || die "${MSG_NOT_ROOT:-Run this script as root: sudo ./setup.sh}"
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
            local attempts=0
            while pgrep -f "apt-get|dpkg" &>/dev/null; do
                ((attempts++))
                if [[ $attempts -gt 300 ]]; then die "Timeout waiting for apt"; fi
                warn "${MSG_APT_LOCKED:-apt/dpkg is locked by another process. Waiting.}"
                sleep 5
            done
            ;;
        dnf|yum)
            local attempts=0
            while pgrep -f "$pm|rpm" &>/dev/null; do
                ((attempts++))
                if [[ $attempts -gt 300 ]]; then die "Timeout waiting for dnf"; fi
                warn "${MSG_DNF_LOCKED:-dnf/rpm is locked by another process. Waiting.}"
                sleep 5
            done
            ;;
        pacman)
            local attempts=0
            while [[ -f /var/lib/pacman/db.lck ]]; do
                ((attempts++))
                if [[ $attempts -gt 300 ]]; then die "Timeout waiting for pacman"; fi
                warn "${MSG_PACMAN_LOCKED:-pacman is locked by db.lck. Waiting.}"
                sleep 5
            done
            ;;
    esac
}

install_packages() {
    local pm="$1"
    local packages="$2"
    local required_cmds="$3"
    info "$(printf "${MSG_DEPS_INSTALLING:-Installing system dependencies with %s: %s}" "$pm" "$packages")"
    wait_for_lock "$pm"

    case "$pm" in
        apt)
            apt-get update && apt-get install -y $packages || die "${MSG_DEP_ERR:-Failed to install system dependencies.}"
            ;;
        dnf|yum)
            if ! $pm repolist | grep -q "epel"; then
                $pm install -y epel-release || true
                $pm makecache || true
            fi
            $pm install -y $packages || die "${MSG_DEP_ERR:-Failed to install system dependencies.}"
            ;;
        pacman)
            pacman -Sy --noconfirm $packages || die "${MSG_DEP_ERR:-Failed to install system dependencies.}"
            ;;
        *)
            die "$(printf "${MSG_UNSUPPORTED_PM:-Unsupported package manager. Install manually: %s}" "$required_cmds")"
            ;;
    esac
}

restart_docker() {
    if command -v systemctl &>/dev/null; then
        systemctl restart docker
    elif command -v rc-service &>/dev/null; then
        rc-service docker restart
    elif command -v service &>/dev/null; then
        service docker restart
    else
        false
    fi
}

install_docker() {
    if ! command -v docker &>/dev/null; then
        info "${MSG_DOCKER_INSTALLING:-Docker is not installed. Installing Docker.}"
        wait_for_lock "$(get_package_manager)"
        if command -v pacman &>/dev/null; then
            pacman -S --noconfirm docker docker-compose || die "${MSG_DOCKER_ERR:-Failed to install Docker.}"
        else
            curl -fsSL https://get.docker.com | sh || die "${MSG_DOCKER_ERR:-Failed to install Docker.}"
        fi
    fi

    if command -v systemctl &>/dev/null; then
        systemctl is-active --quiet docker || systemctl start docker || die "${MSG_DOCKER_START_ERR:-Failed to start Docker service.}"
        systemctl is-enabled --quiet docker || systemctl enable docker
    fi

    docker compose version &>/dev/null || die "${MSG_DOCKER_COMPOSE_ERR:-Docker compose plugin unavailable.}"

    if ! grep -q "dh-mirror.gitverse.ru" /etc/docker/daemon.json 2>/dev/null; then
        echo -e "${YELLOW}${MSG_DOCKER_MIRRORS:-Configuring Docker registry mirror fallback}${NC}"
        mkdir -p /etc/docker && cp "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/daemon.json" /etc/docker/daemon.json
        restart_docker || die "${MSG_DOCKER_RESTART_ERR:-Failed to restart Docker service to apply registry mirror.}"
    fi

    success "${MSG_DOCKER_READY:-Docker is available and running.}"
}

# install_missing_deps <required_cmds> <pkg_apt> <pkg_dnf> <pkg_pacman>
# Installs any missing system commands, then bootstraps Docker (which applies
# the registry mirror and restarts the daemon so it takes effect).
install_missing_deps() {
    local required="$1"
    local pkg_apt="$2"
    local pkg_dnf="$3"
    local pkg_pacman="$4"

    section "${MSG_STEP_PREFLIGHT:-Environment check}"

    local missing=()
    local cmd
    for cmd in $required; do
        command -v "$cmd" &>/dev/null || missing+=("$cmd")
    done

    if [[ ${#missing[@]} -gt 0 ]]; then
        local pm pkg
        pm=$(get_package_manager)
        case "$pm" in
            apt)     pkg="$pkg_apt" ;;
            dnf|yum) pkg="$pkg_dnf" ;;
            pacman)  pkg="$pkg_pacman" ;;
            *)       pkg="" ;;
        esac
        install_packages "$pm" "$pkg" "$required"
    else
        success "${MSG_DEPS_READY:-System dependencies are available.}"
    fi

    install_docker
}
