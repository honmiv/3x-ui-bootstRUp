---
name: 3x-UI BootstRUp Architecture Guide
description: Comprehensive project architecture, components, and code navigation guide for AI agents
category: architecture
---

# 3x-UI BootstRUp: Architecture & Agent Navigation Guide

## Project Overview

**3x-UI BootstRUp** is a sophisticated cross-platform infrastructure-as-code tool for deploying and managing multi-node proxy networks (3x-UI panels). It automates the deployment of XRay-based VPN/proxy infrastructure with cascading node architectures, subscription management, and centralized administration.

**Target Use Case**: Users in regions with internet restrictions who need to deploy multi-region proxy cascades.

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
│  │  ┌──────────────────┐              ┌──────────────────┐    ││
│  │  │  Web UI (HTML)   │ ←→ ←→ ←→ ←→ │ main.py (Flask) │    ││
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
      ├─→ restart_panel / restart_sub
      └─→ backup_sub / rollback_sub
```

---

## Core Components

### 1. Local Control Plane

**Files**: `main.py`, `ssh_deployer.py`, `setup_backup.yml`, `servers.json`

#### main.py - HTTP Server & Orchestrator
- **Role**: Entry point, HTTP server (port 8000), UI routing, deployment dispatch
- **Key Functions**:
  - Serves web UI (HTML/CSS/JS from `panel/static/`)
  - Routes POST requests from forms to `ssh_deployer` functions
  - Manages session state between deployments
  - Streams real-time logs to UI via Server-Sent Events (SSE)
  - Loads/saves deployment configurations in YAML format

- **When to Look Here**:
  - Adding new web form endpoints
  - Changing UI routing or log streaming behavior
  - Modifying deployment flow or orchestration sequence
  - Handling user input and validation

#### ssh_deployer.py - Remote Execution Engine
- **Role**: Core deployment logic, SSH/SCP operations, remote command execution
- **Key Functions**:
  - `SSHDeployer` class: Async SSH connection manager
  - `exec_command()`: Execute remote shell commands with logging
  - `upload_file()` / `download_file()`: File transfers
  - `run_deployment()`: Master orchestration function (handles all 8 deployment modes)

- **Deployment Modes** (handled in `run_deployment()`):
  1. **single** - Deploy one panel (freedom or proxy)
  2. **cascade** - Deploy two panels (freedom → proxy with subscription URL)
  3. **cascade_subscription** - Deploy panels + subscription server
  4. **sub_only** - Deploy only subscription server
  5. **backup** - Download remote ./working/ directory
  6. **recovery** - Restore from backup, auto-replace domain
  7. **update** - Upgrade 3x-ui version (backs up first)
  8. **restart_panel**, **restart_server**, **restart_sub** - Service restart

- **When to Look Here**:
  - Debugging SSH/connection issues
  - Adding new deployment modes
  - Modifying deployment sequence or error handling
  - Changing file transfer mechanisms
  - Understanding how templates are processed on remote servers

#### setup_backup.yml - Session Persistence
- **Role**: Store deployment form data between sessions
- **Format**: YAML with sections per deployment node
- **Example Structure**:
  ```yaml
  freedom_node:
    host: 1.2.3.4
    port: 22
    username: root
    password: secret
    domain: freedom.example.com
    
  proxy_node:
    host: 5.6.7.8
    port: 22
    username: root
    password: secret
    domain: proxy.example.com
    foreign_sub_url: https://freedom.example.com/subs
    
  sub_server:
    host: 9.10.11.12
    port: 22
    username: root
    password: secret
    domain: sub.example.com
  ```

- **When to Look Here**:
  - Resuming incomplete deployments
  - Modifying form state persistence
  - Debugging configuration loading/saving

#### servers.json - Saved VPS Profiles
- **Role**: Quick-select list of previously configured servers
- **Format**: JSON array of server credential objects
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
├── restart.sh            # (Optional) Remote restart script
├── static/               # Web UI assets for local control panel
│   ├── index.html        # Main dashboard
│   ├── app.js            # Frontend logic (forms, logs, state)
│   └── style.css         # Dashboard styling
└── templates/            # Configuration templates (Jinja-like syntax)
    ├── users.yml.template         # (Optional) Initial users for 3x-ui
    └── 3x-ui/
    │   ├── vless-tcp-reality.template    # Inbound protocol config
    │   └── vless-xhttp-reality.template  # Alternative protocol
    ├── caddy/
    │   └── Caddyfile.template    # Reverse proxy config
    ├── docker-compose/
    │   ├── docker-compose.yml.template   # Service definitions
    │   ├── Dockerfile-caddy-l4           # Custom Caddy with Reality support
    │   └── Dockerfile-nginx              # Nginx decoy server Dockerfile
    └── nginx-decoy/
        ├── default.conf.template  # Nginx reverse proxy config
        └── html/                  # Decoy website assets
            ├── index.html, access.html, operations.html, status.html, robots.txt
            └── style.css
            └── errors/            # Error pages (400, 403, 404, 405, 50x)
```

#### panel/setup.sh - Remote Deployment Script
- **Role**: Runs on remote VPS, configures the entire panel deployment
- **Execution Flow**:
  1. Validate prerequisites (root access, Docker installed)
  2. Create working directory structure (./working/)
  3. Process templates (substitute variables via envsubst/sed)
  4. Generate configs in ./working/
  5. Build and start Docker services
  6. Wait for SSL certificate (up to 300s)
  7. Output subscription URLs and admin credentials

- **Environment Variables** (passed from main.py):
  ```bash
  # Core config
  DOMAIN                    # e.g., proxy.example.com
  SECRET_PATH               # e.g., subs or secret123
  DECOY_PORT               # e.g., 80 or 8080
  XUI_INBOUND_PORT         # e.g., 443 (Reality protocol port)
  XUI_VERSION              # e.g., 1.7.5 (Docker image tag)
  
  # Subscription URLs (for cascade deployments)
  FOREIGN_SUB_URL          # URL to foreign node's subscription endpoint
  
  # Admin credentials
  ADMIN_USER               # e.g., admin
  ADMIN_PASSWORD           # Auto-generated if not provided
  
  # Security/TLS
  CERT_EMAIL              # For Let's Encrypt (e.g., admin@example.com)
  ```

- **When to Look Here**:
  - Debugging remote deployment failures
  - Modifying Docker service configuration
  - Changing template variable substitution
  - Adding new services or ports
  - Adjusting SSL certificate handling

#### panel/templates/ - Configuration Templates

All templates use `{{VARIABLE}}` placeholder syntax (processed by envsubst on remote):

**Caddyfile.template**
- **Purpose**: Caddy reverse proxy configuration
- **Key Sections**:
  - Email for Let's Encrypt: `{{CERT_EMAIL}}`
  - Reverse proxy rules for 3x-UI (internal port 2053)
  - Layer 4 proxy for Reality protocol (TCP port {{XUI_INBOUND_PORT}})
  - HTTP/HTTPS routing to Nginx decoy
- **Key Variables**:
  - `{{DOMAIN}}` - Public domain name
  - `{{XUI_INBOUND_PORT}}` - Reality protocol listening port
  - `{{CADDY_INTERNAL_PORT}}` - Internal Caddy port for admin API

**docker-compose.yml.template**
- **Purpose**: Define all Docker services and networking
- **Services**:
  - `3x-ui` - Main XRay panel (port 2053)
  - `caddy` - Custom reverse proxy (port 80, 443)
  - `nginx-decoy` - Fake website server (internal port)
- **Volumes**:
  - `./working/3x-ui/db/` - XRay configuration database
  - `./working/caddy/` - Caddy config and SSL certificates
  - `./working/nginx/` - Nginx config and static files
- **Key Variables**:
  - `{{XUI_VERSION}}` - Docker image tag for 3x-UI
  - All environment variables from setup.sh passed through

**nginx-decoy/default.conf.template**
- **Purpose**: Nginx configuration for decoy website
- **Key Features**:
  - Serves static HTML under `./working/nginx/html/`
  - Reverse proxies /admin paths to 3x-UI backend (security measure)
  - Custom 404/5xx error pages
- **Key Variables**:
  - `{{DOMAIN}}` - Server name directive
  - `{{DECOY_PORT}}` - Listen port for Nginx

**3x-ui/vless-tcp-reality.template & vless-xhttp-reality.template**
- **Purpose**: XRay inbound protocol configurations
- **Key Settings**:
  - Reality protocol settings (private key, public key, server name)
  - VLESS protocol handlers
  - Port binding ({{XUI_INBOUND_PORT}})
- **When to Modify**: Adding new protocol support or tweaking Reality settings

#### Docker Service Architecture (Panel)
```
Freedom/Proxy Node Docker Services:
┌─────────────────────────────────────┐
│ Docker Network: panel-caddy-net     │
├─────────────────────────────────────┤
│                                     │
│  ┌────────────────┐                 │
│  │    3x-ui       │                 │
│  │ • Port 2053    │                 │
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
├── server.py             # Python Flask app (subscription server)
├── setup.sh              # Remote deployment script
├── restart.sh            # Remote restart script
├── subs.yml              # Client database (manually edited or auto-generated)
├── force-subs.yml        # Custom subscription overrides (auto-managed)
└── templates/
    ├── docker-compose.yml.template  # Service definitions
    ├── Dockerfile-python            # Python 3.12 image
    └── caddy/
        └── Caddyfile.template       # Reverse proxy config
```

#### sub-server/server.py - Subscription Server Application

**Architecture**:
```
Client Browser
    ↓ HTTPS
Caddy (Port 443)
    ↓ HTTP
subs-server (Port 8000)
    ├─→ Check force-subs.yml for override
    ├─→ Lookup client in subs.yml
    ├─→ Route to RUSSIAN_SUB_URL or FOREIGN_SUB_URL
    └─→ Return subscription content or custom override
```

**Endpoints**:
| Path | Method | Purpose | Auth | Notes |
|------|--------|---------|------|-------|
| `/{SECRET_SUB_PATH}` | GET | Admin dashboard | Yes | Web UI, shows all clients |
| `/{SECRET_SUB_PATH}/login` | GET/POST | Admin login | No | Session cookie set on success |
| `/{SECRET_SUB_PATH}/logout` | GET | Clear session | No | Removes session cookie |
| `/{SECRET_SUB_PATH}/<client_name>` | GET | Subscription request | No | Returns vless:// config |
| `/{SECRET_SUB_PATH}/api/override` | POST | Set/clear override | Yes | Modifies force-subs.yml |

**Client Routing Logic**:
1. Admin POSTs override → stored in force-subs.yml
2. Client requests subscription:
   - Check `force-subs.yml` first → if found, return it directly
   - Lookup client in `subs.yml`:
     - If in `proxy` section → fetch from `RUSSIAN_SUB_URL`
     - If in `freedom` section → fetch from `FOREIGN_SUB_URL`
   - Return subscription content (or 404 if not found)

**Key Features**:
- **Web UI Dashboard**:
  - Collapsible sections (proxy clients, freedom clients, overrides)
  - QR codes (toggleable) for each subscription URL
  - Copy buttons with visual feedback
  - Override editor with inline base64 encoding
  - Dark theme, responsive design
  
- **Authentication**:
  - Session cookie: HMAC-SHA256 signed, 12-hour TTL
  - Timing-safe comparison (constant-time verification)
  - HTTPS-only, SameSite=Lax, path-scoped
  - HTTP Basic Auth also supported
  
- **Logging**:
  - INFO level: subscription fetches, overrides, auth attempts
  - Format: `YYYY-MM-DD HH:MM:SS LEVEL message`
  - Output to stdout (Docker captures it)

**Environment Variables** (passed from main.py):
```bash
SECRET_SUB_PATH          # e.g., subs or secret123
DOMAIN                   # e.g., sub.example.com
RUSSIAN_SUB_URL          # e.g., https://proxy-node/subs
FOREIGN_SUB_URL          # e.g., https://freedom-node/subs
ADMIN_USER              # e.g., admin
ADMIN_PASSWORD          # Auto-generated or provided
AUTH_SESSION_SECRET     # Defaults to ADMIN_PASSWORD
LOG_LEVEL              # INFO, DEBUG (default: INFO)
```

**When to Look Here**:
- Adding subscription filtering or transformation logic
- Modifying authentication mechanisms
- Changing client routing or override logic
- Debugging subscription fetch failures
- Adding new API endpoints

#### sub-server/setup.sh - Remote Deployment Script
- **Role**: Deploy subscription server to remote VPS
- **Execution Flow**:
  1. Validate Docker/dependencies
  2. Create ./working directory structure
  3. Generate subs.yml from environment variables:
     ```yaml
     proxy:
       - client1
       - client2
     freedom:
       - freedom-user
     ```
  4. Process templates (Caddyfile, docker-compose.yml)
  5. Build and start Docker services (Caddy + Python server)
  6. Wait for SSL certificate (Let's Encrypt)

**Key Environment Variables**:
- `PROXY_CLIENTS` - Space-separated client list for Russian node
- `FREEDOM_CLIENTS` - Space-separated client list for foreign node

#### sub-server/subs.yml - Client Database
```yaml
# Client assignments to proxy groups
proxy:
  - end-user
  - local-client-1
  - local-client-2

freedom:
  - foreign-user
  - international-client
```

**Format**: YAML with two sections (proxy, freedom)
**Management**: 
- Auto-generated by setup.sh from environment variables
- Can be manually edited after deployment
- Changes take effect immediately (server reloads on access)

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
│  │ • Reads subs.yml           │    │
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
- `backup_sub` - Backup subs.yml, force-subs.yml, Caddyfile, SSL certs
- `rollback_sub` - Restore from backup archive

---

## Template Variable Reference

### Panel Templates Variables

| Variable | Example | Usage | Source |
|----------|---------|-------|--------|
| `{{DOMAIN}}` | proxy.example.com | Caddy server_name, Let's Encrypt email | User input (form) |
| `{{SECRET_PATH}}` | subs | Subscription endpoint path | User input (form) |
| `{{DECOY_PORT}}` | 80 or 8080 | Nginx listen port | User input (form) |
| `{{XUI_INBOUND_PORT}}` | 443 | Reality protocol TCP port | User input (form) |
| `{{XUI_VERSION}}` | 1.7.5 | 3x-UI Docker image tag | User input (form) |
| `{{CERT_EMAIL}}` | admin@example.com | Let's Encrypt email | Derived from DOMAIN |
| `{{FOREIGN_SUB_URL}}` | https://freedom/subs | Subscription URL (for proxy node) | Previous deployment |
| `{{ADMIN_USER}}` | admin | 3x-UI admin username | User input (form) |
| `{{ADMIN_PASSWORD}}` | (auto) | 3x-UI admin password | Auto-generated or user input |
| `{{CADDY_INTERNAL_PORT}}` | 2000 | Internal Caddy admin API port | Calculated |

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

## Code Patterns & Conventions

### Async SSH Pattern
```python
# In ssh_deployer.py
async with SSHDeployer(host, port, user, password) as deployer:
    # Execute command with log callback
    success, output = await deployer.exec_command(
        "echo 'Hello'",
        log_callback=lambda msg: print(msg)
    )
    
    # Transfer file
    success = await deployer.upload_file(
        local_path="./config.yml",
        remote_path="/tmp/config.yml",
        log_callback=lambda msg: print(msg)
    )
```

### Template Processing
```bash
# In setup.sh (remote)
# Input: templates/Caddyfile.template with {{DOMAIN}}, {{PORT}}
# Output: ./working/Caddyfile with values substituted

envsubst < /tmp/Caddyfile.template > ./working/Caddyfile
# OR
sed "s|{{DOMAIN}}|$DOMAIN|g; s|{{PORT}}|$PORT|g" /tmp/Caddyfile.template > ./working/Caddyfile
```

### Logging Pattern
```python
# In main.py
@app.route('/api/deploy', methods=['POST'])
def deploy():
    def log(message, level="INFO"):
        # Send to all connected SSE clients
        yield f"data: {json.dumps({'level': level, 'message': message})}\n\n"
    
    # Use in deployment
    asyncio.run(ssh_deployer.run_deployment(..., log_callback=log))
```

### Cross-Platform Script Handling
```python
# In main.py/ssh_deployer.py
# Detect OS and use appropriate script variant
if platform.system() == "Windows":
    script = "start_deployment.bat"
elif platform.system() == "Darwin":  # macOS
    script = "start_deployment.sh"
else:  # Linux
    script = "start_deployment.sh"
```

### Configuration Persistence
```yaml
# setup_backup.yml structure
freedom_node:
  host: 1.2.3.4
  port: 22
  # ... persist all form fields

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
4. ssh_deployer creates SSHDeployer connection
5. Uploads panel/setup.sh to remote /tmp/
6. Executes: bash /tmp/setup.sh (with env vars)
7. setup.sh processes templates → generates ./working/ configs
8. setup.sh builds Docker services
9. Docker Compose starts services
10. Wait for Let's Encrypt certificate
11. Return subscription URLs and credentials
12. main.py displays results to UI
```

### Cascade Subscription Deployment
```
1. Stage 1: Deploy freedom node (single mode)
   → Get FOREIGN_SUB_URL from response
2. Stage 2: Deploy proxy node with FOREIGN_SUB_URL
   → Get RUSSIAN_SUB_URL from response
3. Stage 3: Deploy sub-server with both URLs
   → subs.yml auto-generated with client lists
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
- **Storage**: Credentials in setup_backup.yml (local only, should be encrypted)
- **Validation**: Pre-flight test_connection() before each deployment

### 3x-UI Admin Access
- **Credentials**: Stored in 3x-UI SQLite database
- **Access**: Via Caddy reverse proxy on port 443
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
- **Multi-deployment modes**: 8 different deployment strategies
- **Optional subscription management**: Centralized multi-node proxy routing
- **Cross-platform support**: Windows, macOS, Linux CLI

Key design principles:
- **Abstraction**: Hide Docker/Caddy complexity behind forms
- **Reliability**: Pre-flight checks, error logging, session persistence
- **Portability**: Same UI works across platforms
- **Transparency**: Real-time logs streamed to user
- **Modularity**: Panel and sub-server components can be deployed independently

Start debugging by checking the log stream in main.py → trace to ssh_deployer.py → review remote setup.sh output.
