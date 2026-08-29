# Аудит полей ввода, плейсхолдеров, валидации и скрытых фолбеков

> Полный реестр всех форм, полей, валидаций, плейсхолдеров и каскадных дефолтов в проекте 3x-UI BootstRUp.

---

## 1. Главные конфликты и системные проблемы

### 🔴 Проблема 1: Плейсхолдер используется как значение (`getFieldValueOrDefault`)
В файле [`panel/static/app.js`](panel/static/app.js) объявлена функция:
```javascript
const getFieldValueOrDefault = (fieldId) => {
    const field = document.getElementById(fieldId);
    if (!field) return '';
    const v = field.value.trim();
    return v ? v : (field.placeholder || '').trim();
};
```
**Суть проблемы:** Если пользователь оставляет поле ввода пустым, фронтенд берет текст из HTML-атрибута `placeholder` и передает его как реальное значение на бэкенд и в сохранение конфигурации. Если в будущем изменить текст плейсхолдера для подсказки (например, `"admin (по умолчанию)"` или локализовать), это значение станет паролем/логином/путем.

---

### 🔴 Проблема 2: Конфликт "Опционально в UI vs Обязательно в валидаторе" (`backup_name`, `sub_backup_name`)
* **В HTML/UI:** В описании шага написано: *"Имя файла бэкапа (опционально, по умолчанию имя домена + дата)"*.
* **В бэкенде (`ssh_deployer.py`):** Реализована автогенерация имени `{host}_{now_str}.tar.gz`.
* **В JS-валидаторе (`REQUIRED_FIELDS` в `app.js`):** Поля `backup_name` и `sub_backup_name` объявлены строго обязательными. Форма блокирует пользователя с ошибкой *"Укажите имя файла бэкапа"*.

---

### 🔴 Проблема 3: Ловушка плейсхолдера при восстановлении (`recovery_xui_username`, `recovery_xui_password`)
* **В HTML:** `placeholder="admin"`, атрибут `value` отсутствует. Пользователь видит серый текст `"admin"` и считает, что дефолт уже применится.
* **В `ssh_deployer.py` / Bash:** Есть фолбеки `or "admin"` и `${RECOVERY_PANEL_USER:-admin}`.
* **В JS-валидаторе (`app.js`):** Поля объявлены в `REQUIRED_FIELDS`. Валидатор проверяет реальное значение (`value.trim() !== ''`), из-за чего при пустом поле выдает ошибку *"Укажите логин/пароль админа 3X-UI из бэкапа"*.

---

### 🔴 Проблема 4: Рассинхронизация версий 3X-UI по умолчанию
* В HTML-селекте: дефолтный пункт `<option value="latest">Загрузка версий...</option>`.
* В `app.js`: при пустом значении фолбек на `'3.6.0'`.
* В `panel/setup.sh`: фолбек `${XUI_VERSION:-3.6.0}`.
* При загрузке версий из GitHub GHCR подставляется первая версия из списка.

---

### 🔴 Проблема 5: Неконсистентность атрибута HTML5 `required`
* Атрибут `required` проставлен только на `vps_host` и `sub_vps_host`.
* На `freedom_host`, `proxy_host`, `backup_vps_host`, `recovery_vps_host`, `update_vps_host` атрибута `required` в разметке нет (хотя все они валидируются кастомным JS `REQUIRED_FIELDS`).

---

## 2. Сводная таблица полей и всех уровней их обработки

| Поле (HTML ID) | HTML разметка (value / placeholder / req) | JS Валидация (`REQUIRED_FIELDS`) | JS Фолбек (`app.js`) | Python Фолбек (`main.py` / `ssh_deployer.py`) | Bash / Remote Фолбек (`setup.sh`) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`vps_host`** | `placeholder="xui.duckdns.org"`, `required` | Обязательно в `single`, `proxy_only`, `freedom_only`, `freedom_component`, `freedom_sub` | `.trim()` | `or ""` | Валидация домена через `is_valid_domain` |
| **`vps_port`** | `value="22"`, без placeholder | Обязательно в тех же режимах | `parseInt(...) \|\| 22` | `int(... or 22)` | В SSH вызове |
| **`vps_user`** | `value="root"`, `placeholder="root"` | Обязательно в тех же режимах | `.trim() \|\| 'root'` | `or "root"` | В SSH вызове |
| **`vps_password`** | `placeholder="password"` | Проверяется, если `auth_type == 'password'` | `value` | `get(...) if not None else ""` | `SSH_ASKPASS` |
| **`vps_key`** | `placeholder="-----BEGIN..."` | Проверяется, если `auth_type == 'key'` | `value` | `get(...) if not None else ""` | SSH identity |
| **`vps_auth_type`** | `option value="password" selected` | — | `value` | — | — |
| **`freedom_host`** | `placeholder="freedom.duckdns.org"` | Обязательно в `cascade`, `cascade_sub` | `.trim()` | `or ""` | `DOMAIN` в `setup.sh` |
| **`freedom_port`** | `value="22"` | Обязательно в `cascade`, `cascade_sub` | `parseInt(...) \|\| 22` | `int(... or 22)` | В SSH вызове |
| **`freedom_user`** | `value="root"`, `placeholder="root"` | Обязательно в `cascade`, `cascade_sub` | `.trim() \|\| 'root'` | `or "root"` | В SSH вызове |
| **`freedom_password`** | `placeholder="password"` | По типу авторизации | `value` | `get(...) if not None else ""` | `SSH_ASKPASS` |
| **`freedom_key`** | `placeholder="-----BEGIN..."` | По типу авторизации | `value` | `get(...) if not None else ""` | SSH identity |
| **`freedom_auth_type`** | `option value="password" selected` | — | `value` | — | — |
| **`freedom_xui_username`** | `placeholder="admin"` | **Нет** | `getFieldValueOrDefault` (`"admin"`) | `.strip()` | `USERNAME="${USERNAME:-admin}"` |
| **`freedom_xui_password`** | `placeholder="admin"` | **Нет** | `getFieldValueOrDefault` (`"admin"`) | `.strip()` | `USER_PASSWORD="${USER_PASSWORD:-admin}"` |
| **`freedom_sub_secret`** | `placeholder="panel"` | **Нет** | `getFieldValueOrDefault` (`"panel"`) | `.strip()` | `SECRET_PHRASE` (random 16 digits если пусто) |
| **`freedom_client_name`** | `placeholder="local-proxy-node-client"` | **Нет** | `value.trim() \|\| 'local-proxy-node-client'` | `config.get(...) or "local-proxy-node-client"` | `CLIENTS_XHTTP_LIST` |
| **`proxy_host`** | `placeholder="proxy.duckdns.org"` | Обязательно в `cascade`, `cascade_sub` | `.trim()` | `or ""` | `DOMAIN` в `setup.sh` |
| **`proxy_port`** | `value="22"` | Обязательно в `cascade`, `cascade_sub` | `parseInt(...) \|\| 22` | `int(... or 22)` | В SSH вызове |
| **`proxy_user`** | `value="root"`, `placeholder="root"` | Обязательно в `cascade`, `cascade_sub` | `.trim() \|\| 'root'` | `or "root"` | В SSH вызове |
| **`proxy_password`** | `placeholder="password"` | По типу авторизации | `value` | `get(...) if not None else ""` | `SSH_ASKPASS` |
| **`proxy_key`** | `placeholder="-----BEGIN..."` | По типу авторизации | `value` | `get(...) if not None else ""` | SSH identity |
| **`proxy_auth_type`** | `option value="password" selected` | — | `value` | — | — |
| **`proxy_xui_username`** | `placeholder="admin"` | **Нет** | `getFieldValueOrDefault` (`"admin"`) | `.strip()` | `USERNAME="${USERNAME:-admin}"` |
| **`proxy_xui_password`** | `placeholder="admin"` | **Нет** | `getFieldValueOrDefault` (`"admin"`) | `.strip()` | `USER_PASSWORD="${USER_PASSWORD:-admin}"` |
| **`proxy_sub_secret`** | `placeholder="panel"` | **Нет** | `getFieldValueOrDefault` (`"panel"`) | `.strip()` | `SECRET_PHRASE` (random 16 digits если пусто) |
| **`proxy_client_tcp_list`** | `placeholder="Опционально..."` | Опционально | `.trim()` | `proxy_client_tcp_list or tcp_raw` | `CLIENTS_TCP_LIST` |
| **`proxy_client_xhttp_list`** | `placeholder="Опционально..."` | Опционально | `.trim()` | `proxy_client_xhttp_list or xhttp_raw` | `CLIENTS_XHTTP_LIST` |
| **`sub_vps_host`** | `placeholder="sub.duckdns.org"`, `required` | Обязательно во всех sub-режимах | `.trim()` | `or ""` | `DOMAIN` в `sub-server/setup.sh` |
| **`sub_vps_port`** | `value="22"` | Обязательно во всех sub-режимах | `parseInt(...) \|\| 22` | `int(... or 22)` | В SSH вызове |
| **`sub_vps_user`** | `value="root"`, `placeholder="root"` | Обязательно во всех sub-режимах | `.trim() \|\| 'root'` | `or "root"` | В SSH вызове |
| **`sub_vps_password`** | `placeholder="password"` | По типу авторизации | `value` | `get(...) if not None else ""` | `SSH_ASKPASS` |
| **`sub_vps_key`** | `placeholder="-----BEGIN..."` | По типу авторизации | `value` | `get(...) if not None else ""` | SSH identity |
| **`sub_domain`** | скрытое / вычисляемое | — | `sub_domain \|\| payload.sub_vps_host` | `config.get(...) or sub_host` | `DOMAIN` в `sub-server` |
| **`sub_secret_path`** | `placeholder="subs"` | **Нет** | `getFieldValueOrDefault` (`"subs"`) | `freedom_sub`: `or "subs"`, другие: `.strip()` | `SECRET_SUB_PATH="${SECRET_SUB_PATH:-subs}"` |
| **`sub_admin_user`** | `placeholder="admin"` | **Нет** | `getFieldValueOrDefault` (`"admin"`) | `.strip()` | `ADMIN_USER="${ADMIN_USER:-admin}"` |
| **`sub_admin_password`** | `placeholder="admin"` | **Нет** | `getFieldValueOrDefault` (`"admin"`) | `.strip()` | `ADMIN_PASSWORD` (random 12 chars если пусто) |
| **`sub_russian_url`** | `placeholder="https://..."` | Группа: хотя бы один URL в `sub_only` | `.trim()` | `resolve_sub_server_urls` | `RUSSIAN_SUB_URL` |
| **`sub_foreign_url`** | `placeholder="https://..."` | Группа: хотя бы один URL в `sub_only` | `.trim()` | `resolve_sub_server_urls` | `FOREIGN_SUB_URL` |
| **`sub_proxy_clients`** | `placeholder="client1, client2"` | Опционально | `.trim()` | парсинг в список | `PROXY_CLIENTS` |
| **`sub_freedom_clients`** | `placeholder="foreign-user-1"` | Опционально | `.trim()` | парсинг в список | `FREEDOM_CLIENTS` |
| **`backup_vps_host`** | `placeholder="vps.duckdns.org"` | Обязательно в `backup` | `.trim()` | `or ""` | В SSH вызове |
| **`backup_vps_port`** | `value="22"` | Обязательно в `backup` | `parseInt(...) \|\| 22` | `int(... or 22)` | В SSH вызове |
| **`backup_vps_user`** | `value="root"`, `placeholder="root"` | Обязательно в `backup` | `.trim() \|\| 'root'` | `or "root"` | В SSH вызове |
| **`backup_name`** | `placeholder="my_backup_2026.tar.gz"` | **🔴 Ошибка: сделано обязательным** | `.trim()` | `{host}_{now_str}.tar.gz` | `panel_backup.sh` |
| **`sub_backup_name`** | `placeholder="my_backup_2026.tar.gz"` | **🔴 Ошибка: сделано обязательным** | `.trim()` | `{sub_host}_sub_{now_str}.tar.gz` | `sub-server` бэкап |
| **`recovery_vps_host`** | `placeholder="new-server.duckdns.org"` | Обязательно в `recovery` | `.trim()` | `or ""` | В SSH вызове |
| **`recovery_vps_port`** | `value="22"` | Обязательно в `recovery` | `parseInt(...) \|\| 22` | `int(... or 22)` | В SSH вызове |
| **`recovery_vps_user`** | `value="root"`, `placeholder="root"` | Обязательно в `recovery` | `.trim() \|\| 'root'` | `or "root"` | В SSH вызове |
| **`recovery_backup_file`** | Select из `./backups_panel/` | Обязательно (проверяется бэкендом) | `.value` | `if not backup_filename: error` | Распаковка на сервере |
| **`recovery_xui_username`** | `placeholder="admin"` | **🔴 Ошибка: сделано обязательным** | `getFieldValueOrDefault` | `or "admin"` | `${RECOVERY_PANEL_USER:-admin}` |
| **`recovery_xui_password`** | `placeholder="admin"` | **🔴 Ошибка: сделано обязательным** | `getFieldValueOrDefault` | `or "admin"` | `${RECOVERY_PANEL_PASS:-admin}` |
| **`update_vps_host`** | `placeholder="xui.duckdns.org"` | Обязательно в `update_3xui`, `restart_*` | `.trim()` | `or ""` | В SSH вызове |
| **`update_vps_port`** | `value="22"` | Обязательно в `update_3xui`, `restart_*` | `parseInt(...) \|\| 22` | `int(... or 22)` | В SSH вызове |
| **`update_vps_user`** | `value="root"`, `placeholder="root"` | Обязательно в `update_3xui`, `restart_*` | `.trim() \|\| 'root'` | `or "root"` | В SSH вызове |
| **`xui_version`** | Select (`value="latest"`) | — | `.trim() \|\| '3.6.0'` | `xui_version` | `${XUI_VERSION:-3.6.0}` |
| **`update_xui_version`** | Select (`value="latest"`) | — | `.trim() \|\| '3.6.0'` | `update_xui_version or xui_version` | Аргумент `$1` в `panel_update.sh` |

---

## 3. Модальные окна и второстепенные формы

### 1. Менеджер сохраненных серверов (`Server Manager`)
* `sm_host`: обязательное поле (проверяется `if (!host)` в `doSaveServer` и `testServerSSH`).
* `sm_user`: `value="root" placeholder="root"`, фолбек `smUser.value.trim() || 'root'`.
* `sm_port`: `value="22" placeholder="22"`, фолбек `parseInt(smPort.value) || 22`.
* `sm_pass` / `sm_key`: placeholder `"••••••••"` / `"-----BEGIN..."`, очищаются/шифруются в зависимости от `sm_auth_type`.
* `sm_panel_url`: `placeholder="https://example.com/secret_path/"`, опциональное поле.

### 2. Модальное окно мастер-пароля (`Master Password Modal`)
* `masterPasswordInput`: `placeholder="Введите пароль или PIN"`. Обязательное для расшифровки/шифрования хранилища, дефолтов нет.

### 3. Модальное окно редактора маршрутизации (`Happ Routing Modal`)
* `happRoutingEditor`: `placeholder="Загрузка happ-routing.json..."`. Загружается через `GET /api/happ_routing`, сохраняется через `POST /api/happ_routing` с валидацией JSON на фронтенде.

---

## 4. Скрытые внутренние генераторы значений (серверные фолбеки)

1. **Внутренние порты панели (`panel/setup.sh:generate_ports`)**:
   Генерируются динамически в диапазоне 49152–65535, если не заданы:
   * `XUI_WEB_PORT`
   * `XUI_SUB_PORT`
   * `CADDY_GLOBAL_INTERNAL_PORT`
   * `TCP_REALITY_INBOUND_PORT`
   * `XHTTP_REALITY_INBOUND_PORT`
2. **Секретные хэшированные пути (`panel/setup.sh:generate_paths`)**:
   * `XUI_WEB_BASE_PATH`: `md5("${SECRET_PHRASE}-panel")[0:16]`
   * `XUI_SUB_PATH`: `md5("${SECRET_PHRASE}-sub")[0:16]`
3. **Ключи Reality (`panel/setup.sh:generate_reality_keys`)**:
   Генерируются через временный контейнер `xray-core x25519` (Private/Public keys + shortIds).
4. **Сессии сервера подписок (`sub-server/server.py`)**:
   * `AUTH_SESSION_SECRET`: `os.environ.get(...) or secrets.token_hex(32)`.
   * `SESSION_TTL_SECONDS`: `int(os.environ.get("AUTH_SESSION_TTL", "43200"))` (12 часов).

---

## 5. Рекомендации по устранению "бардака"

1. **Убрать чтение `placeholder` как значения**:
   Заменить `getFieldValueOrDefault(id)` на явные дефолты или явное задание `value="admin"`, `value="panel"`, `value="subs"` в HTML-разметке. Плейсхолдер должен оставаться только визуальной подсказкой (hint).
2. **Исправить `REQUIRED_FIELDS` для бэкапов**:
   Убрать `backup_name` и `sub_backup_name` из `REQUIRED_FIELDS`, так как бэкенд отлично генерирует имя файла бэкапа по маске `{host}_{date}.tar.gz`.
3. **Устранить противоречие в `recovery_xui_*`**:
   Либо прописать в HTML реальный `value="admin"`, либо убрать из `REQUIRED_FIELDS` и передавать дефолт `"admin"` на бэкенд, если поле пустое.
4. **Унифицировать дефолтную версию 3X-UI**:
   Привести единый дефолт к `"latest"` (или единой фиксированной стабильной версии) во всех слоях (HTML / JS / Python / Bash).
5. **Синхронизировать HTML `required`**:
   Либо убрать атрибут `required` из HTML (так как валидацией управляет JS перед переходом по шагам визарда), либо проставить его единообразно на всех полях хостов.
