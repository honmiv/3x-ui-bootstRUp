document.addEventListener('DOMContentLoaded', () => {
    const randomDigits = (len = 16) => {
        let res = '';
        for (let i = 0; i < len; i++) res += Math.floor(Math.random() * 10);
        return res;
    };

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

    const qrModal = document.getElementById('qrModal');
    const qrModalImg = document.getElementById('qrModalImg');
    const qrModalTitle = document.getElementById('qrModalTitle');
    const qrModalUrl = document.getElementById('qrModalUrl');
    const btnCloseQr = document.getElementById('btnCloseQr');

    const fetchBackupList = async () => {
        try {
            const res = await fetch('/api/backups');
            if (!res.ok) return;
            const files = await res.json();
            const select = document.getElementById('recovery_backup_file');
            const selectedSpan = document.getElementById('recoveryBackupSelected');
            const dropdown = document.getElementById('recoveryBackupDropdown');
            if (!select || !selectedSpan || !dropdown) return;

            select.innerHTML = '<option value="">-- Выберите архив --</option>';
            dropdown.innerHTML = '';

            if (!files || files.length === 0) {
                selectedSpan.textContent = 'Архивы бэкапов не найдены в ./backups/';
                dropdown.innerHTML = '<div class="custom-select-option text-muted" style="padding:10px; color:#94a3b8;">Архивы не найдены в ./backups/</div>';
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
                    document.querySelectorAll('#recoveryBackupDropdown .custom-select-option').forEach(el => el.classList.remove('selected'));
                    div.classList.add('selected');
                });
                dropdown.appendChild(div);
            });

            if (files.length > 0 && !select.value) {
                select.value = files[0].name;
                selectedSpan.textContent = `${files[0].name} (${files[0].size})`;
                if (dropdown.children[0]) dropdown.children[0].classList.add('selected');
            }
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
        document.addEventListener('click', () => {
            recDropdown.classList.add('hidden');
        });
    }

    const hideQrModal = () => {
        if (qrModal) qrModal.classList.add('hidden');
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
        if (e.key === 'Escape' && !qrModal.classList.contains('hidden')) {
            hideQrModal();
        }
    });

    const showQrModal = (title, url) => {
        qrModalTitle.textContent = title;
        qrModalUrl.textContent = url;
        qrModalImg.src = `https://api.qrserver.com/v1/create-qr-code/?data=${encodeURIComponent(url)}&size=250x250`;
        qrModal.classList.remove('hidden');
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
                    <div class="topology-stage-title">1. Получение подписки (Прямо с нод)</div>
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
                            <span class="node-title">Proxy Node</span>
                            <span class="node-desc">Входной сервер</span>
                            <span class="topology-badge topology-badge-configurable">🇷🇺</span>
                        </div>
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
                    <div class="topology-stage-title">1. Получение подписки (Прямо с нод)</div>
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
                        <div class="topology-node">
                            <span class="node-icon">🖧</span>
                            <span class="node-title">Proxy Node</span>
                            <span class="node-desc">Входной сервер</span>
                            <span class="topology-badge topology-badge-ru">🇷🇺</span>
                        </div>
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
                            <span class="node-desc">./backups/backup.tar.gz</span>
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
                            <span class="node-desc">./backups/backup.tar.gz</span>
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
                            <span class="node-desc">./backups/backup.tar.gz</span>
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
        }
        diagramEl.innerHTML = html;
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
        const subOnlyTargetGroup = document.getElementById('subOnlyTargetGroup');
        const subWarningBanner = document.getElementById('subWarningBanner');
        const devModeWarning = document.getElementById('devModeWarning');
        const devModeWarningStep1 = document.getElementById('devModeWarningStep1');
        const isDevMode = mode === 'proxy_only' || mode === 'sub_only' || mode === 'backup' || mode === 'recovery' || mode === 'update_3xui';

        if (subWarningBanner) {
            subWarningBanner.classList[isDevMode ? 'remove' : 'add']('hidden');
        }

        if (devModeWarning) {
            devModeWarning.classList[isDevMode ? 'remove' : 'add']('hidden');
        }
        if (devModeWarningStep1) {
            devModeWarningStep1.classList[isDevMode ? 'remove' : 'add']('hidden');
        }

        renderTopologyDiagram(mode);

        if (backupNodeSection) backupNodeSection.classList.add('hidden');
        if (recoveryNodeSection) recoveryNodeSection.classList.add('hidden');
        if (updateNodeSection) updateNodeSection.classList.add('hidden');
        if (backupPanelSection) backupPanelSection.classList.add('hidden');
        if (recoveryPanelSection) recoveryPanelSection.classList.add('hidden');
        if (updatePanelSection) updatePanelSection.classList.add('hidden');

        if (mode === 'single' || mode === 'proxy_only' || mode === 'freedom_only') {
            singleNodeSection.classList.remove('hidden');
            cascadeNodeSection.classList.add('hidden');
            subServerSshSection.classList.add('hidden');

            if (xuiVersionBlock) xuiVersionBlock.classList.remove('hidden');
            if (singlePanelSection) singlePanelSection.classList.remove('hidden');
            if (cascadePanelSection) cascadePanelSection.classList.add('hidden');
            if (subServerPanelSection) subServerPanelSection.classList.add('hidden');
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
            fetchBackupList();
        } else if (mode === 'update_3xui') {
            singleNodeSection.classList.add('hidden');
            cascadeNodeSection.classList.add('hidden');
            subServerSshSection.classList.add('hidden');

            if (updateNodeSection) updateNodeSection.classList.remove('hidden');
            if (xuiVersionBlock) xuiVersionBlock.classList.add('hidden');
            if (singlePanelSection) singlePanelSection.classList.add('hidden');
            if (cascadePanelSection) cascadePanelSection.classList.add('hidden');
            if (subServerPanelSection) subServerPanelSection.classList.add('hidden');
            if (updatePanelSection) updatePanelSection.classList.remove('hidden');
        }
        resetSSHValidation();
    };

    document.querySelectorAll('input[name="deploy_mode"]').forEach(radio => {
        radio.addEventListener('change', updateModeUI);
    });

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
        });
    });

    const initCustomSelects = () => {
        document.querySelectorAll('.auth-type-select').forEach(select => {
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
                vps_password: document.getElementById('vps_password').value,
                vps_key: document.getElementById('vps_key').value,
                vps_auth_type: document.getElementById('vps_auth_type').value,

                freedom_host: document.getElementById('freedom_host').value.trim(),
                freedom_port: parseInt(document.getElementById('freedom_port').value) || 22,
                freedom_user: document.getElementById('freedom_user').value.trim() || 'root',
                freedom_password: document.getElementById('freedom_password').value,
                freedom_key: document.getElementById('freedom_key').value,
                freedom_auth_type: document.getElementById('freedom_auth_type').value,
                freedom_xui_username: document.getElementById('freedom_xui_username').value.trim(),
                freedom_xui_password: document.getElementById('freedom_xui_password').value.trim(),
                freedom_sub_secret: document.getElementById('freedom_sub_secret').value.trim(),
                freedom_client_name: document.getElementById('freedom_client_name').value.trim(),

                proxy_host: document.getElementById('proxy_host').value.trim(),
                proxy_port: parseInt(document.getElementById('proxy_port').value) || 22,
                proxy_user: document.getElementById('proxy_user').value.trim() || 'root',
                proxy_password: document.getElementById('proxy_password').value,
                proxy_key: document.getElementById('proxy_key').value,
                proxy_auth_type: document.getElementById('proxy_auth_type').value,
                proxy_xui_username: document.getElementById('proxy_xui_username').value.trim(),
                proxy_xui_password: document.getElementById('proxy_xui_password').value.trim(),
                proxy_sub_secret: document.getElementById('proxy_sub_secret').value.trim(),
                proxy_client_tcp_list: document.getElementById('proxy_client_tcp_list').value.trim(),
                proxy_client_xhttp_list: document.getElementById('proxy_client_xhttp_list').value.trim(),

                sub_vps_host: document.getElementById('sub_vps_host').value.trim(),
                sub_vps_port: parseInt(document.getElementById('sub_vps_port').value) || 22,
                sub_vps_user: document.getElementById('sub_vps_user').value.trim() || 'root',
                sub_vps_password: document.getElementById('sub_vps_password').value,
                sub_vps_key: document.getElementById('sub_vps_key').value,
                sub_auth_type: document.getElementById('sub_auth_type').value,
                sub_domain: document.getElementById('sub_domain') ? document.getElementById('sub_domain').value.trim() : document.getElementById('sub_vps_host').value.trim(),
                sub_secret_path: document.getElementById('sub_secret_path').value.trim(),
                sub_russian_url: document.getElementById('sub_russian_url').value.trim(),
                sub_foreign_url: document.getElementById('sub_foreign_url').value.trim(),
                sub_proxy_clients: document.getElementById('sub_proxy_clients').value.trim(),
                sub_freedom_clients: document.getElementById('sub_freedom_clients').value.trim(),
                sub_same_as_proxy: subSameAsProxy ? subSameAsProxy.checked : true,

                backup_vps_host: document.getElementById('backup_vps_host') ? document.getElementById('backup_vps_host').value.trim() : '',
                backup_vps_port: document.getElementById('backup_vps_port') ? parseInt(document.getElementById('backup_vps_port').value) || 22 : 22,
                backup_vps_user: document.getElementById('backup_vps_user') ? document.getElementById('backup_vps_user').value.trim() || 'root' : 'root',
                backup_vps_password: document.getElementById('backup_vps_password') ? document.getElementById('backup_vps_password').value : '',
                backup_vps_key: document.getElementById('backup_vps_key') ? document.getElementById('backup_vps_key').value : '',
                backup_auth_type: document.getElementById('backup_auth_type') ? document.getElementById('backup_auth_type').value : 'password',
                backup_name: document.getElementById('backup_name') ? document.getElementById('backup_name').value.trim() : '',

                recovery_vps_host: document.getElementById('recovery_vps_host') ? document.getElementById('recovery_vps_host').value.trim() : '',
                recovery_vps_port: document.getElementById('recovery_vps_port') ? parseInt(document.getElementById('recovery_vps_port').value) || 22 : 22,
                recovery_vps_user: document.getElementById('recovery_vps_user') ? document.getElementById('recovery_vps_user').value.trim() || 'root' : 'root',
                recovery_vps_password: document.getElementById('recovery_vps_password') ? document.getElementById('recovery_vps_password').value : '',
                recovery_vps_key: document.getElementById('recovery_vps_key') ? document.getElementById('recovery_vps_key').value : '',
                recovery_auth_type: document.getElementById('recovery_auth_type') ? document.getElementById('recovery_auth_type').value : 'password',
                recovery_backup_file: document.getElementById('recovery_backup_file') ? document.getElementById('recovery_backup_file').value : '',

                update_vps_host: document.getElementById('update_vps_host') ? document.getElementById('update_vps_host').value.trim() : '',
                update_vps_port: document.getElementById('update_vps_port') ? parseInt(document.getElementById('update_vps_port').value) || 22 : 22,
                update_vps_user: document.getElementById('update_vps_user') ? document.getElementById('update_vps_user').value.trim() || 'root' : 'root',
                update_vps_password: document.getElementById('update_vps_password') ? document.getElementById('update_vps_password').value : '',
                update_vps_key: document.getElementById('update_vps_key') ? document.getElementById('update_vps_key').value : '',
                update_auth_type: document.getElementById('update_auth_type') ? document.getElementById('update_auth_type').value : 'password',
                update_xui_version: document.getElementById('update_xui_version') ? document.getElementById('update_xui_version').value.trim() : '3.6.0',

                xui_username: document.getElementById('xui_username').value.trim(),
                xui_password: document.getElementById('xui_password').value.trim(),
                sub_secret: document.getElementById('sub_secret').value.trim(),
                xui_version: document.getElementById('xui_version') ? document.getElementById('xui_version').value.trim() : '3.6.0',
                client_tcp_list: document.getElementById('client_tcp_list').value.trim(),
                client_xhttp_list: document.getElementById('client_xhttp_list').value.trim()
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
                let mode = cfg.deploy_mode;
                if (!mode) {
                    mode = cfg.is_cascade ? 'cascade' : 'single';
                }
                const radioToSelect = document.querySelector(`input[name="deploy_mode"][value="${mode}"]`);
                if (radioToSelect) radioToSelect.checked = true;

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

                if (cfg.vps_host) document.getElementById('vps_host').value = cfg.vps_host;
                if (cfg.vps_port) document.getElementById('vps_port').value = cfg.vps_port;
                if (cfg.vps_user) document.getElementById('vps_user').value = cfg.vps_user;
                if (cfg.vps_password) document.getElementById('vps_password').value = cfg.vps_password;
                if (cfg.vps_key) document.getElementById('vps_key').value = cfg.vps_key;
                setAuthSelect('vps_auth_type', 'vpsPassGroup', 'vpsKeyGroup', cfg.vps_auth_type, cfg.vps_key);

                if (cfg.freedom_host) document.getElementById('freedom_host').value = cfg.freedom_host;
                if (cfg.freedom_port) document.getElementById('freedom_port').value = cfg.freedom_port;
                if (cfg.freedom_user) document.getElementById('freedom_user').value = cfg.freedom_user;
                if (cfg.freedom_password) document.getElementById('freedom_password').value = cfg.freedom_password;
                if (cfg.freedom_key) document.getElementById('freedom_key').value = cfg.freedom_key;
                setAuthSelect('freedom_auth_type', 'freedomPassGroup', 'freedomKeyGroup', cfg.freedom_auth_type, cfg.freedom_key);
                if (cfg.freedom_xui_username) document.getElementById('freedom_xui_username').value = cfg.freedom_xui_username;
                if (cfg.freedom_xui_password) document.getElementById('freedom_xui_password').value = cfg.freedom_xui_password;
                if (cfg.freedom_sub_secret) {
                    document.getElementById('freedom_sub_secret').value = cfg.freedom_sub_secret;
                } else if (document.getElementById('freedom_sub_secret') && !document.getElementById('freedom_sub_secret').value) {
                    document.getElementById('freedom_sub_secret').value = randomDigits(16);
                }
                if (cfg.freedom_client_name) document.getElementById('freedom_client_name').value = cfg.freedom_client_name;

                if (cfg.proxy_host) document.getElementById('proxy_host').value = cfg.proxy_host;
                if (cfg.proxy_port) document.getElementById('proxy_port').value = cfg.proxy_port;
                if (cfg.proxy_user) document.getElementById('proxy_user').value = cfg.proxy_user;
                if (cfg.proxy_password) document.getElementById('proxy_password').value = cfg.proxy_password;
                if (cfg.proxy_key) document.getElementById('proxy_key').value = cfg.proxy_key;
                setAuthSelect('proxy_auth_type', 'proxyPassGroup', 'proxyKeyGroup', cfg.proxy_auth_type, cfg.proxy_key);
                if (cfg.proxy_xui_username) document.getElementById('proxy_xui_username').value = cfg.proxy_xui_username;
                if (cfg.proxy_xui_password) document.getElementById('proxy_xui_password').value = cfg.proxy_xui_password;
                if (cfg.proxy_sub_secret) {
                    document.getElementById('proxy_sub_secret').value = cfg.proxy_sub_secret;
                } else if (document.getElementById('proxy_sub_secret') && !document.getElementById('proxy_sub_secret').value) {
                    document.getElementById('proxy_sub_secret').value = randomDigits(16);
                }
                if (cfg.proxy_client_tcp_list) document.getElementById('proxy_client_tcp_list').value = cfg.proxy_client_tcp_list;
                if (cfg.proxy_client_xhttp_list) document.getElementById('proxy_client_xhttp_list').value = cfg.proxy_client_xhttp_list;

                if (cfg.sub_vps_host) document.getElementById('sub_vps_host').value = cfg.sub_vps_host;
                if (cfg.sub_vps_port) document.getElementById('sub_vps_port').value = cfg.sub_vps_port;
                if (cfg.sub_vps_user) document.getElementById('sub_vps_user').value = cfg.sub_vps_user;
                if (cfg.sub_vps_password) document.getElementById('sub_vps_password').value = cfg.sub_vps_password;
                if (cfg.sub_vps_key) document.getElementById('sub_vps_key').value = cfg.sub_vps_key;
                setAuthSelect('sub_auth_type', 'subPassGroup', 'subKeyGroup', cfg.sub_auth_type, cfg.sub_vps_key);
                if (cfg.sub_domain && document.getElementById('sub_domain')) document.getElementById('sub_domain').value = cfg.sub_domain;
                if (cfg.sub_secret_path) document.getElementById('sub_secret_path').value = cfg.sub_secret_path;
                if (cfg.sub_russian_url) document.getElementById('sub_russian_url').value = cfg.sub_russian_url;
                if (cfg.sub_foreign_url) document.getElementById('sub_foreign_url').value = cfg.sub_foreign_url;
                if (cfg.sub_proxy_clients) document.getElementById('sub_proxy_clients').value = cfg.sub_proxy_clients;
                if (cfg.sub_freedom_clients) document.getElementById('sub_freedom_clients').value = cfg.sub_freedom_clients;
                if (cfg.sub_same_as_proxy !== undefined && subSameAsProxy) subSameAsProxy.checked = cfg.sub_same_as_proxy;

                if (cfg.backup_vps_host && document.getElementById('backup_vps_host')) document.getElementById('backup_vps_host').value = cfg.backup_vps_host;
                if (cfg.backup_vps_port && document.getElementById('backup_vps_port')) document.getElementById('backup_vps_port').value = cfg.backup_vps_port;
                if (cfg.backup_vps_user && document.getElementById('backup_vps_user')) document.getElementById('backup_vps_user').value = cfg.backup_vps_user;
                if (cfg.backup_vps_password && document.getElementById('backup_vps_password')) document.getElementById('backup_vps_password').value = cfg.backup_vps_password;
                if (cfg.backup_vps_key && document.getElementById('backup_vps_key')) document.getElementById('backup_vps_key').value = cfg.backup_vps_key;
                setAuthSelect('backup_auth_type', 'backupPassGroup', 'backupKeyGroup', cfg.backup_auth_type, cfg.backup_vps_key);
                if (cfg.backup_name && document.getElementById('backup_name')) document.getElementById('backup_name').value = cfg.backup_name;

                if (cfg.recovery_vps_host && document.getElementById('recovery_vps_host')) document.getElementById('recovery_vps_host').value = cfg.recovery_vps_host;
                if (cfg.recovery_vps_port && document.getElementById('recovery_vps_port')) document.getElementById('recovery_vps_port').value = cfg.recovery_vps_port;
                if (cfg.recovery_vps_user && document.getElementById('recovery_vps_user')) document.getElementById('recovery_vps_user').value = cfg.recovery_vps_user;
                if (cfg.recovery_vps_password && document.getElementById('recovery_vps_password')) document.getElementById('recovery_vps_password').value = cfg.recovery_vps_password;
                if (cfg.recovery_vps_key && document.getElementById('recovery_vps_key')) document.getElementById('recovery_vps_key').value = cfg.recovery_vps_key;
                setAuthSelect('recovery_auth_type', 'recoveryPassGroup', 'recoveryKeyGroup', cfg.recovery_auth_type, cfg.recovery_vps_key);

                if (cfg.update_vps_host && document.getElementById('update_vps_host')) document.getElementById('update_vps_host').value = cfg.update_vps_host;
                if (cfg.update_vps_port && document.getElementById('update_vps_port')) document.getElementById('update_vps_port').value = cfg.update_vps_port;
                if (cfg.update_vps_user && document.getElementById('update_vps_user')) document.getElementById('update_vps_user').value = cfg.update_vps_user;
                if (cfg.update_vps_password && document.getElementById('update_vps_password')) document.getElementById('update_vps_password').value = cfg.update_vps_password;
                if (cfg.update_vps_key && document.getElementById('update_vps_key')) document.getElementById('update_vps_key').value = cfg.update_vps_key;
                setAuthSelect('update_auth_type', 'updatePassGroup', 'updateKeyGroup', cfg.update_auth_type, cfg.update_vps_key);
                if (cfg.update_xui_version && document.getElementById('update_xui_version')) document.getElementById('update_xui_version').value = cfg.update_xui_version;

                if (cfg.xui_username) document.getElementById('xui_username').value = cfg.xui_username;
                if (cfg.xui_password) document.getElementById('xui_password').value = cfg.xui_password;
                if (cfg.sub_secret) {
                    document.getElementById('sub_secret').value = cfg.sub_secret;
                } else if (!document.getElementById('sub_secret').value) {
                    document.getElementById('sub_secret').value = randomDigits(16);
                }
                if (cfg.xui_version && document.getElementById('xui_version')) document.getElementById('xui_version').value = cfg.xui_version;
                if (cfg.client_tcp_list) document.getElementById('client_tcp_list').value = cfg.client_tcp_list;
                if (cfg.client_xhttp_list) document.getElementById('client_xhttp_list').value = cfg.client_xhttp_list;

                updateModeUI();
            } else {
                if (!document.getElementById('sub_secret').value) document.getElementById('sub_secret').value = randomDigits(16);
                if (document.getElementById('freedom_sub_secret') && !document.getElementById('freedom_sub_secret').value) document.getElementById('freedom_sub_secret').value = randomDigits(16);
                if (document.getElementById('proxy_sub_secret') && !document.getElementById('proxy_sub_secret').value) document.getElementById('proxy_sub_secret').value = randomDigits(16);
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
        btnNextStep3.addEventListener('click', () => showStep(4));
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
                if (mode === 'single' || mode === 'proxy_only' || mode === 'freedom_only') {
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

    const appendLog = (message, level = 'info') => {
        const line = document.createElement('div');
        line.className = `log-line ${level}`;
        line.textContent = message;
        terminalLogs.appendChild(line);

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
            if (!confirm('Вы уверены, что хотите остановить процесс развертывания?')) return;
            btnStopDeploy.disabled = true;
            btnStopDeploy.textContent = '⏳ Остановка...';
            appendLog('[CANCEL] Запрос остановки процесса пользователем...', 'warning');

            try {
                const res = await fetch('/api/deploy/stop', { method: 'POST' });
                const data = await res.json();
                if (!data.ok) {
                    alert('Не удалось остановить процесс: ' + (data.message || 'Ошибка'));
                    btnStopDeploy.disabled = false;
                    btnStopDeploy.textContent = '🛑 Остановить развертывание';
                }
            } catch (e) {
                alert('Ошибка отправки запроса на остановку: ' + e.message);
                btnStopDeploy.disabled = false;
                btnStopDeploy.textContent = '🛑 Остановить развертывание';
            }
        });
    }

    btnStartDeploy.addEventListener('click', async () => {
        showStep(4);
        updateBadgeStatus('Развертывание...', '#f59e0b', true);
        startDeployTimer();
        isUserScrolledUp = false;
        terminalLogs.innerHTML = '';
        appendLog('[INIT] Starting deployment process...', 'info');

        if (btnStopDeploy) {
            btnStopDeploy.classList.remove('hidden');
            btnStopDeploy.disabled = false;
        }
        btnStartDeploy.classList.add('hidden');

        const mode = getSelectedMode();
        const commonVersion = document.getElementById('xui_version') ? document.getElementById('xui_version').value.trim() || '3.6.0' : '3.6.0';

        let payload = {
            deploy_mode: mode,
            is_cascade: (mode === 'cascade' || mode === 'cascade_sub'),
            xui_version: commonVersion
        };

        if (mode === 'single' || mode === 'proxy_only' || mode === 'freedom_only') {
            payload.vps_host = document.getElementById('vps_host').value.trim();
            payload.domain = payload.vps_host;
            payload.vps_port = parseInt(document.getElementById('vps_port').value) || 22;
            payload.vps_user = document.getElementById('vps_user').value.trim() || 'root';
            payload.vps_password = document.getElementById('vps_password').value;
            payload.vps_key = document.getElementById('vps_key').value;
            payload.xui_username = document.getElementById('xui_username').value.trim() || 'admin';
            payload.xui_password = document.getElementById('xui_password').value.trim() || 'admin';
            payload.sub_secret = document.getElementById('sub_secret').value.trim() || randomDigits(16);
            payload.client_tcp_list = document.getElementById('client_tcp_list').value.trim();
            payload.client_xhttp_list = document.getElementById('client_xhttp_list').value.trim();
        } else if (mode === 'sub_only') {
            payload.sub_vps_host = document.getElementById('sub_vps_host').value.trim();
            payload.sub_vps_port = parseInt(document.getElementById('sub_vps_port').value) || 22;
            payload.sub_vps_user = document.getElementById('sub_vps_user').value.trim() || 'root';
            payload.sub_vps_password = document.getElementById('sub_vps_password').value;
            payload.sub_vps_key = document.getElementById('sub_vps_key').value;
            payload.sub_domain = (document.getElementById('sub_domain') ? document.getElementById('sub_domain').value.trim() : '') || payload.sub_vps_host;
            payload.sub_secret_path = document.getElementById('sub_secret_path').value.trim() || 'subs';
            payload.sub_russian_url = document.getElementById('sub_russian_url').value.trim();
            payload.sub_foreign_url = document.getElementById('sub_foreign_url').value.trim();
            payload.sub_proxy_clients = document.getElementById('sub_proxy_clients').value.trim();
            payload.sub_freedom_clients = document.getElementById('sub_freedom_clients').value.trim();
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
        } else if (mode === 'update_3xui') {
            payload.update_vps_host = document.getElementById('update_vps_host').value.trim();
            payload.update_vps_port = parseInt(document.getElementById('update_vps_port').value) || 22;
            payload.update_vps_user = document.getElementById('update_vps_user').value.trim() || 'root';
            payload.update_vps_password = document.getElementById('update_vps_password').value;
            payload.update_vps_key = document.getElementById('update_vps_key').value;
            payload.update_xui_version = document.getElementById('update_xui_version').value.trim() || '3.6.0';
        } else {
            payload.freedom_host = document.getElementById('freedom_host').value.trim();
            payload.freedom_port = parseInt(document.getElementById('freedom_port').value) || 22;
            payload.freedom_user = document.getElementById('freedom_user').value.trim() || 'root';
            payload.freedom_password = document.getElementById('freedom_password').value;
            payload.freedom_key = document.getElementById('freedom_key').value;
            payload.freedom_xui_username = document.getElementById('freedom_xui_username').value.trim() || 'admin';
            payload.freedom_xui_password = document.getElementById('freedom_xui_password').value.trim() || 'admin';
            payload.freedom_sub_secret = document.getElementById('freedom_sub_secret').value.trim() || randomDigits(16);
            payload.freedom_xui_version = commonVersion;
            payload.freedom_client_name = document.getElementById('freedom_client_name').value.trim() || 'local-proxy-node-client';

            payload.proxy_host = document.getElementById('proxy_host').value.trim();
            payload.proxy_port = parseInt(document.getElementById('proxy_port').value) || 22;
            payload.proxy_user = document.getElementById('proxy_user').value.trim() || 'root';
            payload.proxy_password = document.getElementById('proxy_password').value;
            payload.proxy_key = document.getElementById('proxy_key').value;
            payload.proxy_xui_username = document.getElementById('proxy_xui_username').value.trim() || 'admin';
            payload.proxy_xui_password = document.getElementById('proxy_xui_password').value.trim() || 'admin';
            payload.proxy_sub_secret = document.getElementById('proxy_sub_secret').value.trim() || randomDigits(16);
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
                payload.sub_secret_path = document.getElementById('sub_secret_path').value.trim() || 'subs';
            }
        }

        if (mode === 'single') {
            updateBadgeStatus(`Развертывание ${payload.vps_host || 'сервера'}...`, '#f59e0b', true);
        } else if (mode === 'proxy_only') {
            updateBadgeStatus(`Развертывание Proxy Node...`, '#f59e0b', true);
        } else if (mode === 'freedom_only') {
            updateBadgeStatus(`Развертывание Freedom Node...`, '#f59e0b', true);
        } else if (mode === 'sub_only') {
            updateBadgeStatus('Развертывание Сервера подписок...', '#f59e0b', true);
        } else if (mode === 'backup') {
            updateBadgeStatus('Создание бэкапа сервера...', '#f59e0b', true);
        } else if (mode === 'recovery') {
            updateBadgeStatus('Восстановление сервера...', '#f59e0b', true);
        } else if (mode === 'update_3xui') {
            updateBadgeStatus('Обновление 3X-UI панели...', '#f59e0b', true);
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
                appendLog('[CANCEL] Процесс остановлен пользователем.', 'warning');
                return;
            }

            if (data.status === 'completed') {
                updateBadgeStatus('Успешно завершено!', '#10b981');
                stopDeployTimer();

                if (btnStartDeploy) btnStartDeploy.classList.remove('hidden');
                if (btnStopDeploy) btnStopDeploy.classList.add('hidden');

                const summaryCard = document.getElementById('summaryCard');
                const panelsContainer = document.getElementById('panelsContainer');
                summaryCard.classList.remove('hidden');
                panelsContainer.innerHTML = '';

                const result = data.result || {};

                const renderPanelBlock = (title, icon, url, user, pass, secret) => {
                    const block = document.createElement('div');
                    block.className = 'panel-info-block';
                    block.innerHTML = `
                        <div class="panel-info-header">
                            <span class="panel-icon">${icon}</span>
                            <span class="panel-title-text">${title}</span>
                        </div>
                        <div class="summary-grid">
                            <div class="summary-item full-width">
                                <span class="summary-label">Адрес панели (URL)</span>
                                <div class="val-code-wrapper">
                                    <a href="${url}" target="_blank" class="val-code link">${url}</a>
                                    <button type="button" class="btn-sm btn-copy" data-copy="${url}">📋 Copy</button>
                                </div>
                            </div>
                            ${user ? `
                            <div class="summary-item">
                                <span class="summary-label">Логин администратора</span>
                                <div class="val-code-wrapper">
                                    <span class="val-code">${user}</span>
                                    <button type="button" class="btn-sm btn-copy" data-copy="${user}">📋 Copy</button>
                                </div>
                            </div>` : ''}
                            ${pass ? `
                            <div class="summary-item">
                                <span class="summary-label">Пароль администратора</span>
                                <div class="val-code-wrapper">
                                    <span class="val-code secret-val" data-secret="${pass}">••••••••</span>
                                    <button type="button" class="btn-sm btn-eye-secret">👁️</button>
                                    <button type="button" class="btn-sm btn-copy" data-copy="${pass}">📋 Copy</button>
                                </div>
                            </div>` : ''}
                            ${secret ? `
                            <div class="summary-item full-width">
                                <span class="summary-label">Секретная фраза</span>
                                <div class="val-code-wrapper">
                                    <span class="val-code secret-val" data-secret="${secret}">••••••••</span>
                                    <button type="button" class="btn-sm btn-eye-secret">👁️</button>
                                    <button type="button" class="btn-sm btn-copy" data-copy="${secret}">📋 Copy</button>
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
                    panelsContainer.appendChild(renderPanelBlock('Архив бэкапа успешно создан!', '📦', `Локальный архив: ./backups/${bName}`, `Сервер: ${bHost}`, `Размер архива: ${bSize}`, ''));
                    return;
                }

                if (mode === 'recovery') {
                    const rHost = result.recovery_host || cfg.recovery_vps_host || '';
                    const bFile = result.backup_file || cfg.recovery_backup_file || '';
                    const xuiUrl = result.xui_url || `https://${rHost}/`;
                    panelsContainer.appendChild(renderPanelBlock('Сервер успешно восстановлен из бэкапа!', '🔄', xuiUrl, `Новый домен: ${rHost}`, `Архив: ${bFile}`, ''));
                    return;
                }

                if (mode === 'update_3xui') {
                    const uHost = result.update_host || cfg.update_vps_host || '';
                    const ver = result.xui_version || cfg.update_xui_version || '3.6.0';
                    const xuiUrl = result.xui_url || `https://${uHost}/`;
                    panelsContainer.appendChild(renderPanelBlock('Панель 3X-UI успешно обновлена!', '⬆️', xuiUrl, `Сервер: ${uHost}`, `Версия 3X-UI: ${ver}`, ''));
                    return;
                }

                if (mode === 'sub_only') {
                    const subBaseUrl = result.sub_base_url || `https://${cfg.sub_domain}/${cfg.sub_secret_path}`;
                    panelsContainer.appendChild(renderPanelBlock('Сервер подписок (Caddy Sub-Server)', '📡', `${subBaseUrl}/<username>`, '', '', ''));
                } else if (mode === 'cascade' || mode === 'cascade_sub') {
                    const freedomHost = result.freedom_domain || cfg.freedom_host || 'Freedom Node';
                    const freedomUrl = result.freedom_xui_url || `https://${freedomHost}/`;
                    const freedomUser = result.freedom_username || cfg.freedom_xui_username || 'admin';
                    const freedomPass = result.freedom_password || cfg.freedom_xui_password || 'admin';
                    const freedomSecret = result.freedom_sub_secret || cfg.freedom_sub_secret || '';

                    panelsContainer.appendChild(renderPanelBlock('1. Панель управления Freedom Node (Выходной сервер)', '🕊️', freedomUrl, freedomUser, freedomPass, freedomSecret));

                    const proxyHost = result.domain || cfg.proxy_host || 'Proxy Node';
                    const proxyUrl = result.xui_url || `https://${proxyHost}/`;
                    const proxyUser = result.xui_username || cfg.proxy_xui_username || 'admin';
                    const proxyPass = result.xui_password || cfg.proxy_xui_password || 'admin';
                    const proxySecret = result.sub_secret || cfg.proxy_sub_secret || '';

                    panelsContainer.appendChild(renderPanelBlock('2. Панель управления Proxy Node (Входной сервер)', '🛡️', proxyUrl, proxyUser, proxyPass, proxySecret));

                    if (mode === 'cascade_sub') {
                        const subBaseUrl = result.sub_base_url || `https://${cfg.sub_domain}/${cfg.sub_secret_path}`;
                        panelsContainer.appendChild(renderPanelBlock('3. Сервер подписок (Caddy Sub-Server)', '📡', `${subBaseUrl}/<username>`, '', '', ''));
                    }
                } else {
                    const host = result.domain || cfg.vps_host || 'Server';
                    const xuiUrl = result.xui_url || `https://${host}/`;
                    const xuiUser = result.xui_username || cfg.xui_username || 'admin';
                    const xuiPass = result.xui_password || cfg.xui_password || 'admin';
                    const subSecret = result.sub_secret || cfg.sub_secret || '';
                    
                    let panelTitle = 'Панель управления 3X-UI';
                    let panelIcon = '🔑';
                    if (mode === 'proxy_only') {
                        panelTitle = 'Панель управления Proxy Node';
                        panelIcon = '🛡️';
                    } else if (mode === 'freedom_only') {
                        panelTitle = 'Панель управления Freedom Node';
                        panelIcon = '🕊️';
                    }

                    panelsContainer.appendChild(renderPanelBlock(panelTitle, panelIcon, xuiUrl, xuiUser, xuiPass, subSecret));
                }

                const clientsContainer = document.getElementById('clientsContainer');
                clientsContainer.innerHTML = '';

                const clientsList = result.clients || [];
                if (clientsList.length === 0 && mode !== 'sub_only') {
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
            if (!confirm('Обновить файлы деплоера до последней версии с GitHub master?\n\nВаши сохраненные бэкапы (./backups/) и конфигурация (setup_backup.yml) будут сохранены, а сервер перезапустится.')) {
                return;
            }

            btnUpdateSources.disabled = true;
            btnUpdateSources.textContent = '⏳ Обновление...';
            updateBadgeStatus('Обновление исходников...', '#f59e0b', true);

            try {
                const res = await fetch('/api/update_sources', { method: 'POST' });
                const data = await res.json();
                if (!data.ok) {
                    alert('Ошибка запуска обновления: ' + (data.message || 'Неизвестная ошибка'));
                    btnUpdateSources.disabled = false;
                    btnUpdateSources.textContent = '🔄 Обновить скрипт';
                    updateBadgeStatus('Готов к настройке', '#3b82f6');
                    return;
                }

                alert('Процесс обновления запущен! Сервер сейчас перезапустится. Страница автоматически обновится через несколько секунд.');

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
                alert('Запрос на обновление отправлен. Ожидаем перезапуск сервера...');
                setTimeout(() => window.location.reload(), 4000);
            }
        });
    }

    const btnRestart = document.getElementById('btnRestart');
    if (btnRestart) {
        btnRestart.addEventListener('click', async () => {
            if (!confirm('Перезапустить процесс локального сервера деплоера?')) {
                return;
            }

            btnRestart.disabled = true;
            btnRestart.textContent = '⏳ Перезапуск...';
            updateBadgeStatus('Перезапуск сервера...', '#f59e0b', true);

            try {
                const res = await fetch('/api/restart', { method: 'POST' });
                const data = await res.json();
                if (!data.ok) {
                    alert('Ошибка перезапуска: ' + (data.message || 'Ошибка'));
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
            if (!confirm('Вы действительно хотите выключить локальный сервер деплоера?')) {
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
                    alert('Ошибка остановки: ' + (data.message || 'Ошибка'));
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
});

