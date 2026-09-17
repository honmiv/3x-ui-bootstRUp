// Deploy orchestration & result rendering (verbatim from app.js)
// Note: `terminalLogs` is a top-level const in logs.js (shared).

const btnStartDeploy = document.getElementById('btnStartDeploy');
const btnStopDeploy = document.getElementById('btnStopDeploy');

if (btnStopDeploy) {
        btnStopDeploy.addEventListener('click', async () => {
            if (!await showConfirm('Вы уверены, что хотите остановить процесс развертывания?', 'Остановка развертывания', { confirmText: 'Да, остановить', danger: true })) return;
            btnStopDeploy.disabled = true;
            btnStopDeploy.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon spin"><line x1="12" y1="2" x2="12" y2="6"/><line x1="12" y1="18" x2="12" y2="22"/><line x1="4.93" y1="4.93" x2="7.76" y2="7.76"/><line x1="16.24" y1="16.24" x2="19.07" y2="19.07"/><line x1="2" y1="12" x2="6" y2="12"/><line x1="18" y1="12" x2="22" y2="12"/><line x1="4.93" y1="19.07" x2="7.76" y2="16.24"/><line x1="16.24" y1="7.76" x2="19.07" y2="4.93"/></svg> Остановка...';
            appendLog('[CANCEL] Запрос остановки процесса пользователем...', 'warning');

            try {
                const res = await fetch('/api/deploy/stop', { method: 'POST' });
                const data = await res.json();
                if (!data.ok) {
                    showToast('Не удалось остановить процесс: ' + (data.message || 'Ошибка'), 'error');
                    btnStopDeploy.disabled = false;
                    btnStopDeploy.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon"><polygon points="7.86 2 16.14 2 22 7.86 22 16.14 16.14 22 7.86 22 2 16.14 2 7.86 7.86 2"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg> Остановить развертывание';
                }
            } catch (e) {
                showToast('Ошибка отправки запроса на остановку: ' + e.message, 'error');
                btnStopDeploy.disabled = false;
                btnStopDeploy.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon"><polygon points="7.86 2 16.14 2 22 7.86 22 16.14 16.14 22 7.86 22 2 16.14 2 7.86 7.86 2"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg> Остановить развертывание';
            }
        });
    }

    btnStartDeploy.addEventListener('click', async () => {
        // First, validate all required passwords
        if (!await window.validateRequiredPasswords()) {
            return;
        }

        const mode = window.getSelectedMode();

        window.showStep(4);
        terminalLogs.innerHTML = '';
        const summaryCardReset = document.getElementById('summaryCard');
        if (summaryCardReset) summaryCardReset.classList.add('hidden');
        appendLog('[INIT] Starting deployment process...', 'info');

        if (btnStopDeploy) {
            btnStopDeploy.classList.remove('hidden');
            btnStopDeploy.disabled = false;
        }
        btnStartDeploy.classList.add('hidden');

        const commonVersion = document.getElementById('xui_version') ? document.getElementById('xui_version').value.trim() || window.__getLatestFetchedXuiVersion() : window.__getLatestFetchedXuiVersion();
        const decoyTemplate = document.getElementById('decoy_template') ? document.getElementById('decoy_template').value.trim() || 'builtin' : 'builtin';
        const freedomDecoyTemplate = document.getElementById('freedom_decoy_template') ? document.getElementById('freedom_decoy_template').value.trim() || 'builtin' : 'builtin';
        const proxyDecoyTemplate = document.getElementById('proxy_decoy_template') ? document.getElementById('proxy_decoy_template').value.trim() || 'builtin' : 'builtin';
        const subDecoyTemplate = document.getElementById('sub_decoy_template') ? document.getElementById('sub_decoy_template').value.trim() || 'builtin' : 'builtin';
        let changeSshPort = false;
        let newSshPort = 22222;
        if (mode === 'update_3xui') {
            const cb = document.getElementById('opt_update_change_ssh_port');
            const inp = document.getElementById('custom_update_ssh_port');
            if (cb && cb.checked) {
                changeSshPort = true;
                if (inp && inp.value) newSshPort = parseInt(inp.value, 10) || 22222;
            }
        } else if (mode === 'update_sub') {
            const cb = document.getElementById('opt_update_sub_change_ssh_port');
            const inp = document.getElementById('custom_update_sub_ssh_port');
            if (cb && cb.checked) {
                changeSshPort = true;
                if (inp && inp.value) newSshPort = parseInt(inp.value, 10) || 22222;
            }
        } else {
            const cb = document.getElementById('opt_change_ssh_port');
            const inp = document.getElementById('custom_ssh_port');
            if (cb && cb.checked) {
                changeSshPort = true;
                if (inp && inp.value) newSshPort = parseInt(inp.value, 10) || 22222;
            }
        }

        let payload = {
            deploy_mode: mode,
            is_cascade: (mode === 'cascade' || mode === 'cascade_sub'),
            xui_version: commonVersion,
            decoy_template: decoyTemplate,
            freedom_decoy_template: freedomDecoyTemplate,
            proxy_decoy_template: proxyDecoyTemplate,
            sub_decoy_template: subDecoyTemplate,
            change_ssh_port: changeSshPort,
            new_ssh_port: newSshPort
        };

        if (mode === 'single' || mode === 'proxy_only' || mode === 'freedom_only' || mode === 'freedom_component') {
            payload.vps_host = document.getElementById('vps_host').value.trim();
            payload.domain = payload.vps_host;
            payload.vps_port = parseInt(document.getElementById('vps_port').value) || 22;
            payload.vps_user = document.getElementById('vps_user').value.trim() || 'root';
            payload.vps_password = document.getElementById('vps_password').value;
            payload.vps_key = document.getElementById('vps_key').value;
            payload.xui_username = window.getFieldValue('xui_username');
            payload.xui_password = window.getFieldValue('xui_password');
            payload.sub_secret = window.getFieldValue('sub_secret');
            payload.client_tcp_list = document.getElementById('client_tcp_list').value.trim();
            payload.client_xhttp_list = document.getElementById('client_xhttp_list').value.trim();
            if (mode === 'freedom_component') {
                payload.freedom_client_name = window.getFieldValue('freedom_client_name') || 'local-proxy-node-client';
            } else {
                payload.freedom_client_name = window.getFieldValue('freedom_client_name');
            }
            if (mode === 'proxy_only') {
                payload.foreign_sub_url = document.getElementById('foreign_sub_url').value.trim();
            }
        } else if (mode === 'freedom_sub') {
            payload.vps_host = document.getElementById('vps_host').value.trim();
            payload.domain = payload.vps_host;
            payload.vps_port = parseInt(document.getElementById('vps_port').value) || 22;
            payload.vps_user = document.getElementById('vps_user').value.trim() || 'root';
            payload.vps_password = document.getElementById('vps_password').value;
            payload.vps_key = document.getElementById('vps_key').value;
            payload.xui_username = window.getFieldValue('xui_username');
            payload.xui_password = window.getFieldValue('xui_password');
            payload.sub_secret = window.getFieldValue('sub_secret');
            payload.client_tcp_list = document.getElementById('client_tcp_list').value.trim();
            payload.client_xhttp_list = document.getElementById('client_xhttp_list').value.trim();
            payload.freedom_client_name = window.getFieldValue('freedom_client_name');

            payload.sub_vps_host = document.getElementById('sub_vps_host').value.trim();
            payload.sub_vps_port = parseInt(document.getElementById('sub_vps_port').value) || 22;
            payload.sub_vps_user = document.getElementById('sub_vps_user').value.trim() || 'root';
            payload.sub_vps_password = document.getElementById('sub_vps_password').value;
            payload.sub_vps_key = document.getElementById('sub_vps_key').value;
            payload.sub_domain = (document.getElementById('sub_domain') ? document.getElementById('sub_domain').value.trim() : '') || payload.sub_vps_host;
            payload.sub_secret_path = window.getFieldValue('sub_secret_path');
            payload.sub_admin_user = window.getFieldValue('sub_admin_user');
            payload.sub_admin_password = window.getFieldValue('sub_admin_password');
        } else if (mode === 'sub_only') {
            payload.sub_vps_host = document.getElementById('sub_vps_host').value.trim();
            payload.sub_vps_port = parseInt(document.getElementById('sub_vps_port').value) || 22;
            payload.sub_vps_user = document.getElementById('sub_vps_user').value.trim() || 'root';
            payload.sub_vps_password = document.getElementById('sub_vps_password').value;
            payload.sub_vps_key = document.getElementById('sub_vps_key').value;
            payload.sub_domain = (document.getElementById('sub_domain') ? document.getElementById('sub_domain').value.trim() : '') || payload.sub_vps_host;
            payload.sub_secret_path = window.getFieldValue('sub_secret_path');
            payload.sub_russian_url = document.getElementById('sub_russian_url').value.trim();
            payload.sub_foreign_url = document.getElementById('sub_foreign_url').value.trim();
            payload.sub_proxy_clients = document.getElementById('sub_proxy_clients').value.trim();
            payload.sub_freedom_clients = document.getElementById('sub_freedom_clients').value.trim();
            payload.sub_admin_user = window.getFieldValue('sub_admin_user');
            payload.sub_admin_password = window.getFieldValue('sub_admin_password');
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
            payload.recovery_xui_username = window.getFieldValue('recovery_xui_username');
            payload.recovery_xui_password = window.getFieldValue('recovery_xui_password');
        } else if (mode === 'update_3xui' || mode === 'restart_panel' || mode === 'restart_server') {
            payload.update_vps_host = document.getElementById('update_vps_host').value.trim();
            payload.update_vps_port = parseInt(document.getElementById('update_vps_port').value) || 22;
            payload.update_vps_user = document.getElementById('update_vps_user').value.trim() || 'root';
            payload.update_vps_password = document.getElementById('update_vps_password').value;
            payload.update_vps_key = document.getElementById('update_vps_key').value;
            if (mode === 'update_3xui') {
                payload.update_xui_version = document.getElementById('update_xui_version').value.trim() || window.__getLatestFetchedXuiVersion();
                const updateDecoyEl = document.getElementById('update_decoy_template');
                if (updateDecoyEl && updateDecoyEl.value.trim()) {
                    payload.update_decoy_template = updateDecoyEl.value.trim();
                }
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
            if (mode === 'update_sub') {
                const updateSubDecoyEl = document.getElementById('update_sub_decoy_template');
                if (updateSubDecoyEl && updateSubDecoyEl.value.trim()) {
                    payload.update_sub_decoy_template = updateSubDecoyEl.value.trim();
                }
            }
        } else {
            payload.freedom_host = document.getElementById('freedom_host').value.trim();
            payload.freedom_host_for_ssh = payload.freedom_host;
            payload.freedom_port = parseInt(document.getElementById('freedom_port').value) || 22;
            payload.freedom_user = document.getElementById('freedom_user').value.trim() || 'root';
            payload.freedom_password = document.getElementById('freedom_password').value;
            payload.freedom_key = document.getElementById('freedom_key').value;
            payload.freedom_xui_username = window.getFieldValue('freedom_xui_username');
            payload.freedom_xui_password = window.getFieldValue('freedom_xui_password');
            payload.freedom_sub_secret = window.getFieldValue('freedom_sub_secret');
            payload.freedom_xui_version = commonVersion;
            payload.freedom_client_name = window.getFieldValue('freedom_client_name') || 'local-proxy-node-client';

            payload.proxy_host = document.getElementById('proxy_host').value.trim();
            payload.proxy_host_for_ssh = payload.proxy_host;
            payload.proxy_port = parseInt(document.getElementById('proxy_port').value) || 22;
            payload.proxy_user = document.getElementById('proxy_user').value.trim() || 'root';
            payload.proxy_password = document.getElementById('proxy_password').value;
            payload.proxy_key = document.getElementById('proxy_key').value;
            payload.proxy_xui_username = window.getFieldValue('proxy_xui_username');
            payload.proxy_xui_password = window.getFieldValue('proxy_xui_password');
            payload.proxy_sub_secret = window.getFieldValue('proxy_sub_secret');
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
                payload.sub_secret_path = window.getFieldValue('sub_secret_path');
                payload.sub_admin_user = window.getFieldValue('sub_admin_user');
                payload.sub_admin_password = window.getFieldValue('sub_admin_password');
            }
        }

        if (mode === 'single') {
        } else if (mode === 'proxy_only') {
        } else if (mode === 'freedom_only' || mode === 'freedom_component') {
        } else if (mode === 'freedom_sub') {
        } else if (mode === 'sub_only') {
        } else if (mode === 'backup') {
        } else if (mode === 'recovery') {
        } else if (mode === 'update_3xui') {
        } else if (mode === 'restart_sub') {
        } else if (mode === 'update_sub') {
        } else if (mode === 'backup_sub') {
        } else if (mode === 'rollback_sub') {
        } else {
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
                showToast(res.message, 'error');
                btnStartDeploy.classList.remove('hidden');
                if (btnStopDeploy) btnStopDeploy.classList.add('hidden');
                return;
            }

            // Show progress indicator for cascade deployments
            const progressContainer = document.getElementById('deployProgressContainer');
            if ((mode === 'cascade' || mode === 'cascade_sub' || mode === 'freedom_sub') && progressContainer) {
                progressContainer.classList.remove('hidden');
                initProgressIndicator(mode === 'cascade_sub', mode === 'freedom_sub');
            }

            window.startDeployLogStream(() => checkFinalStatus(mode, payload));

        } catch (err) {
            appendLog(`[ERROR] ${err.message}`, 'error');
            btnStartDeploy.classList.remove('hidden');
            if (btnStopDeploy) btnStopDeploy.classList.add('hidden');
        }
    });

    const checkFinalStatus = async (mode, cfg) => {
        try {
            const resp = await fetch('/api/status');
            const data = await resp.json();

            if (data.status === 'cancelled') {
                if (btnStartDeploy) {
                    btnStartDeploy.classList.remove('hidden');
                    btnStartDeploy.disabled = false;
                }
                if (btnStopDeploy) {
                    btnStopDeploy.classList.add('hidden');
                    btnStopDeploy.disabled = false;
                    btnStopDeploy.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon"><polygon points="7.86 2 16.14 2 22 7.86 22 16.14 16.14 22 7.86 22 2 16.14 2 7.86 7.86 2"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg> Остановить развертывание';
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
                
                const summaryCardHeader = document.getElementById('summaryCardHeader');
                if (summaryCardHeader) {
                    const iconSvg = '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon text-success"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>';
                    if (mode === 'backup' || mode === 'backup_sub') {
                        summaryCardHeader.innerHTML = `${iconSvg} Бэкап успешно создан!`;
                    } else if (mode === 'recovery' || mode === 'rollback_sub') {
                        summaryCardHeader.innerHTML = `${iconSvg} Восстановление завершено!`;
                    } else if (mode === 'restart_panel' || mode === 'restart_server' || mode === 'restart_sub') {
                        summaryCardHeader.innerHTML = `${iconSvg} Перезапуск выполнен!`;
                    } else if (mode === 'update_3xui' || mode === 'update_sub') {
                        summaryCardHeader.innerHTML = `${iconSvg} Обновление завершено!`;
                    } else {
                        summaryCardHeader.innerHTML = `${iconSvg} Установка успешно завершена!`;
                    }
                }
                
                panelsContainer.innerHTML = '';

                const result = data.result || {};

                const renderPanelBlock = (title, icon, url, user, pass, userLabel = 'Логин администратора', passLabel = 'Пароль администратора', passSecret = true, urlLabel = 'Адрес панели (URL)', linkUrl = '') => {
                    const realLink = linkUrl || url;
                    const escTitle = escapeHtml(title || '');
                    const escUrl = escapeHtml(url || '');
                    const escRealLink = escapeHtml(realLink || '');
                    const escUser = escapeHtml(user || '');
                    const escPass = escapeHtml(pass || '');
                    const escUrlLabel = escapeHtml(urlLabel || '');
                    const escUserLabel = escapeHtml(userLabel || '');
                    const escPassLabel = escapeHtml(passLabel || '');

                    const block = document.createElement('div');
                    block.className = 'panel-info-block';
                    block.innerHTML = `
                        <div class="panel-info-header">
                            <span class="panel-icon">${icon}</span>
                            <span class="panel-title-text">${escTitle}</span>
                        </div>
                        <div class="summary-grid">
                            ${url ? `
                            <div class="summary-item full-width">
                                <span class="summary-label">${escUrlLabel}</span>
                                <div class="val-code-wrapper">
                                    <a href="${escRealLink}" target="_blank" class="val-code link">${escUrl}</a>
                                    <button type="button" class="btn-sm btn-copy" data-copy="${escUrl}"><svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg> Copy</button>
                                </div>
                            </div>` : ''}
                            ${user ? `
                            <div class="summary-item">
                                <span class="summary-label">${escUserLabel}</span>
                                <div class="val-code-wrapper">
                                    <span class="val-code">${escUser}</span>
                                    <button type="button" class="btn-sm btn-copy" data-copy="${escUser}"><svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg> Copy</button>
                                </div>
                            </div>` : ''}
                            ${pass ? `
                            <div class="summary-item">
                                <span class="summary-label">${escPassLabel}</span>
                                <div class="val-code-wrapper">
                                    ${passSecret ? `<span class="val-code secret-val" data-secret="${escPass}">••••••••</span>` : `<span class="val-code">${escPass}</span>`}
                                    ${passSecret ? `<button type="button" class="btn-sm btn-eye-secret">👁️</button>` : ''}
                                    <button type="button" class="btn-sm btn-copy" data-copy="${escPass}"><svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg> Copy</button>
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
                                valSpan.innerHTML = '••••••••';
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
                    panelsContainer.appendChild(renderPanelBlock('Архив бэкапа успешно создан!', '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon"><line x1="16.5" y1="9.4" x2="7.5" y2="4.21"/><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/></svg>', `Локальный архив: ./backups_panel/${bName}`, bHost, bSize, 'Сервер', 'Размер архива', false));
                } else if (mode === 'recovery') {
                    const rHost = result.recovery_host || cfg.recovery_vps_host || '';
                    const bFile = result.backup_file || cfg.recovery_backup_file || '';
                    const xuiUrl = result.xui_url || `https://${rHost}/`;
                    panelsContainer.appendChild(renderPanelBlock('Сервер успешно восстановлен из бэкапа!', '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon"><path d="M21 2v6h-6"/><path d="M3 12a9 9 0 0 1 15-6.7L21 8"/><path d="M3 22v-6h6"/><path d="M21 12a9 9 0 0 1-15 6.7L3 16"/></svg>', xuiUrl, rHost, bFile, 'Новый домен', 'Архив', false));
                } else if (mode === 'restart_panel') {
                    const done = document.createElement('div');
                    done.className = 'panel-info-block';
                    done.innerHTML = '<div class="panel-info-header"><span class="panel-icon"><svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon"><path d="M21 2v6h-6"/><path d="M3 12a9 9 0 0 1 15-6.7L21 8"/><path d="M3 22v-6h6"/><path d="M21 12a9 9 0 0 1-15 6.7L3 16"/></svg></span><span class="panel-title-text">Панель 3X-UI перезапущена, всё готово!</span></div>';
                    panelsContainer.appendChild(done);
                } else if (mode === 'restart_server') {
                    const done = document.createElement('div');
                    done.className = 'panel-info-block';
                    done.innerHTML = '<div class="panel-info-header"><span class="panel-icon"><svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon"><path d="M21 2v6h-6"/><path d="M3 12a9 9 0 0 1 15-6.7L21 8"/><path d="M3 22v-6h6"/><path d="M21 12a9 9 0 0 1-15 6.7L3 16"/></svg></span><span class="panel-title-text">Сервер перезагружается, всё готово!</span></div>';
                    panelsContainer.appendChild(done);
                } else if (mode === 'update_3xui') {
                    const uHost = result.update_host || cfg.update_vps_host || '';
                    const ver = result.xui_version || cfg.update_xui_version || window.__getLatestFetchedXuiVersion();
                    const xuiUrl = result.xui_url || `https://${uHost}/`;
                    panelsContainer.appendChild(renderPanelBlock('Панель 3X-UI успешно обновлена!', '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon"><line x1="12" y1="19" x2="12" y2="5"/><polyline points="5 12 12 5 19 12"/></svg>', xuiUrl, uHost, ver, 'Сервер', 'Версия 3X-UI', false));
                } else if (mode === 'restart_sub' || mode === 'update_sub') {
                    const done = document.createElement('div');
                    done.className = 'panel-info-block';
                    const backupInfo = mode === 'update_sub' && result.pre_update_backup
                        ? `<div class="panel-info-line">Pre-update backup: <code>${result.pre_update_backup}</code></div>`
                        : '';
                    done.innerHTML = `<div class="panel-info-header"><span class="panel-icon">${mode === 'update_sub' ? '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon"><line x1="12" y1="19" x2="12" y2="5"/><polyline points="5 12 12 5 19 12"/></svg>' : '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon"><path d="M21 2v6h-6"/><path d="M3 12a9 9 0 0 1 15-6.7L21 8"/><path d="M3 22v-6h6"/><path d="M21 12a9 9 0 0 1-15 6.7L3 16"/></svg>'}</span><span class="panel-title-text">${mode === 'update_sub' ? 'Сервер подписок обновлён, клиенты и ноды сохранены!' : 'Сервер подписок перезапущен, всё готово!'}</span></div>${backupInfo}`;
                    panelsContainer.appendChild(done);
                } else if (mode === 'backup_sub') {
                    const bHost = result.sub_host || cfg.sub_vps_host || '';
                    const bName = result.backup_name || '';
                    const bSize = result.file_size || '';
                    panelsContainer.appendChild(renderPanelBlock('Бэкап Сервера подписок успешно создан!', '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon"><line x1="16.5" y1="9.4" x2="7.5" y2="4.21"/><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/></svg>', `Локальный архив: ./backups_sub_server/${bName}`, bHost, bSize, 'Сервер подписок', 'Размер архива', false, 'Локальный архив'));
                } else if (mode === 'rollback_sub') {
                    const rHost = result.sub_host || cfg.sub_vps_host || '';
                    const bFile = result.backup_file || cfg.rollback_sub_backup_file || '';
                    const subBaseUrl = result.sub_base_url || '';
                    panelsContainer.appendChild(renderPanelBlock('Сервер подписок восстановлен из бэкапа!', '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon"><path d="M21 2v6h-6"/><path d="M3 12a9 9 0 0 1 15-6.7L21 8"/><path d="M3 22v-6h6"/><path d="M21 12a9 9 0 0 1-15 6.7L3 16"/></svg>', subBaseUrl, rHost, bFile, 'Сервер подписок', 'Архив', false, 'Адрес подписок (URL)'));
                }

                if (mode === 'sub_only') {
                    const subBaseUrl = result.sub_base_url || `https://${cfg.sub_domain}/${cfg.sub_secret_path}`;
                    const subUser = result.sub_admin_user || cfg.sub_admin_user || 'admin';
                    const subPass = result.sub_admin_password || 'admin';
                    panelsContainer.appendChild(renderPanelBlock('Сервер подписок (Sub-Server)', '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon"><circle cx="12" cy="12" r="2"/><path d="M16.24 7.76a6 6 0 0 1 0 8.49m-8.48-.01a6 6 0 0 1 0-8.49m11.31-2.82a10 10 0 0 1 0 14.14m-14.14 0a10 10 0 0 1 0-14.14"/></svg>', `${subBaseUrl}`, subUser, subPass, 'Логин панели подписок', 'Пароль панели подписок', true, 'Адрес подписок (URL)', subBaseUrl));
                } else if (mode === 'freedom_sub') {
                    const freedomHost = result.freedom_domain || result.domain || cfg.vps_host || 'Freedom Node';
                    const freedomUrl = result.freedom_xui_url || result.xui_url || `https://${freedomHost}/`;
                    const freedomUser = result.freedom_username || result.xui_username || cfg.xui_username || 'admin';
                    const freedomPass = result.freedom_password || result.xui_password || cfg.xui_password || 'admin';

                    panelsContainer.appendChild(renderPanelBlock('1. Панель управления Freedom Node (Выходной сервер)', '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon"><circle cx="12" cy="12" r="10"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/><line x1="2" y1="12" x2="22" y2="12"/></svg>', freedomUrl, freedomUser, freedomPass));

                    const subBaseUrl = result.sub_base_url || `https://${cfg.sub_domain || cfg.sub_vps_host}/${cfg.sub_secret_path || 'subs'}`;
                    const subUser = result.sub_admin_user || cfg.sub_admin_user || 'admin';
                    const subPass = result.sub_admin_password || 'admin';
                    panelsContainer.appendChild(renderPanelBlock('2. Сервер подписок (Sub-Server)', '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon"><circle cx="12" cy="12" r="2"/><path d="M16.24 7.76a6 6 0 0 1 0 8.49m-8.48-.01a6 6 0 0 1 0-8.49m11.31-2.82a10 10 0 0 1 0 14.14m-14.14 0a10 10 0 0 1 0-14.14"/></svg>', `${subBaseUrl}`, subUser, subPass, 'Логин панели подписок', 'Пароль панели подписок', true, 'Адрес подписок (URL)', subBaseUrl));
                } else if (mode === 'cascade' || mode === 'cascade_sub') {
                    const freedomHost = result.freedom_domain || cfg.freedom_host || 'Freedom Node';
                    const freedomUrl = result.freedom_xui_url || `https://${freedomHost}/`;
                    const freedomUser = result.freedom_username || cfg.freedom_xui_username || 'admin';
                    const freedomPass = result.freedom_password || cfg.freedom_xui_password || 'admin';

                    panelsContainer.appendChild(renderPanelBlock('1. Панель управления Freedom Node (Выходной сервер)', '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon"><circle cx="12" cy="12" r="10"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/><line x1="2" y1="12" x2="22" y2="12"/></svg>', freedomUrl, freedomUser, freedomPass));

                    const proxyHost = result.domain || cfg.proxy_host || 'Proxy Node';
                    const proxyUrl = result.xui_url || `https://${proxyHost}/`;
                    const proxyUser = result.xui_username || cfg.proxy_xui_username || 'admin';
                    const proxyPass = result.xui_password || cfg.proxy_xui_password || 'admin';

                    panelsContainer.appendChild(renderPanelBlock('2. Панель управления Proxy Node (Входной сервер)', '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>', proxyUrl, proxyUser, proxyPass));

                    if (mode === 'cascade_sub') {
                        const subBaseUrl = result.sub_base_url || `https://${cfg.sub_domain}/${cfg.sub_secret_path}`;
                        const subUser = result.sub_admin_user || cfg.sub_admin_user || 'admin';
                        const subPass = result.sub_admin_password || 'admin';
                        panelsContainer.appendChild(renderPanelBlock('3. Сервер подписок (Sub-Server)', '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon"><circle cx="12" cy="12" r="2"/><path d="M16.24 7.76a6 6 0 0 1 0 8.49m-8.48-.01a6 6 0 0 1 0-8.49m11.31-2.82a10 10 0 0 1 0 14.14m-14.14 0a10 10 0 0 1 0-14.14"/></svg>', `${subBaseUrl}`, subUser, subPass, 'Логин панели подписок', 'Пароль панели подписок', true, 'Адрес подписок (URL)', subBaseUrl));
                    }
                } else if (mode === 'single' || mode === 'proxy_only' || mode === 'freedom_only' || mode === 'freedom_component') {
                    const host = result.domain || cfg.vps_host || 'Server';
                    const xuiUrl = result.xui_url || `https://${host}/`;
                    const xuiUser = result.xui_username || cfg.xui_username || 'admin';
                    const xuiPass = result.xui_password || cfg.xui_password || 'admin';
                    
                    let panelTitle = 'Панель управления 3X-UI';
                    let panelIcon = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon"><rect width="7" height="9" x="3" y="3" rx="1"/><rect width="7" height="5" x="14" y="3" rx="1"/><rect width="7" height="9" x="14" y="12" rx="1"/><rect width="7" height="5" x="3" y="16" rx="1"/></svg>';
                    if (mode === 'proxy_only') {
                        panelTitle = 'Панель управления Proxy Node';
                        panelIcon = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>';
                    } else if (mode === 'freedom_only' || mode === 'freedom_component') {
                        panelTitle = 'Панель управления Freedom Node';
                        panelIcon = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon"><circle cx="12" cy="12" r="10"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/><line x1="2" y1="12" x2="22" y2="12"/></svg>';
                    }

                    panelsContainer.appendChild(renderPanelBlock(panelTitle, panelIcon, xuiUrl, xuiUser, xuiPass));
                }

                // Auto-save panel URLs to saved servers if matching hosts exist
                if (Array.isArray(window.getServersList()) && window.getServersList().length > 0) {
                    let serversUpdated = false;
                    const hostUrlMap = {};

                    if (mode === 'sub_only') {
                        const subBaseUrl = result.sub_base_url || `https://${cfg.sub_domain}/${cfg.sub_secret_path}`;
                        const subHost = cfg.sub_vps_host || cfg.vps_host || cfg.sub_domain;
                        if (subHost) hostUrlMap[subHost.toLowerCase()] = subBaseUrl;
                        if (cfg.sub_domain) hostUrlMap[cfg.sub_domain.toLowerCase()] = subBaseUrl;
                    } else if (mode === 'freedom_sub') {
                        const freedomHost = result.freedom_domain || result.domain || cfg.vps_host;
                        const freedomUrl = result.freedom_xui_url || result.xui_url || (freedomHost ? `https://${freedomHost}/` : '');
                        if (freedomHost && freedomUrl) hostUrlMap[freedomHost.toLowerCase()] = freedomUrl;
                        if (cfg.vps_host && freedomUrl) hostUrlMap[cfg.vps_host.toLowerCase()] = freedomUrl;

                        const subBaseUrl = result.sub_base_url || `https://${cfg.sub_domain || cfg.sub_vps_host}/${cfg.sub_secret_path || 'subs'}`;
                        const subHost = cfg.sub_vps_host || cfg.sub_domain;
                        if (subHost) hostUrlMap[subHost.toLowerCase()] = subBaseUrl;
                        if (cfg.sub_domain) hostUrlMap[cfg.sub_domain.toLowerCase()] = subBaseUrl;
                    } else if (mode === 'cascade' || mode === 'cascade_sub') {
                        const freedomHost = result.freedom_domain || cfg.freedom_host;
                        const freedomUrl = result.freedom_xui_url || (freedomHost ? `https://${freedomHost}/` : '');
                        if (freedomHost && freedomUrl) hostUrlMap[freedomHost.toLowerCase()] = freedomUrl;
                        if (cfg.freedom_host && freedomUrl) hostUrlMap[cfg.freedom_host.toLowerCase()] = freedomUrl;

                        const proxyHost = result.domain || cfg.proxy_host;
                        const proxyUrl = result.xui_url || (proxyHost ? `https://${proxyHost}/` : '');
                        if (proxyHost && proxyUrl) hostUrlMap[proxyHost.toLowerCase()] = proxyUrl;
                        if (cfg.proxy_host && proxyUrl) hostUrlMap[cfg.proxy_host.toLowerCase()] = proxyUrl;

                        if (mode === 'cascade_sub') {
                            const subBaseUrl = result.sub_base_url || `https://${cfg.sub_domain}/${cfg.sub_secret_path}`;
                            const subHost = cfg.sub_vps_host || cfg.sub_domain;
                            if (subHost) hostUrlMap[subHost.toLowerCase()] = subBaseUrl;
                            if (cfg.sub_domain) hostUrlMap[cfg.sub_domain.toLowerCase()] = subBaseUrl;
                        }
                    } else if (mode === 'recovery') {
                        const rHost = result.recovery_host || cfg.recovery_vps_host;
                        const xuiUrl = result.xui_url || (rHost ? `https://${rHost}/` : '');
                        if (rHost && xuiUrl) hostUrlMap[rHost.toLowerCase()] = xuiUrl;
                    } else if (mode === 'update_3xui') {
                        const uHost = result.update_host || cfg.update_vps_host;
                        const xuiUrl = result.xui_url || (uHost ? `https://${uHost}/` : '');
                        if (uHost && xuiUrl) hostUrlMap[uHost.toLowerCase()] = xuiUrl;
                    } else if (mode === 'rollback_sub') {
                        const rHost = result.sub_host || cfg.sub_vps_host;
                        const subBaseUrl = result.sub_base_url || '';
                        if (rHost && subBaseUrl) hostUrlMap[rHost.toLowerCase()] = subBaseUrl;
                    } else if (mode === 'single' || mode === 'proxy_only' || mode === 'freedom_only' || mode === 'freedom_component') {
                        const host = result.domain || cfg.vps_host;
                        const xuiUrl = result.xui_url || (host ? `https://${host}/` : '');
                        if (host && xuiUrl) hostUrlMap[host.toLowerCase()] = xuiUrl;
                        if (cfg.vps_host && xuiUrl) hostUrlMap[cfg.vps_host.toLowerCase()] = xuiUrl;
                    }

                    const hostPortMap = {};
                    if (result.new_ssh_port) {
                        const newPort = parseInt(result.new_ssh_port, 10);
                        if (result.updated_ssh_ports && typeof result.updated_ssh_ports === 'object') {
                            for (const [h, p] of Object.entries(result.updated_ssh_ports)) {
                                if (h) hostPortMap[h.toLowerCase()] = p;
                            }
                        }
                        if (mode === 'single' || mode === 'proxy_only' || mode === 'freedom_only' || mode === 'freedom_component') {
                            if (cfg.vps_host) hostPortMap[cfg.vps_host.toLowerCase()] = newPort;
                            if (result.domain) hostPortMap[result.domain.toLowerCase()] = newPort;
                        } else if (mode === 'freedom_sub') {
                            if (cfg.vps_host) hostPortMap[cfg.vps_host.toLowerCase()] = newPort;
                            if (result.freedom_domain) hostPortMap[result.freedom_domain.toLowerCase()] = newPort;
                            if (result.domain) hostPortMap[result.domain.toLowerCase()] = newPort;
                            if (cfg.sub_vps_host) hostPortMap[cfg.sub_vps_host.toLowerCase()] = newPort;
                            if (cfg.sub_domain) hostPortMap[cfg.sub_domain.toLowerCase()] = newPort;
                        } else if (mode === 'cascade' || mode === 'cascade_sub') {
                            if (cfg.freedom_host) hostPortMap[cfg.freedom_host.toLowerCase()] = newPort;
                            if (result.freedom_domain) hostPortMap[result.freedom_domain.toLowerCase()] = newPort;
                            if (cfg.proxy_host) hostPortMap[cfg.proxy_host.toLowerCase()] = newPort;
                            if (result.domain) hostPortMap[result.domain.toLowerCase()] = newPort;
                            if (mode === 'cascade_sub') {
                                if (cfg.sub_vps_host) hostPortMap[cfg.sub_vps_host.toLowerCase()] = newPort;
                                if (cfg.sub_domain) hostPortMap[cfg.sub_domain.toLowerCase()] = newPort;
                            }
                        } else if (mode === 'sub_only' || mode === 'update_sub') {
                            if (cfg.sub_vps_host) hostPortMap[cfg.sub_vps_host.toLowerCase()] = newPort;
                            if (cfg.sub_domain) hostPortMap[cfg.sub_domain.toLowerCase()] = newPort;
                            if (result.sub_domain) hostPortMap[result.sub_domain.toLowerCase()] = newPort;
                            if (result.sub_host) hostPortMap[result.sub_host.toLowerCase()] = newPort;
                        } else if (mode === 'update_3xui') {
                            if (cfg.update_vps_host) hostPortMap[cfg.update_vps_host.toLowerCase()] = newPort;
                            if (result.update_host) hostPortMap[result.update_host.toLowerCase()] = newPort;
                            if (result.target_domain) hostPortMap[result.target_domain.toLowerCase()] = newPort;
                        }
                    }

                    if (window.getServersList().length === 0) {
                        try {
                            const srvRes = await fetch('/api/servers', { cache: 'no-store' });
                            if (srvRes.ok) {
                                const srvData = await srvRes.json();
                                if (Array.isArray(srvData)) window.setServersList(srvData);
                            }
                        } catch (e) {}
                    }

                    const getMatchVal = (rawHost, mapObj) => {
                        if (!rawHost || !mapObj) return null;
                        const lh = rawHost.trim().toLowerCase();
                        if (mapObj[lh] !== undefined) return mapObj[lh];
                        const clean = lh.replace(/^https?:\/\//, '').replace(/\/.*$/, '').split(':')[0];
                        if (clean && mapObj[clean] !== undefined) return mapObj[clean];
                        return null;
                    };

                    window.getServersList().forEach(srv => {
                        const targetUrl = getMatchVal(srv.host, hostUrlMap);
                        if (targetUrl && srv.panel_url !== targetUrl) {
                            srv.panel_url = targetUrl;
                            serversUpdated = true;
                        }
                        const targetPort = getMatchVal(srv.host, hostPortMap);
                        if (targetPort && String(srv.port) !== String(targetPort)) {
                            srv.port = parseInt(targetPort, 10);
                            serversUpdated = true;
                        }
                    });

                    if (serversUpdated) {
                        window.saveServersToBackend().then(() => window.renderSavedServers());
                    }

                    if (result.new_ssh_port) {
                        const newPortStr = String(result.new_ssh_port);
                        if (cfg.vps_host && getMatchVal(cfg.vps_host, hostPortMap)) {
                            const el = document.getElementById('vps_port');
                            if (el) el.value = newPortStr;
                        }
                        if (cfg.freedom_host && getMatchVal(cfg.freedom_host, hostPortMap)) {
                            const el = document.getElementById('freedom_port');
                            if (el) el.value = newPortStr;
                        }
                        if (cfg.proxy_host && getMatchVal(cfg.proxy_host, hostPortMap)) {
                            const el = document.getElementById('proxy_port');
                            if (el) el.value = newPortStr;
                        }
                        if (cfg.sub_vps_host && getMatchVal(cfg.sub_vps_host, hostPortMap)) {
                            const el = document.getElementById('sub_vps_port');
                            if (el) el.value = newPortStr;
                        }
                        if (cfg.update_vps_host && getMatchVal(cfg.update_vps_host, hostPortMap)) {
                            const el = document.getElementById('update_vps_port');
                            if (el) el.value = newPortStr;
                        }

                        ['opt_change_ssh_port', 'opt_update_change_ssh_port', 'opt_update_sub_change_ssh_port'].forEach(cbId => {
                            const cb = document.getElementById(cbId);
                            if (cb && cb.checked) {
                                cb.checked = false;
                                cb.dispatchEvent(new Event('change', { bubbles: true }));
                            }
                        });

                        window.__saveCurrentConfig();
                    }
                }

                const isMaintenanceMode = ['backup', 'recovery', 'update_3xui', 'restart_panel', 'restart_server', 'restart_sub', 'update_sub', 'backup_sub', 'rollback_sub'].includes(mode);
                if (isMaintenanceMode) {
                    const clientsSectionEl = document.getElementById('clientsSection');
                    if (clientsSectionEl) clientsSectionEl.classList.add('hidden');
                    return;
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

                    const groupTag = client.group ? ` (${escapeHtml(client.group)})` : '';
                    let html = `
                        <div class="client-header">
                            <span class="client-name-badge"><svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg> Клиент: ${escapeHtml(client.name || '')}${groupTag}</span>
                        </div>
                        <div class="client-link-group">
                    `;

                    if (client.sub_server_url) {
                        const escSubServer = escapeHtml(client.sub_server_url);
                        html += `
                            <div class="client-link-label"><svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon"><circle cx="12" cy="12" r="2"/><path d="M16.24 7.76a6 6 0 0 1 0 8.49m-8.48-.01a6 6 0 0 1 0-8.49m11.31-2.82a10 10 0 0 1 0 14.14m-14.14 0a10 10 0 0 1 0-14.14"/></svg> Подписка через Сервер подписок</div>
                            <div class="client-link-row">
                                <span class="client-link-text">${escSubServer}</span>
                                <button type="button" class="btn-sm btn-copy-sub-server"><svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg> Копировать</button>
                                <button type="button" class="btn-sm btn-qr-sub-server"><svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon"><rect x="5" y="2" width="14" height="20" rx="2" ry="2"/><line x1="12" y1="18" x2="12.01" y2="18"/></svg> QR</button>
                            </div>
                        `;
                    }

                    if (client.sub_url) {
                        const escSubUrl = escapeHtml(client.sub_url);
                        html += `
                            <div class="client-link-label"><svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg> Прямая ссылка подписки</div>
                            <div class="client-link-row">
                                <span class="client-link-text">${escSubUrl}</span>
                                <button type="button" class="btn-sm btn-copy-sub"><svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg> Копировать</button>
                                <button type="button" class="btn-sm btn-qr-sub"><svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon"><rect x="5" y="2" width="14" height="20" rx="2" ry="2"/><line x1="12" y1="18" x2="12.01" y2="18"/></svg> QR</button>
                            </div>
                        `;
                    }

                    if (client.tcp_url) {
                        const escTcp = escapeHtml(client.tcp_url);
                        html += `
                            <div class="client-link-label"><svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg> VLESS TCP Reality</div>
                            <div class="client-link-row">
                                <span class="client-link-text">${escTcp}</span>
                                <button type="button" class="btn-sm btn-copy-tcp"><svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg> Копировать</button>
                                <button type="button" class="btn-sm btn-qr-tcp"><svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon"><rect x="5" y="2" width="14" height="20" rx="2" ry="2"/><line x1="12" y1="18" x2="12.01" y2="18"/></svg> QR</button>
                            </div>
                        `;
                    }

                    if (client.xhttp_url) {
                        const escXhttp = escapeHtml(client.xhttp_url);
                        html += `
                            <div class="client-link-label"><svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon"><path d="M4.5 16.5c-1.5 1.26-2 5-2 5s3.74-.5 5-2c.71-.84.7-2.13-.09-2.91a2.18 2.18 0 0 0-2.91-.09z"/><path d="M12 15l-3-3a22 22 0 0 1 2-3.95A12.88 12.88 0 0 1 22 2c0 2.72-.78 7.5-6 11a22.35 22.35 0 0 1-4 2z"/><path d="M9 12H4s.55-3.03 2-4c1.62-1.08 5 0 5 0"/><path d="M12 15v5s3.03-.55 4-2c1.08-1.62 0-5 0-5"/></svg> VLESS XHTTP Reality</div>
                            <div class="client-link-row">
                                <span class="client-link-text">${escXhttp}</span>
                                <button type="button" class="btn-sm btn-copy-xhttp"><svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg> Копировать</button>
                                <button type="button" class="btn-sm btn-qr-xhttp"><svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon"><rect x="5" y="2" width="14" height="20" rx="2" ry="2"/><line x1="12" y1="18" x2="12.01" y2="18"/></svg> QR</button>
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
                if (btnStartDeploy) btnStartDeploy.classList.remove('hidden');
                if (btnStopDeploy) btnStopDeploy.classList.add('hidden');
            }
        } catch (e) {
        }
    };

window.checkFinalStatus = checkFinalStatus;