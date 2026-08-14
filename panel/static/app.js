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
        success: '✓',
        error: '✕',
        danger: '✕',
        warning: '⚠️',
        info: 'ℹ️'
    };

    const iconStr = icons[type] || 'ℹ️';

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

        if (!modal || !confirmBtn || !cancelBtn) {
            resolve(window.nativeConfirm ? window.nativeConfirm(message) : true);
            return;
        }

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
            icon = danger ? '⚠️' : (options.icon || '❓'),
            hideCancel = false
        } = options;

        titleEl.textContent = title;
        msgEl.textContent = message;
        iconEl.textContent = icon;
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
        icon: type === 'success' ? '✓' : (type === 'error' ? '✕' : 'ℹ️')
    });
}

window.nativeAlert = window.alert;
window.nativeConfirm = window.confirm;

window.showToast = showToast;
window.showAlert = showAlert;
window.showConfirm = showConfirm;

window.alert = function(msg) {
    if (typeof msg === 'string' && msg.length < 80 && !msg.includes('\n')) {
        showToast(msg, 'info');
    } else {
        showAlert(msg);
    }
};

window.confirm = function(msg) {
    return showConfirm(msg);
};

document.addEventListener('DOMContentLoaded', () => {
    ['category-full', 'category-single', 'category-maintenance'].forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            el.addEventListener('toggle', () => {
                if (window.saveConfig) window.saveConfig();
            });
        }
    });

    const btnTestSSH = document.getElementById('btnTestSSH');
    const btnNext1 = document.getElementById('btnNext1');
    const testResult = document.getElementById('testResult');

    const cascadeNo = document.getElementById('cascade_no');
    const cascadeYes = document.getElementById('cascade_yes');
    const singleNodeSection = document.getElementById('singleNodeSection');
    const cascadeNodeSection = document.getElementById('cascadeNodeSection');

    const passRadio = document.getElementById('auth_type_pass');
    const keyRadio = document.getElementById('auth_type_key');
    const passGroup = document.getElementById('passGroup');
    const keyGroup = document.getElementById('keyGroup');
    const subSameAsProxy = document.getElementById('sub_same_as_proxy');

    const ensureSubAdminFields = () => {
        if (document.getElementById('sub_admin_user') && document.getElementById('sub_admin_password')) return;

        const formGrid = document.querySelector('#subServerPanelSection .form-grid');
        const targetGroup = document.getElementById('subOnlyTargetGroup');
        if (!formGrid) return;

        const userGroup = document.createElement('div');
        userGroup.className = 'form-group';
        userGroup.innerHTML = `
            <label for="sub_admin_user">Логин админа Сервера подписок</label>
            <input type="text" id="sub_admin_user" value="admin" placeholder="admin">
        `;

        const passGroupEl = document.createElement('div');
        passGroupEl.className = 'form-group';
        passGroupEl.innerHTML = `
            <label for="sub_admin_password">Пароль админа Сервера подписок</label>
            <input type="password" id="sub_admin_password" placeholder="admin">
        `;

        if (targetGroup && targetGroup.parentNode === formGrid) {
            formGrid.insertBefore(userGroup, targetGroup);
            formGrid.insertBefore(passGroupEl, targetGroup);
        } else {
            formGrid.appendChild(userGroup);
            formGrid.appendChild(passGroupEl);
        }
    };

    ensureSubAdminFields();

    const qrModal = document.getElementById('qrModal');
    const qrModalImg = document.getElementById('qrModalImg');
    const qrModalTitle = document.getElementById('qrModalTitle');
    const qrModalUrl = document.getElementById('qrModalUrl');
    const btnCloseQr = document.getElementById('btnCloseQr');

    const fetchBackupList = async (folder = 'backups_panel') => {
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
                    selectedSpan.textContent = `Архивы бэкапов не найдены в ./${folder}/`;
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
                    div.innerHTML = `<div><strong>📦 ${f.name}</strong><br><small style="color:#94a3b8">${f.mtime}</small></div><span class="badge" style="background:rgba(59,130,246,0.2); color:#60a5fa; padding:2px 8px; border-radius:4px; font-size:0.8rem;">${f.size}</span>`;
                    div.addEventListener('click', () => {
                        select.value = f.name;
                        selectedSpan.textContent = `${f.name} (${f.size})`;
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
    };

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
        qrModalImg.src = `https://api.qrserver.com/v1/create-qr-code/?data=${encodeURIComponent(url)}&size=250x250`;
        qrModal.classList.add('active');
    };

    const copyToClipboard = (text, btnEl) => {
        navigator.clipboard.writeText(text).then(() => {
            const origText = btnEl.textContent;
            btnEl.textContent = '✅';
            setTimeout(() => { btnEl.textContent = origText; }, 2000);
        }).catch(() => {
            const btnCopyLogs = document.getElementById('btnCopyLogs');
            if (btnCopyLogs) {
                btnCopyLogs.textContent = '❌ Ошибка';
                setTimeout(() => { btnCopyLogs.textContent = '📋 Копировать лог'; }, 2000);
            }
        });
    };

    const updateBadgeStatus = (text, color, pulse = false) => {
        const badge = document.getElementById('statusBadge');
        const textEl = document.getElementById('statusText');
        const dotEl = badge.querySelector('.dot');

        textEl.textContent = text;
        dotEl.style.backgroundColor = color;
        dotEl.style.boxShadow = `0 0 8px ${color}`;
        badge.style.borderColor = color;

        if (pulse) {
            dotEl.classList.add('pulsing');
        } else {
            dotEl.classList.remove('pulsing');
        }
    };

    const getSelectedMode = () => {
        const checked = document.querySelector('input[name="deploy_mode"]:checked');
        return checked ? checked.value : 'cascade';
    };

    const renderTopologyDiagram = (mode) => {
        const diagramEl = document.getElementById('topologyDiagram');
        if (!diagramEl) return;

        let html = '';
        if (mode === 'single') {
            html = `
                <div class="topology-stage">
                    <div class="topology-stage-title">1. Получение подписки</div>
                    <div class="topology-flow">
                        <div class="topology-node">
                            <span class="node-icon">📱</span>
                            <span class="node-title">Клиент</span>
                            <span class="topology-badge topology-badge-ru">🇷🇺</span>
                        </div>
                        <div class="topology-arrow">
                            <span class="arrow-label">Запрос</span>
                            <span class="arrow-label">подписки</span>
                            <span>➔</span>
                        </div>
                        <div class="topology-node configurable">
                            <span class="node-icon">🖧</span>
                            <span class="node-title">VPS Сервер</span>
                            <span class="node-desc">3X-UI Панель</span>
                            <span class="topology-badge topology-badge-configurable">🌐 Зарубежье</span>
                        </div>
                    </div>
                </div>
                <div class="topology-stage">
                    <div class="topology-stage-title">2. Обход блокировок</div>
                    <div class="topology-flow">
                        <div class="topology-node">
                            <span class="node-icon">📱</span>
                            <span class="node-title">Клиент</span>
                            <span class="node-desc">С подпиской</span>
                            <span class="topology-badge topology-badge-ru">🇷🇺</span>
                        </div>
                        <div class="topology-arrow">
                            <span class="arrow-label">VLESS</span>
                            <span>➔</span>
                        </div>
                        <div class="topology-node configurable">
                            <span class="node-icon">🖧</span>
                            <span class="node-title">VPS Сервер</span>
                            <span class="node-desc">3X-UI Панель</span>
                            <span class="topology-badge topology-badge-configurable">🌐 Зарубежье</span>
                        </div>
                        <div class="topology-arrow">
                            <span class="arrow-label">Выход</span>
                            <span class="arrow-label">в сеть</span>
                            <span>➔</span>
                        </div>
                        <div class="topology-node">
                            <span class="node-icon">🌍</span>
                            <span class="node-title">Свободный Web</span>
                        </div>
                    </div>
                </div>
            `;
        } else if (mode === 'proxy_only') {
            html = `
                <div class="topology-stage">
                    <div class="topology-stage-title">Каскадная маршрутизация (Двойной туннель)</div>
                    <div class="topology-flow">
                        <div class="topology-node">
                            <span class="node-icon">📱</span>
                            <span class="node-title">Клиент</span>
                            <span class="node-desc">С подпиской</span>
                            <span class="topology-badge topology-badge-ru">🇷🇺</span>
                        </div>
                        <div class="topology-arrow">
                            <span class="arrow-label">VLESS</span>
                            <span>➔</span>
                        </div>
                        <div class="topology-node configurable">
                            <span class="node-icon">🖧</span>
                            <span class="node-title">Proxy Node</span>
                            <span class="node-desc">Входной сервер</span>
                            <span class="topology-badge topology-badge-configurable">🇷🇺</span>
                        </div>
                        <div class="topology-arrow">
                            <span class="arrow-label">VLESS XHTTP</span>
                            <span>➔</span>
                        </div>
                        <div class="topology-node">
                            <span class="node-icon">🕊️</span>
                            <span class="node-title">Freedom Node</span>
                            <span class="node-desc">Выходной сервер</span>
                            <span class="topology-badge topology-badge-foreign">🌐 Зарубежье</span>
                        </div>
                        <div class="topology-arrow">
                            <span class="arrow-label">Выход</span>
                            <span class="arrow-label">в сеть</span>
                            <span>➔</span>
                        </div>
                        <div class="topology-node">
                            <span class="node-icon">🌍</span>
                            <span class="node-title">Свободный Web</span>
                        </div>
                    </div>
                </div>
            `;
        } else if (mode === 'freedom_only') {
            html = `
                <div class="topology-stage">
                    <div class="topology-stage-title">1. Получение подписки (Прямо с Freedom Node)</div>
                    <div class="topology-flow">
                        <div class="topology-node">
                            <span class="node-icon">📱</span>
                            <span class="node-title">Клиент</span>
                            <span class="topology-badge topology-badge-ru">🇷🇺</span>
                        </div>
                        <div class="topology-arrow">
                            <span class="arrow-label">Запрос</span>
                            <span class="arrow-label">подписки</span>
                            <span>➔</span>
                        </div>
                        <div class="topology-node configurable">
                            <span class="node-icon">🕊️</span>
                            <span class="node-title">Freedom Node</span>
                            <span class="node-desc">Прямое подключение</span>
                            <span class="topology-badge topology-badge-configurable">🌐 Зарубежье</span>
                        </div>
                    </div>
                </div>
                <div class="topology-stage">
                    <div class="topology-stage-title">2. Прямое подключение через зарубежный сервер</div>
                    <div class="topology-flow">
                        <div class="topology-node">
                            <span class="node-icon">📱</span>
                            <span class="node-title">Клиент</span>
                            <span class="node-desc">С подпиской</span>
                            <span class="topology-badge topology-badge-ru">🇷🇺</span>
                        </div>
                        <div class="topology-arrow">
                            <span class="arrow-label">VLESS</span>
                            <span>➔</span>
                        </div>
                        <div class="topology-node configurable">
                            <span class="node-icon">🕊️</span>
                            <span class="node-title">Freedom Node</span>
                            <span class="node-desc">Один сервер</span>
                            <span class="topology-badge topology-badge-configurable">🌐 Зарубежье</span>
                        </div>
                        <div class="topology-arrow">
                            <span class="arrow-label">Выход</span>
                            <span class="arrow-label">в сеть</span>
                            <span>➔</span>
                        </div>
                        <div class="topology-node">
                            <span class="node-icon">🌍</span>
                            <span class="node-title">Свободный Web</span>
                        </div>
                    </div>
                </div>
            `;
        } else if (mode === 'freedom_component') {
            html = `
                <div class="topology-stage">
                    <div class="topology-stage-title">Каскадная маршрутизация (Двойной туннель)</div>
                    <div class="topology-flow">
                        <div class="topology-node">
                            <span class="node-icon">📱</span>
                            <span class="node-title">Клиент</span>
                            <span class="node-desc">С подпиской</span>
                            <span class="topology-badge topology-badge-ru">🇷🇺</span>
                        </div>
                        <div class="topology-arrow">
                            <span class="arrow-label">VLESS</span>
                            <span>➔</span>
                        </div>
                        <div class="topology-node">
                            <span class="node-icon">🖧</span>
                            <span class="node-title">Proxy Node</span>
                            <span class="node-desc">Входной сервер</span>
                            <span class="topology-badge topology-badge-ru">🇷🇺</span>
                        </div>
                        <div class="topology-arrow">
                            <span class="arrow-label">VLESS XHTTP</span>
                            <span>➔</span>
                        </div>
                        <div class="topology-node configurable">
                            <span class="node-icon">🕊️</span>
                            <span class="node-title">Freedom Node</span>
                            <span class="node-desc">Выходной сервер</span>
                            <span class="topology-badge topology-badge-configurable">🌐 Зарубежье</span>
                        </div>
                        <div class="topology-arrow">
                            <span class="arrow-label">Выход</span>
                            <span class="arrow-label">в сеть</span>
                            <span>➔</span>
                        </div>
                        <div class="topology-node">
                            <span class="node-icon">🌍</span>
                            <span class="node-title">Свободный Web</span>
                        </div>
                    </div>
                </div>
            `;
        } else if (mode === 'cascade' || mode === 'cascade_sub') {
            const subTitle = mode === 'cascade_sub' ? '1. Получение единой подписки (Сервер подписок)' : '1. Получение подписки (Прямо с нод)';
            const subNodeHtml = mode === 'cascade_sub' ? `
                <div class="topology-node configurable">
                    <span class="node-icon">📡</span>
                    <span class="node-title">Сервер подписок</span>
                    <span class="node-desc">Caddy Sub-Server</span>
                    <span class="topology-badge topology-badge-configurable">🌐 Зарубежье</span>
                </div>
            ` : `
                <div class="topology-node configurable">
                    <span class="node-icon">🖧</span>
                    <span class="node-title">Proxy Node</span>
                    <span class="node-desc">Входной сервер</span>
                    <span class="topology-badge topology-badge-configurable">🇷🇺</span>
                </div>
            `;

            html = `
                <div class="topology-stage">
                    <div class="topology-stage-title">${subTitle}</div>
                    <div class="topology-flow">
                        <div class="topology-node">
                            <span class="node-icon">📱</span>
                            <span class="node-title">Клиент</span>
                            <span class="topology-badge topology-badge-ru">🇷🇺</span>
                        </div>
                        <div class="topology-arrow">
                            <span class="arrow-label">Запрос</span>
                            <span class="arrow-label">подписки</span>
                            <span>➔</span>
                        </div>
                        ${subNodeHtml}
                    </div>
                </div>
                <div class="topology-stage">
                    <div class="topology-stage-title">2. Каскадная маршрутизация (Двойной туннель)</div>
                    <div class="topology-flow">
                        <div class="topology-node">
                            <span class="node-icon">📱</span>
                            <span class="node-title">Клиент</span>
                            <span class="node-desc">С подпиской</span>
                            <span class="topology-badge topology-badge-ru">🇷🇺</span>
                        </div>
                        <div class="topology-arrow">
                            <span class="arrow-label">VLESS</span>
                            <span>➔</span>
                        </div>
                        <div class="topology-node configurable">
                            <span class="node-icon">🖧</span>
                            <span class="node-title">Proxy Node</span>
                            <span class="node-desc">Входной сервер</span>
                            <span class="topology-badge topology-badge-configurable">🇷🇺</span>
                        </div>
                        <div class="topology-arrow">
                            <span class="arrow-label">VLESS XHTTP</span>
                            <span>➔</span>
                        </div>
                        <div class="topology-node configurable">
                            <span class="node-icon">🕊️</span>
                            <span class="node-title">Freedom Node</span>
                            <span class="node-desc">Выходной сервер</span>
                            <span class="topology-badge topology-badge-configurable">🌐 Зарубежье</span>
                        </div>
                        <div class="topology-arrow">
                            <span class="arrow-label">Выход</span>
                            <span class="arrow-label">в сеть</span>
                            <span>➔</span>
                        </div>
                        <div class="topology-node">
                            <span class="node-icon">🌍</span>
                            <span class="node-title">Свободный Web</span>
                        </div>
                    </div>
                </div>
            `;
        } else if (mode === 'sub_only') {
            html = `
                <div class="topology-stage">
                    <div class="topology-stage-title">Автономный Сервер подписок (Caddy Sub-Server)</div>
                    <div class="topology-flow">
                        <div class="topology-node">
                            <span class="node-icon">📱</span>
                            <span class="node-title">Клиент</span>
                            <span class="topology-badge topology-badge-ru">🇷🇺</span>
                        </div>
                        <div class="topology-arrow">
                            <span class="arrow-label">Запрос</span>
                            <span class="arrow-label">подписки</span>
                            <span>➔</span>
                        </div>
                        <div class="topology-node configurable">
                            <span class="node-icon">📡</span>
                            <span class="node-title">Сервер подписок</span>
                            <span class="node-desc">Caddy Sub-Server</span>
                            <span class="topology-badge topology-badge-configurable">🌐 Caddy</span>
                        </div>
                        <div class="topology-arrow">
                            <span class="arrow-label">Проксирование</span>
                            <span>➔</span>
                        </div>
                        <div class="topology-node">
                            <span class="node-icon">⚙️</span>
                            <span class="node-title">Внешние ноды</span>
                            <span class="node-desc">Существующие 3X-UI</span>
                        </div>
                    </div>
                </div>
            `;
        } else if (mode === 'backup') {
            html = `
                <div class="topology-stage">
                    <div class="topology-stage-title">Создание бэкапа удаленного сервера</div>
                    <div class="topology-flow">
                        <div class="topology-node">
                            <span class="node-icon">💻</span>
                            <span class="node-title">Локальный ПК</span>
                            <span class="node-desc">./backups_panel/backup.tar.gz</span>
                        </div>
                        <div class="topology-arrow">
                            <span class="arrow-label">Упаковка &</span>
                            <span class="arrow-label">SCP Скачивание</span>
                            <span>➔</span>
                        </div>
                        <div class="topology-node configurable">
                            <span class="node-icon">🖥️</span>
                            <span class="node-title">Существующий VPS</span>
                            <span class="node-desc">3X-UI + Docker + Caddy</span>
                        </div>
                    </div>
                </div>
            `;
        } else if (mode === 'recovery') {
            html = `
                <div class="topology-stage">
                    <div class="topology-stage-title">Восстановление конфигурации из бэкапа</div>
                    <div class="topology-flow">
                        <div class="topology-node">
                            <span class="node-icon">💻</span>
                            <span class="node-title">Локальный ПК</span>
                            <span class="node-desc">./backups_panel/backup.tar.gz</span>
                        </div>
                        <div class="topology-arrow">
                            <span class="arrow-label">Загрузка &</span>
                            <span class="arrow-label">Docker Compose</span>
                            <span>➔</span>
                        </div>
                        <div class="topology-node configurable">
                            <span class="node-icon">🚀</span>
                            <span class="node-title">Новый VPS</span>
                            <span class="node-desc">Восстановленная</span>
                            <span class="node-desc">3X-UI Панель</span>
                        </div>
                    </div>
                </div>
            `;
        } else if (mode === 'update_3xui') {
            html = `
                <div class="topology-stage">
                    <div class="topology-stage-title">Обновление 3X-UI панели на сервере</div>
                    <div class="topology-flow">
                        <div class="topology-node">
                            <span class="node-icon">💻</span>
                            <span class="node-title">Локальный ПК</span>
                            <span class="node-desc">./backups_panel/backup.tar.gz</span>
                        </div>
                        <div class="topology-arrow">
                            <span class="arrow-label">Бэкап и</span>
                            <span class="arrow-label">обновление</span>
                            <span>➔</span>
                        </div>
                        <div class="topology-node configurable">
                            <span class="node-icon">🚀</span>
                            <span class="node-title">VPS c 3x-ui</span>
                            <span class="node-desc">Обновленный Docker</span>
                            <span class="node-desc">Образ 3X-UI</span>
                        </div>
                    </div>
                </div>
            `;
        } else if (mode === 'restart_sub' || mode === 'update_sub') {
            const subStageTitle = mode === 'update_sub' ? 'Обновление Сервера подписок' : 'Перезапуск Сервера подписок';
            const subArrowFirst = mode === 'update_sub' ? 'Бэкап &' : 'docker compose';
            const subArrowSecond = mode === 'update_sub' ? 'up -d --build' : 'down / up';
            html = `
                <div class="topology-stage">
                    <div class="topology-stage-title">${subStageTitle}</div>
                    <div class="topology-flow">
                        <div class="topology-node">
                            <span class="node-icon">💻</span>
                            <span class="node-title">Локальный ПК</span>
                            <span class="node-desc">${mode === 'update_sub' ? 'Бэкап & файлы' : 'SSH команда'}</span>
                        </div>
                        <div class="topology-arrow">
                            <span class="arrow-label">${subArrowFirst}</span>
                            <span class="arrow-label">${subArrowSecond}</span>
                            <span>➔</span>
                        </div>
                        <div class="topology-node configurable">
                            <span class="node-icon">📡</span>
                            <span class="node-title">Сервер подписок</span>
                            <span class="node-desc">subs-server + sub-caddy</span>
                        </div>
                    </div>
                </div>
            `;
        } else if (mode === 'backup_sub') {
            html = `
                <div class="topology-stage">
                    <div class="topology-stage-title">Бэкап конфигурации Сервера подписок</div>
                    <div class="topology-flow">
                        <div class="topology-node">
                            <span class="node-icon">💻</span>
                            <span class="node-title">Локальный ПК</span>
                            <span class="node-desc">./backups_panel/backup.tar.gz</span>
                        </div>
                        <div class="topology-arrow">
                            <span class="arrow-label">Упаковка &</span>
                            <span class="arrow-label">SCP Скачивание</span>
                            <span>➔</span>
                        </div>
                        <div class="topology-node configurable">
                            <span class="node-icon">📡</span>
                            <span class="node-title">Сервер подписок</span>
                            <span class="node-desc">nodes.json + Caddyfile</span>
                        </div>
                    </div>
                </div>
            `;
        } else if (mode === 'rollback_sub') {
            html = `
                <div class="topology-stage">
                    <div class="topology-stage-title">Восстановление Сервера подписок из бэкапа</div>
                    <div class="topology-flow">
                        <div class="topology-node">
                            <span class="node-icon">💻</span>
                            <span class="node-title">Локальный ПК</span>
                            <span class="node-desc">./backups_panel/backup.tar.gz</span>
                        </div>
                        <div class="topology-arrow">
                            <span class="arrow-label">Загрузка &</span>
                            <span class="arrow-label">Docker Compose</span>
                            <span>➔</span>
                        </div>
                        <div class="topology-node configurable">
                            <span class="node-icon">📡</span>
                            <span class="node-title">Сервер подписок</span>
                            <span class="node-desc">Восстановленная конфигурация</span>
                        </div>
                    </div>
                </div>
            `;
        }
        diagramEl.innerHTML = html;
    };

    const updateStep3Header = (mode) => {
        const titleEl = document.getElementById('step3Title');
        const descEl = document.getElementById('step3Desc');
        if (!titleEl && !descEl) return;
        let title = '3. Настройки панели и VPN-клиентов';
        let desc = 'Учетные данные панели и список подключаемых пользователей (опционально).';
        if (mode === 'cascade' || mode === 'cascade_sub') {
            title = '3. Настройки панелей и VPN-клиентов';
            desc = 'Учетные данные панелей (Freedom и Proxy) и список подключаемых пользователей (опционально).';
        } else if (mode === 'sub_only') {
            title = '3. Настройки Сервера подписок';
            desc = 'Параметры Сервера подписок: путь подписки, ссылки на ноды и админ-доступ.';
        } else if (mode === 'backup') {
            title = '3. Параметры создания бэкапа';
            desc = 'Задайте имя файла бэкапа (опционально).';
        } else if (mode === 'recovery') {
            title = '3. Параметры восстановления';
            desc = 'Выберите архив бэкапа для восстановления на новом сервере.';
        } else if (mode === 'update_3xui') {
            title = '3. Параметры обновления 3X-UI';
            desc = 'Укажите новую версию 3X-UI панели.';
        } else if (mode === 'restart_panel') {
            title = '3. Перезапуск панели 3X-UI';
            desc = 'Проверьте параметры и запустите перезапуск панели.';
        } else if (mode === 'restart_server') {
            title = '3. Перезагрузка сервера';
            desc = 'Проверьте параметры и запустите перезагрузку сервера.';
        } else if (mode === 'restart_sub' || mode === 'update_sub') {
            title = mode === 'update_sub' ? '3. Обновление Сервера подписок' : '3. Перезапуск Сервера подписок';
            desc = mode === 'update_sub'
                ? 'Файлы будут обновлены, а клиенты, ноды и overrides сохранены.'
                : 'Проверьте параметры и запустите перезапуск Сервера подписок.';
        } else if (mode === 'backup_sub') {
            title = '3. Параметры бэкапа Сервера подписок';
            desc = 'Задайте имя файла бэкапа (опционально).';
        } else if (mode === 'rollback_sub') {
            title = '3. Восстановление Сервера подписок';
            desc = 'Выберите архив бэкапа для восстановления.';
        }
        if (titleEl) titleEl.textContent = title;
        if (descEl) descEl.textContent = desc;
    };

    const updateModeUI = () => {
        const mode = getSelectedMode();
        const singleNodeSection = document.getElementById('singleNodeSection');
        const cascadeNodeSection = document.getElementById('cascadeNodeSection');
        const subServerSshSection = document.getElementById('subServerSshSection');
        const backupNodeSection = document.getElementById('backupNodeSection');
        const recoveryNodeSection = document.getElementById('recoveryNodeSection');
        const updateNodeSection = document.getElementById('updateNodeSection');

        const xuiVersionBlock = document.getElementById('xuiVersionBlock');
        const singlePanelSection = document.getElementById('singlePanelSection');
        const cascadePanelSection = document.getElementById('cascadePanelSection');
        const subServerPanelSection = document.getElementById('subServerPanelSection');
        const backupPanelSection = document.getElementById('backupPanelSection');
        const recoveryPanelSection = document.getElementById('recoveryPanelSection');
        const updatePanelSection = document.getElementById('updatePanelSection');
        const restartPanelSection = document.getElementById('restartPanelSection');
        const restartServerSection = document.getElementById('restartServerSection');
        const restartSubSection = document.getElementById('restartSubSection');
        const updateSubSection = document.getElementById('updateSubSection');
        const backupSubSection = document.getElementById('backupSubSection');
        const rollbackSubSection = document.getElementById('rollbackSubSection');
        const subOnlyTargetGroup = document.getElementById('subOnlyTargetGroup');
        const subWarningBanner = document.getElementById('subWarningBanner');
        const subWarningText = document.getElementById('subWarningText');
        const devModeWarning = document.getElementById('devModeWarning');
        const devModeWarningStep1 = document.getElementById('devModeWarningStep1');
        const isDevMode = mode === 'proxy_only' || mode === 'sub_only' || mode === 'backup' || mode === 'recovery' || mode === 'update_3xui' || mode === 'restart_panel' || mode === 'restart_server' || mode === 'restart_sub' || mode === 'update_sub' || mode === 'backup_sub' || mode === 'rollback_sub';

        if (devModeWarning) {
            devModeWarning.classList[isDevMode ? 'remove' : 'add']('hidden');
        }
        if (devModeWarningStep1) {
            devModeWarningStep1.classList[isDevMode ? 'remove' : 'add']('hidden');
        }

        renderTopologyDiagram(mode);
        updateStep3Header(mode);

        if (backupNodeSection) backupNodeSection.classList.add('hidden');
        if (recoveryNodeSection) recoveryNodeSection.classList.add('hidden');
        if (updateNodeSection) updateNodeSection.classList.add('hidden');
        if (backupPanelSection) backupPanelSection.classList.add('hidden');
        if (recoveryPanelSection) recoveryPanelSection.classList.add('hidden');
        if (updatePanelSection) updatePanelSection.classList.add('hidden');
        if (restartPanelSection) restartPanelSection.classList.add('hidden');
        if (restartServerSection) restartServerSection.classList.add('hidden');
        if (restartSubSection) restartSubSection.classList.add('hidden');
        if (updateSubSection) updateSubSection.classList.add('hidden');
        if (backupSubSection) backupSubSection.classList.add('hidden');
        if (rollbackSubSection) rollbackSubSection.classList.add('hidden');

        const topologySection = document.getElementById('topologySection');
        if (topologySection) {
            if (mode === 'backup' || mode === 'recovery' || mode === 'update_3xui' || mode === 'restart_panel' || mode === 'restart_server' || mode === 'restart_sub' || mode === 'update_sub' || mode === 'backup_sub' || mode === 'rollback_sub') {
                topologySection.classList.add('hidden');
            } else {
                topologySection.classList.remove('hidden');
            }
        }

        if (mode === 'single' || mode === 'proxy_only' || mode === 'freedom_only' || mode === 'freedom_component') {
            singleNodeSection.classList.remove('hidden');
            cascadeNodeSection.classList.add('hidden');
            subServerSshSection.classList.add('hidden');

            if (xuiVersionBlock) xuiVersionBlock.classList.remove('hidden');
            if (singlePanelSection) singlePanelSection.classList.remove('hidden');
            if (cascadePanelSection) cascadePanelSection.classList.add('hidden');
            if (subServerPanelSection) subServerPanelSection.classList.add('hidden');
            const foreignSubUrlGroup = document.getElementById('foreignSubUrlGroup');
            if (foreignSubUrlGroup) {
                foreignSubUrlGroup.classList[mode === 'proxy_only' ? 'remove' : 'add']('hidden');
            }
        } else if (mode === 'cascade') {
            singleNodeSection.classList.add('hidden');
            cascadeNodeSection.classList.remove('hidden');
            subServerSshSection.classList.add('hidden');

            if (xuiVersionBlock) xuiVersionBlock.classList.remove('hidden');
            if (singlePanelSection) singlePanelSection.classList.add('hidden');
            if (cascadePanelSection) cascadePanelSection.classList.remove('hidden');
            if (subServerPanelSection) subServerPanelSection.classList.add('hidden');
        } else if (mode === 'cascade_sub') {
            singleNodeSection.classList.add('hidden');
            cascadeNodeSection.classList.remove('hidden');
            subServerSshSection.classList.remove('hidden');

            if (xuiVersionBlock) xuiVersionBlock.classList.remove('hidden');
            if (singlePanelSection) singlePanelSection.classList.add('hidden');
            if (cascadePanelSection) cascadePanelSection.classList.remove('hidden');
            if (subServerPanelSection) subServerPanelSection.classList.remove('hidden');
            if (subOnlyTargetGroup) subOnlyTargetGroup.classList.add('hidden');
        } else if (mode === 'sub_only') {
            singleNodeSection.classList.add('hidden');
            cascadeNodeSection.classList.add('hidden');
            subServerSshSection.classList.remove('hidden');


            if (xuiVersionBlock) xuiVersionBlock.classList.add('hidden');
            if (singlePanelSection) singlePanelSection.classList.add('hidden');
            if (cascadePanelSection) cascadePanelSection.classList.add('hidden');
            if (subServerPanelSection) subServerPanelSection.classList.remove('hidden');
            if (subOnlyTargetGroup) subOnlyTargetGroup.classList.remove('hidden');
        } else if (mode === 'update_sub') {
            singleNodeSection.classList.add('hidden');
            cascadeNodeSection.classList.add('hidden');
            subServerSshSection.classList.remove('hidden');
            if (updateSubSection) updateSubSection.classList.remove('hidden');
            if (xuiVersionBlock) xuiVersionBlock.classList.add('hidden');
            if (singlePanelSection) singlePanelSection.classList.add('hidden');
            if (cascadePanelSection) cascadePanelSection.classList.add('hidden');
            if (subServerPanelSection) subServerPanelSection.classList.add('hidden');
        } else if (mode === 'backup') {
            singleNodeSection.classList.add('hidden');
            cascadeNodeSection.classList.add('hidden');
            subServerSshSection.classList.add('hidden');

            if (backupNodeSection) backupNodeSection.classList.remove('hidden');
            if (xuiVersionBlock) xuiVersionBlock.classList.add('hidden');
            if (singlePanelSection) singlePanelSection.classList.add('hidden');
            if (cascadePanelSection) cascadePanelSection.classList.add('hidden');
            if (subServerPanelSection) subServerPanelSection.classList.add('hidden');
            if (backupPanelSection) backupPanelSection.classList.remove('hidden');
        } else if (mode === 'recovery') {
            singleNodeSection.classList.add('hidden');
            cascadeNodeSection.classList.add('hidden');
            subServerSshSection.classList.add('hidden');

            if (recoveryNodeSection) recoveryNodeSection.classList.remove('hidden');
            if (xuiVersionBlock) xuiVersionBlock.classList.add('hidden');
            if (singlePanelSection) singlePanelSection.classList.add('hidden');
            if (cascadePanelSection) cascadePanelSection.classList.add('hidden');
            if (subServerPanelSection) subServerPanelSection.classList.add('hidden');
            if (recoveryPanelSection) recoveryPanelSection.classList.remove('hidden');
            fetchBackupList('backups_panel');
        } else if (mode === 'update_3xui' || mode === 'restart_panel' || mode === 'restart_server') {
            singleNodeSection.classList.add('hidden');
            cascadeNodeSection.classList.add('hidden');
            subServerSshSection.classList.add('hidden');

            if (updateNodeSection) {
                updateNodeSection.classList.remove('hidden');
                const titleEl = updateNodeSection.querySelector('.section-title');
                if (titleEl) {
                    if (mode === 'update_3xui') titleEl.textContent = 'Сервер для обновления 3X-UI панели';
                    else if (mode === 'restart_panel') titleEl.textContent = 'Сервер для перезапуска 3X-UI панели';
                    else if (mode === 'restart_server') titleEl.textContent = 'Сервер для перезагрузки';
                }
            }
            if (xuiVersionBlock) xuiVersionBlock.classList.add('hidden');
            if (singlePanelSection) singlePanelSection.classList.add('hidden');
            if (cascadePanelSection) cascadePanelSection.classList.add('hidden');
            if (subServerPanelSection) subServerPanelSection.classList.add('hidden');
            if (mode === 'update_3xui' && updatePanelSection) updatePanelSection.classList.remove('hidden');
            if (mode === 'restart_panel' && restartPanelSection) restartPanelSection.classList.remove('hidden');
            if (mode === 'restart_server' && restartServerSection) restartServerSection.classList.remove('hidden');
        } else if (mode === 'restart_sub' || mode === 'update_sub' || mode === 'backup_sub' || mode === 'rollback_sub') {
            singleNodeSection.classList.add('hidden');
            cascadeNodeSection.classList.add('hidden');
            subServerSshSection.classList.remove('hidden');

            if (xuiVersionBlock) xuiVersionBlock.classList.add('hidden');
            if (singlePanelSection) singlePanelSection.classList.add('hidden');
            if (cascadePanelSection) cascadePanelSection.classList.add('hidden');
            if (subServerPanelSection) subServerPanelSection.classList.add('hidden');
            if (mode === 'restart_sub' && restartSubSection) {
                restartSubSection.classList.remove('hidden');
            }
            if (mode === 'update_sub') {
                if (updateSubSection) updateSubSection.classList.remove('hidden');
            }
            if (mode === 'backup_sub' && backupSubSection) backupSubSection.classList.remove('hidden');
            if (mode === 'rollback_sub' && rollbackSubSection) rollbackSubSection.classList.remove('hidden');
            if (mode === 'rollback_sub') fetchBackupList('backups_sub_server');
        }
        resetSSHValidation();

        if (glowRefresher) glowRefresher();
    };

    document.querySelectorAll('input[name="deploy_mode"]').forEach(radio => {
        radio.addEventListener('change', updateModeUI);
    });
    const padNum = (n) => String(n).padStart(2, '0');

    const updateBackupName = () => {
        const hostEl = document.getElementById('backup_vps_host');
        const nameEl = document.getElementById('backup_name');
        if (!nameEl) return;
        const domain = hostEl ? hostEl.value.trim().replace(/[^A-Za-z0-9._-]/g, '_') : '';
        if (domain) {
            const now = new Date();
            const ts = `${now.getFullYear()}-${padNum(now.getMonth() + 1)}-${padNum(now.getDate())}_${padNum(now.getHours())}${padNum(now.getMinutes())}${padNum(now.getSeconds())}`;
            nameEl.value = `${domain}_${ts}.tar.gz`;
        } else {
            nameEl.value = '';
        }
        if (glowRefresher) glowRefresher();
    };

    const backupHostEl = document.getElementById('backup_vps_host');
    if (backupHostEl) {
        backupHostEl.addEventListener('input', updateBackupName);
        backupHostEl.addEventListener('change', updateBackupName);
    }

    const updateSubBackupName = () => {
        const hostEl = document.getElementById('sub_vps_host');
        const nameEl = document.getElementById('sub_backup_name');
        if (!nameEl) return;
        const domain = hostEl ? hostEl.value.trim().replace(/[^A-Za-z0-9._-]/g, '_') : '';
        if (domain) {
            const now = new Date();
            const ts = `${now.getFullYear()}-${padNum(now.getMonth() + 1)}-${padNum(now.getDate())}_${padNum(now.getHours())}${padNum(now.getMinutes())}${padNum(now.getSeconds())}`;
            nameEl.value = `${domain}_${ts}.tar.gz`;
        } else {
            nameEl.value = '';
        }
        if (glowRefresher) glowRefresher();
    };

    const subHostEl = document.getElementById('sub_vps_host');
    if (subHostEl) {
        subHostEl.addEventListener('input', updateSubBackupName);
        subHostEl.addEventListener('change', updateSubBackupName);
    }

    document.querySelectorAll('.auth-type-select').forEach(select => {
        select.addEventListener('change', () => {
            const passId = select.getAttribute('data-pass');
            const keyId = select.getAttribute('data-key');
            const pGroup = document.getElementById(passId);
            const kGroup = document.getElementById(keyId);
            if (select.value === 'key') {
                if (pGroup) pGroup.classList.add('hidden');
                if (kGroup) kGroup.classList.remove('hidden');
            } else {
                if (pGroup) pGroup.classList.remove('hidden');
                if (kGroup) kGroup.classList.add('hidden');
            }
            resetSSHValidation();
            if (glowRefresher) glowRefresher();
        });
    });

    const initCustomSelects = () => {
        document.querySelectorAll('.auth-type-select, .custom-select').forEach(select => {
            if (select.dataset.customInitialized) return;
            select.dataset.customInitialized = 'true';

            const wrapper = document.createElement('div');
            wrapper.className = 'custom-select-container';

            const trigger = document.createElement('div');
            trigger.className = 'custom-select-trigger';

            const triggerText = document.createElement('span');
            triggerText.className = 'custom-select-text';

            const arrow = document.createElement('div');
            arrow.className = 'custom-select-arrow';
            arrow.innerHTML = `<svg width="10" height="6" viewBox="0 0 10 6" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M1 1L5 5L9 1" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>`;

            trigger.appendChild(triggerText);
            trigger.appendChild(arrow);

            const optionsContainer = document.createElement('div');
            optionsContainer.className = 'custom-select-options';

            const updateSelected = () => {
                const selectedOpt = select.options[select.selectedIndex];
                triggerText.textContent = selectedOpt ? selectedOpt.textContent : '';
                optionsContainer.querySelectorAll('.custom-select-option').forEach(optEl => {
                    if (optEl.dataset.value === select.value) {
                        optEl.classList.add('selected');
                    } else {
                        optEl.classList.remove('selected');
                    }
                });
            };

            Array.from(select.options).forEach(opt => {
                const optEl = document.createElement('div');
                optEl.className = 'custom-select-option';
                optEl.dataset.value = opt.value;
                optEl.textContent = opt.textContent;

                optEl.addEventListener('click', (e) => {
                    e.stopPropagation();
                    if (select.value !== opt.value) {
                        select.value = opt.value;
                        select.dispatchEvent(new Event('change', { bubbles: true }));
                    }
                    wrapper.classList.remove('open');
                });

                optionsContainer.appendChild(optEl);
            });

            select.parentNode.insertBefore(wrapper, select);
            wrapper.appendChild(select);
            wrapper.appendChild(trigger);
            wrapper.appendChild(optionsContainer);
            select.style.display = 'none';

            trigger.addEventListener('click', (e) => {
                e.stopPropagation();
                document.querySelectorAll('.custom-select-container.open').forEach(other => {
                    if (other !== wrapper) other.classList.remove('open');
                });
                wrapper.classList.toggle('open');
            });

            select.addEventListener('change', updateSelected);
            updateSelected();
        });

        document.addEventListener('click', () => {
            document.querySelectorAll('.custom-select-container.open').forEach(wrapper => {
                wrapper.classList.remove('open');
            });
        });
    };

    initCustomSelects();

    const refreshCustomSelect = (select) => {
        const wrapper = select ? select.parentNode : null;
        if (!wrapper || !wrapper.classList.contains('custom-select-container')) return;
        const triggerText = wrapper.querySelector('.custom-select-text');
        const optionsContainer = wrapper.querySelector('.custom-select-options');
        if (optionsContainer) {
            optionsContainer.innerHTML = '';
            Array.from(select.options).forEach(opt => {
                const optEl = document.createElement('div');
                optEl.className = 'custom-select-option';
                optEl.dataset.value = opt.value;
                optEl.textContent = opt.textContent;
                optEl.addEventListener('click', (e) => {
                    e.stopPropagation();
                    if (select.value !== opt.value) {
                        select.value = opt.value;
                        select.dispatchEvent(new Event('change', { bubbles: true }));
                    }
                    wrapper.classList.remove('open');
                });
                optionsContainer.appendChild(optEl);
            });
            optionsContainer.querySelectorAll('.custom-select-option').forEach(el => {
                el.classList.toggle('selected', el.dataset.value === select.value);
            });
        }
        if (triggerText) triggerText.textContent = select.selectedOptions[0] ? select.selectedOptions[0].textContent : select.value;
    };

    const syncVersionSelect = (select) => {
        if (!select) return;
        const wanted = select.dataset.initialVersion || select.value || '3.6.0';
        if (wanted && !Array.from(select.options).some(o => o.value === wanted)) {
            const opt = document.createElement('option');
            opt.value = wanted;
            opt.textContent = wanted;
            select.insertBefore(opt, select.firstChild);
        }
        if (wanted) select.value = wanted;
        refreshCustomSelect(select);
    };

    const loadXuiVersions = async () => {
        let versions = [];
        try {
            const res = await fetch('/api/xui_versions');
            if (res.ok) {
                const data = await res.json();
                if (Array.isArray(data.versions) && data.versions.length) versions = data.versions;
            }
        } catch (e) { }
        if (versions.length === 0) versions = ['latest', '3.6.0', '3.5.0'];
        ['xui_version', 'update_xui_version'].forEach(id => {
            const select = document.getElementById(id);
            if (!select) return;
            const wanted = select.dataset.initialVersion || select.value || '3.6.0';
            select.innerHTML = '';
            const list = versions.includes(wanted) ? versions : [wanted].concat(versions);
            list.forEach(v => {
                const opt = document.createElement('option');
                opt.value = v;
                opt.textContent = v;
                select.appendChild(opt);
            });
            select.value = list.includes(wanted) ? wanted : versions[0];
            refreshCustomSelect(select);
        });
    };

    loadXuiVersions();

    const isVersionBelow = (v, min) => {
        const toParts = (s) => String(s).trim().replace(/^v/, '').split('.').map(n => parseInt(n, 10));
        if (isNaN(toParts(v)[0])) return false;
        const a = toParts(v), b = toParts(min);
        for (let i = 0; i < Math.max(a.length, b.length); i++) {
            const x = a[i] || 0, y = b[i] || 0;
            if (x !== y) return x < y;
        }
        return false;
    };

    ['xui_version', 'update_xui_version'].forEach(id => {
        const sel = document.getElementById(id);
        if (!sel) return;
        sel.addEventListener('change', () => {
            const v = sel.value;
            if (v && isVersionBelow(v, '3.5.0')) {
                showToast(`Версия ${v} ниже 3.5.0 — не тестировалась в этом проекте. Используйте на свой риск.`, 'warning', 5000);
            }
        });
    });

    const resetSSHValidation = () => {
        btnNext1.classList.add('hidden');
        testResult.className = 'test-result';
        testResult.textContent = '';
        saveCurrentConfig();
    };

    let saveTimeout = null;
    const saveCurrentConfig = () => {
        if (saveTimeout) clearTimeout(saveTimeout);
        saveTimeout = setTimeout(async () => {
            const mode = getSelectedMode();
            const payload = {
                deploy_mode: mode,
                is_cascade: (mode === 'cascade' || mode === 'cascade_sub'),
                vps_host: document.getElementById('vps_host').value.trim(),
                vps_port: parseInt(document.getElementById('vps_port').value) || 22,
                vps_user: document.getElementById('vps_user').value.trim() || 'root',
                vps_auth_type: document.getElementById('vps_auth_type').value,

                freedom_host: document.getElementById('freedom_host').value.trim(),
                freedom_port: parseInt(document.getElementById('freedom_port').value) || 22,
                freedom_user: document.getElementById('freedom_user').value.trim() || 'root',
                freedom_auth_type: document.getElementById('freedom_auth_type').value,
                freedom_xui_username: getFieldValueOrDefault('freedom_xui_username'),
                freedom_sub_secret: getFieldValueOrDefault('freedom_sub_secret'),
                freedom_client_name: document.getElementById('freedom_client_name').value.trim(),

                proxy_host: document.getElementById('proxy_host').value.trim(),
                proxy_port: parseInt(document.getElementById('proxy_port').value) || 22,
                proxy_user: document.getElementById('proxy_user').value.trim() || 'root',
                proxy_auth_type: document.getElementById('proxy_auth_type').value,
                proxy_xui_username: getFieldValueOrDefault('proxy_xui_username'),
                proxy_sub_secret: getFieldValueOrDefault('proxy_sub_secret'),
                proxy_client_tcp_list: document.getElementById('proxy_client_tcp_list').value.trim(),
                proxy_client_xhttp_list: document.getElementById('proxy_client_xhttp_list').value.trim(),

                sub_vps_host: document.getElementById('sub_vps_host').value.trim(),
                sub_vps_port: parseInt(document.getElementById('sub_vps_port').value) || 22,
                sub_vps_user: document.getElementById('sub_vps_user').value.trim() || 'root',
                sub_auth_type: document.getElementById('sub_auth_type').value,
                sub_domain: document.getElementById('sub_domain') ? document.getElementById('sub_domain').value.trim() : document.getElementById('sub_vps_host').value.trim(),
                sub_secret_path: getFieldValueOrDefault('sub_secret_path'),
                sub_russian_url: document.getElementById('sub_russian_url').value.trim(),
                sub_foreign_url: document.getElementById('sub_foreign_url').value.trim(),
                sub_proxy_clients: document.getElementById('sub_proxy_clients').value.trim(),
                sub_freedom_clients: document.getElementById('sub_freedom_clients').value.trim(),
                sub_admin_user: getFieldValueOrDefault('sub_admin_user'),
                sub_same_as_proxy: subSameAsProxy ? subSameAsProxy.checked : true,

                backup_vps_host: document.getElementById('backup_vps_host') ? document.getElementById('backup_vps_host').value.trim() : '',
                backup_vps_port: document.getElementById('backup_vps_port') ? parseInt(document.getElementById('backup_vps_port').value) || 22 : 22,
                backup_vps_user: document.getElementById('backup_vps_user') ? document.getElementById('backup_vps_user').value.trim() || 'root' : 'root',
                backup_auth_type: document.getElementById('backup_auth_type') ? document.getElementById('backup_auth_type').value : 'password',
                backup_name: document.getElementById('backup_name') ? document.getElementById('backup_name').value.trim() : '',
                sub_backup_name: document.getElementById('sub_backup_name') ? document.getElementById('sub_backup_name').value.trim() : '',

                recovery_vps_host: document.getElementById('recovery_vps_host') ? document.getElementById('recovery_vps_host').value.trim() : '',
                recovery_vps_port: document.getElementById('recovery_vps_port') ? parseInt(document.getElementById('recovery_vps_port').value) || 22 : 22,
                recovery_vps_user: document.getElementById('recovery_vps_user') ? document.getElementById('recovery_vps_user').value.trim() || 'root' : 'root',
                recovery_auth_type: document.getElementById('recovery_auth_type') ? document.getElementById('recovery_auth_type').value : 'password',
                recovery_backup_file: document.getElementById('recovery_backup_file') ? document.getElementById('recovery_backup_file').value : '',
                recovery_xui_username: getFieldValueOrDefault('recovery_xui_username'),

                update_vps_host: document.getElementById('update_vps_host') ? document.getElementById('update_vps_host').value.trim() : '',
                update_vps_port: document.getElementById('update_vps_port') ? parseInt(document.getElementById('update_vps_port').value) || 22 : 22,
                update_vps_user: document.getElementById('update_vps_user') ? document.getElementById('update_vps_user').value.trim() || 'root' : 'root',
                update_auth_type: document.getElementById('update_auth_type') ? document.getElementById('update_auth_type').value : 'password',
                update_xui_version: document.getElementById('update_xui_version') ? document.getElementById('update_xui_version').value.trim() : '3.6.0',

                xui_username: getFieldValueOrDefault('xui_username'),
                sub_secret: getFieldValueOrDefault('sub_secret'),
                xui_version: document.getElementById('xui_version') ? document.getElementById('xui_version').value.trim() : '3.6.0',
                client_tcp_list: document.getElementById('client_tcp_list').value.trim(),
                client_xhttp_list: document.getElementById('client_xhttp_list').value.trim(),
                ui_open_categories: ['category-full', 'category-single', 'category-maintenance']
                    .filter(id => { const el = document.getElementById(id); return el && el.open; })
                    .join(',')
            };
            try {
                await fetch('/api/config', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
            } catch (e) { }
        }, 500);
    };

    const loadBackupConfig = async () => {
        try {
            const resp = await fetch('/api/config');
            const cfg = await resp.json();

            if (cfg && Object.keys(cfg).length > 0) {
                const has = (key) => Object.prototype.hasOwnProperty.call(cfg, key);
                const setValue = (id, value) => {
                    const el = document.getElementById(id);
                    if (!el) return;
                    el.value = value ?? '';
                };

                let mode = cfg.deploy_mode;
                if (!mode) {
                    mode = cfg.is_cascade ? 'cascade' : 'freedom_only';
                }
                const radioToSelect = document.querySelector(`input[name="deploy_mode"][value="${mode}"]`);
                if (radioToSelect) radioToSelect.checked = true;
                
                if (cfg.ui_open_categories !== undefined) {
                    const openIds = cfg.ui_open_categories.split(',').filter(x => x);
                    ['category-full', 'category-single', 'category-maintenance'].forEach(id => {
                        const el = document.getElementById(id);
                        if (el) {
                            if (openIds.includes(id)) el.setAttribute('open', '');
                            else el.removeAttribute('open');
                        }
                    });
                }

                const setAuthSelect = (selectId, passId, keyId, authType, keyVal) => {
                    const sel = document.getElementById(selectId);
                    const pGroup = document.getElementById(passId);
                    const kGroup = document.getElementById(keyId);
                    if (!sel) return;
                    if (authType === 'key' || keyVal) {
                        sel.value = 'key';
                        if (pGroup) pGroup.classList.add('hidden');
                        if (kGroup) kGroup.classList.remove('hidden');
                    } else {
                        sel.value = 'password';
                        if (pGroup) pGroup.classList.remove('hidden');
                        if (kGroup) kGroup.classList.add('hidden');
                    }
                };

                if (has('vps_host')) setValue('vps_host', cfg.vps_host);
                if (has('vps_port')) setValue('vps_port', cfg.vps_port);
                if (has('vps_user')) setValue('vps_user', cfg.vps_user);
                if (has('vps_password')) setValue('vps_password', cfg.vps_password);
                if (has('vps_key')) setValue('vps_key', cfg.vps_key);
                setAuthSelect('vps_auth_type', 'vpsPassGroup', 'vpsKeyGroup', cfg.vps_auth_type, cfg.vps_key);

                if (has('freedom_host')) setValue('freedom_host', cfg.freedom_host);
                if (has('freedom_port')) setValue('freedom_port', cfg.freedom_port);
                if (has('freedom_user')) setValue('freedom_user', cfg.freedom_user);
                if (has('freedom_password')) setValue('freedom_password', cfg.freedom_password);
                if (has('freedom_key')) setValue('freedom_key', cfg.freedom_key);
                setAuthSelect('freedom_auth_type', 'freedomPassGroup', 'freedomKeyGroup', cfg.freedom_auth_type, cfg.freedom_key);
                if (has('freedom_xui_username')) setValue('freedom_xui_username', cfg.freedom_xui_username);
                if (has('freedom_xui_password')) setValue('freedom_xui_password', cfg.freedom_xui_password);
                if (has('freedom_sub_secret')) {
                    setValue('freedom_sub_secret', cfg.freedom_sub_secret);
                }
                if (has('freedom_client_name')) setValue('freedom_client_name', cfg.freedom_client_name);

                if (has('proxy_host')) setValue('proxy_host', cfg.proxy_host);
                if (has('proxy_port')) setValue('proxy_port', cfg.proxy_port);
                if (has('proxy_user')) setValue('proxy_user', cfg.proxy_user);
                if (has('proxy_password')) setValue('proxy_password', cfg.proxy_password);
                if (has('proxy_key')) setValue('proxy_key', cfg.proxy_key);
                setAuthSelect('proxy_auth_type', 'proxyPassGroup', 'proxyKeyGroup', cfg.proxy_auth_type, cfg.proxy_key);
                if (has('proxy_xui_username')) setValue('proxy_xui_username', cfg.proxy_xui_username);
                if (has('proxy_xui_password')) setValue('proxy_xui_password', cfg.proxy_xui_password);
                if (has('proxy_sub_secret')) {
                    setValue('proxy_sub_secret', cfg.proxy_sub_secret);
                }
                if (has('proxy_client_tcp_list')) setValue('proxy_client_tcp_list', cfg.proxy_client_tcp_list);
                if (has('proxy_client_xhttp_list')) setValue('proxy_client_xhttp_list', cfg.proxy_client_xhttp_list);

                if (has('sub_vps_host')) setValue('sub_vps_host', cfg.sub_vps_host);
                if (has('sub_vps_port')) setValue('sub_vps_port', cfg.sub_vps_port);
                if (has('sub_vps_user')) setValue('sub_vps_user', cfg.sub_vps_user);
                if (has('sub_vps_password')) setValue('sub_vps_password', cfg.sub_vps_password);
                if (has('sub_vps_key')) setValue('sub_vps_key', cfg.sub_vps_key);
                setAuthSelect('sub_auth_type', 'subPassGroup', 'subKeyGroup', cfg.sub_auth_type, cfg.sub_vps_key);
                if (has('sub_domain')) setValue('sub_domain', cfg.sub_domain);
                if (has('sub_secret_path')) setValue('sub_secret_path', cfg.sub_secret_path);
                if (has('sub_russian_url')) setValue('sub_russian_url', cfg.sub_russian_url);
                if (has('sub_foreign_url')) setValue('sub_foreign_url', cfg.sub_foreign_url);
                if (has('sub_proxy_clients')) setValue('sub_proxy_clients', cfg.sub_proxy_clients);
                if (has('sub_freedom_clients')) setValue('sub_freedom_clients', cfg.sub_freedom_clients);
                if (has('sub_admin_user')) setValue('sub_admin_user', cfg.sub_admin_user);
                if (document.getElementById('sub_admin_password')) document.getElementById('sub_admin_password').value = '';
                if (has('sub_same_as_proxy') && subSameAsProxy) subSameAsProxy.checked = !!cfg.sub_same_as_proxy;

                if (has('backup_vps_host')) setValue('backup_vps_host', cfg.backup_vps_host);
                if (has('backup_vps_port')) setValue('backup_vps_port', cfg.backup_vps_port);
                if (has('backup_vps_user')) setValue('backup_vps_user', cfg.backup_vps_user);
                if (has('backup_vps_password')) setValue('backup_vps_password', cfg.backup_vps_password);
                if (has('backup_vps_key')) setValue('backup_vps_key', cfg.backup_vps_key);
                setAuthSelect('backup_auth_type', 'backupPassGroup', 'backupKeyGroup', cfg.backup_auth_type, cfg.backup_vps_key);
                if (has('backup_name')) setValue('backup_name', cfg.backup_name);
                if (has('sub_backup_name')) setValue('sub_backup_name', cfg.sub_backup_name);

                if (has('recovery_vps_host')) setValue('recovery_vps_host', cfg.recovery_vps_host);
                if (has('recovery_vps_port')) setValue('recovery_vps_port', cfg.recovery_vps_port);
                if (has('recovery_vps_user')) setValue('recovery_vps_user', cfg.recovery_vps_user);
                if (has('recovery_vps_password')) setValue('recovery_vps_password', cfg.recovery_vps_password);
                if (has('recovery_vps_key')) setValue('recovery_vps_key', cfg.recovery_vps_key);
                setAuthSelect('recovery_auth_type', 'recoveryPassGroup', 'recoveryKeyGroup', cfg.recovery_auth_type, cfg.recovery_vps_key);
                if (has('recovery_xui_username')) setValue('recovery_xui_username', cfg.recovery_xui_username);

                if (has('update_vps_host')) setValue('update_vps_host', cfg.update_vps_host);
                if (has('update_vps_port')) setValue('update_vps_port', cfg.update_vps_port);
                if (has('update_vps_user')) setValue('update_vps_user', cfg.update_vps_user);
                if (has('update_vps_password')) setValue('update_vps_password', cfg.update_vps_password);
                if (has('update_vps_key')) setValue('update_vps_key', cfg.update_vps_key);
                setAuthSelect('update_auth_type', 'updatePassGroup', 'updateKeyGroup', cfg.update_auth_type, cfg.update_vps_key);
                if (has('update_xui_version') && document.getElementById('update_xui_version')) {
                    const sel = document.getElementById('update_xui_version');
                    sel.dataset.initialVersion = cfg.update_xui_version;
                    syncVersionSelect(sel);
                }

                if (has('xui_username')) setValue('xui_username', cfg.xui_username);
                if (has('xui_password')) setValue('xui_password', cfg.xui_password);
                if (has('sub_secret')) {
                    setValue('sub_secret', cfg.sub_secret);
                }
                if (has('xui_version') && document.getElementById('xui_version')) {
                    const sel = document.getElementById('xui_version');
                    sel.dataset.initialVersion = cfg.xui_version;
                    syncVersionSelect(sel);
                }
                if (has('client_tcp_list')) setValue('client_tcp_list', cfg.client_tcp_list);
                if (has('client_xhttp_list')) setValue('client_xhttp_list', cfg.client_xhttp_list);
                if (has('foreign_sub_url')) setValue('foreign_sub_url', cfg.foreign_sub_url);

                const subBkNameEl = document.getElementById('sub_backup_name');
                if (subBkNameEl && !subBkNameEl.value.trim()) updateSubBackupName();

                updateModeUI();
            } else {
                if (!document.getElementById('sub_secret').value) document.getElementById('sub_secret').value = '';
                if (document.getElementById('freedom_sub_secret') && !document.getElementById('freedom_sub_secret').value) document.getElementById('freedom_sub_secret').value = '';
                if (document.getElementById('proxy_sub_secret') && !document.getElementById('proxy_sub_secret').value) document.getElementById('proxy_sub_secret').value = '';
                updateModeUI();
            }
        } catch (e) { }
    };

    loadBackupConfig();

    document.querySelectorAll('.btn-toggle-eye').forEach(btn => {
        btn.addEventListener('click', () => {
            const targetId = btn.getAttribute('data-target');
            const input = document.getElementById(targetId);
            if (!input) return;
            if (input.type === 'password') {
                input.type = 'text';
                btn.textContent = '🙈';
            } else {
                input.type = 'password';
                btn.textContent = '👁️';
            }
        });
    });

    document.querySelectorAll('input, textarea').forEach(input => {
        input.addEventListener('input', resetSSHValidation);
    });

    if (passRadio) {
        passRadio.addEventListener('change', () => {
            if (passGroup) passGroup.classList.remove('hidden');
            if (keyGroup) keyGroup.classList.add('hidden');
            resetSSHValidation();
        });
    }

    if (keyRadio) {
        keyRadio.addEventListener('change', () => {
            if (keyGroup) keyGroup.classList.remove('hidden');
            if (passGroup) passGroup.classList.add('hidden');
            resetSSHValidation();
        });
    }

    if (cascadeNo) {
        cascadeNo.addEventListener('change', () => {
            if (singleNodeSection) {
                singleNodeSection.classList.remove('hidden');
                singleNodeSection.classList.add('fade-slide-in');
            }
            if (cascadeNodeSection) {
                cascadeNodeSection.classList.add('hidden');
                cascadeNodeSection.classList.remove('fade-slide-in');
            }
            if (singlePanelSection) {
                singlePanelSection.classList.remove('hidden');
                singlePanelSection.classList.add('fade-slide-in');
            }
            if (cascadePanelSection) {
                cascadePanelSection.classList.add('hidden');
                cascadePanelSection.classList.remove('fade-slide-in');
            }
            resetSSHValidation();
        });
    }

    if (cascadeYes) {
        cascadeYes.addEventListener('change', () => {
            if (cascadeNodeSection) {
                cascadeNodeSection.classList.remove('hidden');
                cascadeNodeSection.classList.add('fade-slide-in');
            }
            if (singleNodeSection) {
                singleNodeSection.classList.add('hidden');
                singleNodeSection.classList.remove('fade-slide-in');
            }
            if (cascadePanelSection) {
                cascadePanelSection.classList.remove('hidden');
                cascadePanelSection.classList.add('fade-slide-in');
            }
            if (singlePanelSection) {
                singlePanelSection.classList.add('hidden');
                singlePanelSection.classList.remove('fade-slide-in');
            }
            resetSSHValidation();
        });
    }

    let currentStep = 1;

    const showStep = (stepNum) => {
        currentStep = stepNum;

        document.querySelectorAll('.step').forEach(stepEl => {
            const num = parseInt(stepEl.getAttribute('data-step'));
            if (num <= currentStep) {
                stepEl.classList.add('active');
            } else {
                stepEl.classList.remove('active');
            }
        });

        document.querySelectorAll('.step-content').forEach(contentEl => {
            contentEl.classList.remove('active');
        });

        const targetStep = document.getElementById(`step${currentStep}`);
        if (targetStep) targetStep.classList.add('active');

        if (currentStep === 1) {
            updateBadgeStatus('Выбор режима', '#3b82f6');
        } else if (currentStep === 2) {
            updateBadgeStatus('Ввод параметров SSH', '#06b6d4');
        } else if (currentStep === 3) {
            updateBadgeStatus('Настройки панели', '#8b5cf6');
        } else if (currentStep === 4) {
            updateBadgeStatus('Готов к развертыванию', '#10b981');
        }

        if (glowRefresher) glowRefresher();
    };

    document.querySelectorAll('.step').forEach(stepEl => {
        stepEl.addEventListener('click', () => {
            const stepNum = parseInt(stepEl.getAttribute('data-step'));
            showStep(stepNum);
        });
    });

    const btnNextStep1 = document.getElementById('btnNextStep1');
    if (btnNextStep1) {
        btnNextStep1.addEventListener('click', () => showStep(2));
    }

    const btnBackToStep1 = document.getElementById('btnBackToStep1');
    if (btnBackToStep1) {
        btnBackToStep1.addEventListener('click', () => showStep(1));
    }

    if (btnNext1) {
        btnNext1.addEventListener('click', () => {
            showStep(3);
        });
    }

    const btnBackToStep2 = document.getElementById('btnBackToStep2');
    if (btnBackToStep2) {
        btnBackToStep2.addEventListener('click', () => showStep(2));
    }

    const btnNextStep3 = document.getElementById('btnNextStep3');
    if (btnNextStep3) {
        btnNextStep3.addEventListener('click', () => {
            if (getSelectedMode() === 'proxy_only') {
                const fsu = document.getElementById('foreign_sub_url');
                if (fsu && !fsu.value.trim()) {
                    alert('Для Proxy Node укажите ссылку подписки Freedom ноды в настройках панели.');
                    showStep(3);
                    return;
                }
            }
            showStep(4);
        });
    }

    const btnBackToStep3 = document.getElementById('btnBackToStep3');
    if (btnBackToStep3) {
        btnBackToStep3.addEventListener('click', () => showStep(3));
    }

    if (btnTestSSH) {
        btnTestSSH.addEventListener('click', async () => {
            const mode = getSelectedMode();
            const origBtnHtml = btnTestSSH.innerHTML;
            btnTestSSH.disabled = true;
            btnTestSSH.innerHTML = '<span class="btn-spinner"></span> Проверка...';
            btnNext1.classList.add('hidden');

            try {
                if (mode === 'single' || mode === 'proxy_only' || mode === 'freedom_only' || mode === 'freedom_component') {
                    const host = document.getElementById('vps_host').value.trim();
                    const port = parseInt(document.getElementById('vps_port').value) || 22;
                    const user = document.getElementById('vps_user').value.trim() || 'root';
                    const password = document.getElementById('vps_password').value;
                    const key_data = document.getElementById('vps_key').value;

                    if (!host) {
                        testResult.className = 'test-result error';
                        testResult.textContent = '❌ Укажите домен / IP адрес сервера';
                        return;
                    }

                    testResult.className = 'test-result info';
                    testResult.textContent = `⏳ Проверяем подключение к ${host}:${port}...`;
                    const resp = await fetch('/api/ssh/test', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ vps_host: host, vps_port: port, vps_user: user, vps_password: password, vps_key: key_data })
                    });
                    const res = await resp.json();
                    if (res.ok) {
                        testResult.className = 'test-result success';
                        testResult.textContent = `✅ Успешное подключение к ${host}:${port}`;
                        btnNext1.classList.remove('hidden');
                    } else {
                        testResult.className = 'test-result error';
                        testResult.textContent = `❌ ${res.message}`;
                    }
                } else if (mode === 'sub_only') {
                    const host = document.getElementById('sub_vps_host').value.trim();
                    const port = parseInt(document.getElementById('sub_vps_port').value) || 22;
                    const user = document.getElementById('sub_vps_user').value.trim() || 'root';
                    const password = document.getElementById('sub_vps_password').value;
                    const key_data = document.getElementById('sub_vps_key').value;

                    if (!host) {
                        testResult.className = 'test-result error';
                        testResult.textContent = '❌ Укажите домен Сервера подписок';
                        return;
                    }

                    testResult.className = 'test-result info';
                    testResult.textContent = `⏳ Проверяем подключение к Серверу подписок (${host}:${port})...`;
                    const resp = await fetch('/api/ssh/test', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ vps_host: host, vps_port: port, vps_user: user, vps_password: password, vps_key: key_data })
                    });
                    const res = await resp.json();
                    if (res.ok) {
                        testResult.className = 'test-result success';
                        testResult.textContent = `✅ Успешное подключение к Серверу подписок (${host}:${port})`;
                        btnNext1.classList.remove('hidden');
                    } else {
                        testResult.className = 'test-result error';
                        testResult.textContent = `❌ ${res.message}`;
                    }
                } else if (mode === 'backup') {
                    const host = document.getElementById('backup_vps_host').value.trim();
                    const port = parseInt(document.getElementById('backup_vps_port').value) || 22;
                    const user = document.getElementById('backup_vps_user').value.trim() || 'root';
                    const password = document.getElementById('backup_vps_password').value;
                    const key_data = document.getElementById('backup_vps_key').value;

                    if (!host) {
                        testResult.className = 'test-result error';
                        testResult.textContent = '❌ Укажите домен / IP адрес сервера для бэкапа';
                        return;
                    }

                    testResult.className = 'test-result info';
                    testResult.textContent = `⏳ Проверяем подключение к серверу бэкапа (${host}:${port})...`;
                    const resp = await fetch('/api/ssh/test', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ backup_vps_host: host, backup_vps_port: port, backup_vps_user: user, backup_vps_password: password, backup_vps_key: key_data })
                    });
                    const res = await resp.json();
                    if (res.ok) {
                        testResult.className = 'test-result success';
                        testResult.textContent = `✅ Успешное подключение к серверу (${host}:${port})`;
                        btnNext1.classList.remove('hidden');
                    } else {
                        testResult.className = 'test-result error';
                        testResult.textContent = `❌ ${res.message}`;
                    }
                } else if (mode === 'update_3xui' || mode === 'restart_panel' || mode === 'restart_server') {
                    const host = document.getElementById('update_vps_host').value.trim();
                    const port = parseInt(document.getElementById('update_vps_port').value) || 22;
                    const user = document.getElementById('update_vps_user').value.trim() || 'root';
                    const password = document.getElementById('update_vps_password').value;
                    const key_data = document.getElementById('update_vps_key').value;

                    if (!host) {
                        testResult.className = 'test-result error';
                        testResult.textContent = '❌ Укажите домен / IP адрес сервера';
                        return;
                    }

                    testResult.className = 'test-result info';
                    testResult.textContent = `⏳ Проверяем подключение к серверу (${host}:${port})...`;
                    const resp = await fetch('/api/ssh/test', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ update_vps_host: host, update_vps_port: port, update_vps_user: user, update_vps_password: password, update_vps_key: key_data })
                    });
                    const res = await resp.json();
                    if (res.ok) {
                        testResult.className = 'test-result success';
                        testResult.textContent = `✅ Успешное подключение к серверу (${host}:${port})`;
                        btnNext1.classList.remove('hidden');
                    } else {
                        testResult.className = 'test-result error';
                        testResult.textContent = `❌ ${res.message}`;
                    }
                } else if (mode === 'restart_sub' || mode === 'update_sub' || mode === 'backup_sub' || mode === 'rollback_sub') {
                    const host = document.getElementById('sub_vps_host').value.trim();
                    const port = parseInt(document.getElementById('sub_vps_port').value) || 22;
                    const user = document.getElementById('sub_vps_user').value.trim() || 'root';
                    const password = document.getElementById('sub_vps_password').value;
                    const key_data = document.getElementById('sub_vps_key').value;

                    if (!host) {
                        testResult.className = 'test-result error';
                        testResult.textContent = '❌ Укажите домен Сервера подписок';
                        return;
                    }
                    if (mode === 'rollback_sub') {
                        const backup_file = document.getElementById('rollback_sub_backup_file') ? document.getElementById('rollback_sub_backup_file').value : '';
                        if (!backup_file) {
                            testResult.className = 'test-result error';
                            testResult.textContent = '❌ Выберите архив бэкапа из списка';
                            return;
                        }
                    }

                    testResult.className = 'test-result info';
                    testResult.textContent = `⏳ Проверяем подключение к Серверу подписок (${host}:${port})...`;
                    const resp = await fetch('/api/ssh/test', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ sub_vps_host: host, sub_vps_port: port, sub_vps_user: user, sub_vps_password: password, sub_vps_key: key_data })
                    });
                    const res = await resp.json();
                    if (res.ok) {
                        testResult.className = 'test-result success';
                        testResult.textContent = `✅ Успешное подключение к Серверу подписок (${host}:${port})`;
                        btnNext1.classList.remove('hidden');
                    } else {
                        testResult.className = 'test-result error';
                        testResult.textContent = `❌ ${res.message}`;
                    }
                } else if (mode === 'recovery') {
                    const host = document.getElementById('recovery_vps_host').value.trim();
                    const port = parseInt(document.getElementById('recovery_vps_port').value) || 22;
                    const user = document.getElementById('recovery_vps_user').value.trim() || 'root';
                    const password = document.getElementById('recovery_vps_password').value;
                    const key_data = document.getElementById('recovery_vps_key').value;
                    const backup_file = document.getElementById('recovery_backup_file').value;

                    if (!host) {
                        testResult.className = 'test-result error';
                        testResult.textContent = '❌ Укажите домен / IP адрес нового сервера';
                        return;
                    }
                    if (!backup_file) {
                        testResult.className = 'test-result error';
                        testResult.textContent = '❌ Выберите архив бэкапа из списка';
                        return;
                    }

                    testResult.className = 'test-result info';
                    testResult.textContent = `⏳ Проверяем подключение к целевому серверу (${host}:${port})...`;
                    const resp = await fetch('/api/ssh/test', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ recovery_vps_host: host, recovery_vps_port: port, recovery_vps_user: user, recovery_vps_password: password, recovery_vps_key: key_data })
                    });
                    const res = await resp.json();
                    if (res.ok) {
                        testResult.className = 'test-result success';
                        testResult.textContent = `✅ Успешное подключение к целевому серверу (${host}:${port})`;
                        btnNext1.classList.remove('hidden');
                    } else {
                        testResult.className = 'test-result error';
                        testResult.textContent = `❌ ${res.message}`;
                    }
                } else {
                    const fHost = document.getElementById('freedom_host').value.trim();
                    const fPort = parseInt(document.getElementById('freedom_port').value) || 22;
                    const fUser = document.getElementById('freedom_user').value.trim() || 'root';
                    const fPass = document.getElementById('freedom_password').value;
                    const fKey = document.getElementById('freedom_key').value;

                    const pHost = document.getElementById('proxy_host').value.trim();
                    const pPort = parseInt(document.getElementById('proxy_port').value) || 22;
                    const pUser = document.getElementById('proxy_user').value.trim() || 'root';
                    const pPass = document.getElementById('proxy_password').value;
                    const pKey = document.getElementById('proxy_key').value;

                    if (!fHost || !pHost) {
                        testResult.className = 'test-result error';
                        testResult.textContent = '❌ Укажите хосты для обоих серверов (Freedom Node и Proxy Node)';
                        return;
                    }

                    testResult.className = 'test-result info';
                    testResult.textContent = `⏳ Проверяем подключение к Freedom Node (${fHost}:${fPort})...`;
                    const r1 = await fetch('/api/ssh/test', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ vps_host: fHost, vps_port: fPort, vps_user: fUser, vps_password: fPass, vps_key: fKey })
                    });
                    const res1 = await r1.json();

                    if (!res1.ok) {
                        testResult.className = 'test-result error';
                        testResult.textContent = `❌ Ошибка подключения к Freedom Node (${fHost}): ${res1.message}`;
                        return;
                    }

                    testResult.className = 'test-result info';
                    testResult.textContent = `⏳ Проверяем подключение к Proxy Node (${pHost}:${pPort})...`;
                    const r2 = await fetch('/api/ssh/test', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ vps_host: pHost, vps_port: pPort, vps_user: pUser, vps_password: pPass, vps_key: pKey })
                    });
                    const res2 = await r2.json();

                    if (!res2.ok) {
                        testResult.className = 'test-result error';
                        testResult.textContent = `❌ Ошибка подключения к Proxy Node (${pHost}): ${res2.message}`;
                        return;
                    }

                    if (mode === 'cascade_sub') {
                        const sHost = document.getElementById('sub_vps_host').value.trim();
                        const sPort = parseInt(document.getElementById('sub_vps_port').value) || 22;
                        const sUser = document.getElementById('sub_vps_user').value.trim() || 'root';
                        const sPass = document.getElementById('sub_vps_password').value;
                        const sKey = document.getElementById('sub_vps_key').value;
                        if (!sHost) {
                            testResult.className = 'test-result error';
                            testResult.textContent = '❌ Укажите домен Сервера подписок';
                            return;
                        }
                        testResult.className = 'test-result info';
                        testResult.textContent = `⏳ Проверяем подключение к Серверу подписок (${sHost}:${sPort})...`;
                        const r3 = await fetch('/api/ssh/test', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ vps_host: sHost, vps_port: sPort, vps_user: sUser, vps_password: sPass, vps_key: sKey })
                        });
                        const res3 = await r3.json();
                        if (!res3.ok) {
                            testResult.className = 'test-result error';
                            testResult.textContent = `❌ Ошибка подключения к Серверу подписок (${sHost}): ${res3.message}`;
                            return;
                        }
                    }

                    testResult.className = 'test-result success';
                    testResult.textContent = `✅ Успешная проверка всех выбранных серверов!`;
                    btnNext1.classList.remove('hidden');
                }
            } catch (err) {
                testResult.className = 'test-result error';
                testResult.textContent = `❌ Ошибка запроса: ${err.message}`;
            } finally {
                btnTestSSH.disabled = false;
                btnTestSSH.innerHTML = origBtnHtml;
            }
        });
    }

    const btnStartDeploy = document.getElementById('btnStartDeploy');
    const btnStopDeploy = document.getElementById('btnStopDeploy');
    const terminalLogs = document.getElementById('terminalLogs');
    const btnCopyLogs = document.getElementById('btnCopyLogs');

    if (btnCopyLogs) {
        btnCopyLogs.addEventListener('click', () => {
            const text = terminalLogs.innerText;
            copyToClipboard(text, btnCopyLogs);
        });
    }

    let isUserScrolledUp = false;

    if (terminalLogs) {
        terminalLogs.addEventListener('scroll', () => {
            const distanceFromBottom = terminalLogs.scrollHeight - terminalLogs.clientHeight - terminalLogs.scrollTop;
            isUserScrolledUp = distanceFromBottom > 30;
        });
    }

    const initProgressIndicator = (hasSub = false) => {
        const stage1 = document.getElementById('stage1');
        const stage2 = document.getElementById('stage2');
        const stage3 = document.getElementById('stage3');
        const connector23 = document.getElementById('connector23');
        
        if (stage1) stage1.classList.add('active');
        if (stage2) stage2.classList.remove('active', 'completed');
        if (stage3) {
            if (hasSub) {
                stage3.classList.remove('hidden');
                if (connector23) connector23.classList.remove('hidden');
            } else {
                stage3.classList.add('hidden');
                if (connector23) connector23.classList.add('hidden');
            }
        }
        
        const infoText = document.getElementById('currentStageInfo');
        if (infoText) {
            infoText.innerHTML = '<span class="info-icon">🚀</span><span class="info-text">STAGE 1: Развертывание Freedom Node...</span>';
        }
    };

    const updateProgressIndicator = (message) => {
        const stage1 = document.getElementById('stage1');
        const stage2 = document.getElementById('stage2');
        const stage3 = document.getElementById('stage3');
        const connector12 = document.querySelector('.progress-stages .progress-connector');
        const connector23 = document.getElementById('connector23');
        const infoText = document.getElementById('currentStageInfo');
        
        if (!infoText) return;

        // Stage 1 Detection
        if (message.includes('STAGE 1') && message.includes('FREEDOM NODE')) {
            if (stage1) stage1.classList.add('active');
            infoText.innerHTML = '<span class="info-icon">🚀</span><span class="info-text">STAGE 1: Развертывание Freedom Node...</span>';
        }

        // Stage 1 Complete
        if (message.includes('STAGE 1 COMPLETE')) {
            if (stage1) {
                stage1.classList.remove('active');
                stage1.classList.add('completed');
            }
            if (connector12) connector12.classList.add('completed');
        }

        // Stage 2 Detection
        if (message.includes('STAGE 2') && message.includes('PROXY NODE')) {
            if (stage2) stage2.classList.add('active');
            infoText.innerHTML = '<span class="info-icon">⚙️</span><span class="info-text">STAGE 2: Развертывание Proxy Node...</span>';
        }

        // Stage 2 Complete
        if (message.includes('STAGE 2 COMPLETE')) {
            if (stage2) {
                stage2.classList.remove('active');
                stage2.classList.add('completed');
            }
            if (connector23 && !connector23.classList.contains('hidden')) {
                connector23.classList.add('completed');
            }
        }

        // Stage 3 Detection
        if (message.includes('STAGE 3') && message.includes('SUBSCRIPTION SERVER')) {
            if (stage3) stage3.classList.add('active');
            infoText.innerHTML = '<span class="info-icon">📦</span><span class="info-text">STAGE 3: Развертывание Subscription Server...</span>';
        }

        // Stage 3 Complete
        if (message.includes('STAGE 3 COMPLETE')) {
            if (stage3) {
                stage3.classList.remove('active');
                stage3.classList.add('completed');
            }
        }

        // All stages complete
        if (message.includes('ALL STAGES COMPLETED')) {
            infoText.innerHTML = '<span class="info-icon">✅</span><span class="info-text">Все этапы завершены успешно!</span>';
        }
    };

    const appendLog = (message, level = 'info') => {
        const line = document.createElement('div');
        line.className = `log-line ${level}`;
        line.textContent = message;
        terminalLogs.appendChild(line);

        // Update progress indicator based on log message
        updateProgressIndicator(message);

        if (!isUserScrolledUp) {
            terminalLogs.scrollTop = terminalLogs.scrollHeight;
        }
    };

    let statusPollTimer = null;
    let deployStartTime = null;
    let timerInterval = null;

    const startDeployTimer = () => {
        deployStartTime = Date.now();
        const statusTimer = document.getElementById('statusTimer');
        if (statusTimer) statusTimer.classList.remove('hidden');

        if (timerInterval) clearInterval(timerInterval);
        timerInterval = setInterval(() => {
            if (!deployStartTime) return;
            const elapsedMs = Date.now() - deployStartTime;
            const totalSec = Math.floor(elapsedMs / 1000);
            const mins = String(Math.floor(totalSec / 60)).padStart(2, '0');
            const secs = String(totalSec % 60).padStart(2, '0');
            if (statusTimer) statusTimer.textContent = `⏱️ ${mins}:${secs}`;
        }, 1000);
    };

    const stopDeployTimer = () => {
        if (timerInterval) clearInterval(timerInterval);
    };

    if (btnStopDeploy) {
        btnStopDeploy.addEventListener('click', async () => {
            if (!await showConfirm('Вы уверены, что хотите остановить процесс развертывания?', 'Остановка развертывания', { confirmText: 'Да, остановить', danger: true })) return;
            btnStopDeploy.disabled = true;
            btnStopDeploy.textContent = '⏳ Остановка...';
            appendLog('[CANCEL] Запрос остановки процесса пользователем...', 'warning');

            try {
                const res = await fetch('/api/deploy/stop', { method: 'POST' });
                const data = await res.json();
                if (!data.ok) {
                    showToast('Не удалось остановить процесс: ' + (data.message || 'Ошибка'), 'error');
                    btnStopDeploy.disabled = false;
                    btnStopDeploy.textContent = '🛑 Остановить развертывание';
                }
            } catch (e) {
                showToast('Ошибка отправки запроса на остановку: ' + e.message, 'error');
                btnStopDeploy.disabled = false;
                btnStopDeploy.textContent = '🛑 Остановить развертывание';
            }
        });
    }

    // ==========================================
    // Password Field Validation & Yellow Glow
    // ==========================================
    
    const clearPasswordGlow = () => {
        document.querySelectorAll('.required-password-empty').forEach(input => {
            input.classList.remove('required-password-empty');
        });
    };

    let glowRefresher = null;

    document.addEventListener('input', () => {
        if (glowRefresher) glowRefresher();
    });

    const applyPasswordGlow = (fieldId) => {
        const field = document.getElementById(fieldId);
        if (field) {
            field.classList.add('required-password-empty');
        }
    };

    // ==========================================
    // REQUIRED FIELDS
    // Add a new required field here — no other code changes needed.
    //
    // Single field entry:
    //   id      — HTML id of the input/textarea
    //   step    — wizard step where the field lives (1-4), used to switch there
    //   message — toast text shown when the field is empty
    //   modes   — (optional) array of deploy modes this field applies to.
    //             If omitted — applies to ALL modes.
    //   when    — (optional) predicate () => bool; field is required only
    //             when it returns true.
    //
    // Group entry (validate several fields together). Add `group` instead of `id`:
    //   group: {
    //     mode    — 'any'          | 'all'           | 'exactly_one'
    //               at least one   | every field     | exactly one field
    //               must be filled | must be filled  | must be filled
    //     fields  — array of HTML ids in the group
    //     step    — wizard step (same as for single fields)
    //     message — toast text when the group rule is violated
    //     modes   — (optional) same as above
    //     when    — (optional) same as above
    //   }
    // ==========================================

    const getFieldValue = (fieldId) => {
        const field = document.getElementById(fieldId);
        return field ? field.value.trim() : '';
    };

    const getFieldValueOrDefault = (fieldId) => {
        const field = document.getElementById(fieldId);
        if (!field) return '';
        const v = field.value.trim();
        return v ? v : (field.placeholder || '').trim();
    };

    const REQUIRED_FIELDS = [
        // --- Group: at least one subscription URL must be filled ---
        {
            group: {
                mode: 'any',
                fields: ['sub_russian_url', 'sub_foreign_url'],
                step: 3,
                modes: ['sub_only', 'cascade_sub'],
                message: 'Укажите хотя бы одну ссылку подписки (RUSSIAN_SUB_URL или FOREIGN_SUB_URL)'
            }
        },

        // --- Single node: host / port / user ---
        { id: 'vps_host', step: 2, modes: ['single', 'proxy_only', 'freedom_only', 'freedom_component'], message: 'Укажите домен VPS сервера' },
        { id: 'vps_port', step: 2, modes: ['single', 'proxy_only', 'freedom_only', 'freedom_component'], message: 'Укажите SSH порт VPS сервера' },
        { id: 'vps_user', step: 2, modes: ['single', 'proxy_only', 'freedom_only', 'freedom_component'], message: 'Укажите SSH пользователя VPS сервера' },

        // --- Sub-server: host / port / user ---
        { id: 'sub_vps_host', step: 2, modes: ['sub_only', 'cascade_sub', 'restart_sub', 'update_sub', 'backup_sub', 'rollback_sub'], message: 'Укажите домен Сервера подписок' },
        { id: 'sub_vps_port', step: 2, modes: ['sub_only', 'cascade_sub', 'restart_sub', 'update_sub', 'backup_sub', 'rollback_sub'], message: 'Укажите SSH порт Сервера подписок' },
        { id: 'sub_vps_user', step: 2, modes: ['sub_only', 'cascade_sub', 'restart_sub', 'update_sub', 'backup_sub', 'rollback_sub'], message: 'Укажите SSH пользователя Сервера подписок' },

        // --- Backup: host / port / user ---
        { id: 'backup_vps_host', step: 2, modes: ['backup'], message: 'Укажите домен сервера для бэкапа' },
        { id: 'backup_vps_port', step: 2, modes: ['backup'], message: 'Укажите SSH порт сервера для бэкапа' },
        { id: 'backup_vps_user', step: 2, modes: ['backup'], message: 'Укажите SSH пользователя сервера для бэкапа' },
        { id: 'backup_name', step: 3, modes: ['backup'], message: 'Укажите имя файла бэкапа' },
        { id: 'sub_backup_name', step: 3, modes: ['backup_sub'], message: 'Укажите имя файла бэкапа' },

        // --- Recovery: host / port / user ---
        { id: 'recovery_vps_host', step: 2, modes: ['recovery'], message: 'Укажите домен сервера для восстановления' },
        { id: 'recovery_vps_port', step: 2, modes: ['recovery'], message: 'Укажите SSH порт сервера для восстановления' },
        { id: 'recovery_vps_user', step: 2, modes: ['recovery'], message: 'Укажите SSH пользователя сервера для восстановления' },

        // --- Recovery: panel admin credentials (needed to rewrite domain via the panel API) ---
        { id: 'recovery_xui_username', step: 3, modes: ['recovery'], message: 'Укажите логин админа 3X-UI из бэкапа' },
        { id: 'recovery_xui_password', step: 3, modes: ['recovery'], message: 'Укажите пароль админа 3X-UI из бэкапа' },

        // --- Update/restart: host / port / user ---
        { id: 'update_vps_host', step: 2, modes: ['update_3xui', 'restart_panel', 'restart_server'], message: 'Укажите домен сервера для обновления/перезапуска' },
        { id: 'update_vps_port', step: 2, modes: ['update_3xui', 'restart_panel', 'restart_server'], message: 'Укажите SSH порт сервера для обновления/перезапуска' },
        { id: 'update_vps_user', step: 2, modes: ['update_3xui', 'restart_panel', 'restart_server'], message: 'Укажите SSH пользователя сервера для обновления/перезапуска' },

        // --- Cascade: Freedom host / port / user ---
        { id: 'freedom_host', step: 2, modes: ['cascade', 'cascade_sub'], message: 'Укажите домен Freedom Node' },
        { id: 'freedom_port', step: 2, modes: ['cascade', 'cascade_sub'], message: 'Укажите SSH порт Freedom Node' },
        { id: 'freedom_user', step: 2, modes: ['cascade', 'cascade_sub'], message: 'Укажите SSH пользователя Freedom Node' },

        // --- Cascade: Proxy host / port / user ---
        { id: 'proxy_host', step: 2, modes: ['cascade', 'cascade_sub'], message: 'Укажите домен Proxy Node' },
        { id: 'proxy_port', step: 2, modes: ['cascade', 'cascade_sub'], message: 'Укажите SSH порт Proxy Node' },
        { id: 'proxy_user', step: 2, modes: ['cascade', 'cascade_sub'], message: 'Укажите SSH пользователя Proxy Node' },

        // --- Cascade: XHTTP client name for access to the target node ---
        { id: 'freedom_client_name', step: 3, modes: ['cascade', 'cascade_sub'], message: 'Укажите имя XHTTP клиента для каскада' },
    ];

    const collectPasswordErrors = () => {
        const mode = getSelectedMode();
        const errors = [];

        REQUIRED_FIELDS.forEach(entry => {
            // Group-specific mode filters live inside `entry.group`.
            // Without this branch, a group rule is accidentally applied to
            // every deployment mode (including maintenance modes).
            const modes = entry.group ? entry.group.modes : entry.modes;
            if (modes && !modes.includes(mode)) return;
            if (entry.when && !entry.when()) return;

            if (entry.group) {
                const filled = entry.group.fields.filter(id => getFieldValue(id) !== '').length;
                const modeType = entry.group.mode;
                const fail = modeType === 'any' ? filled === 0
                    : modeType === 'all' ? filled < entry.group.fields.length
                    : filled !== 1;
                if (fail) {
                    errors.push({ group: entry.group, message: entry.group.message, step: entry.group.step });
                }
            } else if (!getFieldValue(entry.id)) {
                errors.push({ fieldId: entry.id, message: entry.message, step: entry.step });
            }
        });

        // Sort by step so the toast/scroll point at the earliest step first
        errors.sort((a, b) => a.step - b.step);
        return errors;
    };

    const applyGroupGlow = (group) => {
        const states = group.fields.map(id => ({ id, filled: getFieldValue(id) !== '' }));
        let toGlow;
        if (group.mode === 'all') {
            toGlow = states.filter(s => !s.filled).map(s => s.id);
        } else if (group.mode === 'any') {
            toGlow = states.every(s => !s.filled) ? states.map(s => s.id) : [];
        } else { // exactly_one
            toGlow = states.every(s => !s.filled)
                ? states.map(s => s.id)
                : states.filter(s => s.filled).map(s => s.id);
        }
        toGlow.forEach(id => applyPasswordGlow(id));
    };

    const getErrorFieldIds = (error) => {
        if (error.group) return error.group.fields;
        return [error.fieldId];
    };

    const applyGlowForEmptyFields = () => {
        clearPasswordGlow();
        const errors = collectPasswordErrors();
        errors.forEach(error => {
            if (error.group) applyGroupGlow(error.group);
            else applyPasswordGlow(error.fieldId);
        });
    };

    const validateRequiredPasswords = () => {
        clearPasswordGlow();
        const errors = collectPasswordErrors();

        // If there are errors, highlight them and show message
        if (errors.length > 0) {
            // Apply glow to all fields with errors
            errors.forEach(error => {
                if (error.group) applyGroupGlow(error.group);
                else applyPasswordGlow(error.fieldId);
            });

            // Show toast with main error message
            const mainError = errors[0];
            showToast(mainError.message, 'warning');

            // Switch to the step with the error
            const lowestStep = Math.min(...errors.map(e => e.step));
            showStep(lowestStep);

            // Scroll to the first errored field
            const firstField = document.getElementById(getErrorFieldIds(errors[0])[0]);
            if (firstField) firstField.scrollIntoView({ behavior: 'smooth', block: 'center' });

            return false;
        }

        return true;
    };

    glowRefresher = applyGlowForEmptyFields;
    glowRefresher();

    btnStartDeploy.addEventListener('click', async () => {
        // First, validate all required passwords
        if (!validateRequiredPasswords()) {
            return;
        }

        const mode = getSelectedMode();

        showStep(4);
        updateBadgeStatus('Развертывание...', '#f59e0b', true);
        startDeployTimer();
        isUserScrolledUp = false;
        terminalLogs.innerHTML = '';
        const summaryCardReset = document.getElementById('summaryCard');
        if (summaryCardReset) summaryCardReset.classList.add('hidden');
        appendLog('[INIT] Starting deployment process...', 'info');

        if (btnStopDeploy) {
            btnStopDeploy.classList.remove('hidden');
            btnStopDeploy.disabled = false;
        }
        btnStartDeploy.classList.add('hidden');

        const commonVersion = document.getElementById('xui_version') ? document.getElementById('xui_version').value.trim() || '3.6.0' : '3.6.0';

        let payload = {
            deploy_mode: mode,
            is_cascade: (mode === 'cascade' || mode === 'cascade_sub'),
            xui_version: commonVersion
        };

        if (mode === 'single' || mode === 'proxy_only' || mode === 'freedom_only' || mode === 'freedom_component') {
            payload.vps_host = document.getElementById('vps_host').value.trim();
            payload.domain = payload.vps_host;
            payload.vps_port = parseInt(document.getElementById('vps_port').value) || 22;
            payload.vps_user = document.getElementById('vps_user').value.trim() || 'root';
            payload.vps_password = document.getElementById('vps_password').value;
            payload.vps_key = document.getElementById('vps_key').value;
            payload.xui_username = getFieldValueOrDefault('xui_username');
            payload.xui_password = getFieldValueOrDefault('xui_password');
            payload.sub_secret = getFieldValueOrDefault('sub_secret');
            payload.client_tcp_list = document.getElementById('client_tcp_list').value.trim();
            payload.client_xhttp_list = document.getElementById('client_xhttp_list').value.trim();
            if (mode === 'proxy_only') {
                payload.foreign_sub_url = document.getElementById('foreign_sub_url').value.trim();
            }
        } else if (mode === 'sub_only') {
            payload.sub_vps_host = document.getElementById('sub_vps_host').value.trim();
            payload.sub_vps_port = parseInt(document.getElementById('sub_vps_port').value) || 22;
            payload.sub_vps_user = document.getElementById('sub_vps_user').value.trim() || 'root';
            payload.sub_vps_password = document.getElementById('sub_vps_password').value;
            payload.sub_vps_key = document.getElementById('sub_vps_key').value;
            payload.sub_domain = (document.getElementById('sub_domain') ? document.getElementById('sub_domain').value.trim() : '') || payload.sub_vps_host;
            payload.sub_secret_path = getFieldValueOrDefault('sub_secret_path');
            payload.sub_russian_url = document.getElementById('sub_russian_url').value.trim();
            payload.sub_foreign_url = document.getElementById('sub_foreign_url').value.trim();
            payload.sub_proxy_clients = document.getElementById('sub_proxy_clients').value.trim();
            payload.sub_freedom_clients = document.getElementById('sub_freedom_clients').value.trim();
            payload.sub_admin_user = getFieldValueOrDefault('sub_admin_user');
            payload.sub_admin_password = getFieldValueOrDefault('sub_admin_password');
        } else if (mode === 'backup') {
            payload.backup_vps_host = document.getElementById('backup_vps_host').value.trim();
            payload.backup_vps_port = parseInt(document.getElementById('backup_vps_port').value) || 22;
            payload.backup_vps_user = document.getElementById('backup_vps_user').value.trim() || 'root';
            payload.backup_vps_password = document.getElementById('backup_vps_password').value;
            payload.backup_vps_key = document.getElementById('backup_vps_key').value;
            payload.backup_name = document.getElementById('backup_name').value.trim();
        } else if (mode === 'recovery') {
            payload.recovery_vps_host = document.getElementById('recovery_vps_host').value.trim();
            payload.recovery_vps_port = parseInt(document.getElementById('recovery_vps_port').value) || 22;
            payload.recovery_vps_user = document.getElementById('recovery_vps_user').value.trim() || 'root';
            payload.recovery_vps_password = document.getElementById('recovery_vps_password').value;
            payload.recovery_vps_key = document.getElementById('recovery_vps_key').value;
            payload.recovery_backup_file = document.getElementById('recovery_backup_file').value;
            payload.recovery_xui_username = getFieldValueOrDefault('recovery_xui_username');
            payload.recovery_xui_password = getFieldValueOrDefault('recovery_xui_password');
        } else if (mode === 'update_3xui' || mode === 'restart_panel' || mode === 'restart_server') {
            payload.update_vps_host = document.getElementById('update_vps_host').value.trim();
            payload.update_vps_port = parseInt(document.getElementById('update_vps_port').value) || 22;
            payload.update_vps_user = document.getElementById('update_vps_user').value.trim() || 'root';
            payload.update_vps_password = document.getElementById('update_vps_password').value;
            payload.update_vps_key = document.getElementById('update_vps_key').value;
            if (mode === 'update_3xui') {
                payload.update_xui_version = document.getElementById('update_xui_version').value.trim() || '3.6.0';
            }
        } else if (mode === 'restart_sub' || mode === 'update_sub' || mode === 'backup_sub' || mode === 'rollback_sub') {
            payload.sub_vps_host = document.getElementById('sub_vps_host').value.trim();
            payload.sub_vps_port = parseInt(document.getElementById('sub_vps_port').value) || 22;
            payload.sub_vps_user = document.getElementById('sub_vps_user').value.trim() || 'root';
            payload.sub_vps_password = document.getElementById('sub_vps_password').value;
            payload.sub_vps_key = document.getElementById('sub_vps_key').value;
            if (mode === 'backup_sub') {
                payload.backup_name = document.getElementById('sub_backup_name') ? document.getElementById('sub_backup_name').value.trim() : '';
            }
            if (mode === 'rollback_sub') {
                payload.rollback_sub_backup_file = document.getElementById('rollback_sub_backup_file') ? document.getElementById('rollback_sub_backup_file').value : '';
            }
        } else {
            payload.freedom_host = document.getElementById('freedom_host').value.trim();
            payload.freedom_port = parseInt(document.getElementById('freedom_port').value) || 22;
            payload.freedom_user = document.getElementById('freedom_user').value.trim() || 'root';
            payload.freedom_password = document.getElementById('freedom_password').value;
            payload.freedom_key = document.getElementById('freedom_key').value;
            payload.freedom_xui_username = getFieldValueOrDefault('freedom_xui_username');
            payload.freedom_xui_password = getFieldValueOrDefault('freedom_xui_password');
            payload.freedom_sub_secret = getFieldValueOrDefault('freedom_sub_secret');
            payload.freedom_xui_version = commonVersion;
            payload.freedom_client_name = document.getElementById('freedom_client_name').value.trim() || 'local-proxy-node-client';

            payload.proxy_host = document.getElementById('proxy_host').value.trim();
            payload.proxy_port = parseInt(document.getElementById('proxy_port').value) || 22;
            payload.proxy_user = document.getElementById('proxy_user').value.trim() || 'root';
            payload.proxy_password = document.getElementById('proxy_password').value;
            payload.proxy_key = document.getElementById('proxy_key').value;
            payload.proxy_xui_username = getFieldValueOrDefault('proxy_xui_username');
            payload.proxy_xui_password = getFieldValueOrDefault('proxy_xui_password');
            payload.proxy_sub_secret = getFieldValueOrDefault('proxy_sub_secret');
            payload.proxy_xui_version = commonVersion;
            payload.proxy_client_tcp_list = document.getElementById('proxy_client_tcp_list').value.trim();
            payload.proxy_client_xhttp_list = document.getElementById('proxy_client_xhttp_list').value.trim();

            if (mode === 'cascade_sub') {
                payload.sub_vps_host = document.getElementById('sub_vps_host').value.trim();
                payload.sub_vps_port = parseInt(document.getElementById('sub_vps_port').value) || 22;
                payload.sub_vps_user = document.getElementById('sub_vps_user').value.trim() || 'root';
                payload.sub_vps_password = document.getElementById('sub_vps_password').value;
                payload.sub_vps_key = document.getElementById('sub_vps_key').value;
                payload.sub_domain = (document.getElementById('sub_domain') ? document.getElementById('sub_domain').value.trim() : '') || payload.sub_vps_host;
                payload.sub_secret_path = getFieldValueOrDefault('sub_secret_path');
                payload.sub_admin_user = getFieldValueOrDefault('sub_admin_user');
                payload.sub_admin_password = getFieldValueOrDefault('sub_admin_password');
            }
        }

        if (mode === 'single') {
            updateBadgeStatus(`Развертывание ${payload.vps_host || 'сервера'}...`, '#f59e0b', true);
        } else if (mode === 'proxy_only') {
            updateBadgeStatus(`Развертывание Proxy Node...`, '#f59e0b', true);
        } else if (mode === 'freedom_only' || mode === 'freedom_component') {
            updateBadgeStatus(`Развертывание Freedom Node...`, '#f59e0b', true);
        } else if (mode === 'sub_only') {
            updateBadgeStatus('Развертывание Сервера подписок...', '#f59e0b', true);
        } else if (mode === 'backup') {
            updateBadgeStatus('Создание бэкапа сервера...', '#f59e0b', true);
        } else if (mode === 'recovery') {
            updateBadgeStatus('Восстановление сервера...', '#f59e0b', true);
        } else if (mode === 'update_3xui') {
            updateBadgeStatus('Обновление 3X-UI панели...', '#f59e0b', true);
        } else if (mode === 'restart_sub') {
            updateBadgeStatus('Перезапуск Сервера подписок...', '#f59e0b', true);
        } else if (mode === 'update_sub') {
            updateBadgeStatus('Обновление Сервера подписок...', '#f59e0b', true);
        } else if (mode === 'backup_sub') {
            updateBadgeStatus('Создание бэкапа Сервера подписок...', '#f59e0b', true);
        } else if (mode === 'rollback_sub') {
            updateBadgeStatus('Восстановление Сервера подписок...', '#f59e0b', true);
        } else {
            updateBadgeStatus('Каскадное развертывание...', '#f59e0b', true);
        }

        try {
            const resp = await fetch('/api/deploy', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const res = await resp.json();
            if (!res.ok) {
                appendLog(`[ERROR] ${res.message}`, 'error');
                updateBadgeStatus('Ошибка запуска', '#ef4444');
                stopDeployTimer();
                btnStartDeploy.classList.remove('hidden');
                if (btnStopDeploy) btnStopDeploy.classList.add('hidden');
                return;
            }

            // Show progress indicator for cascade deployments
            const progressContainer = document.getElementById('deployProgressContainer');
            if ((mode === 'cascade' || mode === 'cascade_sub') && progressContainer) {
                progressContainer.classList.remove('hidden');
                initProgressIndicator(mode === 'cascade_sub');
            }

            const eventSource = new EventSource('/api/deploy/logs');
            eventSource.onmessage = (event) => {
                const item = JSON.parse(event.data);
                if (item.event === 'done') {
                    eventSource.close();
                    checkFinalStatus(mode, payload);
                } else {
                    appendLog(item.message, item.level || 'info');
                }
            };
            eventSource.onerror = () => {
                eventSource.close();
                checkFinalStatus(mode, payload);
            };

        } catch (err) {
            appendLog(`[ERROR] ${err.message}`, 'error');
            updateBadgeStatus('Ошибка сети', '#ef4444');
            stopDeployTimer();
            btnStartDeploy.classList.remove('hidden');
            if (btnStopDeploy) btnStopDeploy.classList.add('hidden');
        }
    });

    const checkFinalStatus = async (mode, cfg) => {
        try {
            const resp = await fetch('/api/status');
            const data = await resp.json();

            if (data.status === 'cancelled') {
                stopDeployTimer();
                updateBadgeStatus('Процесс отменен', '#ef4444');
                if (btnStartDeploy) {
                    btnStartDeploy.classList.remove('hidden');
                    btnStartDeploy.disabled = false;
                }
                if (btnStopDeploy) {
                    btnStopDeploy.classList.add('hidden');
                    btnStopDeploy.disabled = false;
                    btnStopDeploy.textContent = '🛑 Остановить развертывание';
                }
                // Hide progress indicator
                const progressContainer = document.getElementById('deployProgressContainer');
                if (progressContainer) {
                    progressContainer.classList.add('hidden');
                }
                appendLog('[CANCEL] Процесс остановлен пользователем.', 'warning');
                return;
            }

            if (data.status === 'completed') {
                updateBadgeStatus('Успешно завершено!', '#10b981');
                stopDeployTimer();

                if (btnStartDeploy) btnStartDeploy.classList.remove('hidden');
                if (btnStopDeploy) btnStopDeploy.classList.add('hidden');

                // Hide progress indicator
                const progressContainer = document.getElementById('deployProgressContainer');
                if (progressContainer) {
                    setTimeout(() => {
                        progressContainer.classList.add('hidden');
                    }, 1500);
                }

                const summaryCard = document.getElementById('summaryCard');
                const panelsContainer = document.getElementById('panelsContainer');
                summaryCard.classList.remove('hidden');
                panelsContainer.innerHTML = '';

                const result = data.result || {};

                const renderPanelBlock = (title, icon, url, user, pass, userLabel = 'Логин администратора', passLabel = 'Пароль администратора', passSecret = true, urlLabel = 'Адрес панели (URL)', linkUrl = '') => {
                    const realLink = linkUrl || url;
                    const block = document.createElement('div');
                    block.className = 'panel-info-block';
                    block.innerHTML = `
                        <div class="panel-info-header">
                            <span class="panel-icon">${icon}</span>
                            <span class="panel-title-text">${title}</span>
                        </div>
                        <div class="summary-grid">
                            ${url ? `
                            <div class="summary-item full-width">
                                <span class="summary-label">${urlLabel}</span>
                                <div class="val-code-wrapper">
                                    <a href="${realLink}" target="_blank" class="val-code link">${url}</a>
                                    <button type="button" class="btn-sm btn-copy" data-copy="${url}">📋 Copy</button>
                                </div>
                            </div>` : ''}
                            ${user ? `
                            <div class="summary-item">
                                <span class="summary-label">${userLabel}</span>
                                <div class="val-code-wrapper">
                                    <span class="val-code">${user}</span>
                                    <button type="button" class="btn-sm btn-copy" data-copy="${user}">📋 Copy</button>
                                </div>
                            </div>` : ''}
                            ${pass ? `
                            <div class="summary-item">
                                <span class="summary-label">${passLabel}</span>
                                <div class="val-code-wrapper">
                                    ${passSecret ? `<span class="val-code secret-val" data-secret="${pass}">••••••••</span>` : `<span class="val-code">${pass}</span>`}
                                    ${passSecret ? `<button type="button" class="btn-sm btn-eye-secret">👁️</button>` : ''}
                                    <button type="button" class="btn-sm btn-copy" data-copy="${pass}">📋 Copy</button>
                                </div>
                            </div>` : ''}
                        </div>
                    `;

                    block.querySelectorAll('.btn-copy').forEach(btn => {
                        btn.onclick = (e) => copyToClipboard(btn.getAttribute('data-copy'), e.target);
                    });

                    block.querySelectorAll('.btn-eye-secret').forEach(btn => {
                        btn.onclick = () => {
                            const valSpan = btn.parentElement.querySelector('.secret-val');
                            const realSecret = valSpan.getAttribute('data-secret');
                            if (valSpan.textContent === '••••••••') {
                                valSpan.textContent = realSecret;
                                btn.textContent = '🙈';
                            } else {
                                valSpan.textContent = '••••••••';
                                btn.textContent = '👁️';
                            }
                        };
                    });

                    return block;
                };

                if (mode === 'backup') {
                    const bHost = result.backup_host || cfg.backup_vps_host || '';
                    const bName = result.backup_name || cfg.backup_name || '';
                    const bSize = result.file_size || '';
                    panelsContainer.appendChild(renderPanelBlock('Архив бэкапа успешно создан!', '📦', `Локальный архив: ./backups_panel/${bName}`, bHost, bSize, 'Сервер', 'Размер архива', false));
                    return;
                }

                if (mode === 'recovery') {
                    const rHost = result.recovery_host || cfg.recovery_vps_host || '';
                    const bFile = result.backup_file || cfg.recovery_backup_file || '';
                    const xuiUrl = result.xui_url || `https://${rHost}/`;
                    panelsContainer.appendChild(renderPanelBlock('Сервер успешно восстановлен из бэкапа!', '🔄', xuiUrl, rHost, bFile, 'Новый домен', 'Архив', false));
                    return;
                }

                if (mode === 'restart_panel') {
                    const clientsSectionEl = document.getElementById('clientsSection');
                    if (clientsSectionEl) clientsSectionEl.classList.add('hidden');
                    const done = document.createElement('div');
                    done.className = 'panel-info-block';
                    done.innerHTML = '<div class="panel-info-header"><span class="panel-icon">🔄</span><span class="panel-title-text">Панель 3X-UI перезапущена, всё готово!</span></div>';
                    panelsContainer.appendChild(done);
                    return;
                }

                if (mode === 'restart_server') {
                    const clientsSectionEl = document.getElementById('clientsSection');
                    if (clientsSectionEl) clientsSectionEl.classList.add('hidden');
                    const done = document.createElement('div');
                    done.className = 'panel-info-block';
                    done.innerHTML = '<div class="panel-info-header"><span class="panel-icon">🔄</span><span class="panel-title-text">Сервер перезагружается, всё готово!</span></div>';
                    panelsContainer.appendChild(done);
                    return;
                }

                if (mode === 'update_3xui') {
                    const uHost = result.update_host || cfg.update_vps_host || '';
                    const ver = result.xui_version || cfg.update_xui_version || '3.6.0';
                    const xuiUrl = result.xui_url || `https://${uHost}/`;
                    panelsContainer.appendChild(renderPanelBlock('Панель 3X-UI успешно обновлена!', '⬆️', xuiUrl, uHost, ver, 'Сервер', 'Версия 3X-UI', false));
                    return;
                }

                if (mode === 'restart_sub' || mode === 'update_sub') {
                    const clientsSectionEl = document.getElementById('clientsSection');
                    if (clientsSectionEl) clientsSectionEl.classList.add('hidden');
                    const done = document.createElement('div');
                    done.className = 'panel-info-block';
                    const backupInfo = mode === 'update_sub' && result.pre_update_backup
                        ? `<div class="panel-info-line">Pre-update backup: <code>${result.pre_update_backup}</code></div>`
                        : '';
                    done.innerHTML = `<div class="panel-info-header"><span class="panel-icon">${mode === 'update_sub' ? '⬆️' : '🔄'}</span><span class="panel-title-text">${mode === 'update_sub' ? 'Сервер подписок обновлён, клиенты и ноды сохранены!' : 'Сервер подписок перезапущен, всё готово!'}</span></div>${backupInfo}`;
                    panelsContainer.appendChild(done);
                    return;
                }

                if (mode === 'backup_sub') {
                    const clientsSectionEl = document.getElementById('clientsSection');
                    if (clientsSectionEl) clientsSectionEl.classList.add('hidden');
                    const bHost = result.sub_host || cfg.sub_vps_host || '';
                    const bName = result.backup_name || '';
                    const bSize = result.file_size || '';
                    panelsContainer.appendChild(renderPanelBlock('Бэкап Сервера подписок успешно создан!', '📦', `Локальный архив: ./backups_sub_server/${bName}`, bHost, bSize, 'Сервер подписок', 'Размер архива', false, 'Локальный архив'));
                    return;
                }

                if (mode === 'rollback_sub') {
                    const clientsSectionEl = document.getElementById('clientsSection');
                    if (clientsSectionEl) clientsSectionEl.classList.add('hidden');
                    const rHost = result.sub_host || cfg.sub_vps_host || '';
                    const bFile = result.backup_file || cfg.rollback_sub_backup_file || '';
                    const subBaseUrl = result.sub_base_url || '';
                    panelsContainer.appendChild(renderPanelBlock('Сервер подписок восстановлен из бэкапа!', '🔄', subBaseUrl, rHost, bFile, 'Сервер подписок', 'Архив', false, 'Адрес подписок (URL)'));
                    return;
                }

                if (mode === 'sub_only') {
                    const subBaseUrl = result.sub_base_url || `https://${cfg.sub_domain}/${cfg.sub_secret_path}`;
                    const subUser = result.sub_admin_user || cfg.sub_admin_user || 'admin';
                    const subPass = result.sub_admin_password || 'admin';
                    panelsContainer.appendChild(renderPanelBlock('Сервер подписок (Caddy Sub-Server)', '📡', `${subBaseUrl}/<username>`, subUser, subPass, 'Логин панели подписок', 'Пароль панели подписок', true, 'Адрес подписок (URL)', subBaseUrl));
                } else if (mode === 'cascade' || mode === 'cascade_sub') {
                    const freedomHost = result.freedom_domain || cfg.freedom_host || 'Freedom Node';
                    const freedomUrl = result.freedom_xui_url || `https://${freedomHost}/`;
                    const freedomUser = result.freedom_username || cfg.freedom_xui_username || 'admin';
                    const freedomPass = result.freedom_password || cfg.freedom_xui_password || 'admin';

                    panelsContainer.appendChild(renderPanelBlock('1. Панель управления Freedom Node (Выходной сервер)', '🕊️', freedomUrl, freedomUser, freedomPass));

                    const proxyHost = result.domain || cfg.proxy_host || 'Proxy Node';
                    const proxyUrl = result.xui_url || `https://${proxyHost}/`;
                    const proxyUser = result.xui_username || cfg.proxy_xui_username || 'admin';
                    const proxyPass = result.xui_password || cfg.proxy_xui_password || 'admin';

                    panelsContainer.appendChild(renderPanelBlock('2. Панель управления Proxy Node (Входной сервер)', '🛡️', proxyUrl, proxyUser, proxyPass));

                    if (mode === 'cascade_sub') {
                        const subBaseUrl = result.sub_base_url || `https://${cfg.sub_domain}/${cfg.sub_secret_path}`;
                        const subUser = result.sub_admin_user || cfg.sub_admin_user || 'admin';
                        const subPass = result.sub_admin_password || 'admin';
                        panelsContainer.appendChild(renderPanelBlock('3. Сервер подписок (Caddy Sub-Server)', '📡', `${subBaseUrl}/<username>`, subUser, subPass, 'Логин панели подписок', 'Пароль панели подписок', true, 'Адрес подписок (URL)', subBaseUrl));
                    }
                } else {
                    const host = result.domain || cfg.vps_host || 'Server';
                    const xuiUrl = result.xui_url || `https://${host}/`;
                    const xuiUser = result.xui_username || cfg.xui_username || 'admin';
                    const xuiPass = result.xui_password || cfg.xui_password || 'admin';
                    
                    let panelTitle = 'Панель управления 3X-UI';
                    let panelIcon = '🔑';
                    if (mode === 'proxy_only') {
                        panelTitle = 'Панель управления Proxy Node';
                        panelIcon = '🛡️';
                    } else if (mode === 'freedom_only' || mode === 'freedom_component') {
                        panelTitle = 'Панель управления Freedom Node';
                        panelIcon = '🕊️';
                    }

                    panelsContainer.appendChild(renderPanelBlock(panelTitle, panelIcon, xuiUrl, xuiUser, xuiPass));
                }

                const clientsContainer = document.getElementById('clientsContainer');
                clientsContainer.innerHTML = '';

                const clientsList = result.clients || [];
                if (clientsList.length === 0 && mode !== 'sub_only' && mode !== 'restart_panel' && mode !== 'restart_server' && mode !== 'restart_sub' && mode !== 'update_sub' && mode !== 'backup_sub' && mode !== 'rollback_sub') {
                    const targetDomain = (mode === 'cascade' || mode === 'cascade_sub') ? cfg.proxy_host : (cfg.vps_host || cfg.domain);
                    const fallbackSub = `https://${targetDomain}:2096/${cfg.sub_secret}`;
                    clientsList.push({ name: cfg.xui_username, sub_url: fallbackSub, tcp_url: '', xhttp_url: '' });
                }

                clientsList.forEach(client => {
                    const card = document.createElement('div');
                    card.className = 'client-card';

                    const groupTag = client.group ? ` (${client.group})` : '';
                    let html = `
                        <div class="client-header">
                            <span class="client-name-badge">👤 Клиент: ${client.name}${groupTag}</span>
                        </div>
                        <div class="client-link-group">
                    `;

                    if (client.sub_server_url) {
                        html += `
                            <div class="client-link-label">📡 Подписка через Сервер подписок</div>
                            <div class="client-link-row">
                                <span class="client-link-text">${client.sub_server_url}</span>
                                <button type="button" class="btn-sm btn-copy-sub-server">📋 Копировать</button>
                                <button type="button" class="btn-sm btn-qr-sub-server">📱 QR</button>
                            </div>
                        `;
                    }

                    if (client.sub_url) {
                        html += `
                            <div class="client-link-label">🔗 Прямая ссылка подписки</div>
                            <div class="client-link-row">
                                <span class="client-link-text">${client.sub_url}</span>
                                <button type="button" class="btn-sm btn-copy-sub">📋 Копировать</button>
                                <button type="button" class="btn-sm btn-qr-sub">📱 QR</button>
                            </div>
                        `;
                    }

                    if (client.tcp_url) {
                        html += `
                            <div class="client-link-label">⚡ VLESS TCP Reality</div>
                            <div class="client-link-row">
                                <span class="client-link-text">${client.tcp_url}</span>
                                <button type="button" class="btn-sm btn-copy-tcp">📋 Копировать</button>
                                <button type="button" class="btn-sm btn-qr-tcp">📱 QR</button>
                            </div>
                        `;
                    }

                    if (client.xhttp_url) {
                        html += `
                            <div class="client-link-label">🚀 VLESS XHTTP Reality</div>
                            <div class="client-link-row">
                                <span class="client-link-text">${client.xhttp_url}</span>
                                <button type="button" class="btn-sm btn-copy-xhttp">📋 Копировать</button>
                                <button type="button" class="btn-sm btn-qr-xhttp">📱 QR</button>
                            </div>
                        `;
                    }

                    html += `</div>`;
                    card.innerHTML = html;

                    if (client.sub_server_url) {
                        const btnCopy = card.querySelector('.btn-copy-sub-server');
                        if (btnCopy) btnCopy.onclick = (e) => copyToClipboard(client.sub_server_url, e.target);
                        const btnQr = card.querySelector('.btn-qr-sub-server');
                        if (btnQr) btnQr.onclick = () => showQrModal(`QR: Сервер подписок (${client.name})`, client.sub_server_url);
                    }
                    if (client.sub_url) {
                        const btnCopy = card.querySelector('.btn-copy-sub');
                        if (btnCopy) btnCopy.onclick = (e) => copyToClipboard(client.sub_url, e.target);
                        const btnQr = card.querySelector('.btn-qr-sub');
                        if (btnQr) btnQr.onclick = () => showQrModal(`QR: Подписка (${client.name})`, client.sub_url);
                    }
                    if (client.tcp_url) {
                        const btnCopy = card.querySelector('.btn-copy-tcp');
                        if (btnCopy) btnCopy.onclick = (e) => copyToClipboard(client.tcp_url, e.target);
                        const btnQr = card.querySelector('.btn-qr-tcp');
                        if (btnQr) btnQr.onclick = () => showQrModal(`QR: VLESS TCP (${client.name})`, client.tcp_url);
                    }
                    if (client.xhttp_url) {
                        const btnCopy = card.querySelector('.btn-copy-xhttp');
                        if (btnCopy) btnCopy.onclick = (e) => copyToClipboard(client.xhttp_url, e.target);
                        const btnQr = card.querySelector('.btn-qr-xhttp');
                        if (btnQr) btnQr.onclick = () => showQrModal(`QR: VLESS XHTTP (${client.name})`, client.xhttp_url);
                    }

                    clientsContainer.appendChild(card);
                });
            } else if (data.status === 'failed') {
                updateBadgeStatus('Ошибка развертывания', '#ef4444');
                stopDeployTimer();
                if (btnStartDeploy) btnStartDeploy.classList.remove('hidden');
                if (btnStopDeploy) btnStopDeploy.classList.add('hidden');
            }
        } catch (e) {
            updateBadgeStatus('Ошибка развертывания', '#ef4444');
        }
    };

    const btnUpdateSources = document.getElementById('btnUpdateSources');
    if (btnUpdateSources) {
        btnUpdateSources.addEventListener('click', async () => {
            if (!await showConfirm('Обновить файлы деплоера до последней версии с GitHub master?\n\nВаши сохраненные бэкапы (./backups_panel/) и конфигурация (setup_backup.yml) будут сохранены, а сервер перезапустится.', 'Обновление деплоера', { confirmText: 'Обновить', icon: '🔄' })) {
                return;
            }

            btnUpdateSources.disabled = true;
            btnUpdateSources.textContent = '⏳ Обновление...';
            updateBadgeStatus('Обновление исходников...', '#f59e0b', true);

            try {
                const res = await fetch('/api/update_sources', { method: 'POST' });
                const data = await res.json();
                if (!data.ok) {
                    showToast('Ошибка запуска обновления: ' + (data.message || 'Неизвестная ошибка'), 'error');
                    btnUpdateSources.disabled = false;
                    btnUpdateSources.textContent = '🔄 Обновить скрипт';
                    updateBadgeStatus('Готов к настройке', '#3b82f6');
                    return;
                }

                showAlert('Процесс обновления запущен! Сервер сейчас перезапустится. Страница автоматически обновится через несколько секунд.', 'Обновление деплоера', 'success');

                let attempts = 0;
                const pollInterval = setInterval(async () => {
                    attempts++;
                    try {
                        const statusRes = await fetch('/api/status');
                        if (statusRes.ok && attempts > 2) {
                            clearInterval(pollInterval);
                            window.location.reload();
                        }
                    } catch (e) {
                        // Server is restarting
                    }
                    if (attempts > 30) {
                        clearInterval(pollInterval);
                        window.location.reload();
                    }
                }, 1000);
            } catch (e) {
                showToast('Запрос на обновление отправлен. Ожидаем перезапуск сервера...', 'info');
                setTimeout(() => window.location.reload(), 4000);
            }
        });
    }

    const checkForUpdates = async () => {
        try {
            const res = await fetch('/api/update_check', { cache: 'no-store' });
            if (!res.ok) return;
            const data = await res.json();
            if (!data || data.update_available !== true) return;
            const banner = document.getElementById('updateBanner');
            if (banner) banner.classList.remove('hidden');
        } catch (e) {
            // Offline or server restarting - skip silently
        }
    };

    const btnBannerDismiss = document.getElementById('btnBannerDismiss');
    if (btnBannerDismiss) {
        btnBannerDismiss.addEventListener('click', () => {
            const banner = document.getElementById('updateBanner');
            if (banner) banner.classList.add('hidden');
        });
    }

    checkForUpdates();

    const btnRestart = document.getElementById('btnRestart');
    if (btnRestart) {
        btnRestart.addEventListener('click', async () => {
            if (!await showConfirm('Перезапустить процесс локального сервера деплоера?', 'Перезапуск сервера', { confirmText: 'Перезапустить', icon: '⚡' })) {
                return;
            }

            btnRestart.disabled = true;
            btnRestart.textContent = '⏳ Перезапуск...';
            updateBadgeStatus('Перезапуск сервера...', '#f59e0b', true);

            try {
                const res = await fetch('/api/restart', { method: 'POST' });
                const data = await res.json();
                if (!data.ok) {
                    showToast('Ошибка перезапуска: ' + (data.message || 'Ошибка'), 'error');
                    btnRestart.disabled = false;
                    btnRestart.textContent = '⚡ Перезапустить';
                    updateBadgeStatus('Готов к настройке', '#3b82f6');
                    return;
                }

                let attempts = 0;
                const pollInterval = setInterval(async () => {
                    attempts++;
                    try {
                        const statusRes = await fetch('/api/status');
                        if (statusRes.ok && attempts > 2) {
                            clearInterval(pollInterval);
                            window.location.reload();
                        }
                    } catch (e) {
                        // Server is restarting
                    }
                    if (attempts > 30) {
                        clearInterval(pollInterval);
                        window.location.reload();
                    }
                }, 1000);
            } catch (e) {
                setTimeout(() => window.location.reload(), 3000);
            }
        });
    }

    const btnShutdown = document.getElementById('btnShutdown');
    if (btnShutdown) {
        btnShutdown.addEventListener('click', async () => {
            if (!await showConfirm('Вы действительно хотите выключить локальный сервер деплоера?', 'Выключение сервера', { confirmText: 'Выключить', danger: true, icon: '🛑' })) {
                return;
            }

            btnShutdown.disabled = true;
            btnShutdown.textContent = '⏳ Выключение...';
            updateBadgeStatus('Сервер остановлен', '#ef4444');

            const startShutdownReconnectPolling = () => {
                const checkInterval = setInterval(async () => {
                    try {
                        const statusRes = await fetch('/api/status');
                        if (statusRes.ok) {
                            clearInterval(checkInterval);
                            window.location.reload();
                        }
                    } catch (e) {
                        // Server is still down
                    }
                }, 2000);
            };

            try {
                const res = await fetch('/api/shutdown', { method: 'POST' });
                const data = await res.json();
                if (!data.ok) {
                    showToast('Ошибка остановки: ' + (data.message || 'Ошибка'), 'error');
                    btnShutdown.disabled = false;
                    btnShutdown.textContent = '🛑 Выключить';
                    updateBadgeStatus('Готов к настройке', '#3b82f6');
                    return;
                }
                startShutdownReconnectPolling();
            } catch (e) {
                startShutdownReconnectPolling();
            }
        });
    }

    // ==========================================
    // Server Manager Sidebar Logic (Encrypted)
    // ==========================================
    const smTargetType = document.getElementById('sm_target_type');
    const smHost = document.getElementById('sm_host');
    const smUser = document.getElementById('sm_user');
    const smPort = document.getElementById('sm_port');
    const smAuthType = document.getElementById('sm_auth_type');
    const smPass = document.getElementById('sm_pass');
    const smKey = document.getElementById('sm_key');
    const btnSaveServer = document.getElementById('btnSaveServer');
    const savedServersList = document.getElementById('savedServersList');
    const btnResetServers = document.getElementById('btnResetServers');

    const masterPasswordModal = document.getElementById('masterPasswordModal');
    const btnCancelMasterPassword = document.getElementById('btnCancelMasterPassword');
    const pinInputs = document.querySelectorAll('.pin-digit');

    if (pinInputs.length > 0) {
        const checkAutoSubmit = () => {
            const pass = Array.from(pinInputs).map(i => i.value).join('');
            if (/^\d{5}$/.test(pass)) {
                submitMasterPassword();
            }
        };

        pinInputs.forEach((input, index) => {
            input.addEventListener('input', (e) => {
                if (e.target.value.length > 1) {
                    e.target.value = e.target.value.slice(0, 1);
                }
                if (e.target.value && !/^\d$/.test(e.target.value)) {
                    e.target.value = '';
                    return;
                }
                if (e.target.value && index < pinInputs.length - 1) {
                    pinInputs[index + 1].focus();
                }
                checkAutoSubmit();
            });
            
            input.addEventListener('keydown', (e) => {
                if (e.key === 'Backspace' && !e.target.value && index > 0) {
                    pinInputs[index - 1].focus();
                    pinInputs[index - 1].value = '';
                } else if (e.key === 'Enter') {
                    submitMasterPassword();
                }
            });
            
            input.addEventListener('paste', (e) => {
                e.preventDefault();
                const text = (e.clipboardData || window.clipboardData).getData('text').trim();
                if (/^\d{5}$/.test(text)) {
                    pinInputs.forEach((inp, i) => inp.value = text[i]);
                    checkAutoSubmit();
                }
            });
        });
    }

    let cryptoKey = null;
    let serversList = [];
    let serversLoaded = false;
    let serversLoadError = '';
    let editingServerIndex = null;

    // Crypto functions
    const deriveKey = async (password) => {
        const enc = new TextEncoder();
        const keyMaterial = await window.crypto.subtle.importKey(
            "raw", enc.encode(password), { name: "PBKDF2" }, false, ["deriveBits", "deriveKey"]
        );
        return window.crypto.subtle.deriveKey(
            { name: "PBKDF2", salt: enc.encode("3x-ui-salt-v1"), iterations: 100000, hash: "SHA-256" },
            keyMaterial, { name: "AES-GCM", length: 256 }, false, ["encrypt", "decrypt"]
        );
    };

    const encryptData = async (text, key) => {
        if (!text) return "";
        const enc = new TextEncoder();
        const iv = window.crypto.getRandomValues(new Uint8Array(12));
        const encrypted = await window.crypto.subtle.encrypt(
            { name: "AES-GCM", iv: iv }, key, enc.encode(text)
        );
        return btoa(JSON.stringify({ iv: Array.from(iv), data: Array.from(new Uint8Array(encrypted)) }));
    };

    const decryptData = async (encryptedBase64, key) => {
        if (!encryptedBase64) return "";
        try {
            const { iv, data } = JSON.parse(atob(encryptedBase64));
            const decrypted = await window.crypto.subtle.decrypt(
                { name: "AES-GCM", iv: new Uint8Array(iv) }, key, new Uint8Array(data)
            );
            return new TextDecoder().decode(decrypted);
        } catch (e) {
            return "[Ошибка расшифровки]";
        }
    };

    const fetchServers = async (attempt = 0) => {
        if (attempt === 0 && !serversLoaded) {
            renderSavedServers();
        }

        try {
            const res = await fetch('/api/servers', { cache: 'no-store' });
            if (!res.ok) {
                throw new Error(`HTTP ${res.status}`);
            }

            const data = await res.json();
            serversList = Array.isArray(data) ? data : [];
            serversLoaded = true;
            serversLoadError = '';
            renderSavedServers();
        } catch(e) {
            console.error('Failed to fetch servers', e);

            // The local server may need a few seconds to come back after
            // "Перезапустить UI". Retry frequently so the unlock card does
            // not remain hidden behind the initial placeholder for ~12 sec.
            if (attempt < 20) {
                const delay = 350;
                setTimeout(() => fetchServers(attempt + 1), delay);
                return;
            }

            serversLoaded = true;
            serversLoadError = 'Список серверов временно недоступен';
            renderSavedServers();
        }
    };

    const saveServersToBackend = async () => {
        try {
            await fetch('/api/servers', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(serversList)
            });
        } catch(e) {
            showToast('Ошибка сохранения на сервер', 'error');
        }
    };

    let pendingSaveAfterPin = false;

    const promptMasterPassword = (saveAfterUnlock = false) => {
        pendingSaveAfterPin = saveAfterUnlock;
        masterPasswordModal.classList.add('active');
        if (pinInputs.length > 0) {
            pinInputs.forEach(inp => inp.value = '');
            setTimeout(() => pinInputs[0].focus(), 100);
        }
    };

    const renderSavedServers = async () => {
        if (!savedServersList) return;

        if (serversLoadError) {
            savedServersList.innerHTML = `
                <div style="text-align: center; padding: 20px 10px; background: rgba(255,255,255,0.05); border-radius: 8px; margin-top: 10px; border: 1px dashed var(--border-color);">
                    <div style="margin-bottom: 12px; font-size: 0.95rem; color: var(--text-secondary);">${serversLoadError}</div>
                    <button type="button" class="btn btn-primary" id="btnRetryServers" style="width: 100%;">
                        Повторить загрузку
                    </button>
                </div>
            `;
            document.getElementById('btnRetryServers')?.addEventListener('click', (e) => {
                e.preventDefault();
                fetchServers(0);
            });
            return;
        }

        if (!serversLoaded) {
            savedServersList.innerHTML = '<div style="color: var(--text-secondary); font-size: 0.85rem; text-align: center; margin-top: 10px;">Загрузка сохраненных серверов...</div>';
            return;
        }

        if (serversList.length === 0) {
            savedServersList.innerHTML = '<div style="color: var(--text-secondary); font-size: 0.85rem; text-align: center; margin-top: 10px;">Нет сохраненных серверов</div>';
            return;
        }

        if (!cryptoKey) {
            savedServersList.innerHTML = `
                <div style="text-align: center; padding: 20px 10px; background: rgba(255,255,255,0.05); border-radius: 8px; margin-top: 10px; border: 1px dashed var(--border-color);">
                    <svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="color: var(--text-secondary); margin-bottom: 10px;"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
                    <div style="margin-bottom: 15px; font-size: 0.95rem; color: var(--text-secondary);">Хранилище серверов защищено PIN-кодом</div>
                    <button type="button" class="btn btn-primary" id="btnUnlockStorage" style="width: 100%;">
                        Разблокировать
                    </button>
                </div>
            `;
            document.getElementById('btnUnlockStorage').addEventListener('click', (e) => {
                e.preventDefault();
                promptMasterPassword();
            });
            return;
        }

        savedServersList.innerHTML = '';

        const typeNames = {
            'proxy_host': 'Proxy (Вход)',
            'freedom_host': 'Freedom (Выход)',
            'sub_vps_host': 'Подписки',
            'vps_host': 'Одиночный',
            'backup_vps_host': 'Бэкап',
            'recovery_vps_host': 'Восстановление',
            'update_vps_host': 'Обновление'
        };

        for (let index = 0; index < serversList.length; index++) {
            const srv = serversList[index];
            const badge = srv.target_type && typeNames[srv.target_type] 
                ? `<span class="server-card-badge">${typeNames[srv.target_type]}</span>` 
                : '';
            const card = document.createElement('div');
            card.className = 'server-card';
            card.innerHTML = `
                <div class="server-card-info">
                    ${badge}
                    <div class="server-card-host">${srv.host || 'Без IP'}</div>
                    <div class="server-card-details">
                        <span>👤 ${srv.user || 'root'}</span>
                        <span>🔌 ${srv.port || 22}</span>
                    </div>
                </div>
                <div class="server-card-actions">
                    <button type="button" class="btn-icon-sm" title="Заполнить поля" onclick="window.fillServerData(${index})">
                        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><path d="M12 18v-6"/><path d="M9 15h6"/></svg>
                    </button>
                    <button type="button" class="btn-icon-sm" title="Копировать пароль" onclick="window.copyServerPass(${index})">
                        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
                    </button>
                    <button type="button" class="btn-icon-sm" title="Редактировать" onclick="window.editServer(${index})">
                        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z"/></svg>
                    </button>
                    <button type="button" class="btn-icon-sm danger" title="Удалить" onclick="window.deleteServer(${index})">
                        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><line x1="10" y1="11" x2="10" y2="17"/><line x1="14" y1="11" x2="14" y2="17"/></svg>
                    </button>
                </div>
            `;
            savedServersList.appendChild(card);
        }
    };

    window.applyServerData = async (index, hostId) => {
        const srv = serversList[index];
        if (!srv) return;
        
        let prefix = hostId.replace('_host', '');
        
        const elHost = document.getElementById(hostId);
        if (elHost) elHost.value = srv.host || '';
        
        if (hostId === 'backup_vps_host') updateBackupName();
        
        const elPort = document.getElementById(`${prefix}_port`);
        if (elPort) elPort.value = srv.port || 22;
        
        const elUser = document.getElementById(`${prefix}_user`);
        if (elUser) elUser.value = srv.user || 'root';
        
        const authType = srv.auth_type === 'key' ? 'key' : 'password';
        const elAuthType = document.getElementById(`${prefix}_auth_type`);
        if (elAuthType) {
            elAuthType.value = authType;
            elAuthType.dispatchEvent(new Event('change', { bubbles: true }));
        }
        
        const pass = await decryptData(srv.enc_pass, cryptoKey);
        const elPass = document.getElementById(`${prefix}_password`);
        if (elPass) elPass.value = pass || '';
        
        const key = srv.enc_key ? await decryptData(srv.enc_key, cryptoKey) : '';
        const elKey = document.getElementById(`${prefix}_key`);
        if (elKey) elKey.value = key || '';

        if (glowRefresher) glowRefresher();

        showToast('Данные сервера успешно подставлены!', 'success');
    };

    window.fillServerData = async (index) => {
        if (!cryptoKey) { showToast('Сначала разблокируйте список', 'warning'); return; }
        const srv = serversList[index];
        if (!srv) return;

        // Auto-match if target_type is defined and visible
        if (srv.target_type) {
            const targetEl = document.getElementById(srv.target_type);
            if (targetEl && targetEl.offsetParent !== null) {
                applyServerData(index, srv.target_type);
                return;
            }
            // Fallback: if target field is hidden (e.g. freedom_host in single mode),
            // try vps_host if it's visible
            const vpsHost = document.getElementById('vps_host');
            if (vpsHost && vpsHost.offsetParent !== null) {
                applyServerData(index, 'vps_host');
                return;
            }
        }

        const hostsInfo = [
            { id: 'vps_host', name: 'Одиночный сервер' },
            { id: 'proxy_host', name: 'Proxy сервер (Вход)' },
            { id: 'freedom_host', name: 'Freedom сервер (Выход)' },
            { id: 'sub_vps_host', name: 'Сервер подписок' },
            { id: 'backup_vps_host', name: 'Сервер для бэкапа' },
            { id: 'recovery_vps_host', name: 'Сервер для восстановления' },
            { id: 'update_vps_host', name: 'Сервер для обновления' }
        ];

        const visibleHosts = hostsInfo.filter(h => {
            const el = document.getElementById(h.id);
            return el && el.offsetParent !== null;
        }).sort((a, b) => {
            const rectA = document.getElementById(a.id).getBoundingClientRect();
            const rectB = document.getElementById(b.id).getBoundingClientRect();
            return rectA.top - rectB.top;
        });
        
        if (visibleHosts.length === 0) {
            showToast('Сначала выберите режим и перейдите на шаг 2, чтобы было куда подставить данные.', 'warning');
            return;
        }
        
        if (visibleHosts.length === 1) {
            applyServerData(index, visibleHosts[0].id);
        } else {
            const container = document.getElementById('fillServerButtons');
            if (!container) return;
            container.innerHTML = '';
            visibleHosts.forEach(h => {
                const btn = document.createElement('button');
                btn.className = 'btn btn-primary';
                btn.style.width = '100%';
                btn.textContent = h.name;
                btn.onclick = () => {
                    applyServerData(index, h.id);
                    document.getElementById('fillServerModal').classList.remove('active');
                };
                container.appendChild(btn);
            });
            document.getElementById('fillServerModal').classList.add('active');
        }
    };
    
    const btnCancelFillServer = document.getElementById('btnCancelFillServer');
    if (btnCancelFillServer) {
        btnCancelFillServer.addEventListener('click', () => {
            document.getElementById('fillServerModal').classList.remove('active');
        });
    }

    window.copyServerPass = async (index) => {
        if (!cryptoKey) { showToast('Сначала разблокируйте список', 'warning'); return; }
        const srv = serversList[index];
        const secret = srv && (srv.enc_pass || srv.enc_key);
        if (secret) {
            const value = await decryptData(secret, cryptoKey);
            if (value === "[Ошибка расшифровки]") {
                showToast('Неверный PIN-код. Невозможно расшифровать.', 'error');
                return;
            }
            navigator.clipboard.writeText(value)
                .then(() => showToast('Пароль/Ключ скопирован в буфер обмена', 'success'))
                .catch(() => showToast('Не удалось скопировать. Разрешите доступ к буферу обмена.', 'error'));
        } else {
            showToast('Пароль/Ключ не задан для этого сервера.', 'warning');
        }
    };

    const btnCancelEditServer = document.getElementById('btnCancelEditServer');
    const btnSaveServerText = document.getElementById('btnSaveServerText');

    const setEditingMode = (index) => {
        editingServerIndex = index;
        if (btnSaveServerText) btnSaveServerText.textContent = index === null ? 'Сохранить сервер' : 'Обновить сервер';
        if (btnCancelEditServer) btnCancelEditServer.style.display = index === null ? 'none' : 'block';
    };

    window.editServer = async (index) => {
        if (!cryptoKey) { showToast('Сначала разблокируйте список', 'warning'); return; }
        const srv = serversList[index];
        if (!srv) return;

        if (smTargetType) {
            smTargetType.value = srv.target_type || '';
            smTargetType.dispatchEvent(new Event('change', { bubbles: true }));
        }
        smHost.value = srv.host || '';
        smUser.value = srv.user || 'root';
        smPort.value = srv.port || 22;

        const authType = srv.auth_type === 'key' ? 'key' : 'password';
        if (smAuthType) {
            smAuthType.value = authType;
            smAuthType.dispatchEvent(new Event('change', { bubbles: true }));
        }

        const pass = srv.enc_pass ? await decryptData(srv.enc_pass, cryptoKey) : '';
        const key = srv.enc_key ? await decryptData(srv.enc_key, cryptoKey) : '';
        if (pass === "[Ошибка расшифровки]") {
            showToast('Неверный PIN-код. Невозможно расшифровать.', 'error');
            return;
        }
        smPass.value = authType === 'key' ? '' : (pass || '');
        smKey.value = authType === 'key' ? (key || '') : '';

        setEditingMode(index);
        if (glowRefresher) glowRefresher();

        showToast('Редактирование сервера. Внесите изменения и нажмите «Обновить сервер».', 'success');
    };

    window.cancelEditServer = () => {
        setEditingMode(null);
        if (smTargetType) {
            smTargetType.value = '';
            smTargetType.dispatchEvent(new Event('change', { bubbles: true }));
        }
        smHost.value = '';
        smPass.value = '';
        smKey.value = '';
        smUser.value = 'root';
        smPort.value = '22';
        if (smAuthType) {
            smAuthType.value = 'password';
            smAuthType.dispatchEvent(new Event('change', { bubbles: true }));
        }
        showToast('Редактирование отменено', 'success');
    };

    window.deleteServer = async (index) => {
        if (!await showConfirm('Удалить этот сервер из сохраненных?', 'Удаление сервера', { confirmText: 'Удалить', danger: true, icon: '🗑️' })) return;
        serversList.splice(index, 1);
        if (editingServerIndex !== null) {
            if (editingServerIndex === index) {
                setEditingMode(null);
                if (window.cancelEditServer) window.cancelEditServer();
            } else if (editingServerIndex > index) {
                editingServerIndex--;
            }
        }
        await saveServersToBackend();
        renderSavedServers();
    };

    if (btnResetServers) {
        btnResetServers.addEventListener('click', async () => {
            if (!await showConfirm('ВНИМАНИЕ! Это действие удалит файл со всеми сохраненными серверами и сбросит PIN-код. Продолжить?', 'Сброс всех серверов', { confirmText: 'Сбросить все', danger: true, icon: '⚠️' })) return;
            try {
                await fetch('/api/servers/reset', { method: 'DELETE' });
                serversList = [];
                serversLoaded = true;
                serversLoadError = '';
                cryptoKey = null;
                showToast('Все серверы удалены. PIN-код сброшен.', 'success');
                renderSavedServers();
            } catch(e) {
                showToast('Ошибка сброса.', 'error');
            }
        });
    }

    const doSaveServer = async () => {
            const host = smHost.value.trim();
            if (!host) {
                showToast('Укажите IP или Домен сервера', 'warning');
                return;
            }
            
            const authType = smAuthType ? smAuthType.value : 'password';
            const plainPass = authType === 'key' ? '' : smPass.value;
            const plainKey = authType === 'key' ? smKey.value : '';
            const encPass = await encryptData(plainPass, cryptoKey);
            const encKey = await encryptData(plainKey, cryptoKey);

            const newData = {
                target_type: smTargetType ? smTargetType.value : '',
                auth_type: authType,
                host: host,
                user: smUser.value.trim() || 'root',
                port: smPort.value || 22,
                enc_pass: encPass,
                enc_key: encKey
            };

            if (editingServerIndex !== null && serversList[editingServerIndex]) {
                serversList[editingServerIndex] = newData;
            } else {
                serversList.push(newData);
            }
            setEditingMode(null);
            
            await saveServersToBackend();
            
            if (smTargetType) {
                smTargetType.value = '';
                smTargetType.dispatchEvent(new Event('change', { bubbles: true }));
            }
            smHost.value = '';
            smPass.value = '';
            smKey.value = '';
            smUser.value = 'root';
            smPort.value = '22';
            if (smAuthType) {
                smAuthType.value = 'password';
                smAuthType.dispatchEvent(new Event('change', { bubbles: true }));
            }
            
            renderSavedServers();
        };

    if (btnSaveServer) {
        btnSaveServer.addEventListener('click', async () => {
            if (!cryptoKey) {
                promptMasterPassword(true);
                return;
            }
            await doSaveServer();
        });
    }

    if (btnCancelEditServer) {
        btnCancelEditServer.addEventListener('click', () => {
            window.cancelEditServer();
        });
    }

    const submitMasterPassword = async () => {
        const pass = Array.from(pinInputs).map(i => i.value).join('');
        if (!/^\d{5}$/.test(pass)) {
            showToast('PIN-код должен состоять ровно из 5 цифр!', 'warning');
            return;
        }
        const tmpKey = await deriveKey(pass);
        
        if (serversList.length > 0) {
            const testSrv = serversList.find(s => s.enc_pass || s.enc_key);
            if (testSrv) {
                const testSecret = await decryptData(testSrv.enc_pass || testSrv.enc_key, tmpKey);
                if (testSecret === "[Ошибка расшифровки]") {
                    showToast('Неверный PIN-код!', 'error');
                    pinInputs.forEach(inp => inp.value = '');
                    if (pinInputs.length > 0) pinInputs[0].focus();
                    return;
                }
            }
        }
        
        cryptoKey = tmpKey;
        masterPasswordModal.classList.remove('active');

        if (pendingSaveAfterPin) {
            pendingSaveAfterPin = false;
            await doSaveServer();
        } else {
            renderSavedServers();
        }
    };
    
    if (btnCancelMasterPassword) {
        btnCancelMasterPassword.addEventListener('click', () => {
            masterPasswordModal.classList.remove('active');
        });
    }

    // Global modal close events
    document.addEventListener('click', (e) => {
        if (e.target.classList.contains('modal-overlay')) {
            e.target.classList.remove('active');
        }
    });

    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            document.querySelectorAll('.modal-overlay.active').forEach(modal => {
                modal.classList.remove('active');
            });
        }
    });

    fetchServers();
});
