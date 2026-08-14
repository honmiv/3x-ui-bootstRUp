const rocketSvg = (className = '') => `
    <svg class="rocket-svg ${className}" viewBox="0 0 64 64" role="img" aria-label="Ракета">
        <defs>
            <linearGradient id="rocketBodyGradient" x1="0" y1="1" x2="1" y2="0">
                <stop offset="0%" stop-color="#94a3b8" />
                <stop offset="40%" stop-color="#f1f5f9" />
                <stop offset="80%" stop-color="#ffffff" />
                <stop offset="100%" stop-color="#e2e8f0" />
            </linearGradient>
            <linearGradient id="rocketNoseGradient" x1="0" y1="1" x2="1" y2="0">
                <stop offset="0%" stop-color="#991b1b" />
                <stop offset="40%" stop-color="#ef4444" />
                <stop offset="80%" stop-color="#fca5a5" />
                <stop offset="100%" stop-color="#dc2626" />
            </linearGradient>
            <linearGradient id="rocketWindowRing" x1="0" y1="0" x2="1" y2="1">
                <stop offset="0%" stop-color="#94a3b8" />
                <stop offset="100%" stop-color="#f8fafc" />
            </linearGradient>
            <linearGradient id="rocketWindowGlass" x1="0" y1="0" x2="1" y2="1">
                <stop offset="0%" stop-color="rgba(255,255,255,0.9)" />
                <stop offset="40%" stop-color="rgba(255,255,255,0)" />
                <stop offset="100%" stop-color="rgba(0,0,0,0.15)" />
            </linearGradient>
            <linearGradient id="rocketFinGradient" x1="0" y1="1" x2="1" y2="0">
                <stop offset="0%" stop-color="#be185d" />
                <stop offset="100%" stop-color="#f472b6" />
            </linearGradient>
            <linearGradient id="rocketFlameGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stop-color="#fef9c3" />
                <stop offset="30%" stop-color="#fde047" />
                <stop offset="70%" stop-color="#f97316" />
                <stop offset="100%" stop-color="#ea580c" />
            </linearGradient>
        </defs>
        <g class="rocket-speed-lines" aria-hidden="true">
            <path class="rocket-speed-line rocket-speed-line-a" d="M8 9v12" />
            <path class="rocket-speed-line rocket-speed-line-b" d="M20 40v17" />
            <path class="rocket-speed-line rocket-speed-line-c" d="M34 6v13" />
            <path class="rocket-speed-line rocket-speed-line-d" d="M47 32v16" />
            <path class="rocket-speed-line rocket-speed-line-e" d="M58 17v12" />
        </g>
        <g class="rocket-body">
            <path class="rocket-fin-side" d="M 21 38 Q 10 44, 11 51 Q 18 49, 23 46 Z" fill="url(#rocketFinGradient)" />
            <path class="rocket-fin-side" d="M 43 38 Q 54 44, 53 51 Q 46 49, 41 46 Z" fill="url(#rocketFinGradient)" />
            <path d="M 26 45 L 23 53 C 23 54.5 41 54.5 41 53 L 38 45 Z" fill="#64748b" />
            <ellipse cx="32" cy="53" rx="9" ry="1.5" fill="#334155" />
            <path class="rocket-flame" d="M 26 53 C 23 55 16 59 18 67 C 19 65 23 63 25 61 C 26 69 29 79 32 85 C 35 79 38 69 39 61 C 41 63 45 65 46 67 C 48 59 41 55 38 53 Q 32 49 26 53 Z" fill="url(#rocketFlameGradient)" />
            <path d="M 32 6 C 22 16 16 30 20 46 C 26 49 38 49 44 46 C 48 30 42 16 32 6 Z" fill="url(#rocketBodyGradient)" />
            <path d="M 32 6 C 27 11 23.8 16 22 22 C 27 23.5 37 23.5 42 22 C 40.2 16 37 11 32 6 Z" fill="url(#rocketNoseGradient)" />
            <path class="rocket-fin-center" d="M 32 39 C 28 44 26 50 32 53 C 38 50 36 44 32 39 Z" fill="url(#rocketFinGradient)" />
            <g class="rocket-window-roll">
                <g class="rocket-window">
                    <circle cx="32" cy="28" r="6.5" fill="url(#rocketWindowRing)" />
                    <circle cx="32" cy="28" r="4.5" fill="#38bdf8" />
                    <circle cx="32" cy="28" r="4.5" fill="url(#rocketWindowGlass)" />
                </g>
            </g>
            <g class="rocket-exhaust" aria-hidden="true">
                <circle class="rocket-exhaust-puff rocket-exhaust-puff-a" cx="32" cy="81" r="3.4" />
                <circle class="rocket-exhaust-puff rocket-exhaust-puff-b" cx="28" cy="79" r="2.6" />
                <circle class="rocket-exhaust-puff rocket-exhaust-puff-c" cx="36" cy="79" r="2.6" />
            </g>
        </g>
    </svg>`;
