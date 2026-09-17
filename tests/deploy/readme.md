# Интеграционные тесты деплоя (Deploy Test Suite)

В данной директории находятся интеграционные тесты развёртывания компонентов **3x-UI BootstRUp** в изолированном окружении **Docker-in-Docker (DinD)**.

---

## 📋 Состав тестов

| Файл | Режим деплоя (`deploy_mode`) | Описание сценария |
|------|------------------------------|-------------------|
| `test_deploy_freedom_node.py` | `freedom_only` | Развёртывание одиночной зарубежной ноды (Freedom) |
| `test_deploy_proxy_node.py` | `proxy_only` | Развёртывание локальной прокси-ноды с исходящим подключением к Freedom-ноде |
| `test_deploy_cascade.py` | `cascade` | Двухэтапный каскад: сначала Freedom-нода, затем Proxy-нода с каскадной подпиской |
| `test_deploy_sub_server.py` | `sub_only` | Автономный сервер подписок с подключением существующих нод |
| `test_deploy_freedom_sub.py` | `freedom_sub` | Двухэтапный деплой: Freedom-нода + выделенный сервер подписок |
| `test_deploy_cascade_sub.py` | `cascade_sub` | Полный трехэтапный каскад: Freedom-нода + Proxy-нода + сервер подписок |

---

## 🏗 Архитектура окружения Docker-in-Docker (DinD)

Каждый удалённый VPS в тестах эмулируется с помощью контейнера на базе образа `test-vps:latest` (`tests/Dockerfile.vps`):
- Базовая ОС: Debian 12 (Bookworm) с установленным Docker CE, containerd, OpenSSH-сервером и набором утилит (`curl`, `jq`, `openssl`, `sed`, `awk`, `gawk`, `tar`, `procps`).
- Внутри каждого VPS-контейнера запущен **собственный независимый демон Docker (`dockerd`)**.
- Контейнеры запускаются с флагом `--privileged`, что позволяет внутреннему демону Docker управлять cgroups, iptables и сетевыми интерфейсами.
- SSH-сервер слушает стандартный порт 22 внутри контейнера, который проброшен на уникальные порты локального хоста (диапазон `2221–2263`). Аутентификация: `root:root`.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ ХОСТ (Тестовый раннер, pytest / run_deploy_tests.sh)                        │
│                                                                             │
│  Внешняя сеть Docker: testnet (172.18.0.0/16)                               │
│  ┌───────────────────────────────┐     ┌──────────────────────────────────┐ │
│  │ Контейнер vps-cascade-freedom │     │ Контейнер vps-cascade-proxy      │ │
│  │ IP в testnet: 172.18.0.x      │     │ IP в testnet: 172.18.0.y         │ │
│  │ SSH: 127.0.0.1:2231           │     │ SSH: 127.0.0.1:2232              │ │
│  │                               │     │                                  │ │
│  │  ┌── Внутренний dockerd ────┐ │     │  ┌── Внутренний dockerd ───────┐ │ │
│  │  │ Сеть: 3xui-caddy-net     │ │     │  │ Сеть: 3xui-caddy-net        │ │ │
│  │  │ • 3xui                   │ │     │  │ • 3xui                      │ │ │
│  │  │ • caddy                  │ │     │  │ • caddy                     │ │ │
│  │  │ • nginx-decoy            │ │     │  │ • nginx-decoy               │ │ │
│  │  └──────────────────────────┘ │     │  └─────────────────────────────┘ │ │
│  └───────────────────────────────┘     └──────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## ⚙️ Допущения и адаптации для тестирования в DinD

Реальный процесс деплоя рассчитан на публичные VPS с белыми IP, публичными DNS-записями и внешним доступом к центрам сертификации Let's Encrypt / ZeroSSL. Для полного тестирования в изолированном DinD применены следующие допущения:

### 1. Двухуровневая адресация и недоступность `host.docker.internal`
- **Проблема**: В реальном развёртывании сервисы общаются по публичным доменам или через `host.docker.internal`. Внутри DinD обращение к `host.docker.internal` или `127.0.0.1` из внутреннего контейнера (например, `subs-server` или `3xui`) попадает во внутренний виртуальный `docker0` данного VPS, а не на соседний VPS и не на реальный хост.
- **Решение**:
  - Используется механизм тестовых переопределений `tests/overrides/ssh_deployer_test_overrides.py` через функцию `install_dind_overrides(proxy_container, freedom_container)`.
  - Резолвер `resolve_sub_server_urls` подменяется monkey-patching'ом. Он определяет реальные IP контейнеров-VPS во внешней сети `testnet` через `get_outer_docker_ip()` и переписывает URL бэкендов в формат:
    - `http://proxy-docker:80/<sub_path>`
    - `http://freedom-docker:80/<sub_path>`
  - В `tests/overrides/sub-server/process_templates.sh` на этапе генерации конфигурации в `docker-compose.yml` саб-сервера динамически инжектируется секция `extra_hosts`:
    ```yaml
    extra_hosts:
      - "proxy-docker:${TEST_PROXY_DOCKER_IP}"
      - "freedom-docker:${TEST_FREEDOM_DOCKER_IP}"
      - "host.docker.internal:host-gateway"
    ```

### 2. Локальные самоподписанные сертификаты Caddy (`local_certs`)
- **Проблема**: В изолированной сети без публичного DNS валидация ACME-сертификатов (Let's Encrypt / ZeroSSL) через порт 80/443 невозможна и приводит к таймауту.
- **Решение**:
  - В тестовом шаблоне `tests/overrides/panel/templates/caddy/Caddyfile.template` и `tests/overrides/sub-server/templates/caddy/Caddyfile.template` включена директива `local_certs`.
  - Caddy мгновенно генерирует валидные TLS-сертификаты с помощью внутреннего центра сертификации (Caddy Local Authority).
  - Скрипт `wait_for_ssl.sh` заменён оверрайдом `tests/overrides/panel/wait_for_ssl.sh`, который за 1–3 секунды валидирует ответ Caddy по HTTPS через `curl -sk --resolve "${DOMAIN}:443:127.0.0.1"` вместо 300-секундного ожидания публичного сертификата.

### 3. Межсерверный опрос подписок по незашифрованному HTTP `:80`
- **Проблема**: Внутренний контейнер `subs-server` на Python или `3xui` при попытке скачать каскадную подписку по HTTPS натыкался бы на ошибку проверки самоподписанного сертификата Caddy (`SSL: CERTIFICATE_VERIFY_FAILED`).
- **Решение**:
  - В тестовом оверрайде `Caddyfile.template` блок `http://:80` дополнен проксированием эндпоинта подписки:
    ```caddyfile
    http://:80 {
        @sub_path path /{{XUI_SUB_PATH}}/*
        route {
            reverse_proxy @sub_path 3xui:{{XUI_SUB_PORT}}
            reverse_proxy nginx-decoy:80
        }
    }
    ```
  - Это позволяет саб-серверу опрашивать ноды по пути `http://<node-docker>:80/<sub_path>` стабильно и быстро без необходимости монтировать CA-сертификаты внутрь каждого контейнера.

### 4. Разрешение приватных адресов в 3x-ui для тестов (`allowPrivate=true`)
- **Проблема**: 3x-ui по умолчанию блокирует добавление подписок в `/outbound-subs`, если хост резолвится в приватную подсеть (RFC 1918, в том числе `172.16.0.0/12`), а Caddy в DinD использует локальные самоподписанные сертификаты. В продакшене для безопасности строго заданы `allowPrivate=false` и `allowInsecure=false`.
- **Решение**:
  - В репозитории боевой `panel/setup.sh` остаётся полностью чистым (`allowPrivate=false&allowInsecure=false`).
  - Тестовый хелпер `prepare_test_repo` в `tests/helpers.py` на лету подменяет эти флаги только во временной копии бандла перед деплоем на тестовый VPS, позволяя Proxy-ноде забирать каскадную подписку с Freedom-ноды по приватному IP Docker-сети `testnet` (`172.18.0.x`).

### 5. Прямой забор первой подписки в `setup.sh`
- **Проблема**: В боевом `panel/setup.sh` генерация ссылок клиента обращается к внешнему домену через интернет.
- **Решение**:
  - Оверрайд `tests/overrides/panel/build_sub_and_connect_urls.sh` опрашивает подписку напрямую с локального порта `XUI_SUB_PORT` контейнера `3xui` (`http://127.0.0.1:${XUI_SUB_PORT}/...`), что исключает зависимость от DNS хоста.

### 6. Кэширование образов Docker для ускорения
- **Особенность**: Для того чтобы тесты не скачивали гигабайты образов из интернета при каждом запуске, хост однократно скачивает/собирает образы (`ghcr.io/honmiv/caddy-l4:latest`, `ghcr.io/mhsanaei/3x-ui:3.6.0`, `nginx:1.27-alpine`, `python:3.12-alpine`, `ghcr.io/xtls/xray-core:latest`) и сохраняет их в `tests/.cache/*.tar`.
- Скрипт `entrypoint-vps.sh` монтирует этот каталог в `/var/cache/docker-preload` и выполняет `docker load` при первом старте контейнера VPS.

---

## 🔍 Проверка результатов деплоя

Каждый тест деплоя проверяет следующие инварианты:
1. **Успех выполнения `run_deployment`**: функция возвращает `(True, result_dict)`.
2. **Работоспособность внутренних контейнеров**: `check_inner_containers_running(vps, ["3xui", "caddy", "nginx-decoy"])` (или `subs-server`).
3. **Сквозная проверка TLS с хоста**: с помощью `fetch_subscription_via_host_tls()` хостовый `curl` подключается к проброшенному порту HTTPS (`8441–8472`) с опцией `--resolve {DOMAIN}:{PORT}:127.0.0.1`, проверяя реальную работу связки Caddy -> 3x-ui / subs-server.
4. **Декодирование подписки**: тело ответа подписки успешно декодируется из base64 и содержит валидные VLESS-ссылки (`vless://...`).

---

## 🚀 Запуск тестов

```bash
# Запуск всех тестов деплоя параллельно (рекомендуется)
./tests/deploy/run_deploy_tests.sh

# Запуск конкретного теста одиночно
python3 tests/deploy/test_deploy_cascade_sub.py
```

