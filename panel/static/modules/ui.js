
// ==========================================
// Custom UI Toast & Dialog System
// ==========================================
function escapeHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

function showToast(message, type = 'info', duration = 3500) {
    let container = document.getElementById('toastContainer');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toastContainer';
        container.className = 'toast-container';
        document.body.appendChild(container);
    }

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;

    const icons = {
        success: '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon"><polyline points="20 6 9 17 4 12"/></svg>',
        error: '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>',
        danger: '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>',
        warning: '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>',
        info: '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>'
    };

    const iconStr = icons[type] || '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>';

    toast.innerHTML = `
        <div class="toast-icon">${iconStr}</div>
        <div class="toast-message">${escapeHtml(message)}</div>
        <button type="button" class="toast-close">&times;</button>
    `;

    container.appendChild(toast);

    requestAnimationFrame(() => {
        toast.classList.add('toast-show');
    });

    const removeToast = () => {
        toast.classList.remove('toast-show');
        toast.classList.add('toast-hide');
        toast.addEventListener('transitionend', () => {
            if (toast.parentNode) toast.parentNode.removeChild(toast);
        });
    };

    const timer = setTimeout(removeToast, duration);

    toast.querySelector('.toast-close').addEventListener('click', () => {
        clearTimeout(timer);
        removeToast();
    });
}

let activeModalResolve = null;

function showConfirm(message, title = 'Подтверждение', options = {}) {
    return new Promise((resolve) => {
        const modal = document.getElementById('customConfirmModal');
        const titleEl = document.getElementById('customModalTitle');
        const msgEl = document.getElementById('customModalMessage');
        const iconWrapper = document.getElementById('customModalIconWrapper');
        const iconEl = document.getElementById('customModalIcon');
        const confirmBtn = document.getElementById('customModalConfirmBtn');
        const cancelBtn = document.getElementById('customModalCancelBtn');

        

        if (activeModalResolve) {
            activeModalResolve(false);
            activeModalResolve = null;
        }

        activeModalResolve = resolve;

        const {
            confirmText = 'Подтвердить',
            cancelText = 'Отмена',
            danger = false,
            type = danger ? 'danger' : 'info',
            icon = danger ? '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>' : (options.icon || '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon"><circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>'),
            hideCancel = false
        } = options;

        titleEl.textContent = title;
        msgEl.innerHTML = message;
        iconEl.innerHTML = icon;
        confirmBtn.textContent = confirmText;
        cancelBtn.textContent = cancelText;

        cancelBtn.style.display = hideCancel ? 'none' : 'inline-flex';

        iconWrapper.className = `custom-modal-icon-wrapper ${type}`;

        if (danger) {
            confirmBtn.className = 'btn btn-danger-action';
        } else {
            confirmBtn.className = 'btn btn-primary';
        }

        const cleanup = (result) => {
            modal.classList.remove('active');
            confirmBtn.removeEventListener('click', onConfirm);
            cancelBtn.removeEventListener('click', onCancel);
            document.removeEventListener('keydown', onKeyDown);
            modal.removeEventListener('click', onOverlayClick);
            if (activeModalResolve === resolve) {
                activeModalResolve = null;
                resolve(result);
            }
        };

        const onConfirm = () => cleanup(true);
        const onCancel = () => cleanup(false);
        const onOverlayClick = (e) => {
            if (e.target === modal) cleanup(false);
        };

        const onKeyDown = (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                cleanup(true);
            } else if (e.key === 'Escape') {
                e.preventDefault();
                cleanup(false);
            }
        };

        confirmBtn.addEventListener('click', onConfirm);
        cancelBtn.addEventListener('click', onCancel);
        modal.addEventListener('click', onOverlayClick);
        document.addEventListener('keydown', onKeyDown);

        modal.classList.add('active');
        setTimeout(() => confirmBtn.focus(), 50);
    });
}

function showAlert(message, title = 'Уведомление', type = 'info') {
    return showConfirm(message, title, {
        confirmText: 'ОК',
        hideCancel: true,
        type: type,
        icon: type === 'success' ? '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon"><polyline points="20 6 9 17 4 12"/></svg>' : (type === 'error' ? '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>' : '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>')
    });
}

window.showToast = showToast;
window.showAlert = showAlert;
window.showConfirm = showConfirm;

// ==========================================
// Secret Phrase MD5 Hash Derivation Helpers
// ==========================================
function md5(string) {
    var bytes = typeof string === 'string' ? new TextEncoder().encode(string) : string;
    var len = bytes.length;
    var nWords = (((len + 8) >>> 6) + 1) * 16;
    var words = new Uint32Array(nWords);
    for (var i = 0; i < len; i++) {
        words[i >>> 2] |= bytes[i] << ((i % 4) * 8);
    }
    words[len >>> 2] |= 0x80 << ((len % 4) * 8);
    words[nWords - 2] = (len * 8) & 0xffffffff;
    words[nWords - 1] = Math.floor((len * 8) / 0x100000000);

    function rotateLeft(lValue, iShiftBits) {
        return (lValue << iShiftBits) | (lValue >>> (32 - iShiftBits));
    }
    function cmn(q, a, b, x, s, t) {
        a = (a + q + x + t) | 0;
        return (rotateLeft(a, s) + b) | 0;
    }
    function ff(a, b, c, d, x, s, t) { return cmn((b & c) | (~b & d), a, b, x, s, t); }
    function gg(a, b, c, d, x, s, t) { return cmn((b & d) | (c & ~d), a, b, x, s, t); }
    function hh(a, b, c, d, x, s, t) { return cmn(b ^ c ^ d, a, b, x, s, t); }
    function ii(a, b, c, d, x, s, t) { return cmn(c ^ (b | ~d), a, b, x, s, t); }

    var a = 0x67452301, b = 0xefcdab89, c = 0x98badcfe, d = 0x10325476;
    for (var i = 0; i < nWords; i += 16) {
        var aa = a, bb = b, cc = c, dd = d;

        a = ff(a, b, c, d, words[i + 0], 7, 0xd76aa478);
        d = ff(d, a, b, c, words[i + 1], 12, 0xe8c7b756);
        c = ff(c, d, a, b, words[i + 2], 17, 0x242070db);
        b = ff(b, c, d, a, words[i + 3], 22, 0xc1bdceee);
        a = ff(a, b, c, d, words[i + 4], 7, 0xf57c0faf);
        d = ff(d, a, b, c, words[i + 5], 12, 0x4787c62a);
        c = ff(c, d, a, b, words[i + 6], 17, 0xa8304613);
        b = ff(b, c, d, a, words[i + 7], 22, 0xfd469501);
        a = ff(a, b, c, d, words[i + 8], 7, 0x698098d8);
        d = ff(d, a, b, c, words[i + 9], 12, 0x8b44f7af);
        c = ff(c, d, a, b, words[i + 10], 17, 0xffff5bb1);
        b = ff(b, c, d, a, words[i + 11], 22, 0x895cd7be);
        a = ff(a, b, c, d, words[i + 12], 7, 0x6b901122);
        d = ff(d, a, b, c, words[i + 13], 12, 0xfd987193);
        c = ff(c, d, a, b, words[i + 14], 17, 0xa679438e);
        b = ff(b, c, d, a, words[i + 15], 22, 0x49b40821);

        a = gg(a, b, c, d, words[i + 1], 5, 0xf61e2562);
        d = gg(d, a, b, c, words[i + 6], 9, 0xc040b340);
        c = gg(c, d, a, b, words[i + 11], 14, 0x265e5a51);
        b = gg(b, c, d, a, words[i + 0], 20, 0xe9b6c7aa);
        a = gg(a, b, c, d, words[i + 5], 5, 0xd62f105d);
        d = gg(d, a, b, c, words[i + 10], 9, 0x02441453);
        c = gg(c, d, a, b, words[i + 15], 14, 0xd8a1e681);
        b = gg(b, c, d, a, words[i + 4], 20, 0xe7d3fbc8);
        a = gg(a, b, c, d, words[i + 9], 5, 0x21e1cde6);
        d = gg(d, a, b, c, words[i + 14], 9, 0xc33707d6);
        c = gg(c, d, a, b, words[i + 3], 14, 0xf4d50d87);
        b = gg(b, c, d, a, words[i + 8], 20, 0x455a14ed);
        a = gg(a, b, c, d, words[i + 13], 5, 0xa9e3e905);
        d = gg(d, a, b, c, words[i + 2], 9, 0xfcefa3f8);
        c = gg(c, d, a, b, words[i + 7], 14, 0x676f02d9);
        b = gg(b, c, d, a, words[i + 12], 20, 0x8d2a4c8a);

        a = hh(a, b, c, d, words[i + 5], 4, 0xfffa3942);
        d = hh(d, a, b, c, words[i + 8], 11, 0x8771f681);
        c = hh(c, d, a, b, words[i + 11], 16, 0x6d9d6122);
        b = hh(b, c, d, a, words[i + 14], 23, 0xfde5380c);
        a = hh(a, b, c, d, words[i + 1], 4, 0xa4beea44);
        d = hh(d, a, b, c, words[i + 4], 11, 0x4bdecfa9);
        c = hh(c, d, a, b, words[i + 7], 16, 0xf6bb4b60);
        b = hh(b, c, d, a, words[i + 10], 23, 0xbebfbc70);
        a = hh(a, b, c, d, words[i + 13], 4, 0x289b7ec6);
        d = hh(d, a, b, c, words[i + 0], 11, 0xeaa127fa);
        c = hh(c, d, a, b, words[i + 3], 16, 0xd4ef3085);
        b = hh(b, c, d, a, words[i + 6], 23, 0x04881d05);
        a = hh(a, b, c, d, words[i + 9], 4, 0xd9d4d039);
        d = hh(d, a, b, c, words[i + 12], 11, 0xe6db99e5);
        c = hh(c, d, a, b, words[i + 15], 16, 0x1fa27cf8);
        b = hh(b, c, d, a, words[i + 2], 23, 0xc4ac5665);

        a = ii(a, b, c, d, words[i + 0], 6, 0xf4292244);
        d = ii(d, a, b, c, words[i + 7], 10, 0x432aff97);
        c = ii(c, d, a, b, words[i + 14], 15, 0xab9423a7);
        b = ii(b, c, d, a, words[i + 5], 21, 0xfc93a039);
        a = ii(a, b, c, d, words[i + 12], 6, 0x655b59c3);
        d = ii(d, a, b, c, words[i + 3], 10, 0x8f0ccc92);
        c = ii(c, d, a, b, words[i + 10], 15, 0xffeff47d);
        b = ii(b, c, d, a, words[i + 1], 21, 0x85845dd1);
        a = ii(a, b, c, d, words[i + 8], 6, 0x6fa87e4f);
        d = ii(d, a, b, c, words[i + 15], 10, 0xfe2ce6e0);
        c = ii(c, d, a, b, words[i + 6], 15, 0xa3014314);
        b = ii(b, c, d, a, words[i + 13], 21, 0x4e0811a1);
        a = ii(a, b, c, d, words[i + 4], 6, 0xf7537e82);
        d = ii(d, a, b, c, words[i + 11], 10, 0xbd3af235);
        c = ii(c, d, a, b, words[i + 2], 15, 0x2ad7d2bb);
        b = ii(b, c, d, a, words[i + 9], 21, 0xeb86d391);

        a = (a + aa) | 0;
        b = (b + bb) | 0;
        c = (c + cc) | 0;
        d = (d + dd) | 0;
    }

    function hex(n) {
        var s = '';
        for (var j = 0; j < 4; j++) {
            var b = (n >>> (j * 8)) & 0xff;
            s += (b < 16 ? '0' : '') + b.toString(16);
        }
        return s;
    }
    return (hex(a) + hex(b) + hex(c) + hex(d)).toLowerCase();
}

function derivePanelPaths(secret) {
    if (!secret || !secret.trim()) return null;
    const s = secret.trim();
    return {
        web: md5(s + '-panel').slice(0, 16),
        sub: md5(s + '-sub').slice(0, 16)
    };
}

function deriveSubServerPath(secret) {
    if (!secret || !secret.trim()) return null;
    const s = secret.trim();
    return md5(s).slice(0, 16);
}
function updateSecretHashPreviews() {
    const updatePreview = (inputId, previewId, isSubServer) => {
        const inputEl = document.getElementById(inputId);
        const previewEl = document.getElementById(previewId);
        if (!inputEl || !previewEl) return;
        const val = inputEl.value.trim();
        if (!val) {
            previewEl.innerHTML = '';
            previewEl.style.display = 'none';
            return;
        }
        if (isSubServer) {
            const p = deriveSubServerPath(val);
            if (!p) {
                previewEl.innerHTML = '';
                previewEl.style.display = 'none';
                return;
            }
            previewEl.style.display = 'inline-flex';
            previewEl.innerHTML = `<span class="hash-label">sub:</span><span class="hash-val">/${p}</span>`;
        } else {
            const paths = derivePanelPaths(val);
            if (!paths) {
                previewEl.innerHTML = '';
                previewEl.style.display = 'none';
                return;
            }
            previewEl.style.display = 'inline-flex';
            previewEl.innerHTML = `<span class="hash-label">панель:</span><span class="hash-val">/${paths.web}</span><span class="hash-sep">•</span><span class="hash-label">sub:</span><span class="hash-val">/${paths.sub}</span>`;
        }
    };

    // 1. Single / Freedom / Proxy panel sub_secret
    updatePreview('sub_secret', 'sub_secret_preview', false);

    // 2. Freedom sub_secret (Cascade)
    updatePreview('freedom_sub_secret', 'freedom_sub_secret_preview', false);

    // 3. Proxy sub_secret (Cascade)
    updatePreview('proxy_sub_secret', 'proxy_sub_secret_preview', false);

    // 4. Sub-Server sub_secret_path
    updatePreview('sub_secret_path', 'sub_secret_path_preview', true);
}


function copyToClipboard(text, btnEl) {
    navigator.clipboard.writeText(text).then(() => {
        const origText = btnEl.textContent;
        btnEl.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon text-success"><path d="M20 6L9 17l-5-5"/></svg>';
        setTimeout(() => { btnEl.textContent = origText; }, 2000);
    }).catch(() => {
        const btnCopyLogs = document.getElementById('btnCopyLogs');
        if (btnCopyLogs) {
            btnCopyLogs.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon text-danger"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg> Ошибка';
            setTimeout(() => { btnCopyLogs.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg> Копировать лог'; }, 2000);
        }
    });
}

async function fetchBackupList(folder = 'backups_panel') {
    try {
        const res = await fetch(`/api/backups?folder=${encodeURIComponent(folder)}`);
        if (!res.ok) return;
        const files = await res.json();
        const targets = [
            {
                selectId: 'recovery_backup_file',
                selectedId: 'recoveryBackupSelected',
                dropdownId: 'recoveryBackupDropdown'
            },
            {
                selectId: 'rollback_sub_backup_file',
                selectedId: 'rollbackSubBackupSelected',
                dropdownId: 'rollbackSubBackupDropdown'
            }
        ];
        targets.forEach(({ selectId, selectedId, dropdownId }) => {
            const select = document.getElementById(selectId);
            const selectedSpan = document.getElementById(selectedId);
            const dropdown = document.getElementById(dropdownId);
            if (!select || !selectedSpan || !dropdown) return;
            select.innerHTML = '<option value="">-- Выберите архив --</option>';
            dropdown.innerHTML = '';
            if (!files || files.length === 0) {
                selectedSpan.innerHTML = `Архивы бэкапов не найдены в ./${folder}/`;
                dropdown.innerHTML = `<div class="custom-select-option text-muted" style="padding:10px; color:#94a3b8;">Архивы не найдены в ./${folder}/</div>`;
                return;
            }
            files.forEach((f) => {
                const opt = document.createElement('option');
                opt.value = f.name;
                opt.textContent = `${f.name} (${f.size}, ${f.mtime})`;
                select.appendChild(opt);
                const div = document.createElement('div');
                div.className = 'custom-select-option';
                div.style.cssText = 'padding: 10px 14px; cursor: pointer; border-bottom: 1px solid rgba(255,255,255,0.05); display: flex; justify-content: space-between; align-items: center;';
                div.innerHTML = `<div><strong><svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon"><line x1="16.5" y1="9.4" x2="7.5" y2="4.21"/><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/></svg> ${f.name}</strong><br><small style="color:#94a3b8">${f.mtime}</small></div><span class="badge" style="background:rgba(59,130,246,0.2); color:#60a5fa; padding:2px 8px; border-radius:4px; font-size:0.8rem;">${f.size}</span>`;
                div.addEventListener('click', () => {
                    select.value = f.name;
                    selectedSpan.innerHTML = `${f.name} (${f.size})`;
                    dropdown.classList.add('hidden');
                    document.querySelectorAll(`#${dropdownId} .custom-select-option`).forEach(el => el.classList.remove('selected'));
                    div.classList.add('selected');
                });
                dropdown.appendChild(div);
            });
            if (files.length > 0 && !select.value) {
                select.value = files[0].name;
                selectedSpan.textContent = `${files[0].name} (${files[0].size})`;
                if (dropdown.children[0]) dropdown.children[0].classList.add('selected');
            }
        });
    } catch (e) {
        console.error('Failed to fetch backup list', e);
    }
}

// QR modal (verbatim from app.js)
    const qrModal = document.getElementById('qrModal');
    const qrModalImg = document.getElementById('qrModalImg');
    const qrModalTitle = document.getElementById('qrModalTitle');
    const qrModalUrl = document.getElementById('qrModalUrl');
    const btnCloseQr = document.getElementById('btnCloseQr');


    const recTrigger = document.getElementById('recoveryBackupTrigger');
    const recDropdown = document.getElementById('recoveryBackupDropdown');
    if (recTrigger && recDropdown) {
        recTrigger.addEventListener('click', (e) => {
            e.stopPropagation();
            recDropdown.classList.toggle('hidden');
        });
    }

    const rollbackSubTrigger = document.getElementById('rollbackSubBackupTrigger');
    const rollbackSubDropdown = document.getElementById('rollbackSubBackupDropdown');
    if (rollbackSubTrigger && rollbackSubDropdown) {
        rollbackSubTrigger.addEventListener('click', (e) => {
            e.stopPropagation();
            rollbackSubDropdown.classList.toggle('hidden');
        });
    }

    document.addEventListener('click', () => {
        const recDr = document.getElementById('recoveryBackupDropdown');
        if (recDr) recDr.classList.add('hidden');
        const rollDr = document.getElementById('rollbackSubBackupDropdown');
        if (rollDr) rollDr.classList.add('hidden');
    });

    const hideQrModal = () => {
        if (qrModal) qrModal.classList.remove('active');
    };

    if (btnCloseQr) btnCloseQr.addEventListener('click', hideQrModal);

    if (qrModal) {
        qrModal.addEventListener('click', (e) => {
            if (e.target === qrModal) {
                hideQrModal();
            }
        });
    }

    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && qrModal.classList.contains('active')) {
            hideQrModal();
        }
    });

    const showQrModal = (title, url) => {
        qrModalTitle.textContent = title;
        qrModalUrl.textContent = url;
        if (typeof qrcode !== 'undefined' && qrcode.generateSvgDataUrl) {
            try {
                qrModalImg.src = qrcode.generateSvgDataUrl(url, 6, 3);
            } catch (e) {
                console.error('QR generation error:', e);
            }
        }
        qrModal.classList.add('active');
    };


window.showQrModal = showQrModal;
window.hideQrModal = hideQrModal;

// Changelog & Happ Routing modals (verbatim from app.js)
    const changelogModal = document.getElementById('changelogModal');
    const changelogContent = document.getElementById('changelogContent');
    const btnCloseChangelog = document.getElementById('btnCloseChangelog');
    const btnDismissChangelogModal = document.getElementById('btnDismissChangelogModal');

    const showChangelogModal = (text) => {
        if (!changelogModal || !changelogContent) return;
        changelogContent.textContent = text || 'Нет новых записей в change.log относительно текущей версии.';
        changelogModal.classList.add('active');
    };

    const hideChangelogModal = () => {
        if (changelogModal) changelogModal.classList.remove('active');
    };

    if (btnCloseChangelog) btnCloseChangelog.addEventListener('click', hideChangelogModal);
    if (btnDismissChangelogModal) btnDismissChangelogModal.addEventListener('click', hideChangelogModal);
    if (changelogModal) {
        changelogModal.addEventListener('click', (e) => {
            if (e.target === changelogModal) hideChangelogModal();
        });
    }
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && changelogModal && changelogModal.classList.contains('active')) {
            hideChangelogModal();
        }
    });

    // --- Happ Routing Modal & Editor ---
    const happRoutingModal = document.getElementById('happRoutingModal');
    const happRoutingEditor = document.getElementById('happRoutingEditor');
    const happRoutingStatus = document.getElementById('happRoutingStatus');
    const btnOpenHappRoutingModal = document.getElementById('btnOpenHappRoutingModal');
    const btnCloseHappRoutingModal = document.getElementById('btnCloseHappRoutingModal');
    const btnCancelHappRoutingModal = document.getElementById('btnCancelHappRoutingModal');
    const btnSaveHappRoutingModal = document.getElementById('btnSaveHappRoutingModal');
    const btnFormatHappRouting = document.getElementById('btnFormatHappRouting');

    const showHappRoutingModal = async () => {
        if (!happRoutingModal || !happRoutingEditor) return;
        if (happRoutingStatus) {
            happRoutingStatus.textContent = '';
            happRoutingStatus.classList.add('hidden');
        }
        happRoutingEditor.value = 'Загрузка happ-routing.json...';
        happRoutingModal.classList.add('active');

        try {
            const res = await fetch('/api/happ_routing', { cache: 'no-store' });
            if (res.ok) {
                const data = await res.json();
                if (data.ok && data.content) {
                    try {
                        const parsed = JSON.parse(data.content);
                        happRoutingEditor.value = JSON.stringify(parsed, null, 4);
                    } catch {
                        happRoutingEditor.value = data.content;
                    }
                } else {
                    happRoutingEditor.value = '';
                    if (happRoutingStatus) {
                        happRoutingStatus.textContent = data.error || 'Не удалось загрузить happ-routing.json';
                        happRoutingStatus.classList.remove('hidden');
                    }
                }
            } else {
                if (happRoutingStatus) {
                    happRoutingStatus.textContent = 'Ошибка сервера при загрузке happ-routing.json';
                    happRoutingStatus.classList.remove('hidden');
                }
            }
        } catch (err) {
            if (happRoutingStatus) {
                happRoutingStatus.textContent = 'Ошибка сети: ' + err.message;
                happRoutingStatus.classList.remove('hidden');
            }
        }
    };

    const hideHappRoutingModal = () => {
        if (happRoutingModal) happRoutingModal.classList.remove('active');
    };

    if (btnOpenHappRoutingModal) btnOpenHappRoutingModal.addEventListener('click', showHappRoutingModal);
    if (btnCloseHappRoutingModal) btnCloseHappRoutingModal.addEventListener('click', hideHappRoutingModal);
    if (btnCancelHappRoutingModal) btnCancelHappRoutingModal.addEventListener('click', hideHappRoutingModal);
    if (happRoutingModal) {
        happRoutingModal.addEventListener('click', (e) => {
            if (e.target === happRoutingModal) hideHappRoutingModal();
        });
    }
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && happRoutingModal && happRoutingModal.classList.contains('active')) {
            hideHappRoutingModal();
        }
    });

    if (btnFormatHappRouting) {
        btnFormatHappRouting.addEventListener('click', () => {
            if (!happRoutingEditor) return;
            try {
                const val = happRoutingEditor.value.trim();
                if (!val) return;
                const parsed = JSON.parse(val);
                happRoutingEditor.value = JSON.stringify(parsed, null, 4);
                if (happRoutingStatus) {
                    happRoutingStatus.textContent = '';
                    happRoutingStatus.classList.add('hidden');
                }
                showToast('JSON успешно отформатирован', 'info', 2000);
            } catch (err) {
                if (happRoutingStatus) {
                    happRoutingStatus.textContent = 'Синтаксическая ошибка JSON: ' + err.message;
                    happRoutingStatus.classList.remove('hidden');
                }
            }
        });
    }

    if (btnSaveHappRoutingModal) {
        btnSaveHappRoutingModal.addEventListener('click', async () => {
            if (!happRoutingEditor) return;
            const content = happRoutingEditor.value.trim();
            if (!content) {
                if (happRoutingStatus) {
                    happRoutingStatus.textContent = 'Контент не может быть пустым';
                    happRoutingStatus.classList.remove('hidden');
                }
                return;
            }

            try {
                JSON.parse(content);
            } catch (err) {
                if (happRoutingStatus) {
                    happRoutingStatus.textContent = 'Синтаксическая ошибка JSON: ' + err.message;
                    happRoutingStatus.classList.remove('hidden');
                }
                return;
            }

            if (happRoutingStatus) {
                happRoutingStatus.textContent = '';
                happRoutingStatus.classList.add('hidden');
            }

            btnSaveHappRoutingModal.disabled = true;
            btnSaveHappRoutingModal.textContent = 'Сохранение...';

            try {
                const res = await fetch('/api/happ_routing', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ content })
                });
                const data = await res.json();
                if (data.ok) {
                    if (data.content) {
                        happRoutingEditor.value = data.content;
                    }
                    showToast('happ-routing.json успешно сохранен!', 'success');
                    hideHappRoutingModal();
                } else {
                    if (happRoutingStatus) {
                        happRoutingStatus.textContent = 'Ошибка сохранения: ' + (data.error || 'Неизвестная ошибка');
                        happRoutingStatus.classList.remove('hidden');
                    }
                }
            } catch (err) {
                if (happRoutingStatus) {
                    happRoutingStatus.textContent = 'Ошибка сети: ' + err.message;
                    happRoutingStatus.classList.remove('hidden');
                }
            } finally {
                btnSaveHappRoutingModal.disabled = false;
                btnSaveHappRoutingModal.textContent = 'Сохранить';
            }
        });
    }

window.showChangelogModal = showChangelogModal;
window.hideChangelogModal = hideChangelogModal;
window.showHappRoutingModal = showHappRoutingModal;
window.hideHappRoutingModal = hideHappRoutingModal;
