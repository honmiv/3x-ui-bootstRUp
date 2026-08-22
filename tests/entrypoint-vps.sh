#!/usr/bin/env bash
set -e

# Generate host keys if missing and start SSH daemon
mkdir -p /var/run/sshd
ssh-keygen -A >/dev/null 2>&1 || true
/usr/sbin/sshd

# Clean up any leftover docker PID
rm -f /var/run/docker.pid /var/run/docker.sock

# Start dockerd in background
echo "[TEST-VPS] Starting Docker daemon..."
dockerd > /var/log/dockerd.log 2>&1 &

# Wait for dockerd to be ready
timeout=45
counter=0
while ! docker info >/dev/null 2>&1; do
    sleep 1
    counter=$((counter + 1))
    if [ "$counter" -ge "$timeout" ]; then
        echo "[ERROR] Docker daemon failed to start within $timeout seconds. Logs:"
        cat /var/log/dockerd.log
        exit 1
    fi
done

echo "[TEST-VPS] Docker daemon & SSH server are ready."

# Pre-load cached docker images if available
if [ -d /var/cache/docker-preload ]; then
    for tarfile in /var/cache/docker-preload/*.tar; do
        if [ -f "$tarfile" ]; then
            echo "[TEST-VPS] Pre-loading $(basename "$tarfile") into Docker..."
            docker load -i "$tarfile" >/dev/null 2>&1 || true
        fi
    done
    echo "[TEST-VPS] All cached images loaded! Ready for tests."
fi

# Keep container alive
exec tail -f /dev/null
