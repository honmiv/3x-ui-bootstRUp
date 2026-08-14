# 3x-ui Deployment Manager

## ✨ Возможности

- **Удалённый деплой 3x-ui** — развёртывание панели на VPS с подключением по SSH (пароль или SSH-ключ)
- **Автоустановка ПО на удалённом сервере** — скрипт можно запускать сразу после создания VPS у провайдера
- 🌐 **Собственный сервер подписок** — единая ссылка клиента на подписку остаётся доступной даже при блокировке VPN-сервера. Всех пользователей можно единоразово перевести на другие ноды: переразвернуть сервер подписок или изменить назначения серверов в его веб-интерфейсе.
- **Режимы развёртывания:**
  - 🟢 **Single** — подразумевается, что 3x-ui панель будет развернута на зарубежном сервере для доступа к заблокированным ресурсам. Трафик на RU (geoip:ru \ geosite:category-ru заблокирован)
  - 🔗 **Cascade** — каскад из двух нод: 
    - Зарубежная (freedom) - трафик на RU (geoip:ru \ geosite:category-ru) заблокирован
    - Локальная (Proxy).  - трафик на RU (geoip:ru \ geosite:category-ru) идёт напрямую, остальной трафик идёт на зарубежную ноду
  - 📦 **Cascade + Subscription Server** — каскад с развёртыванием отдельного саб-сервера.
  - 📡 **Sub-only** — автономный сервер подписок для уже настроенной панели
  - 🛰 **Proxy-only / Freedom-only** — развёртывание только одного компонента - может быть полезно, если одна из нод была забанена.
- **Генерация клиентов** — массовое создание клиентов через списки для протоколов **vless + TCP (Reality)** и **vless + XHTTP (Reality)**.
- **Бэкапы:** - полезно при переносе панелей с забаненых серверов без потери настроек
  - 💾 Создание бэкапа панели и саб-сервера на удалённом сервере с загрузкой архивов на локальную машину (`backups_panel/`, `backups_sub_server/`).
  - ♻️ Восстановление из бэкапа на новом сервере с автозаменой домена.
- **Обновление 3x-ui** — выбор версии из актуального списка, автоматический бэкап перед обновлением.
- **Обслуживание** — перезапуск панели, перезапуск сервера, перезапуск саб-сервера в один клик.
- **Проверка SSH-подключения** до начала любых операций.
- **Кроссплатформенность** — запуск на Windows (CMD/PowerShell), Linux и macOS (Bash/Zsh).
- **Менеджер серверов** — возможность локально сохранить данные для доступа к серверу для последующего переиспользования

> ⚠️ **Важно:** при настройке панелей не используются никакие сторонние сервисы. Всё происходит на вашей локальной машине и на серверах, которые вы указали.
---
### 3x-ui Deployment Manager
#### Настройка 3x-ui на удалённых серверах с помощью удобного веб интерфейса
![Web UI](preview-3x-ui-deployment-manager.png)
### Сервер подписок
#### Прокси для подписок VLESS - позволяет не менять url подписки при блокировке VLESS-сервера
![subs-server](preview-subscriptions-server.png)
---

## 🚀 Быстрый запуск 3x-ui Deployment Manager'а

### 🐧 🍎 Linux / macOS (Bash / Zsh)
```bash
curl -fsSL https://github.com/honmiv/3x-ui-bootstRUp/archive/refs/heads/master.tar.gz | tar -xz && cd 3x-ui-bootstRUp-master && ./start_3x_ui_deployment_manager.sh
```

### 💻 Windows CMD (cmd.exe)
```cmd
curl -fsSL https://github.com/honmiv/3x-ui-bootstRUp/archive/refs/heads/master.zip -o 3x-ui.zip && powershell -Command "Expand-Archive -Path '3x-ui.zip' -DestinationPath '.' -Force" && cd 3x-ui-bootstRUp-master && start_3x_ui_deployment_manager.bat
```

### ⚡ Windows PowerShell
```powershell
iwr -useb https://github.com/honmiv/3x-ui-bootstRUp/archive/refs/heads/master.zip -OutFile 3x-ui.zip; Expand-Archive 3x-ui.zip -DestinationPath . -Force; cd 3x-ui-bootstRUp-master; .\start_3x_ui_deployment_manager.ps1
```
