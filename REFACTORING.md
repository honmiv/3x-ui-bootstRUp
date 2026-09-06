# Рефакторинг 3x-UI BootstRUp: большой план

> Статус: в процессе. **Фазы A и B + C1 + C3 + C4 + C5 + D1 выполнены** (A — защитный слой unit-тестов и фиксация контрактов; B — шаблонизация `sub-server/server.py`; C1 — maintenance-срез `ssh_deployer.py` → `deployers/maintenance.py`; C3 — deploy-ветки → `deployers/panel_deployer.py` + `deployers/sub_deployer.py`; C4 — сигнатуры `_deploy_node`/`_deploy_sub_server` → `NodeConfig`; C5 — `SSHDeployer` → `core/ssh_client.py`; D1 — маршруты `main.py` → `routing.py`).
> Порядок фаз — по убыванию ценности/безопасности.
> Принцип: каждый шаг рефакторинга — отдельный PR, без изменения поведения. Тесты до и после.

---

## 0. Суть проблемы

Код рабочий, но четыре файла-монолита завязали логику на три разных «языка»:

| Файл | Строк | Проблема |
|------|-------|----------|
| `panel/static/app.js` | 5428 | 1 глобал, 782 функции, нет модулей |
| `sub-server/server.py` | ~~4563~~ → 1848 | HTML/CSS/JS вшито в `"""` строки (Фаза B: вынесено в `templates/web/`) |
| `ssh_deployer.py` | ~~2363~~ → 1159 | bash/awk встроены в Python-строки; maintenance-ветки → `deployers/maintenance.py` (C1); deploy-ветки → `deployers/panel_deployer.py` + `deployers/sub_deployer.py` (C3); сигнатуры деплоя → `NodeConfig` dataclass (C4); `SSHDeployer` → `core/ssh_client.py` (C5). Остался диспетчер + оркестрация |
| `main.py` | 1419 | самописный YAML, гигантские `do_GET`/`do_POST` |

Три самостоятельные болезни:
1. **Модульность** — нет границ, всё в общей области видимости.
2. **Шаблонизация** — разметка/скрипты вшиты в код, не вынесены.
3. **Разделение языков** — Python + HTML/CSS/JS + bash/awk смешаны в одном файле.

Плюс системная проблема: **7 дублирующихся наборов SSH-полей** (`vps_*`, `freedom_*`, `proxy_*`, `sub_vps_*`, `backup_vps_*`, `recovery_vps_*`, `update_vps_*`).

### Находки (обоснования, почему это болит)

| # | Где | Проблема | Почему болит |
|---|-----|----------|--------------|
| F1 | `main.py` | HTTP + YAML + конфиг + апдейтер + лаунчер в одном файле | Изменение YAML рискует сломать маршруты; тест `save_backup_config` требует импорта всего HTTP-сервера |
| F2 | `main.py` | Самописный YAML (~150 строк) | Самый хрупкий код в проекте: `_parse_yaml_scalar`/`_dump_yaml_simple`/`_load_yaml_simple` не умеют вложенные dict/якоря; крайний случай в `setup_backup.yml` = тихая потеря данных. Решение zero-dep оставляем, но покрываем тестами |
| F3 | `ssh_deployer.py` | Транспорт + оркестрация + embedded bash в одном файле | `run_deployment` — ~1272 строк `if/elif`; bash-строки без подсветки/linting/shellcheck |
| F4 | всё | Нет data model — всё `Dict[str, Any]`, 7 префикс-групп | Опечатка (`update_vps_hots`) молча резолвится в `None`; `save_backup_config` ведёт ручной список ~80 ключей; валидация SSH продублирована 7 раз |
| F5 | `app.js` | 5428 строк глобальных функций, нет IIFE/модулей | Коллизии имён; невозможно тестировать один concern отдельно; WebCrypto переплетён с UI |
| F7 | `ssh_deployer.py` | Embedded bash: `PANEL_DOMAIN_REWRITE_SCRIPT` (~140 строк), `LEGACY_COMPOSE_REWRITE_CMD` и др. | Нет shellcheck; хрупкий экранинг многострочных строк; правка скрипта = правка Python-файла |
| F9 | `server.py` | ~2000 строк HTML/CSS/SVG внутри Python-строк | Нет подсветки HTML; правка CSS = правка Python-файла |
| F10 | `ssh_deployer.py` | Захардкоженные пути/строки: `/opt/3x-ui-bootstRUp` (8+ раз), `PANEL_CONTAINER`, `PANEL_API_PORT` | Смена пути = 8+ правок; опечатка молча создаёт директорию или роняет runtime |

**Отклонённые находки из предыдущего плана** (обоснование решений):
- ~~F2→PyYAML~~ — zero-dep на Windows/macOS/Linux — осознанный дизайн (см. AGENTS.md TODO #1). Оставляем самописный парсер, закрываем тестами.
- ~~F6 services/ слой~~ — overengineering: у `main.py` один entry point, HTTP-маршруты уже понятны. Сервисный слой оправдан при нескольких потребителях бизнес-логики, тут их нет.
- ~~F8 MockTransport/RemoteTransport~~ — проект уже поднимает настоящие Docker-VPS-контейнеры (`tests/docker-compose.test.yml`, `Dockerfile.vps`) и гоняет реальный `SSHDeployer` через ssh. Это сильнее любого мока.

---

## Фаза A: Страховка (без изменения поведения) — [ВЫПОЛНЕНО]

> **Статус**: ВЫПОЛНЕНО. Создана директория `tests/unit/` (без `__init__.py` для совместимости с namespace/runner), добавлены 40 тестов.
> Запуск: `.python_env/bin/python3 -m unittest discover -s tests/unit` (выполняются за ~0.005с, все зелёные).
> Тесты написаны по принципу black-box (по ожидаемому поведению и инвариантам безопасности, а не по внутренней реализации).

### С чем уже работают тесты (НЕ трогаем, используют как основу)
- Интеграция ядра `run_deployment`: `tests/deploy/test_deploy_*.py` (freedom/proxy/sub/
  cascade/cascade_sub/freedom_sub) против Docker-VPS.
- `validate_deployment_config`: `tests/test_validation_and_fallbacks.py`.
- `get_bundle_bytes`: `tests/test_decoy_manager.py`.
- `derive_sub_path`/`derive_sub_server_path`: `tests/test_validation_and_fallbacks.py:239`.
- Порт-менеджмент `main`: `tests/test_server_port_management.py`.
- UI E2E (playwright): `tests/ui/`.
- Обновление/changelog: `tests/test_changelog_update.py`.

### A1, A1.5, A1.6, A2. Что и как реализовано

1. **`tests/unit/test_yaml_config_security.py`** (13 тестов):
   - **`_parse_yaml_scalar`**: парсинг booleans (`true`/`false`/`yes`/`no`/`on`/`off`), nulls (`null`/`none`/`~`), чисел (`int`, `float`), экранированных строк (`\n`, `\t`, `\"`, `''`) и инлайн-комментариев.
   - **`_dump_yaml_simple`**: проверка экранирования строк с двоеточиями, решётками, скобками, кавычками; корректная обработка пустых секций.
   - **Roundtrip и идемпотентность**: `_load_yaml_simple(_dump_yaml_simple(data)) == data` для сложных конфигов; повторный дамп выдаёт байт-в-байт идентичный результат.
   - **Security (критично)**: проверка, что пароли (`*password*`) и SSH-ключи (`*_key`) **никогда** не попадают в `setup_backup.yml` на диске. Проверена защита от инъекций sensitive-полей и очистка при чтении в `load_backup_config`.

2. **`tests/unit/test_deployment_parsing.py`** (17 тестов):
   - **`parse_deployment_results`**: извлечение URL панели и клиентов из маркеров `===RESULT_JSON_START===` ... `===RESULT_JSON_END===`.
   - **Отказоустойчивость**: корректная обработка отсутствующих маркеров, перевёрнутых маркеров, нескольких маркеров (берётся первый блок), пустого вывода, битого JSON.
   - **Fuzzing (A1.5)**: устойчивость к ANSI escape-кодам (`\x1b[32m`), неожиданным типам клиентов (`null`, `int`, `list`), гигантским строкам (>100Кб). Функция не падает с unhandled exception, а отдаёт безопасный дефолт `("", [])`.
   - **`extract_domain_from_url`**: корректное извлечение хоста из схем `http`, `https`, `vless`, с портами, путями, IP-адресами.
   - **`_sub_server_sync_cmd`**: проверка генерации bash-команды архивации/восстановления с флагами `preserve=True` (сохранение `nodes.json`/`force-subs.yml`) и `preserve=False`.

3. **`tests/unit/test_core_signatures.py`** (10 тестов):
   - Зафиксированы точные контракты и сигнатуры через `inspect.signature`:
     * `ssh_deployer.run_deployment(config, log_callback, cancel_check=None)`
     * `ssh_deployer.parse_deployment_results(output_text)`
     * `ssh_deployer.derive_sub_path(secret)` / `derive_sub_server_path(secret)`
     * `ssh_deployer.resolve_sub_server_urls(proxy_sub_url, freedom_sub_url)` (критично: monkey-patched в tests/overrides)
     * `ssh_deployer.extract_domain_from_url(url)`
     * `ssh_deployer._sub_server_sync_cmd(remote_dir, preserve)`
     * `ssh_deployer.SSHDeployer` методы (`exec_command`, `download_file`, `test_connection`)
     * `main.save_backup_config(data)` / `load_backup_config()`
     * `main._dump_yaml_simple(data)` / `_load_yaml_simple(text)` / `_parse_yaml_scalar(val_str)`
     * `main.fetch_xui_versions()` / `check_for_update(force=False)` / `list_backup_files(folder)`

4. **Интеграционный baseline**:
   - Запуск полного сьюта unit-тестов проекта (`.python_env/bin/python3 -m unittest discover -s tests -p "test_*.py"`) проходит без ошибок. Baseline зафиксирован.

---

## Фаза B: `sub-server/server.py` (шаблонизация) — быстрый выигрыш

> **Статус**: ВЫПОЛНЕНО (B1 + B3). `server.py`: 4563 → 1848 строк. B2 (JS наружу) отложен как опция.

### Что сделано

- `PAGE_TEMPLATE` (бывшие строки 127–2479) → `sub-server/templates/web/dashboard.html` (99 373 байт).
- `LOGIN_TEMPLATE` (2481–2851) → `sub-server/templates/web/login.html` (16 136 байт).
- В `server.py` (~127–136) добавлены `WEB_TEMPLATE_DIR` и `_load_web_template(name)`: `PAGE_TEMPLATE = _load_web_template("dashboard.html")`, `LOGIN_TEMPLATE = _load_web_template("login.html")`.
- Все `__VAR__`-плейсхолдеры и цепочка `.replace()` не тронуты — подстановка работает как раньше.
- Docker-синхронизация (критичный нюанс из плана):
  - `Dockerfile-python` → добавлено `COPY templates/web /app/templates/web`.
  - `docker-compose.yml.template` → добавлен volume `- ./sub-server/templates/web:/app/templates/web`.
  - `get_bundle_bytes()` проверен построением бандла: `sub-server/templates/web/{dashboard,login}.html` попадают в tar.gz (exclusion list не трогает `sub-server/templates/web/`).

### Как делалось (важный урок extraction)

- Извлекать **вычисленные** строки (импорт старой версии модуля из git HEAD и дамп их значений), а НЕ сырой исходник из `"""`-блока. Сырое извлечение ломает Python escape-обработку: `\\/` → `\/` в JS-регэкспах (5-байтовая разница, расхождение на позиции 88030).
- После переизвлечения оба файла байт-в-байт идентичны оригинальным строкам (`identical=True`).

### Проверка (B3)

- `compileall` + `py_compile` — OK.
- Тесты зелёные: 40 unit (`tests/unit`), sub-server integration (`test_sub_server_nodes`, `test_sub_server_https`, `test_deploy_sub_server`), decoy/validation (`test_decoy_manager`, `test_validation_and_fallbacks`).
- Smoke-рендер: dashboard 200 (содержит `node-type-badge`, имена клиентов; нет `__SECTIONS__`/`__API_NODE__`), login 200 (содержит «Пароль»; нет `__ERROR_BLOCK__`/`__LOGIN_ACTION__`); запрос без cookie → 302 на login (корректно).
- Реальный деплой пользователя: `update_sub` на VPS прошёл успешно (шаг `COPY templates/web` DONE, контейнеры подняты, SSL OK, «Subscription Server updated successfully; clients and nodes preserved!»).

### Эксплуатационные последствия (важно!)

- **`update_sub`** перегенерирует compose из шаблона → применяет изменения шаблонов на любом сервере (и старом, и новом).
- **`restart_sub`** только пересоздаёт контейнер по существующему `working/docker-compose/docker-compose.yml` — НЕ перегенерирует. На сервере, деплоенном до Фазы B, контейнер упадёт с `RuntimeError: cannot load web template` (нет `/app/templates/web`). Лечение: сначала `update_sub`.

### Побочная находка (исправлено вне плана B)

- При верификации найден предсуществующий баг рендера карточек результата: голый `else` в `app.js` (~строка 3663) для ЛЮБОГО не-панельного режима рендерил фейковую карточку «Панель управления 3X-UI» с URL `https://Server/` (проявился после первого `update_sub`).
- Фикс: `} else {` → `} else if (mode === 'single' || mode === 'proxy_only' || mode === 'freedom_only' || mode === 'freedom_component') {`.
- Причины, почему логи не ловили: логи = stdout бэкенда (SSE), карточка = фронт-рендер `app.js` после завершения; тестов на карточки не было вовсе.
- Добавлен E2E `tests/ui/test_ui_result_cards.py` (Playwright): 10 проверок — 9 maintenance-режимов (`update_sub`, `restart_sub`, `backup_sub`, `rollback_sub`, `backup`, `recovery`, `restart_panel`, `restart_server`, `update_3xui`) без фейковой панельной карточки + позитивный контроль `freedom_only` (реальная панельная карточка рендерится). Доказано, что тест ловит регрессию: при откате фикса падает на `update_sub`. Приёмы: мок `/api/deploy` + `/api/status`; hidden selects бэкапов (`recovery_backup_file`, `rollback_sub_backup_file`) заполняются через `set_hidden_select()` (evaluate + change, валидация читает `select.value`); `/api/backups` мокнут.
- Раннеры: `run_ui_parallel.py` автоподхватывает `test_ui_*.py` по glob — тест попадает в `all`/`parallel`.

### Прочее / отложено

- `style.css` и `app.js` (внешние) НЕ выносились — встроенная `.replace()`-подстановка в `server.py` работает, отдельные файлы появились бы без реального pain point. Переделка отложена (см. B2 ниже).
- **B2 (опция, не делается)**: JS-функции внутри `Handler` → `.js` + `src="..."`; `Handler` разбить на «логику запросов» и «генерацию HTML». Отложено как низкоприоритетное.

---

## Фаза C: SSH-транспорт и `ssh_deployer.py`

### C1. Разбить orchestration по поведенческим срезам — [ВЫПОЛНЕНО]
- Maintenance-срез вынесен первым: `deployers/maintenance.py` (backup, recovery, update/update_3xui,
  restart_panel/restart_server, restart_sub/update_sub/backup_sub/rollback_sub).
- Создан пакет `deployers/` (namespace-пакет, PEP 420 — `__init__.py` удалён по решению
  пользователя; `from deployers import maintenance` работает и тесты зелёные);
  `ssh_deployer.py` — 2483 → 1854 строк.
- `run_deployment` сохранил публичную сигнатуру и маршрутизацию режимов; ветки делегируют
  через отложенный `from deployers.maintenance import ...` (ломает циклический импорт: maintenance
  импортирует из ssh_deployer наверху).
- В maintenance-функции переданы зависимости как параметры: `prepare_decoy_files` (замыкание
  `run_deployment`, используется и deploy-ветками), `change_ssh_port`/`new_ssh_port`/`updated_ssh_ports`
  (dict мутируется до return — поведение сохранено).
- Тела веток перенесены дословно (сверено диффом с HEAD: только сигнатуры/отступы).
- Проверено: 40 unit + 22 validation/changelog зелёные; deploy-интеграции и UI E2E не затронуты
  (требуют docker/playwright — гонять в финальном прогоне перед мержем).
- Осталось после C1: panel/cascade → `deployers/panel_deployer.py`, sub-only → `deployers/sub_deployer.py`
  (выполнено в C3 ниже).

### C2. Вынести embedded bash/awk в файлы *(понижен приоритет)*
- `PANEL_DOMAIN_REWRITE_SCRIPT` (149–291, ~140 строк bash) → `common/remote_scripts/panel_domain_rewrite.sh`.
- `LEGACY_COMPOSE_REWRITE_CMD` (133) → `common/remote_scripts/legacy_compose_rewrite.sh`.
- `LEGACY_TEMPLATES_SYMLINK_CMD` (120) → `common/remote_scripts/legacy_templates_symlink.sh`.
- **Почему понижен**: встроенный bash работает; shellcheck можно запускать на строку (`bash -n`); динамические env vars (`${RECOVERY_OLD_DOMAIN}`) уже через shell env, не Python f-strings. Выносить только когда будет pain point (много embedded scripts, баги при правке).
- Загружать в рантайме через `Path.read_text()` и стримить на удалённую сторону (логика `get_bundle_bytes` уже умеет включать файлы в bundle).
- Проверить `get_bundle_bytes()`: remote_scripts должны попадать в tar-бандл (сейчас exclusion list не трогает `common/`).

### C3. Разбить `run_deployment` на поведенческие модули — [ВЫПОЛНЕНО]
- `deployers/panel_deployer.py` (551 строка) — `deploy_single` (single/proxy_only/freedom_only/
  freedom_component), `deploy_freedom_sub` (freedom+sub-server, 2 стадии), `deploy_cascade`
  (cascade/cascade_sub, 2-3 стадии). Тела веток перенесены дословно (сверено диффом строк:
  только сигнатуры + перенос общих преамбульных деклараций внутрь функций).
- `deployers/sub_deployer.py` (114 строк) — `deploy_sub_only`.
- `ssh_deployer.py::run_deployment` — 2483 → 1854 (C1) → **1349 строк**: диспетчер из 9 делегирований.
- **Отклонение от буквального плана**: `_deploy_node`, `_deploy_sub_server`, `_sub_server_sync_cmd`
  **остаются в ssh_deployer.py** как shared-хелперы — они импортируют `SSHDeployer`/`get_bundle_bytes`
  из ssh_deployer; перенос в deployers/ создал бы циклический импорт. По плану C5 они уедут в
  `core/ssh_client.py`. Снапшоты тестов (`test_core_signatures`, `test_deployment_parsing`)
  фиксируют `ssh_deployer._sub_server_sync_cmd` — сигнатура сохранена.
- Другие импорты деплой-модулей из ssh_deployer: `_change_remote_ssh_port`, `derive_sub_path`,
  `derive_sub_server_path`, `extract_domain_from_url`, `parse_deployment_results`, `resolve_sub_server_urls`.
- Каждая verify: 40 unit + 22 validation/changelog зелёные (после всех правок); `py_compile` OK.
  deploy-интеграции и UI E2E не гонялись (требуют docker/playwright — финальный прогон перед мержем).

### C4. Сократить сигнатуры — [ВЫПОЛНЕНО]
- Введён `@dataclass NodeConfig` в `ssh_deployer.py`: `host, port, user, password,
  key_data, env_vars, cancel_check, bundle_source_dir, decoy_files`.
- `_deploy_node(node: NodeConfig, log)` и `_deploy_sub_server(node: NodeConfig, log)`
  — 10 аргументов → 2. Публичное имя и поведение сохранены, всё внутри репо.
- Обновлены все 7 вызовов: `deployers/panel_deployer.py` ×5, `deployers/sub_deployer.py` ×1,
  `deployers/maintenance.py` ×1.
- **Отклонение от плана**: шаг «адаптеры со старыми сигнатурами» пропущен — внешних
  потребителей нет (тесты и overrides сигнатуры не фиксируют, main.py не вызывает;
  проверено grep). Адаптеры были бы мёртвым кодом с первого дня.
- Проверено: 40 unit + 22 validation/changelog зелёные; `py_compile` OK, импорты OK.

### C5. Вынести `SSHDeployer` в модуль — [ВЫПОЛНЕНО]
- `core/ssh_client.py` (219 строк) — низкоуровневый async SSH/SCP враппер
  (`SSHDeployer` + `ANSI_ESCAPE`/`strip_ansi`). Тело класса перенесено дословно
  (сверено диффом: байт-в-байт идентично).
- `ssh_deployer.py` — 1349 → 1141 строк: транспорт удалён, осталась оркестрация.
  Публичный импорт `from core.ssh_client import SSHDeployer` сохраняет
  `ssh_deployer.SSHDeployer` (проверено: тот же объект класса; main.py:19,
  tests/overrides, deployers-модули работают без правок).
- `import tempfile` удалён из `ssh_deployer.py` (стал мёртвым после выноса);
  мёртвый `import base64` (был до C5) намеренно не тронут.
- `get_bundle_bytes()`: `core/` добавлен в exclusion (локальный транспорт remote
  не нужен, аналогично `deployers/`); проверено — 0 записей `core/` в бандле.
- Проверено: 40 unit + 22 validation/changelog зелёные; `py_compile` OK.

### C6. Константы наружу (F10)
- `/opt/3x-ui-bootstRUp` (8+ вхождений), `PANEL_CONTAINER="3xui"`, `PANEL_API_PORT="2053"` → 
  `constants.py` (Python) + `common/constants.sh` (Bash, source в setup-скриптах).
- В `panel/setup.sh`/`sub-server/setup.sh` значения оставить до отдельного решения (remote IaC, см. «Что НЕ делать»).

---

## Фаза D: `main.py`

### D1. Маршруты из гигантских `do_GET`/`do_POST` — [ВЫПОЛНЕНО]
- Создан `routing.py` (542 строки): `handle_get`/`handle_post`/`handle_delete`
  диспетчеры + отдельные функции-хендлеры (`_get_*`/`_post_*`), тела перенесены
  дословно (менялись только `self.` → `handler.` и `global`-глобалы → `M.`).
- `main.py` `WebUIHandler.do_GET/do_POST/do_DELETE` сведены к 3 ленивым импортам
  (`import routing`), класс и сигнатуры сохранены — UI-тесты, которые поднимают
  реальный `ThreadingHTTPServer(WebUIHandler)` и патчат `main`-атрибуты, работают.
- **Антициклический трюк**: `routing.py` делает `import main as M` наверху и читает
  всё глобальное состояние через `M.` (не `from main import ...`) — чтобы
  переприсваивание модульных атрибутов во время тестов (`SERVERS_FILE`,
  `is_deploying` и т.д.) было всегда видимо и не было циклического импорта.
- `urllib.parse` импорт удалён из main.py (использовался только маршрутами).
- Проверено: 62 unit/validation зелёные; live-HTTP smoke 15/15 маршрутов (GET/POST/DELETE,
  отдача статики, SSE, 404, валидация); `py_compile` OK.

### D2. YAML через стандартную библиотеку (пересмотреть requirement)
- `_dump_yaml_simple`/`_load_yaml_simple` (~150 строк) — самописный YAML ради zero-dependency.
- **Оставлено по дизайну** (см. AGENTS.md TODO #1): гарантия zero-зависимостей на Windows/macOS/Linux.
- **Действие**: если требование zero-dep остаётся — минимум покрыть парсер unit-тестами (A1); иначе — рассмотреть `PyYAML` и удалить самописный код.

---

## Фаза E: `panel/static/app.js` (модульность) — самая большая

### E1. Split на ES-модули
Так как файл — `<script>` без сборщика, перейти на `type="module"` или IIFE-модули. Целевая структура:
```
panel/static/modules/
  crypto.js      # WebCrypto PBKDF2/AES-GCM, мастер-пароль, авто-миграция
  servers.js     # drawer сохранённых VPS, lock, edit, quick-select
  logs.js        # SSE-стрим, auto-scroll, статус-бейджи
  forms.js       # переключение режимов, валидация, основная логика
  topology.js    # SVG-диаграмма
  md5.js         # вынести самописный md5 из app.js (177–288)
  ui.js          # toast/dialog/alert (перезапись window.alert/confirm)
  deploy.js      # управление деплоем, старт/стоп (без UI-части SSE)
```
- **Шаг**: сначала вынести `md5`/`derivePanelPaths`/`ui` — изолированные, безопасные, без зависимостей. Потом `crypto`, `topology`, `logs`, потом `forms`/`servers` (самая связанная часть).
- [ВЫПОЛНЕНО, частично] `modules/ui.js` создан (ui + md5 + derive, verbatim-копия строк 1–303 app.js, подключён обычным `<script>` перед app.js — глобальные функции сохранены); app.js 5460 → 5157 строк. `modules/crypto.js` создан (deriveKeyV1/V2, vault cookie, getPayloadVersion, encryptData/decryptData — 8 чистых crypto-функций, window-экспорт для app.js); app.js 5157 → 5081 строк. Осталось: `topology`, `logs`, `forms`, `servers`, `deploy.js`.
- `index.html` — подключить модули.
- **Критичный нюанс ES Modules**: при `<script type="module">` функции не попадают в глобальный `window`. Перед переводом убедиться, что инлайновые атрибуты (вроде `onclick="..."`) заменены на `addEventListener`, либо нужные функции явно экспортированы в `window` ради совместимости с тестами Playwright (`tests/ui/`).

### E2. Убрать глобальную подмену `window.alert`/`confirm`
- Оставить подмену только если требуется явно (совместимость), иначе использовать `showToast`/`showConfirm` напрямую, не трогая window.

---

## Фаза F: единая модель сервера (сквозная проблема)

### F1. Unified `ServerConnection`
- Сейчас 7 наборов ключей (`vps_*`, `freedom_*`, `proxy_*`, `sub_vps_*`, `backup_vps_*`, `recovery_vps_*`, `update_vps_*`).
- **Действие**: единая dataclass `ServerConnection` (host, port, user, auth_type, password, key) + маппинг старых ключей → модель на границе парсинга формы.
- **Порядок**: не ломать сохранённый `setup_backup.yml` — маппить при чтении/записи; формат файла можно оставить (обратная совместимость) или мигрировать с запасным парсером.
- **Побочный выигрыш**: `validate_deployment_config` — убрать 7-кратное дублирование `_check_ssh(key_prefix, ...)`, заменить одной `ServerConnection.validate()`; `save_backup_config` — заменить ручной список ~80 ключей сериализацией dataclass.
- Выполнять после стабилизации C и D, но до крупного E: backend-модель должна стать
  устойчивой границей до унификации frontend-полей.

### F2. Переиспользуемый frontend-селектор сервера
- Вынести повторяющиеся поля ввода SSH в один HTML-компонент/шаблон, вместо копипасты по секциям формы.
- Делать после F1 и небольшими срезами по ролям, сохраняя старые имена полей на границе API.

---

## Фаза G: стратегический паттерн режимов (опция, самое дальнее)

- Каскадные `if/elif` по `mode` в `app.js`, `main.py`, `ssh_deployer.py` — нарушение Open/Closed.
- **Действие**: `DeploymentStrategy` реестр, каждый режим инкапсулирует schema валидации + pipeline + формат результата.
- **Зависимость**: требует готовых фаз C, D, E (границы сначала, паттерн потом).

---

## Целевая структура файлов (после всех фаз)

```
3x-ui-bootstrup/
├── main.py                        # HTTP-сервер + роутинг (~400 строк)
├── routing.py                     # Диспетчер маршрутов (из do_GET/do_POST)
├── constants.py                   # PANEL_CONTAINER, PANEL_API_PORT, remote_dir
├── core/
│   └── ssh_client.py              # SSHDeployer (из ssh_deployer.py)
├── ssh_deployer.py                # Оркестрация деплоя (режимы, НЕ транспорт)
├── deployers/
│   ├── panel_deployer.py          # single + cascade + _deploy_node
│   ├── sub_deployer.py            # _deploy_sub_server, _sub_server_sync_cmd
│   └── maintenance.py             # backup/restart/update/recovery
├── common/
│   ├── constants.sh               # source в setup-скриптах
│   ├── remote_scripts/            # *.sh, загружаются Path.read_text()
│   │   ├── panel_domain_rewrite.sh
│   │   ├── legacy_compose_rewrite.sh
│   │   └── legacy_templates_symlink.sh
│   └── setup.sh                   # (unchanged)
├── models.py                      # ServerConnection, NodeConfig dataclass
├── panel/
│   ├── setup.sh                   # (unchanged)
│   └── static/
│       ├── index.html             # подключает ES-модули
│       ├── style.css
│       └── modules/
│           ├── crypto.js  ui.js  servers.js  deploy.js
│           ├── forms.js  topology.js  logs.js  md5.js
├── sub-server/
│   ├── server.py                  # Роутинг + прокси (~400 строк)
│   ├── templates/
│   │   ├── web/
│   │   │   ├── dashboard.html  login.html  style.css  app.js
│   │   ├── caddy/                 # (unchanged)
│   │   └── docker-compose/        # (unchanged)
│   └── setup.sh                   # (unchanged)
└── tests/                         # tests/deploy/, tests/ui/, tests/vpn/ + tests/unit/
    └── unit/                      # Чистые unit-тесты ядра (без __init__.py)
        ├── test_yaml_config_security.py
        ├── test_deployment_parsing.py
        └── test_core_signatures.py
```

---

## Порядок, риски и оценка

| Приоритет | Фаза | Ценность | Риск | Статус |
|-----------|------|----------|------|--------|
| 1 | A (тесты) | основа | низкий | **ВЫПОЛНЕНО (40 тестов)** |
| 2 | B (server.py) | высокая, быстрая | низкий | **ВЫПОЛНЕНО** (4563→1848; шаблоны + подвязка Docker/bundle; `test_ui_result_cards.py` как бонус) |
| 3 | C1/C3 (orchestration-срезы) | высокая | средний | **C1+C3 ВЫПОЛНЕНО** (maintenance → `deployers/maintenance.py`; panel/cascade → `deployers/panel_deployer.py`; sub-only → `deployers/sub_deployer.py`; `ssh_deployer.py` → 1349 строк). |
| 4 | C5 (SSH-транспорт) | высокая | средний | **ВЫПОЛНЕНО** (`SSHDeployer` → `core/ssh_client.py`; `ssh_deployer.py` → 1141 строк) |
| 4a | C4 (сигнатуры `_deploy_node`/`_deploy_sub_server`) | средняя | низкий | **ВЫПОЛНЕНО** (`NodeConfig` dataclass; 10 аргументов → 2) |
| 5 | D (main.py) | средняя | средний | **D1 ВЫПОЛНЕНО** (`routing.py`; маршруты из `do_GET/do_POST/do_DELETE`; `main.py` 1419 → 987 строк) |
| 6 | F (модель сервера) | средняя | средний | запланировано |
| 7 | E (app.js) | высокая | высокий | запланировано |
| 8 | G (стратегии) | опция | высокий | запланировано |

**Золотое правило**: каждый поведенческий срез = отдельный PR. Поведение не меняется,
публичные импорты и сигнатуры временно сохраняются адаптерами, тесты зелёные до/после.
Не объединять перенос шаблонов, маршрутизации и бизнес-логики в один PR.

---

## Что НЕ делать

- Не переписывать `setup.sh`/`sub-server/setup.sh` как часть рефакторинга (это remote IaC, ломается легко). Константы в них — только через `common/constants.sh` source.
- Не убирать zero-dependency YAML без явного решения стейкхолдера.
- Не вводить сборщик фронта (webpack/vite) — проект без node-тулчейна; ES-модули достаточно.
- Не вводить MockTransport/RemoteTransport — Docker-VPS-интеграция уже покрывает тестируемость транспорта.
- Не вводить services/-слой между HTTP и бизнес-логикой — один entry point, нет нескольких потребителей.
- Не мигрировать `subs.yml`→`nodes.json` тут (уже сделано в AGENTS.md TODO #2).