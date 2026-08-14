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
import uuid
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
NODES_FILE = os.environ.get("NODES_FILE", "nodes.json")
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

NODES = []

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
.header-search { width: min(300px, 35vw); margin: 0; }
.header-search { height: 38px; padding: 8px 13px; border: 1px solid var(--border-color); border-radius: 999px; outline: none; background: rgba(30, 41, 59, .72); color: var(--text-primary); box-shadow: inset 0 1px 0 rgba(255,255,255,.04), 0 8px 24px rgba(2, 6, 23, .18); font: inherit; font-size: .82rem; transition: border-color .2s ease, box-shadow .2s ease, background .2s ease; }
.header-search::placeholder { color: var(--text-secondary); opacity: 1; }
.header-search:focus { border-color: rgba(59, 130, 246, .72); background: rgba(30, 41, 59, .94); box-shadow: 0 0 0 3px var(--accent-glow), 0 8px 24px rgba(2, 6, 23, .24); }
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
.management-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; margin: 0 0 24px; }
.management-panel { padding: 16px; background: rgba(30, 41, 59, 0.55); border: 1px solid var(--border-color); border-radius: 14px; }
.management-title { font-weight: 600; margin-bottom: 10px; }
.management-row { display: flex; gap: 8px; margin-top: 8px; }
.management-row input, .management-row select { flex: 1; min-width: 0; border: 1px solid var(--border-color); border-radius: 6px; background: rgba(15, 23, 42, 0.8); color: var(--text-primary); padding: 8px 10px; font: inherit; font-size: .82rem; }
.management-row select { appearance: none; background-image: linear-gradient(45deg, transparent 50%, #94a3b8 50%), linear-gradient(135deg, #94a3b8 50%, transparent 50%); background-position: calc(100% - 15px) 50%, calc(100% - 10px) 50%; background-size: 5px 5px, 5px 5px; background-repeat: no-repeat; padding-right: 28px; }
.node-select { position: relative; flex: 1; min-width: 0; }
.node-select-trigger { display: flex; align-items: center; justify-content: space-between; width: 100%; min-height: 38px; padding: 8px 10px; background: rgba(15, 23, 42, .9); border: 1px solid var(--border-color); border-radius: 8px; color: var(--text-primary); font: inherit; font-size: .82rem; cursor: pointer; }
.node-select-trigger:hover, .node-select.open .node-select-trigger { border-color: rgba(59, 130, 246, .6); background: rgba(30, 41, 59, .95); }
.node-select-arrow { color: var(--text-secondary); transition: transform .2s ease; }
.node-select.open .node-select-arrow { transform: rotate(180deg); color: var(--primary-color); }
.node-select-options { position: absolute; z-index: 20; top: calc(100% + 6px); left: 0; right: 0; padding: 5px; background: rgba(30, 41, 59, .97); border: 1px solid rgba(255,255,255,.12); border-radius: 10px; box-shadow: 0 10px 25px rgba(0,0,0,.5); opacity: 0; visibility: hidden; transform: translateY(-4px) scale(.98); transition: all .18s ease; }
.node-select.open .node-select-options { opacity: 1; visibility: visible; transform: translateY(0) scale(1); }
.node-select-option { padding: 8px 10px; color: var(--text-secondary); border-radius: 6px; cursor: pointer; font-size: .82rem; }
.node-select-option:hover, .node-select-option.selected { background: rgba(59,130,246,.2); color: var(--text-primary); }
.management-row .btn-sm { flex-shrink: 0; }
.btn-client-delete, .btn-node-delete { color: #fecaca; border-color: rgba(239, 68, 68, .35); padding: 5px 7px; line-height: 1; }
.btn-client-delete svg, .btn-node-delete svg { width: 16px; height: 16px; display: block; }
.btn-client-edit, .btn-node-edit { color: #bfdbfe; border-color: rgba(59, 130, 246, .35); padding: 5px 7px; line-height: 1; }
.btn-client-edit svg, .btn-node-edit svg { width: 16px; height: 16px; display: block; }
.btn-client-edit:hover, .btn-node-edit:hover { background: rgba(59, 130, 246, .2); }
.edit-modal { position: fixed; inset: 0; z-index: 1000; display: flex; align-items: center; justify-content: center; padding: 20px; }
.edit-modal[hidden] { display: none; }
.edit-modal-backdrop { position: absolute; inset: 0; background: rgba(2, 6, 23, .6); backdrop-filter: blur(4px); }
.edit-modal-card { position: relative; width: min(480px, 100%); background: rgba(30, 41, 59, .97); border: 1px solid var(--border-color); border-radius: 14px; padding: 22px; box-shadow: 0 24px 60px rgba(0, 0, 0, .5); }
.edit-modal-title { font-size: 1rem; font-weight: 700; margin-bottom: 16px; }
.edit-modal-field { margin-bottom: 12px; }
.edit-modal-field label { display: block; font-size: .78rem; color: var(--text-secondary); margin-bottom: 6px; }
.edit-modal-field input, .edit-modal-field select { width: 100%; border: 1px solid var(--border-color); border-radius: 6px; background: rgba(15, 23, 42, 0.9); color: var(--text-primary); padding: 9px 11px; font: inherit; font-size: .85rem; }
.edit-modal-hint { font-size: .74rem; color: var(--text-secondary); margin-top: -4px; margin-bottom: 12px; }
.edit-modal-field select { appearance: auto; }
.edit-modal-actions { display: flex; gap: 8px; justify-content: flex-end; margin-top: 18px; }
.btn-sm.btn-save { border-color: rgba(16, 185, 129, 0.4); background: rgba(16, 185, 129, 0.18); }
.node-management { position: relative; }
.management-error { position: absolute; right: 16px; bottom: 58px; z-index: 100; max-width: calc(100% - 32px); color: #fecaca; border: 1px solid rgba(239, 68, 68, .5); background: rgba(127, 29, 29, .72); backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px); border-radius: 8px; padding: 8px 10px; font-size: .78rem; box-shadow: 0 8px 24px rgba(127, 29, 29, .25); }
@media (max-width: 700px) { .management-grid { grid-template-columns: 1fr; } .management-row { flex-wrap: wrap; } .management-row .btn-sm { width: 100%; } .header-search { width: 100%; order: 3; } }
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
            __SEARCH__
            __AUTH_ACTIONS__
            <div class="status-badge"><span class="dot"></span><span>__STATUS__</span></div>
        </div>
    </div>
__MANAGEMENT__
    <div class="section-header"><span class="chevron">▾</span>🌐 Подписочные ссылки нод<span class="line"></span></div>
    <div class="cards-grid">
__NODES__
    </div>
__SECTIONS__
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
const NODES_DATA = __NODES_JSON__;
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
    const old = btn.textContent;
    btn.textContent = '…';
    btn.disabled = true;
    Promise.resolve(editModalState.save())
        .then(() => location.reload())
        .catch(err => {
            btn.textContent = err.message || 'Ошибка';
            btn.disabled = false;
            setTimeout(() => { btn.textContent = old; btn.disabled = false; }, 2500);
        });
});
function filterCards() {
    const query = (document.getElementById('client-search')?.value || '').trim().toLocaleLowerCase();
    document.querySelectorAll('.card').forEach(card => {
        const text = (card.dataset.search || '').toLocaleLowerCase();
        card.style.display = !query || text.includes(query) ? '' : 'none';
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
            + '<div class="edit-modal-hint">Схему (http:// или https://) можно не указывать — https:// добавится автоматически.</div>';
        openEditModal('Редактировать ноду · ' + node.name, body, {
            save: () => submitManagement('__API_NODE__', {
                action: 'edit',
                node: node.id,
                name: document.getElementById('edit-node-name').value.trim(),
                url: document.getElementById('edit-node-url').value.trim()
            })
        });
        return;
    }
    const editClient = e.target.closest('.btn-client-edit');
    if (editClient) {
        const client = editClient.dataset.client;
        const curNode = (NODES_DATA || []).find(n => (n.clients || []).includes(client));
        const opts = (NODES_DATA || []).map(n =>
            '<option value="' + escAttr(n.id) + '"' + (curNode && n.id === curNode.id ? ' selected' : '') + '>' + escAttr(n.name) + '</option>'
        ).join('');
        const forceOpt = curNode ? '' : '<option value="">Кастом (force-subs)</option>';
        const body = ''
            + '<div class="edit-modal-field"><label>Имя клиента</label><input id="edit-client-name" value="' + escAttr(client) + '"></div>'
            + '<div class="edit-modal-field"><label>Нода</label><select id="edit-client-node">' + opts + forceOpt + '</select></div>';
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
        const open = el.classList.toggle('open');
        document.querySelectorAll('.btn-qr[data-target="' + sel + '"]').forEach(b => {
            b.textContent = 'QR';
            b.classList.toggle('active', open);
        });
    }
});
document.getElementById('client-search')?.addEventListener('input', filterCards);
document.querySelector('.node-select-trigger')?.addEventListener('click', function () {
    document.getElementById('node-select').classList.toggle('open');
});
document.querySelectorAll('.node-select-option').forEach(option => option.addEventListener('click', function () {
    document.getElementById('client-node').value = this.dataset.value;
    document.getElementById('client-node-label').textContent = this.textContent;
    document.querySelectorAll('.node-select-option').forEach(item => item.classList.toggle('selected', item === this));
    document.getElementById('node-select').classList.remove('open');
}));
document.addEventListener('click', function (e) {
    const picker = document.getElementById('node-select');
    if (picker && !picker.contains(e.target)) picker.classList.remove('open');
});
document.getElementById('add-client-form')?.addEventListener('submit', function (e) {
    e.preventDefault();
    submitManagement('__API_CLIENT__', { action: 'add', node: document.getElementById('client-node').value, client: document.getElementById('new-client').value.trim() })
        .then(() => location.reload()).catch(showManagementError);
});
document.getElementById('add-node-form')?.addEventListener('submit', function (e) {
    e.preventDefault();
    submitManagement('__API_NODE__', { action: 'add', name: document.getElementById('new-node-name').value.trim(), url: document.getElementById('new-node-url').value.trim() })
        .then(() => location.reload()).catch(showManagementError);
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


def default_nodes(subs):
    nodes = []
    for node_id, name, url, group in (
        ("proxy", GROUP_LABELS["proxy"], RUSSIAN_SUB_URL, "proxy"),
        ("freedom", GROUP_LABELS["freedom"], FOREIGN_SUB_URL, "freedom"),
    ):
        url = url.rstrip("/")
        if url and not url.startswith(("http://", "https://")):
            url = "https://" + url
        if url or subs[group]:
            nodes.append({"id": node_id, "name": name, "url": url, "clients": list(subs[group])})
    return nodes


def load_nodes(path, subs):
    if not os.path.exists(path):
        return default_nodes(subs)
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as exc:
        log.warning("failed to load %s: %s; using legacy node configuration", path, exc)
        return default_nodes(subs)
    if not isinstance(data, list):
        return default_nodes(subs)
    result = []
    for item in data:
        if not isinstance(item, dict) or not item.get("id") or not item.get("name") or not item.get("url"):
            continue
        clients = item.get("clients", [])
        if not isinstance(clients, list):
            clients = []
        url = str(item["url"]).strip().rstrip("/")
        if url and not url.startswith(("http://", "https://")):
            url = "https://" + url
        result.append({
            "id": str(item["id"]),
            "name": str(item["name"]).strip(),
            "url": url,
            "clients": [str(client).strip() for client in clients if str(client).strip()],
        })
    return result or default_nodes(subs)


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

    LEGACY: remove this migration and the environment fallback one month
    after the commit that introduced nodes.json, once existing deployments
    have had time to migrate.

    setup.sh creates nodes.json with ``touch`` for new installations. Treat
    that empty file as a legacy configuration that should be migrated from
    the environment-backed node URLs.
    """
    if not os.path.exists(path):
        return True
    try:
        with open(path, encoding="utf-8") as f:
            return not f.read().strip()
    except OSError:
        return False


def all_clients():
    return {client for node in NODES for client in node["clients"]}


def find_client_node(client):
    return next((node for node in NODES if client in node["clients"]), None)


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
        node = find_client_node(client)
        if not node:
            log.warning("404 unknown client: %s", client)
            self.send_error(404)
            return
        base_url = node["url"]
        group = node["id"]
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
        }
        if path not in api_paths:
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

        if path == f"{SECRET_SUB_PATH}/api/client":
            action = (data.get("action") or "").strip()
            client = (data.get("client") or "").strip()
            if not client or any(char in client for char in "\r\n:/"):
                self._send_json(400, {"ok": False, "error": "некорректное имя клиента"})
                return
            if action == "add":
                node = next((item for item in NODES if item["id"] == (data.get("node") or "")), None)
                if not node:
                    self._send_json(400, {"ok": False, "error": "нода не найдена"})
                    return
                if client in all_clients() or client in FORCE_SUBS:
                    self._send_json(400, {"ok": False, "error": "клиент с таким именем уже существует"})
                    return
                node["clients"].append(client)
            elif action == "delete":
                node = find_client_node(client)
                if not node:
                    self._send_json(400, {"ok": False, "error": "клиент не найден"})
                    return
                node["clients"].remove(client)
                if client in FORCE_SUBS:
                    new_force = dict(FORCE_SUBS)
                    new_force.pop(client, None)
                    try:
                        save_force_subs(new_force)
                    except OSError as exc:
                        self._send_json(500, {"ok": False, "error": f"не удалось удалить override: {exc}"})
                        return
                    FORCE_SUBS = new_force
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
                if new_name != client and (new_name in all_clients() or new_name in FORCE_SUBS):
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
                if cur_node:
                    cur_node["clients"].remove(client)
                if target_node:
                    target_node["clients"].append(new_name)
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
                NODES.append({"id": uuid.uuid4().hex, "name": name, "url": url, "clients": []})
            elif action == "delete":
                node_id = (data.get("node") or "").strip()
                node = next((item for item in NODES if item["id"] == node_id), None)
                if not node:
                    self._send_json(400, {"ok": False, "error": "нода не найдена"})
                    return
                if node["clients"]:
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
        scheme = self.headers.get("X-Forwarded-Proto", "http").split(",")[0].strip().lower()
        if scheme not in ("http", "https"):
            scheme = "http"
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
                f'<span class="client-name-badge">🌐 {esc(node["name"])}</span>'
                f'<span style="display:flex;gap:6px;align-items:center">'
                f'<span class="group-badge">база подписки</span>'
                f'<button type="button" class="btn-sm btn-node-edit" data-node="{esc(node["id"])}" title="Редактировать ноду" aria-label="Редактировать ноду">'
                '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z"/></svg></button>'
                f'<button type="button" class="btn-sm btn-node-delete" data-node="{esc(node["id"])}" title="Удалить ноду" aria-label="Удалить ноду">'
                '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6l-1 14H6L5 6m3 0V4h8v2"></path><line x1="10" y1="11" x2="10" y2="17"></line><line x1="14" y1="11" x2="14" y2="17"></line></svg></button></span></div>'
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
        for node in NODES:
            clients = node["clients"]
            if not clients:
                continue
            cards = []
            for client in clients:
                cards.append(self._card_html(client, node, base, idx))
                seen.add(client)
                idx += 1
            sections.append(self._section_html(f'👤 Карточки клиентов · {html.escape(node["name"])}', "\n".join(cards)))
        force_clients = [c for c in sorted(FORCE_SUBS) if c not in seen]
        if force_clients:
            cards = []
            for client in force_clients:
                cards.append(self._card_html(client, None, base, idx))
                idx += 1
            sections.append(self._section_html("👤 Карточки клиентов · Кастом (force-subs.yml)", "\n".join(cards)))
        return "\n".join(sections)

    def _section_html(self, title, cards):
        return (
            f'<div class="section-header" role="button" tabindex="0">'
            f'<span class="chevron">▾</span>{title}<span class="line"></span></div>'
            f'<div class="cards-grid stacked">\n{cards}\n    </div>'
        )

    def _card_html(self, client, node, base, idx):
        esc = html.escape
        force = client in FORCE_SUBS
        sub_url = f"{base}/{SECRET_SUB_PATH}/{client}" if base else f"/{SECRET_SUB_PATH}/{client}"
        direct_url = f'{node["url"]}/{client}' if node else None

        force_tag = '<span class="force-tag">⚡ override</span>' if force else ""
        qr_panel_id = f"qr-panel-{idx}"

        search_text = f'{client} {node["name"]}' if node else client
        p = [f'<div class="card" data-search="{esc(search_text)}">']
        p.append(
            f'<div class="client-header">'
            f'<span class="client-name-badge">👤 {esc(client)}</span>'
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
            if not node:
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
        total = len(all_clients()) + len([c for c in FORCE_SUBS if c not in all_clients()])
        options = "".join(
            f'<div class="node-select-option" data-value="{html.escape(node["id"], quote=True)}">{html.escape(node["name"])}</div>'
            for node in NODES
        )
        first_node = NODES[0] if NODES else None
        node_picker = (
            f'<div class="node-select" id="node-select">'
            f'<input type="hidden" id="client-node" value="{html.escape(first_node["id"], quote=True) if first_node else ""}">'
            f'<button type="button" class="node-select-trigger"><span id="client-node-label">{html.escape(first_node["name"]) if first_node else "Нет доступных нод"}</span><span class="node-select-arrow">⌄</span></button>'
            f'<div class="node-select-options">{options}</div></div>'
        )
        management = (
            '<div class="management-grid">'
            '<div class="management-panel"><div class="management-title">Добавить клиента</div>'
            f'<form class="management-row" id="add-client-form">{node_picker}<input id="new-client" placeholder="Имя нового клиента" required><button class="btn-sm" type="submit">Добавить</button></form></div>'
            '<div class="management-panel node-management"><div class="management-title">Добавить ноду</div>'
            '<form class="management-row" id="add-node-form"><input id="new-node-name" placeholder="Имя ноды" required><input id="new-node-url" placeholder="node.example/subs" required><button class="btn-sm" type="submit">Добавить</button></form>'
            '<div id="management-message" class="management-error" hidden></div></div></div>'
        )
        status = f"Клиентов: {total}"
        body = (
            PAGE_TEMPLATE.replace("__SECTIONS__", sections)
            .replace("__NODES__", nodes)
            .replace("__MANAGEMENT__", management)
            .replace("__SEARCH__", '<input id="client-search" class="header-search" placeholder="поиск" aria-label="поиск">')
            .replace("__STATUS__", status)
            .replace("__RAW_URL__", f"/{SECRET_SUB_PATH}?raw=1")
            .replace("__AUTH_ACTIONS__", f'<a class="btn-logout" href="/{SECRET_SUB_PATH}/logout">Выйти</a>' if ADMIN_USER and ADMIN_PASSWORD else "")
            .replace("__API_OVERRIDE__", f"/{SECRET_SUB_PATH}/api/override")
            .replace("__API_CLIENT__", f"/{SECRET_SUB_PATH}/api/client")
            .replace("__API_NODE__", f"/{SECRET_SUB_PATH}/api/node")
            .replace("__NODES_JSON__", json.dumps(NODES, ensure_ascii=False).replace("</", "<\\/"))
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
        for node in NODES:
            for client in node["clients"]:
                if node["url"]:
                    lines.append(f"{node['url']}/{client}")
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
    global SUBS, FORCE_SUBS, NODES
    SUBS = load_subs(DATABASE_FILE)
    FORCE_SUBS = load_force_subs(FORCE_FILE)
    migrate_nodes = nodes_file_is_empty(NODES_FILE)
    NODES = load_nodes(NODES_FILE, SUBS)
    if migrate_nodes:
        try:
            save_nodes()
            log.info("migrated node configuration from environment to %s", NODES_FILE)
        except OSError as exc:
            log.warning("could not persist initial node configuration: %s", exc)
    log.info("listening on %s:%s, path prefix /%s, db %s", HOST, PORT, SECRET_SUB_PATH, DATABASE_FILE)
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
