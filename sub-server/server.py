#!/usr/bin/env python3
"""Subscription server: proxy + web interface.

GET /<SECRET_SUB_PATH>               - web page with client cards (links + QR).
GET /<SECRET_SUB_PATH>?raw=1         - plain text list of target subscription URLs
                                       (also served for non-browser clients).
GET /<SECRET_SUB_PATH>/<client_name> - subscription content fetched from the
                                       node's subscription URL.
POST /<SECRET_SUB_PATH>/api/override - set/clear a custom vless:// override for a
                                       client. Body: {"client": "...", "value": "..."}.
                                       value="" clears the override. Values are stored
                                       in FORCE_FILE as base64.
GET  /<SECRET_SUB_PATH>/api/logs     - real-time log stream (SSE) tailing LOG_FILE,
                                       the same output docker logs -f subs-server shows.

The client name is looked up in the node registry (nodes.json):
  - each node has an id, a display name, a subscription base URL and a
    client list; clients are routed to the node that owns them.
  - a legacy subs.yml (two lists: proxy and freedom) is only read once to
    seed nodes.json when the registry is missing or empty.

Env vars:
  FORCE_FILE      path to force-subs.yml overrides (default: force-subs.yml)
  NODES_FILE      path to nodes.json registry (default: nodes.json)
  LOG_FILE        path to a log file tailed by the /api/logs SSE stream
                  (default: sub-server.log)
  SECRET_SUB_PATH path prefix from the domain root (default: subs)
  RUSSIAN_SUB_URL subscription URL of the Russian node (fallback only)
  FOREIGN_SUB_URL subscription URL of the non-Russian node (fallback only)
  PUBLIC_URL      optional public base URL (e.g. https://vpn.example.com);
                  if unset, derived from the request Host/X-Forwarded-* headers
  HOST            listen address (default: 0.0.0.0)
  PORT            listen port (default: 8080)
"""

import base64
import hmac
import html
import json
import logging
import os
import queue
import re
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import yaml
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from logging.handlers import RotatingFileHandler
from urllib.parse import unquote

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("sub-server")

LOG_LINE_RE = re.compile(r"^(\S+ \S+) (\w+) (.*)$")
LOG_HISTORY_LINES = 200
LOG_HISTORY_BYTES = 256 * 1024

DATABASE_FILE = os.environ.get("DATABASE_FILE", "subs.yml")
FORCE_FILE = os.environ.get("FORCE_FILE", "force-subs.yml")
NODES_FILE = os.environ.get("NODES_FILE", "nodes.json")
LOG_FILE = os.environ.get("LOG_FILE", "sub-server.log")
SECRET_SUB_PATH = os.environ.get("SECRET_SUB_PATH", "subs").strip("/")
RUSSIAN_SUB_URL = os.environ.get("RUSSIAN_SUB_URL", "")
FOREIGN_SUB_URL = os.environ.get("FOREIGN_SUB_URL", "")
PUBLIC_URL = os.environ.get("PUBLIC_URL", "").strip().strip("/")
ADMIN_USER = os.environ.get("ADMIN_USER", "").strip()
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "").strip()
AUTH_SESSION_SECRET = os.environ.get("AUTH_SESSION_SECRET", "").strip() or secrets.token_hex(32)
SESSION_TTL_SECONDS = int(os.environ.get("AUTH_SESSION_TTL", "43200"))
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "8080"))

GROUP_LABELS = {
    "proxy": "Proxy (РФ)",
    "freedom": "Freedom (зарубежье)",
    "force": "Кастом (force-subs.yml)",
}

NODES = []
FORCE_SUBS = {}
DATA_LOCK = threading.Lock()
ACTIVITY_LOCK = threading.Lock()
LOGIN_LOCK = threading.Lock()
LOGIN_ATTEMPTS = {}  # ip -> {"count": int, "lockout_until": float, "last_attempt": float}

PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Сервер подписок</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet">
<style>
:root {
    --bg-dark: #0f172a;
    --card-bg: rgba(30, 41, 59, 0.7);
    --border-color: rgba(255, 255, 255, 0.1);
    --primary-color: #3b82f6;
    --primary-hover: #2563eb;
    --success-color: #10b981;
    --success-hover: #059669;
    --text-primary: #f8fafc;
    --text-secondary: #94a3b8;
    --accent-glow: rgba(59, 130, 246, 0.25);
}
html, body {
    height: 100vh;
    overflow: hidden;
}
body {
    font-family: 'Inter', sans-serif;
    background-color: var(--bg-dark);
    background-image:
        radial-gradient(at 0% 0%, rgba(59, 130, 246, 0.2) 0px, transparent 50%),
        radial-gradient(at 100% 100%, rgba(16, 185, 129, 0.15) 0px, transparent 50%),
        radial-gradient(at 50% 50%, rgba(15, 23, 42, 0.8) 0px, rgba(15, 23, 42, 1) 100%);
    color: var(--text-primary);
    margin: 0;
    padding: 0;
}

/* Global Custom Scrollbars */
* {
    box-sizing: border-box;
    margin: 0;
    padding: 0;
    scrollbar-width: thin;
    scrollbar-color: rgba(255, 255, 255, 0.2) rgba(15, 23, 42, 0.6);
}
::-webkit-scrollbar {
    width: 6px;
    height: 6px;
}
::-webkit-scrollbar-track {
    background: rgba(15, 23, 42, 0.6);
    border-radius: 4px;
}
::-webkit-scrollbar-thumb {
    background: rgba(255, 255, 255, 0.2);
    border-radius: 4px;
}
::-webkit-scrollbar-thumb:hover {
    background: var(--primary-color);
}

.app-shell {
    display: flex;
    flex-direction: column;
    height: 100vh;
    width: 100%;
    overflow: hidden;
}
.app-top-bar {
    flex-shrink: 0;
    width: 100%;
    background: transparent;
    z-index: 50;
}
.top-bar-inner {
    width: 100%;
    max-width: 1400px;
    margin: 0 auto;
    padding: 20px 24px 0 24px;
    box-sizing: border-box;
}
.app-body {
    flex: 1 1 0;
    min-height: 0;
    width: 100%;
    overflow: hidden;
}
.app-body-inner {
    width: 100%;
    max-width: 1400px;
    height: 100%;
    margin: 0 auto;
    padding: 0 24px 24px 24px;
    box-sizing: border-box;
}
.cards-scroll-area {
    flex: 1 1 0;
    min-width: 0;
    height: 100%;
    overflow-y: auto;
    overflow-x: hidden;
    padding-top: 36px;
    padding-bottom: 40px;
    padding-right: 6px;
    box-sizing: border-box;
    mask-image: linear-gradient(to bottom, transparent 0px, transparent 4px, black 32px, black 100%);
    -webkit-mask-image: linear-gradient(to bottom, transparent 0px, transparent 4px, black 32px, black 100%);
}
.app-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 14px;
    flex-wrap: wrap;
    gap: 16px;
}
.logo-area { display: flex; align-items: center; gap: 14px; }
.logo-icon {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 44px;
    height: 44px;
    background: rgba(255, 255, 255, 0.05);
    border-radius: 12px;
    border: 1px solid var(--border-color);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
    flex-shrink: 0;
}
.app-header h1 {
    font-size: 1.45rem;
    font-weight: 700;
    letter-spacing: -0.5px;
    line-height: 1.2;
    margin: 0;
}
.subtitle {
    font-size: 0.85rem;
    color: var(--text-secondary);
    margin-top: 3px;
    line-height: 1.3;
}
.subtitle a { color: var(--primary-color); text-decoration: none; transition: color 0.15s ease; }
.subtitle a:hover { text-decoration: underline; color: #60a5fa; }
.header-actions { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.header-search {
    width: min(280px, 35vw);
    height: 36px;
    padding: 0 14px;
    border: 1px solid var(--border-color);
    border-radius: 999px;
    outline: none;
    background: rgba(30, 41, 59, .72);
    color: var(--text-primary);
    box-shadow: inset 0 1px 0 rgba(255,255,255,.04), 0 8px 24px rgba(2, 6, 23, .18);
    font: inherit;
    font-size: .82rem;
    line-height: 34px;
    box-sizing: border-box;
    transition: border-color .2s ease, box-shadow .2s ease, background .2s ease;
}
.header-search::placeholder { color: var(--text-secondary); opacity: 1; }
.header-search:focus {
    border-color: rgba(59, 130, 246, .72);
    background: rgba(30, 41, 59, .94);
    box-shadow: 0 0 0 3px var(--accent-glow), 0 8px 24px rgba(2, 6, 23, .24);
}

.status-badge {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    height: 36px;
    font-size: 0.8rem;
    font-weight: 500;
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid var(--border-color);
    padding: 0 14px;
    border-radius: 999px;
    box-sizing: border-box;
    white-space: nowrap;
    user-select: none;
}
.status-badge .stats-label {
    color: var(--text-primary);
    cursor: pointer;
}
.status-badge .stats-label:hover {
    color: #60a5fa;
}
.status-badge .stats-divider {
    width: 1px;
    height: 14px;
    background: var(--border-color);
    margin: 0 2px;
}
.status-badge .stat-item {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    cursor: pointer;
    color: var(--text-secondary);
    border-radius: 999px;
    transition: background 0.15s ease, box-shadow 0.15s ease, color 0.15s ease;
}
.status-badge .stat-item:hover {
    color: var(--text-primary);
    background: rgba(255, 255, 255, 0.07);
}
.status-badge .stat-item span:last-child {
    font-variant-numeric: tabular-nums;
    font-weight: 600;
    color: var(--text-primary);
}
.status-badge .dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    flex-shrink: 0;
}
.status-badge .dot.dot-recent {
    background-color: var(--success-color);
    color: var(--success-color);
    box-shadow: 0 0 6px currentColor;
}
.status-badge .dot.dot-ever {
    background-color: #f59e0b;
    color: #f59e0b;
    box-shadow: 0 0 6px currentColor;
}
.status-badge .dot.dot-never {
    background-color: #64748b;
    color: #64748b;
    box-shadow: 0 0 4px currentColor;
}
/* Active filter: animated pulsing glow in the status color */
.status-badge .stat-item.filtering .dot {
    animation: status-dot-pulse 1.6s ease-in-out infinite;
}
.status-badge .stat-item.filtering span:last-child {
    animation: status-text-pulse 1.6s ease-in-out infinite;
}
.status-badge .stat-item.filtering[data-filter="recent"] span:last-child { color: var(--success-color); }
.status-badge .stat-item.filtering[data-filter="ever"] span:last-child { color: #f59e0b; }
.status-badge .stat-item.filtering[data-filter="never"] span:last-child { color: #94a3b8; }
@keyframes status-dot-pulse {
    0%, 100% { transform: scale(1); box-shadow: 0 0 2px currentColor, 0 0 6px currentColor; }
    50% { transform: scale(1.3); box-shadow: 0 0 8px currentColor, 0 0 18px currentColor; }
}
@keyframes status-text-pulse {
    0%, 100% { text-shadow: 0 0 2px currentColor, 0 0 6px currentColor; }
    50% { text-shadow: 0 0 5px currentColor, 0 0 14px currentColor; }
}

.cards-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(min(540px, 100%), 1fr));
    gap: 16px;
}
.cards-grid.stacked { grid-template-columns: minmax(0, 1fr); }
.cards-grid.collapsed { display: none; }
.card {
    background: var(--card-bg);
    backdrop-filter: blur(24px);
    -webkit-backdrop-filter: blur(24px);
    border: 1px solid var(--border-color);
    border-radius: 16px;
    padding: 20px;
    transition: border-color 0.2s ease;
}
.card:hover {
    border-color: rgba(255, 255, 255, 0.16);
}
.client-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    margin-bottom: 12px;
    flex-wrap: wrap;
}
.client-name-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    background: rgba(59, 130, 246, 0.15);
    border: 1px solid rgba(59, 130, 246, 0.4);
    color: #93c5fd;
    padding: 4px 10px;
    border-radius: 6px;
    font-size: 0.85rem;
    font-weight: 600;
}
.client-name-badge svg { flex-shrink: 0; }
.group-badge {
    font-size: 0.75rem;
    color: var(--text-secondary);
    padding: 4px 10px;
    border-radius: 6px;
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid var(--border-color);
}
.force-tag {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    font-size: 0.72rem;
    font-weight: 600;
    color: #fbbf24;
    border: 1px solid rgba(251, 191, 36, 0.4);
    background: rgba(251, 191, 36, 0.1);
    padding: 2px 8px;
    border-radius: 6px;
}
.client-link-group { display: flex; flex-direction: column; }
.client-link-label {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    font-size: 0.78rem;
    color: var(--text-secondary);
    font-weight: 500;
    margin-top: 10px;
}
.client-link-label svg { color: var(--text-secondary); flex-shrink: 0; }
.client-link-label:first-child { margin-top: 0; }
.client-link-row {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-top: 6px;
    background: rgba(15, 23, 42, 0.6);
    padding: 8px 12px;
    border-radius: 8px;
    border: 1px solid rgba(255, 255, 255, 0.06);
}
.client-link-text {
    flex: 1;
    min-width: 0;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.78rem;
    color: #e2e8f0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    word-break: break-all;
}

/* Button styles matching Deployer */
.btn-sm {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid var(--border-color);
    color: var(--text-primary);
    border-radius: 6px;
    padding: 6px 11px;
    font-size: 0.75rem;
    font-weight: 500;
    cursor: pointer;
    font-family: inherit;
    white-space: nowrap;
    transition: all 0.2s ease;
}
.btn-sm:hover {
    background: rgba(255, 255, 255, 0.12);
    border-color: rgba(255, 255, 255, 0.2);
}
.btn-sm.btn-primary, .btn-primary {
    background: var(--primary-color);
    border-color: var(--primary-color);
    color: #fff;
}
.btn-sm.btn-primary:hover, .btn-primary:hover {
    background: var(--primary-hover);
    border-color: var(--primary-hover);
    box-shadow: 0 0 12px var(--accent-glow);
}
.btn-sm.active {
    background: var(--primary-color);
    border-color: var(--primary-color);
    color: #fff;
    box-shadow: 0 0 10px var(--accent-glow);
}

.management-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 16px;
    margin: 0;
    position: relative;
    z-index: 30;
}
.management-panel {
    padding: 18px;
    background: rgba(30, 41, 59, 0.55);
    border: 1px solid var(--border-color);
    border-radius: 14px;
    backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);
    position: relative;
    z-index: 1;
}
.management-panel:focus-within,
.management-panel:has(.node-select.open) {
    z-index: 50;
}
.management-title {
    display: flex;
    align-items: center;
    gap: 8px;
    font-weight: 600;
    font-size: 0.9rem;
    margin-bottom: 12px;
    color: var(--text-primary);
}
.management-title svg { color: var(--primary-color); flex-shrink: 0; }
.management-row {
    display: flex;
    align-items: stretch;
    gap: 8px;
    margin-top: 8px;
    position: relative;
}
.management-row input, .management-row select {
    flex: 1;
    min-width: 0;
    height: 38px;
    box-sizing: border-box;
    border: 1px solid var(--border-color);
    border-radius: 8px;
    background: rgba(15, 23, 42, 0.8);
    color: var(--text-primary);
    padding: 0 12px;
    font: inherit;
    font-size: .82rem;
    line-height: 36px;
    outline: none;
    transition: border-color .2s ease, box-shadow .2s ease;
}
.management-row input:focus, .management-row select:focus {
    border-color: rgba(59, 130, 246, .72);
    box-shadow: 0 0 0 3px var(--accent-glow);
}

/* Dropdown native select arrow */
select {
    appearance: none;
    -webkit-appearance: none;
    background-image: url("data:image/svg+xml,%3Csvg width='10' height='6' viewBox='0 0 10 6' fill='none' xmlns='http://www.w3.org/2000/svg'%3E%3Cpath d='M1 1L5 5L9 1' stroke='%2394a3b8' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E");
    background-position: calc(100% - 12px) center;
    background-size: 10px 6px;
    background-repeat: no-repeat;
    padding-right: 32px !important;
    cursor: pointer;
}
select:focus {
    background-image: url("data:image/svg+xml,%3Csvg width='10' height='6' viewBox='0 0 10 6' fill='none' xmlns='http://www.w3.org/2000/svg'%3E%3Cpath d='M1 1L5 5L9 1' stroke='%233b82f6' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E");
}
select option {
    background-color: #0f172a;
    color: #f8fafc;
    padding: 8px;
}

/* Custom Node Select Component */
.node-select { position: relative; width: 100%; flex: 1; min-width: 0; z-index: 10; display: flex; }
.node-select.open { z-index: 100; }
.node-select-trigger {
    display: flex;
    align-items: center;
    justify-content: space-between;
    width: 100%;
    height: 38px;
    box-sizing: border-box;
    padding: 0 12px;
    background: rgba(15, 23, 42, .9);
    border: 1px solid var(--border-color);
    border-radius: 8px;
    color: var(--text-primary);
    font: inherit;
    font-size: .82rem;
    cursor: pointer;
    transition: all .2s ease;
}
.node-select-trigger:hover, .node-select.open .node-select-trigger {
    border-color: rgba(59, 130, 246, .6);
    background: rgba(30, 41, 59, .95);
}
.node-select.open .node-select-trigger {
    box-shadow: 0 0 0 3px var(--accent-glow);
}
.node-select-arrow {
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--text-secondary);
    transition: transform .25s cubic-bezier(0.16, 1, 0.3, 1), color .2s ease;
}
.node-select.open .node-select-arrow {
    transform: rotate(180deg);
    color: var(--primary-color);
}
.node-select-options {
    position: absolute;
    z-index: 999;
    top: calc(100% + 6px);
    left: 0;
    right: 0;
    padding: 5px;
    background: rgba(30, 41, 59, .97);
    border: 1px solid rgba(255,255,255,.12);
    border-radius: 10px;
    box-shadow: 0 10px 25px rgba(0,0,0,.5), 0 0 15px rgba(59, 130, 246, 0.15);
    backdrop-filter: blur(24px);
    -webkit-backdrop-filter: blur(24px);
    opacity: 0;
    visibility: hidden;
    transform: translateY(-6px) scale(.98);
    transition: all .18s cubic-bezier(0.16, 1, 0.3, 1);
    max-height: 220px;
    overflow-y: auto;
}
.node-select.open .node-select-options {
    opacity: 1;
    visibility: visible;
    transform: translateY(0) scale(1);
}
.node-select-option {
    padding: 8px 12px;
    color: var(--text-secondary);
    border-radius: 6px;
    cursor: pointer;
    font-size: .82rem;
    font-weight: 500;
    transition: all 0.15s ease;
}
.node-select-option:hover, .node-select-option.selected {
    background: rgba(59,130,246,.2);
    color: var(--text-primary);
}

.management-row .btn-sm {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    height: 38px;
    box-sizing: border-box;
    padding: 0 16px;
    border: 1px solid var(--primary-color);
    border-radius: 8px;
    font-size: 0.82rem;
    font-weight: 600;
    flex-shrink: 0;
}
.btn-client-delete, .btn-node-delete {
    color: #fecaca;
    border-color: rgba(239, 68, 68, .35);
    padding: 5px 8px;
    line-height: 1;
}
.btn-client-delete:hover, .btn-node-delete:hover {
    background: rgba(239, 68, 68, .2);
    border-color: rgba(239, 68, 68, .5);
}
.btn-client-delete svg, .btn-node-delete svg { width: 14px; height: 14px; display: block; }
.btn-client-edit, .btn-node-edit {
    color: #bfdbfe;
    border-color: rgba(59, 130, 246, .35);
    padding: 5px 8px;
    line-height: 1;
}
.btn-client-edit svg, .btn-node-edit svg { width: 14px; height: 14px; display: block; }
.btn-client-edit:hover, .btn-node-edit:hover {
    background: rgba(59, 130, 246, .2);
    border-color: rgba(59, 130, 246, .5);
}

.edit-modal {
    position: fixed;
    inset: 0;
    z-index: 1000;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 20px;
}
.edit-modal[hidden] { display: none; }
.edit-modal-backdrop {
    position: absolute;
    inset: 0;
    background: rgba(2, 6, 23, .7);
    backdrop-filter: blur(8px);
    -webkit-backdrop-filter: blur(8px);
}
.edit-modal-card {
    position: relative;
    width: min(480px, 100%);
    background: rgba(30, 41, 59, .97);
    border: 1px solid var(--border-color);
    border-radius: 16px;
    padding: 24px;
    box-shadow: 0 24px 60px rgba(0, 0, 0, .6);
    backdrop-filter: blur(24px);
    -webkit-backdrop-filter: blur(24px);
}
.edit-modal-title { font-size: 1.1rem; font-weight: 700; margin-bottom: 18px; color: var(--text-primary); }
.edit-modal-field { margin-bottom: 14px; }
.edit-modal-field label { display: block; font-size: .8rem; font-weight: 500; color: var(--text-secondary); margin-bottom: 6px; }
.edit-modal-field input, .edit-modal-field select {
    width: 100%;
    border: 1px solid var(--border-color);
    border-radius: 8px;
    background: rgba(15, 23, 42, 0.9);
    color: var(--text-primary);
    padding: 9px 12px;
    font: inherit;
    font-size: .85rem;
    outline: none;
    transition: border-color .2s ease, box-shadow .2s ease;
}
.edit-modal-field input:focus, .edit-modal-field select:focus {
    border-color: rgba(59, 130, 246, .72);
    box-shadow: 0 0 0 3px var(--accent-glow);
}
.edit-modal-hint { font-size: .74rem; color: var(--text-secondary); margin-top: -6px; margin-bottom: 14px; }
.edit-modal-actions { display: flex; gap: 10px; justify-content: flex-end; margin-top: 20px; }
.btn-sm.btn-save { border-color: rgba(16, 185, 129, 0.4); background: rgba(16, 185, 129, 0.2); color: #6ee7b7; }
.btn-sm.btn-save:hover { background: rgba(16, 185, 129, 0.32); border-color: rgba(16, 185, 129, 0.6); color: #fff; }

.node-management { position: relative; }
.management-error {
    position: absolute;
    right: 16px;
    bottom: 58px;
    z-index: 100;
    max-width: calc(100% - 32px);
    color: #fecaca;
    border: 1px solid rgba(239, 68, 68, .5);
    background: rgba(127, 29, 29, .8);
    backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);
    border-radius: 8px;
    padding: 8px 12px;
    font-size: .78rem;
    box-shadow: 0 8px 24px rgba(127, 29, 29, .3);
}

@media (max-width: 700px) {
    .management-grid { grid-template-columns: 1fr; }
    .management-row { flex-wrap: wrap; }
    .management-row .btn-sm { width: 100%; }
    .header-search { width: 100%; order: 3; }
    .top-bar-inner { padding: 14px 16px 0 16px; }
    .app-body-inner { padding: 0 16px 16px 16px; }
}

.client-link-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; margin-top: 12px; }
@media (max-width: 900px) { .client-link-grid { grid-template-columns: 1fr; } }
.client-link-col { display: flex; flex-direction: column; min-width: 0; }
.qr-panel { display: none; margin-top: 14px; }
.qr-panel.open { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
@media (max-width: 900px) { .qr-panel.open { grid-template-columns: 1fr; } }
.qr-item {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 8px;
    background: rgba(15, 23, 42, 0.6);
    border: 1px solid rgba(255, 255, 255, 0.06);
    border-radius: 10px;
    padding: 14px;
}
.qr-item img { width: 170px; height: 170px; background: #fff; border-radius: 8px; padding: 6px; }
.qr-item span { font-size: 0.74rem; color: var(--text-secondary); }

.override-block { margin-top: 14px; min-width: 0; }
.override-row {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-top: 6px;
    min-width: 0;
    background: rgba(15, 23, 42, 0.6);
    padding: 8px 12px;
    border-radius: 8px;
    border: 1px solid rgba(251, 191, 36, 0.25);
}
.override-text {
    flex: 1;
    min-width: 0;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.75rem;
    color: #fbbf24;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    word-break: break-all;
}
.override-text.muted { color: var(--text-secondary); }
.override-editor { display: none; margin-top: 8px; }
.override-editor.open { display: block; }
.override-input {
    width: 100%;
    resize: vertical;
    background: rgba(15, 23, 42, 0.9);
    color: var(--text-primary);
    border: 1px solid var(--border-color);
    border-radius: 8px;
    padding: 9px 12px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.78rem;
    outline: none;
    transition: border-color .2s ease, box-shadow .2s ease;
}
.override-input:focus {
    border-color: rgba(59, 130, 246, .72);
    box-shadow: 0 0 0 3px var(--accent-glow);
}
.override-hint { font-size: 0.72rem; color: var(--text-secondary); margin-top: 6px; }
.override-editor-actions { display: flex; gap: 8px; margin-top: 8px; }
.override-editor-actions .btn-sm.btn-override-save {
    border-color: rgba(16, 185, 129, 0.4);
    background: rgba(16, 185, 129, 0.18);
    color: #6ee7b7;
}
.override-editor-actions .btn-sm.btn-override-save:hover {
    background: rgba(16, 185, 129, 0.3);
    color: #fff;
}

.client-status {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-top: 14px;
    padding: 8px 12px;
    background: rgba(15, 23, 42, 0.6);
    border: 1px solid rgba(255, 255, 255, 0.05);
    border-radius: 8px;
    font-size: 0.72rem;
    color: var(--text-secondary);
}
.status-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: #64748b;
    flex-shrink: 0;
}
.status-dot.st-recent, .status-dot.st-ok { background: var(--success-color); box-shadow: 0 0 6px var(--success-color); }
.status-dot.st-ever { background: #f59e0b; box-shadow: 0 0 6px #f59e0b; }
.status-dot.st-never { background: #64748b; }
.status-dot.st-err { background: #f87171; box-shadow: 0 0 6px #f87171; }
.status-text { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.note {
    font-size: 0.78rem;
    color: var(--text-secondary);
    margin-top: 6px;
    padding: 8px 12px;
    background: rgba(15, 23, 42, 0.6);
    border-radius: 8px;
    border: 1px dashed rgba(255, 255, 255, 0.1);
}

.section-header {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 0.92rem;
    font-weight: 600;
    margin-bottom: 14px;
    color: var(--text-primary);
    cursor: pointer;
    user-select: none;
    transition: color 0.15s ease;
}
.section-header:hover { color: #93c5fd; }
.section-header .chevron {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    color: var(--text-secondary);
    transition: transform 0.25s cubic-bezier(0.16, 1, 0.3, 1), color 0.2s ease;
    flex-shrink: 0;
}
.section-header:hover .chevron { color: var(--primary-color); }
.section-header .chevron.closed { transform: rotate(-90deg); }
.section-header .section-title-icon {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    color: var(--primary-color);
    flex-shrink: 0;
}
.section-header .line { flex: 1; height: 1px; background: var(--border-color); }
.section-header + .cards-grid { margin-bottom: 24px; }

.btn-logout {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
    height: 36px;
    padding: 0 14px;
    border: 1px solid rgba(239, 68, 68, 0.3);
    border-radius: 999px;
    background: rgba(239, 68, 68, 0.15);
    color: #fecaca;
    font-size: 0.8rem;
    font-weight: 500;
    text-decoration: none;
    box-sizing: border-box;
    white-space: nowrap;
    transition: all 0.2s ease;
}
.btn-logout:hover {
    background: rgba(239, 68, 68, 0.28);
    border-color: rgba(239, 68, 68, 0.5);
    color: #fff;
}
.dashboard-layout {
    display: flex;
    gap: 20px;
    align-items: stretch;
    height: 100%;
    width: 100%;
}
.btn-logs {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
    height: 36px;
    padding: 0 14px;
    border-radius: 999px;
    font-size: 0.8rem;
    box-sizing: border-box;
    white-space: nowrap;
}

/* Log Panel Sidebar */
.log-panel {
    width: min(420px, 100%);
    flex-shrink: 0;
    display: flex;
    flex-direction: column;
    height: 99%;
    margin-top: 16px;
    background: rgba(15, 23, 42, 0.85);
    border: 1px solid var(--border-color);
    border-radius: 16px;
    overflow: hidden;
    backdrop-filter: blur(24px);
    -webkit-backdrop-filter: blur(24px);
    box-shadow: 0 20px 40px rgba(0, 0, 0, 0.4);
    box-sizing: border-box;
    transition: opacity 0.2s ease, transform 0.2s ease;
}
.log-panel.hidden { display: none; }
.log-panel-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    padding: 10px 14px;
    border-bottom: 1px solid var(--border-color);
    background: rgba(30, 41, 59, 0.4);
    min-width: 0;
    flex-shrink: 0;
}
.log-panel-title {
    display: flex;
    align-items: center;
    gap: 6px;
    color: var(--text-primary);
    font-size: 0.82rem;
    font-weight: 600;
    white-space: nowrap;
    flex-shrink: 0;
}
.log-panel-actions {
    display: flex;
    align-items: center;
    gap: 6px;
    min-width: 0;
    flex-shrink: 0;
}

/* Custom Checkbox for Log Auto-scroll */
.log-autoscroll {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    font-size: 0.72rem;
    color: var(--text-secondary);
    cursor: pointer;
    user-select: none;
    font-weight: 500;
    white-space: nowrap;
    flex-shrink: 0;
    transition: color 0.15s ease;
}
.log-autoscroll:hover { color: var(--text-primary); }
.log-autoscroll input[type="checkbox"] {
    appearance: none;
    -webkit-appearance: none;
    width: 14px;
    height: 14px;
    border: 1.5px solid var(--border-color);
    border-radius: 4px;
    outline: none;
    background-color: rgba(15, 23, 42, 0.6);
    cursor: pointer;
    display: grid;
    place-content: center;
    flex-shrink: 0;
    transition: all 0.2s ease;
}
.log-autoscroll input[type="checkbox"]::before {
    content: "";
    width: 6px;
    height: 6px;
    border-radius: 1px;
    transform: scale(0);
    transition: transform 0.15s ease-in-out;
    background-color: var(--primary-color);
}
.log-autoscroll input[type="checkbox"]:checked {
    border-color: var(--primary-color);
    background-color: rgba(59, 130, 246, 0.15);
    box-shadow: 0 0 6px var(--accent-glow);
}
.log-autoscroll input[type="checkbox"]:checked::before {
    transform: scale(1);
}
.log-autoscroll:hover input[type="checkbox"] {
    border-color: var(--primary-color);
}

.log-panel-actions .btn-sm {
    padding: 4px 8px;
    font-size: 0.72rem;
}
.log-close-btn {
    padding: 4px 7px !important;
    line-height: 1;
    color: var(--text-secondary);
}
.log-close-btn:hover {
    color: #f87171;
    background: rgba(239, 68, 68, 0.15);
    border-color: rgba(239, 68, 68, 0.3);
}

.log-body {
    flex: 1 1 0;
    min-height: 0;
    overflow-y: auto;
    padding: 12px 14px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.74rem;
    line-height: 1.55;
    background: rgba(0, 0, 0, 0.35);
    color: #cbd5e1;
    scrollbar-width: thin;
    scrollbar-color: rgba(255, 255, 255, 0.2) rgba(15, 23, 42, 0.6);
}
.log-line {
    white-space: pre-wrap;
    word-break: break-word;
    margin-bottom: 3px;
}
.log-line .lt { color: #64748b; margin-right: 8px; }
.log-line.L-WARNING { color: #fbbf24; }
.log-line.L-ERROR { color: #f87171; }
.log-footer {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 10px 14px;
    font-size: 0.72rem;
    color: var(--text-secondary);
    border-top: 1px solid var(--border-color);
    background: rgba(30, 41, 59, 0.2);
}
.log-footer .dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: var(--success-color);
    box-shadow: 0 0 6px var(--success-color);
    flex-shrink: 0;
}
.log-footer.disconnected .dot { background: #f87171; box-shadow: none; }
@media (max-width: 980px) {
    .dashboard-layout { flex-direction: column; overflow-y: auto; }
    .cards-scroll-area { height: auto; overflow-y: visible; flex: none; mask-image: none; -webkit-mask-image: none; padding-top: 20px; }
    .log-panel { width: 100%; height: 380px; flex-shrink: 0; margin-top: 0; }
}

.info-tooltip-container {
    position: relative;
    display: inline-flex;
    align-items: center;
    cursor: pointer;
    color: #94a3b8;
    transition: color 0.2s ease;
}
.info-tooltip-container:hover {
    color: #60a5fa;
}
.info-tooltip {
    position: absolute;
    bottom: calc(100% + 8px);
    right: -10px;
    width: 270px;
    background: rgba(15, 23, 42, 0.95);
    border: 1px solid rgba(96, 165, 250, 0.3);
    border-radius: 8px;
    padding: 10px 14px;
    color: #e2e8f0;
    font-size: 12px;
    font-weight: 400;
    line-height: 1.45;
    box-shadow: 0 10px 25px rgba(0,0,0,0.5), 0 0 15px rgba(59, 130, 246, 0.15);
    opacity: 0;
    visibility: hidden;
    transform: translateY(6px);
    transition: opacity 0.25s ease, transform 0.25s ease, visibility 0.25s;
    z-index: 100;
    pointer-events: none;
    text-align: left;
    backdrop-filter: blur(10px);
    -webkit-backdrop-filter: blur(10px);
}
.info-tooltip-container:hover .info-tooltip {
    opacity: 1;
    visibility: visible;
    transform: translateY(0);
}
.info-tooltip::after {
    content: '';
    position: absolute;
    top: 100%;
    right: 14px;
    border-width: 6px;
    border-style: solid;
    border-color: rgba(96, 165, 250, 0.3) transparent transparent transparent;
}

.custom-checkbox-wrapper {
    display: flex;
    align-items: center;
    gap: 8px;
    cursor: pointer;
    font-size: 13px;
    color: var(--text-secondary);
    margin-top: 8px;
    user-select: none;
}
.custom-checkbox-wrapper input[type="checkbox"] {
    appearance: none;
    -webkit-appearance: none;
    width: 16px;
    height: 16px;
    border: 1.5px solid var(--border-color);
    border-radius: 4px;
    outline: none;
    background-color: rgba(15, 23, 42, 0.6);
    cursor: pointer;
    display: grid;
    place-content: center;
    margin: 0;
    transition: all 0.2s ease;
}
.custom-checkbox-wrapper input[type="checkbox"]::before {
    content: "";
    width: 10px;
    height: 10px;
    transform: scale(0);
    transition: transform 0.15s cubic-bezier(0.4, 0, 0.2, 1);
    background-color: var(--primary-color);
    mask-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='3' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='20 6 9 17 4 12'%3E%3C/polyline%3E%3C/svg%3E");
    -webkit-mask-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='3' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='20 6 9 17 4 12'%3E%3C/polyline%3E%3C/svg%3E");
    mask-size: contain;
    -webkit-mask-size: contain;
    mask-repeat: no-repeat;
    -webkit-mask-repeat: no-repeat;
    mask-position: center;
    -webkit-mask-position: center;
}
.custom-checkbox-wrapper input[type="checkbox"]:checked {
    border-color: var(--primary-color);
    background-color: rgba(59, 130, 246, 0.15);
    box-shadow: 0 0 8px var(--accent-glow);
}
.custom-checkbox-wrapper input[type="checkbox"]:checked::before {
    transform: scale(1);
}
.custom-checkbox-wrapper:hover input[type="checkbox"] {
    border-color: var(--primary-color);
}
.custom-checkbox-wrapper:hover {
    color: var(--text-color);
}
</style>
</head>
<body>
<div class="app-shell">
    <header class="app-top-bar">
        <div class="top-bar-inner">
            <div class="app-header">
                <div class="logo-area">
                    <span class="logo-icon">
                        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="color: var(--primary-color); display:block;">
                            <circle cx="12" cy="12" r="2"/>
                            <path d="M16.24 7.76a6 6 0 0 1 0 8.49m-8.48-.01a6 6 0 0 1 0-8.49m11.31-2.82a10 10 0 0 1 0 14.14m-14.14 0a10 10 0 0 1 0-14.14"/>
                        </svg>
                    </span>
                    <div>
                        <h1>Сервер подписок</h1>
                        <div class="subtitle">Карточки клиентов · <a href="__RAW_URL__">текстовый список</a></div>
                    </div>
                </div>
                <div class="header-actions">
                    __SEARCH__
                    <button type="button" class="btn-sm btn-logs" id="log-toggle">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>
                        <span>Логи</span>
                    </button>
                    __AUTH_ACTIONS__
                    <button type="button" class="btn-sm btn-logs" id="reset-statuses" title="Сбросить статусы синхронизации (очистит лог-файл)" aria-label="Сбросить статусы синхронизации">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"/></svg>
                        <span>Сбросить статусы</span>
                    </button>
                    <div class="status-badge" id="client-stats" title="Статистика клиентов по синхронизации. Нажмите на счётчик, чтобы отфильтровать карточки.">
                        <span class="stats-label" title="Показать всех клиентов (сбросить фильтр)">Клиентов: <span id="count-total">__COUNT_TOTAL__</span></span>
                        <span class="stats-divider"></span>
                        <span class="stat-item" data-filter="recent" title="Синхронизация в теч. последних 24ч · нажмите для фильтра"><span class="dot dot-recent"></span><span id="count-recent">__COUNT_RECENT__</span></span>
                        <span class="stat-item" data-filter="ever" title="Синхронизация была ранее (&gt;24ч) · нажмите для фильтра"><span class="dot dot-ever"></span><span id="count-ever">__COUNT_EVER__</span></span>
                        <span class="stat-item" data-filter="never" title="Синхронизации не было никогда · нажмите для фильтра"><span class="dot dot-never"></span><span id="count-never">__COUNT_NEVER__</span></span>
                    </div>
                </div>
            </div>
__MANAGEMENT__
        </div>
    </header>
    <div class="app-body">
        <div class="app-body-inner">
            <div class="dashboard-layout">
                <main class="cards-scroll-area">
    <div class="section-header" role="button" tabindex="0" data-section="management-nodes">
        <span class="chevron closed"><svg width="10" height="6" viewBox="0 0 10 6" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M1 1L5 5L9 1" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg></span>
        <span class="section-title-icon"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg></span>
        <span>Подписочные ссылки нод</span>
        <span class="line"></span>
    </div>
    <div class="cards-grid collapsed" data-section="management-nodes">
__NODES__
    </div>
__SECTIONS__
                </main>
                <aside class="log-panel hidden" id="log-panel">
                    <div class="log-panel-header">
                        <div class="log-panel-title">
                            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="color:var(--primary-color)"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>
                            <span>Логи сервера</span>
                        </div>
                        <div class="log-panel-actions">
                            <label class="log-autoscroll"><input type="checkbox" id="log-autoscroll" checked><span>авто-скролл</span></label>
                            <button type="button" class="btn-sm" id="log-clear" title="Очистить логи">
                                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6l-1 14H6L5 6m3 0V4h8v2"></path></svg>
                                <span>Очистить</span>
                            </button>
                            <button type="button" class="btn-sm log-close-btn" id="log-close" title="Скрыть логи" aria-label="Скрыть логи">
                                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
                            </button>
                        </div>
                    </div>
                    <div class="log-body" id="log-body"></div>
                    <div class="log-footer" id="log-status"><span class="dot"></span><span>подключение к логам…</span></div>
                </aside>
            </div>
        </div>
    </div>
</div>
<div id="editModal" class="edit-modal" hidden>
    <div class="edit-modal-backdrop"></div>
    <div class="edit-modal-card">
        <div class="edit-modal-title" id="editModalTitle">Редактирование</div>
        <div id="editModalBody"></div>
        <div class="edit-modal-actions">
            <button type="button" class="btn-sm" id="editModalCancel">Отмена</button>
            <button type="button" class="btn-sm btn-save" id="editModalSave">Сохранить</button>
        </div>
    </div>
</div>
<script>
// Lightweight client-side QR generator
var qrcode = (function() {
    function QR8bitByte(data) {
        this.mode = 4; this.data = data; this.parsedData = [];
        for (var i = 0, l = this.data.length; i < l; i++) {
            var byteArray = []; var code = this.data.charCodeAt(i);
            if (code > 0x10000) {
                byteArray[0] = 0xF0 | ((code & 0x1C0000) >>> 18); byteArray[1] = 0x80 | ((code & 0x3F000) >>> 12);
                byteArray[2] = 0x80 | ((code & 0xFC0) >>> 6); byteArray[3] = 0x80 | (code & 0x3F);
            } else if (code > 0x800) {
                byteArray[0] = 0xE0 | ((code & 0xF000) >>> 12); byteArray[1] = 0x80 | ((code & 0xFC0) >>> 6); byteArray[2] = 0x80 | (code & 0x3F);
            } else if (code > 0x80) {
                byteArray[0] = 0xC0 | ((code & 0x7C0) >>> 6); byteArray[1] = 0x80 | (code & 0x3F);
            } else { byteArray[0] = code; }
            this.parsedData.push(byteArray);
        }
        this.parsedData = Array.prototype.concat.apply([], this.parsedData);
        if (this.parsedData.length != this.data.length) { this.parsedData.unshift(191); this.parsedData.unshift(187); this.parsedData.unshift(239); }
    }
    QR8bitByte.prototype = {
        getLength: function() { return this.parsedData.length; },
        write: function(buffer) { for (var i = 0; i < this.parsedData.length; i++) buffer.put(this.parsedData[i], 8); }
    };
    var QRUtil = {
        PATTERN_POSITION_TABLE: [
            [], [6, 18], [6, 22], [6, 26], [6, 30], [6, 34], [6, 22, 38], [6, 24, 42], [6, 26, 46], [6, 28, 50],
            [6, 30, 54], [6, 32, 58], [6, 34, 62], [6, 26, 46, 66], [6, 26, 48, 70], [6, 26, 50, 74], [6, 30, 54, 78],
            [6, 30, 56, 82], [6, 30, 58, 86], [6, 34, 62, 90], [6, 28, 50, 72, 94], [6, 26, 50, 74, 98], [6, 30, 54, 78, 102],
            [6, 28, 54, 80, 106], [6, 32, 58, 84, 110], [6, 30, 58, 86, 114], [6, 34, 62, 90, 118], [6, 26, 50, 74, 98, 122],
            [6, 30, 54, 78, 102, 126], [6, 26, 52, 78, 104, 130], [6, 30, 56, 82, 108, 134], [6, 34, 60, 86, 112, 138],
            [6, 30, 58, 86, 114, 142], [6, 34, 62, 90, 118, 146], [6, 30, 54, 78, 102, 126, 150], [6, 24, 50, 76, 102, 128, 154],
            [6, 28, 54, 80, 106, 132, 158], [6, 32, 58, 84, 110, 136, 162], [6, 26, 54, 82, 110, 138, 166], [6, 30, 58, 86, 114, 142, 170]
        ],
        G15: (1 << 10) | (1 << 8) | (1 << 5) | (1 << 4) | (1 << 2) | (1 << 1) | (1 << 0),
        G18: (1 << 12) | (1 << 11) | (1 << 10) | (1 << 9) | (1 << 8) | (1 << 5) | (1 << 2) | (1 << 0),
        G15_MASK: (1 << 14) | (1 << 12) | (1 << 10) | (1 << 4) | (1 << 1),
        getBCHTypeInfo: function(d) {
            var data = d << 10;
            while (QRUtil.getBCHDigit(data) - QRUtil.getBCHDigit(QRUtil.G15) >= 0) data ^= (QRUtil.G15 << (QRUtil.getBCHDigit(data) - QRUtil.getBCHDigit(QRUtil.G15)));
            return ((d << 10) | data) ^ QRUtil.G15_MASK;
        },
        getBCHTypeNumber: function(d) {
            var data = d << 12;
            while (QRUtil.getBCHDigit(data) - QRUtil.getBCHDigit(QRUtil.G18) >= 0) data ^= (QRUtil.G18 << (QRUtil.getBCHDigit(data) - QRUtil.getBCHDigit(QRUtil.G18)));
            return (d << 12) | data;
        },
        getBCHDigit: function(data) { var digit = 0; while (data != 0) { digit++; data >>>= 1; } return digit; },
        getPatternPosition: function(t) { return QRUtil.PATTERN_POSITION_TABLE[t - 1]; },
        getMask: function(maskPattern, i, j) {
            switch (maskPattern) {
                case 0: return (i + j) % 2 == 0;
                case 1: return i % 2 == 0;
                case 2: return j % 3 == 0;
                case 3: return (i + j) % 3 == 0;
                case 4: return (Math.floor(i / 2) + Math.floor(j / 3)) % 2 == 0;
                case 5: return (i * j) % 2 + (i * j) % 3 == 0;
                case 6: return ((i * j) % 2 + (i * j) % 3) % 2 == 0;
                case 7: return ((i * j) % 3 + (i + j) % 2) % 2 == 0;
                default: throw new Error("bad maskPattern:" + maskPattern);
            }
        },
        getErrorCorrectPolynomial: function(len) {
            var a = new QRPolynomial([1], 0);
            for (var i = 0; i < len; i++) a = a.multiply(new QRPolynomial([1, QRMath.gexp(i)], 0));
            return a;
        },
        getLengthInBits: function(mode, type) {
            if (1 <= type && type < 10) return mode == 4 ? 8 : (mode == 1 ? 10 : 9);
            if (type < 27) return mode == 4 ? 16 : (mode == 1 ? 12 : 11);
            return mode == 4 ? 16 : (mode == 1 ? 14 : 13);
        },
        getLostPoint: function(qr) {
            var n = qr.getModuleCount(), lost = 0;
            for (var r = 0; r < n; r++) {
                for (var c = 0; c < n; c++) {
                    var same = 0, dark = qr.isDark(r, c);
                    for (var dr = -1; dr <= 1; dr++) {
                        if (r + dr < 0 || n <= r + dr) continue;
                        for (var dc = -1; dc <= 1; dc++) {
                            if (c + dc < 0 || n <= c + dc) continue;
                            if (dr == 0 && dc == 0) continue;
                            if (dark == qr.isDark(r + dr, c + dc)) same++;
                        }
                    }
                    if (same > 5) lost += (3 + same - 5);
                }
            }
            for (var r = 0; r < n - 1; r++) {
                for (var c = 0; c < n - 1; c++) {
                    var cnt = 0;
                    if (qr.isDark(r, c)) cnt++; if (qr.isDark(r + 1, c)) cnt++;
                    if (qr.isDark(r, c + 1)) cnt++; if (qr.isDark(r + 1, c + 1)) cnt++;
                    if (cnt == 0 || cnt == 4) lost += 3;
                }
            }
            for (var r = 0; r < n; r++) {
                for (var c = 0; c < n - 6; c++) {
                    if (qr.isDark(r, c) && !qr.isDark(r, c + 1) && qr.isDark(r, c + 2) && qr.isDark(r, c + 3) && qr.isDark(r, c + 4) && !qr.isDark(r, c + 5) && qr.isDark(r, c + 6)) lost += 40;
                }
            }
            for (var c = 0; c < n; c++) {
                for (var r = 0; r < n - 6; r++) {
                    if (qr.isDark(r, c) && !qr.isDark(r + 1, c) && qr.isDark(r + 2, c) && qr.isDark(r + 3, c) && qr.isDark(r + 4, c) && !qr.isDark(r + 5, c) && qr.isDark(r + 6, c)) lost += 40;
                }
            }
            var darkCount = 0;
            for (var c = 0; c < n; c++) for (var r = 0; r < n; r++) if (qr.isDark(r, c)) darkCount++;
            return lost + Math.abs(100 * darkCount / n / n - 50) / 5 * 10;
        }
    };
    var QRMath = {
        glog: function(n) { if (n < 1) throw new Error("glog(" + n + ")"); return QRMath.LOG_TABLE[n]; },
        gexp: function(n) { while (n < 0) n += 255; while (n >= 256) n -= 255; return QRMath.EXP_TABLE[n]; },
        EXP_TABLE: new Array(256), LOG_TABLE: new Array(256)
    };
    for (var i = 0; i < 8; i++) QRMath.EXP_TABLE[i] = 1 << i;
    for (var i = 8; i < 256; i++) QRMath.EXP_TABLE[i] = QRMath.EXP_TABLE[i - 4] ^ QRMath.EXP_TABLE[i - 5] ^ QRMath.EXP_TABLE[i - 6] ^ QRMath.EXP_TABLE[i - 8];
    for (var i = 0; i < 255; i++) QRMath.LOG_TABLE[QRMath.EXP_TABLE[i]] = i;

    function QRPolynomial(num, shift) {
        var offset = 0; while (offset < num.length && num[offset] == 0) offset++;
        this.num = new Array(num.length - offset + shift);
        for (var i = 0; i < num.length - offset; i++) this.num[i] = num[i + offset];
    }
    QRPolynomial.prototype = {
        get: function(index) { return this.num[index]; },
        getLength: function() { return this.num.length; },
        multiply: function(e) {
            var num = new Array(this.getLength() + e.getLength() - 1);
            for (var i = 0; i < this.getLength(); i++) for (var j = 0; j < e.getLength(); j++) num[i + j] ^= QRMath.gexp(QRMath.glog(this.get(i)) + QRMath.glog(e.get(j)));
            return new QRPolynomial(num, 0);
        },
        mod: function(e) {
            if (this.getLength() - e.getLength() < 0) return this;
            var ratio = QRMath.glog(this.get(0)) - QRMath.glog(e.get(0));
            var num = new Array(this.getLength());
            for (var i = 0; i < this.getLength(); i++) num[i] = this.get(i);
            for (var i = 0; i < e.getLength(); i++) num[i] ^= QRMath.gexp(QRMath.glog(e.get(i)) + ratio);
            return new QRPolynomial(num, 0).mod(e);
        }
    };
    var QRRSBlock = {
        RS_BLOCK_TABLE: [
            [1, 26, 19], [1, 26, 16], [1, 26, 13], [1, 26, 9], [1, 44, 34], [1, 44, 28], [1, 44, 22], [1, 44, 16],
            [1, 70, 55], [1, 70, 44], [2, 35, 17], [2, 35, 13], [1, 100, 80], [2, 50, 32], [2, 50, 24], [4, 25, 9],
            [1, 134, 108], [2, 67, 43], [2, 33, 15, 2, 34, 16], [2, 33, 11, 2, 34, 12], [2, 86, 68], [4, 43, 27], [4, 43, 19], [4, 43, 15],
            [2, 98, 78], [4, 49, 31], [2, 32, 14, 4, 33, 15], [4, 39, 13, 1, 40, 14], [2, 121, 97], [2, 60, 38, 2, 61, 39], [4, 40, 18, 2, 41, 19], [4, 40, 14, 2, 41, 15],
            [2, 146, 116], [3, 58, 36, 2, 59, 37], [4, 36, 16, 4, 37, 17], [4, 36, 12, 4, 37, 13], [2, 86, 68, 2, 87, 69], [4, 69, 43, 1, 70, 44], [6, 43, 19, 2, 44, 20], [6, 43, 15, 2, 44, 16],
            [4, 101, 81], [1, 80, 50, 4, 81, 51], [4, 50, 22, 4, 51, 23], [3, 36, 12, 8, 37, 13], [2, 116, 92, 2, 117, 93], [6, 58, 36, 2, 59, 37], [4, 46, 20, 6, 47, 21], [7, 42, 14, 4, 43, 15],
            [4, 133, 107], [8, 59, 37, 1, 60, 38], [8, 44, 20, 4, 45, 21], [12, 33, 11, 4, 34, 12], [3, 145, 115, 1, 146, 116], [4, 64, 40, 5, 65, 41], [11, 36, 16, 5, 37, 17], [11, 36, 12, 5, 37, 13],
            [5, 109, 87, 1, 110, 88], [5, 65, 41, 5, 66, 42], [5, 54, 24, 7, 55, 25], [11, 36, 12, 7, 37, 13], [5, 122, 98, 1, 123, 99], [7, 73, 45, 3, 74, 46], [15, 43, 19, 2, 44, 20], [3, 45, 15, 13, 46, 16],
            [1, 135, 107, 5, 136, 108], [10, 74, 46, 1, 75, 47], [1, 50, 22, 15, 51, 23], [2, 42, 14, 17, 43, 15], [5, 150, 120, 1, 151, 121], [9, 69, 43, 4, 70, 44], [17, 50, 22, 1, 51, 23], [2, 42, 14, 19, 43, 15],
            [3, 141, 113, 4, 142, 114], [3, 70, 44, 11, 71, 45], [17, 47, 21, 4, 48, 22], [9, 39, 13, 16, 40, 14], [3, 135, 107, 5, 136, 108], [3, 67, 41, 13, 68, 42], [15, 54, 24, 5, 55, 25], [15, 43, 15, 10, 44, 16]
        ],
        getRSBlocks: function(typeNumber, errorCorrectLevel) {
            var rsBlock = QRRSBlock.RS_BLOCK_TABLE[(typeNumber - 1) * 4 + errorCorrectLevel];
            var length = rsBlock.length / 3, list = [];
            for (var i = 0; i < length; i++) list.push({ totalCount: rsBlock[i * 3 + 1], dataCount: rsBlock[i * 3 + 2] });
            return list;
        }
    };
    function QRBitBuffer() { this.buffer = []; this.length = 0; }
    QRBitBuffer.prototype = {
        get: function(index) { return ((this.buffer[Math.floor(index / 8)] >>> (7 - index % 8)) & 1) == 1; },
        put: function(num, length) { for (var i = 0; i < length; i++) this.putBit(((num >>> (length - i - 1)) & 1) == 1); },
        putBit: function(bit) {
            var bufIndex = Math.floor(this.length / 8);
            if (this.buffer.length <= bufIndex) this.buffer.push(0);
            if (bit) this.buffer[bufIndex] |= (0x80 >>> (this.length % 8));
            this.length++;
        }
    };
    function QRCode(typeNumber, errorCorrectLevel) {
        this.typeNumber = typeNumber || 0; this.errorCorrectLevel = errorCorrectLevel !== undefined ? errorCorrectLevel : 0;
        this.modules = null; this.moduleCount = 0; this.dataCache = null; this.dataList = [];
    }
    QRCode.prototype = {
        addData: function(data) { this.dataList.push(new QR8bitByte(data)); this.dataCache = null; },
        isDark: function(r, c) { return this.modules[r][c]; },
        getModuleCount: function() { return this.moduleCount; },
        make: function() {
            if (this.typeNumber < 1) {
                for (var t = 1; t < 40; t++) {
                    var rsBlocks = QRRSBlock.getRSBlocks(t, this.errorCorrectLevel), total = 0, len = 0;
                    for (var i = 0; i < rsBlocks.length; i++) total += rsBlocks[i].dataCount;
                    for (var i = 0; i < this.dataList.length; i++) { len += QRUtil.getLengthInBits(this.dataList[i].mode, t) + this.dataList[i].getLength() * 8; }
                    if (len <= total * 8) { this.typeNumber = t; break; }
                }
            }
            this.makeImpl(false, this.getBestMaskPattern());
        },
        makeImpl: function(test, maskPattern) {
            this.moduleCount = this.typeNumber * 4 + 17; this.modules = new Array(this.moduleCount);
            for (var r = 0; r < this.moduleCount; r++) { this.modules[r] = new Array(this.moduleCount); for (var c = 0; c < this.moduleCount; c++) this.modules[r][c] = null; }
            this.setupPositionProbePattern(0, 0); this.setupPositionProbePattern(this.moduleCount - 7, 0); this.setupPositionProbePattern(0, this.moduleCount - 7);
            this.setupPositionAdjustPattern(); this.setupTimingPattern(); this.setupTypeInfo(test, maskPattern);
            if (this.typeNumber >= 7) this.setupTypeNumber(test);
            if (this.dataCache == null) this.dataCache = QRCode.createData(this.typeNumber, this.errorCorrectLevel, this.dataList);
            this.mapData(this.dataCache, maskPattern);
        },
        setupPositionProbePattern: function(row, col) {
            for (var r = -1; r <= 7; r++) {
                if (row + r <= -1 || this.moduleCount <= row + r) continue;
                for (var c = -1; c <= 7; c++) {
                    if (col + c <= -1 || this.moduleCount <= col + c) continue;
                    if ((0 <= r && r <= 6 && (c == 0 || c == 6)) || (0 <= c && c <= 6 && (r == 0 || r == 6)) || (2 <= r && r <= 4 && 2 <= c && c <= 4)) this.modules[row + r][col + c] = true;
                    else this.modules[row + r][col + c] = false;
                }
            }
        },
        getBestMaskPattern: function() {
            var minLost = 0, pattern = 0;
            for (var i = 0; i < 8; i++) {
                this.makeImpl(true, i);
                var lost = QRUtil.getLostPoint(this);
                if (i == 0 || minLost > lost) { minLost = lost; pattern = i; }
            }
            return pattern;
        },
        setupTimingPattern: function() {
            for (var r = 8; r < this.moduleCount - 8; r++) if (this.modules[r][6] === null) this.modules[r][6] = (r % 2 == 0);
            for (var c = 8; c < this.moduleCount - 8; c++) if (this.modules[6][c] === null) this.modules[6][c] = (c % 2 == 0);
        },
        setupPositionAdjustPattern: function() {
            var pos = QRUtil.getPatternPosition(this.typeNumber);
            for (var i = 0; i < pos.length; i++) {
                for (var j = 0; j < pos.length; j++) {
                    var row = pos[i], col = pos[j];
                    if (this.modules[row][col] !== null) continue;
                    for (var r = -2; r <= 2; r++) {
                        for (var c = -2; c <= 2; c++) {
                            if (r == -2 || r == 2 || c == -2 || c == 2 || (r == 0 && c == 0)) this.modules[row + r][col + c] = true;
                            else this.modules[row + r][col + c] = false;
                        }
                    }
                }
            }
        },
        setupTypeNumber: function(test) {
            var bits = QRUtil.getBCHTypeNumber(this.typeNumber);
            for (var i = 0; i < 18; i++) {
                var mod = (!test && ((bits >> i) & 1) == 1);
                this.modules[Math.floor(i / 3)][i % 3 + this.moduleCount - 8 - 3] = mod;
                this.modules[i % 3 + this.moduleCount - 8 - 3][Math.floor(i / 3)] = mod;
            }
        },
        setupTypeInfo: function(test, maskPattern) {
            var data = (this.errorCorrectLevel << 3) | maskPattern, bits = QRUtil.getBCHTypeInfo(data);
            for (var i = 0; i < 15; i++) {
                var mod = (!test && ((bits >> i) & 1) == 1);
                if (i < 6) this.modules[i][8] = mod; else if (i < 8) this.modules[i + 1][8] = mod; else this.modules[this.moduleCount - 15 + i][8] = mod;
                if (i < 8) this.modules[8][this.moduleCount - i - 1] = mod; else if (i < 9) this.modules[8][15 - i - 1 + 1] = mod; else this.modules[8][15 - i - 1] = mod;
            }
            this.modules[this.moduleCount - 8][8] = (!test);
        },
        mapData: function(data, maskPattern) {
            var inc = -1, row = this.moduleCount - 1, bitIndex = 7, byteIndex = 0;
            for (var col = this.moduleCount - 1; col > 0; col -= 2) {
                if (col == 6) col--;
                while (true) {
                    for (var c = 0; c < 2; c++) {
                        if (this.modules[row][col - c] === null) {
                            var dark = false;
                            if (byteIndex < data.length) dark = (((data[byteIndex] >>> bitIndex) & 1) == 1);
                            if (QRUtil.getMask(maskPattern, row, col - c)) dark = !dark;
                            this.modules[row][col - c] = dark;
                            bitIndex--; if (bitIndex == -1) { byteIndex++; bitIndex = 7; }
                        }
                    }
                    row += inc; if (row < 0 || this.moduleCount <= row) { row -= inc; inc = -inc; break; }
                }
            }
        },
        createSvgDataUrl: function(cellSize, margin) {
            cellSize = cellSize || 4; margin = margin !== undefined ? margin : 4;
            var size = this.getModuleCount() * cellSize + margin * 2;
            var svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ' + size + ' ' + size + '" width="' + size + '" height="' + size + '">';
            svg += '<rect width="100%" height="100%" fill="#ffffff"/><path d="';
            for (var r = 0; r < this.getModuleCount(); r++) {
                for (var c = 0; c < this.getModuleCount(); c++) {
                    if (this.isDark(r, c)) {
                        svg += 'M' + (margin + c * cellSize) + ',' + (margin + r * cellSize) + 'h' + cellSize + 'v' + cellSize + 'h-' + cellSize + 'z ';
                    }
                }
            }
            svg += '" fill="#000000"/></svg>';
            return 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg);
        }
    };
    QRCode.createData = function(typeNumber, errorCorrectLevel, dataList) {
        var rsBlocks = QRRSBlock.getRSBlocks(typeNumber, errorCorrectLevel), buffer = new QRBitBuffer();
        for (var i = 0; i < dataList.length; i++) {
            buffer.put(dataList[i].mode, 4);
            buffer.put(dataList[i].getLength(), QRUtil.getLengthInBits(dataList[i].mode, typeNumber));
            dataList[i].write(buffer);
        }
        var total = 0; for (var i = 0; i < rsBlocks.length; i++) total += rsBlocks[i].dataCount;
        if (buffer.length + 4 <= total * 8) buffer.put(0, 4);
        while (buffer.length % 8 != 0) buffer.putBit(false);
        while (true) { if (buffer.length >= total * 8) break; buffer.put(0xEC, 8); if (buffer.length >= total * 8) break; buffer.put(0x11, 8); }
        var offset = 0, maxDc = 0, maxEc = 0, dcdata = new Array(rsBlocks.length), ecdata = new Array(rsBlocks.length);
        for (var r = 0; r < rsBlocks.length; r++) {
            var dc = rsBlocks[r].dataCount, ec = rsBlocks[r].totalCount - dc;
            maxDc = Math.max(maxDc, dc); maxEc = Math.max(maxEc, ec); dcdata[r] = new Array(dc);
            for (var i = 0; i < dc; i++) dcdata[r][i] = 0xff & buffer.buffer[i + offset];
            offset += dc;
            var modPoly = new QRPolynomial(dcdata[r], QRUtil.getErrorCorrectPolynomial(ec).getLength() - 1).mod(QRUtil.getErrorCorrectPolynomial(ec));
            ecdata[r] = new Array(QRUtil.getErrorCorrectPolynomial(ec).getLength() - 1);
            for (var i = 0; i < ecdata[r].length; i++) { var modIndex = i + modPoly.getLength() - ecdata[r].length; ecdata[r][i] = (modIndex >= 0) ? modPoly.get(modIndex) : 0; }
        }
        var totalCode = 0; for (var i = 0; i < rsBlocks.length; i++) totalCode += rsBlocks[i].totalCount;
        var data = new Array(totalCode), idx = 0;
        for (var i = 0; i < maxDc; i++) for (var r = 0; r < rsBlocks.length; r++) if (i < dcdata[r].length) data[idx++] = dcdata[r][i];
        for (var i = 0; i < maxEc; i++) for (var r = 0; r < rsBlocks.length; r++) if (i < ecdata[r].length) data[idx++] = ecdata[r][i];
        return data;
    };
    return {
        generateSvgDataUrl: function(text, cellSize, margin) {
            var qr = new QRCode(0, 0);
            qr.addData(text);
            qr.make();
            return qr.createSvgDataUrl(cellSize || 5, margin !== undefined ? margin : 3);
        }
    };
})();

const NODES_DATA = __NODES_JSON__;
const logPanel = document.getElementById('log-panel');
const logBody = document.getElementById('log-body');
const logStatus = document.getElementById('log-status');
const logAutoScroll = document.getElementById('log-autoscroll');
const logToggleBtn = document.getElementById('log-toggle');
let logSource = null;

const CLIENT_ACTIVITIES = {};
document.querySelectorAll('.client-status[data-client]').forEach(el => {
    const client = el.getAttribute('data-client');
    const timeStr = el.getAttribute('data-time') || '';
    const ts = Number(el.getAttribute('data-timestamp')) || 0;
    if (timeStr) {
        CLIENT_ACTIVITIES[client] = { client: client, time: timeStr, timestamp: ts };
    }
});

function getSyncState(a) {
    if (!a || !a.time) return 'never';
    let ts = a.timestamp ? (a.timestamp > 1e11 ? a.timestamp : a.timestamp * 1000) : Date.parse(a.time.replace(' ', 'T'));
    if (isNaN(ts) || !ts) return 'ever';
    const now = Date.now();
    if (now - ts <= 24 * 60 * 60 * 1000 && now - ts >= -60 * 1000) {
        return 'recent';
    }
    return 'ever';
}

function updateTopStats() {
    let recent = 0, ever = 0, never = 0;
    const cards = document.querySelectorAll('.client-status[data-client]');
    cards.forEach(el => {
        const client = el.getAttribute('data-client');
        const act = CLIENT_ACTIVITIES[client];
        const state = getSyncState(act);
        if (state === 'recent') recent++;
        else if (state === 'ever') ever++;
        else never++;
    });
    const rEl = document.getElementById('count-recent');
    const eEl = document.getElementById('count-ever');
    const nEl = document.getElementById('count-never');
    const tEl = document.getElementById('count-total');
    if (rEl) rEl.textContent = recent;
    if (eEl) eEl.textContent = ever;
    if (nEl) nEl.textContent = never;
    if (tEl) tEl.textContent = (recent + ever + never);
}

function refreshAllCardStates() {
    document.querySelectorAll('.client-status[data-client]').forEach(el => {
        const client = el.getAttribute('data-client');
        const act = CLIENT_ACTIVITIES[client];
        const state = getSyncState(act);
        const dot = el.querySelector('.status-dot');
        if (dot && !dot.classList.contains('st-err')) {
            dot.className = 'status-dot st-' + state;
        }
    });
    updateTopStats();
    filterCards();
}
setInterval(refreshAllCardStates, 60000);

let syncFilter = null;
function cardSyncState(card) {
    const st = card.querySelector('.client-status[data-client]');
    if (!st) return null;
    return getSyncState(CLIENT_ACTIVITIES[st.getAttribute('data-client')]);
}
function setSyncFilter(value) {
    syncFilter = value || null;
    document.querySelectorAll('.status-badge .stat-item').forEach(item => {
        item.classList.toggle('filtering', item.getAttribute('data-filter') === syncFilter);
    });
    filterCards();
}
document.querySelectorAll('.status-badge .stat-item').forEach(item => {
    item.addEventListener('click', () => {
        const f = item.getAttribute('data-filter');
        setSyncFilter(syncFilter === f ? null : f);
    });
});
document.querySelector('.status-badge .stats-label')?.addEventListener('click', () => setSyncFilter(null));
document.getElementById('reset-statuses')?.addEventListener('click', function () {
    if (!confirm('Сбросить статусы синхронизации для всех клиентов? Лог-файл будет очищен, статусы станут «Синхронизации не было».')) return;
    const btn = this;
    const originalHtml = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<span>…</span>';
    fetch('__API_RESET__', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({}) })
        .then(r => r.json())
        .then(d => { location.reload(); })
        .catch(() => {
            btn.disabled = false;
            btn.innerHTML = originalHtml;
            alert('Не удалось сбросить статусы.');
        });
});

function updateLogToggleVisibility() {
    if (!logToggleBtn || !logPanel) return;
    const isHidden = logPanel.classList.contains('hidden');
    logToggleBtn.style.display = isHidden ? 'inline-flex' : 'none';
}

function updateCardActivity(a) {
    if (!a || !a.client) return;
    CLIENT_ACTIVITIES[a.client] = a;
    const el = document.querySelector('.client-status[data-client="' + CSS.escape(a.client) + '"]');
    if (el) {
        el.setAttribute('data-time', a.time || '');
        if (a.timestamp) el.setAttribute('data-timestamp', a.timestamp);
        const dot = el.querySelector('.status-dot');
        const status = Number(a.status);
        const isOk = status >= 200 && status < 300;
        const state = getSyncState(a);
        dot.className = 'status-dot ' + (isOk ? ('st-' + state) : 'st-err');
        let src = '';
        if (a.node_name) src = 'через «' + a.node_name + '»';
        else if (a.source === 'force') src = 'через кастом';
        let bytes = '';
        if (a.bytes) bytes = a.bytes >= 1024 ? (a.bytes / 1024).toFixed(1) + ' КБ' : a.bytes + ' B';
        const text = 'Последняя синхронизация: ' + (a.time || '—') + (status ? ' · HTTP ' + status : '')
            + (bytes ? ' · ' + bytes : '') + (src ? ' · ' + src : '');
        const st = el.querySelector('.status-text');
        if (st) {
            st.textContent = text;
            st.setAttribute('title', text);
        }
    }
    updateTopStats();
    filterCards();
}
function connectLogs() {
    if (logSource) return;
    logSource = new EventSource('__LOGS_URL__');
    logSource.onopen = () => {
        logStatus.classList.remove('disconnected');
        logStatus.innerHTML = '<span class="dot"></span><span>онлайн · docker logs -f subs-server</span>';
    };
    logSource.onerror = () => {
        logStatus.classList.add('disconnected');
        logStatus.innerHTML = '<span class="dot"></span><span>соединение потеряно, переподключение…</span>';
    };
    logSource.onmessage = (e) => {
        let data;
        try { data = JSON.parse(e.data); } catch (err) { return; }
        const line = document.createElement('div');
        line.className = 'log-line L-' + (data.level || 'INFO');
        const ts = document.createElement('span');
        ts.className = 'lt';
        ts.textContent = data.time || '';
        line.appendChild(ts);
        line.appendChild(document.createTextNode(data.message || ''));
        logBody.appendChild(line);
        while (logBody.childElementCount > 1000) logBody.removeChild(logBody.firstChild);
        if (logAutoScroll.checked) logBody.scrollTop = logBody.scrollHeight;
    };
    logSource.addEventListener('activity', (e) => {
        let a;
        try { a = JSON.parse(e.data); } catch (err) { return; }
        updateCardActivity(a);
    });
}
logToggleBtn?.addEventListener('click', () => {
    logPanel.classList.toggle('hidden');
    try {
        localStorage.setItem('subs_logs_hidden', logPanel.classList.contains('hidden') ? '1' : '0');
    } catch (e) {}
    updateLogToggleVisibility();
});
document.getElementById('log-close')?.addEventListener('click', () => {
    logPanel.classList.add('hidden');
    try {
        localStorage.setItem('subs_logs_hidden', '1');
    } catch (e) {}
    updateLogToggleVisibility();
});
document.getElementById('log-clear')?.addEventListener('click', () => { logBody.innerHTML = ''; });
try {
    if (localStorage.getItem('subs_logs_hidden') === '0') {
        logPanel?.classList.remove('hidden');
    }
} catch (e) {}
updateLogToggleVisibility();
connectLogs();

function copyText(text, btn) {
    const originalHtml = btn.innerHTML;
    const done = () => {
        btn.innerHTML = '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg><span>Скопировано</span>';
        btn.classList.add('active');
        setTimeout(() => { btn.innerHTML = originalHtml; btn.classList.remove('active'); }, 1200);
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(done).catch(() => fallbackCopy(text, done));
    } else {
        fallbackCopy(text, done);
    }
}
function fallbackCopy(text, done) {
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand('copy'); done(); } catch (e) {}
    document.body.removeChild(ta);
}
function submitOverride(client, value, btn) {
    const originalHtml = btn.innerHTML;
    btn.textContent = '…';
    btn.disabled = true;
    fetch('__API_OVERRIDE__', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ client: client, value: value })
    })
        .then(r => r.json())
        .then(d => {
            if (d.ok) { location.reload(); return; }
            btn.textContent = d.error || 'Ошибка';
            btn.disabled = false;
            setTimeout(() => { btn.innerHTML = originalHtml; btn.disabled = false; }, 2500);
        })
        .catch(() => {
            btn.textContent = 'Ошибка сети';
            btn.disabled = false;
            setTimeout(() => { btn.innerHTML = originalHtml; btn.disabled = false; }, 2500);
        });
}
function submitManagement(url, payload) {
    return fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })
        .then(r => r.json()).then(d => { if (!d.ok) throw new Error(d.error || 'Ошибка'); return d; });
}
function showManagementError(error) {
    const box = document.getElementById('management-message');
    if (box) {
        box.hidden = false;
        box.textContent = error.message || String(error);
        clearTimeout(window.managementErrorTimer);
        window.managementErrorTimer = setTimeout(() => { box.hidden = true; }, 6000);
    }
}
function escAttr(s) {
    return String(s).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
const editModal = document.getElementById('editModal');
let editModalState = null;
function openEditModal(title, body, state) {
    document.getElementById('editModalTitle').textContent = title;
    document.getElementById('editModalBody').innerHTML = body;
    editModalState = state;
    editModal.hidden = false;
}
function closeEditModal() {
    editModal.hidden = true;
    editModalState = null;
}
document.getElementById('editModalCancel')?.addEventListener('click', closeEditModal);
document.querySelector('.edit-modal-backdrop')?.addEventListener('click', closeEditModal);
document.getElementById('editModalSave')?.addEventListener('click', function () {
    if (!editModalState) return;
    const btn = this;
    const originalHtml = btn.innerHTML;
    btn.textContent = '…';
    btn.disabled = true;
    Promise.resolve(editModalState.save())
        .then(() => location.reload())
        .catch(err => {
            btn.textContent = err.message || 'Ошибка';
            btn.disabled = false;
            setTimeout(() => { btn.innerHTML = originalHtml; btn.disabled = false; }, 2500);
        });
});
function filterCards() {
    const query = (document.getElementById('client-search')?.value || '').trim().toLocaleLowerCase();
    document.querySelectorAll('.card').forEach(card => {
        const text = (card.dataset.search || '').toLocaleLowerCase();
        const state = cardSyncState(card);
        const matchesQuery = !query || text.includes(query);
        const matchesSync = !syncFilter || state === null || state === syncFilter;
        card.style.display = (matchesQuery && matchesSync) ? '' : 'none';
    });
    document.querySelectorAll('.section-header').forEach(header => {
        const grid = header.nextElementSibling;
        if (!grid || !grid.classList.contains('cards-grid')) return;
        const visible = [...grid.querySelectorAll('.card')].some(card => card.style.display !== 'none');
        header.style.display = visible ? '' : 'none';
    });
}
document.addEventListener('click', function (e) {
    const header = e.target.closest('.section-header');
    if (header) {
        const grid = header.nextElementSibling;
        if (grid && grid.classList.contains('cards-grid')) {
            const closed = grid.classList.toggle('collapsed');
            const chevron = header.querySelector('.chevron');
            if (chevron) chevron.classList.toggle('closed', closed);
        }
        return;
    }
    const save = e.target.closest('.btn-override-save');
    if (save) {
        const client = save.getAttribute('data-client');
        const input = save.closest('.override-editor').querySelector('.override-input');
        submitOverride(client, input.value.trim(), save);
        return;
    }
    const clear = e.target.closest('.btn-override-clear');
    if (clear) {
        submitOverride(clear.getAttribute('data-client'), '', clear);
        return;
    }
    const setBtn = e.target.closest('.btn-override');
    if (setBtn) {
        const card = setBtn.closest('.card');
        const editor = card.querySelector('.override-editor');
        const input = editor.querySelector('.override-input');
        const cur = card.querySelector('.override-text').getAttribute('data-custom');
        input.value = cur === '__none__' ? '' : cur;
        editor.classList.toggle('open');
        if (editor.classList.contains('open')) input.focus();
        return;
    }
    const cancel = e.target.closest('.btn-override-cancel');
    if (cancel) {
        cancel.closest('.override-editor').classList.remove('open');
        return;
    }
    const deleteClient = e.target.closest('.btn-client-delete');
    if (deleteClient) {
        if (!confirm('Удалить клиента и его кастомную подписку?')) return;
        submitManagement('__API_CLIENT__', { action: 'delete', client: deleteClient.dataset.client })
            .then(() => location.reload()).catch(showManagementError);
        return;
    }
    const editNode = e.target.closest('.btn-node-edit');
    if (editNode) {
        const node = (NODES_DATA || []).find(n => n.id === editNode.dataset.node);
        if (!node) return;
        const body = ''
            + '<div class="edit-modal-field"><label>Имя ноды</label><input id="edit-node-name" value="' + escAttr(node.name) + '"></div>'
            + '<div class="edit-modal-field"><label>URL подписки</label><input id="edit-node-url" value="' + escAttr(node.url || '') + '"></div>'
            + '<div class="edit-modal-hint">Схему (http:// или https://) можно не указывать — https:// добавится автоматически.</div>'
            + '<label class="custom-checkbox-wrapper" style="margin-top:16px;">'
            + '<input type="checkbox" id="edit-node-json" ' + (node.supports_json !== false ? 'checked' : '') + '>'
            + '<span>Поддерживает JSON подписки</span>'
            + '</label>';
        openEditModal('Редактировать ноду · ' + node.name, body, {
            save: () => submitManagement('__API_NODE__', {
                action: 'edit',
                node: node.id,
                name: document.getElementById('edit-node-name').value.trim(),
                url: document.getElementById('edit-node-url').value.trim(),
                supports_json: document.getElementById('edit-node-json').checked
            })
        });
        return;
    }
    const editClient = e.target.closest('.btn-client-edit');
    if (editClient) {
        const client = editClient.dataset.client;
        const curNode = (NODES_DATA || []).find(n => (n.clients || []).includes(client));
        const opts = (NODES_DATA || []).map(n =>
            '<div class="node-select-option' + (curNode && n.id === curNode.id ? ' selected' : '') + '" data-value="' + escAttr(n.id) + '">' + escAttr(n.name) + '</div>'
        ).join('');
        const forceOpt = curNode ? '' : '<div class="node-select-option selected" data-value="">Кастом (force-subs)</div>';
        const curName = curNode ? curNode.name : 'Кастом (force-subs)';
        const curVal = curNode ? curNode.id : '';
        const nodePicker = '<div class="node-select" id="edit-node-select">'
            + '<input type="hidden" id="edit-client-node" value="' + escAttr(curVal) + '">'
            + '<button type="button" class="node-select-trigger"><span>' + escAttr(curName) + '</span>'
            + '<span class="node-select-arrow"><svg width="10" height="6" viewBox="0 0 10 6" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M1 1L5 5L9 1" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg></span></button>'
            + '<div class="node-select-options">' + opts + forceOpt + '</div></div>';
        const body = ''
            + '<div class="edit-modal-field"><label>Имя клиента</label><input id="edit-client-name" value="' + escAttr(client) + '"></div>'
            + '<div class="edit-modal-field"><label>Нода</label>' + nodePicker + '</div>';
        openEditModal('Редактировать клиента · ' + client, body, {
            save: () => submitManagement('__API_CLIENT__', {
                action: 'edit',
                client: client,
                new_name: document.getElementById('edit-client-name').value.trim(),
                node: document.getElementById('edit-client-node').value
            })
        });
        return;
    }
    const deleteNode = e.target.closest('.btn-node-delete');
    if (deleteNode) {
        if (!confirm('Удалить ноду? Сначала должны быть удалены все её клиенты.')) return;
        submitManagement('__API_NODE__', { action: 'delete', node: deleteNode.dataset.node })
            .then(() => location.reload()).catch(showManagementError);
        return;
    }
    const copy = e.target.closest('.btn-copy');
    if (copy) { copyText(copy.getAttribute('data-url'), copy); return; }
    const qr = e.target.closest('.btn-qr');
    if (qr) {
        const sel = qr.getAttribute('data-target');
        const el = document.querySelector(sel);
        if (!el) return;
        const open = el.classList.toggle('open');
        if (open) {
            el.querySelectorAll('.qr-item[data-qr-val]').forEach(item => {
                const img = item.querySelector('img');
                if (img && (!img.src || img.src === window.location.href) && item.dataset.qrVal) {
                    try {
                        img.src = qrcode.generateSvgDataUrl(item.dataset.qrVal, 5, 3);
                    } catch (err) {
                        console.error('QR generation error:', err);
                    }
                }
            });
        }
        document.querySelectorAll('.btn-qr[data-target="' + sel + '"]').forEach(b => {
            b.classList.toggle('active', open);
        });
        return;
    }
});
document.getElementById('client-search')?.addEventListener('input', filterCards);
document.addEventListener('click', function (e) {
    const addBtn = e.target.closest('.btn-json-node-add');
    if (addBtn) {
        const client = addBtn.getAttribute('data-client');
        const selectId = addBtn.getAttribute('data-select');
        const nodeId = document.getElementById(selectId).value;
        if (!nodeId) return;
        submitManagement('__API_CLIENT__', { action: 'add_json_node', client: client, node: nodeId })
            .then(() => location.reload()).catch(showManagementError);
    }
    const delBtn = e.target.closest('.btn-json-node-delete');
    if (delBtn) {
        const client = delBtn.getAttribute('data-client');
        const nodeId = delBtn.getAttribute('data-node');
        if (!confirm('Удалить эту ноду из дополнительных для JSON?')) return;
        submitManagement('__API_CLIENT__', { action: 'remove_json_node', client: client, node: nodeId })
            .then(() => location.reload()).catch(showManagementError);
    }
});
document.addEventListener('click', function (e) {
    const trigger = e.target.closest('.node-select-trigger');
    if (trigger) {
        const select = trigger.closest('.node-select');
        document.querySelectorAll('.node-select.open').forEach(s => {
            if (s !== select) s.classList.remove('open');
        });
        if (select) select.classList.toggle('open');
        return;
    }
    const option = e.target.closest('.node-select-option');
    if (option) {
        const select = option.closest('.node-select');
        if (select) {
            const input = select.querySelector('input[type="hidden"]');
            const label = select.querySelector('.node-select-trigger span:first-child');
            if (input) input.value = option.dataset.value;
            if (label) label.textContent = option.textContent;
            select.querySelectorAll('.node-select-option').forEach(item => item.classList.toggle('selected', item === option));
            select.classList.remove('open');
            if (select.id === 'node-select' && typeof renderAddClientJsonNodes === 'function') {
                renderAddClientJsonNodes();
            }
        }
        return;
    }
    document.querySelectorAll('.node-select.open').forEach(select => {
        if (!select.contains(e.target)) select.classList.remove('open');
    });
});
function renderAddClientJsonNodes() {
    const container = document.getElementById('add-client-json-nodes');
    if (!container) return;
    const selectedNodeId = document.getElementById('client-node')?.value;
    const availableNodes = (NODES_DATA || []).filter(n => n.id !== selectedNodeId && n.supports_json !== false);
    if (availableNodes.length === 0) {
        container.innerHTML = '';
        return;
    }
    let html = '<div style="font-size:12px; color:var(--text-secondary); width:100%; margin-bottom:0px;">Дополнительные ноды для JSON подписки:</div>';
    availableNodes.forEach(n => {
        html += '<label class="custom-checkbox-wrapper" style="font-size:12px; margin-top:0;">'
             + '<input type="checkbox" class="add-client-json-checkbox" value="' + escAttr(n.id) + '">'
             + '<span>' + escAttr(n.name) + '</span>'
             + '</label>';
    });
    container.innerHTML = html;
}
document.addEventListener("DOMContentLoaded", renderAddClientJsonNodes);

document.getElementById('add-client-form')?.addEventListener('submit', function (e) {
    e.preventDefault();
    const extraNodes = Array.from(document.querySelectorAll('.add-client-json-checkbox:checked')).map(cb => cb.value);
    submitManagement('__API_CLIENT__', { 
        action: 'add', 
        node: document.getElementById('client-node').value, 
        client: document.getElementById('new-client').value.trim(),
        additional_json_nodes: extraNodes
    }).then(() => location.reload()).catch(showManagementError);
});
document.getElementById('add-node-form')?.addEventListener('submit', function (e) {
    e.preventDefault();
    submitManagement('__API_NODE__', { 
        action: 'add', 
        name: document.getElementById('new-node-name').value.trim(), 
        url: document.getElementById('new-node-url').value.trim(),
        supports_json: document.getElementById('new-node-json').checked
    }).then(() => location.reload()).catch(showManagementError);
});
function saveUIState() {
    try {
        sessionStorage.setItem('subs_search', document.getElementById('client-search')?.value || '');
        sessionStorage.setItem('subs_sync_filter', syncFilter || '');
        const collapsed = [];
        document.querySelectorAll('.cards-grid.collapsed').forEach(g => {
            if (g.dataset.section) collapsed.push(g.dataset.section);
        });
        sessionStorage.setItem('subs_collapsed', JSON.stringify(collapsed));
    } catch (e) {}
}

function restoreUIState() {
    try {
        const search = sessionStorage.getItem('subs_search');
        if (search) {
            const input = document.getElementById('client-search');
            if (input) input.value = search;
        }
        const filter = sessionStorage.getItem('subs_sync_filter');
        if (filter) setSyncFilter(filter); // setSyncFilter internally calls filterCards()
        else filterCards();

        const collapsedStr = sessionStorage.getItem('subs_collapsed');
        if (collapsedStr) {
            const collapsed = JSON.parse(collapsedStr);
            document.querySelectorAll('.cards-grid').forEach(g => {
                if (g.dataset.section) {
                    const shouldCollapse = collapsed.includes(g.dataset.section);
                    g.classList.toggle('collapsed', shouldCollapse);
                    const header = g.previousElementSibling;
                    if (header && header.classList.contains('section-header')) {
                        const chevron = header.querySelector('.chevron');
                        if (chevron) chevron.classList.toggle('closed', shouldCollapse);
                    }
                }
            });
        }
    } catch (e) {}
}

window.addEventListener('beforeunload', saveUIState);
window.addEventListener('pagehide', saveUIState);
restoreUIState();
</script>
</body>
</html>
"""

LOGIN_TEMPLATE = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Вход · Сервер подписок</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
:root {
    --bg-dark: #0f172a;
    --bg-card: rgba(30, 41, 59, 0.85);
    --bg-input: rgba(15, 23, 42, 0.85);
    --border-color: rgba(255, 255, 255, 0.12);
    --border-focus: #3b82f6;
    --text-primary: #f8fafc;
    --text-secondary: #94a3b8;
    --primary-color: #3b82f6;
    --primary-hover: #2563eb;
    --accent: #3b82f6;
    --accent-hover: #2563eb;
    --accent-glow: rgba(59, 130, 246, 0.25);
    --danger-bg: rgba(239, 68, 68, 0.22);
    --danger-border: rgba(239, 68, 68, 0.5);
    --glow: 0 24px 50px rgba(2, 6, 23, 0.5);
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    font-family: 'Inter', sans-serif;
    color: var(--text-primary);
    background-color: var(--bg-dark);
    background-image:
        radial-gradient(at 0% 0%, rgba(59, 130, 246, 0.25) 0px, transparent 50%),
        radial-gradient(at 100% 100%, rgba(16, 185, 129, 0.15) 0px, transparent 50%),
        radial-gradient(at 50% 50%, rgba(15, 23, 42, 0.8) 0px, rgba(15, 23, 42, 1) 100%);
    padding: 20px;
}
.login-shell {
    width: min(460px, 100%);
    background: var(--bg-card);
    border: 1px solid var(--border-color);
    border-radius: 18px;
    padding: 28px;
    box-shadow: var(--glow);
    backdrop-filter: blur(24px);
    -webkit-backdrop-filter: blur(24px);
}
.login-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    margin-bottom: 18px;
}
.brand {
    display: flex;
    align-items: center;
    gap: 12px;
}
.brand-icon {
    width: 42px;
    height: 42px;
    border-radius: 12px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: rgba(59, 130, 246, 0.15);
    border: 1px solid rgba(59, 130, 246, 0.35);
}
.brand-title {
    font-size: 1.15rem;
    font-weight: 700;
    letter-spacing: -0.3px;
}
.brand-subtitle {
    margin-top: 2px;
    font-size: 0.82rem;
    color: var(--text-secondary);
}
.secure-pill {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    font-size: 0.75rem;
    font-weight: 500;
    color: #93c5fd;
    border: 1px solid rgba(59, 130, 246, 0.4);
    background: rgba(59, 130, 246, 0.12);
    border-radius: 999px;
    padding: 5px 11px;
}
h1 {
    margin: 6px 0 8px;
    font-size: 1.35rem;
    font-weight: 700;
    letter-spacing: -0.4px;
}
.desc {
    margin-bottom: 18px;
    color: var(--text-secondary);
    line-height: 1.45;
    font-size: 0.9rem;
}
label {
    display: block;
    margin: 14px 0 6px;
    font-size: 0.85rem;
    color: var(--text-secondary);
    font-weight: 500;
}
input {
    width: 100%;
    border: 1px solid var(--border-color);
    border-radius: 8px;
    background: var(--bg-input);
    color: var(--text-primary);
    padding: 10px 12px;
    font-size: 0.9rem;
    outline: none;
    transition: border-color 0.2s ease, box-shadow 0.2s ease;
}
input:focus {
    border-color: var(--border-focus);
    box-shadow: 0 0 0 3px var(--accent-glow);
}
button {
    margin-top: 20px;
    width: 100%;
    border: 0;
    border-radius: 8px;
    background: var(--accent);
    color: #fff;
    font-weight: 600;
    padding: 11px 14px;
    font-size: 0.92rem;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    transition: background 0.18s ease, transform 0.08s ease, box-shadow 0.18s ease;
}
button:hover { background: var(--accent-hover); box-shadow: 0 0 14px var(--accent-glow); }
button:active { transform: translateY(1px); }
.error {
    margin: 0 0 14px;
    color: #fecaca;
    border: 1px solid var(--danger-border);
    background: var(--danger-bg);
    border-radius: 8px;
    padding: 9px 12px;
    font-size: 0.85rem;
}
.hint {
    margin-top: 14px;
    font-size: 0.78rem;
    color: var(--text-secondary);
    line-height: 1.42;
}
@media (max-width: 560px) {
    .login-shell {
        padding: 20px;
        border-radius: 14px;
    }
    .login-head {
        flex-direction: column;
        align-items: flex-start;
    }
}
</style>
</head>
<body>
<div class="login-shell">
    <div class="login-head">
        <div class="brand">
            <div class="brand-icon">
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="color: var(--primary-color);">
                    <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
                    <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
                </svg>
            </div>
            <div>
                <div class="brand-title">Сервер подписок</div>
                <div class="brand-subtitle">Административный доступ</div>
            </div>
        </div>
        <div class="secure-pill">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
            <span>Secure Login</span>
        </div>
    </div>
    <h1>Вход в панель</h1>
    <p class="desc">Введите учетные данные администратора, чтобы открыть управление подписками и клиентскими ссылками.</p>
    __ERROR_BLOCK__
    <form method="post" action="__LOGIN_ACTION__">
        <input type="hidden" name="next" value="__NEXT__">
        <label for="user">Логин</label>
        <input id="user" name="user" autocomplete="username" required autofocus>
        <label for="password">Пароль</label>
        <input id="password" name="password" type="password" autocomplete="current-password" required>
        <button type="submit">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4"/><polyline points="10 17 15 12 10 7"/><line x1="15" y1="12" x2="3" y2="12"/></svg>
            <span>Войти</span>
        </button>
    </form>
    <div class="hint">Сессия сохраняется в браузере через защищенный cookie на 12 часов (или до перезапуска контейнера).</div>
</div>
</body>
</html>
"""


def setup_file_logging():
    """Mirror all sub-server logs to a file (the web UI tails this file).

    stdout (captured by ``docker logs -f subs-server``) and the log file stay
    in sync because the "sub-server" logger propagates to the root handler
    while also writing to LOG_FILE.
    """
    try:
        directory = os.path.dirname(os.path.abspath(LOG_FILE))
        os.makedirs(directory, exist_ok=True)
        handler = RotatingFileHandler(LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
        log.addHandler(handler)
    except OSError as exc:
        log.warning("could not open log file %s: %s", LOG_FILE, exc)


# Real-time per-client activity (last sync status), pushed to the web UI via
# the /api/logs SSE stream as `event: activity`.
CLIENT_ACTIVITY: dict = {}
ACTIVITY_SUBSCRIBERS: set = set()
ACTIVITY_LOCK = threading.Lock()
# Incremented on every admin status reset; open SSE streams use it to reset
# their log-file position after the file is truncated.
LOG_RESET_EVENT = 0


def reset_sync_statuses():
    """Clear all per-client sync statuses (memory + log file).

    ``CLIENT_ACTIVITY`` is emptied in-place so already-connected SSE streams
    pick up the change, and LOG_FILE is truncated so the statuses do not come
    back after a container restart (load_past_activity_from_logs reads it at
    startup).
    """
    global LOG_RESET_EVENT
    with ACTIVITY_LOCK:
        CLIENT_ACTIVITY.clear()
    try:
        with open(LOG_FILE, "w", encoding="utf-8"):
            pass
    except OSError as exc:
        log.warning("could not truncate %s: %s", LOG_FILE, exc)
    LOG_RESET_EVENT += 1
    log.info("sync statuses reset by admin")


def get_client_sync_state(client):
    with ACTIVITY_LOCK:
            activity = CLIENT_ACTIVITY.get(client)
    if not activity or not activity.get("time"):
        return "never"
    ts = activity.get("timestamp")
    if ts is None and activity.get("time"):
        try:
            ts = time.mktime(time.strptime(activity["time"], "%Y-%m-%d %H:%M:%S"))
        except Exception:
            ts = 0
    now = time.time()
    if ts and (now - ts <= 86400):
        return "recent"
    return "ever"


def _record_activity(client, status, bytes_, node, node_name, source, timestamp=None, ts_str=None):
    now_ts = timestamp if timestamp is not None else time.time()
    time_str = ts_str if ts_str is not None else time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now_ts))
    activity = {
        "client": client,
        "time": time_str,
        "timestamp": now_ts,
        "status": status,
        "bytes": bytes_,
        "node": node,
        "node_name": node_name,
        "source": source,
    }
    with ACTIVITY_LOCK:
        CLIENT_ACTIVITY[client] = activity
    payload = json.dumps(activity, ensure_ascii=False)
    with ACTIVITY_LOCK:
        for stream_queue in list(ACTIVITY_SUBSCRIBERS):
            try:
                stream_queue.put_nowait(payload)
            except Exception:
                pass


def load_past_activity_from_logs(path):
    if not os.path.exists(path):
        return
    sync_re = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+\w+\s+(200|404|502)\s+([^\s\(]+)(?:\s+\((.*)\))?\s*(?:->|<-\s*(\S+))?\s*(?:\(?(\d+)\s*bytes\)?)?")
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                m = sync_re.search(line)
                if m:
                    ts_str, status_str, client, group, url, bytes_str = m.groups()
                    try:
                        ts = time.mktime(time.strptime(ts_str, "%Y-%m-%d %H:%M:%S"))
                    except Exception:
                        ts = 0
                    status = int(status_str)
                    bytes_ = int(bytes_str) if bytes_str else 0
                    node_name = GROUP_LABELS.get("force") if group == "force" else group
                    with ACTIVITY_LOCK:
                        CLIENT_ACTIVITY[client] = {
                            "client": client,
                            "time": ts_str,
                            "timestamp": ts,
                            "status": status,
                            "bytes": bytes_,
                            "node": group if group != "force" else None,
                            "node_name": node_name,
                            "source": "force" if group == "force" else "node",
                        }
    except Exception as exc:
        log.warning("could not read past activity from log file: %s", exc)


def load_subs(path):
    """Load the legacy client database (subs.yml) with PyYAML.

    Expected structure (generated by older setup.sh versions):

        proxy:
          - client1
        freedom:
          - client2

    Only the ``proxy`` and ``freedom`` lists are read; anything else is ignored.

    LEGACY: subs.yml is only used to seed nodes.json when the registry is
    missing or empty. Remove once all existing deployments have migrated.
    """
    subs = {"proxy": [], "freedom": []}
    try:
        with open(path, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
    except (OSError, ValueError, yaml.YAMLError) as exc:
        log.warning("failed to parse %s: %s; using empty legacy configuration", path, exc)
        return subs
    if not isinstance(raw, dict):
        return subs
    for group in subs:
        clients = raw.get(group, [])
        if isinstance(clients, list):
            subs[group] = [str(client).strip() for client in clients if str(client).strip()]
    return subs


def default_nodes(legacy_subs=None):
    nodes = []
    legacy_subs = legacy_subs or {"proxy": [], "freedom": []}
    for node_id, name, url, group in (
        ("proxy", GROUP_LABELS["proxy"], RUSSIAN_SUB_URL, "proxy"),
        ("freedom", GROUP_LABELS["freedom"], FOREIGN_SUB_URL, "freedom"),
    ):
        url = url.rstrip("/")
        if url and not url.startswith(("http://", "https://")):
            url = "https://" + url
        if url or legacy_subs[group]:
            nodes.append({"id": node_id, "name": name, "url": url, "clients": list(legacy_subs[group]), "supports_json": True})
    return nodes


def load_nodes(path, legacy_subs=None):
    if not os.path.exists(path):
        return default_nodes(legacy_subs)
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as exc:
        log.warning("failed to load %s: %s; using node configuration from environment", path, exc)
        return default_nodes(legacy_subs)
    if not isinstance(data, list):
        return default_nodes(legacy_subs)
    result = []
    for item in data:
        if not isinstance(item, dict) or not item.get("id") or not item.get("name") or not item.get("url"):
            continue
        clients = item.get("clients", [])
        if not isinstance(clients, list):
            clients = []
        json_clients = item.get("json_clients", [])
        if not isinstance(json_clients, list):
            json_clients = []
        url = str(item["url"]).strip().rstrip("/")
        if url and not url.startswith(("http://", "https://")):
            url = "https://" + url
        result.append({
            "id": str(item["id"]),
            "name": str(item["name"]).strip(),
            "url": url,
            "clients": [str(client).strip() for client in clients if str(client).strip()],
            "json_clients": [str(client).strip() for client in json_clients if str(client).strip()],
        })
    return result or default_nodes(legacy_subs)


def save_nodes(nodes=None):
    nodes = NODES if nodes is None else nodes
    directory = os.path.dirname(os.path.abspath(NODES_FILE))
    os.makedirs(directory, exist_ok=True)
    # NODES_FILE is bind-mounted by Docker, so replace() would fail on the
    # mount point itself. The file is tiny and is protected by the admin API.
    with open(NODES_FILE, "w", encoding="utf-8") as f:
        json.dump(nodes, f, ensure_ascii=False, indent=2)
        f.write("\n")


def nodes_file_is_empty(path):
    """Return whether the node file is missing or contains no JSON data.

    setup.sh creates nodes.json with the full registry for new installations.
    A missing or empty file is reseeded from the environment URLs, optionally
    migrated from the legacy subs.yml.
    """
    if not os.path.exists(path):
        return True
    try:
        with open(path, encoding="utf-8") as f:
            return not f.read().strip()
    except OSError:
        return False


def all_clients():
    return {client for node in NODES for client in node.get("clients", [])}


def find_client_node(client):
    return next((node for node in NODES if client in node.get("clients", [])), None)


def load_force_subs(path):
    """Load override subscriptions from force-subs.yml (map of client -> value)."""
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
    except (OSError, ValueError, yaml.YAMLError) as exc:
        log.warning("failed to parse %s: %s; ignoring overrides", path, exc)
        return {}
    if not isinstance(raw, dict):
        log.warning("%s is not a mapping; ignoring overrides", path)
        return {}
    force = {}
    for key, value in raw.items():
        key = str(key).strip()
        value = str(value).strip()
        if key and value:
            force[key] = value
    return force


def encode_override_value(value):
    return base64.b64encode(value.encode("utf-8")).decode("ascii")


def decode_override_value(raw):
    raw = (raw or "").strip()
    try:
        data = base64.b64decode(raw, validate=True)
    except Exception:
        return raw
    if base64.b64encode(data).decode("ascii").rstrip("=") != raw.rstrip("="):
        return raw
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return raw


def save_force_subs(force=None):
    force = FORCE_SUBS if force is None else force
    directory = os.path.dirname(os.path.abspath(FORCE_FILE))
    os.makedirs(directory, exist_ok=True)
    header = (
        "# force-subs.yml\n"
        "# Переопределение подписки для конкретного клиента (значение закодировано в base64).\n"
        "# Формат: <client>: <base64-контент подписки>\n"
    )
    with open(FORCE_FILE, "w", encoding="utf-8") as f:
        f.write(header)
        yaml.safe_dump(force, f, allow_unicode=True, sort_keys=True, default_flow_style=False)


FORWARD_EXCLUDED_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "content-length",
    "date",
    "server",
}



def transform_configs(all_configs, routing_header_b64, client_name):
    if not all_configs:
        return {}
        
    base_config = all_configs[0]
    is_multi = len(all_configs) > 1
    
    final_config = {
        "dns": base_config.get("dns", {}),
        "inbounds": base_config.get("inbounds", []),
        "log": base_config.get("log", {"loglevel": "warning"}),
        "policy": base_config.get("policy", {}),
        "routing": base_config.get("routing", {}),
        "stats": base_config.get("stats", {})
    }
    final_config["remarks"] = client_name
    
    target_tag_key = "outboundTag"
    target_tag_val = "proxy"
    proxy_tags = []
    
    if is_multi:
        proxy_outbounds = []
        for idx, conf in enumerate(all_configs):
            outs = conf.get("outbounds", [])
            for out in outs:
                if out.get("tag") == "proxy" or out.get("protocol") in ("vless", "vmess", "trojan", "shadowsocks"):
                    addr = out.get("settings", {}).get("address", f"node{idx}")
                    net = out.get("streamSettings", {}).get("network", "tcp")
                    new_tag = f"proxy-{addr.split('.')[0]}-{net}-{idx}"
                    out["tag"] = new_tag
                    proxy_outbounds.append(out)
                    proxy_tags.append(new_tag)
                    
        final_outbounds = proxy_outbounds + [
            {"protocol": "freedom", "settings": {"domainStrategy": "AsIs", "noises": [], "redirect": ""}, "tag": "direct"},
            {"protocol": "blackhole", "settings": {"response": {"type": "http"}}, "tag": "block"}
        ]
        final_config["outbounds"] = final_outbounds
        final_config["observatory"] = {
            "subjectSelector": proxy_tags,
            "probeURL": "https://cp.cloudflare.com/generate_204",
            "probeInterval": "10s",
            "enableConcurrent": True
        }
        target_tag_key = "balancerTag"
        target_tag_val = "lb"
    else:
        final_config["outbounds"] = base_config.get("outbounds", [])
        
    if routing_header_b64:
        try:
            import json, base64
            header_val = routing_header_b64
            if "happ://routing/onadd/" in header_val:
                header_val = header_val.split("happ://routing/onadd/")[-1]
            elif "://" in header_val:
                header_val = header_val.split("://")[-1].split("/")[-1]
                
            routing_data = json.loads(base64.b64decode(header_val).decode('utf-8'))
            
            dns = {
                "queryStrategy": "UseIP",
                "servers": [],
                "tag": "dns_out"
            }
            if routing_data.get("DnsHosts"):
                dns["hosts"] = routing_data["DnsHosts"]
                
            if routing_data.get("RemoteDns"):
                dns["servers"].append({"address": routing_data["RemoteDns"], "skipFallback": False})
                
            if routing_data.get("DomesticDns"):
                dom_dns = {"address": routing_data["DomesticDns"]}
                dom_domains = []
                if "domain:ru" in routing_data.get("DirectSites", []):
                    dom_domains.append("domain:ru")
                if "domain:xn--p1ai" in routing_data.get("DirectSites", []):
                    dom_domains.append("domain:xn--p1ai")
                if "geosite:category-ru" in routing_data.get("DirectSites", []):
                    dom_domains.append("geosite:category-ru")
                if dom_domains:
                    dom_dns["domains"] = dom_domains
                dns["servers"].append(dom_dns)
                
            final_config["dns"] = dns
            
            rules = []
            
            if routing_data.get("BlockSites"):
                rules.append({"type": "field", "outboundTag": "block", "domain": routing_data["BlockSites"]})
            if routing_data.get("BlockIp"):
                rules.append({"type": "field", "outboundTag": "block", "ip": routing_data["BlockIp"]})
                
            if routing_data.get("ProxySites"):
                rules.append({"type": "field", target_tag_key: target_tag_val, "domain": routing_data["ProxySites"]})
            if routing_data.get("ProxyIp"):
                rules.append({"type": "field", target_tag_key: target_tag_val, "ip": routing_data["ProxyIp"]})
                
            if routing_data.get("DirectSites"):
                rules.append({"type": "field", "outboundTag": "direct", "domain": routing_data["DirectSites"]})
            if routing_data.get("DirectIp"):
                rules.append({"type": "field", "outboundTag": "direct", "ip": routing_data["DirectIp"]})
                
            rules.append({"network": "tcp,udp", "type": "field", target_tag_key: target_tag_val})
            
            final_routing = {
                "domainStrategy": routing_data.get("DomainStrategy", "IPIfNonMatch"),
                "rules": rules
            }
            if is_multi:
                final_routing["balancers"] = [{
                    "tag": "lb", 
                    "selector": proxy_tags, 
                    "strategy": {
                        "type": "leastLoad",
                        "settings": {"expected": 1, "maxRTT": "5s", "baselines": ["50ms", "150ms", "300ms", "500ms", "1s"], "tolerance": 0.1}
                    }
                }]
            final_config["routing"] = final_routing

        except Exception as e:
            log.error("Error parsing routing header: %s", e)
            if is_multi:
                final_config["routing"] = {
                    "domainStrategy": "IPIfNonMatch",
                    "balancers": [{ "tag": "lb", "selector": proxy_tags, "strategy": {"type": "leastLoad","settings": {"expected": 1, "maxRTT": "5s", "baselines": ["50ms", "150ms", "300ms", "500ms", "1s"], "tolerance": 0.1}}}],
                    "rules": [{"network": "tcp,udp", "balancerTag": "lb", "type": "field"}]
                }
            else:
                final_config["routing"] = {
                    "domainStrategy": "IPIfNonMatch",
                    "rules": [{"network": "tcp,udp", "outboundTag": "proxy", "type": "field"}]
                }
    else:
        # No routing header case
        if is_multi:
            final_config["routing"] = {
                "domainStrategy": "IPIfNonMatch",
                "balancers": [{ "tag": "lb", "selector": proxy_tags, "strategy": {"type": "leastLoad","settings": {"expected": 1, "maxRTT": "5s", "baselines": ["50ms", "150ms", "300ms", "500ms", "1s"], "tolerance": 0.1}}}],
                "rules": [{"network": "tcp,udp", "balancerTag": "lb", "type": "field"}]
            }

    return final_config

def fetch_subscription(url, user_agent=None, extra_headers=None):
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    req_headers = {}
    if user_agent:
        req_headers["User-Agent"] = user_agent
    else:
        req_headers["User-Agent"] = "sub-server/1.0"
    if extra_headers:
        req_headers.update(extra_headers)
    req = urllib.request.Request(url, headers=req_headers)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read(), resp.headers


class Handler(BaseHTTPRequestHandler):
    def _enforce_https(self):
        proto = self.headers.get("X-Forwarded-Proto", "").split(",")[0].strip().lower()
        if proto == "http":
            host = (self.headers.get("X-Forwarded-Host") or self.headers.get("Host") or "").strip()
            if host:
                self.send_response(301)
                self.send_header("Location", f"https://{host}{self.path}")
                self.end_headers()
                return False
            self.send_error(403, "HTTPS required")
            return False
        return True

    def _cookie_name(self):
        return f"sub_session_{SECRET_SUB_PATH}"

    def _parse_cookies(self):
        raw = self.headers.get("Cookie", "")
        cookies = {}
        for part in raw.split(";"):
            if "=" not in part:
                continue
            k, v = part.split("=", 1)
            cookies[k.strip()] = urllib.parse.unquote(v.strip())
        return cookies

    def _safe_next_path(self, next_path):
        val = (next_path or "").strip()
        if not val.startswith("/"):
            return f"/{SECRET_SUB_PATH}"
        # Prevent open redirects to external URLs.
        if not val.startswith(f"/{SECRET_SUB_PATH}"):
            return f"/{SECRET_SUB_PATH}"
        return val

    def _build_session_value(self, expires_ts):
        payload = f"{ADMIN_USER}:{expires_ts}"
        sig = hmac.new(AUTH_SESSION_SECRET.encode("utf-8"), payload.encode("utf-8"), "sha256").hexdigest()
        return f"{expires_ts}.{sig}"

    def _validate_session_value(self, token):
        if not token or "." not in token or not AUTH_SESSION_SECRET:
            return False
        ts_raw, sig = token.split(".", 1)
        if not ts_raw.isdigit():
            return False
        expires_ts = int(ts_raw)
        if expires_ts <= int(time.time()):
            return False
        expected = self._build_session_value(expires_ts).split(".", 1)[1]
        return hmac.compare_digest(sig, expected)

    def _set_session_cookie(self, max_age=SESSION_TTL_SECONDS):
        expires_ts = int(time.time()) + max(60, max_age)
        token = self._build_session_value(expires_ts)
        cookie = f"{self._cookie_name()}={urllib.parse.quote(token)}; Path=/{SECRET_SUB_PATH}; HttpOnly; SameSite=Lax; Max-Age={max(60, max_age)}"
        proto = self.headers.get("X-Forwarded-Proto", "").lower()
        if proto == "https":
            cookie += "; Secure"
        self.send_header("Set-Cookie", cookie)

    def _clear_session_cookie(self):
        cookie = f"{self._cookie_name()}=; Path=/{SECRET_SUB_PATH}; HttpOnly; SameSite=Lax; Max-Age=0"
        proto = self.headers.get("X-Forwarded-Proto", "").lower()
        if proto == "https":
            cookie += "; Secure"
        self.send_header("Set-Cookie", cookie)

    def _verify_login_password(self, user, password):
        return hmac.compare_digest(user or "", ADMIN_USER) and hmac.compare_digest(password or "", ADMIN_PASSWORD)

    def _basic_header_is_valid(self):
        header = self.headers.get("Authorization", "")
        if not header.startswith("Basic "):
            return False
        try:
            decoded = base64.b64decode(header[6:]).decode("utf-8")
        except Exception:
            return False
        user, _, password = decoded.partition(":")
        return self._verify_login_password(user, password)

    def _is_admin_authenticated(self):
        if not ADMIN_USER or not ADMIN_PASSWORD:
            return True
        cookies = self._parse_cookies()
        if self._validate_session_value(cookies.get(self._cookie_name(), "")):
            return True
        return self._basic_header_is_valid()

    def _require_auth(self, api=False):
        if self._is_admin_authenticated():
            return True
        log.info("401 unauthorized: %s", self.path)
        if api:
            self._send_json(401, {"ok": False, "error": "authentication required"})
            return False

        next_path = self._safe_next_path(self.path)
        login_url = f"/{SECRET_SUB_PATH}/login?next={urllib.parse.quote(next_path, safe='/%?=&') }"
        self.send_response(302)
        self.send_header("Location", login_url)
        self.end_headers()
        return False

    def _render_login_page(self, error_message="", next_path=""):
        safe_next = self._safe_next_path(next_path)
        error_html = ""
        if error_message:
            error_html = f'<div class="error">{html.escape(error_message)}</div>'
        body = (
            LOGIN_TEMPLATE
            .replace("__ERROR_BLOCK__", error_html)
            .replace("__NEXT__", html.escape(safe_next, quote=True))
            .replace("__LOGIN_ACTION__", f"/{SECRET_SUB_PATH}/login")
            .encode("utf-8")
        )
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _client_ip(self):
        xff = self.headers.get("X-Forwarded-For", "").strip()
        if xff:
            return xff.split(",")[0].strip()
        return self.client_address[0] if self.client_address else "unknown"

    def _handle_login_post(self):
        ip = self._client_ip()
        now = time.time()

        with LOGIN_LOCK:
            record = LOGIN_ATTEMPTS.get(ip)
            if record and record.get("lockout_until", 0) > now:
                remaining = int(record["lockout_until"] - now)
                self._render_login_page(f"Слишком много неудачных попыток. Попробуйте через {remaining} сек.", self._safe_next_path(f"/{SECRET_SUB_PATH}"))
                return

        length = int(self.headers.get("Content-Length", "0") or 0)
        raw = self.rfile.read(length).decode("utf-8", errors="ignore") if length else ""
        form = urllib.parse.parse_qs(raw, keep_blank_values=True)
        user = (form.get("user", [""])[0] or "").strip()
        password = form.get("password", [""])[0] or ""
        next_path = self._safe_next_path(form.get("next", [f"/{SECRET_SUB_PATH}"])[0])

        if not self._verify_login_password(user, password):
            with LOGIN_LOCK:
                rec = LOGIN_ATTEMPTS.setdefault(ip, {"count": 0, "lockout_until": 0, "last_attempt": now})
                if now - rec.get("last_attempt", 0) > 300:
                    rec["count"] = 0
                rec["count"] += 1
                rec["last_attempt"] = now
                if rec["count"] >= 5:
                    rec["lockout_until"] = now + 300  # 5 min lockout
                    rec["count"] = 0
            self._render_login_page("Неверный логин или пароль.", next_path)
            return

        with LOGIN_LOCK:
            LOGIN_ATTEMPTS.pop(ip, None)

        self.send_response(302)
        self._set_session_cookie()
        self.send_header("Location", next_path)
        self.end_headers()

    def _handle_logout(self):
        self.send_response(302)
        self._clear_session_cookie()
        self.send_header("Location", f"/{SECRET_SUB_PATH}/login")
        self.end_headers()

    def do_GET(self):
        if not self._enforce_https():
            return
        path = unquote(self.path.split("?", 1)[0]).strip("/")
        if path == f"{SECRET_SUB_PATH}/login":
            if not ADMIN_USER or not ADMIN_PASSWORD:
                self.send_response(302)
                self.send_header("Location", f"/{SECRET_SUB_PATH}")
                self.end_headers()
                return
            params = urllib.parse.parse_qs(self.path.split("?", 1)[1] if "?" in self.path else "")
            next_path = params.get("next", [f"/{SECRET_SUB_PATH}"])[0]
            self._render_login_page("", next_path)
            return

        if path == f"{SECRET_SUB_PATH}/logout":
            self._handle_logout()
            return

        if path == f"{SECRET_SUB_PATH}/api/logs":
            if not self._require_auth(api=True):
                return
            self._stream_logs()
            return

        parts = path.split("/")
        if len(parts) == 1 and parts[0] == SECRET_SUB_PATH:
            if not self._require_auth():
                return
            if self._wants_html():
                self._list_html()
            else:
                self._list_subscriptions()
            return
        if len(parts) == 3 and parts[0] == SECRET_SUB_PATH and parts[1] == "json":
            client = parts[2]
            is_json = True
        elif len(parts) == 2 and parts[0] == SECRET_SUB_PATH:
            client = parts[1]
            is_json = False
        else:
            log.warning("404 unknown path: %s", self.path)
            self.send_error(404)
            return
        if client in FORCE_SUBS:
            body = FORCE_SUBS[client].encode("utf-8")
            log.info("200 %s (force) -> %d bytes", client, len(body))
            _record_activity(client, 200, len(body), None, GROUP_LABELS["force"], "force")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        node = find_client_node(client)
        if not node:
            log.warning("404 unknown client: %s", client)
            _record_activity(client, 404, 0, None, None, None)
            self.send_error(404)
            return
        base_url = node["url"]
        group = node["id"]
        node_name = node["name"]
        if not base_url:
            log.error("502 no subscription URL configured for node '%s' (client %s)", node_name, client)
            _record_activity(client, 502, 0, group, node_name, "node")
            self.send_error(502)
            return
        quoted_client = urllib.parse.quote(client, safe='')
        client_ua = self.headers.get("User-Agent")
        extra_headers = {}
        for h in ("Accept", "Accept-Language"):
            val = self.headers.get(h)
            if val:
                extra_headers[h] = val

        if is_json:
            additional_json_nodes = [n for n in NODES if client in n.get("json_clients", [])]
            all_nodes = [node] + additional_json_nodes
            merged_json = []
            routing_header_b64 = None
            
            primary_upstream_headers = None
            for idx, n in enumerate(all_nodes):
                n_url = f"{n['url'].rstrip('/')}/json/{quoted_client}"
                try:
                    b, up_headers = fetch_subscription(n_url, user_agent=client_ua, extra_headers=extra_headers)
                    # grab routing header from primary node
                    if idx == 0 and up_headers:
                        primary_upstream_headers = up_headers
                        for k, v in up_headers.items():
                            if k.lower() == "routing":
                                routing_header_b64 = v
                                break
                    import json
                    data = json.loads(b.decode("utf-8"))
                    if isinstance(data, list):
                        merged_json.extend(data)
                    else:
                        merged_json.append(data)
                except Exception as e:
                    log.error("Failed to fetch JSON for %s from node %s: %s", client, n['name'], e)
            
            final_config = transform_configs(merged_json, routing_header_b64, client)
            body = json.dumps(final_config, ensure_ascii=False, indent=2).encode("utf-8")
            log.info("200 %s (transformed JSON %d nodes) <- (%d bytes)", client, len(all_nodes), len(body))
            _record_activity(client, 200, len(body), group, node_name, "node")
            self.send_response(200)
            
            if primary_upstream_headers:
                for key, value in primary_upstream_headers.items():
                    kl = key.lower()
                    if kl in FORWARD_EXCLUDED_HEADERS or kl == "content-type" or kl == "content-length":
                        continue
                    self.send_header(key, value)

            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        url = f"{base_url.rstrip('/')}/{quoted_client}"

        try:
            body, upstream_headers = fetch_subscription(url, user_agent=client_ua, extra_headers=extra_headers)
        except urllib.error.HTTPError as e:
            log.error("502 fetch failed for %s (%s): HTTP %s %s (url=%s)", client, node_name, e.code, e.reason, url)
            _record_activity(client, 502, 0, group, node_name, "node")
            self.send_error(502)
            return
        except urllib.error.URLError as e:
            log.error("502 fetch failed for %s (%s): %s (url=%s)", client, node_name, e.reason, url)
            _record_activity(client, 502, 0, group, node_name, "node")
            self.send_error(502)
            return
        except Exception as e:
            log.error("502 fetch failed for %s (%s): %r (url=%s)", client, node_name, e, url)
            _record_activity(client, 502, 0, group, node_name, "node")
            self.send_error(502)
            return
        log.info("200 %s (%s) <- %s (%d bytes)", client, node_name, url, len(body))
        _record_activity(client, 200, len(body), group, node_name, "node")
        self.send_response(200)
        has_content_type = False
        if upstream_headers:
            for key, value in upstream_headers.items():
                if key.lower() in FORWARD_EXCLUDED_HEADERS:
                    continue
                if key.lower() == "content-type":
                    has_content_type = True
                self.send_header(key, value)
        if not has_content_type:
            self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _query_params(self):
        query = self.path.split("?", 1)[1] if "?" in self.path else ""
        return set(p.split("=")[0].strip() for p in query.split("&") if p.strip())

    def do_POST(self):
        if not self._enforce_https():
            return
        global FORCE_SUBS, NODES
        path = unquote(self.path.split("?", 1)[0]).strip("/")
        if path == f"{SECRET_SUB_PATH}/login":
            self._handle_login_post()
            return
        if path == f"{SECRET_SUB_PATH}/logout":
            self._handle_logout()
            return

        api_paths = {
            f"{SECRET_SUB_PATH}/api/override",
            f"{SECRET_SUB_PATH}/api/client",
            f"{SECRET_SUB_PATH}/api/node",
            f"{SECRET_SUB_PATH}/api/reset",
        }
        if path not in api_paths:
            log.warning("404 unknown POST path: %s", self.path)
            self.send_error(404)
            return
        if not self._require_auth(api=True):
            return
        if path == f"{SECRET_SUB_PATH}/api/reset":
            reset_sync_statuses()
            self._send_json(200, {"ok": True})
            return
        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length) if length else b""
        try:
            data = json.loads(raw.decode("utf-8"))
            if not isinstance(data, dict):
                raise ValueError("JSON must be an object")
        except Exception:
            self._send_json(400, {"ok": False, "error": "невалидный JSON"})
            return

        with DATA_LOCK:
            if path == f"{SECRET_SUB_PATH}/api/client":
                action = (data.get("action") or "").strip()
                client = (data.get("client") or "").strip()
                reserved = {"login", "logout", "api", "logs", "static"}
                if not client or any(char in client for char in "\r\n:/") or client in reserved:
                    self._send_json(400, {"ok": False, "error": "некорректное или зарезервированное имя клиента"})
                    return
                if action == "add":
                    node = next((item for item in NODES if item["id"] == (data.get("node") or "")), None)
                    if not node:
                        self._send_json(400, {"ok": False, "error": "нода не найдена"})
                        return
                    if client in all_clients() or client in FORCE_SUBS:
                        self._send_json(400, {"ok": False, "error": "клиент с таким именем уже существует"})
                        return
                    node.get("clients", []).append(client)
                    if "additional_json_nodes" in data:
                        for n_id in data["additional_json_nodes"]:
                            target = next((n for n in NODES if n["id"] == n_id), None)
                            if target:
                                if "json_clients" not in target:
                                    target["json_clients"] = []
                                if client not in target["json_clients"]:
                                    target["json_clients"].append(client)
                elif action == "delete":
                    node = find_client_node(client)
                    if not node and client not in FORCE_SUBS:
                        self._send_json(400, {"ok": False, "error": "клиент не найден"})
                        return
                    for n in NODES:
                        while client in n.get("clients", []):
                            n["clients"].remove(client)
                    if client in FORCE_SUBS:
                        new_force = dict(FORCE_SUBS)
                        new_force.pop(client, None)
                        try:
                            save_force_subs(new_force)
                        except OSError as exc:
                            self._send_json(500, {"ok": False, "error": f"не удалось удалить override: {exc}"})
                            return
                        FORCE_SUBS = new_force
                elif action == "add_json_node":
                    node_id = (data.get("node") or "").strip()
                    target_node = next((n for n in NODES if n["id"] == node_id), None)
                    if not target_node:
                        self._send_json(400, {"ok": False, "error": "нода не найдена"})
                        return
                    if "json_clients" not in target_node:
                        target_node["json_clients"] = []
                    if client not in target_node["json_clients"]:
                        target_node["json_clients"].append(client)
                        try:
                            save_nodes()
                        except Exception as e:
                            self._send_json(500, {"ok": False, "error": str(e)})
                            return
                    self._send_json(200, {"ok": True})
                elif action == "remove_json_node":
                    node_id = (data.get("node") or "").strip()
                    target_node = next((n for n in NODES if n["id"] == node_id), None)
                    if not target_node:
                        self._send_json(400, {"ok": False, "error": "нода не найдена"})
                        return
                    if "json_clients" in target_node and client in target_node["json_clients"]:
                        target_node["json_clients"].remove(client)
                        try:
                            save_nodes()
                        except Exception as e:
                            self._send_json(500, {"ok": False, "error": str(e)})
                            return
                    self._send_json(200, {"ok": True})
                elif action == "edit":
                    new_name = (data.get("new_name") or "").strip()
                    target_id = (data.get("node") or "").strip()
                    if not new_name or any(char in new_name for char in "\r\n:/"):
                        self._send_json(400, {"ok": False, "error": "некорректное имя клиента"})
                        return
                    cur_node = find_client_node(client)
                    is_force = client in FORCE_SUBS
                    if not cur_node and not is_force:
                        self._send_json(400, {"ok": False, "error": "клиент не найден"})
                        return
                    target_node = None
                    if target_id:
                        target_node = next((item for item in NODES if item["id"] == target_id), None)
                        if not target_node:
                            self._send_json(400, {"ok": False, "error": "нода не найдена"})
                            return
                    other_clients = {c for n in NODES for c in n.get("clients", []) if c != client}
                    if new_name != client and (new_name in other_clients or (new_name in FORCE_SUBS and not is_force)):
                        self._send_json(400, {"ok": False, "error": "клиент с таким именем уже существует"})
                        return
                    if new_name == client and cur_node is target_node:
                        self._send_json(200, {"ok": True})
                        return
                    if new_name != client and client in FORCE_SUBS:
                        new_force = dict(FORCE_SUBS)
                        new_force[new_name] = new_force.pop(client)
                        try:
                            save_force_subs(new_force)
                        except OSError as exc:
                            self._send_json(500, {"ok": False, "error": f"не удалось обновить override: {exc}"})
                            return
                        FORCE_SUBS = new_force
                    for n in NODES:
                        while client in n.get("clients", []):
                            n["clients"].remove(client)
                    if target_node:
                        if new_name not in target_node.get("clients", []):
                            target_node.get("clients", []).append(new_name)
                else:
                    self._send_json(400, {"ok": False, "error": "неизвестное действие"})
                    return
                try:
                    save_nodes()
                except OSError as exc:
                    self._send_json(500, {"ok": False, "error": f"не удалось сохранить ноды: {exc}"})
                    return
                self._send_json(200, {"ok": True})
                return

            if path == f"{SECRET_SUB_PATH}/api/node":
                action = (data.get("action") or "").strip()
                if action == "add":
                    name = (data.get("name") or "").strip()
                    url = (data.get("url") or "").strip().rstrip("/")
                    if url and not url.startswith(("http://", "https://")):
                        url = "https://" + url
                    if not name or not url.startswith(("http://", "https://")):
                        self._send_json(400, {"ok": False, "error": "укажите имя и URL ноды (например: node.example.com/subs)"})
                        return
                    if any(node["name"].casefold() == name.casefold() for node in NODES):
                        self._send_json(400, {"ok": False, "error": "нода с таким именем уже существует"})
                        return
                    NODES.append({"id": uuid.uuid4().hex, "name": name, "url": url, "clients": [], "supports_json": bool(data.get("supports_json", True))})
                elif action == "delete":
                    node_id = (data.get("node") or "").strip()
                    node = next((item for item in NODES if item["id"] == node_id), None)
                    if not node:
                        self._send_json(400, {"ok": False, "error": "нода не найдена"})
                        return
                    if node.get("clients", []):
                        self._send_json(400, {"ok": False, "error": "сначала удалите клиентов этой ноды"})
                        return
                    NODES.remove(node)
                elif action == "edit":
                    node_id = (data.get("node") or "").strip()
                    node = next((item for item in NODES if item["id"] == node_id), None)
                    if not node:
                        self._send_json(400, {"ok": False, "error": "нода не найдена"})
                        return
                    name = (data.get("name") or "").strip()
                    url = (data.get("url") or "").strip().rstrip("/")
                    if not name:
                        name = node["name"]
                    if not url:
                        url = node["url"]
                    elif not url.startswith(("http://", "https://")):
                        url = "https://" + url
                    if not name:
                        self._send_json(400, {"ok": False, "error": "укажите имя ноды"})
                        return
                    if not url.startswith(("http://", "https://")):
                        self._send_json(400, {"ok": False, "error": "укажите URL ноды (например: node.example.com/subs)"})
                        return
                    if name != node["name"] and any(
                        item["name"].casefold() == name.casefold() and item["id"] != node_id for item in NODES
                    ):
                        self._send_json(400, {"ok": False, "error": "нода с таким именем уже существует"})
                        return
                    node["name"] = name
                    node["url"] = url
                    if "supports_json" in data:
                        node["supports_json"] = bool(data["supports_json"])
                else:
                    self._send_json(400, {"ok": False, "error": "неизвестное действие"})
                    return
                try:
                    save_nodes()
                except OSError as exc:
                    self._send_json(500, {"ok": False, "error": f"не удалось сохранить ноды: {exc}"})
                    return
                self._send_json(200, {"ok": True})
                return

            client = (data.get("client") or "").strip()
            value = (data.get("value") or "").strip()
            if client not in all_clients() and client not in FORCE_SUBS:
                self._send_json(400, {"ok": False, "error": f"неизвестный клиент: {client}"})
                return
            if value:
                if not value.startswith("vless://"):
                    self._send_json(400, {"ok": False, "error": "ссылка должна начинаться с vless://"})
                    return
                new_force = dict(FORCE_SUBS)
                new_force[client] = encode_override_value(value)
                action = "set"
            else:
                new_force = dict(FORCE_SUBS)
                new_force.pop(client, None)
                action = "cleared"
            try:
                save_force_subs(new_force)
            except Exception as e:
                log.error("failed to save %s: %r", FORCE_FILE, e)
                self._send_json(500, {"ok": False, "error": f"не удалось сохранить оверрайд: {e}"})
                return
            FORCE_SUBS = new_force
            log.info("override %s for client %s", action, client)
            self._send_json(200, {"ok": True})

    def _send_json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _wants_html(self):
        params = self._query_params()
        if "html" in params or "raw" in params:
            return "html" in params
        return "text/html" in self.headers.get("Accept", "")

    def _public_base(self):
        if PUBLIC_URL:
            return PUBLIC_URL
        scheme = self.headers.get("X-Forwarded-Proto", "https").split(",")[0].strip().lower()
        if scheme not in ("http", "https"):
            scheme = "https"
        host = (self.headers.get("X-Forwarded-Host") or self.headers.get("Host") or "").strip()
        return f"{scheme}://{host}".rstrip("/") if host else None

    def _node_cards(self):
        esc = html.escape
        cards = []
        for node in NODES:
            group = node["id"]
            url = node["url"]
            if not url:
                continue
            p = [f'<div class="card" data-search="{esc(node["name"])}">']
            p.append(
                f'<div class="client-header">'
                f'<span class="client-name-badge">'
                f'<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>'
                f'<span>{esc(node["name"])}</span></span>'
                f'<span style="display:flex;gap:6px;align-items:center">'
                f'<span class="group-badge">база подписки</span>'
                f'<button type="button" class="btn-sm btn-node-edit" data-node="{esc(node["id"])}" title="Редактировать ноду" aria-label="Редактировать ноду">'
                '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z"/></svg></button>'
                f'<button type="button" class="btn-sm btn-node-delete" data-node="{esc(node["id"])}" title="Удалить ноду" aria-label="Удалить ноду">'
                '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6l-1 14H6L5 6m3 0V4h8v2"></path><line x1="10" y1="11" x2="10" y2="17"></line><line x1="14" y1="11" x2="14" y2="17"></line></svg></button></span></div>'
            )
            p.append('<div class="client-link-group">')
            p.append(
                '<div class="client-link-label">'
                '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>'
                '<span>Подписочная ссылка ноды</span></div>'
            )
            p.append(
                f'<div class="client-link-row">'
                f'<span class="client-link-text" title="{esc(url)}">{esc(url)}</span>'
                f'<button type="button" class="btn-sm btn-copy" data-url="{esc(url)}">'
                '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>'
                '<span>Копировать</span></button>'
                f'</div>'
            )
            p.append('</div></div>')
            cards.append("\n".join(p))
        return cards

    def _client_sections(self):
        base = self._public_base()
        if not base:
            log.warning("no public base URL (PUBLIC_URL not set, Host header missing); using relative links")
            base = ""
        sections = []
        seen = set()
        idx = 0
        for node in NODES:
            clients = node.get("clients", [])
            if not clients:
                continue
            cards = []
            for client in clients:
                if client in seen:
                    continue
                cards.append(self._card_html(client, node, base, idx))
                seen.add(client)
                idx += 1
            if cards:
                sections.append(self._section_html(f'Карточки клиентов · {html.escape(node["name"])}', "\n".join(cards), f'node-{html.escape(node["id"])}'))
        force_clients = [c for c in sorted(FORCE_SUBS) if c not in seen]
        if force_clients:
            cards = []
            for client in force_clients:
                cards.append(self._card_html(client, None, base, idx))
                idx += 1
            sections.append(self._section_html("Карточки клиентов · Кастом (force-subs.yml)", "\n".join(cards), "force-subs"))
        return "\n".join(sections)

    def _section_html(self, title, cards, section_id=None):
        sid_attr = f' data-section="{html.escape(section_id)}"' if section_id else ''
        return (
            f'<div class="section-header" role="button" tabindex="0"{sid_attr}>'
            f'<span class="chevron"><svg width="10" height="6" viewBox="0 0 10 6" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M1 1L5 5L9 1" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg></span>'
            f'<span class="section-title-icon"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg></span>'
            f'<span>{title}</span><span class="line"></span></div>'
            f'<div class="cards-grid stacked"{sid_attr}>\n{cards}\n    </div>'
        )

    def _card_html(self, client, node, base, idx):
        esc = html.escape
        force = client in FORCE_SUBS
        sub_url = f"{base}/{SECRET_SUB_PATH}/{client}" if base else f"/{SECRET_SUB_PATH}/{client}"
        direct_url = f'{node["url"]}/{client}' if node else None

        force_tag = (
            '<span class="force-tag">'
            '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>'
            '<span>override</span></span>'
        ) if force else ""
        qr_panel_id = f"qr-panel-{idx}"

        search_text = f'{client} {node["name"]}' if node else client
        p = [f'<div class="card" data-search="{esc(search_text)}">']
        p.append(
            f'<div class="client-header">'
            f'<span class="client-name-badge">'
            f'<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>'
            f'<span>{esc(client)}</span></span>'
            f'<span style="display:flex;gap:6px;align-items:center">'
            f'<span class="group-badge">{esc(node["name"]) if node else GROUP_LABELS["force"]}</span>{force_tag}'
            + (f'<button type="button" class="btn-sm btn-client-edit" data-client="{esc(client)}" title="Редактировать клиента" aria-label="Редактировать клиента">'
               '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z"/></svg></button>'
               + (f'<button type="button" class="btn-sm btn-client-delete" data-client="{esc(client)}" title="Удалить клиента" aria-label="Удалить клиента">'
               '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6l-1 14H6L5 6m3 0V4h8v2"></path><line x1="10" y1="11" x2="10" y2="17"></line><line x1="14" y1="11" x2="14" y2="17"></line></svg></button>' if node else '')
               + '</span></div>')
        )
        p.append('<div class="client-link-grid">')

        p.append('<div class="client-link-col">')
        p.append(
            '<div class="client-link-label">'
            '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="2"/><path d="M16.24 7.76a6 6 0 0 1 0 8.49m-8.48-.01a6 6 0 0 1 0-8.49m11.31-2.82a10 10 0 0 1 0 14.14m-14.14 0a10 10 0 0 1 0-14.14"/></svg>'
            '<span>Через Сервер подписок</span></div>'
        )
        p.append(
            f'<div class="client-link-row">'
            f'<span class="client-link-text" title="{esc(sub_url)}">{esc(sub_url)}</span>'
            f'<button type="button" class="btn-sm btn-copy" data-url="{esc(sub_url)}">'
            '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>'
            '<span>Копировать</span></button>'
            f'<button type="button" class="btn-sm btn-qr" data-target="#{qr_panel_id}">'
            '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7"></rect><rect x="14" y="3" width="7" height="7"></rect><rect x="14" y="14" width="7" height="7"></rect><rect x="3" y="14" width="7" height="7"></rect></svg>'
            '<span>QR</span></button>'
            f'</div>'
        )
        sub_json_url = f"{base}/{SECRET_SUB_PATH}/json/{client}" if base else f"/{SECRET_SUB_PATH}/json/{client}"
        p.append(
            '<div class="client-link-label">'
            '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"></path><polyline points="3.27 6.96 12 12.01 20.73 6.96"></polyline><line x1="12" y1="22.08" x2="12" y2="12"></line></svg>'
            '<span>Через Сервер подписок (JSON)</span></div>'
        )
        p.append(
            f'<div class="client-link-row">'
            f'<span class="client-link-text" title="{esc(sub_json_url)}">{esc(sub_json_url)}</span>'
            f'<button type="button" class="btn-sm btn-copy" data-url="{esc(sub_json_url)}">'
            '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>'
            '<span>Копировать</span></button>'
            f'<button type="button" class="btn-sm btn-qr" data-target="#{qr_panel_id}">'
            '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7"></rect><rect x="14" y="3" width="7" height="7"></rect><rect x="14" y="14" width="7" height="7"></rect><rect x="3" y="14" width="7" height="7"></rect></svg>'
            '<span>QR</span></button>'
            f'</div>'
        )
        p.append('</div>')

        p.append('<div class="client-link-col">')
        p.append(
            '<div class="client-link-label">'
            '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>'
            '<span>Прямая ссылка</span></div>'
        )
        if direct_url:
            direct_json_url = f"{node["url"]}/json/{client}"
            p.append(
                f'<div class="client-link-row">'
                f'<span class="client-link-text" title="{esc(direct_url)}">{esc(direct_url)}</span>'
                f'<button type="button" class="btn-sm btn-copy" data-url="{esc(direct_url)}">'
                '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>'
                '<span>Копировать</span></button>'
                f'<button type="button" class="btn-sm btn-qr" data-target="#{qr_panel_id}">'
                '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7"></rect><rect x="14" y="3" width="7" height="7"></rect><rect x="14" y="14" width="7" height="7"></rect><rect x="3" y="14" width="7" height="7"></rect></svg>'
                '<span>QR</span></button>'
                f'</div>'
            )
            p.append(
                '<div class="client-link-label">'
                '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"></path><polyline points="3.27 6.96 12 12.01 20.73 6.96"></polyline><line x1="12" y1="22.08" x2="12" y2="12"></line></svg>'
                '<span>Прямая ссылка (JSON)</span></div>'
            )
            p.append(
                f'<div class="client-link-row">'
                f'<span class="client-link-text" title="{esc(direct_json_url)}">{esc(direct_json_url)}</span>'
                f'<button type="button" class="btn-sm btn-copy" data-url="{esc(direct_json_url)}">'
                '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>'
                '<span>Копировать</span></button>'
                f'<button type="button" class="btn-sm btn-qr" data-target="#{qr_panel_id}">'
                '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7"></rect><rect x="14" y="3" width="7" height="7"></rect><rect x="14" y="14" width="7" height="7"></rect><rect x="3" y="14" width="7" height="7"></rect></svg>'
                '<span>QR</span></button>'
                f'</div>'
            )
        else:
            if not node:
                p.append('<div class="note">Кастомная подписка из force-subs.yml — прямого таргета нет.</div>')
            else:
                p.append('<div class="note">Таргет-URL для группы не настроен.</div>')
        p.append('</div>')

        p.append('</div>')

        qr_items = []
        qr_items.append(f'<div class="qr-item" data-qr-val="{esc(sub_url)}"><img src="" alt="QR"><span>Через Сервер</span></div>')
        if direct_url:
            qr_items.append(f'<div class="qr-item" data-qr-val="{esc(direct_url)}"><img src="" alt="QR"><span>Прямая ссылка</span></div>')
        
        supports_json = node.get("supports_json", True)
        if supports_json:
            qr_items.append(f'<div class="qr-item" data-qr-val="{esc(sub_json_url)}"><img src="" alt="QR"><span>Через Сервер (JSON)</span></div>')
            if direct_url:
                qr_items.append(f'<div class="qr-item" data-qr-val="{esc(direct_json_url)}"><img src="" alt="QR"><span>Прямая ссылка (JSON)</span></div>')
        p.append(f'<div class="qr-panel" id="{qr_panel_id}">' + "".join(qr_items) + '</div>')

        if supports_json:
            additional_json_nodes = [n for n in NODES if client in n.get("json_clients", [])]
            p.append('<div class="additional-nodes-section" style="margin-top: 15px; padding: 12px; background: rgba(59, 130, 246, 0.05); border: 1px solid rgba(59, 130, 246, 0.15); border-radius: 8px;">')
            p.append('<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom: 8px;">')
            p.append('<div style="font-size: 13px; font-weight: 600; color: #60a5fa; display:flex; align-items:center; gap:6px;">'
                     '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"></path><polyline points="3.27 6.96 12 12.01 20.73 6.96"></polyline><line x1="12" y1="22.08" x2="12" y2="12"></line></svg>'
                     'Дополнительные ноды (только JSON)</div>')
            p.append('<div class="info-tooltip-container">'
                     '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"></path><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>'
                     f'<div class="info-tooltip">В JSON-подписку клиента объединяются конфигурации основной и всех дополнительных нод. Приложение клиента каждые 30 секунд проверяет их доступность (загружая тестовый URL через каждую ноду) и автоматически перенаправляет трафик через самую быструю рабочую ноду.</div>'
                     '</div>')
            p.append('</div>')
            if additional_json_nodes:
                for an in additional_json_nodes:
                    p.append(f'<div style="display:flex; justify-content: space-between; align-items:center; background: rgba(255, 255, 255, 0.05); border: 1px solid rgba(255,255,255,0.1); padding: 6px 10px; border-radius: 6px; margin-bottom: 6px; font-size:13px;">')
                    p.append(f'<span>{esc(an["name"])}</span>')
                    p.append(f'<button type="button" class="btn-sm btn-json-node-delete" data-client="{esc(client)}" data-node="{esc(an["id"])}" style="color:var(--danger-color); padding:4px; border:none; background:transparent; cursor:pointer;" title="Удалить"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6l-1 14H6L5 6m3 0V4h8v2"></path></svg></button>')
                    p.append('</div>')

            available_nodes = [n for n in NODES if n != node and client not in n.get("json_clients", [])]
            if available_nodes:
                opts = "".join(f'<div class="node-select-option{" selected" if n["id"] == available_nodes[0]["id"] else ""}" data-value="{esc(n["id"])}">{esc(n["name"])}</div>' for n in available_nodes)
                first_node = available_nodes[0]
                p.append(f'<div style="display:flex; gap: 8px; margin-top:8px; align-items:center;">')
                p.append(f'<button type="button" class="btn btn-sm btn-json-node-add" data-client="{esc(client)}" data-select="add-json-{qr_panel_id}" style="height: 32px; padding: 0 12px; font-size:13px; font-weight:500;">Добавить</button>')
                p.append(f'<div class="node-select" style="flex:1; min-width: 0;">'
                         f'<input type="hidden" id="add-json-{qr_panel_id}" value="{esc(first_node["id"])}">'
                         f'<button type="button" class="node-select-trigger" style="height: 32px; min-height: 32px; padding: 0 12px; margin: 0;"><span style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">{esc(first_node["name"])}</span>'
                         f'<span class="node-select-arrow"><svg width="10" height="6" viewBox="0 0 10 6" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M1 1L5 5L9 1" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg></span></button>'
                         f'<div class="node-select-options">{opts}</div>'
                         f'</div>')
                p.append('</div>')
            else:
                p.append('<div style="font-size:12px; color:var(--text-muted); margin-top:8px; text-align:center;">Нет доступных нод для добавления</div>')
            p.append('</div>')

        override_raw = FORCE_SUBS.get(client)
        override_val = decode_override_value(override_raw) if override_raw else None
        p.append('<div class="override-block">')
        p.append(
            '<div class="client-link-label">'
            '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"></circle><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path></svg>'
            '<span>Кастомная подписка (override)</span></div>'
        )
        if override_val:
            p.append(
                f'<div class="override-row">'
                f'<span class="override-text" data-custom="{esc(override_val)}" title="{esc(override_val)}">{esc(override_val)}</span>'
                f'<button type="button" class="btn-sm btn-override" data-client="{esc(client)}">'
                '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"></circle><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path></svg>'
                '<span>Установить</span></button>'
                f'<button type="button" class="btn-sm btn-override-clear" data-client="{esc(client)}">'
                '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>'
                '<span>Очистить</span></button>'
                f'</div>'
            )
        else:
            p.append(
                f'<div class="override-row">'
                f'<span class="override-text muted" data-custom="__none__">нет кастомной подписки</span>'
                f'<button type="button" class="btn-sm btn-override" data-client="{esc(client)}">'
                '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"></circle><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path></svg>'
                '<span>Установить</span></button>'
                f'</div>'
            )
        p.append(
            '<div class="override-editor">'
            '<textarea class="override-input" rows="3" placeholder="Вставьте сюда ссылку подписки vless://..."></textarea>'
            f'<div class="override-hint">Подключение к /{esc(SECRET_SUB_PATH)}/{esc(client)} будет отдавать указанную ссылку.</div>'
            '<div class="override-editor-actions">'
            f'<button type="button" class="btn-sm btn-override-save" data-client="{esc(client)}">'
            '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>'
            '<span>Сохранить</span></button>'
            '<button type="button" class="btn-sm btn-override-cancel">Отмена</button>'
            '</div></div>'
        )
        p.append('</div>')

        p.append(self._client_status_html(client))
        p.append('</div>')
        return "\n".join(p)

    def _client_status_html(self, client):
        esc = html.escape
        with ACTIVITY_LOCK:
            activity = CLIENT_ACTIVITY.get(client)
        state = get_client_sync_state(client)
        if state == "never" or not activity:
            return (
                f'<div class="client-status" data-client="{esc(client)}" data-time="" data-timestamp="0">'
                '<span class="status-dot st-never"></span>'
                '<span class="status-text">Синхронизации не было</span>'
                '</div>'
            )
        status = activity.get("status")
        dot_class = f"st-{state}"
        if isinstance(status, int) and not (200 <= status < 300):
            dot_class = "st-err"
        if activity.get("node_name"):
            src = f'через «{activity["node_name"]}»'
        elif activity.get("source") == "force":
            src = "через кастом"
        else:
            src = ""
        time_str = activity.get("time") or "—"
        ts_val = activity.get("timestamp") or 0
        text = (
            f'Последняя синхронизация: {time_str}'
            + (f' · HTTP {status}' if status else '')
            + (f' · {activity["bytes"]} B' if activity.get("bytes") else "")
            + (f' · {src}' if src else "")
        )
        return (
            f'<div class="client-status" data-client="{esc(client)}" data-time="{esc(time_str)}" data-timestamp="{ts_val}">'
            f'<span class="status-dot {dot_class}"></span>'
            f'<span class="status-text" title="{esc(text)}">{esc(text)}</span>'
            '</div>'
        )

    def _list_html(self):
        sections = self._client_sections() or '<div class="note">Клиенты не настроены.</div>'
        nodes = "\n".join(self._node_cards()) or '<div class="note">Подписочные URL нод не настроены.</div>'
        all_c = list(all_clients()) + [c for c in FORCE_SUBS if c not in all_clients()]
        total = len(all_c)
        count_recent = sum(1 for c in all_c if get_client_sync_state(c) == "recent")
        count_ever = sum(1 for c in all_c if get_client_sync_state(c) == "ever")
        count_never = sum(1 for c in all_c if get_client_sync_state(c) == "never")
        options = "".join(
            f'<div class="node-select-option" data-value="{html.escape(node["id"], quote=True)}">{html.escape(node["name"])}</div>'
            for node in NODES
        )
        first_node = NODES[0] if NODES else None
        node_picker = (
            f'<div class="node-select" id="node-select">'
            f'<input type="hidden" id="client-node" value="{html.escape(first_node["id"], quote=True) if first_node else ""}">'
            f'<button type="button" class="node-select-trigger"><span id="client-node-label">{html.escape(first_node["name"]) if first_node else "Нет доступных нод"}</span>'
            '<span class="node-select-arrow"><svg width="10" height="6" viewBox="0 0 10 6" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M1 1L5 5L9 1" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg></span></button>'
            f'<div class="node-select-options">{options}</div></div>'
        )
        management = (
            '<div class="management-grid">'
            '<div class="management-panel">'
            '<div class="management-title">'
            '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M16 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="8.5" cy="7" r="4"/><line x1="20" y1="8" x2="20" y2="14"/><line x1="23" y1="11" x2="17" y2="11"/></svg>'
            '<span>Добавить клиента</span></div>'
            f'<form class="management-row" id="add-client-form">{node_picker}<input id="new-client" placeholder="Имя нового клиента" required>'
            '<button class="btn-sm btn-primary" type="submit">'
            '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"></line><line x1="5" y1="12" x2="19" y2="12"></line></svg>'
            '<span>Добавить</span></button></form>'
            '<div id="add-client-json-nodes" style="display:flex; flex-wrap:wrap; gap:12px; margin-top:10px;"></div>'
            '</div>'
            '<div class="management-panel node-management">'
            '<div class="management-title">'
            '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="2" width="20" height="8" rx="2" ry="2"/><rect x="2" y="14" width="20" height="8" rx="2" ry="2"/><line x1="6" y1="6" x2="6.01" y2="6"/><line x1="6" y1="18" x2="6.01" y2="18"/></svg>'
            '<span>Добавить ноду</span></div>'
            '<form id="add-node-form">'
            '<div class="management-row"><input id="new-node-name" placeholder="Имя ноды" required><input id="new-node-url" placeholder="node.example/subs" required>'
            '<button class="btn-sm btn-primary" type="submit">'
            '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"></line><line x1="5" y1="12" x2="19" y2="12"></line></svg>'
            '<span>Добавить</span></button></div>'
            '<label class="custom-checkbox-wrapper" style="font-size:12px; margin-top:10px;">'
            '<input type="checkbox" id="new-node-json" checked>'
            '<span>Поддерживает JSON подписки</span>'
            '</label></form>'
            '<div id="management-message" class="management-error" hidden></div></div></div>'
        )
        body = (
            PAGE_TEMPLATE.replace("__SECTIONS__", sections)
            .replace("__NODES__", nodes)
            .replace("__MANAGEMENT__", management)
            .replace("__SEARCH__", '<input id="client-search" class="header-search" placeholder="поиск" aria-label="поиск">')
            .replace("__COUNT_TOTAL__", str(total))
            .replace("__COUNT_RECENT__", str(count_recent))
            .replace("__COUNT_EVER__", str(count_ever))
            .replace("__COUNT_NEVER__", str(count_never))
            .replace("__RAW_URL__", f"/{SECRET_SUB_PATH}?raw=1")
            .replace("__AUTH_ACTIONS__", f'<a class="btn-logout" href="/{SECRET_SUB_PATH}/logout">Выйти</a>' if ADMIN_USER and ADMIN_PASSWORD else "")
            .replace("__API_OVERRIDE__", f"/{SECRET_SUB_PATH}/api/override")
            .replace("__API_CLIENT__", f"/{SECRET_SUB_PATH}/api/client")
            .replace("__API_NODE__", f"/{SECRET_SUB_PATH}/api/node")
            .replace("__API_RESET__", f"/{SECRET_SUB_PATH}/api/reset")
            .replace("__LOGS_URL__", f"/{SECRET_SUB_PATH}/api/logs")
            .replace("__NODES_JSON__", json.dumps(NODES, ensure_ascii=False).replace("</", "<\\/"))
            .encode("utf-8")
        )
        log.info("200 html interface (%d cards)", total)
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _log_tail(self):
        """Return (recent log lines, file inode, byte size) for the SSE backlog."""
        try:
            size = os.path.getsize(LOG_FILE)
        except OSError:
            return b"", None, 0
        start = max(0, size - LOG_HISTORY_BYTES)
        if start:
            with open(LOG_FILE, "rb") as f:
                f.seek(start)
                data = f.read()
            first_nl = data.find(b"\n")
            if first_nl != -1:
                data = data[first_nl + 1:]
        else:
            with open(LOG_FILE, "rb") as f:
                data = f.read()
        lines = data.splitlines()
        tail = b"\n".join(lines[-LOG_HISTORY_LINES:])
        try:
            st = os.stat(LOG_FILE)
            inode, size = st.st_ino, st.st_size
        except OSError:
            inode, size = None, 0
        return tail, inode, size

    def _log_file_info(self):
        try:
            st = os.stat(LOG_FILE)
            return st.st_ino, st.st_size
        except OSError:
            return None, 0

    def _emit_log_events(self, raw):
        if not raw:
            return
        text = raw.decode("utf-8", errors="replace")
        for line in text.splitlines():
            line = line.rstrip()
            if not line:
                continue
            match = LOG_LINE_RE.match(line)
            if match:
                ts, level, msg = match.group(1), match.group(2), match.group(3)
            else:
                ts, level, msg = "", "INFO", line
            payload = json.dumps({"time": ts, "level": level, "message": msg}, ensure_ascii=False)
            self.wfile.write(f"data: {payload}\n\n".encode("utf-8"))
        self.wfile.flush()

    def _stream_logs(self):
        """Server-Sent Events stream tailing LOG_FILE (equivalent of docker logs -f).

        Emits ``message`` events for log lines and ``activity`` events for
        per-client subscription activity (drives the card status rows).
        """
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

        stream_queue = queue.Queue()
        with ACTIVITY_LOCK:
            ACTIVITY_SUBSCRIBERS.add(stream_queue)
        try:
            with ACTIVITY_LOCK:
                snapshot = [json.dumps(a, ensure_ascii=False) for a in CLIENT_ACTIVITY.values()]
            for payload in snapshot:
                self.wfile.write(f"event: activity\ndata: {payload}\n\n".encode("utf-8"))

            tail, last_inode, pos = self._log_tail()
            self._emit_log_events(tail)
            last_active = time.time()
            last_reset = LOG_RESET_EVENT
            while True:
                while True:
                    try:
                        payload = stream_queue.get_nowait()
                    except queue.Empty:
                        break
                    self.wfile.write(f"event: activity\ndata: {payload}\n\n".encode("utf-8"))
                inode, size = self._log_file_info()
                if LOG_RESET_EVENT != last_reset:
                    last_reset = LOG_RESET_EVENT
                    last_inode = inode
                    pos = 0
                    last_active = time.time()
                if inode != last_inode:
                    last_inode = inode
                    pos = 0
                if size > pos:
                    with open(LOG_FILE, "rb") as f:
                        f.seek(pos)
                        chunk = f.read(size - pos)
                    pos = size
                    self._emit_log_events(chunk)
                    last_active = time.time()
                elif time.time() - last_active > 15:
                    self.wfile.write(b": keep-alive\n\n")
                    self.wfile.flush()
                    last_active = time.time()
                time.sleep(0.7)
        except (BrokenPipeError, ConnectionResetError, OSError):
            log.info("log stream closed by client")
        finally:
            with ACTIVITY_LOCK:
                ACTIVITY_SUBSCRIBERS.discard(stream_queue)

    def _list_subscriptions(self):
        blocks = []
        total_urls = 0
        for node in NODES:
            clients = node.get("clients", [])
            url = (node.get("url") or "").rstrip("/")
            if not clients or not url:
                continue
            clients_line = ",".join(clients)
            url_lines = [f"{url}/{client}" for client in clients]
            total_urls += len(url_lines)
            blocks.append("\n".join([clients_line] + url_lines))
        separator = "========================"
        body = (f"\n{separator}\n".join(blocks) + "\n").encode("utf-8") if blocks else b""
        log.info("200 subscription list (%d urls across %d nodes)", total_urls, len(blocks))
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        log.info("request: %s", format % args)


def main():
    global FORCE_SUBS, NODES
    setup_file_logging()
    load_past_activity_from_logs(LOG_FILE)
    FORCE_SUBS = load_force_subs(FORCE_FILE)
    legacy_subs = None
    if nodes_file_is_empty(NODES_FILE):
        legacy_subs = load_subs(DATABASE_FILE)
        if not os.path.exists(DATABASE_FILE):
            log.info("no %s found, seeding node registry from environment", DATABASE_FILE)
    NODES = load_nodes(NODES_FILE, legacy_subs)
    if nodes_file_is_empty(NODES_FILE):
        try:
            save_nodes()
            log.info("initialized node registry %s (nodes.json is the source of truth)", NODES_FILE)
        except OSError as exc:
            log.warning("could not persist initial node configuration: %s", exc)
    log.info("listening on %s:%s, path prefix /%s, registry %s", HOST, PORT, SECRET_SUB_PATH, NODES_FILE)
    if ADMIN_USER and ADMIN_PASSWORD:
        log.info("admin auth enabled (user: %s)", ADMIN_USER)
    else:
        log.warning("admin auth DISABLED (set ADMIN_USER / ADMIN_PASSWORD)")
    log.info("RUSSIAN_SUB_URL=%s", RUSSIAN_SUB_URL or "(not set)")
    log.info("FOREIGN_SUB_URL=%s", FOREIGN_SUB_URL or "(not set)")
    log.info("PUBLIC_URL=%s", PUBLIC_URL or "(not set, derived from request headers)")
    log.info("nodes: %s", ", ".join(node["name"] for node in NODES) or "(none)")
    log.info("force overrides: %s", ", ".join(FORCE_SUBS) or "(none)")
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
