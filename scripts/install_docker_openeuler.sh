#!/bin/bash
# Install Docker CE on openEuler using Aliyun mirror
# Consolidated approach: same Aliyun source as other RHEL-family, no start.py dependency
# Usage: bash install_docker_openeuler.sh
# Key: openEuler $releasever is not 7/8/9, must hardcode to 8
set -e

echo "[INFO] Installing Docker CE for openEuler (releasever=8, Aliyun mirror)"

# Kill any stuck start.py
kill $(pgrep -f start.py) 2>/dev/null || true

# Remove conflicting packages (openEuler ships docker-engine)
yum remove -y docker-engine docker docker-client docker-common 2>/dev/null || true

# Install dependencies
yum install -y yum-utils 2>&1 | tail -3

# Optimize DNF/YUM: enable parallel downloads
if ! grep -q "max_parallel_downloads" /etc/dnf/dnf.conf 2>/dev/null; then
    echo "max_parallel_downloads=10" >> /etc/dnf/dnf.conf
    echo "fastestmirror=True" >> /etc/dnf/dnf.conf
    echo "[INFO] DNF optimized: max_parallel_downloads=10, fastestmirror=True"
fi

# Create Docker CE repo directly (no download+sed needed)
# Key: replace $releasever with 8, use Aliyun mirror
cat > /etc/yum.repos.d/docker-ce.repo << 'REPOEOF'
[docker-ce-stable]
name=Docker CE Stable - $basearch
baseurl=https://mirrors.aliyun.com/docker-ce/linux/centos/8/$basearch/stable
enabled=1
gpgcheck=1
gpgkey=https://mirrors.aliyun.com/docker-ce/linux/centos/gpg
REPOEOF

# Install Docker
yum install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin 2>&1 | tail -10

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

# Start and enable
systemctl enable --now docker
systemctl reset-failed docker 2>/dev/null || true

# Handle potential nftables issue (same as Anolis, just in case)
sleep 3
if ! systemctl is-active docker --quiet; then
    echo "[WARN] Docker not active, attempting nftables workaround..."
    kill -9 $(pgrep dockerd) 2>/dev/null || true
    rm -f /var/run/docker.pid
    systemctl reset-failed docker 2>/dev/null || true
    systemctl start docker
    sleep 3
fi

# Verify
docker --version
docker compose version
systemctl is-active docker

echo "DOCKER_INSTALL_OK"
