#!/bin/bash
# Install Docker CE on RHEL-family (AlmaLinux/Rocky/Anolis/Kylin) using Aliyun mirror
# Usage: bash install_docker_rhel.sh <os_id> <releasever>
#   os_id: almalinux, rocky, anolis, centos, kylin
#   releasever: 8 or 9 (Anolis 23 → 9, Rocky 9/10 → 9, Kylin V10 → 8)
# Example:
#   bash install_docker_rhel.sh almalinux 9
#   bash install_docker_rhel.sh anolis 9
#   bash install_docker_rhel.sh kylin 8
#
# Mirror fallback: Aliyun → USTC → TUNA (auto-switch on 403/missing packages)
set -e

OS_ID=$1
RELEASEVER=$2

if [ -z "$OS_ID" ] || [ -z "$RELEASEVER" ]; then
    echo "Usage: bash $0 <os_id> <releasever>"
    echo "  os_id: almalinux, rocky, anolis, centos, kylin"
    echo "  releasever: 8 or 9"
    echo "Example: bash $0 almalinux 9"
    exit 1
fi

echo "[INFO] Installing Docker CE for $OS_ID (releasever=$RELEASEVER)"

# Kill any stuck start.py
kill $(pgrep -f start.py) 2>/dev/null || true

# Remove conflicting packages
dnf remove -y podman podman-docker docker docker-engine 2>/dev/null || true

# Install dnf-plugins-core
dnf install -y dnf-plugins-core 2>&1 | tail -3

# Optimize DNF: enable parallel downloads and fastest mirror
if ! grep -q "max_parallel_downloads" /etc/dnf/dnf.conf 2>/dev/null; then
    echo "max_parallel_downloads=10" >> /etc/dnf/dnf.conf
    echo "fastestmirror=True" >> /etc/dnf/dnf.conf
    echo "[INFO] DNF optimized: max_parallel_downloads=10, fastestmirror=True"
fi

# Docker CE repo mirror list (fallback order: Aliyun → USTC → TUNA)
MIRRORS=(
    "https://mirrors.aliyun.com/docker-ce/linux/centos"
    "https://mirrors.ustc.edu.cn/docker-ce/linux/centos"
    "https://mirrors.tuna.tsinghua.edu.cn/docker-ce/linux/centos"
)

DOCKER_INSTALLED=false

for MIRROR_BASE in "${MIRRORS[@]}"; do
    MIRROR_NAME=$(echo "$MIRROR_BASE" | sed 's|https://||; s|/docker-ce.*||')

    echo "[INFO] Trying mirror: $MIRROR_NAME (releasever=$RELEASEVER)"

    # Create repo file
    cat > /etc/yum.repos.d/docker-ce.repo << REPOEOF
[docker-ce-stable]
name=Docker CE Stable - \$basearch
baseurl=${MIRROR_BASE}/${RELEASEVER}/\$basearch/stable
enabled=1
gpgcheck=1
gpgkey=${MIRROR_BASE}/gpg
REPOEOF

    # Clean cache and install
    dnf clean all 2>/dev/null || true

    # Temporarily disable set -e to capture dnf result
    set +e
    INSTALL_OUTPUT=$(dnf install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin 2>&1)
    INSTALL_RC=$?
    set -e

    if [ $INSTALL_RC -eq 0 ]; then
        echo "[INFO] Docker packages installed successfully from $MIRROR_NAME"
        DOCKER_INSTALLED=true
        break
    fi

    # Check if failure is due to 403/missing packages
    if echo "$INSTALL_OUTPUT" | grep -qE "403|No more mirrors|Cannot download"; then
        echo "[WARN] Mirror $MIRROR_NAME has missing packages (403), trying next mirror..."
        echo "$INSTALL_OUTPUT" | tail -5
    else
        # Non-mirror failure, show error and exit
        echo "[ERROR] dnf install failed (non-mirror issue):"
        echo "$INSTALL_OUTPUT" | tail -10
        exit 1
    fi
done

if [ "$DOCKER_INSTALLED" = "false" ]; then
    echo "[ERROR] All mirrors failed to provide Docker packages"
    exit 1
fi

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

# Start and enable (use || true to avoid set -e exit, fixes are below)
systemctl enable --now docker 2>/dev/null || true
systemctl reset-failed docker 2>/dev/null || true

# Check if Docker is running; if not, try fixes
sleep 3
if ! systemctl is-active docker --quiet; then
    echo "[WARN] Docker not active, attempting fixes..."

    # Fix 1: Missing kernel modules (Rocky 10 / RHEL 10 kernel 6.12+)
    # br_netfilter, xt_addrtype, iptable_nat are needed by iptables-nft
    if ! lsmod | grep -q br_netfilter; then
        echo "[INFO] Trying to load br_netfilter..."
        modprobe br_netfilter 2>/dev/null || true
        modprobe xt_addrtype 2>/dev/null || true
        modprobe iptable_nat 2>/dev/null || true

        # If modprobe fails, install kernel-modules-extra (contains these modules)
        if ! lsmod | grep -q br_netfilter; then
            echo "[INFO] Installing kernel-modules + kernel-modules-extra..."
            KVER=$(uname -r)
            dnf install -y "kernel-modules-${KVER}" "kernel-modules-extra-${KVER}" 2>&1 | tail -3
            modprobe br_netfilter 2>/dev/null || true
            modprobe xt_addrtype 2>/dev/null || true
            modprobe iptable_nat 2>/dev/null || true
            # Persist for reboot
            printf 'br_netfilter\nxt_addrtype\niptable_nat\n' > /etc/modules-load.d/docker-netfilter.conf
        fi
    fi

    # Fix 2: Kill stuck dockerd and retry (nftables workaround for Anolis)
    echo "[INFO] Restarting Docker..."
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
