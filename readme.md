# 3x-ui bootstRUp

Automated 3x-ui + Caddy setup for a VPS with a domain.

Автоматическая установка 3x-ui + Caddy на VPS с доменом.

---

# Prerequisites / Требования

<details open>
<summary><b><img src="https://raw.githubusercontent.com/lipis/flag-icons/main/flags/4x3/gb.svg" style="height: 1em; vertical-align: -0.15em;"> English</b></summary>

* **OS (Tested on):** Ubuntu 26.04, Debian 13, CentOS 9
* **Domain Setup:** Point your domain to the VPS IP address:
  * **A record** for all IPv4 addresses
  * **AAAA record** for all IPv6 addresses (if provided by your VDS vendor)
* **Ports:** `80` and `443` must be available
* **Dependencies:** `curl` installed
</details>
<br/>
<details open>
<summary><b><img src="https://raw.githubusercontent.com/lipis/flag-icons/main/flags/4x3/ru.svg" style="height: 1em; vertical-align: -0.15em;"> Русский</b></summary>

* **ОС (Протестировано на):** Ubuntu 26.04, Debian 13, CentOS 9
* **Настройка домена:** Направьте доменное имя на IP-адрес VPS:
  * **A-запись** для всех IPv4 адресов
  * **AAAA-запись** для всех IPv6 адресов (если предоставляются вашим VDS-провайдером)
* **Порты:** `80` и `443` должны быть свободны
* **Зависимости:** установленные `curl`
</details>

---

# Installation / Установка

```shell
curl -fsSL https://raw.githubusercontent.com/honmiv/3x-ui-bootstRUp/master/install.sh | bash
```
