/* forms.js — Deployment Mode UI, Wizard Navigation & Required-Field Validation — extracted from app.js (E1) */
document.addEventListener('DOMContentLoaded', () => {
    // ==========================================
    // Reusable SSH Fields Rendering (Phase F2)
    // ==========================================
    const renderSshFields = () => {
        const tpl = document.getElementById('tpl-ssh-fields');
        if (!tpl) return;
        document.querySelectorAll('[data-ssh-prefix]').forEach(hook => {
            const prefix = hook.getAttribute('data-ssh-prefix');
            const authBase = prefix.endsWith('_vps') ? prefix.slice(0, -4) : prefix;
            hook.innerHTML = tpl.innerHTML
                .replaceAll('{{P}}', prefix)
                .replaceAll('{{A}}', authBase)
                .replaceAll('{{HOST_LABEL}}', hook.getAttribute('data-host-label') || 'Домен')
                .replaceAll('{{HOST_PLACEHOLDER}}', hook.getAttribute('data-host-placeholder') || 'xui.duckdns.org');
        });
    };
    renderSshFields();

    // ==========================================
    // Deployment Mode UI Switching
    // ==========================================
    const getSelectedMode = () => {
        const checked = document.querySelector('input[name="deploy_mode"]:checked');
        return checked ? checked.value : 'cascade';
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
        } else if (mode === 'freedom_sub') {
            title = '3. Настройки Freedom панели и Сервера подписок';
            desc = 'Учетные данные Freedom 3X-UI панели, список клиентов и параметры Сервера подписок.';
        } else if (mode === 'sub_only') {
            title = '3. Настройки Сервера подписок';
            desc = 'Параметры Сервера подписок: путь подписки, безопасность SSH и админ-доступ.';
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

        const isPanelMode = ['single', 'proxy_only', 'freedom_only', 'freedom_component', 'cascade', 'cascade_sub', 'freedom_sub'].includes(mode);
        const isDeployMode = isPanelMode || mode === 'sub_only';
        const generalSettingsCard = document.getElementById('generalSettingsCard');
        if (generalSettingsCard) {
            generalSettingsCard.classList[isDeployMode ? 'remove' : 'add']('hidden');
        }
        const generalSettingsTitle = document.getElementById('generalSettingsTitle');
        const generalSettingsBadge = document.getElementById('generalSettingsBadge');
        const sshSecurityBlock = document.getElementById('sshSecurityBlock');
        if (generalSettingsTitle && generalSettingsBadge) {
            if (mode === 'sub_only') {
                generalSettingsTitle.textContent = 'Общие параметры безопасности (SSH)';
                generalSettingsBadge.textContent = 'Security';
                generalSettingsBadge.className = 'config-card-badge badge-warning';
                if (sshSecurityBlock) {
                    sshSecurityBlock.style.borderTop = 'none';
                    sshSecurityBlock.style.marginTop = '0';
                    sshSecurityBlock.style.paddingTop = '0';
                }
            } else {
                generalSettingsTitle.textContent = 'Общие настройки (3X-UI и безопасность)';
                generalSettingsBadge.textContent = '3X-UI & Security';
                generalSettingsBadge.className = 'config-card-badge badge-primary';
                if (sshSecurityBlock) {
                    sshSecurityBlock.style.borderTop = '1px solid var(--border-color)';
                    sshSecurityBlock.style.marginTop = '15px';
                    sshSecurityBlock.style.paddingTop = '15px';
                }
            }
        }
        if (xuiVersionBlock) {
            xuiVersionBlock.classList[isPanelMode ? 'remove' : 'add']('hidden');
        }
        const happRoutingBlock = document.getElementById('happRoutingBlock');
        if (happRoutingBlock) {
            happRoutingBlock.classList[isPanelMode ? 'remove' : 'add']('hidden');
        }

        const singlePanelTitle = document.getElementById('singlePanelTitle');
        const freedomPanelTitle = document.getElementById('freedomPanelTitle');
        const proxyPanelTitle = document.getElementById('proxyPanelTitle');
        const subServerPanelTitle = document.getElementById('subServerPanelTitle');

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
            const singleTitle = singleNodeSection.querySelector('.section-title');
            if (singleTitle) singleTitle.textContent = 'Подключение к серверу 3X-UI';
            cascadeNodeSection.classList.add('hidden');
            subServerSshSection.classList.add('hidden');

            if (xuiVersionBlock) xuiVersionBlock.classList.remove('hidden');
            if (singlePanelSection) singlePanelSection.classList.remove('hidden');
            if (cascadePanelSection) cascadePanelSection.classList.add('hidden');
            if (subServerPanelSection) subServerPanelSection.classList.add('hidden');

            if (singlePanelTitle) {
                if (mode === 'freedom_component' || mode === 'freedom_only') {
                    singlePanelTitle.textContent = 'Панель и клиент Целевого сервера (Freedom Node)';
                } else if (mode === 'proxy_only') {
                    singlePanelTitle.textContent = 'Панель Прокси ноды (Proxy Node)';
                } else {
                    singlePanelTitle.textContent = 'Параметры панели 3X-UI';
                }
            }

            const foreignSubUrlGroup = document.getElementById('foreignSubUrlGroup');
            if (foreignSubUrlGroup) {
                foreignSubUrlGroup.classList[mode === 'proxy_only' ? 'remove' : 'add']('hidden');
            }
            const freedomOnlyBanner = document.querySelector('.freedom-only-banner');
            if (freedomOnlyBanner) {
                // Show banner ONLY for freedom_component (part of cascade infrastructure)
                freedomOnlyBanner.classList[mode === 'freedom_component' ? 'remove' : 'add']('hidden');
            }
            const clientXhttpInput = document.getElementById('client_xhttp_list');
            if (clientXhttpInput) {
                if (mode === 'freedom_component') {
                    clientXhttpInput.placeholder = 'local-proxy-node-client (или укажите дополнительные имена через запятую)';
                } else {
                    clientXhttpInput.placeholder = 'Опционально (например: alex, mom, phone)';
                }
            }
        } else if (mode === 'freedom_sub') {
            singleNodeSection.classList.remove('hidden');
            const singleTitle = singleNodeSection.querySelector('.section-title');
            if (singleTitle) singleTitle.textContent = '2.1 Freedom Node (Выходной сервер 3X-UI)';
            cascadeNodeSection.classList.add('hidden');
            subServerSshSection.classList.remove('hidden');
            const subTitle = subServerSshSection.querySelector('.section-title');
            if (subTitle) subTitle.textContent = '2.2 Сервер подписок (Отдельный VPS)';

            if (xuiVersionBlock) xuiVersionBlock.classList.remove('hidden');
            if (singlePanelSection) singlePanelSection.classList.remove('hidden');
            if (cascadePanelSection) cascadePanelSection.classList.add('hidden');
            if (subServerPanelSection) subServerPanelSection.classList.remove('hidden');
            if (subOnlyTargetGroup) subOnlyTargetGroup.classList.add('hidden');

            if (singlePanelTitle) singlePanelTitle.textContent = '3.1. Freedom Node (Выходной сервер 3X-UI)';
            if (subServerPanelTitle) subServerPanelTitle.textContent = '3.2. Параметры Сервера подписок';

            const foreignSubUrlGroup = document.getElementById('foreignSubUrlGroup');
            if (foreignSubUrlGroup) foreignSubUrlGroup.classList.add('hidden');
            const freedomOnlyBanner = document.querySelector('.freedom-only-banner');
            if (freedomOnlyBanner) freedomOnlyBanner.classList.add('hidden');
            const clientXhttpInput = document.getElementById('client_xhttp_list');
            if (clientXhttpInput) clientXhttpInput.placeholder = 'Опционально (например: alex, mom, phone)';
        } else if (mode === 'cascade') {
            singleNodeSection.classList.add('hidden');
            cascadeNodeSection.classList.remove('hidden');
            subServerSshSection.classList.add('hidden');

            if (xuiVersionBlock) xuiVersionBlock.classList.remove('hidden');
            if (singlePanelSection) singlePanelSection.classList.add('hidden');
            if (cascadePanelSection) cascadePanelSection.classList.remove('hidden');
            if (subServerPanelSection) subServerPanelSection.classList.add('hidden');

            if (freedomPanelTitle) freedomPanelTitle.textContent = '3.1. Панель и клиент Целевого сервера (Freedom Node)';
            if (proxyPanelTitle) proxyPanelTitle.textContent = '3.2. Панель и VPN-клиенты прокси ноды (Proxy Node)';
        } else if (mode === 'cascade_sub') {
            singleNodeSection.classList.add('hidden');
            cascadeNodeSection.classList.remove('hidden');
            subServerSshSection.classList.remove('hidden');
            const subTitle = subServerSshSection.querySelector('.section-title');
            if (subTitle) subTitle.textContent = '2.3 Сервер подписок (Отдельный VPS)';

            if (xuiVersionBlock) xuiVersionBlock.classList.remove('hidden');
            if (singlePanelSection) singlePanelSection.classList.add('hidden');
            if (cascadePanelSection) cascadePanelSection.classList.remove('hidden');
            if (subServerPanelSection) subServerPanelSection.classList.remove('hidden');
            if (subOnlyTargetGroup) subOnlyTargetGroup.classList.add('hidden');

            if (freedomPanelTitle) freedomPanelTitle.textContent = '3.1. Панель и клиент Целевого сервера (Freedom Node)';
            if (proxyPanelTitle) proxyPanelTitle.textContent = '3.2. Панель и VPN-клиенты прокси ноды (Proxy Node)';
            if (subServerPanelTitle) subServerPanelTitle.textContent = '3.3. Параметры Сервера подписок';
        } else if (mode === 'sub_only') {
            singleNodeSection.classList.add('hidden');
            cascadeNodeSection.classList.add('hidden');
            subServerSshSection.classList.remove('hidden');
            const subTitle = subServerSshSection.querySelector('.section-title');
            if (subTitle) subTitle.textContent = 'Сервер подписок (Отдельный VPS)';

            if (xuiVersionBlock) xuiVersionBlock.classList.add('hidden');
            if (singlePanelSection) singlePanelSection.classList.add('hidden');
            if (cascadePanelSection) cascadePanelSection.classList.add('hidden');
            if (subServerPanelSection) subServerPanelSection.classList.remove('hidden');
            if (subOnlyTargetGroup) subOnlyTargetGroup.classList.remove('hidden');

            if (subServerPanelTitle) subServerPanelTitle.textContent = 'Параметры Сервера подписок';
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
                    if (mode === 'update_3xui') titleEl.innerHTML = 'Сервер для обновления 3X-UI панели';
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
        if (window.__resetSSHValidation) window.__resetSSHValidation();
        updateSecretHashPreviews();

        const glowRefresher = window.__getGlowRefresher ? window.__getGlowRefresher() : null;
        if (glowRefresher) glowRefresher();
    };

    document.querySelectorAll('input[name="deploy_mode"]').forEach(radio => {
        radio.addEventListener('change', updateModeUI);
    });

    // ==========================================
    // Wizard Step Navigation
    // ==========================================
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

        const glowRefresher = window.__getGlowRefresher ? window.__getGlowRefresher() : null;
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

    const btnNext1 = document.getElementById('btnNext1');
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
                    showAlert('Для Proxy Node укажите ссылку подписки Freedom ноды в настройках панели.');
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

    // ==========================================
    // Required Password Glow & Validation
    // ==========================================
    const clearPasswordGlow = () => {
        document.querySelectorAll('.required-password-empty').forEach(input => {
            input.classList.remove('required-password-empty');
        });
    };

    const applyPasswordGlow = (fieldId) => {
        const field = document.getElementById(fieldId);
        if (field) {
            field.classList.add('required-password-empty');
        }
    };

    const getFieldValue = (fieldId) => {
        const field = document.getElementById(fieldId);
        return field ? field.value.trim() : '';
    };

    // Schema of required fields comes from the backend (GET /api/modes, Phase
    // G2). Same shape as the old hardcoded array: {group:...} rules and
    // {id, step, modes, message} fields; SSH password/key entries get their
    // `when` rebuilt from authField/authValue (e.g. vps_auth_type === 'key').
    // Loaded lazily (once) so the first submit waits for the fetch.
    let REQUIRED_FIELDS = [];
    let requiredFieldsPromise = null;
    const loadRequiredFields = () => {
        if (!requiredFieldsPromise) {
            requiredFieldsPromise = fetch('/api/modes')
                .then(res => res.json())
                .then(data => {
                    REQUIRED_FIELDS = (data.modes || []).map(rule => {
                        if (rule.kind === 'group') {
                            return {
                                group: { mode: rule.mode, fields: rule.fields, step: rule.step, modes: rule.modes, message: rule.message }
                            };
                        }
                        const entry = { id: rule.id, step: rule.step, modes: rule.modes, message: rule.message };
                        if (rule.authField && rule.authValue) {
                            entry.when = () => (document.getElementById(rule.authField)?.value || (rule.authValue === 'password' ? 'password' : '')) === rule.authValue;
                        }
                        return entry;
                    });
                    return REQUIRED_FIELDS;
                })
                .catch(() => { REQUIRED_FIELDS = []; return REQUIRED_FIELDS; });
        }
        return requiredFieldsPromise;
    };

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

    const validateRequiredPasswords = async () => {
        await loadRequiredFields();
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

    window.getSelectedMode = getSelectedMode;
    window.updateModeUI = updateModeUI;
    window.showStep = showStep;
    window.getFieldValue = getFieldValue;
    window.applyGlowForEmptyFields = applyGlowForEmptyFields;
    window.validateRequiredPasswords = validateRequiredPasswords;
});