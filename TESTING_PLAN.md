# Комплексный План Тестирования 3x-UI BootstRUp

Данный документ содержит полное описание архитектуры, стратегии и тест-кейсов для автоматизированного тестирования инфраструктуры **3x-UI BootstRUp**.

Тестирование разделено на 4 ключевых уровня:
1. **Деплой-тесты (Deployment Tests)** — проверка корректности SSH-оркестрации, генерации конфигураций, развертывания Docker-сервисов и выпуска TLS-сертификатов.
2. **VPN-тесты сквозного трафика (VPN Connectivity Tests)** — проверка реального проксирования через `xray-core` клиент, работы VLESS Reality TCP/XHTTP и маршрутизации трафика.
3. **UI-тесты веб-интерфейсов (Control Panel & Sub-Server UI Tests)** — тестирование локальной панели управления и веб-интерфейса сервера подписок.
4. **Регрессионные тесты и тесты жизненного цикла (Regression & Lifecycle Tests)** — миграция версий, бэкап/восстановление с заменой доменов, обновление 3x-UI, замена заблокированных нод и откат.

---

## 🏗️ Архитектура Тестового Стенда (Testbed Topology)

Все тесты выполняются в изолированной Docker-сети (`testnet`) на виртуализированных контейнерах VPS (Debian 12 + Docker-in-Docker + SSHD):

```
                                ┌────────────────────────────────────────────────────────────────────────┐
                                │                     DOCKER TEST NETWORK (testnet)                      │
                                │                                                                        │
┌───────────────────────┐       │  ┌────────────────┐                ┌────────────────┐                  │
│      TEST RUNNER      │       │  │  vps-freedom   │                │   vps-proxy    │                  │
│(tests/run_all_tests.sh)│      │  │ (freedom.test) │                │  (proxy.test)  │                  │
│ • Orchestrates stages │       │  ├────────────────┤                ├────────────────┤                  │
│ • Runs ssh_deployer   │─(SSH)─┼─→│ • 3x-UI Panel  │                │ • 3x-UI Panel  │                  │
│ • Validates APIs & TLS│       │  │ • Caddy L4     │                │ • Caddy L4     │                  │
└───────────┬───────────┘       │  │ • Nginx Decoy  │                │ • Nginx Decoy  │                  │
            │                   │  │ • DinD Engine  │                │ • DinD Engine  │                  │
            │                   │  └────────┬───────┘                └────────┬───────┘                  │
            │                   │           ▲                                 ▲                          │
            │                   │           │ Outbound Sub (Cascading)        │                          │
            │                   │           └─────────────────────────────────┘                          │
            │                   │                            ▲                                           │
            │                   │                            │                                           │
            │                   │                  ┌─────────┴──────┐                                    │
            │                   │                  │    vps-sub     │                                    │
            │                   │                  │   (sub.test)   │                                    │
            │                   │                  ├────────────────┤                                    │
            │                   │                  │ • Sub-Server   │                                    │
            │                   │                  │ • Caddy Proxy  │                                    │
            │                   │                  └────────┬───────┘                                    │
            │                   │                           ▲                                            │
            │                   │     Fetch Sub / Connect   │                                            │
            │                   │  ┌────────────────────────┴───┐         ┌───────────────────────────┐  │
            │                   │  │        test-client         │         │        echo-server        │  │
            │                   │  ├────────────────────────────┤  (VPN)  │       (echo.test:80)      │  │
            │                   │  │ • Runs XRay Core client    │────────>│ • Echoes Client Remote IP │  │
            │                   │  │ • SOCKS5/HTTP on :10808    │         │ • Validates Tunnel Path   │  │
            │                   │  └────────────────────────────┘         └───────────────────────────┘  │
            │                   └────────────────────────────────────────────────────────────────────────┘
            │                                               │
            └───────────────────────────────────────────────┘
```

---

## Уровень 1: Деплой-Тесты (Deployment Tests) `[СТАТУС: РЕАЛИЗОВАНО]`

Проверяют автоматическое развертывание нод и серверов из панели управления без участия пользователя.

| Скрипт | Режим | Проверяемые операции |
|:---|:---|:---|
| [`tests/deploy/test_deploy_freedom_node.py`](file:///Users/ilia.maksimov/dev/3x-ui-bootstRUp/tests/deploy/test_deploy_freedom_node.py) | `freedom_only` | Развертывание зарубежного узла: 3x-ui + Caddy L4 + Nginx decoy, создание inbounds VLESS TCP/XHTTP Reality, блокировка RU-трафика в routing rules, отдача валидной подписки. |
| [`tests/deploy/test_deploy_proxy_node.py`](file:///Users/ilia.maksimov/dev/3x-ui-bootstRUp/tests/deploy/test_deploy_proxy_node.py) | `proxy_only` | Развертывание прокси-ноды: подключение `FOREIGN_SUB_URL`, маршрутизация зарубежного трафика через Freedom-ноду, генерация подписок клиентов. |
| [`tests/deploy/test_deploy_sub_server.py`](file:///Users/ilia.maksimov/dev/3x-ui-bootstRUp/tests/deploy/test_deploy_sub_server.py) | `sub_only` | Развертывание сервера подписок: `subs-server` (Python 3.12) + Caddy, создание `nodes.json`, авторизация в веб-панели, раздача подписок клиентам. |
| [`tests/deploy/test_deploy_cascade.py`](file:///Users/ilia.maksimov/dev/3x-ui-bootstRUp/tests/deploy/test_deploy_cascade.py) | `cascade` | 2-стадийный деплой: Freedom VPS → автоматическая передача sub URL → Proxy VPS. Проверка TLS и ссылок на обоих узлах. |
| [`tests/deploy/test_deploy_cascade_sub.py`](file:///Users/ilia.maksimov/dev/3x-ui-bootstRUp/tests/deploy/test_deploy_cascade_sub.py) | `cascade_sub` | 3-стадийный деплой: Freedom VPS → Proxy VPS → Subscription Server VPS. Сквозная проверка генерации подписок через единый сервер. |

---

## Уровень 2: VPN-Тесты Сквозного Трафика (VPN Connectivity & Routing Tests)

Проверяют реальное сетевое туннелирование через ядро `xray-core` в изолированной Docker-сети.

### 🎯 Концепция Тестирования с `echo-server` (IP Reflect Target)
Так как все тесты запускаются локально на одной машине, запрос к внешнему `api.ipify.org` возвращал бы один и тот же внешний IP хоста (Mac).
Для точной проверки маршрутизации мы запускаем собственный легковесный контейнер **`echo-server`** (домен `echo.test` в сети `testnet`).

Когда клиент делает запрос к `http://echo.test/ip` через VPN:
- Сервер возвращает IP адрес, с которого физически пришел TCP пакет: `self.client_address[0]`.
- **Прямой выход через Freedom**: `echo-server` видит IP контейнера `vps-freedom`.
- **Каскадный выход Proxy → Freedom**: клиент подключается к `vps-proxy`, трафик туннелируется в `vps-freedom` и выходит в сеть — `echo-server` видит IP контейнера `vps-freedom` (100% подтверждение работы каскада!).
- **Прямой трафик (Bypass RU на Proxy)**: при обращении к simulated RU хостам на Proxy-ноде запрос идет direct — `echo-server` видит IP контейнера `vps-proxy`.

```
┌─────────────────┐   VLESS Reality    ┌──────────────┐   VLESS Reality   ┌──────────────┐     HTTP       ┌────────────────────────┐
│ test-client     │ ─────────────────> │  vps-proxy   │ ────────────────> │ vps-freedom  │ ─────────────> │ echo-server            │
│ (xray-core)     │                    │ (172.28.0.3) │  (Foreign Tunnel) │ (172.28.0.2) │                │ (echo.test:80)         │
└─────────────────┘                    └──────────────┘                   └──────────────┘                └───────────┬────────────┘
         │                                                                                                            │
         └─────────────────────────────── Expects Remote IP == 172.28.0.2 ────────────────────────────────────────────┘
```

---

### Сценарии VPN-Тестов (`tests/vpn/`):

```bash
# Запуск всех VPN тестов:
./tests/vpn/run_vpn_tests.sh all

# Запуск конкретного теста:
./tests/vpn/run_vpn_tests.sh freedom
./tests/vpn/run_vpn_tests.sh proxy
./tests/vpn/run_vpn_tests.sh sub
./tests/vpn/run_vpn_tests.sh cascade
./tests/vpn/run_vpn_tests.sh cascade_sub
```

### 1. `test_vpn_freedom_node.py` (Прямое подключение к Freedom Node) — ✅ PASSED
- **Сценарий**: Клиент скачивает подписку `https://freedom.test/.../freedom-direct-client`, генерирует конфиг XRay и выходит в интернет.
- **Проверки**:
  - `curl --socks5 ... http://echo.test/ip` возвращает IP Freedom-ноды (`vps-freedom`).
  - Проверены протоколы **VLESS TCP Reality** и **VLESS XHTTP Reality**.

### 2. `test_vpn_proxy_node.py` (Российский узел Proxy Only) — ✅ PASSED
- **Сценарий**: Клиент подключается к `proxy.test:443`, трафик туннелируется во Freedom Node через `FOREIGN_SUB_URL`.
- **Проверки**:
  - Запрос к `http://echo.test/ip` возвращает IP Freedom-ноды (`vps-freedom`).
  - Проверены протоколы **VLESS TCP Reality** и **VLESS XHTTP Reality**.

### 3. `test_vpn_sub_server.py` (Subscription Server Standalone) — ✅ PASSED
- **Сценарий**: Клиент запрашивает ссылку с сервера подписок `https://sub.test/subs/...`, получает VLESS профиль и подключается.
- **Проверки**:
  - Динамическая выдача подписки с декодированием `vless://`.
  - Успешный выход через выданный профиль в целевую сеть.

### 4. `test_vpn_cascade.py` (2-Стадийный каскад Freedom + Proxy) — ✅ PASSED
- **Сценарий**: Клиент подключается к `proxy.test:443`, трафик каскадируется во `freedom.test:443` -> `echo.test`.
- **Проверки**:
  - Запрос к `http://echo.test/ip` возвращает IP Freedom-ноды (`vps-freedom`).
  - Проверены протоколы **VLESS TCP Reality** и **VLESS XHTTP Reality**.

### 5. `test_vpn_cascade_sub.py` (3-Стадийный каскад Freedom + Proxy + Sub-Server) — ✅ PASSED
- **Сценарий**: Полная цепочка: Sub-Server (`sub.test`) -> Proxy (`proxy.test`) -> Freedom (`freedom.test`) -> `echo-server`.
- **Проверки**:
  - Получение подписки с сервера подписок.
  - Подключение к российскому прокси и сквозной выход через зарубежную ноду с проверкой исходного IP Freedom-ноды.

---

## Уровень 3: UI-Тесты Веб-Интерфейсов (UI & Frontend Tests) `[СТАТУС: ПОЛНОСТЬЮ РЕАЛИЗОВАНО]`

> **Инструмент**: Headless Chromium через **Playwright** (`.python_env`).
> Запускает изолированные инстансы серверов в песочнице и тестирует реальный DOM, WebCrypto, сессии и все пользовательские сценарии без моков бизнес-логики.

```bash
# Запуск всех UI тестов:
./tests/ui/run_ui_tests.sh all

# Запуск конкретного набора:
./tests/ui/run_ui_tests.sh servers   # Сейф серверов и PIN
./tests/ui/run_ui_tests.sh wizard    # Визард, режимы и валидация
./tests/ui/run_ui_tests.sh terminal  # SSE логи и отмена деплоя
./tests/ui/run_ui_tests.sh sub       # Панель сервера подписок

# Или через мастер-раннер:
./tests/run_all_tests.sh ui
```

### 1. Локальная Панель Управления (`localhost:8000`)
- **Управление серверами и PIN-шифрование (`test_ui_server_management.py`)** — ✅ **PASSED (7s)**:
  - Ввод Master PIN, генерация ключа через WebCrypto `PBKDF2` (600k итераций) + `AES-GCM`.
  - Добавление карточки сервера, рендеринг в DOM.
  - **Проверка безопасности**: `servers.json` на диске содержит строго зашифрованный ciphertext, пароли в открытом виде отсутствуют.
  - Блокировка сервера (`locked: true`) — защита от случайного изменения/удаления (кнопка `disabled`).
  - Автоподстановка параметров сервера в активную форму деплоя («Заполнить поля»).
  - Сброс сейфа серверов через подтверждение модального окна и удаление `servers.json`.
- **Визард, динамические режимы и сессионный стейт (`test_ui_wizard_modes.py`)** — ✅ **PASSED (10s)**:
  - Переключение режимов: Cascade, Cascade + Sub, Freedom Single, Recovery, Maintenance.
  - Динамическое отображение/скрытие секций серверов на Шаге 2 в зависимости от архитектуры.
  - Навигация по шагам визарда вперед/назад с сохранением введенных значений.
  - **Автосохранение `setup_backup.yml`**: проверка очистки паролей и SSH-ключей на диске.
  - Восстановление формы после перезагрузки страницы (F5).
  - Клиентская валидация (блокировка перехода на Шаг 3 при пустых хостах и вывод ошибок).
- **Терминал развертывания, SSE и API управления (`test_ui_terminal_and_control.py`)** — ✅ **PASSED (5s)**:
  - Автозагрузка доступных версий 3x-ui из `/api/xui_versions` в выпадающий список.
  - Стриминг Server-Sent Events (SSE) в терминал с ANSI-подсветкой.
  - Остановка деплоя: клик «Остановить деплой», подтверждение в `#customConfirmModal`, вызов `/api/deploy/stop` и фиксация флага отмены на бэкенде.

### 2. Панель Сервера Подписок (`https://sub.test/subs`)
- **Авторизация, клиенты и оверрайды (`test_ui_sub_server_panel.py`)** — ✅ **PASSED (3s)**:
  - Авторедирект неавторизованного пользователя на `/subs/login`.
  - Отклонение неверных учетных данных с выводом ошибки.
  - Успешный логин, установка сессионной cookie и вход в дашборд.
  - Рендеринг карточек нод и списков клиентов из `nodes.json`.
  - Добавление клиента и наложение custom override с фиксацией в `force-subs.yml`.

---

## Уровень 4: Регрессионные Тесты и Жизненный Цикл (Regression & Lifecycle Tests)

Проверяют сохранение данных, совместимость версий, восстановление после сбоев и операции технического обслуживания.

### 1. `test_regression_backup_recovery.py` (Миграция Версий и Замена Доменов)
- **Сценарий**:
  1. Развертывание ноды на более старой версии 3x-ui (например, `2.4.8`) с набором клиентов.
  2. Создание резервной копии (`mode: backup`): создание архива `./working/` и скачивание в `./backups_panel/`.
  3. Полная очистка ноды (симуляция потери сервера).
  4. Восстановление (`mode: recovery`) из бэкапа на новую версию 3x-ui (`3.6.0`) с **новым доменом** (`recovery.test`).
- **Проверки**:
  - Целостность базы SQLite (`/etc/x-ui/x-ui.db`).
  - Автоматическая замена старого домена на новый во всех конфигах Caddy и XRay.
  - Сохранение клиентских UUID, ключей Reality и истории трафика.
  - Работоспособность панели управления и выпуска нового TLS-сертификата.

### 2. `test_regression_update_3xui.py` (Бесшовное Обновление 3x-UI)
- **Сценарий**:
  1. Развертывание ноды с версией 3x-ui `XUI_VERSION=2.4.8`.
  2. Запуск операции `mode: update_3xui` с целевой версией `XUI_VERSION=3.6.0`.
- **Проверки**:
  - Автоматическое создание пред-обновленческого бэкапа перед модификацией контейнеров.
  - Обновление Docker-образа и перезапуск контейнера `3xui`.
  - Проверка доступности API 3x-ui и сохранения всех inbounds после апгрейда.

### 3. `test_regression_freedom_replacement.py` (Замена Заблокированного Узла Каскада)
- **Сценарий**:
  1. Работает каскад (Freedom 1 + Proxy 1).
  2. Имитация блокировки Freedom 1 (остановка контейнера или смена IP).
  3. Развертывание новой зарубежной ноды в режиме `freedom_component` на `vps-freedom-new`.
  4. Автоматическое обновление `FOREIGN_SUB_URL` на российской Proxy-ноде.
- **Проверки**:
  - Proxy-нода подхватывает новый зарубежный сервер без пересоздания российских клиентов.
  - Восстановление туннелирования трафика без простоя клиентов.

### 4. `test_regression_sub_server_lifecycle.py` (Жизненный Цикл Сервера Подписок)
- **Сценарий**:
  1. Создание бэкапа сервера подписок (`mode: backup_sub`) — архивация `nodes.json` и `force-subs.yml`.
  2. Модификация списка клиентов или обновление кода (`mode: update_sub`).
  3. Выполнение отката (`mode: rollback_sub`) к предыдущему сохраненному состоянию.
- **Проверки**:
  - Восстановление реестра `nodes.json` и переопределений из бэкапа.
  - Непрерывность раздачи подписок.

### 5. `test_regression_restarts.py` (Устойчивость к Перезагрузкам и Сбоям)
- **Сценарий**:
  1. Выполнение операций `restart_panel` (перезапуск Docker-сервисов) и `restart_server` (reboot VPS).
  2. Перезапуск демона Docker (`dockerd`).
- **Проверки**:
  - Автозапуск контейнеров благодаря политике `restart: unless-stopped`.
  - Автоматическое восстановление TLS в Caddy и соединений XRay Core.

---

## 📋 Сводная Матрица Всех Тестов

| Категория | Файл / Модуль | Описание | Окружение |
|:---|:---|:---|:---|
| **Деплой** | [`test_deploy_freedom_node.py`](file:///Users/ilia.maksimov/dev/3x-ui-bootstRUp/tests/test_deploy_freedom_node.py) | Деплой зарубежного узла (VLESS Reality) | Docker (`vps-freedom`) |
| **Деплой** | [`test_deploy_proxy_node.py`](file:///Users/ilia.maksimov/dev/3x-ui-bootstRUp/tests/test_deploy_proxy_node.py) | Деплой прокси-ноды (Россия) с каскадом | Docker (`vps-proxy`) |
| **Деплой** | [`test_deploy_sub_server.py`](file:///Users/ilia.maksimov/dev/3x-ui-bootstRUp/tests/test_deploy_sub_server.py) | Деплой сервера подписок (Python 3.12) | Docker (`vps-sub`) |
| **Деплой** | [`test_deploy_cascade.py`](file:///Users/ilia.maksimov/dev/3x-ui-bootstRUp/tests/test_deploy_cascade.py) | 2-стадийный каскад Freedom → Proxy | Docker (`vps-freedom`, `vps-proxy`) |
| **Деплой** | [`test_deploy_cascade_sub.py`](file:///Users/ilia.maksimov/dev/3x-ui-bootstRUp/tests/test_deploy_cascade_sub.py) | 3-стадийный каскад + сервер подписок | Docker (все 3 узла) |
| **VPN Трафик** | `tests/test_vpn_freedom.py` | Сквозной выход в интернет через Freedom | Docker (`test-client` + `vps-freedom`) |
| **VPN Трафик** | `tests/test_vpn_cascade.py` | Сквозной выход в интернет через каскад | Docker (`test-client` + каскад) |
| **UI** | `tests/test_ui_control_panel.py` | Панель управления: PIN, формы, SSE, SSH | Локальный веб-сервер (`:8000`) |
| **UI** | `tests/test_ui_sub_server.py` | Панель сервера подписок: auth, CRUD, overrides | Docker (`vps-sub:443`) |
| **Регресс** | `tests/test_regression_backup_recovery.py` | Бэкап на старой версии → Рекавери на новой + смена домена | Docker VPS |
| **Регресс** | `tests/test_regression_update_3xui.py` | Обновление версии 3x-UI с автобэкапом | Docker VPS |
| **Регресс** | `tests/test_regression_component_replace.py` | Замена заблокированной Freedom-ноды в каскаде | Docker VPS |
| **Регресс** | `tests/test_regression_sub_lifecycle.py` | Бэкап, обновление и откат сервера подписок | Docker (`vps-sub`) |
| **Регресс** | `tests/test_regression_restarts.py` | Рестарт контейнеров и перезагрузка VPS | Docker VPS |

---

## ⚙️ Управление Запуском (`run_tests.sh`)

Скрипт [`run_tests.sh`](file:///Users/ilia.maksimov/dev/3x-ui-bootstRUp/run_tests.sh) поддерживает запуск отдельных групп или полного набора тестов:

```bash
# Деплой-тесты:
./run_tests.sh deploy          # Все тесты деплоя

# VPN-тесты:
./run_tests.sh vpn             # Все сквозные тесты трафика

# UI-тесты:
./run_tests.sh ui              # Все UI тесты

# Регрессионные тесты:
./run_tests.sh regression      # Все тесты миграции, бэкапов и обновлений

# Полный прогон перед релизом/пушем:
./run_tests.sh all
```
