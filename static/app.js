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

    const qrModal = document.getElementById('qrModal');
    const qrModalImg = document.getElementById('qrModalImg');
    const qrModalTitle = document.getElementById('qrModalTitle');
    const qrModalUrl = document.getElementById('qrModalUrl');
    const btnCloseQr = document.getElementById('btnCloseQr');

    btnCloseQr.addEventListener('click', () => {
        qrModal.classList.add('hidden');
    });

    qrModal.addEventListener('click', (e) => {
        if (e.target === qrModal) {
            qrModal.classList.add('hidden');
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
            btnCopyLogs.textContent = '❌ Ошибка';
            setTimeout(() => { btnCopyLogs.textContent = '📋 Копировать лог'; }, 2000);
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
            const isCascade = cascadeYes.checked;
            const payload = {
                is_cascade: isCascade,
                vps_host: document.getElementById('vps_host').value.trim(),
                vps_port: parseInt(document.getElementById('vps_port').value) || 22,
                vps_user: document.getElementById('vps_user').value.trim() || 'root',
                vps_password: document.getElementById('vps_password').value,
                vps_key: document.getElementById('vps_key').value,

                freedom_host: document.getElementById('freedom_host').value.trim(),
                freedom_port: parseInt(document.getElementById('freedom_port').value) || 22,
                freedom_user: document.getElementById('freedom_user').value.trim() || 'root',
                freedom_password: document.getElementById('freedom_password').value,
                freedom_xui_username: document.getElementById('freedom_xui_username').value.trim(),
                freedom_xui_password: document.getElementById('freedom_xui_password').value.trim(),
                freedom_sub_secret: document.getElementById('freedom_sub_secret').value.trim(),
                freedom_client_name: document.getElementById('freedom_client_name').value.trim(),

                proxy_host: document.getElementById('proxy_host').value.trim(),
                proxy_port: parseInt(document.getElementById('proxy_port').value) || 22,
                proxy_user: document.getElementById('proxy_user').value.trim() || 'root',
                proxy_password: document.getElementById('proxy_password').value,
                proxy_xui_username: document.getElementById('proxy_xui_username').value.trim(),
                proxy_xui_password: document.getElementById('proxy_xui_password').value.trim(),
                proxy_sub_secret: document.getElementById('proxy_sub_secret').value.trim(),
                proxy_client_tcp_list: document.getElementById('proxy_client_tcp_list').value.trim(),
                proxy_client_xhttp_list: document.getElementById('proxy_client_xhttp_list').value.trim(),

                xui_username: document.getElementById('xui_username').value.trim(),
                xui_password: document.getElementById('xui_password').value.trim(),
                sub_secret: document.getElementById('sub_secret').value.trim(),
                xui_version: document.getElementById('xui_version').value.trim(),
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
        const singlePanelSection = document.getElementById('singlePanelSection');
        const cascadePanelSection = document.getElementById('cascadePanelSection');

        try {
            const resp = await fetch('/api/config');
            const cfg = await resp.json();

            if (cfg && Object.keys(cfg).length > 0) {
                if (cfg.is_cascade) {
                    cascadeYes.checked = true;
                    cascadeNodeSection.classList.remove('hidden');
                    singleNodeSection.classList.add('hidden');
                    if (cascadePanelSection) cascadePanelSection.classList.remove('hidden');
                    if (singlePanelSection) singlePanelSection.classList.add('hidden');
                } else {
                    cascadeNo.checked = true;
                    singleNodeSection.classList.remove('hidden');
                    cascadeNodeSection.classList.add('hidden');
                    if (singlePanelSection) singlePanelSection.classList.remove('hidden');
                    if (cascadePanelSection) cascadePanelSection.classList.add('hidden');
                }

                if (cfg.vps_host) document.getElementById('vps_host').value = cfg.vps_host;
                if (cfg.vps_port) document.getElementById('vps_port').value = cfg.vps_port;
                if (cfg.vps_user) document.getElementById('vps_user').value = cfg.vps_user;
                if (cfg.vps_password) document.getElementById('vps_password').value = cfg.vps_password;
                if (cfg.vps_key) {
                    document.getElementById('vps_key').value = cfg.vps_key;
                    keyRadio.checked = true;
                    keyGroup.classList.remove('hidden');
                    passGroup.classList.add('hidden');
                }

                if (cfg.freedom_host) document.getElementById('freedom_host').value = cfg.freedom_host;
                if (cfg.freedom_port) document.getElementById('freedom_port').value = cfg.freedom_port;
                if (cfg.freedom_user) document.getElementById('freedom_user').value = cfg.freedom_user;
                if (cfg.freedom_password) document.getElementById('freedom_password').value = cfg.freedom_password;
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
                if (cfg.proxy_xui_username) document.getElementById('proxy_xui_username').value = cfg.proxy_xui_username;
                if (cfg.proxy_xui_password) document.getElementById('proxy_xui_password').value = cfg.proxy_xui_password;
                if (cfg.proxy_sub_secret) {
                    document.getElementById('proxy_sub_secret').value = cfg.proxy_sub_secret;
                } else if (document.getElementById('proxy_sub_secret') && !document.getElementById('proxy_sub_secret').value) {
                    document.getElementById('proxy_sub_secret').value = randomDigits(16);
                }
                if (cfg.proxy_client_tcp_list) document.getElementById('proxy_client_tcp_list').value = cfg.proxy_client_tcp_list;
                if (cfg.proxy_client_xhttp_list) document.getElementById('proxy_client_xhttp_list').value = cfg.proxy_client_xhttp_list;

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
            } else {
                if (!document.getElementById('sub_secret').value) document.getElementById('sub_secret').value = randomDigits(16);
                if (document.getElementById('freedom_sub_secret') && !document.getElementById('freedom_sub_secret').value) document.getElementById('freedom_sub_secret').value = randomDigits(16);
                if (document.getElementById('proxy_sub_secret') && !document.getElementById('proxy_sub_secret').value) document.getElementById('proxy_sub_secret').value = randomDigits(16);
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

    passRadio.addEventListener('change', () => {
        passGroup.classList.remove('hidden');
        keyGroup.classList.add('hidden');
        resetSSHValidation();
    });

    keyRadio.addEventListener('change', () => {
        keyGroup.classList.remove('hidden');
        passGroup.classList.add('hidden');
        resetSSHValidation();
    });

    cascadeNo.addEventListener('change', () => {
        singleNodeSection.classList.remove('hidden');
        singleNodeSection.classList.add('fade-slide-in');
        cascadeNodeSection.classList.add('hidden');
        cascadeNodeSection.classList.remove('fade-slide-in');
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

    cascadeYes.addEventListener('change', () => {
        cascadeNodeSection.classList.remove('hidden');
        cascadeNodeSection.classList.add('fade-slide-in');
        singleNodeSection.classList.add('hidden');
        singleNodeSection.classList.remove('fade-slide-in');
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
            updateBadgeStatus('Готов к настройке', '#3b82f6');
        } else if (currentStep === 2) {
            updateBadgeStatus('Настройка параметров', '#06b6d4');
        }
    };

    document.querySelectorAll('.step').forEach(stepEl => {
        stepEl.addEventListener('click', () => {
            const stepNum = parseInt(stepEl.getAttribute('data-step'));
            showStep(stepNum);
        });
    });

    btnNext1.addEventListener('click', () => {
        showStep(2);
    });

    document.getElementById('btnBack2').addEventListener('click', () => showStep(1));

    btnTestSSH.addEventListener('click', async () => {
        const isCascade = cascadeYes.checked;
        const origBtnHtml = btnTestSSH.innerHTML;
        btnTestSSH.disabled = true;
        btnTestSSH.innerHTML = '<span class="btn-spinner"></span> Проверка...';
        btnNext1.classList.add('hidden');

        if (!isCascade) {
            const host = document.getElementById('vps_host').value.trim();
            const port = parseInt(document.getElementById('vps_port').value) || 22;
            const user = document.getElementById('vps_user').value.trim() || 'root';
            const password = document.getElementById('vps_password').value;
            const key_data = document.getElementById('vps_key').value;

            if (!host) {
                testResult.className = 'test-result error';
                testResult.textContent = '❌ Укажите домен / IP адрес сервера';
                btnTestSSH.disabled = false;
                btnTestSSH.innerHTML = origBtnHtml;
                return;
            }

            try {
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
            } catch (err) {
                testResult.className = 'test-result error';
                testResult.textContent = `❌ Ошибка запроса: ${err.message}`;
            } finally {
                btnTestSSH.disabled = false;
                btnTestSSH.innerHTML = origBtnHtml;
            }
        } else {
            const fHost = document.getElementById('freedom_host').value.trim();
            const fPort = parseInt(document.getElementById('freedom_port').value) || 22;
            const fUser = document.getElementById('freedom_user').value.trim() || 'root';
            const fPass = document.getElementById('freedom_password').value;

            const pHost = document.getElementById('proxy_host').value.trim();
            const pPort = parseInt(document.getElementById('proxy_port').value) || 22;
            const pUser = document.getElementById('proxy_user').value.trim() || 'root';
            const pPass = document.getElementById('proxy_password').value;

            if (!fHost || !pHost) {
                testResult.className = 'test-result error';
                testResult.textContent = '❌ Укажите хосты для обоих серверов (Freedom Node и Proxy Node)';
                btnTestSSH.disabled = false;
                btnTestSSH.innerHTML = origBtnHtml;
                return;
            }

            try {
                const r1 = await fetch('/api/ssh/test', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ vps_host: fHost, vps_port: fPort, vps_user: fUser, vps_password: fPass })
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
                    body: JSON.stringify({ vps_host: pHost, vps_port: pPort, vps_user: pUser, vps_password: pPass })
                });
                const res2 = await r2.json();

                if (!res2.ok) {
                    testResult.className = 'test-result error';
                    testResult.textContent = `❌ Ошибка подключения к Proxy Node (${pHost}): ${res2.message}`;
                    return;
                }

                testResult.className = 'test-result success';
                testResult.textContent = `✅ Успешная проверка обоих серверов (${fHost} и ${pHost})`;
                btnNext1.classList.remove('hidden');

            } catch (err) {
                testResult.className = 'test-result error';
                testResult.textContent = `❌ Ошибка запроса: ${err.message}`;
            } finally {
                btnTestSSH.disabled = false;
                btnTestSSH.innerHTML = origBtnHtml;
            }
        }
    });

    const btnStartDeploy = document.getElementById('btnStartDeploy');
    const terminalLogs = document.getElementById('terminalLogs');
    const btnCopyLogs = document.getElementById('btnCopyLogs');

    btnCopyLogs.addEventListener('click', () => {
        const text = terminalLogs.innerText;
        copyToClipboard(text, btnCopyLogs);
    });

    let isUserScrolledUp = false;

    terminalLogs.addEventListener('scroll', () => {
        const distanceFromBottom = terminalLogs.scrollHeight - terminalLogs.clientHeight - terminalLogs.scrollTop;
        isUserScrolledUp = distanceFromBottom > 30;
    });

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

    btnStartDeploy.addEventListener('click', async () => {
        showStep(3);
        updateBadgeStatus('Развертывание...', '#f59e0b', true);
        startDeployTimer();
        isUserScrolledUp = false;
        terminalLogs.innerHTML = '';
        appendLog('[INIT] Starting deployment process...', 'info');

        const isCascade = cascadeYes.checked;
        const commonVersion = document.getElementById('xui_version').value.trim() || '3.6.0';

        let payload = {
            is_cascade: isCascade,
            xui_version: commonVersion
        };

        if (!isCascade) {
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
        } else {
            payload.freedom_host = document.getElementById('freedom_host').value.trim();
            payload.freedom_port = parseInt(document.getElementById('freedom_port').value) || 22;
            payload.freedom_user = document.getElementById('freedom_user').value.trim() || 'root';
            payload.freedom_password = document.getElementById('freedom_password').value;
            payload.freedom_xui_username = document.getElementById('freedom_xui_username').value.trim() || 'admin';
            payload.freedom_xui_password = document.getElementById('freedom_xui_password').value.trim() || 'admin';
            payload.freedom_sub_secret = document.getElementById('freedom_sub_secret').value.trim() || randomDigits(16);
            payload.freedom_xui_version = commonVersion;
            payload.freedom_client_name = document.getElementById('freedom_client_name').value.trim() || 'local-proxy-node-client';

            payload.proxy_host = document.getElementById('proxy_host').value.trim();
            payload.proxy_port = parseInt(document.getElementById('proxy_port').value) || 22;
            payload.proxy_user = document.getElementById('proxy_user').value.trim() || 'root';
            payload.proxy_password = document.getElementById('proxy_password').value;
            payload.proxy_xui_username = document.getElementById('proxy_xui_username').value.trim() || 'admin';
            payload.proxy_xui_password = document.getElementById('proxy_xui_password').value.trim() || 'admin';
            payload.proxy_sub_secret = document.getElementById('proxy_sub_secret').value.trim() || randomDigits(16);
            payload.proxy_xui_version = commonVersion;
            payload.proxy_client_tcp_list = document.getElementById('proxy_client_tcp_list').value.trim();
            payload.proxy_client_xhttp_list = document.getElementById('proxy_client_xhttp_list').value.trim();
        }

        if (!isCascade) {
            updateBadgeStatus(`Развертывание ${payload.vps_host || 'сервера'}...`, '#f59e0b', true);
        } else {
            updateBadgeStatus('Развертывание Freedom Node (1/2)...', '#f59e0b', true);
        }

        try {
            const resp = await fetch('/api/deploy', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const data = await resp.json();

            if (!data.ok) {
                appendLog(`[ERROR] ${data.message}`, 'error');
                updateBadgeStatus('Ошибка установки', '#ef4444');
                stopDeployTimer();
                return;
            }

            const evtSource = new EventSource('/api/deploy/logs');

            const handleFinish = () => {
                stopDeployTimer();
                if (statusPollTimer) clearInterval(statusPollTimer);
                try { evtSource.close(); } catch (e) { }
                checkFinalStatus(payload);
            };

            evtSource.onmessage = (event) => {
                try {
                    const item = JSON.parse(event.data);
                    if (item.message) {
                        appendLog(item.message, item.level);

                        if (item.message.includes('[STAGE 1/2]') || item.message.includes('[ЭТАП 1/2]')) {
                            updateBadgeStatus('Развертывание Freedom Node (1/2)...', '#f59e0b', true);
                        } else if (item.message.includes('[STAGE 2/2]') || item.message.includes('[ЭТАП 2/2]')) {
                            updateBadgeStatus('Развертывание Proxy Node (2/2)...', '#f59e0b', true);
                        } else if (item.message.includes('Starting deployment process') || item.message.includes('Запуск развертывания на одиночном')) {
                            updateBadgeStatus('Развертывание VPS...', '#f59e0b', true);
                        }
                    }
                    if (item.event === 'done' || item.status === 'completed' || item.status === 'failed') {
                        handleFinish();
                    }
                } catch (e) {
                    appendLog(event.data, 'info');
                }
            };

            evtSource.onerror = () => {
                handleFinish();
            };

            // Status Polling Fallback (every 1.5 seconds)
            statusPollTimer = setInterval(async () => {
                try {
                    const r = await fetch('/api/status');
                    const d = await r.json();
                    if (d.status === 'completed' || d.status === 'failed') {
                        handleFinish();
                    }
                } catch (e) { }
            }, 1500);

        } catch (err) {
            appendLog(`[ERROR] Не удалось начать развертывание: ${err.message}`, 'error');
            updateBadgeStatus('Ошибка установки', '#ef4444');
            stopDeployTimer();
        }
    });

    const checkFinalStatus = async (cfg) => {
        try {
            const res = await fetch('/api/status');
            const data = await res.json();

            if (data.status === 'completed') {
                updateBadgeStatus('Установка завершена', '#10b981');
                stopDeployTimer();

                const summaryCard = document.getElementById('summaryCard');
                summaryCard.classList.remove('hidden');

                const result = data.result || {};
                const isCascade = cfg.is_cascade || result.is_cascade;

                const panelsContainer = document.getElementById('panelsContainer');
                panelsContainer.innerHTML = '';

                const renderPanelBlock = (title, icon, url, user, pass, secret) => {
                    const block = document.createElement('div');
                    block.className = 'summary-section';
                    block.innerHTML = `
                        <div class="summary-section-title">${icon} ${title}</div>
                        <div class="summary-grid">
                            <div class="summary-item full-width">
                                <span class="label">Адрес панели:</span>
                                <div class="summary-val-row">
                                    <a href="${url}" target="_blank" class="val-link">${url}</a>
                                    <button type="button" class="btn-copy-val" data-copy="${url}" title="Копировать адрес">📋</button>
                                </div>
                            </div>
                            <div class="summary-item">
                                <span class="label">Логин админа:</span>
                                <div class="summary-val-row">
                                    <span class="val-bold">${user}</span>
                                    <button type="button" class="btn-copy-val" data-copy="${user}">📋</button>
                                </div>
                            </div>
                            <div class="summary-item">
                                <span class="label">Пароль админа:</span>
                                <div class="summary-val-row">
                                    <span class="secret-val" data-secret="${pass}">••••••••</span>
                                    <button type="button" class="btn-eye-secret" title="Показать/скрыть">👁️</button>
                                    <button type="button" class="btn-copy-val" data-copy="${pass}">📋</button>
                                </div>
                            </div>
                            <div class="summary-item full-width">
                                <span class="label">Секретная фраза:</span>
                                <div class="summary-val-row">
                                    <span class="secret-val" data-secret="${secret}">••••••••</span>
                                    <button type="button" class="btn-eye-secret" title="Показать/скрыть">👁️</button>
                                    <button type="button" class="btn-copy-val" data-copy="${secret}">📋</button>
                                </div>
                            </div>
                        </div>
                    `;

                    block.querySelectorAll('.btn-copy-val').forEach(btn => {
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

                if (isCascade) {
                    const freedomHost = result.freedom_domain || cfg.freedom_host || 'Freedom Node';
                    const freedomUrl = result.freedom_xui_url || `https://${freedomHost}/`;
                    const freedomUser = result.freedom_username || cfg.freedom_xui_username || cfg.xui_username || 'admin';
                    const freedomPass = result.freedom_password || cfg.freedom_xui_password || cfg.xui_password || 'admin';
                    const freedomSecret = result.freedom_sub_secret || cfg.freedom_sub_secret || cfg.sub_secret || '';

                    panelsContainer.appendChild(renderPanelBlock('1. Зарубежная панель (Freedom Node)', '🌐', freedomUrl, freedomUser, freedomPass, freedomSecret));

                    const proxyHost = result.domain || cfg.proxy_host || 'Proxy Node';
                    const proxyUrl = result.xui_url || `https://${proxyHost}/`;
                    const proxyUser = result.xui_username || cfg.proxy_xui_username || cfg.xui_username || 'admin';
                    const proxyPass = result.xui_password || cfg.proxy_xui_password || cfg.xui_password || 'admin';
                    const proxySecret = result.sub_secret || cfg.proxy_sub_secret || cfg.sub_secret || '';

                    panelsContainer.appendChild(renderPanelBlock('2. Местная панель (Proxy Node)', '🛡️', proxyUrl, proxyUser, proxyPass, proxySecret));
                } else {
                    const targetHost = result.domain || cfg.vps_host || cfg.domain;
                    const xuiUrl = result.xui_url || `https://${targetHost}/`;
                    const xuiUser = result.xui_username || cfg.xui_username || 'admin';
                    const xuiPass = result.xui_password || cfg.xui_password || 'admin';
                    const subSecret = result.sub_secret || cfg.sub_secret || '';

                    panelsContainer.appendChild(renderPanelBlock('Панель управления 3X-UI', '🔑', xuiUrl, xuiUser, xuiPass, subSecret));
                }

                const clientsContainer = document.getElementById('clientsContainer');
                clientsContainer.innerHTML = '';

                const clientsList = result.clients || [];
                const targetDomain = isCascade ? cfg.proxy_host : (cfg.vps_host || cfg.domain);
                if (clientsList.length === 0) {
                    const fallbackSub = `https://${targetDomain}:2096/${cfg.sub_secret}`;
                    clientsList.push({ name: cfg.xui_username, sub_url: fallbackSub, tcp_url: '', xhttp_url: '' });
                }

                clientsList.forEach(client => {
                    const card = document.createElement('div');
                    card.className = 'client-card';

                    let html = `
                        <div class="client-header">
                            <span class="client-name-badge">👤 Клиент: ${client.name}</span>
                        </div>
                        <div class="client-link-group">
                    `;

                    if (client.sub_url) {
                        html += `
                            <div class="client-link-label">🔗 Ссылка подписки</div>
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

                    if (client.sub_url) {
                        card.querySelector('.btn-copy-sub').onclick = (e) => copyToClipboard(client.sub_url, e.target);
                        card.querySelector('.btn-qr-sub').onclick = () => showQrModal(`QR: Подписка (${client.name})`, client.sub_url);
                    }
                    if (client.tcp_url) {
                        card.querySelector('.btn-copy-tcp').onclick = (e) => copyToClipboard(client.tcp_url, e.target);
                        card.querySelector('.btn-qr-tcp').onclick = () => showQrModal(`QR: VLESS TCP (${client.name})`, client.tcp_url);
                    }
                    if (client.xhttp_url) {
                        card.querySelector('.btn-copy-xhttp').onclick = (e) => copyToClipboard(client.xhttp_url, e.target);
                        card.querySelector('.btn-qr-xhttp').onclick = () => showQrModal(`QR: VLESS XHTTP (${client.name})`, client.xhttp_url);
                    }

                    clientsContainer.appendChild(card);
                });
            } else if (data.status === 'failed') {
                updateBadgeStatus('Ошибка развертывания', '#ef4444');
                stopDeployTimer();
            }
        } catch (e) {
            updateBadgeStatus('Ошибка развертывания', '#ef4444');
        }
    };
});
