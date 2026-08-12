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

The client name is looked up in subs.yml (two lists: proxy and freedom).
  - proxy   -> RUSSIAN_SUB_URL  (Russian node)
  - freedom -> FOREIGN_SUB_URL  (non-Russian node)

Env vars:
  DATABASE_FILE   path to subs.yml (default: subs.yml)
  FORCE_FILE      path to force-subs.yml overrides (default: force-subs.yml)
  SECRET_SUB_PATH path prefix from the domain root (default: subs)
  RUSSIAN_SUB_URL subscription URL of the Russian node
  FOREIGN_SUB_URL subscription URL of the non-Russian node
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
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("sub-server")

DATABASE_FILE = os.environ.get("DATABASE_FILE", "subs.yml")
FORCE_FILE = os.environ.get("FORCE_FILE", "force-subs.yml")
SECRET_SUB_PATH = os.environ.get("SECRET_SUB_PATH", "subs").strip("/")
RUSSIAN_SUB_URL = os.environ.get("RUSSIAN_SUB_URL", "")
FOREIGN_SUB_URL = os.environ.get("FOREIGN_SUB_URL", "")
PUBLIC_URL = os.environ.get("PUBLIC_URL", "").strip().strip("/")
ADMIN_USER = os.environ.get("ADMIN_USER", "").strip()
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "").strip()
AUTH_SESSION_SECRET = os.environ.get("AUTH_SESSION_SECRET", "").strip() or ADMIN_PASSWORD
SESSION_TTL_SECONDS = int(os.environ.get("AUTH_SESSION_TTL", "43200"))
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "8080"))

GROUP_LABELS = {
    "proxy": "Proxy (РФ)",
    "freedom": "Freedom (зарубежье)",
    "force": "Кастом (force-subs.yml)",
}

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
    --text-primary: #f8fafc;
    --text-secondary: #94a3b8;
    --accent-glow: rgba(59, 130, 246, 0.25);
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
    font-family: 'Inter', sans-serif;
    background-color: var(--bg-dark);
    background-image:
        radial-gradient(at 0% 0%, rgba(59, 130, 246, 0.2) 0px, transparent 50%),
        radial-gradient(at 100% 100%, rgba(16, 185, 129, 0.15) 0px, transparent 50%),
        radial-gradient(at 50% 50%, rgba(15, 23, 42, 0.8) 0px, rgba(15, 23, 42, 1) 100%);
    color: var(--text-primary);
    min-height: 100vh;
    padding: 20px;
    display: flex;
    justify-content: center;
}
.app-container { width: 100%; max-width: 1140px; }
.app-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 25px; flex-wrap: wrap; gap: 10px; }
.logo-area { display: flex; align-items: center; gap: 12px; }
.logo-icon { font-size: 2rem; background: rgba(255, 255, 255, 0.05); padding: 10px; border-radius: 12px; border: 1px solid var(--border-color); }
.app-header h1 { font-size: 1.5rem; font-weight: 700; letter-spacing: -0.5px; }
.subtitle { font-size: 0.85rem; color: var(--text-secondary); }
.subtitle a { color: var(--primary-color); text-decoration: none; }
.subtitle a:hover { text-decoration: underline; }
.header-actions { display: flex; align-items: center; gap: 8px; }
.status-badge {
    display: flex; align-items: center; gap: 8px; font-size: 0.8rem;
    background: rgba(255, 255, 255, 0.05); border: 1px solid var(--border-color);
    padding: 6px 14px; border-radius: 20px;
}
.status-badge .dot { width: 8px; height: 8px; background-color: var(--success-color); border-radius: 50%; box-shadow: 0 0 8px var(--success-color); }
.cards-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(520px, 100%), 1fr)); gap: 16px; }
.cards-grid.stacked { grid-template-columns: minmax(0, 1fr); }
.cards-grid.collapsed { display: none; }
.card {
    background: var(--card-bg); backdrop-filter: blur(24px); -webkit-backdrop-filter: blur(24px);
    border: 1px solid var(--border-color); border-radius: 16px; padding: 20px;
    box-shadow: 0 20px 40px rgba(0, 0, 0, 0.3);
}
.client-header { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; }
.client-name-badge {
    background: rgba(59, 130, 246, 0.2); border: 1px solid rgba(59, 130, 246, 0.4);
    color: #93c5fd; padding: 4px 10px; border-radius: 6px; font-size: 0.85rem; font-weight: 600;
}
.group-badge { font-size: 0.75rem; color: var(--text-secondary); padding: 4px 10px; border-radius: 6px; background: rgba(255, 255, 255, 0.05); border: 1px solid var(--border-color); }
.force-tag { font-size: 0.72rem; color: #fbbf24; border: 1px solid rgba(251, 191, 36, 0.4); background: rgba(251, 191, 36, 0.1); padding: 2px 8px; border-radius: 6px; }
.client-link-group { display: flex; flex-direction: column; }
.client-link-label { font-size: 0.78rem; color: var(--text-secondary); font-weight: 500; margin-top: 10px; }
.client-link-label:first-child { margin-top: 0; }
.client-link-row {
    display: flex; align-items: center; gap: 8px; margin-top: 6px;
    background: rgba(15, 23, 42, 0.6); padding: 8px 12px; border-radius: 6px;
    border: 1px solid rgba(255, 255, 255, 0.05);
}
.client-link-text {
    flex: 1; min-width: 0; font-family: 'JetBrains Mono', monospace; font-size: 0.78rem;
    color: #e2e8f0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    word-break: break-all;
}
.btn-sm {
    background: rgba(255, 255, 255, 0.05); border: 1px solid var(--border-color);
    color: var(--text-primary); border-radius: 6px; padding: 6px 10px;
    font-size: 0.75rem; cursor: pointer; font-family: inherit; white-space: nowrap;
    transition: all 0.2s ease;
}
.btn-sm:hover { background: rgba(255, 255, 255, 0.12); }
.btn-sm.active { background: var(--primary-color); border-color: var(--primary-color); }
.client-link-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; margin-top: 12px; }
@media (max-width: 900px) { .client-link-grid { grid-template-columns: 1fr; } }
.client-link-col { display: flex; flex-direction: column; min-width: 0; }
.qr-panel { display: none; margin-top: 14px; }
.qr-panel.open { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
@media (max-width: 900px) { .qr-panel.open { grid-template-columns: 1fr; } }
.qr-item { display: flex; flex-direction: column; align-items: center; gap: 6px; background: rgba(15, 23, 42, 0.6); border: 1px solid rgba(255, 255, 255, 0.05); border-radius: 10px; padding: 12px; }
.qr-item img { width: 170px; height: 170px; background: #fff; border-radius: 8px; padding: 5px; }
.qr-item span { font-size: 0.72rem; color: var(--text-secondary); }
.override-block { margin-top: 14px; min-width: 0; }
.override-row { display: flex; align-items: center; gap: 8px; margin-top: 6px; min-width: 0; background: rgba(15, 23, 42, 0.6); padding: 8px 12px; border-radius: 6px; border: 1px solid rgba(251, 191, 36, 0.25); }
.override-text { flex: 1; min-width: 0; font-family: 'JetBrains Mono', monospace; font-size: 0.75rem; color: #fbbf24; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; word-break: break-all; }
.override-text.muted { color: var(--text-secondary); }
.override-editor { display: none; margin-top: 8px; }
.override-editor.open { display: block; }
.override-input { width: 100%; resize: vertical; background: rgba(15, 23, 42, 0.8); color: var(--text-primary); border: 1px solid var(--border-color); border-radius: 6px; padding: 8px 10px; font-family: 'JetBrains Mono', monospace; font-size: 0.78rem; }
.override-hint { font-size: 0.72rem; color: var(--text-secondary); margin-top: 6px; }
.override-editor-actions { display: flex; gap: 8px; margin-top: 8px; }
.override-editor-actions .btn-sm.btn-override-save { border-color: rgba(16, 185, 129, 0.4); background: rgba(16, 185, 129, 0.15); }
.note { font-size: 0.78rem; color: var(--text-secondary); margin-top: 6px; padding: 8px 12px; background: rgba(15, 23, 42, 0.6); border-radius: 6px; border: 1px dashed rgba(255, 255, 255, 0.1); }
.section-header { display: flex; align-items: center; gap: 8px; font-size: 0.9rem; font-weight: 600; margin-bottom: 14px; color: var(--text-primary); cursor: pointer; user-select: none; }
.section-header .chevron { transition: transform 0.2s ease; font-size: 0.8rem; }
.section-header .chevron.closed { transform: rotate(-90deg); }
.section-header .line { flex: 1; height: 1px; background: var(--border-color); }
.section-header + .cards-grid { margin-bottom: 24px; }
.btn-logout {
    border: 1px solid var(--border-color);
    border-radius: 999px;
    background: rgba(239, 68, 68, 0.2);
    color: #fecaca;
    padding: 6px 12px;
    font-size: 0.8rem;
    text-decoration: none;
}
.btn-logout:hover { background: rgba(239, 68, 68, 0.32); }
</style>
</head>
<body>
<div class="app-container">
    <div class="app-header">
        <div class="logo-area">
            <span class="logo-icon">📡</span>
            <div>
                <h1>Сервер подписок</h1>
                <div class="subtitle">Карточки клиентов · <a href="__RAW_URL__">текстовый список</a></div>
            </div>
        </div>
        <div class="header-actions">
            __AUTH_ACTIONS__
            <div class="status-badge"><span class="dot"></span><span>__STATUS__</span></div>
        </div>
    </div>
    <div class="section-header"><span class="chevron">▾</span>🌐 Подписочные ссылки нод<span class="line"></span></div>
    <div class="cards-grid">
__NODES__
    </div>
__SECTIONS__
</div>
<script>
function copyText(text, btn) {
    const done = () => {
        const old = btn.textContent;
        btn.textContent = '✓ Скопировано';
        btn.classList.add('active');
        setTimeout(() => { btn.textContent = old; btn.classList.remove('active'); }, 1200);
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
    const old = btn.textContent;
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
            setTimeout(() => { btn.textContent = old; btn.disabled = false; }, 2500);
        })
        .catch(() => {
            btn.textContent = 'Ошибка сети';
            btn.disabled = false;
            setTimeout(() => { btn.textContent = old; btn.disabled = false; }, 2500);
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
    const copy = e.target.closest('.btn-copy');
    if (copy) { copyText(copy.getAttribute('data-url'), copy); return; }
    const qr = e.target.closest('.btn-qr');
    if (qr) {
        const sel = qr.getAttribute('data-target');
        const el = document.querySelector(sel);
        const open = el.classList.toggle('open');
        document.querySelectorAll('.btn-qr[data-target="' + sel + '"]').forEach(b => {
            b.textContent = open ? 'Скрыть QR' : 'QR';
            b.classList.toggle('active', open);
        });
    }
});
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
<style>
:root {
    --bg-dark: #0f172a;
    --bg-card: rgba(30, 41, 59, 0.84);
    --bg-input: rgba(15, 23, 42, 0.78);
    --border-color: rgba(148, 163, 184, 0.28);
    --border-focus: rgba(34, 197, 94, 0.62);
    --text-primary: #f8fafc;
    --text-secondary: #94a3b8;
    --accent: #22c55e;
    --accent-hover: #16a34a;
    --danger-bg: rgba(239, 68, 68, 0.22);
    --danger-border: rgba(239, 68, 68, 0.5);
    --glow: 0 24px 50px rgba(2, 6, 23, 0.45);
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    font-family: 'Inter', 'Segoe UI', -apple-system, BlinkMacSystemFont, sans-serif;
    color: var(--text-primary);
    background:
        radial-gradient(850px 460px at 14% 16%, rgba(34, 197, 94, 0.2), transparent 56%),
        radial-gradient(760px 430px at 82% 74%, rgba(59, 130, 246, 0.16), transparent 53%),
        var(--bg-dark);
    padding: 20px;
}
.login-shell {
    width: min(460px, 100%);
    background: var(--bg-card);
    border: 1px solid var(--border-color);
    border-radius: 18px;
    padding: 26px;
    box-shadow: var(--glow);
    backdrop-filter: blur(12px);
}
.login-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    margin-bottom: 14px;
}
.brand {
    display: flex;
    align-items: center;
    gap: 12px;
}
.brand-icon {
    width: 40px;
    height: 40px;
    border-radius: 12px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: rgba(34, 197, 94, 0.18);
    border: 1px solid rgba(34, 197, 94, 0.35);
    font-size: 1.1rem;
}
.brand-title {
    font-size: 1.14rem;
    font-weight: 700;
    letter-spacing: 0.01em;
}
.brand-subtitle {
    margin-top: 2px;
    font-size: 0.82rem;
    color: var(--text-secondary);
}
.secure-pill {
    font-size: 0.75rem;
    color: #bbf7d0;
    border: 1px solid rgba(34, 197, 94, 0.42);
    background: rgba(34, 197, 94, 0.14);
    border-radius: 999px;
    padding: 6px 10px;
}
h1 {
    margin: 6px 0 8px;
    font-size: 1.38rem;
    font-weight: 750;
}
.desc {
    margin-bottom: 16px;
    color: var(--text-secondary);
    line-height: 1.42;
    font-size: 0.95rem;
}
label {
    display: block;
    margin: 13px 0 7px;
    font-size: 0.9rem;
    color: #dbeafe;
    font-weight: 560;
}
input {
    width: 100%;
    border: 1px solid var(--border-color);
    border-radius: 10px;
    background: var(--bg-input);
    color: var(--text-primary);
    padding: 11px 12px;
    font-size: 0.95rem;
    outline: none;
    transition: border-color 0.18s ease, box-shadow 0.18s ease;
}
input:focus {
    border-color: var(--border-focus);
    box-shadow: 0 0 0 3px rgba(34, 197, 94, 0.2);
}
button {
    margin-top: 18px;
    width: 100%;
    border: 0;
    border-radius: 10px;
    background: var(--accent);
    color: #052e16;
    font-weight: 700;
    padding: 11px 12px;
    font-size: 0.95rem;
    cursor: pointer;
    transition: background 0.18s ease, transform 0.08s ease;
}
button:hover { background: var(--accent-hover); }
button:active { transform: translateY(1px); }
.error {
    margin: 0 0 12px;
    color: #fecaca;
    border: 1px solid var(--danger-border);
    background: var(--danger-bg);
    border-radius: 8px;
    padding: 9px 10px;
    font-size: 0.9rem;
}
.hint {
    margin-top: 13px;
    font-size: 0.8rem;
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
            <div class="brand-icon">🔐</div>
            <div>
                <div class="brand-title">Сервер подписок</div>
                <div class="brand-subtitle">Административный доступ</div>
            </div>
        </div>
        <div class="secure-pill">Secure Login</div>
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
        <button type="submit">Войти</button>
    </form>
    <div class="hint">Сессия сохраняется в браузере через защищенный cookie и не требует повторного ввода на каждом действии.</div>
</div>
</body>
</html>
"""


def load_subs(path):
    subs = {"proxy": [], "freedom": []}
    section = None
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.endswith(":"):
                section = line[:-1].strip()
                if section not in subs:
                    section = None
                continue
            if section and line.startswith("-"):
                name = line[1:].strip()
                if name:
                    subs[section].append(name)
    return subs


def load_force_subs(path):
    force = {}
    if not os.path.exists(path):
        return force
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" not in line:
                continue
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip()
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
    lines = [
        "# force-subs.yml",
        "# Переопределение подписки для конкретного клиента (значение закодировано в base64).",
        "# Формат: <client>: <base64-контент подписки>",
    ]
    for client in sorted(force):
        lines.append(f"{client}: {force[client]}")
    with open(FORCE_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def fetch_subscription(url):
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    req = urllib.request.Request(url, headers={"User-Agent": "sub-server/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read()


def qr_img_url(value):
    data = urllib.parse.quote(value, safe="")
    return f"https://api.qrserver.com/v1/create-qr-code/?data={data}&size=200x200&margin=6"


class Handler(BaseHTTPRequestHandler):
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
        if val.startswith("//") or "://" in val:
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

    def _handle_login_post(self):
        length = int(self.headers.get("Content-Length", "0") or 0)
        raw = self.rfile.read(length).decode("utf-8", errors="ignore") if length else ""
        form = urllib.parse.parse_qs(raw, keep_blank_values=True)
        user = (form.get("user", [""])[0] or "").strip()
        password = form.get("password", [""])[0] or ""
        next_path = self._safe_next_path(form.get("next", [f"/{SECRET_SUB_PATH}"])[0])

        if not self._verify_login_password(user, password):
            self._render_login_page("Неверный логин или пароль.", next_path)
            return

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

        parts = path.split("/")
        if len(parts) == 1 and parts[0] == SECRET_SUB_PATH:
            if not self._require_auth():
                return
            if self._wants_html():
                self._list_html()
            else:
                self._list_subscriptions()
            return
        if len(parts) != 2 or parts[0] != SECRET_SUB_PATH:
            log.warning("404 unknown path: %s", self.path)
            self.send_error(404)
            return
        client = parts[1]
        if client in FORCE_SUBS:
            body = FORCE_SUBS[client].encode("utf-8")
            log.info("200 %s (force) -> %d bytes", client, len(body))
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if client in SUBS["proxy"]:
            base_url = RUSSIAN_SUB_URL
            group = "proxy"
        elif client in SUBS["freedom"]:
            base_url = FOREIGN_SUB_URL
            group = "freedom"
        else:
            log.warning("404 unknown client: %s", client)
            self.send_error(404)
            return
        if not base_url:
            log.error("502 no subscription URL configured for group '%s' (client %s)", group, client)
            self.send_error(502)
            return
        url = f"{base_url.rstrip('/')}/{client}"
        try:
            body = fetch_subscription(url)
        except urllib.error.HTTPError as e:
            log.error("502 fetch failed for %s (%s): HTTP %s %s (url=%s)", client, group, e.code, e.reason, url)
            self.send_error(502)
            return
        except urllib.error.URLError as e:
            log.error("502 fetch failed for %s (%s): %s (url=%s)", client, group, e.reason, url)
            self.send_error(502)
            return
        except Exception as e:
            log.error("502 fetch failed for %s (%s): %r (url=%s)", client, group, e, url)
            self.send_error(502)
            return
        log.info("200 %s (%s) <- %s (%d bytes)", client, group, url, len(body))
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _query_params(self):
        query = self.path.split("?", 1)[1] if "?" in self.path else ""
        return set(p.split("=")[0].strip() for p in query.split("&") if p.strip())

    def do_POST(self):
        global FORCE_SUBS
        path = unquote(self.path.split("?", 1)[0]).strip("/")
        if path == f"{SECRET_SUB_PATH}/login":
            self._handle_login_post()
            return
        if path == f"{SECRET_SUB_PATH}/logout":
            self._handle_logout()
            return

        if path != f"{SECRET_SUB_PATH}/api/override":
            log.warning("404 unknown POST path: %s", self.path)
            self.send_error(404)
            return
        if not self._require_auth(api=True):
            return
        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length) if length else b""
        try:
            data = json.loads(raw.decode("utf-8"))
        except Exception:
            self._send_json(400, {"ok": False, "error": "невалидный JSON"})
            return
        client = (data.get("client") or "").strip()
        value = (data.get("value") or "").strip()
        if client not in SUBS["proxy"] and client not in SUBS["freedom"] and client not in FORCE_SUBS:
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
        scheme = self.headers.get("X-Forwarded-Proto", "http").split(",")[0].strip().lower()
        if scheme not in ("http", "https"):
            scheme = "http"
        host = (self.headers.get("X-Forwarded-Host") or self.headers.get("Host") or "").strip()
        return f"{scheme}://{host}".rstrip("/") if host else None

    def _node_cards(self):
        esc = html.escape
        cards = []
        for group, url in (("proxy", RUSSIAN_SUB_URL), ("freedom", FOREIGN_SUB_URL)):
            if not url:
                continue
            p = ['<div class="card">']
            p.append(
                f'<div class="client-header">'
                f'<span class="client-name-badge">🌐 {GROUP_LABELS[group]}</span>'
                f'<span class="group-badge">база подписки</span></div>'
            )
            p.append('<div class="client-link-group">')
            p.append('<div class="client-link-label">🔗 Подписочная ссылка ноды</div>')
            p.append(
                f'<div class="client-link-row">'
                f'<span class="client-link-text" title="{esc(url)}">{esc(url)}</span>'
                f'<button type="button" class="btn-sm btn-copy" data-url="{esc(url)}">📋 Копировать</button>'
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
        for group, label in (
            ("proxy", "👤 Карточки клиентов · Proxy node"),
            ("freedom", "👤 Карточки клиентов · Freedom node"),
        ):
            clients = SUBS[group]
            if not clients:
                continue
            cards = []
            for client in clients:
                cards.append(self._card_html(client, group, base, idx))
                seen.add(client)
                idx += 1
            sections.append(self._section_html(label, "\n".join(cards)))
        force_clients = [c for c in sorted(FORCE_SUBS) if c not in seen]
        if force_clients:
            cards = []
            for client in force_clients:
                cards.append(self._card_html(client, "force", base, idx))
                idx += 1
            sections.append(self._section_html("👤 Карточки клиентов · Кастом (force-subs.yml)", "\n".join(cards)))
        return "\n".join(sections)

    def _section_html(self, title, cards):
        return (
            f'<div class="section-header" role="button" tabindex="0">'
            f'<span class="chevron">▾</span>{title}<span class="line"></span></div>'
            f'<div class="cards-grid stacked">\n{cards}\n    </div>'
        )

    def _card_html(self, client, group, base, idx):
        esc = html.escape
        force = client in FORCE_SUBS
        sub_url = f"{base}/{SECRET_SUB_PATH}/{client}" if base else f"/{SECRET_SUB_PATH}/{client}"
        if group == "proxy":
            direct_url = f"{RUSSIAN_SUB_URL.rstrip('/')}/{client}" if RUSSIAN_SUB_URL else None
        elif group == "freedom":
            direct_url = f"{FOREIGN_SUB_URL.rstrip('/')}/{client}" if FOREIGN_SUB_URL else None
        else:
            direct_url = None

        force_tag = '<span class="force-tag">⚡ override</span>' if force else ""
        qr_panel_id = f"qr-panel-{idx}"

        p = ['<div class="card">']
        p.append(
            f'<div class="client-header">'
            f'<span class="client-name-badge">👤 {esc(client)}</span>'
            f'<span style="display:flex;gap:6px;align-items:center">'
            f'<span class="group-badge">{GROUP_LABELS[group]}</span>{force_tag}</span></div>'
        )
        p.append('<div class="client-link-grid">')

        p.append('<div class="client-link-col">')
        p.append('<div class="client-link-label">📡 Через Сервер подписок</div>')
        p.append(
            f'<div class="client-link-row">'
            f'<span class="client-link-text" title="{esc(sub_url)}">{esc(sub_url)}</span>'
            f'<button type="button" class="btn-sm btn-copy" data-url="{esc(sub_url)}">📋 Копировать</button>'
            f'<button type="button" class="btn-sm btn-qr" data-target="#{qr_panel_id}">QR</button>'
            f'</div>'
        )
        p.append('</div>')

        p.append('<div class="client-link-col">')
        p.append('<div class="client-link-label">🔗 Прямая ссылка</div>')
        if direct_url:
            p.append(
                f'<div class="client-link-row">'
                f'<span class="client-link-text" title="{esc(direct_url)}">{esc(direct_url)}</span>'
                f'<button type="button" class="btn-sm btn-copy" data-url="{esc(direct_url)}">📋 Копировать</button>'
                f'<button type="button" class="btn-sm btn-qr" data-target="#{qr_panel_id}">QR</button>'
                f'</div>'
            )
        else:
            if group == "force":
                p.append('<div class="note">Кастомная подписка из force-subs.yml — прямого таргета нет.</div>')
            else:
                p.append('<div class="note">Таргет-URL для группы не настроен.</div>')
        p.append('</div>')

        p.append('</div>')

        qr_items = [
            f'<div class="qr-item"><img src="{esc(qr_img_url(sub_url))}" alt="QR"><span>Через Сервер подписок</span></div>'
        ]
        if direct_url:
            qr_items.append(f'<div class="qr-item"><img src="{esc(qr_img_url(direct_url))}" alt="QR"><span>Прямая ссылка</span></div>')
        p.append(f'<div class="qr-panel" id="{qr_panel_id}">' + "".join(qr_items) + '</div>')

        override_raw = FORCE_SUBS.get(client)
        override_val = decode_override_value(override_raw) if override_raw else None
        p.append('<div class="override-block">')
        p.append('<div class="client-link-label">⚙ Кастомная подписка (override)</div>')
        if override_val:
            p.append(
                f'<div class="override-row">'
                f'<span class="override-text" data-custom="{esc(override_val)}" title="{esc(override_val)}">{esc(override_val)}</span>'
                f'<button type="button" class="btn-sm btn-override" data-client="{esc(client)}">⚙ Установить</button>'
                f'<button type="button" class="btn-sm btn-override-clear" data-client="{esc(client)}">✖ Очистить</button>'
                f'</div>'
            )
        else:
            p.append(
                f'<div class="override-row">'
                f'<span class="override-text muted" data-custom="__none__">нет кастомной подписки</span>'
                f'<button type="button" class="btn-sm btn-override" data-client="{esc(client)}">⚙ Установить</button>'
                f'</div>'
            )
        p.append(
            '<div class="override-editor">'
            '<textarea class="override-input" rows="3" placeholder="Вставьте сюда ссылку подписки vless://..."></textarea>'
            f'<div class="override-hint">Подключение к /{esc(SECRET_SUB_PATH)}/{esc(client)} будет отдавать указанную ссылку.</div>'
            '<div class="override-editor-actions">'
            f'<button type="button" class="btn-sm btn-override-save" data-client="{esc(client)}">✓ Сохранить</button>'
            '<button type="button" class="btn-sm btn-override-cancel">Отмена</button>'
            '</div></div>'
        )
        p.append('</div>')

        p.append('</div>')
        return "\n".join(p)

    def _list_html(self):
        sections = self._client_sections() or '<div class="note">Клиенты не настроены.</div>'
        nodes = "\n".join(self._node_cards()) or '<div class="note">Подписочные URL нод не настроены.</div>'
        total = len(SUBS["proxy"]) + len(SUBS["freedom"]) + len(
            [c for c in FORCE_SUBS if c not in SUBS["proxy"] and c not in SUBS["freedom"]]
        )
        status = f"Клиентов: {total}"
        body = (
            PAGE_TEMPLATE.replace("__SECTIONS__", sections)
            .replace("__NODES__", nodes)
            .replace("__STATUS__", status)
            .replace("__RAW_URL__", f"/{SECRET_SUB_PATH}?raw=1")
            .replace("__AUTH_ACTIONS__", f'<a class="btn-logout" href="/{SECRET_SUB_PATH}/logout">Выйти</a>' if ADMIN_USER and ADMIN_PASSWORD else "")
            .replace("__API_OVERRIDE__", f"/{SECRET_SUB_PATH}/api/override")
            .encode("utf-8")
        )
        log.info("200 html interface (%d cards)", total)
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _list_subscriptions(self):
        lines = []
        for client in SUBS["proxy"]:
            if RUSSIAN_SUB_URL:
                lines.append(f"{RUSSIAN_SUB_URL}/{client}")
        for client in SUBS["freedom"]:
            if FOREIGN_SUB_URL:
                lines.append(f"{FOREIGN_SUB_URL}/{client}")
        body = ("\n".join(lines) + "\n").encode("utf-8")
        log.info("200 subscription list (%d urls)", len(lines))
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        log.info("request: %s", format % args)


def main():
    global SUBS, FORCE_SUBS
    SUBS = load_subs(DATABASE_FILE)
    FORCE_SUBS = load_force_subs(FORCE_FILE)
    log.info("listening on %s:%s, path prefix /%s, db %s", HOST, PORT, SECRET_SUB_PATH, DATABASE_FILE)
    if ADMIN_USER and ADMIN_PASSWORD:
        log.info("admin auth enabled (user: %s)", ADMIN_USER)
    else:
        log.warning("admin auth DISABLED (set ADMIN_USER / ADMIN_PASSWORD)")
    log.info("RUSSIAN_SUB_URL=%s", RUSSIAN_SUB_URL or "(not set)")
    log.info("FOREIGN_SUB_URL=%s", FOREIGN_SUB_URL or "(not set)")
    log.info("PUBLIC_URL=%s", PUBLIC_URL or "(not set, derived from request headers)")
    log.info("proxy clients: %s", ", ".join(SUBS["proxy"]) or "(none)")
    log.info("freedom clients: %s", ", ".join(SUBS["freedom"]) or "(none)")
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
