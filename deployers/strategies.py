"""Deployment mode strategies (Фаза G1).

Каждый режим/группа режимов: валидатор + runner. Поведение идентично бывшим
if/elif в `ssh_deployer.py` — это data-driven реестр без изменения логики.
"""

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, Optional, Tuple

# Импорт ленивый (внутри функций) — избегаем цикла: ssh_deployer импортирует
# этот модуль внутри validate_deployment_config/run_deployment.
_CALLBACK = Callable[[str, str], None]
_CANCEL = Optional[Callable[[], bool]]


@dataclass(frozen=True)
class RunContext:
    bundle_dir: Optional[str]
    change_ssh_port: bool
    new_ssh_port: Optional[int]
    updated_ssh_ports: Dict[str, int]
    prepare_decoy_files: Callable[[str, str], Optional[Dict[str, bytes]]]


@dataclass(frozen=True)
class ModeStrategy:
    modes: Tuple[str, ...]
    validate: Callable[[Dict[str, Any]], Optional[str]]
    run: Callable[[Dict[str, Any], _CALLBACK, _CANCEL, RunContext], Awaitable[Tuple[bool, Dict[str, Any]]]]


def _check_ssh(config: Dict[str, Any], prefix: str, label: str) -> Optional[str]:
    from ssh_deployer import ServerConnection
    return ServerConnection.from_config(config, prefix).validate(label)


def _validate_sub_server(config: Dict[str, Any]) -> Optional[str]:
    err = _check_ssh(config, "sub_vps", "Сервера подписок")
    if err:
        return err
    if not str(config.get("sub_secret_path", "") or "").strip():
        return "Укажите префикс пути подписок Сервера подписок"
    if not str(config.get("sub_admin_user", "") or "").strip():
        return "Укажите логин админа Сервера подписок"
    if not str(config.get("sub_admin_password", "") or "").strip():
        return "Укажите пароль админа Сервера подписок"
    return None


# --- Валидаторы ------------------------------------------------------------

def _validate_single_group(config: Dict[str, Any]) -> Optional[str]:
    err = _check_ssh(config, "vps", "VPS сервера")
    if err:
        return err
    if not str(config.get("xui_username", "") or "").strip():
        return "Укажите логин админа 3X-UI"
    if not str(config.get("xui_password", "") or "").strip():
        return "Укажите пароль админа 3X-UI"
    if not str(config.get("sub_secret", "") or "").strip():
        return "Укажите секретную фразу панели"
    mode = (config.get("deploy_mode", "") or "").strip()
    if mode == "proxy_only":
        if not str(config.get("foreign_sub_url", "") or "").strip():
            return "Укажите ссылку подписки Freedom ноды (FOREIGN_SUB_URL)"
    elif mode in ["freedom_only", "freedom_sub"]:
        tcp = str(config.get("client_tcp_list", "") or "").strip()
        xhttp = str(config.get("client_xhttp_list", "") or "").strip()
        if not tcp and not xhttp:
            return "Укажите хотя бы одного клиента (VLESS TCP или VLESS XHTTP)"
    if mode == "freedom_sub":
        err = _validate_sub_server(config)
        if err:
            return err
    return None


def _validate_cascade_group(config: Dict[str, Any]) -> Optional[str]:
    err = _check_ssh(config, "freedom", "Freedom Node")
    if err:
        return err
    if not str(config.get("freedom_xui_username", "") or "").strip():
        return "Укажите логин админа Freedom 3X-UI"
    if not str(config.get("freedom_xui_password", "") or "").strip():
        return "Укажите пароль админа Freedom 3X-UI"
    if not str(config.get("freedom_sub_secret", "") or "").strip():
        return "Укажите секретную фразу Freedom панели"

    err = _check_ssh(config, "proxy", "Proxy Node")
    if err:
        return err
    if not str(config.get("proxy_xui_username", "") or "").strip():
        return "Укажите логин админа Proxy 3X-UI"
    if not str(config.get("proxy_xui_password", "") or "").strip():
        return "Укажите пароль админа Proxy 3X-UI"
    if not str(config.get("proxy_sub_secret", "") or "").strip():
        return "Укажите секретную фразу Proxy панели"

    mode = (config.get("deploy_mode", "") or "").strip()
    if mode == "cascade_sub":
        err = _validate_sub_server(config)
        if err:
            return err
    return None


def _validate_sub_only(config: Dict[str, Any]) -> Optional[str]:
    err = _validate_sub_server(config)
    if err:
        return err
    sub_rus = str(config.get("sub_russian_url", "") or "").strip()
    sub_for = str(config.get("sub_foreign_url", "") or "").strip()
    if not sub_rus and not sub_for:
        return "Укажите хотя бы одну ссылку подписки (RUSSIAN_SUB_URL или FOREIGN_SUB_URL)"
    return None


def _validate_backup(config: Dict[str, Any]) -> Optional[str]:
    return _check_ssh(config, "backup_vps", "сервера для бэкапа")


def _validate_recovery(config: Dict[str, Any]) -> Optional[str]:
    err = _check_ssh(config, "recovery_vps", "сервера для восстановления")
    if err:
        return err
    if not str(config.get("recovery_backup_file", "") or "").strip():
        return "Выберите архив бэкапа для восстановления"
    if not str(config.get("recovery_xui_username", "") or "").strip():
        return "Укажите логин админа 3X-UI из бэкапа"
    if not str(config.get("recovery_xui_password", "") or "").strip():
        return "Укажите пароль админа 3X-UI из бэкапа"
    return None


def _validate_update_group(config: Dict[str, Any]) -> Optional[str]:
    err = _check_ssh(config, "update_vps", "сервера для обновления/перезапуска")
    if err:
        return err
    mode = (config.get("deploy_mode", "") or "").strip()
    if mode in ["update_3xui"]:
        ver = str(config.get("update_xui_version", "") or config.get("xui_version", "") or "").strip()
        if not ver:
            return "Укажите версию 3X-UI для обновления"
    return None


def _validate_sub_ops_group(config: Dict[str, Any]) -> Optional[str]:
    err = _check_ssh(config, "sub_vps", "Сервера подписок")
    if err:
        return err
    mode = (config.get("deploy_mode", "") or "").strip()
    if mode == "rollback_sub" and not str(config.get("rollback_sub_backup_file", "") or "").strip():
        return "Выберите архив бэкапа Сервера подписок"
    return None


# --- Runners ---------------------------------------------------------------

async def _run_backup(config: Dict[str, Any], log: _CALLBACK, cancel_check: _CANCEL, ctx: RunContext) -> Tuple[bool, Dict[str, Any]]:
    from deployers.maintenance import deploy_backup
    return await deploy_backup(config, log, cancel_check)


async def _run_recovery(config: Dict[str, Any], log: _CALLBACK, cancel_check: _CANCEL, ctx: RunContext) -> Tuple[bool, Dict[str, Any]]:
    from deployers.maintenance import deploy_recovery
    return await deploy_recovery(config, log, cancel_check)


async def _run_update(config: Dict[str, Any], log: _CALLBACK, cancel_check: _CANCEL, ctx: RunContext) -> Tuple[bool, Dict[str, Any]]:
    from deployers.maintenance import deploy_update
    return await deploy_update(
        config, log, cancel_check,
        change_ssh_port=ctx.change_ssh_port,
        new_ssh_port=ctx.new_ssh_port,
        updated_ssh_ports=ctx.updated_ssh_ports,
        prepare_decoy_files=ctx.prepare_decoy_files,
    )


async def _run_restart(config: Dict[str, Any], log: _CALLBACK, cancel_check: _CANCEL, ctx: RunContext) -> Tuple[bool, Dict[str, Any]]:
    from deployers.maintenance import deploy_restart
    return await deploy_restart(config, log, cancel_check)


async def _run_sub_ops(config: Dict[str, Any], log: _CALLBACK, cancel_check: _CANCEL, ctx: RunContext) -> Tuple[bool, Dict[str, Any]]:
    from deployers.maintenance import deploy_sub_ops
    return await deploy_sub_ops(
        config, log, cancel_check,
        change_ssh_port=ctx.change_ssh_port,
        new_ssh_port=ctx.new_ssh_port,
        updated_ssh_ports=ctx.updated_ssh_ports,
        prepare_decoy_files=ctx.prepare_decoy_files,
    )


async def _run_sub_only(config: Dict[str, Any], log: _CALLBACK, cancel_check: _CANCEL, ctx: RunContext) -> Tuple[bool, Dict[str, Any]]:
    from deployers.sub_deployer import deploy_sub_only
    return await deploy_sub_only(
        config, log, cancel_check,
        bundle_dir=ctx.bundle_dir,
        change_ssh_port=ctx.change_ssh_port,
        new_ssh_port=ctx.new_ssh_port,
        updated_ssh_ports=ctx.updated_ssh_ports,
        prepare_decoy_files=ctx.prepare_decoy_files,
    )


async def _run_single(config: Dict[str, Any], log: _CALLBACK, cancel_check: _CANCEL, ctx: RunContext) -> Tuple[bool, Dict[str, Any]]:
    from deployers.panel_deployer import deploy_single
    return await deploy_single(
        config, log, cancel_check,
        bundle_dir=ctx.bundle_dir,
        change_ssh_port=ctx.change_ssh_port,
        new_ssh_port=ctx.new_ssh_port,
        updated_ssh_ports=ctx.updated_ssh_ports,
        prepare_decoy_files=ctx.prepare_decoy_files,
    )


async def _run_freedom_sub(config: Dict[str, Any], log: _CALLBACK, cancel_check: _CANCEL, ctx: RunContext) -> Tuple[bool, Dict[str, Any]]:
    from deployers.panel_deployer import deploy_freedom_sub
    return await deploy_freedom_sub(
        config, log, cancel_check,
        bundle_dir=ctx.bundle_dir,
        change_ssh_port=ctx.change_ssh_port,
        new_ssh_port=ctx.new_ssh_port,
        updated_ssh_ports=ctx.updated_ssh_ports,
        prepare_decoy_files=ctx.prepare_decoy_files,
    )


async def _run_cascade(config: Dict[str, Any], log: _CALLBACK, cancel_check: _CANCEL, ctx: RunContext) -> Tuple[bool, Dict[str, Any]]:
    from deployers.panel_deployer import deploy_cascade
    return await deploy_cascade(
        config, log, cancel_check,
        bundle_dir=ctx.bundle_dir,
        change_ssh_port=ctx.change_ssh_port,
        new_ssh_port=ctx.new_ssh_port,
        updated_ssh_ports=ctx.updated_ssh_ports,
        prepare_decoy_files=ctx.prepare_decoy_files,
    )


# --- Реестр (mode -> стратегия) -------------------------------------------

STRATEGIES: Dict[str, ModeStrategy] = {}
for _s in [
    ModeStrategy(("single", "proxy_only", "freedom_only", "freedom_component"), _validate_single_group, _run_single),
    ModeStrategy(("freedom_sub",), _validate_single_group, _run_freedom_sub),
    ModeStrategy(("cascade", "cascade_sub"), _validate_cascade_group, _run_cascade),
    ModeStrategy(("sub_only",), _validate_sub_only, _run_sub_only),
    ModeStrategy(("backup",), _validate_backup, _run_backup),
    ModeStrategy(("recovery",), _validate_recovery, _run_recovery),
    ModeStrategy(("update_3xui",), _validate_update_group, _run_update),
    ModeStrategy(("restart_panel", "restart_server"), _validate_update_group, _run_restart),
    ModeStrategy(("restart_sub", "update_sub", "backup_sub", "rollback_sub"), _validate_sub_ops_group, _run_sub_ops),
]:
    for _m in _s.modes:
        STRATEGIES[_m] = _s


# --- Фронтенд-схема валидации (G2) ----------------------------------------
#
# Декларативная схема обязательных полей для форм. Отдаётся через
# GET /api/modes; `forms.js` строит из неё REQUIRED_FIELDS динамически
# вместо хардкода. Формат совпадает со старым JS-массивом 1:1:
#   - {"kind": "group", "mode": "any"/"all"/"exactly_one", "fields": [...],
#      "step": N, "modes": [...], "message": "..."}
#   - {"kind": "field", "id": "...", "step": N, "modes": [...], "message": "...",
#      "authField": id_селектора, "authValue": "password"|"key"}  (SSH creds: when-условие)

MODES_SCHEMA: list = [
    {"kind": "group", "mode": "any", "fields": ["sub_russian_url", "sub_foreign_url"],
     "step": 3, "modes": ["sub_only"],
     "message": "Укажите хотя бы одну ссылку подписки (RUSSIAN_SUB_URL или FOREIGN_SUB_URL)"},
    {"kind": "group", "mode": "any", "fields": ["client_tcp_list", "client_xhttp_list"],
     "step": 3, "modes": ["freedom_only", "freedom_sub"],
     "message": "Укажите хотя бы одного клиента (VLESS TCP или VLESS XHTTP)"},

    {"kind": "field", "id": "vps_host", "step": 2, "modes": ["single", "proxy_only", "freedom_only", "freedom_component", "freedom_sub"], "message": "Укажите домен VPS сервера"},
    {"kind": "field", "id": "vps_port", "step": 2, "modes": ["single", "proxy_only", "freedom_only", "freedom_component", "freedom_sub"], "message": "Укажите SSH порт VPS сервера"},
    {"kind": "field", "id": "vps_user", "step": 2, "modes": ["single", "proxy_only", "freedom_only", "freedom_component", "freedom_sub"], "message": "Укажите SSH пользователя VPS сервера"},
    {"kind": "field", "id": "vps_password", "step": 2, "modes": ["single", "proxy_only", "freedom_only", "freedom_component", "freedom_sub"], "authField": "vps_auth_type", "authValue": "password", "message": "Укажите SSH пароль VPS сервера"},
    {"kind": "field", "id": "vps_key", "step": 2, "modes": ["single", "proxy_only", "freedom_only", "freedom_component", "freedom_sub"], "authField": "vps_auth_type", "authValue": "key", "message": "Укажите SSH ключ VPS сервера"},

    {"kind": "field", "id": "freedom_host", "step": 2, "modes": ["cascade", "cascade_sub"], "message": "Укажите домен Freedom Node"},
    {"kind": "field", "id": "freedom_port", "step": 2, "modes": ["cascade", "cascade_sub"], "message": "Укажите SSH порт Freedom Node"},
    {"kind": "field", "id": "freedom_user", "step": 2, "modes": ["cascade", "cascade_sub"], "message": "Укажите SSH пользователя Freedom Node"},
    {"kind": "field", "id": "freedom_password", "step": 2, "modes": ["cascade", "cascade_sub"], "authField": "freedom_auth_type", "authValue": "password", "message": "Укажите SSH пароль Freedom Node"},
    {"kind": "field", "id": "freedom_key", "step": 2, "modes": ["cascade", "cascade_sub"], "authField": "freedom_auth_type", "authValue": "key", "message": "Укажите SSH ключ Freedom Node"},

    {"kind": "field", "id": "proxy_host", "step": 2, "modes": ["cascade", "cascade_sub"], "message": "Укажите домен Proxy Node"},
    {"kind": "field", "id": "proxy_port", "step": 2, "modes": ["cascade", "cascade_sub"], "message": "Укажите SSH порт Proxy Node"},
    {"kind": "field", "id": "proxy_user", "step": 2, "modes": ["cascade", "cascade_sub"], "message": "Укажите SSH пользователя Proxy Node"},
    {"kind": "field", "id": "proxy_password", "step": 2, "modes": ["cascade", "cascade_sub"], "authField": "proxy_auth_type", "authValue": "password", "message": "Укажите SSH пароль Proxy Node"},
    {"kind": "field", "id": "proxy_key", "step": 2, "modes": ["cascade", "cascade_sub"], "authField": "proxy_auth_type", "authValue": "key", "message": "Укажите SSH ключ Proxy Node"},

    {"kind": "field", "id": "sub_vps_host", "step": 2, "modes": ["sub_only", "cascade_sub", "freedom_sub", "restart_sub", "update_sub", "backup_sub", "rollback_sub"], "message": "Укажите домен Сервера подписок"},
    {"kind": "field", "id": "sub_vps_port", "step": 2, "modes": ["sub_only", "cascade_sub", "freedom_sub", "restart_sub", "update_sub", "backup_sub", "rollback_sub"], "message": "Укажите SSH порт Сервера подписок"},
    {"kind": "field", "id": "sub_vps_user", "step": 2, "modes": ["sub_only", "cascade_sub", "freedom_sub", "restart_sub", "update_sub", "backup_sub", "rollback_sub"], "message": "Укажите SSH пользователя Сервера подписок"},
    {"kind": "field", "id": "sub_vps_password", "step": 2, "modes": ["sub_only", "cascade_sub", "freedom_sub", "restart_sub", "update_sub", "backup_sub", "rollback_sub"], "authField": "sub_auth_type", "authValue": "password", "message": "Укажите SSH пароль Сервера подписок"},
    {"kind": "field", "id": "sub_vps_key", "step": 2, "modes": ["sub_only", "cascade_sub", "freedom_sub", "restart_sub", "update_sub", "backup_sub", "rollback_sub"], "authField": "sub_auth_type", "authValue": "key", "message": "Укажите SSH ключ Сервера подписок"},

    {"kind": "field", "id": "backup_vps_host", "step": 2, "modes": ["backup"], "message": "Укажите домен сервера для бэкапа"},
    {"kind": "field", "id": "backup_vps_port", "step": 2, "modes": ["backup"], "message": "Укажите SSH порт сервера для бэкапа"},
    {"kind": "field", "id": "backup_vps_user", "step": 2, "modes": ["backup"], "message": "Укажите SSH пользователя сервера для бэкапа"},
    {"kind": "field", "id": "backup_vps_password", "step": 2, "modes": ["backup"], "authField": "backup_auth_type", "authValue": "password", "message": "Укажите SSH пароль сервера для бэкапа"},
    {"kind": "field", "id": "backup_vps_key", "step": 2, "modes": ["backup"], "authField": "backup_auth_type", "authValue": "key", "message": "Укажите SSH ключ сервера для бэкапа"},

    {"kind": "field", "id": "recovery_vps_host", "step": 2, "modes": ["recovery"], "message": "Укажите домен сервера для восстановления"},
    {"kind": "field", "id": "recovery_vps_port", "step": 2, "modes": ["recovery"], "message": "Укажите SSH порт сервера для восстановления"},
    {"kind": "field", "id": "recovery_vps_user", "step": 2, "modes": ["recovery"], "message": "Укажите SSH пользователя сервера для восстановления"},
    {"kind": "field", "id": "recovery_vps_password", "step": 2, "modes": ["recovery"], "authField": "recovery_auth_type", "authValue": "password", "message": "Укажите SSH пароль сервера для восстановления"},
    {"kind": "field", "id": "recovery_vps_key", "step": 2, "modes": ["recovery"], "authField": "recovery_auth_type", "authValue": "key", "message": "Укажите SSH ключ сервера для восстановления"},

    {"kind": "field", "id": "update_vps_host", "step": 2, "modes": ["update_3xui", "restart_panel", "restart_server"], "message": "Укажите домен сервера для обновления/перезапуска"},
    {"kind": "field", "id": "update_vps_port", "step": 2, "modes": ["update_3xui", "restart_panel", "restart_server"], "message": "Укажите SSH порт сервера для обновления/перезапуска"},
    {"kind": "field", "id": "update_vps_user", "step": 2, "modes": ["update_3xui", "restart_panel", "restart_server"], "message": "Укажите SSH пользователя сервера для обновления/перезапуска"},
    {"kind": "field", "id": "update_vps_password", "step": 2, "modes": ["update_3xui", "restart_panel", "restart_server"], "authField": "update_auth_type", "authValue": "password", "message": "Укажите SSH пароль сервера для обновления/перезапуска"},
    {"kind": "field", "id": "update_vps_key", "step": 2, "modes": ["update_3xui", "restart_panel", "restart_server"], "authField": "update_auth_type", "authValue": "key", "message": "Укажите SSH ключ сервера для обновления/перезапуска"},

    {"kind": "field", "id": "xui_username", "step": 3, "modes": ["single", "proxy_only", "freedom_only", "freedom_component", "freedom_sub"], "message": "Укажите логин админа 3X-UI"},
    {"kind": "field", "id": "xui_password", "step": 3, "modes": ["single", "proxy_only", "freedom_only", "freedom_component", "freedom_sub"], "message": "Укажите пароль админа 3X-UI"},
    {"kind": "field", "id": "sub_secret", "step": 3, "modes": ["single", "proxy_only", "freedom_only", "freedom_component", "freedom_sub"], "message": "Укажите секретную фразу панели"},

    {"kind": "field", "id": "freedom_xui_username", "step": 3, "modes": ["cascade", "cascade_sub"], "message": "Укажите логин админа Freedom 3X-UI"},
    {"kind": "field", "id": "freedom_xui_password", "step": 3, "modes": ["cascade", "cascade_sub"], "message": "Укажите пароль админа Freedom 3X-UI"},
    {"kind": "field", "id": "freedom_sub_secret", "step": 3, "modes": ["cascade", "cascade_sub"], "message": "Укажите секретную фразу Freedom панели"},

    {"kind": "field", "id": "proxy_xui_username", "step": 3, "modes": ["cascade", "cascade_sub"], "message": "Укажите логин админа Proxy 3X-UI"},
    {"kind": "field", "id": "proxy_xui_password", "step": 3, "modes": ["cascade", "cascade_sub"], "message": "Укажите пароль админа Proxy 3X-UI"},
    {"kind": "field", "id": "proxy_sub_secret", "step": 3, "modes": ["cascade", "cascade_sub"], "message": "Укажите секретную фразу Proxy панели"},

    {"kind": "field", "id": "sub_secret_path", "step": 3, "modes": ["sub_only", "cascade_sub", "freedom_sub"], "message": "Укажите секретную фразу Сервера подписок"},
    {"kind": "field", "id": "sub_admin_user", "step": 3, "modes": ["sub_only", "cascade_sub", "freedom_sub"], "message": "Укажите логин админа Сервера подписок"},
    {"kind": "field", "id": "sub_admin_password", "step": 3, "modes": ["sub_only", "cascade_sub", "freedom_sub"], "message": "Укажите пароль админа Сервера подписок"},

    {"kind": "field", "id": "foreign_sub_url", "step": 3, "modes": ["proxy_only"], "message": "Укажите ссылку подписки Freedom ноды (FOREIGN_SUB_URL)"},

    {"kind": "field", "id": "recovery_backup_file", "step": 3, "modes": ["recovery"], "message": "Выберите архив бэкапа для восстановления"},
    {"kind": "field", "id": "recovery_xui_username", "step": 3, "modes": ["recovery"], "message": "Укажите логин админа 3X-UI из бэкапа"},
    {"kind": "field", "id": "recovery_xui_password", "step": 3, "modes": ["recovery"], "message": "Укажите пароль админа 3X-UI из бэкапа"},

    {"kind": "field", "id": "rollback_sub_backup_file", "step": 3, "modes": ["rollback_sub"], "message": "Выберите архив бэкапа Сервера подписок"},
]