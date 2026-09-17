/* servers.js — Server Manager Sidebar Logic (Encrypted) — extracted from app.js (E1) */
document.addEventListener('DOMContentLoaded', () => {
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
    const smPanelUrl = document.getElementById('sm_panel_url');
    const btnSaveServer = document.getElementById('btnSaveServer');
    const btnTestServerForm = document.getElementById('btnTestServerForm');
    const savedServersList = document.getElementById('savedServersList');
    const btnResetServers = document.getElementById('btnResetServers');

    const masterPasswordModal = document.getElementById('masterPasswordModal');
    const btnCancelMasterPassword = document.getElementById('btnCancelMasterPassword');
    const btnSubmitMasterPassword = document.getElementById('btnSubmitMasterPassword');
    const masterPasswordInput = document.getElementById('masterPasswordInput');

    if (masterPasswordInput) {
        masterPasswordInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                submitMasterPassword();
            }
        });
    }

    if (btnSubmitMasterPassword) {
        btnSubmitMasterPassword.addEventListener('click', () => {
            submitMasterPassword();
        });
    }

    if (savedServersList) {
        savedServersList.addEventListener('dragover', (e) => {
            if (draggedServerIndex !== null) {
                e.preventDefault();
                e.dataTransfer.dropEffect = 'move';
            }
        });
        savedServersList.addEventListener('drop', async (e) => {
            if (draggedServerIndex === null) return;
            if (e.target.closest('.server-card')) return;
            e.preventDefault();
            const fromIdx = draggedServerIndex;
            draggedServerIndex = null;
            const newIndex = serversList.length - 1;
            if (fromIdx !== newIndex && fromIdx >= 0 && fromIdx < serversList.length) {
                const [moved] = serversList.splice(fromIdx, 1);
                serversList.push(moved);
                if (editingServerIndex !== null) {
                    if (editingServerIndex === fromIdx) {
                        editingServerIndex = newIndex;
                    } else if (fromIdx < editingServerIndex) {
                        editingServerIndex--;
                    }
                }
                await saveServersToBackend();
                renderSavedServers();
            }
        });
    }

    let cryptoKey = null;
    let serversList = [];
    let serversLoaded = false;
    let serversLoadError = '';
    let editingServerIndex = null;
    let draggedServerIndex = null;


    const restoreVaultKeyFromCookie = async () => {
        const keyB64 = getVaultCookie();
        if (!keyB64) return false;
        try {
            const rawStr = atob(keyB64);
            const rawBytes = new Uint8Array(rawStr.length);
            for (let i = 0; i < rawStr.length; i++) {
                rawBytes[i] = rawStr.charCodeAt(i);
            }
            const key = await window.crypto.subtle.importKey(
                "raw", rawBytes, { name: "AES-GCM" }, true, ["encrypt", "decrypt"]
            );
            if (serversList.length > 0) {
                const testSrv = serversList.find(s => s.enc_pass || s.enc_key);
                if (testSrv) {
                    const sampleField = testSrv.enc_pass || testSrv.enc_key;
                    const plain = await decryptData(sampleField, key);
                    if (plain === "[Ошибка расшифровки]") {
                        clearVaultCookie();
                        return false;
                    }
                }
            }
            cryptoKey = key;
            return true;
        } catch (e) {
            clearVaultCookie();
            return false;
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

            if (!cryptoKey && serversList.length > 0) {
                await restoreVaultKeyFromCookie();
            }

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
        const masterPasswordInput = document.getElementById('masterPasswordInput');
        if (masterPasswordInput) {
            masterPasswordInput.value = '';
            setTimeout(() => masterPasswordInput.focus(), 100);
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
                    <div style="margin-bottom: 15px; font-size: 0.95rem; color: var(--text-secondary);">Хранилище серверов защищено мастер-паролем</div>
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
            'proxy_host': 'Proxy',
            'freedom_host': 'Freedom',
            'sub_vps_host': 'Подписки',
            'vps_host': 'Одиночный',
            'backup_vps_host': 'Бэкап',
            'recovery_vps_host': 'Восстановление',
            'update_vps_host': 'Обновление'
        };

        for (let index = 0; index < serversList.length; index++) {
            const srv = serversList[index];
            const isLocked = !!srv.locked;
            const badge = srv.target_type && typeNames[srv.target_type] 
                ? `<span class="server-card-badge">${typeNames[srv.target_type]}</span>` 
                : '';
            const lockIcon = isLocked
                ? `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>`
                : `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 9.9-1"/></svg>`;
            
            const panelBtn = srv.panel_url 
                ? `<a href="${escapeHtml(srv.panel_url)}" target="_blank" rel="noopener noreferrer" class="btn-open-panel-card" title="Открыть веб-панель (${escapeHtml(srv.panel_url)})">
                    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
                </a>`
                : '';
            
            const card = document.createElement('div');
            card.className = `server-card ${isLocked ? 'is-locked' : ''}`;
            card.draggable = true;
            card.dataset.serverIndex = index;
            card.innerHTML = `
                <div class="server-card-info">
                    <div class="server-card-header">
                        ${badge}
                        <button type="button" class="btn-lock-toggle ${isLocked ? 'locked' : ''}" 
                            title="${isLocked ? 'Разблокировать управление сервером' : 'Заблокировать (защита от случайных действий)'}" 
                            onclick="window.toggleServerLock(${index})">
                            ${lockIcon}
                        </button>
                        <button type="button" class="btn-test-ssh-card" id="btn-test-ssh-${index}"
                            title="Проверить SSH-соединение"
                            onclick="window.testServerSSH(${index}, this)">
                            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
                        </button>
                        ${panelBtn}
                    </div>
                    <div class="server-card-host">${escapeHtml(srv.host || 'Без IP')}</div>
                    <div class="server-card-details">
                        <span><svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg> ${escapeHtml(srv.user || 'root')}</span>
                        <span><svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon"><path d="M8 12a4 4 0 0 1 8 0V4a4 4 0 0 1-8 0v8z"/><line x1="12" y1="16" x2="12" y2="22"/><line x1="10" y1="2" x2="10" y2="4"/><line x1="14" y1="2" x2="14" y2="4"/></svg> ${srv.port || 22}</span>
                    </div>
                </div>
                <div class="server-card-actions">
                    <button type="button" class="btn-icon-sm" title="${isLocked ? 'Сервер заблокирован' : 'Заполнить поля'}" ${isLocked ? 'disabled' : ''} onclick="window.fillServerData(${index})">
                        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><path d="M12 18v-6"/><path d="M9 15h6"/></svg>
                    </button>
                    <button type="button" class="btn-icon-sm" title="${isLocked ? 'Сервер заблокирован' : 'Копировать пароль'}" ${isLocked ? 'disabled' : ''} onclick="window.copyServerPass(${index})">
                        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
                    </button>
                    <button type="button" class="btn-icon-sm" title="${isLocked ? 'Сервер заблокирован' : 'Редактировать'}" ${isLocked ? 'disabled' : ''} onclick="window.editServer(${index})">
                        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z"/></svg>
                    </button>
                    <button type="button" class="btn-icon-sm danger" title="${isLocked ? 'Сервер заблокирован' : 'Удалить'}" ${isLocked ? 'disabled' : ''} onclick="window.deleteServer(${index})">
                        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><line x1="10" y1="11" x2="10" y2="17"/><line x1="14" y1="11" x2="14" y2="17"/></svg>
                    </button>
                </div>
            `;

            card.addEventListener('dragstart', (e) => {
                if (e.target.closest('button, a, input, textarea, select')) {
                    e.preventDefault();
                    return;
                }
                draggedServerIndex = index;
                e.dataTransfer.effectAllowed = 'copyMove';
                e.dataTransfer.setData('text/plain', String(index));
                document.body.classList.add('dragging-server-card');
                setTimeout(() => card.classList.add('dragging'), 0);
            });

            card.addEventListener('dragover', (e) => {
                if (draggedServerIndex === null) return;
                e.preventDefault();
                e.dataTransfer.dropEffect = 'move';
                const rect = card.getBoundingClientRect();
                const isAfter = e.clientY > rect.top + rect.height / 2;
                if (isAfter) {
                    card.classList.remove('drag-over-top');
                    card.classList.add('drag-over-bottom');
                } else {
                    card.classList.remove('drag-over-bottom');
                    card.classList.add('drag-over-top');
                }
            });

            card.addEventListener('dragleave', (e) => {
                if (!card.contains(e.relatedTarget)) {
                    card.classList.remove('drag-over-top', 'drag-over-bottom');
                }
            });

            card.addEventListener('dragend', () => {
                draggedServerIndex = null;
                document.body.classList.remove('dragging-server-card');
                document.querySelectorAll('.server-drop-over').forEach(el => el.classList.remove('server-drop-over'));
                if (savedServersList) {
                    savedServersList.querySelectorAll('.server-card').forEach(c => {
                        c.classList.remove('dragging', 'drag-over-top', 'drag-over-bottom');
                    });
                }
            });

            card.addEventListener('drop', async (e) => {
                e.preventDefault();
                e.stopPropagation();
                card.classList.remove('drag-over-top', 'drag-over-bottom');
                if (draggedServerIndex === null || draggedServerIndex === undefined) return;

                const fromIdx = draggedServerIndex;
                draggedServerIndex = null;

                const rect = card.getBoundingClientRect();
                const isAfter = e.clientY > rect.top + rect.height / 2;
                let newIndex = isAfter ? index + 1 : index;
                if (fromIdx < newIndex) {
                    newIndex--;
                }

                if (fromIdx !== newIndex && fromIdx >= 0 && fromIdx < serversList.length && newIndex >= 0 && newIndex < serversList.length) {
                    const [moved] = serversList.splice(fromIdx, 1);
                    serversList.splice(newIndex, 0, moved);
                    if (editingServerIndex !== null) {
                        if (editingServerIndex === fromIdx) {
                            editingServerIndex = newIndex;
                        } else if (fromIdx < editingServerIndex && newIndex >= editingServerIndex) {
                            editingServerIndex--;
                        } else if (fromIdx > editingServerIndex && newIndex <= editingServerIndex) {
                            editingServerIndex++;
                        }
                    }
                    await saveServersToBackend();
                    renderSavedServers();
                }
            });

            savedServersList.appendChild(card);
        }
    };

    window.testServerSSH = async (index, btnElement) => {
        if (!cryptoKey) {
            showToast('Сначала разблокируйте список', 'warning');
            return;
        }
        const srv = serversList[index];
        if (!srv) return;
        if (!srv.host) {
            showToast('Укажите домен / IP адрес сервера', 'warning');
            return;
        }

        const btn = btnElement || document.getElementById(`btn-test-ssh-${index}`);
        const origIconHtml = btn ? btn.innerHTML : '';
        if (btn) {
            btn.disabled = true;
            btn.classList.add('testing');
            btn.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="spin"><line x1="12" y1="2" x2="12" y2="6"/><line x1="12" y1="18" x2="12" y2="22"/><line x1="4.93" y1="4.93" x2="7.76" y2="7.76"/><line x1="16.24" y1="16.24" x2="19.07" y2="19.07"/><line x1="2" y1="12" x2="6" y2="12"/><line x1="18" y1="12" x2="22" y2="12"/><line x1="4.93" y1="19.07" x2="7.76" y2="16.24"/><line x1="16.24" y1="7.76" x2="19.07" y2="4.93"/></svg>`;
        }

        try {
            const pass = srv.enc_pass ? await decryptData(srv.enc_pass, cryptoKey) : '';
            const key = srv.enc_key ? await decryptData(srv.enc_key, cryptoKey) : '';
            const port = parseInt(srv.port) || 22;
            const user = (srv.user || 'root').trim();

            const resp = await fetch('/api/ssh/test', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    vps_host: srv.host,
                    vps_port: port,
                    vps_user: user,
                    vps_password: pass,
                    vps_key: key
                })
            });
            const res = await resp.json();
            if (res.ok) {
                showToast(`Успешное SSH-подключение к ${srv.host}:${port}`, 'success');
                if (btn) {
                    btn.classList.remove('testing');
                    btn.classList.add('success');
                    btn.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6L9 17l-5-5"/></svg>`;
                    setTimeout(() => {
                        if (btn) {
                            btn.classList.remove('success');
                            btn.innerHTML = origIconHtml;
                            btn.disabled = false;
                        }
                    }, 2000);
                }
            } else {
                showToast(`Ошибка SSH (${srv.host}): ${res.message || 'Ошибка подключения'}`, 'error');
                if (btn) {
                    btn.classList.remove('testing');
                    btn.classList.add('error');
                    btn.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>`;
                    setTimeout(() => {
                        if (btn) {
                            btn.classList.remove('error');
                            btn.innerHTML = origIconHtml;
                            btn.disabled = false;
                        }
                    }, 2500);
                }
            }
        } catch (err) {
            showToast(`Ошибка проверки SSH: ${err.message || err}`, 'error');
            if (btn) {
                btn.classList.remove('testing');
                btn.classList.add('error');
                btn.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>`;
                setTimeout(() => {
                    if (btn) {
                        btn.classList.remove('error');
                        btn.innerHTML = origIconHtml;
                        btn.disabled = false;
                    }
                }, 2500);
            }
        }
    };

    window.toggleServerLock = async (index) => {
        const srv = serversList[index];
        if (!srv) return;
        const willLock = !srv.locked;
        srv.locked = willLock;
        await saveServersToBackend();
        renderSavedServers();
        showToast(willLock ? 'Сервер заблокирован от случайных действий' : 'Сервер разблокирован', 'info');
    };

    window.applyServerData = async (index, hostId) => {
        const srv = serversList[index];
        if (!srv) return;
        
        let prefix = hostId.replace('_host', '');
        
        const elHost = document.getElementById(hostId);
        if (elHost) {
            elHost.value = srv.host || '';
            elHost.dispatchEvent(new Event('input', { bubbles: true }));
            elHost.dispatchEvent(new Event('change', { bubbles: true }));
        }
        
        if (hostId === 'backup_vps_host') window.__updateBackupName();
        
        const elPort = document.getElementById(`${prefix}_port`);
        if (elPort) {
            elPort.value = srv.port || 22;
            elPort.dispatchEvent(new Event('input', { bubbles: true }));
            elPort.dispatchEvent(new Event('change', { bubbles: true }));
        }
        
        const elUser = document.getElementById(`${prefix}_user`);
        if (elUser) {
            elUser.value = srv.user || 'root';
            elUser.dispatchEvent(new Event('input', { bubbles: true }));
            elUser.dispatchEvent(new Event('change', { bubbles: true }));
        }
        
        const authType = srv.auth_type === 'key' ? 'key' : 'password';
        const elAuthType = document.getElementById(`${prefix}_auth_type`) || document.getElementById(`${prefix.replace('_vps', '')}_auth_type`);
        if (elAuthType) {
            elAuthType.value = authType;
            elAuthType.dispatchEvent(new Event('change', { bubbles: true }));
        }
        
        const pass = await decryptData(srv.enc_pass, cryptoKey);
        const elPass = document.getElementById(`${prefix}_password`);
        if (elPass) {
            elPass.value = pass || '';
            elPass.dispatchEvent(new Event('input', { bubbles: true }));
            elPass.dispatchEvent(new Event('change', { bubbles: true }));
        }
        
        const key = srv.enc_key ? await decryptData(srv.enc_key, cryptoKey) : '';
        const elKey = document.getElementById(`${prefix}_key`);
        if (elKey) {
            elKey.value = key || '';
            elKey.dispatchEvent(new Event('input', { bubbles: true }));
            elKey.dispatchEvent(new Event('change', { bubbles: true }));
        }

        if (window.__getGlowRefresher()) window.__getGlowRefresher();

        showToast('Данные сервера успешно подставлены!', 'success');
    };

    const initServerDropZones = () => {
        const dropZones = document.querySelectorAll('.server-drop-zone, [data-drop-host]');
        
        dropZones.forEach(zone => {
            let dragEnterCounter = 0;

            zone.addEventListener('dragenter', (e) => {
                if (draggedServerIndex === null && !e.dataTransfer.types.includes('text/plain')) return;
                e.preventDefault();
                dragEnterCounter++;
                zone.classList.add('server-drop-over');
            });

            zone.addEventListener('dragover', (e) => {
                if (draggedServerIndex === null && !e.dataTransfer.types.includes('text/plain')) return;
                e.preventDefault();
                e.dataTransfer.dropEffect = 'copy';
                if (!zone.classList.contains('server-drop-over')) {
                    zone.classList.add('server-drop-over');
                }
            });

            zone.addEventListener('dragleave', (e) => {
                dragEnterCounter--;
                if (dragEnterCounter <= 0) {
                    dragEnterCounter = 0;
                    zone.classList.remove('server-drop-over');
                }
            });

            zone.addEventListener('drop', async (e) => {
                dragEnterCounter = 0;
                zone.classList.remove('server-drop-over');
                document.body.classList.remove('dragging-server-card');
                
                const rawIdx = draggedServerIndex !== null 
                    ? draggedServerIndex 
                    : e.dataTransfer.getData('text/plain');
                
                const index = parseInt(rawIdx, 10);
                if (isNaN(index) || index < 0 || index >= serversList.length) return;

                e.preventDefault();
                e.stopPropagation();

                const hostId = zone.dataset.dropHost || (zone.querySelector('input[id$="_host"], input[id="vps_host"]') || {}).id;
                if (!hostId) return;

                if (!cryptoKey) {
                    showToast('Сначала разблокируйте список сохраненных серверов', 'warning');
                    return;
                }

                const srv = serversList[index];
                if (!srv) return;
                if (srv.locked) {
                    zone.classList.add('server-drop-locked');
                    setTimeout(() => zone.classList.remove('server-drop-locked'), 500);
                    showToast('Сервер заблокирован. Снимите замочек для выполнения действий.', 'warning');
                    return;
                }

                await applyServerData(index, hostId);
                zone.classList.add('server-drop-success');
                setTimeout(() => zone.classList.remove('server-drop-success'), 850);
            });
        });

        window.addEventListener('dragend', () => {
            draggedServerIndex = null;
            document.body.classList.remove('dragging-server-card');
            document.querySelectorAll('.server-drop-over').forEach(el => el.classList.remove('server-drop-over'));
        });
    };

    window.fillServerData = async (index) => {
        if (!cryptoKey) { showToast('Сначала разблокируйте список', 'warning'); return; }
        const srv = serversList[index];
        if (!srv) return;
        if (srv.locked) {
            showToast('Сервер заблокирован. Снимите замочек для выполнения действий.', 'warning');
            return;
        }

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
        if (!srv) return;
        if (srv.locked) {
            showToast('Сервер заблокирован. Снимите замочек для выполнения действий.', 'warning');
            return;
        }
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
        if (btnSaveServerText) btnSaveServerText.textContent = index === null ? 'Сохранить' : 'Обновить сервер';
        if (btnCancelEditServer) btnCancelEditServer.style.display = index === null ? 'none' : 'block';
    };

    window.editServer = async (index) => {
        if (!cryptoKey) { showToast('Сначала разблокируйте список', 'warning'); return; }
        const srv = serversList[index];
        if (!srv) return;
        if (srv.locked) {
            showToast('Сервер заблокирован. Снимите замочек для выполнения действий.', 'warning');
            return;
        }

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
        if (smPanelUrl) smPanelUrl.value = srv.panel_url || '';

        setEditingMode(index);
        if (window.__getGlowRefresher()) window.__getGlowRefresher();

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
        if (smPanelUrl) smPanelUrl.value = '';
        smUser.value = 'root';
        smPort.value = '22';
        if (smAuthType) {
            smAuthType.value = 'password';
            smAuthType.dispatchEvent(new Event('change', { bubbles: true }));
        }
        showToast('Редактирование отменено', 'success');
    };

    window.deleteServer = async (index) => {
        const srv = serversList[index];
        if (srv && srv.locked) {
            showToast('Сервер заблокирован. Снимите замочек для выполнения действий.', 'warning');
            return;
        }
        if (!await showConfirm('Удалить этот сервер из сохраненных?', 'Удаление сервера', { confirmText: 'Удалить', danger: true, icon: '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>' })) return;
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
            if (!await showConfirm('ВНИМАНИЕ! Это действие удалит файл со всеми сохраненными серверами и сбросит PIN-код. Продолжить?', 'Сброс всех серверов', { confirmText: 'Сбросить все', danger: true, icon: '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>' })) return;
            try {
                await fetch('/api/servers/reset', { method: 'DELETE' });
                serversList = [];
                serversLoaded = true;
                serversLoadError = '';
                clearVaultCookie();
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
            const panelUrl = smPanelUrl ? smPanelUrl.value.trim() : '';

            const isLocked = (editingServerIndex !== null && serversList[editingServerIndex]) ? !!serversList[editingServerIndex].locked : false;
            const newData = {
                target_type: smTargetType ? smTargetType.value : '',
                auth_type: authType,
                host: host,
                user: smUser.value.trim() || 'root',
                port: smPort.value || 22,
                enc_pass: encPass,
                enc_key: encKey,
                panel_url: panelUrl,
                locked: isLocked
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
            if (smPanelUrl) smPanelUrl.value = '';
            smUser.value = 'root';
            smPort.value = '22';
            if (smAuthType) {
                smAuthType.value = 'password';
                smAuthType.dispatchEvent(new Event('change', { bubbles: true }));
            }
            
            renderSavedServers();
        };

    if (btnTestServerForm) {
        const origTestHtml = btnTestServerForm.innerHTML;
        btnTestServerForm.addEventListener('click', async () => {
            const host = smHost ? smHost.value.trim() : '';
            if (!host) {
                showToast('Укажите IP или Домен сервера', 'warning');
                if (smHost) smHost.focus();
                return;
            }

            const user = (smUser ? smUser.value.trim() : '') || 'root';
            const port = parseInt(smPort ? smPort.value : 22) || 22;
            const authType = smAuthType ? smAuthType.value : 'password';
            const pass = authType === 'key' ? '' : (smPass ? smPass.value : '');
            const key = authType === 'key' ? (smKey ? smKey.value : '') : '';

            btnTestServerForm.disabled = true;
            btnTestServerForm.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="spin"><line x1="12" y1="2" x2="12" y2="6"/><line x1="12" y1="18" x2="12" y2="22"/><line x1="4.93" y1="4.93" x2="7.76" y2="7.76"/><line x1="16.24" y1="16.24" x2="19.07" y2="19.07"/><line x1="2" y1="12" x2="6" y2="12"/><line x1="18" y1="12" x2="22" y2="12"/><line x1="4.93" y1="19.07" x2="7.76" y2="16.24"/><line x1="16.24" y1="7.76" x2="19.07" y2="4.93"/></svg><span>Тест...</span>`;

            try {
                const resp = await fetch('/api/ssh/test', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        vps_host: host,
                        vps_port: port,
                        vps_user: user,
                        vps_password: pass,
                        vps_key: key
                    })
                });
                const res = await resp.json();
                if (res.ok) {
                    showToast(`Успешное SSH-подключение к ${host}:${port}`, 'success');
                    btnTestServerForm.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#22c55e" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6L9 17l-5-5"/></svg><span style="color: #22c55e;">OK</span>`;
                } else {
                    showToast(`Ошибка SSH (${host}): ${res.message || 'Ошибка подключения'}`, 'error');
                    btnTestServerForm.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#ef4444" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg><span style="color: #ef4444;">Ошибка</span>`;
                }
            } catch (err) {
                showToast(`Ошибка сети: ${err.message}`, 'error');
                btnTestServerForm.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#ef4444" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg><span style="color: #ef4444;">Ошибка</span>`;
            } finally {
                setTimeout(() => {
                    if (btnTestServerForm) {
                        btnTestServerForm.disabled = false;
                        btnTestServerForm.innerHTML = origTestHtml;
                    }
                }, 2500);
            }
        });
    }

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
        const inputEl = document.getElementById('masterPasswordInput');
        const pass = inputEl ? inputEl.value.trim() : '';
        if (!pass) {
            showToast('Введите мастер-пароль или PIN!', 'warning');
            return;
        }

        const keyV2 = await deriveKeyV2(pass);
        const keyV1 = await deriveKeyV1(pass);

        if (serversList.length > 0) {
            const testSrv = serversList.find(s => s.enc_pass || s.enc_key);
            if (testSrv) {
                const sampleField = testSrv.enc_pass || testSrv.enc_key;
                const sampleVer = getPayloadVersion(sampleField);

                let matchedVersion = null;

                if (sampleVer === 2) {
                    const tryV2 = await decryptData(sampleField, keyV2);
                    if (tryV2 !== "[Ошибка расшифровки]") {
                        matchedVersion = 2;
                    }
                } else {
                    const tryV1 = await decryptData(sampleField, keyV1);
                    if (tryV1 !== "[Ошибка расшифровки]") {
                        matchedVersion = 1;
                    } else {
                        const tryV2 = await decryptData(sampleField, keyV2);
                        if (tryV2 !== "[Ошибка расшифровки]") {
                            matchedVersion = 2;
                        }
                    }
                }

                if (!matchedVersion) {
                    showToast('Неверный мастер-пароль / PIN!', 'error');
                    if (inputEl) {
                        inputEl.value = '';
                        inputEl.focus();
                    }
                    return;
                }

                // Seamless auto-migration: if opened with legacy V1 key, upgrade all secrets to V2
                if (matchedVersion === 1) {
                    let migratedCount = 0;
                    for (let srv of serversList) {
                        if (srv.enc_pass && getPayloadVersion(srv.enc_pass) === 1) {
                            const plain = await decryptData(srv.enc_pass, keyV1);
                            if (plain && plain !== "[Ошибка расшифровки]") {
                                srv.enc_pass = await encryptData(plain, keyV2);
                                migratedCount++;
                            }
                        }
                        if (srv.enc_key && getPayloadVersion(srv.enc_key) === 1) {
                            const plain = await decryptData(srv.enc_key, keyV1);
                            if (plain && plain !== "[Ошибка расшифровки]") {
                                srv.enc_key = await encryptData(plain, keyV2);
                                migratedCount++;
                            }
                        }
                    }
                    if (migratedCount > 0) {
                        await saveServersToBackend();
                        showToast('<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg> Хранилище серверов успешно обновлено на усиленный формат V2 (PBKDF2 600k)!', 'success');
                    }
                }
            }
        }

        cryptoKey = keyV2;
        try {
            const exported = await window.crypto.subtle.exportKey("raw", keyV2);
            const keyB64 = btoa(String.fromCharCode(...new Uint8Array(exported)));
            setVaultCookie(keyB64);
        } catch (e) { }
        masterPasswordModal.classList.remove('active');
        if (inputEl) inputEl.value = '';

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

window.fetchServers = fetchServers;
window.saveServersToBackend = saveServersToBackend;
window.renderSavedServers = renderSavedServers;
window.promptMasterPassword = promptMasterPassword;
window.submitMasterPassword = submitMasterPassword;
window.restoreVaultKeyFromCookie = restoreVaultKeyFromCookie;
window.setEditingMode = setEditingMode;
window.doSaveServer = doSaveServer;
window.initServerDropZones = initServerDropZones;
window.getServersList = () => serversList;
window.setServersList = (v) => { serversList = v; };
});
