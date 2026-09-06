    // Crypto functions (V2: 600k iterations with auto-migration from legacy V1: 100k)
    const deriveKeyV2 = async (password) => {
        const enc = new TextEncoder();
        const keyMaterial = await window.crypto.subtle.importKey(
            "raw", enc.encode(password), { name: "PBKDF2" }, false, ["deriveBits", "deriveKey"]
        );
        return window.crypto.subtle.deriveKey(
            { name: "PBKDF2", salt: enc.encode("3x-ui-salt-v2"), iterations: 600000, hash: "SHA-256" },
            keyMaterial, { name: "AES-GCM", length: 256 }, true, ["encrypt", "decrypt"]
        );
    };

    const deriveKeyV1 = async (password) => {
        const enc = new TextEncoder();
        const keyMaterial = await window.crypto.subtle.importKey(
            "raw", enc.encode(password), { name: "PBKDF2" }, false, ["deriveBits", "deriveKey"]
        );
        return window.crypto.subtle.deriveKey(
            { name: "PBKDF2", salt: enc.encode("3x-ui-salt-v1"), iterations: 100000, hash: "SHA-256" },
            keyMaterial, { name: "AES-GCM", length: 256 }, true, ["encrypt", "decrypt"]
        );
    };

    const getVaultCookie = () => {
        const name = "vault_key=";
        const decoded = decodeURIComponent(document.cookie || '');
        const ca = decoded.split(';');
        for (let i = 0; i < ca.length; i++) {
            let c = ca[i].trim();
            if (c.indexOf(name) === 0) {
                return c.substring(name.length, c.length);
            }
        }
        return "";
    };

    const setVaultCookie = (keyB64) => {
        const maxAge = 86400; // 24 hours in seconds
        document.cookie = `vault_key=${encodeURIComponent(keyB64)}; max-age=${maxAge}; path=/; SameSite=Strict`;
    };

    const clearVaultCookie = () => {
        document.cookie = "vault_key=; max-age=0; path=/; SameSite=Strict";
    };
    const getPayloadVersion = (encryptedBase64) => {
        if (!encryptedBase64) return 2;
        try {
            const parsed = JSON.parse(atob(encryptedBase64));
            return parsed.v || 1;
        } catch (e) {
            return 1;
        }
    };

    const encryptData = async (text, key) => {
        if (!text) return "";
        const enc = new TextEncoder();
        const iv = window.crypto.getRandomValues(new Uint8Array(12));
        const encrypted = await window.crypto.subtle.encrypt(
            { name: "AES-GCM", iv: iv }, key, enc.encode(text)
        );
        return btoa(JSON.stringify({ v: 2, iv: Array.from(iv), data: Array.from(new Uint8Array(encrypted)) }));
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

    window.deriveKeyV2 = deriveKeyV2;
    window.deriveKeyV1 = deriveKeyV1;
    window.getVaultCookie = getVaultCookie;
    window.setVaultCookie = setVaultCookie;
    window.clearVaultCookie = clearVaultCookie;
    window.getPayloadVersion = getPayloadVersion;
    window.encryptData = encryptData;
    window.decryptData = decryptData;
