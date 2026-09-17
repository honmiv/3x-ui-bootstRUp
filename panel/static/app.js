
document.addEventListener('DOMContentLoaded', () => {
    const terminalLogsInit = document.getElementById('terminalLogs');
    if (terminalLogsInit && terminalLogsInit.children.length === 0) {
        const initLine = document.createElement('div');
        initLine.className = 'log-line info';
        initLine.textContent = '[INIT] Готов к развертыванию. Нажмите кнопку "Запустить развертывание"...';
        terminalLogsInit.appendChild(initLine);
    }

    document.querySelectorAll('[data-rocket-slot]').forEach((slot) => {
        slot.innerHTML = rocketSvg(slot.dataset.rocketClass || '');
    });

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

    const ensureSubAdminFields = () => {
        if (document.getElementById('sub_admin_user') && document.getElementById('sub_admin_password')) return;

        const formGrid = document.querySelector('#subServerPanelSection .form-grid');
        const targetGroup = document.getElementById('subOnlyTargetGroup');
        if (!formGrid) return;

        const userGroup = document.createElement('div');
        userGroup.className = 'form-group';
        userGroup.innerHTML = `
            <label for="sub_admin_user">Логин админа Сервера подписок</label>
            <input type="text" id="sub_admin_user" placeholder="admin">
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
    window.__updateBackupName = updateBackupName;

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
            if (typeof hideDecoyHoverPreview === 'function') hideDecoyHoverPreview();
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
                    if (typeof hideDecoyHoverPreview === 'function') hideDecoyHoverPreview();
                });
                optionsContainer.appendChild(optEl);

                if (select.classList.contains('decoy-select') || select.id.endsWith('decoy_template')) {
                    optEl.addEventListener('mouseenter', () => {
                        if (typeof showDecoyHoverPreview === 'function') {
                            showDecoyHoverPreview(opt.value, optEl);
                        }
                    });
                    optEl.addEventListener('mouseleave', () => {
                        if (typeof hideDecoyHoverPreview === 'function') {
                            hideDecoyHoverPreview();
                        }
                    });
                }
            });
            optionsContainer.querySelectorAll('.custom-select-option').forEach(el => {
                el.classList.toggle('selected', el.dataset.value === select.value);
            });
        }
        if (triggerText) triggerText.textContent = select.selectedOptions[0] ? select.selectedOptions[0].textContent : select.value;
    };

    const syncVersionSelect = (select) => {
        if (!select) return;
        const wanted = select.dataset.initialVersion || select.value || latestFetchedXuiVersion;
        if (wanted && !Array.from(select.options).some(o => o.value === wanted)) {
            const opt = document.createElement('option');
            opt.value = wanted;
            opt.textContent = wanted;
            select.insertBefore(opt, select.firstChild);
        }
        if (wanted) select.value = wanted;
        refreshCustomSelect(select);
    };

    let latestFetchedXuiVersion = '';
    window.__getLatestFetchedXuiVersion = () => latestFetchedXuiVersion;
    const loadXuiVersions = async () => {
        let versions = [];
        try {
            const res = await fetch('/api/xui_versions');
            if (res.ok) {
                const data = await res.json();
                if (Array.isArray(data.versions) && data.versions.length) versions = data.versions;
            }
        } catch (e) { }
        if (versions.length === 0) return;

        if (!versions.includes('latest')) {
            versions.unshift('latest');
        } else {
            versions = ['latest', ...versions.filter(v => v !== 'latest')];
        }
        const latestConcrete = versions.find(v => v !== 'latest') || 'latest';
        latestFetchedXuiVersion = latestConcrete;

        ['xui_version', 'update_xui_version'].forEach(id => {
            const select = document.getElementById(id);
            if (!select) return;
            const initVal = select.dataset.initialVersion;
            const currentVal = select.value;
            let wanted = latestConcrete;
            if (initVal) {
                wanted = initVal;
            } else if (currentVal) {
                wanted = currentVal;
            }
            select.innerHTML = '';
            const list = (wanted && !versions.includes(wanted)) ? [wanted].concat(versions) : versions;
            list.forEach(v => {
                const opt = document.createElement('option');
                opt.value = v;
                opt.textContent = v;
                select.appendChild(opt);
            });
            select.value = wanted;
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

    let availableDecoys = [];
    let decoyPopoverEl = null;

    const getOrCreateDecoyPopover = () => {
        if (!decoyPopoverEl) {
            decoyPopoverEl = document.createElement('div');
            decoyPopoverEl.className = 'decoy-hover-popover';
            decoyPopoverEl.innerHTML = `
                <div class="decoy-hover-img-wrap">
                    <img class="decoy-hover-img" src="" alt="Decoy Preview" style="display:none;" />
                    <div class="decoy-hover-placeholder" style="display:flex; flex-direction:column; align-items:center; justify-content:center; gap:6px; color:var(--text-secondary); text-align:center; padding:12px;">
                        <svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><line x1="3" y1="9" x2="21" y2="9"/><line x1="9" y1="21" x2="9" y2="9"/></svg>
                        <span style="font-size:0.75rem;">Заглушка сайта</span>
                    </div>
                </div>
                <div class="decoy-hover-info">
                    <div class="decoy-hover-title-row">
                        <span class="decoy-hover-title"></span>
                        <span class="decoy-hover-badge"></span>
                    </div>
                    <div class="decoy-hover-desc"></div>
                </div>
            `;
            document.body.appendChild(decoyPopoverEl);
        }
        return decoyPopoverEl;
    };

    let activePreviewRequestId = 0;

    const setPlaceholderFor = (item) => {
        const popover = getOrCreateDecoyPopover();
        const placeholder = popover.querySelector('.decoy-hover-placeholder');
        if (!placeholder || !item) return;

        const badge = item.badge || '';
        let iconSvg = '';
        let subtitle = item.badge ? `${item.badge} • Шаблон` : 'Статический сайт';

        if (item.id === 'builtin') {
            iconSvg = `<svg xmlns="http://www.w3.org/2000/svg" width="38" height="38" viewBox="0 0 24 24" fill="none" stroke="#60a5fa" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>`;
            subtitle = 'Встроенная страница документации';
        } else if (badge === 'Игра') {
            iconSvg = `<svg xmlns="http://www.w3.org/2000/svg" width="38" height="38" viewBox="0 0 24 24" fill="none" stroke="#a78bfa" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="6" width="20" height="12" rx="2"/><path d="M6 12h4"/><path d="M8 10v4"/><circle cx="15" cy="11" r="1"/><circle cx="18" cy="13" r="1"/></svg>`;
            subtitle = 'HTML5 интерактивная игра';
        } else if (badge === 'Кафе') {
            iconSvg = `<svg xmlns="http://www.w3.org/2000/svg" width="38" height="38" viewBox="0 0 24 24" fill="none" stroke="#f59e0b" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 8h1a4 4 0 0 1 0 8h-1"/><path d="M2 8h16v9a4 4 0 0 1-4 4H6a4 4 0 0 1-4-4V8z"/><line x1="6" y1="1" x2="6" y2="4"/><line x1="10" y1="1" x2="10" y2="4"/><line x1="14" y1="1" x2="14" y2="4"/></svg>`;
            subtitle = 'Сайт кафе и ресторанов';
        } else if (badge === 'Магазин') {
            iconSvg = `<svg xmlns="http://www.w3.org/2000/svg" width="38" height="38" viewBox="0 0 24 24" fill="none" stroke="#10b981" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 2L3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4z"/><line x1="3" y1="6" x2="21" y2="6"/><path d="M16 10a4 4 0 0 1-8 0"/></svg>`;
            subtitle = 'E-Commerce онлайн-магазин';
        } else if (badge === 'App') {
            iconSvg = `<svg xmlns="http://www.w3.org/2000/svg" width="38" height="38" viewBox="0 0 24 24" fill="none" stroke="#38bdf8" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="5" y="2" width="14" height="20" rx="2" ry="2"/><line x1="12" y1="18" x2="12.01" y2="18"/></svg>`;
            subtitle = 'Лендинг мобильного приложения';
        } else {
            iconSvg = `<svg xmlns="http://www.w3.org/2000/svg" width="38" height="38" viewBox="0 0 24 24" fill="none" stroke="#60a5fa" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="3" width="20" height="14" rx="2" ry="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>`;
        }

        placeholder.innerHTML = `
            ${iconSvg}
            <span style="font-size:0.8rem; color:var(--text-primary); font-weight:600; text-align:center; margin-top:2px;">${item.name || ''}</span>
            <span style="font-size:0.7rem; color:var(--text-secondary);">${subtitle}</span>
        `;
    };

    const showDecoyHoverPreview = (decoyId, targetElement) => {
        const item = availableDecoys.find(d => d.id === decoyId);
        if (!item) return;
        const popover = getOrCreateDecoyPopover();
        const img = popover.querySelector('.decoy-hover-img');
        const placeholder = popover.querySelector('.decoy-hover-placeholder');
        const title = popover.querySelector('.decoy-hover-title');
        const badge = popover.querySelector('.decoy-hover-badge');
        const desc = popover.querySelector('.decoy-hover-desc');

        title.textContent = item.name || decoyId;
        badge.textContent = item.badge || (item.type === 'github' ? 'GitHub' : 'Шаблон');
        desc.textContent = item.description || '';

        setPlaceholderFor(item);
        placeholder.style.display = 'flex';
        img.style.display = 'none';

        const previewImgUrl = item.preview_image;
        if (previewImgUrl || item.repo) {
            const reqId = ++activePreviewRequestId;
            const primaryUrl = previewImgUrl || (item.repo ? `https://opengraph.githubassets.com/1/${item.repo}` : '');
            const tempImg = new Image();
            tempImg.onload = () => {
                if (reqId !== activePreviewRequestId) return;
                img.src = tempImg.src;
                img.style.display = 'block';
                img.style.opacity = '1';
                placeholder.style.display = 'none';
            };
            tempImg.onerror = () => {
                if (reqId !== activePreviewRequestId) return;
                const ogFallback = item.repo ? `https://opengraph.githubassets.com/1/${item.repo}` : '';
                if (ogFallback && tempImg.src !== ogFallback) {
                    tempImg.src = ogFallback;
                } else {
                    img.style.display = 'none';
                    placeholder.style.display = 'flex';
                }
            };
            tempImg.src = primaryUrl;
        } else {
            img.style.display = 'none';
            placeholder.style.display = 'flex';
        }

        const rect = targetElement.getBoundingClientRect();
        const popoverWidth = 320;
        const popoverHeight = 240;

        let left = rect.right + 12;
        let top = rect.top - 20;

        if (left + popoverWidth > window.innerWidth - 10) {
            left = rect.left - popoverWidth - 12;
        }
        if (left < 10) {
            left = Math.max(10, (window.innerWidth - popoverWidth) / 2);
        }

        if (top + popoverHeight > window.innerHeight - 10) {
            top = window.innerHeight - popoverHeight - 10;
        }
        if (top < 10) top = 10;

        popover.style.left = `${left}px`;
        popover.style.top = `${top}px`;
        popover.classList.add('visible');
    };

    const hideDecoyHoverPreview = () => {
        if (decoyPopoverEl) {
            decoyPopoverEl.classList.remove('visible');
        }
    };
    const updateDecoyInfo = (targetSelectId) => {
        const selectIds = targetSelectId ? [targetSelectId] : ['decoy_template', 'freedom_decoy_template', 'proxy_decoy_template', 'sub_decoy_template', 'update_decoy_template', 'update_sub_decoy_template'];
        selectIds.forEach(id => {
            const select = document.getElementById(id);
            if (!select) return;
            const parentBlock = select.closest('.form-group') || select.parentElement;
            const descEl = parentBlock ? parentBlock.querySelector('.decoy-desc-text') : document.getElementById(`${id.replace('_template', '')}_decoyDescText`);
            const badgeEl = parentBlock ? parentBlock.querySelector('.decoy-cache-badge') : document.getElementById(`${id.replace('_template', '')}_decoyCacheStatus`);

            const selId = select.value;
            const item = availableDecoys.find(d => d.id === selId);

            if (descEl && item) {
                descEl.textContent = item.description || 'Статический сайт-заглушка для портов 80 и 443 (fallback).';
            }

            if (badgeEl) {
                if (selId === 'builtin') {
                    badgeEl.textContent = 'Встроено';
                    badgeEl.style.background = 'rgba(59, 130, 246, 0.15)';
                    badgeEl.style.color = 'var(--accent-color, #3b82f6)';
                    badgeEl.style.borderColor = 'rgba(59, 130, 246, 0.3)';
                } else if (item && item.is_cached) {
                    badgeEl.textContent = 'В кэше';
                    badgeEl.style.background = 'rgba(16, 185, 129, 0.15)';
                    badgeEl.style.color = 'var(--success-color, #10b981)';
                    badgeEl.style.borderColor = 'rgba(16, 185, 129, 0.3)';
                } else {
                    badgeEl.textContent = 'Не скачано';
                    badgeEl.style.background = 'rgba(234, 179, 8, 0.15)';
                    badgeEl.style.color = 'var(--warning-color, #eab308)';
                    badgeEl.style.borderColor = 'rgba(234, 179, 8, 0.3)';
                }
            }
        });
    };

    const loadDecoyTemplates = async () => {
        try {
            const res = await fetch('/api/decoys');
            if (res.ok) {
                const data = await res.json();
                if (Array.isArray(data.decoys) && data.decoys.length) {
                    availableDecoys = data.decoys;
                }
            }
        } catch (e) { }

        const decoySelects = document.querySelectorAll('select.decoy-select');
        decoySelects.forEach(select => {
            const isOptional = select.id === 'update_decoy_template' || select.id === 'update_sub_decoy_template';
            const initialVal = select.dataset.initialVal || select.value || (isOptional ? '' : 'builtin');
            select.innerHTML = '';
            if (isOptional) {
                const emptyOpt = document.createElement('option');
                emptyOpt.value = '';
                emptyOpt.textContent = '— Не обновлять заглушку —';
                select.appendChild(emptyOpt);
            }
            availableDecoys.forEach(d => {
                const opt = document.createElement('option');
                opt.value = d.id;
                opt.textContent = d.name;
                select.appendChild(opt);
            });
            select.value = initialVal;
            refreshCustomSelect(select);
        });
        updateDecoyInfo();
    };

    loadDecoyTemplates();

    document.addEventListener('change', (e) => {
        if (e.target && e.target.classList && e.target.classList.contains('decoy-select')) {
            updateDecoyInfo(e.target.id);
            saveCurrentConfig();
        }
    });

    document.addEventListener('click', async (e) => {
        const randomBtn = e.target.closest('.btn-random-decoy');
        if (randomBtn) {
            const targetId = randomBtn.dataset.target || 'decoy_template';
            const select = document.getElementById(targetId);
            if (!select || !availableDecoys.length) return;
            const currentVal = select.value;
            const candidates = availableDecoys.filter(d => d.id !== currentVal);
            const pool = candidates.length > 0 ? candidates : availableDecoys;
            const chosen = pool[Math.floor(Math.random() * pool.length)];

            select.value = chosen.id;
            refreshCustomSelect(select);
            updateDecoyInfo(targetId);
            saveCurrentConfig();
            showToast(`🎲 Выбрана заглушка: ${chosen.name}`, 'info', 2500);
            return;
        }

        const previewBtn = e.target.closest('.btn-preview-decoy');
        if (previewBtn) {
            const targetId = previewBtn.dataset.target || 'decoy_template';
            const select = document.getElementById(targetId);
            if (!select) return;
            const decoyId = select.value;

            const item = availableDecoys.find(d => d.id === decoyId);
            if (decoyId !== 'builtin' && (!item || !item.is_cached)) {
                showToast('Загрузка шаблона в локальный кэш...', 'info', 3000);
                try {
                    const dlRes = await fetch('/api/decoys/download', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ id: decoyId })
                    });
                    const dlData = await dlRes.json();
                    if (!dlData.ok) {
                        showToast(`Ошибка загрузки: ${dlData.error || 'не удалось скачать'}`, 'error');
                        return;
                    }
                    if (item) item.is_cached = true;
                    updateDecoyInfo(targetId);
                } catch (err) {
                    showToast(`Ошибка скачивания: ${err.message}`, 'error');
                    return;
                }
            }

            window.open(`/api/decoys/preview/${encodeURIComponent(decoyId)}/index.html`, '_blank');
        }
    });

    const resetSSHValidation = () => {
        btnNext1.classList.add('hidden');
        testResult.className = 'test-result';
        testResult.innerHTML = '';
        saveCurrentConfig();
    };
    window.__resetSSHValidation = resetSSHValidation;

    let saveTimeout = null;
    const saveCurrentConfig = () => {
        if (saveTimeout) clearTimeout(saveTimeout);
        saveTimeout = setTimeout(async () => {
            const mode = window.getSelectedMode();
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
                freedom_xui_username: window.getFieldValue('freedom_xui_username'),
                freedom_sub_secret: window.getFieldValue('freedom_sub_secret'),
                freedom_client_name: document.getElementById('freedom_client_name').value.trim(),

                proxy_host: document.getElementById('proxy_host').value.trim(),
                proxy_port: parseInt(document.getElementById('proxy_port').value) || 22,
                proxy_user: document.getElementById('proxy_user').value.trim() || 'root',
                proxy_auth_type: document.getElementById('proxy_auth_type').value,
                proxy_xui_username: window.getFieldValue('proxy_xui_username'),
                proxy_sub_secret: window.getFieldValue('proxy_sub_secret'),
                proxy_client_tcp_list: document.getElementById('proxy_client_tcp_list').value.trim(),
                proxy_client_xhttp_list: document.getElementById('proxy_client_xhttp_list').value.trim(),
                foreign_sub_url: document.getElementById('foreign_sub_url') ? document.getElementById('foreign_sub_url').value.trim() : '',

                sub_vps_host: document.getElementById('sub_vps_host').value.trim(),
                sub_vps_port: parseInt(document.getElementById('sub_vps_port').value) || 22,
                sub_vps_user: document.getElementById('sub_vps_user').value.trim() || 'root',
                sub_auth_type: document.getElementById('sub_auth_type').value,
                sub_domain: document.getElementById('sub_domain') ? document.getElementById('sub_domain').value.trim() : document.getElementById('sub_vps_host').value.trim(),
                sub_secret_path: window.getFieldValue('sub_secret_path'),
                sub_russian_url: document.getElementById('sub_russian_url').value.trim(),
                sub_foreign_url: document.getElementById('sub_foreign_url').value.trim(),
                sub_proxy_clients: document.getElementById('sub_proxy_clients').value.trim(),
                sub_freedom_clients: document.getElementById('sub_freedom_clients').value.trim(),
                sub_admin_user: window.getFieldValue('sub_admin_user'),
                rollback_sub_backup_file: document.getElementById('rollback_sub_backup_file') ? document.getElementById('rollback_sub_backup_file').value : '',

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
                recovery_xui_username: window.getFieldValue('recovery_xui_username'),

                update_vps_host: document.getElementById('update_vps_host') ? document.getElementById('update_vps_host').value.trim() : '',
                update_vps_port: document.getElementById('update_vps_port') ? parseInt(document.getElementById('update_vps_port').value) || 22 : 22,
                update_vps_user: document.getElementById('update_vps_user') ? document.getElementById('update_vps_user').value.trim() || 'root' : 'root',
                update_auth_type: document.getElementById('update_auth_type') ? document.getElementById('update_auth_type').value : 'password',
                update_xui_version: document.getElementById('update_xui_version') ? document.getElementById('update_xui_version').value.trim() || latestFetchedXuiVersion : latestFetchedXuiVersion,

                xui_username: window.getFieldValue('xui_username'),
                sub_secret: window.getFieldValue('sub_secret'),
                xui_version: document.getElementById('xui_version') ? document.getElementById('xui_version').value.trim() || latestFetchedXuiVersion : latestFetchedXuiVersion,
                decoy_template: document.getElementById('decoy_template') ? document.getElementById('decoy_template').value : 'builtin',
                freedom_decoy_template: document.getElementById('freedom_decoy_template') ? document.getElementById('freedom_decoy_template').value : 'builtin',
                proxy_decoy_template: document.getElementById('proxy_decoy_template') ? document.getElementById('proxy_decoy_template').value : 'builtin',
                sub_decoy_template: document.getElementById('sub_decoy_template') ? document.getElementById('sub_decoy_template').value : 'builtin',
                update_decoy_template: document.getElementById('update_decoy_template') ? document.getElementById('update_decoy_template').value : '',
                update_sub_decoy_template: document.getElementById('update_sub_decoy_template') ? document.getElementById('update_sub_decoy_template').value : '',
                opt_change_ssh_port: document.getElementById('opt_change_ssh_port') ? document.getElementById('opt_change_ssh_port').checked : false,
                custom_ssh_port: document.getElementById('custom_ssh_port') ? document.getElementById('custom_ssh_port').value : '22222',
                opt_update_change_ssh_port: document.getElementById('opt_update_change_ssh_port') ? document.getElementById('opt_update_change_ssh_port').checked : false,
                custom_update_ssh_port: document.getElementById('custom_update_ssh_port') ? document.getElementById('custom_update_ssh_port').value : '22222',
                opt_update_sub_change_ssh_port: document.getElementById('opt_update_sub_change_ssh_port') ? document.getElementById('opt_update_sub_change_ssh_port').checked : false,
                custom_update_sub_ssh_port: document.getElementById('custom_update_sub_ssh_port') ? document.getElementById('custom_update_sub_ssh_port').value : '22222',
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
    window.__saveCurrentConfig = saveCurrentConfig;

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
                ['decoy_template', 'freedom_decoy_template', 'proxy_decoy_template', 'sub_decoy_template', 'update_decoy_template', 'update_sub_decoy_template'].forEach(id => {
                    if (has(id) && document.getElementById(id)) {
                        const sel = document.getElementById(id);
                        sel.dataset.initialVal = cfg[id];
                        sel.value = cfg[id];
                        refreshCustomSelect(sel);
                    }
                });
                if (typeof updateDecoyInfo === 'function') updateDecoyInfo();
                if (has('client_tcp_list')) setValue('client_tcp_list', cfg.client_tcp_list);
                if (has('client_xhttp_list')) setValue('client_xhttp_list', cfg.client_xhttp_list);
                if (has('foreign_sub_url')) setValue('foreign_sub_url', cfg.foreign_sub_url);
                if (has('opt_change_ssh_port') && document.getElementById('opt_change_ssh_port')) {
                    const isChecked = !!cfg.opt_change_ssh_port;
                    document.getElementById('opt_change_ssh_port').checked = isChecked;
                    const row = document.getElementById('sshPortConfigRow');
                    if (row) row.classList[isChecked ? 'remove' : 'add']('hidden');
                }
                if (has('custom_ssh_port') && document.getElementById('custom_ssh_port')) {
                    document.getElementById('custom_ssh_port').value = cfg.custom_ssh_port;
                }
                if (has('opt_update_change_ssh_port') && document.getElementById('opt_update_change_ssh_port')) {
                    const isChecked = !!cfg.opt_update_change_ssh_port;
                    document.getElementById('opt_update_change_ssh_port').checked = isChecked;
                    const row = document.getElementById('sshPortConfigRowUpdate');
                    if (row) row.classList[isChecked ? 'remove' : 'add']('hidden');
                }
                if (has('custom_update_ssh_port') && document.getElementById('custom_update_ssh_port')) {
                    document.getElementById('custom_update_ssh_port').value = cfg.custom_update_ssh_port;
                }
                if (has('opt_update_sub_change_ssh_port') && document.getElementById('opt_update_sub_change_ssh_port')) {
                    const isChecked = !!cfg.opt_update_sub_change_ssh_port;
                    document.getElementById('opt_update_sub_change_ssh_port').checked = isChecked;
                    const row = document.getElementById('sshPortConfigRowUpdateSub');
                    if (row) row.classList[isChecked ? 'remove' : 'add']('hidden');
                }
                if (has('custom_update_sub_ssh_port') && document.getElementById('custom_update_sub_ssh_port')) {
                    document.getElementById('custom_update_sub_ssh_port').value = cfg.custom_update_sub_ssh_port;
                }

                const subBkNameEl = document.getElementById('sub_backup_name');
                if (subBkNameEl && !subBkNameEl.value.trim()) updateSubBackupName();

                window.updateModeUI();
                updateSecretHashPreviews();
            } else {
                if (!document.getElementById('sub_secret').value) document.getElementById('sub_secret').value = '';
                if (document.getElementById('freedom_sub_secret') && !document.getElementById('freedom_sub_secret').value) document.getElementById('freedom_sub_secret').value = '';
                if (document.getElementById('proxy_sub_secret') && !document.getElementById('proxy_sub_secret').value) document.getElementById('proxy_sub_secret').value = '';
                window.updateModeUI();
                updateSecretHashPreviews();
            }
        } catch (e) { }
    };

    loadBackupConfig();

    const optChangeSshPort = document.getElementById('opt_change_ssh_port');
    const sshPortConfigRow = document.getElementById('sshPortConfigRow');
    const customSshPort = document.getElementById('custom_ssh_port');
    if (optChangeSshPort) {
        optChangeSshPort.addEventListener('change', () => {
            if (sshPortConfigRow) {
                sshPortConfigRow.classList[optChangeSshPort.checked ? 'remove' : 'add']('hidden');
            }
            saveCurrentConfig();
        });
    }
    if (customSshPort) {
        customSshPort.addEventListener('input', saveCurrentConfig);
        customSshPort.addEventListener('change', saveCurrentConfig);
    }
    [
        { cb: 'opt_change_ssh_port', row: 'sshPortConfigRow', inp: 'custom_ssh_port' },
        { cb: 'opt_update_change_ssh_port', row: 'sshPortConfigRowUpdate', inp: 'custom_update_ssh_port' },
        { cb: 'opt_update_sub_change_ssh_port', row: 'sshPortConfigRowUpdateSub', inp: 'custom_update_sub_ssh_port' }
    ].forEach(({ cb: cbId, row: rowId, inp: inpId }) => {
        const cb = document.getElementById(cbId);
        const row = document.getElementById(rowId);
        const inp = document.getElementById(inpId);
        if (cb) {
            cb.addEventListener('change', () => {
                if (row) {
                    row.classList[cb.checked ? 'remove' : 'add']('hidden');
                }
                saveCurrentConfig();
            });
        }
        if (inp) {
            inp.addEventListener('input', saveCurrentConfig);
            inp.addEventListener('change', saveCurrentConfig);
        }
    });

    ['sub_secret', 'freedom_sub_secret', 'proxy_sub_secret', 'sub_secret_path'].forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            el.addEventListener('input', updateSecretHashPreviews);
            el.addEventListener('change', updateSecretHashPreviews);
            el.addEventListener('keyup', updateSecretHashPreviews);
            el.addEventListener('paste', () => setTimeout(updateSecretHashPreviews, 10));
        }
    });
    updateSecretHashPreviews();

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

    if (btnTestSSH) {
        btnTestSSH.addEventListener('click', async () => {
            const mode = window.getSelectedMode();
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
                        testResult.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon text-danger"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg> Укажите домен / IP адрес сервера';
                        return;
                    }

                    testResult.className = 'test-result info';
                    testResult.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon spin"><line x1="12" y1="2" x2="12" y2="6"/><line x1="12" y1="18" x2="12" y2="22"/><line x1="4.93" y1="4.93" x2="7.76" y2="7.76"/><line x1="16.24" y1="16.24" x2="19.07" y2="19.07"/><line x1="2" y1="12" x2="6" y2="12"/><line x1="18" y1="12" x2="22" y2="12"/><line x1="4.93" y1="19.07" x2="7.76" y2="16.24"/><line x1="16.24" y1="7.76" x2="19.07" y2="4.93"/></svg> Проверяем подключение к ${host}:${port}...`;
                    const resp = await fetch('/api/ssh/test', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ vps_host: host, vps_port: port, vps_user: user, vps_password: password, vps_key: key_data })
                    });
                    const res = await resp.json();
                    if (res.ok) {
                        testResult.className = 'test-result success';
                        testResult.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon text-success"><path d="M20 6L9 17l-5-5"/></svg> Успешное подключение к ${host}:${port}`;
                        btnNext1.classList.remove('hidden');
                    } else {
                        testResult.className = 'test-result error';
                        testResult.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon text-danger"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg> ${res.message}`;
                    }
                } else if (mode === 'sub_only') {
                    const host = document.getElementById('sub_vps_host').value.trim();
                    const port = parseInt(document.getElementById('sub_vps_port').value) || 22;
                    const user = document.getElementById('sub_vps_user').value.trim() || 'root';
                    const password = document.getElementById('sub_vps_password').value;
                    const key_data = document.getElementById('sub_vps_key').value;

                    if (!host) {
                        testResult.className = 'test-result error';
                        testResult.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon text-danger"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg> Укажите домен Сервера подписок';
                        return;
                    }

                    testResult.className = 'test-result info';
                    testResult.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon spin"><line x1="12" y1="2" x2="12" y2="6"/><line x1="12" y1="18" x2="12" y2="22"/><line x1="4.93" y1="4.93" x2="7.76" y2="7.76"/><line x1="16.24" y1="16.24" x2="19.07" y2="19.07"/><line x1="2" y1="12" x2="6" y2="12"/><line x1="18" y1="12" x2="22" y2="12"/><line x1="4.93" y1="19.07" x2="7.76" y2="16.24"/><line x1="16.24" y1="7.76" x2="19.07" y2="4.93"/></svg> Проверяем подключение к Серверу подписок (${host}:${port})...`;
                    const resp = await fetch('/api/ssh/test', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ vps_host: host, vps_port: port, vps_user: user, vps_password: password, vps_key: key_data })
                    });
                    const res = await resp.json();
                    if (res.ok) {
                        testResult.className = 'test-result success';
                        testResult.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon text-success"><path d="M20 6L9 17l-5-5"/></svg> Успешное подключение к Серверу подписок (${host}:${port})`;
                        btnNext1.classList.remove('hidden');
                    } else {
                        testResult.className = 'test-result error';
                        testResult.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon text-danger"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg> ${res.message}`;
                    }
                } else if (mode === 'backup') {
                    const host = document.getElementById('backup_vps_host').value.trim();
                    const port = parseInt(document.getElementById('backup_vps_port').value) || 22;
                    const user = document.getElementById('backup_vps_user').value.trim() || 'root';
                    const password = document.getElementById('backup_vps_password').value;
                    const key_data = document.getElementById('backup_vps_key').value;

                    if (!host) {
                        testResult.className = 'test-result error';
                        testResult.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon text-danger"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg> Укажите домен / IP адрес сервера для бэкапа';
                        return;
                    }

                    testResult.className = 'test-result info';
                    testResult.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon spin"><line x1="12" y1="2" x2="12" y2="6"/><line x1="12" y1="18" x2="12" y2="22"/><line x1="4.93" y1="4.93" x2="7.76" y2="7.76"/><line x1="16.24" y1="16.24" x2="19.07" y2="19.07"/><line x1="2" y1="12" x2="6" y2="12"/><line x1="18" y1="12" x2="22" y2="12"/><line x1="4.93" y1="19.07" x2="7.76" y2="16.24"/><line x1="16.24" y1="7.76" x2="19.07" y2="4.93"/></svg> Проверяем подключение к серверу бэкапа (${host}:${port})...`;
                    const resp = await fetch('/api/ssh/test', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ backup_vps_host: host, backup_vps_port: port, backup_vps_user: user, backup_vps_password: password, backup_vps_key: key_data })
                    });
                    const res = await resp.json();
                    if (res.ok) {
                        testResult.className = 'test-result success';
                        testResult.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon text-success"><path d="M20 6L9 17l-5-5"/></svg> Успешное подключение к серверу (${host}:${port})`;
                        btnNext1.classList.remove('hidden');
                    } else {
                        testResult.className = 'test-result error';
                        testResult.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon text-danger"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg> ${res.message}`;
                    }
                } else if (mode === 'update_3xui' || mode === 'restart_panel' || mode === 'restart_server') {
                    const host = document.getElementById('update_vps_host').value.trim();
                    const port = parseInt(document.getElementById('update_vps_port').value) || 22;
                    const user = document.getElementById('update_vps_user').value.trim() || 'root';
                    const password = document.getElementById('update_vps_password').value;
                    const key_data = document.getElementById('update_vps_key').value;

                    if (!host) {
                        testResult.className = 'test-result error';
                        testResult.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon text-danger"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg> Укажите домен / IP адрес сервера';
                        return;
                    }

                    testResult.className = 'test-result info';
                    testResult.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon spin"><line x1="12" y1="2" x2="12" y2="6"/><line x1="12" y1="18" x2="12" y2="22"/><line x1="4.93" y1="4.93" x2="7.76" y2="7.76"/><line x1="16.24" y1="16.24" x2="19.07" y2="19.07"/><line x1="2" y1="12" x2="6" y2="12"/><line x1="18" y1="12" x2="22" y2="12"/><line x1="4.93" y1="19.07" x2="7.76" y2="16.24"/><line x1="16.24" y1="7.76" x2="19.07" y2="4.93"/></svg> Проверяем подключение к серверу (${host}:${port})...`;
                    const resp = await fetch('/api/ssh/test', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ update_vps_host: host, update_vps_port: port, update_vps_user: user, update_vps_password: password, update_vps_key: key_data })
                    });
                    const res = await resp.json();
                    if (res.ok) {
                        testResult.className = 'test-result success';
                        testResult.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon text-success"><path d="M20 6L9 17l-5-5"/></svg> Успешное подключение к серверу (${host}:${port})`;
                        btnNext1.classList.remove('hidden');
                    } else {
                        testResult.className = 'test-result error';
                        testResult.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon text-danger"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg> ${res.message}`;
                    }
                } else if (mode === 'restart_sub' || mode === 'update_sub' || mode === 'backup_sub' || mode === 'rollback_sub') {
                    const host = document.getElementById('sub_vps_host').value.trim();
                    const port = parseInt(document.getElementById('sub_vps_port').value) || 22;
                    const user = document.getElementById('sub_vps_user').value.trim() || 'root';
                    const password = document.getElementById('sub_vps_password').value;
                    const key_data = document.getElementById('sub_vps_key').value;

                    if (!host) {
                        testResult.className = 'test-result error';
                        testResult.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon text-danger"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg> Укажите домен Сервера подписок';
                        return;
                    }
                    if (mode === 'rollback_sub') {
                        const backup_file = document.getElementById('rollback_sub_backup_file') ? document.getElementById('rollback_sub_backup_file').value : '';
                        if (!backup_file) {
                            testResult.className = 'test-result error';
                            testResult.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon text-danger"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg> Выберите архив бэкапа из списка';
                            return;
                        }
                    }

                    testResult.className = 'test-result info';
                    testResult.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon spin"><line x1="12" y1="2" x2="12" y2="6"/><line x1="12" y1="18" x2="12" y2="22"/><line x1="4.93" y1="4.93" x2="7.76" y2="7.76"/><line x1="16.24" y1="16.24" x2="19.07" y2="19.07"/><line x1="2" y1="12" x2="6" y2="12"/><line x1="18" y1="12" x2="22" y2="12"/><line x1="4.93" y1="19.07" x2="7.76" y2="16.24"/><line x1="16.24" y1="7.76" x2="19.07" y2="4.93"/></svg> Проверяем подключение к Серверу подписок (${host}:${port})...`;
                    const resp = await fetch('/api/ssh/test', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ sub_vps_host: host, sub_vps_port: port, sub_vps_user: user, sub_vps_password: password, sub_vps_key: key_data })
                    });
                    const res = await resp.json();
                    if (res.ok) {
                        testResult.className = 'test-result success';
                        testResult.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon text-success"><path d="M20 6L9 17l-5-5"/></svg> Успешное подключение к Серверу подписок (${host}:${port})`;
                        btnNext1.classList.remove('hidden');
                    } else {
                        testResult.className = 'test-result error';
                        testResult.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon text-danger"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg> ${res.message}`;
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
                        testResult.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon text-danger"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg> Укажите домен / IP адрес нового сервера';
                        return;
                    }
                    if (!backup_file) {
                        testResult.className = 'test-result error';
                        testResult.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon text-danger"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg> Выберите архив бэкапа из списка';
                        return;
                    }

                    testResult.className = 'test-result info';
                    testResult.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon spin"><line x1="12" y1="2" x2="12" y2="6"/><line x1="12" y1="18" x2="12" y2="22"/><line x1="4.93" y1="4.93" x2="7.76" y2="7.76"/><line x1="16.24" y1="16.24" x2="19.07" y2="19.07"/><line x1="2" y1="12" x2="6" y2="12"/><line x1="18" y1="12" x2="22" y2="12"/><line x1="4.93" y1="19.07" x2="7.76" y2="16.24"/><line x1="16.24" y1="7.76" x2="19.07" y2="4.93"/></svg> Проверяем подключение к целевому серверу (${host}:${port})...`;
                    const resp = await fetch('/api/ssh/test', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ recovery_vps_host: host, recovery_vps_port: port, recovery_vps_user: user, recovery_vps_password: password, recovery_vps_key: key_data })
                    });
                    const res = await resp.json();
                    if (res.ok) {
                        testResult.className = 'test-result success';
                        testResult.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon text-success"><path d="M20 6L9 17l-5-5"/></svg> Успешное подключение к целевому серверу (${host}:${port})`;
                        btnNext1.classList.remove('hidden');
                    } else {
                        testResult.className = 'test-result error';
                        testResult.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon text-danger"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg> ${res.message}`;
                    }
                } else if (mode === 'freedom_sub') {
                    const fHost = document.getElementById('vps_host').value.trim();
                    const fPort = parseInt(document.getElementById('vps_port').value) || 22;
                    const fUser = document.getElementById('vps_user').value.trim() || 'root';
                    const fPass = document.getElementById('vps_password').value;
                    const fKey = document.getElementById('vps_key').value;

                    const sHost = document.getElementById('sub_vps_host').value.trim();
                    const sPort = parseInt(document.getElementById('sub_vps_port').value) || 22;
                    const sUser = document.getElementById('sub_vps_user').value.trim() || 'root';
                    const sPass = document.getElementById('sub_vps_password').value;
                    const sKey = document.getElementById('sub_vps_key').value;

                    if (!fHost || !sHost) {
                        testResult.className = 'test-result error';
                        testResult.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon text-danger"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg> Укажите хосты для Freedom Node и Сервера подписок';
                        return;
                    }

                    testResult.className = 'test-result info';
                    testResult.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon spin"><line x1="12" y1="2" x2="12" y2="6"/><line x1="12" y1="18" x2="12" y2="22"/><line x1="4.93" y1="4.93" x2="7.76" y2="7.76"/><line x1="16.24" y1="16.24" x2="19.07" y2="19.07"/><line x1="2" y1="12" x2="6" y2="12"/><line x1="18" y1="12" x2="22" y2="12"/><line x1="4.93" y1="19.07" x2="7.76" y2="16.24"/><line x1="16.24" y1="7.76" x2="19.07" y2="4.93"/></svg> Проверяем подключение к Freedom Node (${fHost}:${fPort})...`;
                    const r1 = await fetch('/api/ssh/test', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ vps_host: fHost, vps_port: fPort, vps_user: fUser, vps_password: fPass, vps_key: fKey })
                    });
                    const res1 = await r1.json();
                    if (!res1.ok) {
                        testResult.className = 'test-result error';
                        testResult.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon text-danger"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg> Ошибка подключения к Freedom Node (${fHost}): ${res1.message}`;
                        return;
                    }

                    testResult.className = 'test-result info';
                    testResult.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon spin"><line x1="12" y1="2" x2="12" y2="6"/><line x1="12" y1="18" x2="12" y2="22"/><line x1="4.93" y1="4.93" x2="7.76" y2="7.76"/><line x1="16.24" y1="16.24" x2="19.07" y2="19.07"/><line x1="2" y1="12" x2="6" y2="12"/><line x1="18" y1="12" x2="22" y2="12"/><line x1="4.93" y1="19.07" x2="7.76" y2="16.24"/><line x1="16.24" y1="7.76" x2="19.07" y2="4.93"/></svg> Проверяем подключение к Серверу подписок (${sHost}:${sPort})...`;
                    const r2 = await fetch('/api/ssh/test', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ vps_host: sHost, vps_port: sPort, vps_user: sUser, vps_password: sPass, vps_key: sKey })
                    });
                    const res2 = await r2.json();
                    if (!res2.ok) {
                        testResult.className = 'test-result error';
                        testResult.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon text-danger"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg> Ошибка подключения к Серверу подписок (${sHost}): ${res2.message}`;
                        return;
                    }

                    testResult.className = 'test-result success';
                    testResult.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon text-success"><path d="M20 6L9 17l-5-5"/></svg> Успешная проверка Freedom Node и Сервера подписок!`;
                    btnNext1.classList.remove('hidden');
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
                        testResult.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon text-danger"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg> Укажите хосты для обоих серверов (Freedom Node и Proxy Node)';
                        return;
                    }

                    testResult.className = 'test-result info';
                    testResult.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon spin"><line x1="12" y1="2" x2="12" y2="6"/><line x1="12" y1="18" x2="12" y2="22"/><line x1="4.93" y1="4.93" x2="7.76" y2="7.76"/><line x1="16.24" y1="16.24" x2="19.07" y2="19.07"/><line x1="2" y1="12" x2="6" y2="12"/><line x1="18" y1="12" x2="22" y2="12"/><line x1="4.93" y1="19.07" x2="7.76" y2="16.24"/><line x1="16.24" y1="7.76" x2="19.07" y2="4.93"/></svg> Проверяем подключение к Freedom Node (${fHost}:${fPort})...`;
                    const r1 = await fetch('/api/ssh/test', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ vps_host: fHost, vps_port: fPort, vps_user: fUser, vps_password: fPass, vps_key: fKey })
                    });
                    const res1 = await r1.json();

                    if (!res1.ok) {
                        testResult.className = 'test-result error';
                        testResult.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon text-danger"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg> Ошибка подключения к Freedom Node (${fHost}): ${res1.message}`;
                        return;
                    }

                    testResult.className = 'test-result info';
                    testResult.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon spin"><line x1="12" y1="2" x2="12" y2="6"/><line x1="12" y1="18" x2="12" y2="22"/><line x1="4.93" y1="4.93" x2="7.76" y2="7.76"/><line x1="16.24" y1="16.24" x2="19.07" y2="19.07"/><line x1="2" y1="12" x2="6" y2="12"/><line x1="18" y1="12" x2="22" y2="12"/><line x1="4.93" y1="19.07" x2="7.76" y2="16.24"/><line x1="16.24" y1="7.76" x2="19.07" y2="4.93"/></svg> Проверяем подключение к Proxy Node (${pHost}:${pPort})...`;
                    const r2 = await fetch('/api/ssh/test', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ vps_host: pHost, vps_port: pPort, vps_user: pUser, vps_password: pPass, vps_key: pKey })
                    });
                    const res2 = await r2.json();

                    if (!res2.ok) {
                        testResult.className = 'test-result error';
                        testResult.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon text-danger"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg> Ошибка подключения к Proxy Node (${pHost}): ${res2.message}`;
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
                            testResult.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon text-danger"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg> Укажите домен Сервера подписок';
                            return;
                        }
                        testResult.className = 'test-result info';
                        testResult.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon spin"><line x1="12" y1="2" x2="12" y2="6"/><line x1="12" y1="18" x2="12" y2="22"/><line x1="4.93" y1="4.93" x2="7.76" y2="7.76"/><line x1="16.24" y1="16.24" x2="19.07" y2="19.07"/><line x1="2" y1="12" x2="6" y2="12"/><line x1="18" y1="12" x2="22" y2="12"/><line x1="4.93" y1="19.07" x2="7.76" y2="16.24"/><line x1="16.24" y1="7.76" x2="19.07" y2="4.93"/></svg> Проверяем подключение к Серверу подписок (${sHost}:${sPort})...`;
                        const r3 = await fetch('/api/ssh/test', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ vps_host: sHost, vps_port: sPort, vps_user: sUser, vps_password: sPass, vps_key: sKey })
                        });
                        const res3 = await r3.json();
                        if (!res3.ok) {
                            testResult.className = 'test-result error';
                            testResult.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon text-danger"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg> Ошибка подключения к Серверу подписок (${sHost}): ${res3.message}`;
                            return;
                        }
                    }

                    testResult.className = 'test-result success';
                    testResult.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon text-success"><path d="M20 6L9 17l-5-5"/></svg> Успешная проверка всех выбранных серверов!`;
                    btnNext1.classList.remove('hidden');
                }
            } catch (err) {
                testResult.className = 'test-result error';
                testResult.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon text-danger"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg> Ошибка запроса: ${err.message}`;
            } finally {
                btnTestSSH.disabled = false;
                btnTestSSH.innerHTML = origBtnHtml;
            }
        });
    }

    // ==========================================
    // Password Field Validation & Yellow Glow
    // ==========================================

    let glowRefresher = null;
    window.__getGlowRefresher = () => glowRefresher;

    document.addEventListener('input', () => {
        if (glowRefresher) glowRefresher();
        updateSecretHashPreviews();
    });

    glowRefresher = window.applyGlowForEmptyFields;
    glowRefresher();

const btnUpdateSources = document.getElementById('btnUpdateSources');
    if (btnUpdateSources) {
        btnUpdateSources.addEventListener('click', async () => {
            if (!await showConfirm('Обновить файлы деплоера до последней версии с GitHub master?\n\nВаши сохраненные бэкапы (./backups_panel/) и конфигурация (setup_backup.yml) будут сохранены, а сервер перезапустится.', 'Обновление деплоера', { confirmText: 'Обновить', icon: '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon"><path d="M21 2v6h-6"/><path d="M3 12a9 9 0 0 1 15-6.7L21 8"/><path d="M3 22v-6h6"/><path d="M21 12a9 9 0 0 1-15 6.7L3 16"/></svg>' })) {
                return;
            }

            btnUpdateSources.disabled = true;
            btnUpdateSources.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon spin"><line x1="12" y1="2" x2="12" y2="6"/><line x1="12" y1="18" x2="12" y2="22"/><line x1="4.93" y1="4.93" x2="7.76" y2="7.76"/><line x1="16.24" y1="16.24" x2="19.07" y2="19.07"/><line x1="2" y1="12" x2="6" y2="12"/><line x1="18" y1="12" x2="22" y2="12"/><line x1="4.93" y1="19.07" x2="7.76" y2="16.24"/><line x1="16.24" y1="7.76" x2="19.07" y2="4.93"/></svg> Обновление...';

            try {
                const res = await fetch('/api/update_sources', { method: 'POST' });
                const data = await res.json();
                if (!data.ok) {
                    showToast('Ошибка запуска обновления: ' + (data.message || 'Неизвестная ошибка'), 'error');
                    btnUpdateSources.disabled = false;
                    btnUpdateSources.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon"><path d="M21 2v6h-6"/><path d="M3 12a9 9 0 0 1 15-6.7L21 8"/><path d="M3 22v-6h6"/><path d="M21 12a9 9 0 0 1-15 6.7L3 16"/></svg> Обновить скрипт';
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

    let latestUpdateInfo = null;


    const setupBannerActionDelegation = (containerId) => {
        const container = document.getElementById(containerId);
        if (!container) return;
        container.addEventListener('click', async (e) => {
            const btn = e.target.closest('[data-action]');
            if (!btn) return;
            const action = btn.getAttribute('data-action');
            if (action === 'dismiss') {
                container.classList.add('hidden');
            } else if (action === 'update') {
                const btnUpdateSources = document.getElementById('btnUpdateSources');
                if (btnUpdateSources) btnUpdateSources.click();
            } else if (action === 'changelog') {
                if (latestUpdateInfo && latestUpdateInfo.changelog !== undefined) {
                    showChangelogModal(latestUpdateInfo.changelog || 'Нет новых записей в change.log относительно текущей версии.');
                    return;
                }
                try {
                    const res = await fetch('/api/update_check', { cache: 'no-store' });
                    if (res.ok) {
                        const data = await res.json();
                        latestUpdateInfo = data;
                        showChangelogModal((data && data.changelog) ? data.changelog : 'Нет новых записей в change.log относительно текущей версии.');
                    } else {
                        showChangelogModal('Не удалось загрузить change.log.');
                    }
                } catch (err) {
                    showChangelogModal('Ошибка при получении change.log: ' + err.message);
                }
            }
        });
    };

    setupBannerActionDelegation('updateBanner');
    setupBannerActionDelegation('announcementBanner');

    const renderBanners = (data) => {
        const updateBanner = document.getElementById('updateBanner');
        const annBanner = document.getElementById('announcementBanner');

        const isUpdate = data && (data.update_available === true || data.has_changelog === true);
        const updateHtml = typeof data?.update_banner === 'string' ? data.update_banner.trim() : '';
        const notifHtml = typeof data?.notification === 'string' ? data.notification.trim() : '';

        // 1. Script Update Banner: shown ONLY when an update or changelog diff is available
        if (updateBanner) {
            if (isUpdate && updateHtml) {
                updateBanner.innerHTML = updateHtml;
                updateBanner.classList.remove('hidden');
            } else {
                updateBanner.classList.add('hidden');
            }
        }

        // 2. Developer Announcement Banner: shown whenever notification.html contains content
        if (annBanner) {
            if (notifHtml) {
                annBanner.innerHTML = notifHtml;
                annBanner.classList.remove('hidden');
            } else {
                annBanner.classList.add('hidden');
            }
        }
    };

    const checkForUpdates = async () => {
        try {
            const res = await fetch('/api/update_check', { cache: 'no-store' });
            if (!res.ok) return;
            const data = await res.json();
            if (!data) return;
            latestUpdateInfo = data;
            renderBanners(data);
        } catch (e) {
            // Offline or server restarting - skip silently
        }
    };

    checkForUpdates();

    const btnRestart = document.getElementById('btnRestart');
    if (btnRestart) {
        btnRestart.addEventListener('click', async () => {
            if (!await showConfirm('Перезапустить процесс локального сервера деплоера?', 'Перезапуск сервера', { confirmText: 'Перезапустить', icon: '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>' })) {
                return;
            }

            btnRestart.disabled = true;
            btnRestart.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon spin"><line x1="12" y1="2" x2="12" y2="6"/><line x1="12" y1="18" x2="12" y2="22"/><line x1="4.93" y1="4.93" x2="7.76" y2="7.76"/><line x1="16.24" y1="16.24" x2="19.07" y2="19.07"/><line x1="2" y1="12" x2="6" y2="12"/><line x1="18" y1="12" x2="22" y2="12"/><line x1="4.93" y1="19.07" x2="7.76" y2="16.24"/><line x1="16.24" y1="7.76" x2="19.07" y2="4.93"/></svg> Перезапуск...';

            try {
                const res = await fetch('/api/restart', { method: 'POST' });
                const data = await res.json();
                if (!data.ok) {
                    showToast('Ошибка перезапуска: ' + (data.message || 'Ошибка'), 'error');
                    btnRestart.disabled = false;
                    btnRestart.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg> Перезапустить';
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
            if (!await showConfirm('Вы действительно хотите выключить локальный сервер деплоера?', 'Выключение сервера', { confirmText: 'Выключить', danger: true, icon: '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon"><polygon points="7.86 2 16.14 2 22 7.86 22 16.14 16.14 22 7.86 22 2 16.14 2 7.86 7.86 2"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>' })) {
                return;
            }

            btnShutdown.disabled = true;
            btnShutdown.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon spin"><line x1="12" y1="2" x2="12" y2="6"/><line x1="12" y1="18" x2="12" y2="22"/><line x1="4.93" y1="4.93" x2="7.76" y2="7.76"/><line x1="16.24" y1="16.24" x2="19.07" y2="19.07"/><line x1="2" y1="12" x2="6" y2="12"/><line x1="18" y1="12" x2="22" y2="12"/><line x1="4.93" y1="19.07" x2="7.76" y2="16.24"/><line x1="16.24" y1="7.76" x2="19.07" y2="4.93"/></svg> Выключение...';

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
                    btnShutdown.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon"><polygon points="7.86 2 16.14 2 22 7.86 22 16.14 16.14 22 7.86 22 2 16.14 2 7.86 7.86 2"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg> Выключить';
                    return;
                }
                startShutdownReconnectPolling();
            } catch (e) {
                startShutdownReconnectPolling();
            }
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

    window.initServerDropZones();
    window.fetchServers();
});
