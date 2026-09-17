(() => {
    'use strict';

    const ICONS = {
        client: `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon"><rect x="5" y="2" width="14" height="20" rx="2" ry="2"/><line x1="12" y1="18" x2="12.01" y2="18"/></svg>`,
        server: `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon"><rect x="2" y="2" width="20" height="8" rx="2" ry="2"/><rect x="2" y="14" width="20" height="8" rx="2" ry="2"/><line x1="6" y1="6" x2="6.01" y2="6"/><line x1="6" y1="18" x2="6.01" y2="18"/></svg>`,
        globe: `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon"><circle cx="12" cy="12" r="10"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>`,
        globeNetwork: `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>`,
        subServer: `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon"><circle cx="12" cy="12" r="2"/><path d="M16.24 7.76a6 6 0 0 1 0 8.49m-8.48-.01a6 6 0 0 1 0-8.49m11.31-2.82a10 10 0 0 1 0 14.14m-14.14 0a10 10 0 0 1 0-14.14"/></svg>`,
        cluster: `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>`,
        pc: `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon"><rect x="2" y="3" width="20" height="14" rx="2" ry="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>`,
        arrow: `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>`,
        refresh: `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon"><path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/><path d="M12 8v4l3 3"/></svg>`,
        power: `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon"><path d="M18.36 6.64a9 9 0 1 1-12.73 0"/><line x1="12" y1="2" x2="12" y2="12"/></svg>`
    };

    const renderNodeCard = ({
        title,
        desc = null,
        icon,
        badgeText = null,
        badgeType = 'foreign',
        badgeIcon = null,
        configurable = false,
        roleClass = ''
    }) => {
        let nodeClasses = 'topology-node';
        if (configurable) nodeClasses += ' configurable';
        if (roleClass) nodeClasses += ' ' + roleClass;

        let descHtml = '';
        if (Array.isArray(desc)) {
            descHtml = desc.filter(Boolean).map(d => `<span class="node-desc">${d}</span>`).join('');
        } else if (desc) {
            descHtml = `<span class="node-desc">${desc}</span>`;
        }

        let badgeHtml = '';
        if (badgeText) {
            const bClass = configurable
                ? 'topology-badge-configurable'
                : (badgeType ? `topology-badge-${badgeType}` : 'topology-badge-foreign');
            const bIcon = badgeIcon || (badgeType === 'ru' ? ICONS.globe : ICONS.globeNetwork);
            badgeHtml = `<span class="topology-badge ${bClass}">${bIcon} ${badgeText}</span>`;
        }

        return `
            <div class="${nodeClasses}">
                <span class="node-icon">${icon}</span>
                <span class="node-title">${title}</span>
                ${descHtml}
                ${badgeHtml}
            </div>
        `.trim();
    };

    const createClientNode = ({ desc = '', hasSubscription = false } = {}) => renderNodeCard({
        title: 'Клиент',
        desc: hasSubscription ? 'С подпиской' : desc,
        icon: ICONS.client,
        badgeText: 'РФ',
        badgeType: 'ru',
        configurable: false,
        roleClass: 'node-role-client'
    });

    const createProxyNode = ({ desc = 'Входной сервер', configurable = true } = {}) => renderNodeCard({
        title: 'Proxy Node',
        desc,
        icon: ICONS.server,
        badgeText: 'РФ',
        badgeType: 'ru',
        configurable,
        roleClass: 'node-role-proxy'
    });

    const createFreedomNode = ({ title = 'Freedom Node', desc = 'Выходной сервер', configurable = true } = {}) => renderNodeCard({
        title,
        desc,
        icon: ICONS.globeNetwork,
        badgeText: 'Зарубежье',
        badgeType: 'foreign',
        configurable,
        roleClass: 'node-role-freedom'
    });

    const createSubServerNode = ({ desc = 'Sub-Server', configurable = true, badgeText = 'Зарубежье' } = {}) => renderNodeCard({
        title: 'Сервер подписок',
        desc,
        icon: ICONS.subServer,
        badgeText,
        badgeType: 'foreign',
        configurable,
        roleClass: 'node-role-sub'
    });

    const createWebNode = ({ title = 'Свободный Web', desc = '' } = {}) => renderNodeCard({
        title,
        desc,
        icon: ICONS.globeNetwork,
        configurable: false
    });

    const createExternalNodes = ({ title = 'Внешние ноды', desc = 'Существующие 3X-UI' } = {}) => renderNodeCard({
        title,
        desc,
        icon: ICONS.cluster,
        configurable: false
    });

    const createLocalPcNode = ({ desc = './backups_panel/backup.tar.gz' } = {}) => renderNodeCard({
        title: 'Локальный ПК',
        desc,
        icon: ICONS.pc,
        badgeText: 'Локально',
        badgeType: 'local',
        configurable: false,
        roleClass: 'node-role-local'
    });

    const createMaintenanceNode = ({
        title = 'VPS Сервер',
        desc = '3X-UI Панель',
        icon = null,
        configurable = true,
        rocket = false
    } = {}) => {
        const nodeIcon = rocket
            ? (typeof window.rocketSvg === 'function' ? window.rocketSvg('topology-rocket') : ICONS.server)
            : (icon || ICONS.server);
        return renderNodeCard({
            title,
            desc,
            icon: nodeIcon,
            configurable
        });
    };

    const createArrow = (labels) => {
        const list = Array.isArray(labels) ? labels : [labels];
        const labelsHtml = list.filter(Boolean).map(lbl => `<span class="arrow-label">${lbl}</span>`).join('');
        return `
            <div class="topology-arrow">
                ${labelsHtml}
                <span>${ICONS.arrow}</span>
            </div>
        `.trim();
    };

    const createStage = (title, elements) => `
        <div class="topology-stage">
            <div class="topology-stage-title">${title}</div>
            <div class="topology-flow">
                ${elements.join('')}
            </div>
        </div>
    `.trim();

    const TOPOLOGY_MODES = {
        cascade_sub: () => [
            createStage('1. Получение единой подписки (Сервер подписок)', [
                createClientNode(),
                createArrow(['Запрос', 'подписки']),
                createSubServerNode({ configurable: true })
            ]),
            createStage('2. Каскадная маршрутизация (Двойной туннель)', [
                createClientNode({ hasSubscription: true }),
                createArrow('VLESS'),
                createProxyNode({ configurable: true }),
                createArrow(['VLESS', 'XHTTP']),
                createFreedomNode({ configurable: true }),
                createArrow(['Выход', 'в сеть']),
                createWebNode()
            ])
        ],

        cascade: () => [
            createStage('1. Получение подписки (Прямо с нод)', [
                createClientNode(),
                createArrow(['Запрос', 'подписки']),
                createProxyNode({ configurable: true })
            ]),
            createStage('2. Каскадная маршрутизация (Двойной туннель)', [
                createClientNode({ hasSubscription: true }),
                createArrow('VLESS'),
                createProxyNode({ configurable: true }),
                createArrow(['VLESS', 'XHTTP']),
                createFreedomNode({ configurable: true }),
                createArrow(['Выход', 'в сеть']),
                createWebNode()
            ])
        ],

        freedom_sub: () => [
            createStage('1. Получение подписки (Сервер подписок)', [
                createClientNode(),
                createArrow(['Запрос', 'подписки']),
                createSubServerNode({ configurable: true })
            ]),
            createStage('2. Прямое подключение через зарубежный сервер', [
                createClientNode({ hasSubscription: true }),
                createArrow('VLESS'),
                createFreedomNode({ configurable: true, desc: '3X-UI Панель' }),
                createArrow(['Выход', 'в сеть']),
                createWebNode()
            ])
        ],

        freedom_only: () => [
            createStage('1. Получение подписки (Прямо с Freedom Node)', [
                createClientNode(),
                createArrow(['Запрос', 'подписки']),
                createFreedomNode({ configurable: true, desc: 'Прямое подключение' })
            ]),
            createStage('2. Прямое подключение через зарубежный сервер', [
                createClientNode({ hasSubscription: true }),
                createArrow('VLESS'),
                createFreedomNode({ configurable: true, desc: '3X-UI Панель' }),
                createArrow(['Выход', 'в сеть']),
                createWebNode()
            ])
        ],

        single: () => TOPOLOGY_MODES.freedom_only(),

        proxy_only: () => [
            createStage('Каскадная маршрутизация (Двойной туннель)', [
                createClientNode({ hasSubscription: true }),
                createArrow('VLESS'),
                createProxyNode({ configurable: true, desc: 'Входной сервер' }),
                createArrow(['VLESS', 'XHTTP']),
                createFreedomNode({ configurable: false, desc: 'Выходной сервер' }),
                createArrow(['Выход', 'в сеть']),
                createWebNode()
            ])
        ],

        freedom_component: () => [
            createStage('Каскадная маршрутизация (Двойной туннель)', [
                createClientNode({ hasSubscription: true }),
                createArrow('VLESS'),
                createProxyNode({ configurable: false, desc: 'Входной сервер' }),
                createArrow(['VLESS', 'XHTTP']),
                createFreedomNode({ configurable: true, desc: 'Выходной сервер' }),
                createArrow(['Выход', 'в сеть']),
                createWebNode()
            ])
        ],

        sub_only: () => [
            createStage('Автономный Сервер подписок (Sub-Server)', [
                createClientNode(),
                createArrow(['Запрос', 'подписки']),
                createSubServerNode({ configurable: true }),
                createArrow('Проксирование'),
                createExternalNodes()
            ])
        ],

        backup: () => [
            createStage('Создание бэкапа удаленного сервера', [
                createLocalPcNode({ desc: './backups_panel/backup.tar.gz' }),
                createArrow(['Упаковка &', 'SCP Скачивание']),
                createMaintenanceNode({ title: 'Существующий VPS', desc: '3X-UI + Docker + Caddy', configurable: true })
            ])
        ],

        recovery: () => [
            createStage('Восстановление конфигурации из бэкапа', [
                createLocalPcNode({ desc: './backups_panel/backup.tar.gz' }),
                createArrow(['Загрузка &', 'Docker Compose']),
                createMaintenanceNode({ title: 'Новый VPS', desc: ['Восстановленная', '3X-UI Панель'], configurable: true, rocket: true })
            ])
        ],

        update_3xui: () => [
            createStage('Обновление 3X-UI панели на сервере', [
                createLocalPcNode({ desc: './backups_panel/backup.tar.gz' }),
                createArrow(['Бэкап и', 'обновление']),
                createMaintenanceNode({ title: 'VPS c 3x-ui', desc: ['Обновленный Docker', 'Образ 3X-UI'], configurable: true, rocket: true })
            ])
        ],

        restart_panel: () => [
            createStage('Перезапуск 3X-UI панели', [
                createLocalPcNode({ desc: 'SSH команда' }),
                createArrow(['docker compose', 'down / up']),
                createMaintenanceNode({ title: 'VPS c 3x-ui', desc: '3X-UI Панель', configurable: true, icon: ICONS.refresh })
            ])
        ],

        restart_server: () => [
            createStage('Перезагрузка сервера (VPS Reboot)', [
                createLocalPcNode({ desc: 'SSH команда' }),
                createArrow(['systemctl', 'reboot']),
                createMaintenanceNode({ title: 'VPS Сервер', desc: 'Перезагрузка ОС', configurable: true, icon: ICONS.power })
            ])
        ],

        restart_sub: () => [
            createStage('Перезапуск Сервера подписок', [
                createLocalPcNode({ desc: 'SSH команда' }),
                createArrow(['docker compose', 'down / up']),
                createSubServerNode({ configurable: true, desc: 'subs-server + sub-caddy' })
            ])
        ],

        update_sub: () => [
            createStage('Обновление Сервера подписок', [
                createLocalPcNode({ desc: 'Бэкап & файлы' }),
                createArrow(['Бэкап &', 'up -d --build']),
                createSubServerNode({ configurable: true, desc: 'subs-server + sub-caddy' })
            ])
        ],

        backup_sub: () => [
            createStage('Бэкап конфигурации Сервера подписок', [
                createLocalPcNode({ desc: './backups_panel/backup.tar.gz' }),
                createArrow(['Упаковка &', 'SCP Скачивание']),
                createSubServerNode({ configurable: true, desc: 'nodes.json + Caddyfile' })
            ])
        ],

        rollback_sub: () => [
            createStage('Восстановление Сервера подписок из бэкапа', [
                createLocalPcNode({ desc: './backups_panel/backup.tar.gz' }),
                createArrow(['Загрузка &', 'Docker Compose']),
                createSubServerNode({ configurable: true, desc: 'Восстановленная конфигурация' })
            ])
        ]
    };

    const renderTopologyDiagram = (mode) => {
        const diagramEl = document.getElementById('topologyDiagram');
        if (!diagramEl) return;

        const builder = TOPOLOGY_MODES[mode];
        if (typeof builder === 'function') {
            const stages = builder();
            diagramEl.innerHTML = Array.isArray(stages) ? stages.join('') : stages;
        } else {
            diagramEl.innerHTML = '';
        }
    };

    window.renderTopologyDiagram = renderTopologyDiagram;
})();
