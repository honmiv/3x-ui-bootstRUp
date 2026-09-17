// Logs & progress indicators (verbatim from app.js)
const terminalLogs = document.getElementById('terminalLogs');
const appendLog = (message, level = 'info') => {
        const line = document.createElement('div');
        line.className = `log-line ${level}`;
        line.textContent = message;
        terminalLogs.appendChild(line);

        // Update progress indicator based on log message
        updateProgressIndicator(message);

        line.scrollIntoView({ block: 'end', behavior: 'smooth' });
    };

    const initProgressIndicator = (hasSub = false, isFreedomSub = false) => {
        const stage1 = document.getElementById('stage1');

        const stage2 = document.getElementById('stage2');
        const stage3 = document.getElementById('stage3');
        const connector23 = document.getElementById('connector23');
        
        if (stage1) stage1.classList.add('active');
        if (stage2) {
            stage2.classList.remove('active', 'completed');
            const stage2Name = stage2.querySelector('.stage-name');
            if (stage2Name) {
                stage2Name.textContent = isFreedomSub ? 'Sub Server' : 'Proxy Node';
            }
        }
        if (stage3) {
            if (hasSub && !isFreedomSub) {
                stage3.classList.remove('hidden');
                if (connector23) connector23.classList.remove('hidden');
            } else {
                stage3.classList.add('hidden');
                if (connector23) connector23.classList.add('hidden');
            }
        }
        
        const infoText = document.getElementById('currentStageInfo');
        if (infoText) {
            infoText.innerHTML = `<span class="info-icon"><span class="rocket-slot rocket-slot-progress">${rocketSvg('')}</span></span><span class="info-text">STAGE 1: Развертывание Freedom Node...</span>`;
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
            infoText.innerHTML = `<span class="info-icon"><span class="rocket-slot rocket-slot-progress">${rocketSvg('')}</span></span><span class="info-text">STAGE 1: Развертывание Freedom Node...</span>`;
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
        if (message.includes('STAGE 2') && (message.includes('PROXY NODE') || message.includes('SUBSCRIPTION SERVER'))) {
            if (stage2) stage2.classList.add('active');
            const stageName = message.includes('SUBSCRIPTION SERVER') ? 'Subscription Server' : 'Proxy Node';
            infoText.innerHTML = `<span class="info-icon"><span class="rocket-slot rocket-slot-progress">${rocketSvg('')}</span></span><span class="info-text">STAGE 2: Развертывание ${stageName}...</span>`;
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
            infoText.innerHTML = `<span class="info-icon"><span class="rocket-slot rocket-slot-progress">${rocketSvg('')}</span></span><span class="info-text">STAGE 3: Развертывание Subscription Server...</span>`;
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
            infoText.innerHTML = `<span class="info-icon"><span class="rocket-slot rocket-slot-progress">${rocketSvg('')}</span></span><span class="info-text">Все этапы завершены успешно!</span>`;
        }
    };

    const startDeployLogStream = (onDone) => {
        const eventSource = new EventSource('/api/deploy/logs');
        eventSource.onmessage = (event) => {
            try {
                const item = JSON.parse(event.data);
                if (item.event === 'done') {
                    eventSource.close();
                    onDone();
                } else {
                    appendLog(item.message, item.level || 'info');
                }
            } catch (e) {
                console.error('Failed to parse SSE event data:', e);
            }
        };
        eventSource.onerror = () => {
            eventSource.close();
            onDone();
        };
    };

    const btnCopyLogs = document.getElementById('btnCopyLogs');
    if (btnCopyLogs) {
        btnCopyLogs.addEventListener('click', () => {
            const text = terminalLogs.innerText;
            copyToClipboard(text, btnCopyLogs);
        });
    }

window.appendLog = appendLog;
window.initProgressIndicator = initProgressIndicator;
window.updateProgressIndicator = updateProgressIndicator;
window.startDeployLogStream = startDeployLogStream;
