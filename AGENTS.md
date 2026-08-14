---
name: 3x-UI BootstRUp Architecture Guide
description: Comprehensive project architecture, components, and code navigation guide for AI agents
category: architecture
---

# 3x-UI BootstRUp: Architecture & Agent Navigation Guide

## Project Overview

**3x-UI BootstRUp** is a sophisticated cross-platform infrastructure-as-code tool for deploying and managing multi-node proxy networks (3x-UI panels). It automates the deployment of XRay-based VPN/proxy infrastructure with cascading node architectures, subscription management, and centralized administration.

### Business Problem & Goal (Бизнес-задача)
**The Problem**: Users in regions with strict internet censorship (like Russia, Iran, China) face deep packet inspection (DPI) and active probing that blocks standard VPNs. Direct connections to foreign servers are often detected and blocked.
**The Solution**: 3x-UI BootstRUp automates the complex deployment of multi-node proxy networks that resist DPI. By routing traffic through a domestic "proxy" node (which looks like normal domestic traffic to ISPs) and then tunneling to a foreign "freedom" node, it bypasses restrictions. The project abstracts this complex Docker, Caddy, and XRay configuration behind a simple, local web interface so non-technical administrators can deploy censorship-resistant infrastructure in minutes.

**Key Capabilities**:
- Deploy XRay proxy panels to remote VPS servers via SSH
- Manage single or cascading multi-node setups (Russian node → Foreign node → Subscription server)
- Handle backups, recovery, version updates, and server maintenance
- Provide local web UI for configuration and monitoring
- Centralized subscription management through dedicated subscription servers
- Support for multiple deployment architectures and maintenance modes

---

## System Architecture

### High-Level Deployment Model

```
┌─────────────────────────────────────────────────────────────────┐
│                      LOCAL MACHINE                              │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │  3x-UI BootstRUp Control Panel (localhost:8000)             ││
│  │  ┌──────────────────┐              ┌──────────────────┐     ││
│  │  │  Web UI (HTML)   │ ←→ ←→ ←→ ←→ │ main.py (http.server) │ │
│  │  │ • Forms          │  (HTTP)      │ • Routes        │    ││
│  │  │ • Logs (SSE)     │              │ • State mgmt    │    ││
│  │  └──────────────────┘              └────────┬─────────┘    ││
│  │                                             │               ││
│  │                                    ┌────────▼──────────┐   ││
│  │                                    │ ssh_deployer.py   │   ││
│  │                                    │ • SSH executor    │   ││
│  │                                    │ • File transfers  │   ││
│  │                                    │ • Orchestration   │   ││
│  │                                    └───────┬──────────┘   ││
│  └────────────────────────────────────────────┼────────────────┘│
└──────────────────────────────────────────────┼─────────────────┘
                                               │ SSH (port 22)
                    ┌──────────────────────────┼──────────────────────┐
                    │                          │                      │
          ┌─────────▼──────┐          ┌───────▼────────┐    ┌────────▼──────┐
          │ FREEDOM NODE   │          │ PROXY NODE     │    │ SUB-SERVER    │
          │ (Foreign VPS)  │          │ (Russian VPS)  │    │ (Standalone)  │
          ├────────────────┤          ├────────────────┤    ├───────────────┤
          │ • 3x-UI Panel  │          │ • 3x-UI Panel  │    │ • Caddy       │
          │ • Caddy L4     │          │ • Caddy L4     │    │ • subs-server │
          │ • Nginx Decoy  │          │ • Nginx Decoy  │    │ • Python 3.12 │
          │ • Docker       │          │ • Docker       │    │ • Docker      │
          └────────────────┘          └────────────────┘    └───────────────┘
               ↑                             ↑
               │ VLESS Reality              │ VLESS Reality
               │ (TCP Port 443)             │ (TCP Port 443)
               └─────────────┬──────────────┘
                             │
                    [Client VPN Connections]
```

### Component Relationship Map

```
main.py (Orchestrator)
  ├─→ Panel Deployment (Freedom + Proxy nodes)
  │   ├─→ ssh_deployer.exec_command() → panel/setup.sh
  │   ├─→ Template processing (panel/templates/*)
  │   └─→ Configuration via setup_backup.yml
  │
  ├─→ Sub-Server Deployment (Optional cascade architecture)
  │   ├─→ ssh_deployer.exec_command() → sub-server/setup.sh
  │   ├─→ Template processing (sub-server/templates/*)
  │   └─→ Receives subscription URLs from panel nodes
  │
  └─→ Maintenance Operations
      ├─→ backup_panel / recovery_panel
      ├─→ update_3xui
      ├─→ restart_panel / restart_server / restart_sub
      ├─→ update_sub / backup_sub / rollback_sub
      └─→ update_sources (git pull on remote)
```

---

## Core Components

### 1. Local Control Plane

**Files**: `main.py`, `ssh_deployer.py`, `setup_backup.yml`, `servers.json`

#### main.py - HTTP Server & Orchestrator
- **Role**: Entry point, HTTP server (127.0.0.1:8000 via `http.server.ThreadingHTTPServer`), UI routing, deployment dispatch
- **Key Functions**:
  - Serves web UI (HTML/CSS/JS from `panel/static/`)
  - Routes POST requests from forms to `ssh_deployer` functions
  - Manages session state between deployments (globals `active_logs`, `is_deploying`, `deploy_status`, `deploy_result`, `cancel_requested`)
  - Streams real-time logs to UI via Server-Sent Events (SSE) at `/api/deploy/logs`
  - Loads/saves deployment configurations in YAML format (`setup_backup.yml`)
  - `fetch_xui_versions()`: fetches available 3x-ui Docker tags from ghcr.io (token + tags API, 300s cache) for the version dropdown
- **API Endpoints**:
  - `GET/POST /api/config` - load/save form state (passwords and `*_key` stripped)
  - `GET /api/xui_versions`, `GET /api/backups`, `GET /api/status`
  - `GET/POST /api/servers`, `DELETE /api/servers/reset` - saved VPS profiles
  - `POST /api/deploy`, `GET /api/deploy/logs` (SSE), `POST /api/deploy/stop` - run/cancel deployments
  - `POST /api/ssh/test` - pre-flight SSH connection test
  - `POST /api/update_sources` - git pull on remote
  - `POST /api/restart`, `POST /api/shutdown` - restart/shutdown the local control panel
- **When to Look Here**:
  - Adding new web form endpoints
  - Changing UI routing or log streaming behavior
  - Modifying deployment flow or orchestration sequence
  - Handling user input and validation

#### ssh_deployer.py - Remote Execution Engine
- **Role**: Core deployment logic, SSH/SCP operations, remote command execution
- **Key Functions**:
  - `SSHDeployer` class: Async SSH/SCP wrapper that shells out to the system `ssh`/`scp` binaries (password auth via `SSH_ASKPASS`; optional private key)
  - `exec_command()`: Execute remote shell commands with logging; supports `stdin_data` streaming (used to upload files/bundles)
  - `download_file()`: SCP download from the remote host
  - `get_bundle_bytes()`: Builds a tar.gz of the whole repo (excludes `.git`, `.python_env`, `__pycache__`, `panel/static`, `*.pyc`, `setup_backup.yml`) that is streamed to the remote `/opt/3x-ui-bootstRUp` directory
  - `parse_deployment_results()`: Extracts panel URL + client subscriptions (sub/tcp/xhttp) from the structured, marker-delimited JSON block (`===RESULT_JSON_START===` to `===RESULT_JSON_END===`) printed at the end of `setup.sh` output
  - `run_deployment()`: Master orchestration function (handles all deployment modes)

- **Deployment Modes** (handled in `run_deployment()`):
  1. **single** - Deploy one standalone panel (node type `custom`, no RU blocking)
  2. **cascade** - Deploy two panels (freedom → proxy with subscription URL)
  3. **cascade_sub** - Deploy panels + subscription server (3 stages)
  4. **sub_only** - Deploy only subscription server
  5. **proxy_only** / **freedom_only** / **freedom_component** - Deploy a single cascade component (useful when a node was banned)
  6. **backup** - Create remote ./working/ archive, download to ./backups_panel/
  7. **recovery** - Restore from backup, auto-replace domain
  8. **update_3xui** - Upgrade 3x-ui version (creates pre-update backup first)
  9. **restart_panel** / **restart_server** - Restart panel containers or reboot the VPS
  10. **restart_sub** / **update_sub** / **backup_sub** / **rollback_sub** - Subscription server maintenance

- **When to Look Here**:
  - Debugging SSH/connection issues
  - Adding new deployment modes
  - Modifying deployment sequence or error handling
  - Changing file transfer mechanisms
  - Understanding how templates are processed on remote servers

#### setup_backup.yml - Session Persistence
- **Role**: Store deployment form data between sessions
- **Format**: YAML with sections per deployment mode (secrets stripped, see Code Patterns below)
- **Example Structure**:
  ```yaml
  common:
    deploy_mode: cascade
    vps_host: 1.2.3.4
    vps_port: 22
    vps_user: root
    vps_auth_type: password

  freedom_node:
    host: 1.2.3.4
    port: 22
    username: root
    domain: freedom.example.com

  proxy_node:
    host: 5.6.7.8
    port: 22
    username: root
    domain: proxy.example.com
    foreign_sub_url: https://freedom.example.com/subs
  ```
  **Important**: passwords and `*_key` fields are stripped by `save_backup_config()` on every save — credentials are never persisted.

- **When to Look Here**:
  - Resuming incomplete deployments
  - Modifying form state persistence
  - Debugging configuration loading/saving

#### servers.json - Saved VPS Profiles (PIN-encrypted)
- **Role**: Quick-select list of previously configured servers
- **Format**: JSON object with credentials encrypted via PBKDF2 (100k iterations) + AES-GCM under a user-set PIN; plaintext never stored
- **When to Look Here**:
  - Adding server profile management features
  - Changing credential encryption or storage

---

### 2. Panel Component (3x-UI Nodes)

**Location**: `panel/` directory
**Deployed To**: Freedom and Proxy VPS nodes

#### Panel Structure
```
panel/
├── setup.sh              # Remote deployment script (runs on VPS)
├── static/               # Web UI assets for local control panel
│   ├── index.html        # Main dashboard
│   ├── app.js            # Frontend logic (forms, logs, state)
│   └── style.css         # Dashboard styling
└── templates/            # Configuration templates ({{VARIABLE}} syntax)
    ├── users.yml         # (Optional) Initial users for 3x-ui
    └── 3x-ui/
    │   ├── vless-tcp-reality.template    # Inbound protocol config
    │   └── vless-xhttp-reality.template  # Alternative protocol
    ├── caddy/
    │   └── Caddyfile.template    # Reverse proxy config
    ├── docker-compose/
    │   ├── docker-compose.yml.template   # Service definitions
    │   └── Dockerfile-caddy-l4           # Custom Caddy with Reality (L4) support
    └── nginx-decoy/
        ├── default.conf.template  # Nginx reverse proxy config
        └── html/                  # Decoy website assets
            ├── index.html, access.html, operations.html, status.html, robots.txt
            ├── style.css
            └── errors/            # Error pages (400, 403, 404, 405, 50x)
```

#### panel/setup.sh - Remote Deployment Script
- **Role**: Runs on remote VPS, configures the entire panel deployment
- **Key Constants**: `PANEL_CONTAINER="3xui"`, `PANEL_API_PORT="2053"` (3x-UI web/API port), `REQUIRED_CMDS` (curl, jq, openssl, ss, qrencode, pgrep, base64, md5sum, awk, grep, sed)
- **Execution Flow**:
  1. Validate prerequisites (root access, Docker installed, required commands)
  2. Create working directory structure (./working/)
  3. Generate random ports (49152–65535) for `XUI_WEB_PORT`, `XUI_SUB_PORT`, `CADDY_GLOBAL_INTERNAL_PORT`, `TCP_REALITY_INBOUND_PORT`, `XHTTP_REALITY_INBOUND_PORT`
  4. Derive hidden admin web base path and subscription path from `SECRET_PHRASE` (md5 → 16 hex chars)
  5. Generate Reality keypair via `docker run ghcr.io/xtls/xray-core x25519`
  6. Process templates (substitute variables via sed)
  7. Configure 3x-UI through its HTTP API (admin/admin + CSRF token): login, create two inbounds (`vless-tcp-reality` id 1, `vless-xhttp-reality` id 2), set admin credentials
  8. Build and start Docker services (3xui, caddy, nginx-decoy)
  9. Wait for SSL certificate (up to 300s)
  10. Output subscription URLs and admin credentials
- **Node Types** (via `NODE_TYPE_CHOICE`):
  - `freedom` - Blocks `geoip:ru` / `geosite:category-ru` in XRay routing (for foreign nodes)
  - `proxy` - Routes foreign traffic via `outbound-subs` API (client traffic goes freedom node → internet)
  - `custom` - Standalone single node with no RU blocking
- **Environment Variables** (passed from main.py):
  ```bash
  # Core config
  DOMAIN                    # e.g., proxy.example.com
  XUI_VERSION               # e.g., 1.7.5 (Docker image tag)
  
  # Random ports (generated if not provided)
  XUI_WEB_PORT              # 3x-UI web UI internal port
  XUI_SUB_PORT              # subscription service internal port
  CADDY_GLOBAL_INTERNAL_PORT # Caddy https_port (e.g., 2000)
  TCP_REALITY_INBOUND_PORT  # VLESS TCP Reality inbound port
  XHTTP_REALITY_INBOUND_PORT # VLESS XHTTP Reality inbound port
  
  # Secrets & clients
  SECRET_PHRASE            # Used to derive hidden web base path + sub path (md5)
  CLIENTS_TCP_LIST         # Space-separated client UUIDs for TCP inbound
  CLIENTS_XHTTP_LIST       # Space-separated client UUIDs for XHTTP inbound
  
  # Cascade configuration
  CASCADE_CHOICE           # e.g., "true"/"false" (whether sub path is enabled)
  NODE_TYPE_CHOICE         # freedom | proxy | custom
  FOREIGN_SUB_URL          # URL to foreign node's subscription endpoint (proxy node only)
  
  # Admin credentials
  USERNAME                 # e.g., admin
  USER_PASSWORD            # Auto-generated if not provided
  ```

- **When to Look Here**:
  - Debugging remote deployment failures
  - Modifying Docker service configuration
  - Changing template variable substitution
  - Adding new services or ports
  - Adjusting SSL certificate handling

#### panel/templates/ - Configuration Templates

All templates use `{{VARIABLE}}` placeholder syntax (processed by sed on remote; the vars are exported env vars, see panel/setup.sh):

**Caddyfile.template**
- **Purpose**: Caddy reverse proxy configuration
- **Key Sections**:
  - Email for Let's Encrypt: `3xui@{{DOMAIN}}` (ZeroSSL + Let's Encrypt)
  - `https_port {{CADDY_GLOBAL_INTERNAL_PORT}}` + `auto_https disable_redirects` (L4 mode)
  - Layer 4 proxy on `:443` → `3xui:{{TCP_REALITY_INBOUND_PORT}}` (VLESS TCP Reality)
  - HTTP `:80` → nginx-decoy (defeats active probing)
  - HTTPS routing: `@sub_path` → 3xui subscription port, `@web_base_path` (hidden base path) → 3xui web port, everything else → nginx-decoy
- **Key Variables**:
  - `{{DOMAIN}}` - Public domain name
  - `{{TCP_REALITY_INBOUND_PORT}}` - Reality protocol inbound port
  - `{{CADDY_GLOBAL_INTERNAL_PORT}}` - Internal Caddy https_port
  - `{{XUI_SUB_PORT}}`, `{{XUI_WEB_PORT}}` - 3x-UI internal ports

**docker-compose.yml.template**
- **Purpose**: Define all Docker services and networking (network `3xui-caddy-net`)
- **Services**:
  - `3xui` - Main XRay panel (image `ghcr.io/mhsanaei/3x-ui:{{XUI_VERSION}}`, volume `./working/3x-ui/db/:/etc/x-ui/`, env `XRAY_VMESS_AEAD_FORCED="false"`, `XUI_ENABLE_FAIL2BAN="true"`)
  - `caddy` - Custom reverse proxy `ghcr.io/honmiv/caddy-l4:latest` (ports 80, 443; Caddyfile from `./working/caddy/Caddyfile`; depends on both services)
  - `nginx-decoy` - Fake website server (image `nginx:1.27-alpine`, static files from `./working/nginx-decoy/`)
- **Key Variables**:
  - `{{XUI_VERSION}}` - Docker image tag for 3x-UI
  - All environment variables from setup.sh passed through

**nginx-decoy/default.conf.template**
- **Purpose**: Nginx configuration for decoy website (static-only; all proxying is done by Caddy)
- **Key Features**:
  - Serves static HTML under `./working/nginx-decoy/html/`
  - Blocks `CONNECT` requests (return 444) and URL-in-request-target (return 400)
  - Returns 404 for any host other than `{{DOMAIN}}` (via `map $host $known_decoy_host`)
  - Custom 400/403/404/405/50x error pages (`/errors/*`)
- **Key Variables**:
  - `{{DOMAIN}}` - Server name directive

**3x-ui/vless-tcp-reality.template & vless-xhttp-reality.template**
- **Purpose**: XRay inbound protocol configurations (loaded into 3x-UI via its API, not as static files)
- **Key Settings**:
  - VLESS + Reality (private key, public key, serverName `{{DOMAIN}}`)
  - TCP inbound: tag `in-{{TCP_REALITY_INBOUND_PORT}}-tcp`, reality target `127.0.0.1:{{XHTTP_REALITY_INBOUND_PORT}}`, externalProxy `forceTls` same destination `{{DOMAIN}}:443`
  - XHTTP inbound: network `xhttp`, mode `auto`, `xPaddingBytes "100-1000"`, reality target `caddy:{{CADDY_GLOBAL_INTERNAL_PORT}}`, path `/`, host `{{DOMAIN}}`
  - `shortIds` passed as JSON arrays (`{{TCP_REALITY_SHORT_IDS_JSON_ARRAY}}`, `{{XHTTP_REALITY_SHORT_IDS_JSON_ARRAY}}`)
- **When to Modify**: Adding new protocol support or tweaking Reality settings

#### Docker Service Architecture (Panel)
```
Freedom/Proxy Node Docker Services:
┌─────────────────────────────────────┐
│ Docker Network: 3xui-caddy-net      │
├─────────────────────────────────────┤
│                                     │
│  ┌────────────────┐                 │
│  │    3x-ui       │                 │
│  │ • Ports 2053,  │                 │
│  │   2001-65535   │                 │
│  │ • XRay core    │                 │
│  │ • Proxy rules  │                 │
│  └────────────────┘                 │
│                                     │
│  ┌────────────────┐                 │
│  │    Caddy       │ ←→ External     │
│  │ • Port 80/443  │  (Public)       │
│  │ • L4 proxy     │                 │
│  │ • SSL/TLS      │                 │
│  └────────────────┘                 │
│         ↓                           │
│  ┌────────────────┐                 │
│  │ nginx-decoy    │                 │
│  │ • Decoy site   │                 │
│  │ • Static HTML  │                 │
│  └────────────────┘                 │
│                                     │
└─────────────────────────────────────┘
```

---

### 3. Sub-Server Component (Subscription Management)

**Location**: `sub-server/` directory
**Deployed To**: Separate standalone VPS (optional, for cascade deployments)

#### Sub-Server Purpose & Architecture
- **Role**: Centralized subscription proxy and client management
- **Function**: Sits between clients and 3x-UI nodes, providing:
  - Client-to-node routing (multi-node support)
  - Per-client custom subscription overrides
  - Admin web dashboard for client management
  - Automatic subscription fetching from backend nodes

#### Sub-Server Structure
```
sub-server/
├── server.py             # Python http.server app (subscription server)
├── setup.sh              # Remote deployment script
├── restart.sh            # Remote restart script
├── force-subs.yml        # Custom subscription overrides (auto-managed)
├── nodes.json            # Node registry: [{id, name, url, clients[]}] (single source of truth)
└── templates/
    ├── docker-compose/
    │   ├── docker-compose.yml.template  # Service definitions
    │   └── Dockerfile-python            # Python 3.12 image
    └── caddy/
        └── Caddyfile.template       # Reverse proxy config
```
> Note: legacy `subs.yml` was removed; `nodes.json` is now the single source of
> truth. Old remote deployments may still have a `subs.yml` — server.py reads it
> once to seed `nodes.json` when the registry is missing/empty, and the backup /
> sync / rollback helpers preserve it conditionally for backward compatibility.

#### sub-server/server.py - Subscription Server Application

**Architecture**:
```
Client Browser
    ↓ HTTPS
Caddy (Port 443)
    ↓ HTTP
subs-server (Port 8080, Docker port 8000)
    ├─→ Check force-subs.yml for override
    ├─→ Lookup client in nodes.json (node registry)
    ├─→ Fetch from that node's subscription URL: {node.url}/{client}
    └─→ Return subscription content or custom override
```

**Endpoints**:
| Path | Method | Purpose | Auth | Notes |
|------|--------|---------|------|-------|
| `/{SECRET_SUB_PATH}` | GET | Admin dashboard | Yes | Web UI, shows all nodes/clients; `?raw=1` returns plain list |
| `/{SECRET_SUB_PATH}/login` | GET/POST | Admin login | No | Session cookie set on success |
| `/{SECRET_SUB_PATH}/logout` | GET | Clear session | No | Removes session cookie |
| `/{SECRET_SUB_PATH}/<client_name>` | GET | Subscription request | No | Returns vless:// config |
| `/{SECRET_SUB_PATH}/api/override` | POST | Set/clear override | Yes | Modifies force-subs.yml |
| `/{SECRET_SUB_PATH}/api/client` | POST | Add/remove client | Yes | Modifies nodes.json |
| `/{SECRET_SUB_PATH}/api/node` | POST | Add/remove node | Yes | Modifies nodes.json |
| `/{SECRET_SUB_PATH}/api/logs` | GET | Real-time log stream (SSE) | Yes | Tails LOG_FILE; emits `message` events for log lines (same output as `docker logs -f subs-server`) and `activity` events for per-client subscription requests (time, HTTP status, bytes, node) |

**Client Routing Logic**:
1. Admin POSTs override → stored in force-subs.yml
2. Client requests subscription:
   - Check `force-subs.yml` first → if found, return it directly
   - Look up client via `find_client_node()` in `nodes.json` registry
   - Fetch subscription from the owning node: `{node['url']}/{client}` (e.g., proxy node → RUSSIAN_SUB_URL, freedom node → FOREIGN_SUB_URL)
   - Return subscription content (or 404 if not found)

**Key Features**:
- **Web UI Dashboard**:
  - Collapsible sections (proxy nodes, freedom nodes, overrides)
  - QR codes (toggleable) for each subscription URL
  - Copy buttons with visual feedback
  - Override editor with inline base64 encoding
  - Real-time log viewer (`docker logs -f subs-server` equivalent) in a sticky right-side panel
  - Per-client status row updated live: last sync time, HTTP status, bytes, node (via SSE `activity` events)
  - Dark theme, responsive design
  - `?raw=1` mode returns a plain newline-separated subscription list (useful for curl/clients)
  
- **Authentication**:
  - Session cookie: HMAC-SHA256 signed, 12-hour TTL (`AUTH_SESSION_TTL`)
  - Timing-safe comparison (constant-time verification)
  - HTTPS-only, SameSite=Lax, path-scoped
  - HTTP Basic Auth also supported
  
- **Logging**:
  - INFO level: subscription fetches, overrides, auth attempts
  - Format: `YYYY-MM-DD HH:MM:SS LEVEL message`
  - Output to stdout (Docker captures it) and mirrored to `LOG_FILE` (rotating, 5 MB × 3); the web UI tails `LOG_FILE` via the `/api/logs` SSE stream

**Environment Variables** (passed from main.py):
```bash
FORCE_FILE               # Path to force-subs.yml (overrides), e.g. ./force-subs.yml
NODES_FILE               # Path to nodes.json (node registry), e.g. ./nodes.json
LOG_FILE                 # Path to a log file tailed by the /api/logs SSE stream, e.g. /data/sub-server.log
SECRET_SUB_PATH          # e.g., subs or secret123
DOMAIN                   # e.g., sub.example.com
RUSSIAN_SUB_URL          # e.g., https://proxy-node/subs (fallback only)
FOREIGN_SUB_URL          # e.g., https://freedom-node/subs (fallback only)
PUBLIC_URL               # Optional; if unset, derived from X-Forwarded-Proto/Host
ADMIN_USER              # e.g., admin
ADMIN_PASSWORD          # Auto-generated or provided
AUTH_SESSION_SECRET     # Defaults to ADMIN_PASSWORD
AUTH_SESSION_TTL        # Seconds, default 43200 (12h)
HOST                     # Listen host, default 0.0.0.0
PORT                     # Listen port, default 8080 (Docker maps 8000)
LOG_LEVEL              # INFO, DEBUG (default: INFO)
```
> Note: `RUSSIAN_SUB_URL` / `FOREIGN_SUB_URL` are only used to seed `nodes.json`
> when the registry is missing/empty. Once `nodes.json` exists it is the single
> source of truth for node URLs and clients.

**When to Look Here**:
- Adding subscription filtering or transformation logic
- Modifying authentication mechanisms
- Changing client routing or override logic
- Debugging subscription fetch failures
- Adding new API endpoints

#### sub-server/setup.sh - Remote Deployment Script
- **Role**: Deploy subscription server to remote VPS
- **Execution Flow**:
  1. Validate Docker/dependencies (root, docker compose plugin, curl)
  2. `validate_update_state()`: if `UPDATE_SUB_SERVER=1`, keep existing nodes.json/force-subs.yml
  3. `load_existing_update_values()`: in update mode, restore SECRET_SUB_PATH, RUSSIAN_SUB_URL, FOREIGN_SUB_URL, ADMIN_USER/PASSWORD, DOMAIN from existing ./working/ configs
  4. Reset ./working directory (compose down first if needed)
  5. Prompt for domain, sub path, subscription URLs, admin credentials (env vars pre-fill)
  6. `create_nodes_json()`: generate nodes.json from environment variables
     (one entry per node with a subscription URL, clients from `PROXY_CLIENTS` /
     `FREEDOM_CLIENTS`), e.g.:
     ```json
     [
       {"id": "proxy", "name": "Proxy (РФ)", "url": "https://proxy-node/subs", "clients": ["client1", "client2"]},
       {"id": "freedom", "name": "Freedom (зарубежье)", "url": "https://freedom-node/subs", "clients": ["freedom-user"]}
     ]
     ```
  7. Process templates (Caddyfile, docker-compose.yml) via `generate_config()` + sed substitution
  8. Build and start Docker services (`compose up -d --build`)
  9. Wait for SSL certificate (Let's Encrypt, up to 300s)

**Key Environment Variables**:
- `PROXY_CLIENTS` - Space-separated client list for the proxy (Russian) node
- `FREEDOM_CLIENTS` - Space-separated client list for the freedom (foreign) node
- `UPDATE_SUB_SERVER` - `1` preserves existing client/node config (used by `update_sub` mode)

#### sub-server/nodes.json - Node Registry (single source of truth)
```json
[
  {"id": "proxy", "name": "Proxy (РФ)", "url": "https://proxy-node/subs", "clients": ["end-user", "local-client-1"]},
  {"id": "freedom", "name": "Freedom (зарубежье)", "url": "https://freedom-node/subs", "clients": ["foreign-user"]}
]
```

**Format**: JSON array of nodes; each node has `id`, `name`, `url` (subscription
base URL) and `clients[]`. Arbitrary nodes/clients are supported.
**Management**:
- Generated by `setup.sh` (`create_nodes_json()`) from environment variables
- Managed via the web UI (`POST /api/client`, `POST /api/node`) which persists to this file
- **Legacy**: if the file is missing or empty, `server.py` seeds it from
  `RUSSIAN_SUB_URL`/`FOREIGN_SUB_URL` (optionally migrating client lists from an
  old `subs.yml`); once written, nodes.json is the only source of truth

#### sub-server/force-subs.yml - Subscription Overrides
```yaml
# Base64-encoded custom subscriptions (auto-managed by server)
client-name: dmxlc3M6Ly9jdXN0b20tdmxlc3MtdXJsCg==
another-client: dmxlc3M6Ly9vdGhlcl91cmwK
```

**Purpose**: Allow admin to override subscription for specific clients
**Management**: 
- Admin sets override via web UI POST to `/api/override`
- Server base64-encodes and appends to force-subs.yml
- On client request, server checks this file first
- Admin can clear override, which removes entry

**When to Look Here**:
- Per-client custom URL configuration
- Emergency fixes for specific clients
- Testing alternative subscription sources

#### Docker Service Architecture (Sub-Server)
```
Sub-Server Node Docker Services:
┌─────────────────────────────────────┐
│ Docker Network: sub-caddy-net       │
├─────────────────────────────────────┤
│                                     │
│  ┌────────────────────────────┐    │
│  │   subs-server              │    │
│  │ • Python 3.12-alpine       │    │
│  │ • Port 8000 (internal)     │    │
│  │ • Reads nodes.json         │    │
│  │ • Manages force-subs.yml   │    │
│  │ • Routes to backend nodes  │    │
│  └────────────────────────────┘    │
│                                     │
│  ┌────────────────────────────┐    │
│  │   Caddy                    │    │
│  │ • Port 80/443 (public)     │    │
│  │ • HTTPS termination        │    │
│  │ • Let's Encrypt cert       │    │
│  │ • Reverse proxy to :8000   │    │
│  └────────────────────────────┘    │
│                                     │
└─────────────────────────────────────┘
```

#### Integration with Panel Deployment

**Cascade Deployment Workflow** (from ssh_deployer.py):
```
Stage 1: Deploy Freedom Node
  ├─→ ssh_deployer.exec_command("panel/setup.sh")
  └─→ Result: FREEDOM_SUB_URL = https://freedom-node.com/subs

Stage 2: Deploy Proxy Node (with freedom node URL)
  ├─→ Pass FOREIGN_SUB_URL=FREEDOM_SUB_URL to setup.sh
  ├─→ ssh_deployer.exec_command("panel/setup.sh")
  └─→ Result: PROXY_SUB_URL = https://proxy-node.com/subs

Stage 3: Deploy Subscription Server (with both node URLs)
  ├─→ Pass RUSSIAN_SUB_URL=PROXY_SUB_URL
  ├─→ Pass FOREIGN_SUB_URL=FREEDOM_SUB_URL
  ├─→ Pass PROXY_CLIENTS=[list from proxy node config]
  ├─→ Pass FREEDOM_CLIENTS=[list from freedom node config]
  ├─→ ssh_deployer.exec_command("sub-server/setup.sh")
  └─→ Result: Sub-server routes clients to appropriate backends
```

**Maintenance Operations**:
- `restart_sub` - Restart containers via ./restart.sh
- `update_sub` - One-click update: creates a full pre-update backup (nodes.json, force-subs.yml, Caddyfile, SSL certs), then redeploys preserving client/node/override data; aborts if backup fails
- `backup_sub` - Backup nodes.json, force-subs.yml, Caddyfile, SSL certs
- `rollback_sub` - Restore from backup archive (incl. nodes.json)

---

## Template Variable Reference

### Panel Templates Variables

| Variable | Example | Usage | Source |
|----------|---------|-------|--------|
| `{{DOMAIN}}` | proxy.example.com | Caddy server_name, Let's Encrypt email | User input (form) |
| `{{XUI_WEB_PORT}}` | 2053 | 3x-UI web UI internal port | Random (49152–65535) |
| `{{XUI_SUB_PORT}}` | 2053+1 | 3x-UI subscription internal port | Random (49152–65535) |
| `{{XUI_WEB_BASE_PATH}}` | a1b2c3d4e5f60718 | Hidden admin web base path | Derived from SECRET_PHRASE (md5) |
| `{{XUI_SUB_PATH}}` | subs | Subscription endpoint path | Derived from SECRET_PHRASE (md5) |
| `{{CADDY_GLOBAL_INTERNAL_PORT}}` | 2000 | Caddy `https_port` (internal) | Random (49152–65535) |
| `{{TCP_REALITY_INBOUND_PORT}}` | 52113 | VLESS TCP Reality inbound port | Random (49152–65535) |
| `{{TCP_REALITY_SHORT_IDS_JSON_ARRAY}}` | ["abcd"] | TCP inbound shortIds (JSON) | Auto-generated |
| `{{XHTTP_REALITY_SHORT_IDS_JSON_ARRAY}}` | ["abcd"] | XHTTP inbound shortIds (JSON) | Auto-generated |
| `{{XUI_VERSION}}` | 1.7.5 | 3x-UI Docker image tag | User input (form) |
| `{{FOREIGN_SUB_URL}}` | https://freedom/subs | Subscription URL (for proxy node) | Previous deployment |

### Sub-Server Template Variables

| Variable | Example | Usage | Source |
|----------|---------|-------|--------|
| `{{DOMAIN}}` | sub.example.com | Caddy server_name, Let's Encrypt | User input (form) |
| `{{SECRET_SUB_PATH}}` | subs | Subscription endpoint path | User input (form) |
| `{{RUSSIAN_SUB_URL}}` | https://proxy-node/subs | Proxy node subscription URL | Previous deployment (Stage 2) |
| `{{FOREIGN_SUB_URL}}` | https://freedom-node/subs | Freedom node subscription URL | Previous deployment (Stage 1) |
| `{{ADMIN_USER}}` | admin | Subscription server admin | User input (form) |
| `{{ADMIN_PASSWORD}}` | (auto) | Subscription server admin password | Auto-generated or user input |

---

## File Navigation by Task

### Adding a New Deployment Mode
1. **Understand existing modes** → `ssh_deployer.py` `run_deployment()` function
2. **Define new mode logic** → Add case to `run_deployment()` switch
3. **Create remote script** → `panel/setup.sh` or `sub-server/setup.sh`
4. **Update web UI** → `main.py` add form fields
5. **Test** → Run deployment locally with mock SSH

### Modifying Configuration Templates
1. **Identify component** → Find template in `panel/templates/` or `sub-server/templates/`
2. **Edit template** → Change {{VARIABLE}} syntax (never hardcode values)
3. **Add new variable** → Add to ssh_deployer.py environment vars
4. **Test on remote** → Deploy and verify config generates correctly

### Fixing SSH/Connection Issues
1. **Check connection** → `ssh_deployer.py` `test_connection()` method
2. **Review credentials** → `setup_backup.yml` (form persistence)
3. **Debug remote execution** → Check log output streamed from `main.py` SSE handler
4. **Verify remote scripts** → `panel/setup.sh` or `sub-server/setup.sh` exit codes

### Adding Subscription Filtering
1. **Understand current flow** → `sub-server/server.py` client routing
2. **Modify routing logic** → Add filter before `return subscription_content`
3. **Update UI** → Add controls in subscription server dashboard

### Debugging Deployment Failures
1. **Check logs** → Streamed to UI via `main.py` SSE
2. **SSH into remote** → Manually run `panel/setup.sh` with debug flags
3. **Inspect Docker** → `docker logs <container_name>` on remote VPS
4. **Review templates** → Check variable substitution in `./working/` directory

### Handling Updates & Backups
1. **Understand backup format** → ssh_deployer.py `run_deployment(..., mode='backup')`
2. **Recovery logic** → ssh_deployer.py `mode='recovery'` auto-replaces domain
3. **Version management** → {{XUI_VERSION}} variable in docker-compose.yml.template

---

### Frontend Technical Specifics (Особенности работы фронтенда)
1. **Validation & Mandatory Fields (`REQUIRED_FIELDS`)**:
   - The frontend enforces declarative validation logic in `panel/static/app.js` via the `REQUIRED_FIELDS` array.
   - Fields are dynamically validated based on the selected deployment mode (e.g., `cascade`, `single`, `sub_only`, `proxy_only`, `freedom_only`, `freedom_component`, `update_3xui`, `recovery`, `backup`, `restart_panel`, `restart_server`, and sub-server operations).
   - Supports both single-field checks and group-based rules (e.g., `mode: 'any'` ensures at least one field in a group is populated, such as requiring either `sub_russian_url` or `sub_foreign_url` for `sub_only` / `cascade_sub`).
   - Multi-step validation: Checks are organized by wizard steps (Step 1: Mode selection, Step 2: VPS SSH credentials, Step 3: Node & Subscription parameters). The form prevents submission if any required field is missing or invalid.
   - Dynamic authentication validation: Dynamically validates either SSH password or SSH private key depending on the chosen `auth_type` (`password` vs `key`).

2. **Debounced Background State Saving (`setup_backup.yml`)**: 
   - **Debounce Timer**: On every form input and configuration change, a 500ms debounce timer (`debounceAutoSave`) triggers a background `POST /api/config` request to persist user inputs.
   - **Accordion State Persistence**: Persists not only input values, but also UI state such as open/closed accordions (`ui_open_categories`: `category-full`, `category-single`, `category-maintenance`).
   - **State Restoration (`loadBackupConfig`)**: On page load, `GET /api/config` fetches the saved state, re-populates inputs, selects active deployment modes, restores accordion visibility, and sets the proper auth type selectors.
   - **Security Filter (Secret Stripping)**: In `main.py` (`save_backup_config`), the backend strictly filters the payload before writing to `setup_backup.yml` — all keys containing `"password"` or ending in `"_key"` are stripped. Passwords and private keys are never stored in plaintext on disk.

3. **Saved VPS Profiles Manager (PIN-encrypted `servers.json`)**: 
   - The UI includes a slide-out "Servers" drawer to save and reload server credentials for any host role (`proxy_host`, `freedom_host`, `sub_vps_host`, `vps_host`, `backup_vps_host`, etc.).
   - Security: Uses client-side PBKDF2 (100,000 iterations) + AES-GCM encryption with a user-defined PIN. Plaintext credentials never hit the filesystem.
   - Endpoints: `GET /api/servers` (reads encrypted vault), `POST /api/servers` (saves encrypted vault), `DELETE /api/servers/reset` (resets vault).

4. **Real-time Log Streaming & Process Control (SSE)**: 
   - Long-running operations (deployment, recovery, backups, updates) stream `stdout`/`stderr` line-by-line via Server-Sent Events (`GET /api/deploy/logs`).
   - Frontend creates an `EventSource`, color-codes log messages by level (`INFO`, `WARN`, `ERROR`, `SUCCESS`), and auto-scrolls the terminal output.
   - Cancellation: `POST /api/deploy/stop` signals the backend `cancel_requested` flag, which aborts active SSH subprocesses cleanly and alerts the UI.

5. **Pre-flight SSH Connection Testing (`/api/ssh/test`)**:
   - Each host entry card in Step 2 features a "Test Connection" button.
   - Sends a lightweight probe to `POST /api/ssh/test` with host, port, user, and credentials to verify connectivity and auth before committing to a full deployment.

6. **Asynchronous Version & Backup Fetching**:
   - `GET /api/xui_versions`: Fetches available 3x-ui Docker tags from ghcr.io (cached for 300s) and dynamically populates version dropdowns in the UI.
   - `GET /api/backups`: Scans `./backups_panel/` and populates the backup selection dropdown for the recovery mode.

7. **Custom Non-blocking UI Modals & Toasts**: 
   - Browser-native `window.alert` and `window.confirm` are replaced in `app.js` with custom DOM-based components (`showAlert`, `showConfirm`, `showToast`).
   - Keeps the UI non-blocking and visually aligned with the dark theme during long background operations.

8. **Dynamic Visual Topology Rendering**: 
   - Dynamically renders an interactive topology diagram showing traffic flow (Client → Domestic Proxy → Freedom Node → Internet) based on the currently selected `deploy_mode`.

---

### Infrastructure Problem-Solving Patterns (Паттерны технических решений)
1. **Caddy L4 SNI Multiplexing + Nginx Decoy Active-Probe Defense**: 
   - *Problem*: Active probing scanners connect to port 443 with TLS handshakes or HTTP requests to detect proxy signatures (e.g., GFW/RKN active probes).
   - *Solution*: Caddy operates in Layer 4 mode on port 443 with SNI passthrough. Legitimate VLESS Reality traffic matches Reality keys and is handled by XRay, while regular HTTPS and HTTP port 80 traffic falls back to `nginx-decoy` serving a genuine static website with valid TLS certificates, headers, and custom error pages.

2. **Cascade Tunneling Pattern (Russian Proxy + Foreign Freedom)**: 
   - *Problem*: Direct connections from domestic users to foreign servers are throttled or blocked by domestic DPI.
   - *Solution*: A two-tier cascade:
     - Tier 1 (Russian Proxy Node): Deployed on a domestic VPS; routes foreign destinations through an XRay outbound subscription to the Freedom Node. Domestic traffic stays in-country.
     - Tier 2 (Foreign Freedom Node): Deployed outside censorship boundaries; unblocks global internet while blocking direct `.ru` traffic via XRay routing rules.
     - Result: Domestic ISPs only see domestic TLS traffic between the user and the Russian node.

3. **Self-Contained SSH Tarball Streaming**:
   - *Problem*: Remote VPS nodes may have minimal OS installations, restricted repositories, or lack `git`/Python environments.
   - *Solution*: The local deployment engine builds an in-memory `.tar.gz` bundle of the necessary repository scripts and templates (`get_bundle_bytes()`) and pipes it directly over SSH standard input (`exec_command(stdin_data=...)`) to `tar -xzf - -C /opt/3x-ui-bootstRUp`. No `git clone` or external dependencies required on the target VPS.

4. **Dynamic Domain Migration & Auto-Recovery**:
   - *Problem*: If a VPS domain is blocked by DNS filtering or SNI blocking, recovering from a backup on a new domain traditionally requires manual database edits.
   - *Solution*: In `recovery` mode, the orchestrator unpacks the `./working/` archive on the VPS and rewrites the domain in the Caddyfile/Nginx configs via `sed`, then rewrites the domain *inside the running 3x-UI panel through its HTTP API* (CSRF + cookie auth via `docker exec` + `curl` + `jq`, using the panel admin credentials supplied in the recovery form). The API rewrite covers `serverName`, `serverNames[]`, client `add`, `externalProxy[].dest`, `xhttpSettings.host`, and the `subURI` setting, then restarts Xray — so regenerated subscriptions point to the new host without ever touching SQLite.

5. **Decoupled Centralized Subscription Server**:
   - *Problem*: Exposing direct panel subscription links can lead to panel discovery, credential leaks, or hardcoded client config lock-in.
   - *Solution*: A standalone Python/Caddy `sub-server` acts as an abstraction proxy. It maintains a `nodes.json` registry and client routing table. When a client requests their subscription, the sub-server fetches and transforms the upstream config on-the-fly, supports instant per-client overrides via `force-subs.yml`, and provides an isolated admin panel with HMAC session authentication.

---

## Code Patterns & Conventions

### Async SSH Pattern
```python
# In ssh_deployer.py — the SSHDeployer wraps the system ssh/scp binaries
# (password auth via SSH_ASKPASS; optional private key), not paramiko.
async with SSHDeployer(host, port, user, password, key_data, cancel_check=cancel_check) as deployer:
    # Execute a remote command with a log callback
    rc, output = await deployer.exec_command(
        "cd /opt/3x-ui-bootstRUp && bash panel/setup.sh",
        log_callback=lambda msg: log(msg, "info")
    )

    # Stream binary data (e.g. the repo tar.gz bundle) to a remote command's stdin
    rc, out = await deployer.exec_command(
        "mkdir -p /opt/3x-ui-bootstRUp && tar -xzf - -C /opt/3x-ui-bootstRUp",
        log_callback=lambda m: log(m, "info"),
        stdin_data=bundle_bytes,
    )

    # Download a file via SCP
    rc_scp, scp_out = await deployer.download_file("/tmp/backup.tar.gz", local_path, log_callback)
```

### Template Processing
```bash
# In panel/setup.sh / sub-server/setup.sh (remote)
# generate_config() copies ./panel/templates → ./working, then substitutes
# {{VARIABLE}} placeholders in *.template files via sed (not envsubst).
apply_template_values() {
    local target_path="$1"
    sed -i \
       -e "s|{{DOMAIN}}|${DOMAIN}|g" \
       -e "s|{{SECRET_SUB_PATH}}|${SECRET_SUB_PATH}|g" \
       -e "s|{{ADMIN_USER}}|${ADMIN_USER}|g" \
       "$target_path"
}
```

### Logging Pattern
```python
# In main.py (http.server, not Flask)
def log(self, message, level="INFO"):
    # Broadcast to all connected SSE clients (GET /api/deploy/logs)
    yield f"data: {json.dumps({'level': level, 'message': message})}\n\n"
```

### Cross-Platform Script Handling
```python
# In main.py — cli_script_path() picks the launcher variant per OS
def cli_script_path(base_name: str) -> str:
    if platform.system() == "Windows":
        return f"./{base_name}.cmd"
    if platform.system() == "Darwin":
        return f"./{base_name}.sh"
    return f"./{base_name}.sh"
# Launchers: start_3x_ui_deployment_manager, update_sources, panel_backup,
# panel_recover, panel_update (each has .sh / .ps1 / .cmd variants)
```

### Configuration Persistence
```yaml
# setup_backup.yml structure — secrets are NEVER stored
# save_backup_config() strips any field containing "password" or ending "_key"
freedom_node:
  host: 1.2.3.4
  port: 22
  # ... persist all form fields (except passwords and *_key)

proxy_node:
  host: 5.6.7.8
  # ... loaded on app restart to resume forms
```

---

## Deployment Execution Flow

### Single/Cascade Panel Deployment
```
1. main.py receives form submission
2. Validates inputs
3. Calls ssh_deployer.run_deployment(mode="single" or "cascade")
4. ssh_deployer creates SSHDeployer connection + test_connection()
5. Ensures Docker on remote (_ensure_remote_docker)
6. Streams repo tar.gz via exec_command(stdin_data) → /opt/3x-ui-bootstRUp
7. Executes: cd /opt/3x-ui-bootstRUp && ENV_VARS bash panel/setup.sh
8. setup.sh processes templates → generates ./working/ configs
9. setup.sh configures 3x-UI via its HTTP API and builds Docker services
10. Docker Compose starts services
11. Wait for Let's Encrypt certificate (300s)
12. parse_deployment_results() extracts subscription URLs
13. main.py displays results to UI
```

### Cascade Subscription Deployment
```
1. Stage 1: Deploy freedom node (single mode)
   → Get FOREIGN_SUB_URL from response
2. Stage 2: Deploy proxy node with FOREIGN_SUB_URL
   → Get RUSSIAN_SUB_URL from response
3. Stage 3: Deploy sub-server with both URLs
   → nodes.json auto-generated with node URLs + client lists
   → Sub-server routes clients to appropriate backends
```

### Backup & Recovery
```
Backup:
1. ssh_deployer.run_deployment(mode="backup")
2. Remote: tar -czf /tmp/backup.tar.gz ./working/
3. scp transfer to local machine
4. Save as backup_TIMESTAMP.tar.gz

Recovery:
1. ssh_deployer.run_deployment(mode="recovery", backup_file="...")
2. Remote: Extract backup.tar.gz
3. Auto-replace old domain with new domain in configs
4. Restart Docker services
```

---

## Security & Authentication

### SSH Authentication
- **Methods**: Password or private key-based
- **Storage**: Passwords and private keys are never persisted — `save_backup_config()` strips any field containing "password" or ending in `_key` from `setup_backup.yml`; saved VPS profiles in `servers.json` are encrypted (PBKDF2 + AES-GCM under a user PIN)
- **Validation**: Pre-flight test_connection() before each deployment

### 3x-UI Admin Access
- **Credentials**: Stored in 3x-UI SQLite database
- **Access**: Via Caddy reverse proxy on port 443 (hidden web base path derived from SECRET_PHRASE)
- **Default user**: Created during setup.sh execution

### Sub-Server Admin Access
- **Session Auth**: HMAC-SHA256 signed cookies (12-hour TTL)
- **Credential**: Username/password set during deployment
- **Transport**: HTTPS only (Caddy termination)

---

## Common Issues & Troubleshooting

### Template Variable Not Substituting
- **Cause**: Variable not passed to setup.sh environment
- **Fix**: Check ssh_deployer.py `run_deployment()` env dict, ensure variable is set
- **Debug**: SSH into remote, check `env | grep VARIABLE`

### Docker Service Fails to Start
- **Cause**: Port conflict, insufficient resources, image pull failure
- **Fix**: Check Docker logs: `docker logs 3x-ui` or `docker logs caddy`
- **Debug**: SSH into remote, run: `docker-compose logs -f`

### SSL Certificate Not Issued
- **Cause**: Domain DNS not resolving, Let's Encrypt rate limit, port 80 blocked
- **Fix**: Verify domain DNS A record, wait before retry, check firewall
- **Debug**: `docker logs caddy`, check Caddy logs for Let's Encrypt errors

### Subscription Fetch Fails
- **Cause**: Backend node down, network unreachable, 404 on subscription URL
- **Fix**: Verify backend node is running, check subscription path matches config
- **Debug**: SSH into sub-server, curl the RUSSIAN_SUB_URL manually

---

## Agent Quick Reference

**When you need to...**

| Task | Primary Files | Secondary Files |
|------|---------------|-----------------|
| Add new deployment mode | `ssh_deployer.py` (run_deployment) | `main.py` (form routing), `setup.sh` (logic) |
| Modify config template | `panel/templates/*` or `sub-server/templates/*` | `ssh_deployer.py` (env vars) |
| Debug SSH issues | `ssh_deployer.py` (SSHDeployer class) | `main.py` (log streaming) |
| Add subscription filter | `sub-server/server.py` (routing logic) | `sub-server/templates/*` (config) |
| Fix web UI | `panel/static/app.js`, `panel/static/index.html` | `main.py` (backend routes) |
| Handle new VPS type | `ssh_deployer.py` (connection logic) | `setup.sh` (remote script) |
| Improve logging | `main.py` (SSE handler) | `ssh_deployer.py` (log_callback usage) |
| Add backup feature | `ssh_deployer.py` (backup mode) | `main.py` (UI route) |

---

## Summary

This project implements a **sophisticated deployment orchestration system** with:
- **Dual-tier architecture**: Local control plane + remote nodes
- **Template-driven configuration**: Centralized config generation
- **Multi-deployment modes**: 8+ different deployment strategies (single, cascade, cascade_sub, sub_only, per-node deploy, backup/recovery, updates, restarts)
- **Optional subscription management**: Centralized multi-node proxy routing
- **Cross-platform support**: Windows, macOS, Linux CLI

Key design principles:
- **Abstraction**: Hide Docker/Caddy complexity behind forms
- **Reliability**: Pre-flight checks, error logging, session persistence
- **Portability**: Same UI works across platforms
- **Transparency**: Real-time logs streamed to user
- **Modularity**: Panel and sub-server components can be deployed independently

Start debugging by checking the log stream in main.py → trace to ssh_deployer.py → review remote setup.sh output.

---

## TODO / Technical Debt & Architectural Inconsistencies

1. **YAML Parsing Inconsistency & Duplication** — *RESOLVED*:
   - `main.py` now uses PyYAML for both loading and saving `setup_backup.yml`; the line-by-line fallback parser was removed (`load_backup_config` degrades to `{}` without PyYAML) and `save_backup_config` logs failures instead of swallowing them.
   - `sub-server/server.py` parses `subs.yml` (`load_subs`) and `force-subs.yml` (`load_force_subs` / `save_force_subs`) with PyYAML; the ad-hoc line parsers were removed.
   - PyYAML is installed in the sub-server Docker image (`sub-server/templates/docker-compose/Dockerfile-python`).
   - `nodes.json` remains the JSON node registry (stdlib `json` module).
   - *Remaining debt*: full migration of `subs.yml` → `nodes.json` is tracked separately in item 2.

2. **Schema Divergence: Legacy `subs.yml` vs `nodes.json`** — *RESOLVED*:
   - `sub-server/setup.sh` now generates `nodes.json` (`create_nodes_json()`) from `RUSSIAN_SUB_URL`/`FOREIGN_SUB_URL` + `PROXY_CLIENTS`/`FREEDOM_CLIENTS` instead of `subs.yml`; the `subs.yml` volume mount and `DATABASE_FILE` env were removed from the docker-compose template.
   - `sub-server/server.py` uses `nodes.json` as the single source of truth; the legacy `subs.yml` is only read once to seed `nodes.json` when the registry is missing/empty.
   - Backups, `update_sub` and `rollback_sub` center on `nodes.json`; the legacy `subs.yml` is preserved conditionally for backward compatibility with old deployments.

3. **Fragile Remote Output Parsing in Deployer** — *RESOLVED*::
   - `ssh_deployer.py:parse_deployment_results()` parses unstructured text and localized strings (`"Клиент:"`, `"Client:"`, `"3x-UI"`, `vless://`) from remote `setup.sh` stdout.
   - *Goal*: Have remote scripts emit a machine-readable JSON summary block at completion to avoid breaking on script output/locale changes.

4. **Template Substitution Edge Cases (`sed` vs Structured Configs)** — *RESOLVED*::
   - Config templates in `panel/` and `sub-server/` rely on `sed -i "s|{{VAR}}|...|g"`. Special characters (`|`, `&`, `\`) in passwords or secrets can break substitution.
   - 3x-UI inbound configurations are rendered via curl API payload injection rather than file-based templating.
   - *Goal*: Ensure proper escaping in bash scripts or generate configuration files via python/json serialization where applicable.

5. **Thread Safety in Local Control Plane (`main.py`)**:
   - Shared globals (`active_logs`, `is_deploying`, `deploy_status`, `deploy_result`, `cancel_requested`) are accessed concurrently across HTTP worker threads without explicit synchronization locks (`threading.Lock`).
   - *Goal*: Add synchronization primitives around shared deployment state and SSE log streaming buffers.

6. **`restart_sub` Overwrites Runtime Data on Remote Node** — *RESOLVED*:
   - `ssh_deployer.py` now has a single `_sub_server_sync_cmd(remote_dir, preserve)` helper used by both `_deploy_sub_server` (update mode) and `restart_sub`; it backs up `subs.yml`/`force-subs.yml`/`nodes.json` before extracting the bundle and restores them afterwards, so syncing tool scripts never clobbers remote client/override data.
   - The duplicate `force-subs.yml` backup in the update-mode sync command (inside the loop and via a separate `if`) was removed.

7. **`save_backup_config` Silently Swallows All Errors** — *RESOLVED*:
   - `main.py:save_backup_config` now returns a `bool` and logs failures via `log_event` (`[ERROR] Failed to save setup_backup.yml: ...`) instead of a bare `except Exception: pass`.
   - `POST /api/config` returns HTTP 500 with `{"ok": false, "error": ...}` when the save fails, so a broken `setup_backup.yml` is no longer silently dropped.

8. **Recovery Domain Replacement Misses the 3x-UI Database** — *RESOLVED*:
   - `recovery` mode now rewrites the domain *inside the running 3x-UI panel through its HTTP API* (`ssh_deployer.py` → `PANEL_DOMAIN_REWRITE_SCRIPT`, uploaded to the recovered host and run via `docker exec` + `curl` + `jq`): it logs into the panel with the admin credentials supplied in the recovery form (default `admin`/`admin`), updates `subURI` in `panel/api/setting/update`, rewrites `serverName`/`serverNames[]`/client `add`/`externalProxy[].dest`/`xhttpSettings.host` in every inbound via `panel/api/inbounds/update/{id}`, and restarts Xray. No SQLite access is involved.
   - The useless `sed` over `working/3x-ui/*.json` was removed; the old domain is detected locally from the backup's Caddyfile before upload, and if the domain changed the recovery form *requires* the panel credentials (hard error otherwise, so a half-done recovery with a dead-domain panel is avoided).
   - Backups from the pre-`panel/` repo layout still contain a compose file that builds caddy from `./templates/docker-compose` (relative to `--project-directory`). As a *legacy fallback* `recovery` now rewrites that caddy `build:` block to `image: ghcr.io/honmiv/caddy-l4:latest` (`LEGACY_COMPOSE_REWRITE_CMD` in `ssh_deployer.py`) — only when the restored compose actually references the old build context — so recovery pulls the published image instead of a ~70s source build and needs no build context. `restart_panel`/`panel_update.sh` keep the `templates -> panel/templates` compatibility symlink fallback (`LEGACY_TEMPLATES_SYMLINK_CMD`) for legacy servers that were never re-recovered. Neither path touches modern deployments.
   - *Remaining debt*: a failed login mid-recovery aborts after containers are up (the recovery itself is idempotent and can be re-run with correct creds).

9. **Docker Installation & Registry Mirror Logic Duplicated and Inert**:
   - Docker bootstrap is implemented three times: `_ensure_remote_docker` (ssh_deployer.py), `install_docker` (panel/setup.sh), `install_docker` (sub-server/setup.sh).
   - `daemon.json` (registry mirror) is written but the docker daemon is never restarted, so the mirror is not actually applied.
   - *Goal*: Single shared Docker bootstrap (orchestrator-side only) and restart the daemon after writing `daemon.json`.

10. **Dead Configuration: Environment Variables and UI Fields That Do Nothing**:
    - `EMAIL` is passed to node setup (ssh_deployer.py) but never read by `panel/setup.sh`.
    - `XUI_WEB_PORT` / `XUI_SUB_PORT` / `CADDY_GLOBAL_INTERNAL_PORT` / `TCP_REALITY_INBOUND_PORT` / `XHTTP_REALITY_INBOUND_PORT` are always regenerated by `generate_ports()` in `panel/setup.sh`, so any port values sent from the UI/orchestrator are ignored (AGENTS.md's "generated if not provided" is wrong).
    - `sub_same_as_proxy` checkbox is persisted to `setup_backup.yml` but never consumed (neither in `app.js` deploy payload nor in `ssh_deployer.py`).
    - `freedom_component` mode is a pure alias of `freedom_only` (same code path in `ssh_deployer.py` and identical frontend handling) — redundant radio button.
    - *Goal*: Remove dead fields/env vars, or wire them up (e.g., actually apply user-specified ports, or implement "same SSH creds as proxy").

11. **Backup Asymmetry & Duplication Between Panel and Sub-Server**:
    - `_perform_remote_backup` (ssh_deployer.py) and `_perform_remote_sub_backup` (ssh_deployer.py) are near-identical copy-paste helpers differing only in the file list.
    - The panel backup (`panel_backup.sh` / `_perform_remote_backup`) does **not** include `.caddy_data` (SSL certificates), while the sub-server backup does — so recovering a panel forces re-issuing certificates on the new host (Let's Encrypt rate-limit risk), and the two components' backups are inconsistent in scope.
    - *Goal*: One parameterized backup helper and consistent inclusion of TLS state across both components.

12. **Misc Local-Orchestrator & Frontend Oddities**:
    - `main.py` imports `from ssh_deployer import run_deployment` but never uses it; instead `importlib.reload(ssh_deployer)` is invoked on every `/api/deploy` request, which can desync already-imported references.
    - `panel_api_request` in `panel/setup.sh` builds the remote curl command via string concatenation with manual quote-escaping — fragile and injection-prone.
    - Sub-server QR codes are loaded from the external `api.qrserver.com` service, leaking client subscription URLs to a third party.
    - Default XUI version `"3.6.0"` is hardcoded in multiple places (main.py, ssh_deployer.py, app.js, panel/setup.sh).
    - The `tests/` directory is empty despite AGENTS.md referencing test-driven flows.
    - *Goal*: Drop the unused import/reload hack, build curl args as an array, self-host or inline QR generation, centralize version defaults, and add basic tests.

13. **Weak Encryption of servers.json**:
    - Uses PBKDF2 (100k iterations) based on a user PIN. If the PIN is short (4-6 digits), the file is easily brute-forced locally. Short passwords require significantly more iterations or the use of argon2id.

14. **Vulnerable Session Secret**:
    - In sub-server, `AUTH_SESSION_SECRET` defaults to `ADMIN_PASSWORD`. If the password is weak, an attacker can brute-force it and forge the HMAC-SHA256 cookie to access the panel.
