#!/bin/bash
# Install Docker CE on Debian-family (Ubuntu/Debian) using Aliyun mirror
# Usage: bash install_docker_debian.sh [codename]
#   codename: jammy (Ubuntu 22.04), noble (Ubuntu 24.04), bookworm (Debian 12), bullseye (Debian 11)
#   If not specified, auto-detect from /etc/os-release
set -e

# Auto-detect codename if not provided
if [ -z "$1" ]; then
    CODENAME=$(. /etc/os-release && echo "$VERSION_CODENAME")
    DISTRO=$(. /etc/os-release && echo "$ID")
else
    CODENAME=$1
    DISTRO=$(. /etc/os-release && echo "$ID")
fi

echo "[INFO] Detected: $DISTRO $CODENAME"

# Kill any stuck start.py
kill $(pgrep -f start.py) 2>/dev/null || true

# Remove conflicting packages
apt-get remove -y docker.io docker-doc docker-compose podman-docker containerd runc 2>/dev/null || true

# Optimize system source: replace with Aliyun mirror (8x faster for apt-get update)
if [ ! -f /etc/apt/sources.list.aliyun-bak ]; then
    cp /etc/apt/sources.list /etc/apt/sources.list.aliyun-bak 2>/dev/null || true
    if [ "$DISTRO" = "ubuntu" ]; then
        sed -i 's|http://archive.ubuntu.com/ubuntu|https://mirrors.aliyun.com/ubuntu|g' /etc/apt/sources.list 2>/dev/null || true
        sed -i 's|http://security.ubuntu.com/ubuntu|https://mirrors.aliyun.com/ubuntu|g' /etc/apt/sources.list 2>/dev/null || true
        # Ubuntu 24.04 uses new sources format
        if [ -f /etc/apt/sources.list.d/ubuntu.sources ]; then
            sed -i 's|http://archive.ubuntu.com/ubuntu|https://mirrors.aliyun.com/ubuntu|g' /etc/apt/sources.list.d/ubuntu.sources 2>/dev/null || true
            sed -i 's|http://security.ubuntu.com/ubuntu|https://mirrors.aliyun.com/ubuntu|g' /etc/apt/sources.list.d/ubuntu.sources 2>/dev/null || true
        fi
    elif [ "$DISTRO" = "debian" ]; then
        sed -i 's|http://deb.debian.org/debian|https://mirrors.aliyun.com/debian|g' /etc/apt/sources.list 2>/dev/null || true
        sed -i 's|http://security.debian.org/debian-security|https://mirrors.aliyun.com/debian-security|g' /etc/apt/sources.list 2>/dev/null || true
        # Debian 13+ uses DEB822 format (.sources file)
        if [ -f /etc/apt/sources.list.d/debian.sources ]; then
            sed -i 's|http://deb.debian.org/debian|https://mirrors.aliyun.com/debian|g' /etc/apt/sources.list.d/debian.sources 2>/dev/null || true
            sed -i 's|http://security.debian.org/debian-security|https://mirrors.aliyun.com/debian-security|g' /etc/apt/sources.list.d/debian.sources 2>/dev/null || true
            echo "[INFO] Debian DEB822 format sources updated"
        fi
    fi
    echo "[INFO] System source replaced with Aliyun mirror"
fi

# Install dependencies
apt-get update -qq
apt-get install -y ca-certificates curl

# Setup keyring (ASCII format, no gpg --dearmor needed)
install -m 0755 -d /etc/apt/keyrings
curl -fsSL "https://mirrors.aliyun.com/docker-ce/linux/${DISTRO}/gpg" -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc

# Add repo
echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/docker.asc] https://mirrors.aliyun.com/docker-ce/linux/${DISTRO} ${CODENAME} stable" > /etc/apt/sources.list.d/docker.list

# Update and install
apt-get update -qq
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Configure daemon.json (optimized: 4 fastest mirrors + parallel downloads)
mkdir -p /etc/docker
cat > /etc/docker/daemon.json << 'JSONEOF'
{
  "registry-mirrors": [
    "https://docker.m.daocloud.io",
    "https://docker.1ms.run",
    "https://hub.rat.dev",
    "https://docker.kejilion.pro"
  ],
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  },
  "max-concurrent-downloads": 10,
  "max-download-attempts": 5
}
JSONEOF

# Restart
systemctl enable --now docker
systemctl restart docker

# Verify
docker --version
docker compose version
systemctl is-active docker

echo "DOCKER_INSTALL_OK"
