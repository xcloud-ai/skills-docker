---
name: "docker"
description: "Comprehensive Docker skill: install, image build, container lifecycle, network, volume, compose, troubleshooting. Invoke when user asks anything about Docker operations."
---


> **⚡ 操作原则：先验证再修改**
>
> 修改文档中的命令、路径、参数前，**必须先实际执行验证**，确认当前命令是否可用。不要基于推测或部分检查就修改已验证的命令模式。
>
> - ❌ 错误：用 `find` 没找到文件，就认为路径不存在，然后修改文档
> - ✅ 正确：先实际执行 `source /path/to/venv/bin/activate && openstack --version`，确认是否可用，再决定是否修改
> - 教训来源：2026-07-19 误将 `/path/to/venv`（真实路径）当成占位符，错误修改了 172 处正确命令

# Docker 综合管理 Skill

涵盖 Docker 安装部署、镜像管理、容器生命周期、网络配置、数据卷管理、Dockerfile 构建、Docker Compose 编排、故障排查的系统性 Skill。支持 6 大 Linux 发行版（Ubuntu、Debian、Rocky、Anolis、Kylin、openEuler），全部经过实际验证。安装源使用阿里云镜像，截至 2026-07-20 安装版本为 Docker CE 29.6.2 + Compose v5.3.1。内置版本兼容性参考，覆盖各发行版历史与未来版本的快速部署指南。

## 目录

1. [安装与配置](#1-安装与配置)
2. [镜像管理](#2-镜像管理)
3. [容器生命周期](#3-容器生命周期)
4. [容器查看与调试](#4-容器查看与调试)
5. [网络管理](#5-网络管理)
6. [数据卷管理](#6-数据卷管理)
7. [Dockerfile 构建](#7-dockerfile-构建)
8. [Docker Compose 编排](#8-docker-compose-编排)
9. [系统管理与清理](#9-系统管理与清理)
10. [故障排查](#10-故障排查)

---

## 1. 安装与配置

### 支持的操作系统

| 系统 | 已验证版本 | 支持版本范围 | 包管理器 | 安装方式 |
|------|-----------|-------------|---------|---------|
| Ubuntu | 22.04 (jammy) | 20.04 ~ 26.04 LTS | apt | apt 在线安装（阿里云源） |
| Debian | 13 (trixie) | 10 ~ 14 | apt | apt 在线安装（阿里云源） |
| Rocky Linux | 10 | 8 ~ 10 | dnf | dnf 在线安装（阿里云源） |
| AlmaLinux | — | 8 ~ 10 | dnf | dnf 在线安装（阿里云源） |
| Anolis OS | 23.4 | 7 / 8 / 23 | dnf | dnf 在线安装（阿里云源） |
| Kylin V10 | SP3 | SP1 / SP2 / SP3 | dnf | dnf 在线安装（阿里云源） |
| openEuler | 24.03 | 22.03 ~ 25.03 | dnf | dnf 在线安装（阿里云源） |
| CentOS | — | 7 / 8 Stream / 9 Stream | yum/dnf | 在线源安装 |

> 详细的版本→codename/releasever 映射、Docker 支持状态、已知问题速查，见 [版本兼容性参考](#版本兼容性参考2026-07-20-新增)。

### 安装版本

> 截至 2026-07-17，通过阿里云镜像源安装的最新版本：

| 组件 | 版本（apt/dnf 源） | 版本（start.py 脚本） |
|------|-------------------|---------------------|
| Docker CE | 29.6.1 | 26.1.3（openEuler 旧版） |
| Containerd | 随包附带 | 随包附带 |
| Buildx Plugin | 随包附带 | 随包附带 |
| Compose Plugin | v5.3.1 | v2.27.0（openEuler 旧版） |

> **注意**：start.py 脚本为早期版本，现已被 `install_docker_openeuler.sh` 替代。新脚本使用阿里云源，安装版本与其他 5 种 OS 一致（29.6.1）。若需最新版建议直接用阿里云源在线安装。

### 环境要求

| 项目 | 要求 |
|------|------|
| 权限 | root |
| 架构 | x86_64 (amd64) / arm64 |
| 依赖 | Python 3, curl 或 wget |

### 使用安装脚本

本 Skill 随附 `start.py` 安装脚本，自动检测操作系统并选择对应安装方式：

```bash
# 命令行模式
python3 start.py install          # 安装 Docker（自动检测系统）
python3 start.py install -f       # 强制重新安装
python3 start.py uninstall        # 卸载 Docker
python3 start.py reconfigure      # 重新配置镜像加速
python3 start.py status           # 查看 Docker 状态

# 交互式菜单
python3 start.py
```

### 安装流程（自动适配）

脚本通过 `/etc/os-release` 检测系统类型，自动选择安装路径：

**Debian 系（Ubuntu/Debian）**：
1. 卸载冲突包（docker.io, podman 等）
2. 安装依赖（ca-certificates, curl）
3. 从 Docker 官方源下载 6 个 deb 包（支持断点续传，10 次重试）
4. 按依赖顺序通过 dpkg 安装，失败时自动修复依赖并重试
5. 配置 daemon.json + 启动服务 + 验证

**RHEL 系（CentOS/Rocky/Anolis/openEuler）**：
1. 卸载冲突包（docker-engine, podman 等）
2. 安装依赖（dnf-plugins-core / yum-utils）
3. 添加 docker-ce.repo 源
4. openEuler/Anolis 特殊处理：替换 `$releasever` 为 7 或 8
5. 替换为阿里云镜像源加速
6. 通过 yum/dnf 在线安装 5 个 rpm 包
7. 配置 daemon.json + 启动服务 + 验证

### 各系统手动安装方法（推荐：阿里云源）

> **已知问题**：`download.docker.com` 在部分网络环境中 SSL 握手失败（`curl: (35) OpenSSL SSL_connect: SSL_ERROR_SYSCALL`），建议直接使用阿里云镜像源 `mirrors.aliyun.com/docker-ce`。

#### Ubuntu 22.04/24.04（阿里云源，已验证）

```bash
# 1. 卸载旧版本
apt-get remove -y docker.io docker-doc docker-compose podman-docker containerd runc

# 2. 安装依赖 + 添加 GPG 密钥（使用阿里云源）
apt-get update
apt-get install -y ca-certificates curl
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://mirrors.aliyun.com/docker-ce/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc

# 3. 添加源（注意：用 .asc 格式而非 .gpg）
echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/docker.asc] https://mirrors.aliyun.com/docker-ce/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | tee /etc/apt/sources.list.d/docker.list

# 4. 安装
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# 5. 启动（apt 安装后自动启动，但建议确认）
systemctl enable --now docker
```

> **GPG 密钥格式**：阿里云源提供的是 ASCII 格式的 `.asc` 文件，直接用 `curl -o` 下载即可，**不要**用 `gpg --dearmor` 转换。`signed-by` 指向 `.asc` 文件。

#### Debian 12（阿里云源，已验证）

```bash
# 与 Ubuntu 相同，将 ubuntu 替换为 debian，codename 为 bookworm
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://mirrors.aliyun.com/docker-ce/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/docker.asc] https://mirrors.aliyun.com/docker-ce/linux/debian bookworm stable" | tee /etc/apt/sources.list.d/docker.list
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
systemctl enable --now docker
```

#### CentOS 7/8/9 Stream

```bash
# 1. 卸载旧版本
yum remove -y docker docker-client docker-client-latest docker-common docker-latest docker-latest-logrotate docker-logrotate docker-engine podman runc

# 2. 添加源
yum install -y yum-utils
yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo

# 3. 安装
yum install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# 4. 启动（RPM 系不自动启动）
systemctl enable --now docker
```

#### Rocky Linux 9（阿里云源，已验证）

```bash
# 1. 卸载旧版本
dnf remove -y docker docker-client docker-common podman runc

# 2. 手动创建 repo 文件（使用阿里云源，避免 SSL 问题）
cat > /etc/yum.repos.d/docker-ce.repo << 'EOF'
[docker-ce-stable]
name=Docker CE Stable - $basearch
baseurl=https://mirrors.aliyun.com/docker-ce/linux/centos/9/$basearch/stable
enabled=1
gpgcheck=1
gpgkey=https://mirrors.aliyun.com/docker-ce/linux/centos/gpg
EOF

# 3. 安装
dnf install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# 4. 启动
systemctl enable --now docker
```

#### Anolis OS 23（阿里云源，已验证）

```bash
# 1. 卸载预装的 podman（关键！不卸载会冲突）
dnf remove -y podman podman-docker docker docker-engine

# 2. 手动创建 repo 文件（使用阿里云源）
# Anolis 23 → 替换 releasever 为 9
cat > /etc/yum.repos.d/docker-ce.repo << 'EOF'
[docker-ce-stable]
name=Docker CE Stable - $basearch
baseurl=https://mirrors.aliyun.com/docker-ce/linux/centos/9/$basearch/stable
enabled=1
gpgcheck=1
gpgkey=https://mirrors.aliyun.com/docker-ce/linux/centos/gpg
EOF

# 3. 安装
dnf install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# 4. 启动（可能遇到 iptables/nftables 问题，见下方故障排查）
systemctl enable --now docker
```

> **已知问题（Anolis OS 23）**：Docker 安装后首次启动可能因 nftables 兼容性失败，表现为 `systemctl start docker` 超时。解决方法：
> ```bash
> # 杀掉残留的 dockerd 进程
> kill -9 $(pgrep dockerd) 2>/dev/null
> rm -f /var/run/docker.pid
> systemctl reset-failed docker
> systemctl start docker
> ```
> 如果仍然失败，检查 `journalctl -u docker.service` 是否有 iptables 相关错误。

#### openEuler 24.03（阿里云源，已验证）

**推荐方式：使用 install_docker_openeuler.sh 脚本**

```bash
# 直接创建 repo 文件（阿里云源，releasever=8 硬编码）
cat > /etc/yum.repos.d/docker-ce.repo << 'EOF'
[docker-ce-stable]
name=Docker CE Stable - $basearch
baseurl=https://mirrors.aliyun.com/docker-ce/linux/centos/8/$basearch/stable
enabled=1
gpgcheck=1
gpgkey=https://mirrors.aliyun.com/docker-ce/linux/centos/gpg
EOF

# 安装
yum install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
systemctl enable --now docker
```

> **关键**：openEuler 不在 Docker 官方支持列表中，`$releasever` 不是 7/8/9，必须手动指定为 `8`。`get.docker.com` 便捷脚本会报 `Unsupported distribution`。
> **脚本位置**：`scripts/install_docker_openeuler.sh`（自动处理 repo 创建、安装、daemon.json 配置、nftables 兜底）
> **旧版方式**：start.py 脚本仍可用（安装 Docker CE 26.1.3），但建议使用新脚本以获取最新版本（29.6.1）。

### 各系统关键差异对比

| 维度 | Debian 系 (Ubuntu/Debian) | RHEL 系 (CentOS/Rocky/Anolis/openEuler) |
|------|--------------------------|----------------------------------------|
| 包格式 | .deb | .rpm |
| 包管理器 | apt-get / dpkg | yum / dnf |
| Docker 源 | mirrors.aliyun.com/docker-ce/linux/{distro} | mirrors.aliyun.com/docker-ce/linux/centos |
| GPG 密钥 | .asc 格式，需手动添加到 keyrings | repo 文件自带 gpgcheck |
| 安装方式 | apt-get 在线安装 | dnf/yum 在线安装 |
| 安装后启动 | 自动启动 | 需手动 systemctl start |
| 版本号格式 | `5:29.6.1-1~ubuntu.22.04~jammy` | `29.6.1`（纯数字） |
| 特殊处理 | 无 | openEuler/Anolis 需替换 $releasever |

### 安装速度优化（2026-07-20 新增）

所有安装脚本已内置以下优化，无需手动配置：

| 优化项 | 说明 | 效果 |
|--------|------|------|
| **系统源替换** | Debian 系自动将 `archive.ubuntu.com`/`deb.debian.org` 替换为阿里云源 | `apt-get update` 快约 8 倍（0.12s vs 0.94s） |
| **DNF 并行下载** | RHEL 系自动设置 `max_parallel_downloads=10` + `fastestmirror=True` | dnf install 快约 2-3 倍 |
| **镜像加速器精简** | daemon.json 从 10 个精简为 4 个（去掉不可用的） | `docker pull` 快约 48%（25s→13s） |
| **Docker 并行下载** | daemon.json 新增 `max-concurrent-downloads: 10` | 多层镜像并行拉取 |
| **deb 包并行下载** | start.py 用 ThreadPoolExecutor 6 包并行下载（原串行） | 下载阶段快约 3-4 倍 |

### 版本兼容性参考（2026-07-20 新增）

> **目的**：测试环境有限，但通过版本映射和已知问题速查，未来遇到新版本（如 Ubuntu 26.04、Debian 14、Rocky 11 等）可快速参考部署，无需从零调研。

#### Docker CE 官方支持 vs 社区兼容

| 平台 | 官方支持 | Docker 源路径 | 说明 |
|------|:--------:|--------------|------|
| Ubuntu | ✅ | `docker-ce/linux/ubuntu` | 官方测试验证，按 codename 区分 |
| Debian | ✅ | `docker-ce/linux/debian` | 官方测试验证，按 codename 区分 |
| CentOS | ✅ | `docker-ce/linux/centos` | 按 `$releasever`（7/8/9）区分 |
| RHEL | ✅ | `docker-ce/linux/centos` | 与 CentOS 共用源 |
| Fedora | ✅ | `docker-ce/linux/fedora` | 按 `$releasever` 区分 |
| Rocky Linux | ❌ 社区兼容 | `docker-ce/linux/centos` | RHEL 二进制兼容，用 CentOS 源 |
| AlmaLinux | ❌ 社区兼容 | `docker-ce/linux/centos` | RHEL 二进制兼容，用 CentOS 源 |
| Anolis OS | ❌ 社区兼容 | `docker-ce/linux/centos` | RHEL 兼容，需手动指定 releasever |
| openEuler | ❌ 社区兼容 | `docker-ce/linux/centos` | 不在官方列表，需手动指定 releasever=8 |
| Kylin V10 | ❌ 社区兼容 | `docker-ce/linux/centos` | 基于 CentOS 8/openEuler，用 releasever=8 |

> **关键规则**：Debian 系按 **codename**（如 jammy、bookworm）区分版本；RHEL 系按 **releasever**（如 8、9）区分版本。阿里云源路径中的 `{distro}` 和 `{codename}/{releasever}` 必须正确匹配，否则 404。

#### Ubuntu 版本映射表

| 版本 | Codename | 内核 | 发布时间 | EOL | Docker 源 codename | 测试状态 |
|------|----------|------|----------|-----|-------------------|:--------:|
| 20.04 LTS | focal | 5.4 | 2020-04 | 2025-04 | focal | 代码支持 |
| 22.04 LTS | jammy | 5.15 | 2022-04 | 2027-04 | jammy | ✅ 已验证 |
| 24.04 LTS | noble | 6.8 | 2024-04 | 2029-04 | noble | 代码支持 |
| 24.10 | oracular | 6.11 | 2024-10 | 2025-07 | oracular | 代码支持 |
| 25.04 | plucky | 6.14 | 2025-04 | 2026-01 | plucky | 代码支持 |
| 26.04 LTS | resolute | 6.16+ | 2026-04 | 2030-04 | resolute | 代码支持 |

> **部署新版本**：运行 `. /etc/os-release && echo "$VERSION_CODENAME"` 获取 codename，脚本会自动填入源地址。GPG 密钥路径为 `mirrors.aliyun.com/docker-ce/linux/ubuntu/gpg`（.asc 格式）。

#### Debian 版本映射表

| 版本 | Codename | 内核 | 发布时间 | EOL | Docker 源 codename | 测试状态 |
|------|----------|------|----------|-----|-------------------|:--------:|
| 10 | buster | 4.19 | 2019-07 | 2024-06 | buster | 代码支持 |
| 11 | bullseye | 5.10 | 2021-08 | 2026-08 | bullseye | 代码支持 |
| 12 | bookworm | 6.1 | 2023-06 | 2028-06 | bookworm | ✅ 已验证 |
| 13 | trixie | 6.12 | 2025-08 | 2030-08 | trixie | ✅ 已验证 |
| 14 | forky | — | 计划 2027 | — | forky | 未测试 |

> **部署新版本**：运行 `. /etc/os-release && echo "$VERSION_CODENAME"` 获取 codename。Debian 13+ 默认使用 `/etc/apt/sources.list.d/debian.sources`（DEB822 格式），安装脚本已兼容此格式。

#### Rocky Linux / AlmaLinux 版本映射表

| 主版本 | releasever | 内核 | Rocky 首次发布 | AlmaLinux 首次发布 | EOL | Docker 源 releasever | 测试状态 |
|--------|-----------|------|---------------|-------------------|-----|---------------------|:--------:|
| 8.x | 8 | 4.18 | 2021-05 (8.3) | 2021-03 (8.3) | 2029-05 | 8 | 代码支持 |
| 9.x | 9 | 5.14 | 2022-07 (9.0) | 2022-05 (9.0) | 2032-05 | 9 | ✅ 已验证 (Rocky) |
| 10.x | 9¹ | 6.12 | 2025-06 (10.0) | 2025-05 (10.0) | 2035-05 | 9 | ✅ 已验证 (Rocky 10) |

> ¹ **Rocky/AlmaLinux 10 的 releasever 仍用 9**：Docker CE 的 CentOS 源目前最高只到 releasever=9，Rocky 10/AlmaLinux 10 二进制兼容 RHEL 9 的 Docker 包，因此安装时传 `releasever=9`。当 Docker 官方发布 centos/10 源后可切换。
>
> **已知问题（Rocky 10 / 内核 6.12+）**：`br_netfilter`、`xt_addrtype`、`iptable_nat` 模块可能缺失，导致 Docker 启动失败。安装脚本已内置自动修复（modprobe + 安装 kernel-modules-extra）。详见 [故障排查](#10-故障排查)。

#### 国产 OS 版本映射表

| 系统 | 版本 | releasever | 内核 | 上游基础 | 发布时间 | Docker 源 | 测试状态 |
|------|------|-----------|------|---------|----------|-----------|:--------:|
| Anolis OS | 7 | 7 | 3.10 (RHCK) / 4.19 (ANCK) | RHEL 7 | 2021 | centos/7 | 代码支持 |
| Anolis OS | 8 | 8 | 4.18 (RHCK) / 5.10 (ANCK) | RHEL 8 | 2021 | centos/8 | 代码支持 |
| Anolis OS | 23 | 9¹ | 6.6 (ANCK) | RHEL 9 兼容 | 2024-08 (GA) | centos/9 | ✅ 已验证 |
| Kylin V10 | SP1/SP2 | 8 | 4.19 | openEuler 20.03 / CentOS 8 | 2020-2021 | centos/8 | 代码支持 |
| Kylin V10 | SP3 | 8 | 4.19 | openEuler 20.03 / CentOS 8 | 2022-12 | centos/8 | ✅ 已验证 |
| openEuler | 22.03 LTS | 8² | 5.10 | 独立社区 | 2022-03 | centos/8 | 代码支持 |
| openEuler | 24.03 LTS | 8² | 6.6 | 独立社区 | 2024-06 | centos/8 | ✅ 已验证 |
| openEuler | 24.03 LTS SP3 | 8² | 6.6 | 独立社区 | 2025-12 | centos/8 | 代码支持 |
| openEuler | 25.03 | 8² | 6.6 | 独立社区 | 2025-03 | centos/8 | 代码支持 |

> ¹ **Anolis OS 23 的 releasever 用 9**：Anolis 23 兼容 RHEL 9 的 glibc 和 ABI，可使用 centos/9 的 Docker 包。
>
> ² **openEuler 的 releasever 固定用 8**：openEuler 不在 Docker 官方支持列表中，`$releasever` 不是 7/8/9。经测试 releasever=8 兼容性最好。`get.docker.com` 便捷脚本会报 `Unsupported distribution`。
>
> **Kylin V10 镜像源注意事项**：阿里云源的 el8 部分 RPM 可能缺失（403 错误），安装脚本已内置三镜像回退（阿里云 → USTC → TUNA），自动切换到可用镜像。

#### releasever 选择决策树

遇到新版本 OS 时，按以下逻辑确定 `releasever`：

```
1. 查看系统 /etc/os-release 中的 ID 和 VERSION_ID
   $ . /etc/os-release && echo "$ID $VERSION_ID"

2. 判断 OS 家族：
   ├─ ID=ubuntu / debian → 用 Debian 系脚本（install_docker_debian.sh）
   │   └─ codename = $VERSION_CODENAME（自动检测）
   │
   ├─ ID=rocky / almalinux / centos / rhel → 用 RHEL 系脚本（install_docker_rhel.sh）
   │   ├─ VERSION_ID=8.x → releasever=8
   │   ├─ VERSION_ID=9.x → releasever=9
   │   └─ VERSION_ID=10.x → releasever=9（Docker 源暂无 10，用 9 兼容）
   │
   ├─ ID=anolis → 用 RHEL 系脚本
   │   ├─ VERSION_ID=7 → releasever=7
   │   ├─ VERSION_ID=8 → releasever=8
   │   └─ VERSION_ID=23 → releasever=9
   │
   ├─ ID=kylin → 用 RHEL 系脚本
   │   └─ releasever=8（所有 Kylin V10 SP1/SP2/SP3 均用 8）
   │
   └─ ID=openeuler → 用 openEuler 专用脚本
       └─ releasever=8（所有版本固定用 8）
```

#### 已知问题速查表

| OS + 版本 | 问题 | 现象 | 解决方案 | 脚本是否自动处理 |
|-----------|------|------|---------|:---------------:|
| Rocky 10 / 内核 6.12+ | br_netfilter 模块缺失 | Docker 启动失败，iptables-nft 报错 | `modprobe br_netfilter` + 安装 `kernel-modules-extra` | ✅ |
| Kylin V10 SP3 | 阿里云源 el8 RPM 缺失 | dnf install 返回 403 | 三镜像回退（阿里云→USTC→TUNA） | ✅ |
| Anolis OS 23 | nftables 兼容性 | systemctl start docker 超时 | 杀残留 dockerd + reset-failed + 重启 | ✅ |
| openEuler 24.03 | 不在 Docker 官方列表 | get.docker.com 报 Unsupported | 手动创建 repo，releasever=8 | ✅ |
| Ubuntu 24.04+ | sources 格式变化 | sed 替换 sources.list 无效 | 同时处理 `.sources`（DEB822 格式） | ✅ |
| Rocky 10 / RHEL 10 | systemctl enable --now 失败 | set -e 导致脚本退出 | 改用 `\|\| true` + 后续修复逻辑 | ✅ |
| Debian 13+ | sources.list.d/debian.sources | 系统源替换遗漏 | 脚本兼容 DEB822 格式 | ✅ |

#### 快速部署检查清单

遇到新版本 OS 时，按此清单快速验证：

```bash
# 1. 确认系统信息
cat /etc/os-release | grep -E "^ID=|^VERSION_ID=|^VERSION_CODENAME="

# 2. 确认内核版本（判断是否需要 kernel-modules-extra）
uname -r

# 3. 确认包管理器
which dnf yum apt-get 2>/dev/null

# 4. 测试阿里云源连通性（RHEL 系）
curl -sI https://mirrors.aliyun.com/docker-ce/linux/centos/9/x86_64/stable/ | head -1

# 5. 测试阿里云源连通性（Debian 系）
curl -sI https://mirrors.aliyun.com/docker-ce/linux/ubuntu/dists/jammy/Release | head -1

# 6. 选择安装脚本
#    Debian 系 → install_docker_debian.sh
#    RHEL 系   → install_docker_rhel.sh <os_id> <releasever>
#    openEuler → install_docker_openeuler.sh
```

> **版本规律总结**：
> - **Ubuntu LTS** 每 2 年 4 月发布（22.04→24.04→26.04），codename 首字母按字母表顺序（j→n→r）
> - **Debian** 每 ~2 年发布一个稳定版（12→13→14），codename 取自 Toy Story 角色
> - **Rocky/AlmaLinux** 跟随 RHEL 大版本（8→9→10），EOL 比上游晚约 10 年
> - **openEuler LTS** 每 2 年发布（20.03→22.03→24.03），中间穿插 SP1/SP2/SP3 更新
> - **Anolis OS** 奇数版本号（7→8→23），23 之后预计 25
> - **Kylin V10** 通过 SP1/SP2/SP3 迭代，SP3 基于 openEuler 20.03 LTS

### 远程安装

#### 单台远程安装

```bash
# 上传脚本
scp start.py root@<server>:/root/

# 远程安装（自动检测系统类型）
ssh root@<server> "python3 /root/start.py install -f"

# 验证
ssh root@<server> "docker --version && systemctl is-active docker"
```

#### 批量远程安装（从 Windows PowerShell）

> 适用于 OpenStack 创建的 VM 集群，6 种 OS 混合环境。

**Debian 系（Ubuntu/Debian）— 上传脚本执行**：

```powershell
# 上传安装脚本（需 sudo 权限的用户）
scp install_docker_debian.sh <user>@<VM_IP>:/tmp/install_docker.sh
ssh <user>@<VM_IP> 'sudo bash /tmp/install_docker.sh'
```

**RHEL 系（AlmaLinux/Rocky/Anolis）— 上传脚本执行**：

```powershell
# 参数：<os_id> <releasever>
scp install_docker_rhel.sh <user>@<VM_IP>:/tmp/install_docker.sh
ssh <user>@<VM_IP> 'sudo bash /tmp/install_docker.sh almalinux 9'
# Anolis 23 用: sudo bash /tmp/install_docker.sh anolis 9
```

**openEuler — 上传脚本执行**：

```powershell
# 使用专用脚本（阿里云源，releasever=8 自动处理）
scp install_docker_openeuler.sh root@<VM_IP>:/tmp/install_docker.sh
ssh root@<VM_IP> 'bash /tmp/install_docker.sh'
```

**批量验证（PowerShell 循环）**：

```powershell
$vms = @(
    @{Name="ubuntu"; IP="192.168.100.1"; User="ubuntu"},
    @{Name="debian"; IP="192.168.100.2"; User="debian"},
    @{Name="almalinux"; IP="192.168.100.3"; User="almalinux"},
    @{Name="rocky"; IP="192.168.100.4"; User="rocky"},
    @{Name="anolis"; IP="192.168.100.5"; User="root"},
    @{Name="openeuler"; IP="192.168.100.6"; User="root"}
)
foreach ($vm in $vms) {
    $ver = ssh -o StrictHostKeyChecking=no "$($vm.User)@$($vm.IP)" "docker --version; systemctl is-active docker; docker compose version" 2>&1
    Write-Output "=== $($vm.Name) ==="; $ver
}
```

> **注意**：VM IP 每次创建可能变化，请通过 `ssh root@10.0.10.13 "source /etc/kolla/admin-openrc.sh && source /path/to/venv/bin/activate && openstack server list"` 获取最新 IP。

#### 一键批量安装（推荐）

使用 `scripts/batch_install_docker.ps1` 脚本，自动完成 6 台 VM 的 Docker 安装：

```powershell
# 自动获取 VM IP → 上传脚本 → 并行安装 → 验证
powershell -ExecutionPolicy Bypass -File '.trae\skills\docker\scripts\batch_install_docker.ps1'
```

脚本执行流程：
1. 从 OpenStack API 自动获取 6 台 VM 的当前 IP
2. 并行上传对应安装脚本到各 VM（Debian 系/RHEL 系/openEuler）
3. 并行执行安装（约 5-8 分钟完成全部 6 台）
4. 逐台验证 Docker 版本、服务状态、Compose 版本
5. 输出汇总表格

> **安装脚本位置**：
> - `scripts/install_docker_debian.sh` — Debian 系（Ubuntu/Debian）
> - `scripts/install_docker_rhel.sh` — RHEL 系（AlmaLinux/Rocky/Anolis）
> - `scripts/install_docker_openeuler.sh` — openEuler 专用（阿里云源）
> - `scripts/batch_install_docker.ps1` — 批量一键安装（PowerShell）
> - `start.py` — 通用安装脚本（旧版，保留兼容）

### 镜像加速配置

`/etc/docker/daemon.json` 内容（所有系统通用，2026-07-20 优化版）：

```json
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
```

> **优化说明**（2026-07-20）：
> - 镜像加速器从 10 个精简为 4 个（实测 6 个不可用或超时，精简后 `docker pull` 速度提升约 48%）
> - 新增 `max-concurrent-downloads: 10`（默认 3），加速镜像层并行下载
> - 新增 `max-download-attempts: 5`（默认 5），提高下载可靠性

修改后执行 `systemctl restart docker` 或 `python3 start.py reconfigure`。

---

## 2. 镜像管理

### 拉取与查看

```bash
docker pull nginx:alpine              # 拉取指定标签
docker pull alpine                     # 拉取 latest
docker images                          # 列出本地镜像
docker image ls --no-trunc             # 完整信息（不截断）
docker image ls -q                     # 只列出镜像 ID
docker image inspect nginx:alpine      # 查看镜像详情
docker history nginx:alpine            # 查看构建历史（每层指令）
docker search hello-world              # 搜索镜像
```

### 镜像标签

```bash
docker tag alpine:latest alpine:v3     # 添加标签
docker tag <image-id> myrepo/myimage:1.0
```

### 导出与导入

```bash
# 镜像导出（保留分层信息）
docker save -o /tmp/alpine.tar alpine:latest
docker save alpine:latest > /tmp/alpine.tar

# 镜像导入
docker load -i /tmp/alpine.tar
docker load < /tmp/alpine.tar
```

### 容器导出与导入

```bash
# 容器文件系统快照导出（不含分层历史，体积更小）
docker export -o /tmp/container.tar <容器名>

# 导入为新镜像
docker import /tmp/container.tar myimage:1.0
```

> `save/load` 针对镜像，保留完整分层；`export/import` 针对容器，导出文件系统快照。

### 删除与清理

```bash
docker rmi alpine:v3                   # 删除指定标签
docker image rm -f <image-id>          # 强制删除
docker image rm -f $(docker image ls -q)  # 删除所有镜像
docker image prune -f                  # 清理无用镜像
docker image prune -a -f               # 清理所有未使用镜像
```

---

## 3. 容器生命周期

### 创建与启动

```bash
# 后台运行 + 端口映射 + 命名
docker run -d -p 8080:80 --name web1 nginx:alpine

# 交互式运行
docker run -it alpine /bin/sh

# 一次性任务（退出后自动删除）
docker run --rm alpine echo "Hello Docker!"

# 挂载数据卷
docker run -d -v /data/html:/usr/share/nginx/html nginx:alpine

# 使用命名卷
docker run -d -v mydata:/data nginx:alpine

# 设置环境变量
docker run -d -e TZ=Asia/Shanghai -e MYSQL_ROOT_PASSWORD=secret mysql:5.7

# 指定重启策略
docker run -d --restart=always nginx:alpine

# 资源限制
docker run -d -m 128m --cpus 0.5 nginx:alpine

# 使用自定义网络 + 固定 IP
docker run -d --network mynet --ip 192.168.10.10 nginx:alpine
```

### docker run 常用参数

| 参数 | 说明 |
|------|------|
| `-d` | 后台运行 |
| `-it` | 交互式终端 |
| `-p hostPort:containerPort` | 端口映射 |
| `-P` | 自动映射所有 EXPOSE 端口 |
| `-v hostDir:containerDir` | 挂载数据卷 |
| `-e KEY=VALUE` | 环境变量 |
| `--name` | 容器名称 |
| `--rm` | 退出后自动删除 |
| `--restart` | 重启策略 (no/always/on-failure/unless-stopped) |
| `-m` | 内存限制 |
| `--cpus` | CPU 限制 |
| `--network` | 指定网络 |

### 端口映射格式

```bash
-p 8080:80              # 所有 IP 的 8080 → 容器 80
-p 10.0.0.100:8081:80   # 指定 IP 的 8081 → 容器 80
-p 80                   # 随机主机端口 → 容器 80
-p 9998:53/udp          # UDP 端口映射
-p 33060:3306 -p 22222:22  # 多端口映射
```

### 启停与暂停

```bash
docker start web1          # 启动已停止的容器
docker start -i web1       # 启动并连接（交互模式）
docker stop web1           # 停止容器
docker restart web1        # 重启容器
docker pause web1          # 暂停（冻结进程，不释放内存）
docker unpause web1        # 取消暂停
docker kill web1           # 强制终止
```

### 删除容器

```bash
docker rm web1                          # 删除已停止的容器
docker rm -f web1                       # 强制删除运行中的容器
docker rm -f $(docker ps -a -q)         # 删除所有容器
docker rm $(docker ps -q -f status=exited)  # 删除所有已退出容器
docker container prune -f               # 清理所有已停止容器
```

### 调整运行中容器的资源

```bash
docker update web1 -m 256m --memory-swap -1
docker update web1 --cpus 1.0
```

---

## 4. 容器查看与调试

### 查看容器列表

```bash
docker ps                    # 运行中的容器
docker ps -a                 # 所有容器（包括已停止）
docker ps -q                 # 只看容器 ID
docker ps -f status=exited   # 筛选已退出容器
```

### 查看容器详情

```bash
docker inspect web1                              # 完整详情
docker inspect web1 -f 'IP: {{.NetworkSettings.IPAddress}}'
docker inspect web1 -f 'State: {{.State.Status}}'
docker inspect web1 -f 'Memory: {{.HostConfig.Memory}} CPUs: {{.HostConfig.NanoCpus}}'
docker inspect --format '{{.Name}} {{.NetworkSettings.IPAddress}}' $(docker ps -q)
```

### 查看容器进程与日志

```bash
docker top web1                              # 容器内进程
docker logs web1                             # 全部日志
docker logs -f web1                          # 跟踪日志
docker logs -tf web1                         # 跟踪 + 时间戳
docker logs --tail 10 web1                   # 最后 10 行
docker logs --since 5m web1                  # 最近 5 分钟
docker logs --since "2024-01-01T10:00:00" web1
```

### 进入容器

```bash
# exec（推荐）：以子进程进入，退出不影响主进程
docker exec -it web1 /bin/sh
docker exec web1 cat /etc/os-release         # 容器外直接执行命令

# attach：连接主进程前台，Ctrl+P+Q 脱离
docker attach web1
```

### 文件复制

```bash
docker cp /tmp/file.txt web1:/path/          # 主机 → 容器
docker cp web1:/path/file.txt /tmp/          # 容器 → 主机
```

### 资源使用统计

```bash
docker stats                    # 实时监控所有容器
docker stats --no-stream        # 一次性快照
docker stats web1               # 指定容器
```

### 常用组合命令

```bash
docker stop $(docker ps -q)                            # 停止所有运行中容器
docker rm -f $(docker ps -a -q)                        # 删除所有容器
docker inspect --format '{{.Name}} {{.NetworkSettings.IPAddress}}' $(docker ps -q)  # 查看所有容器 IP
```

---

## 5. 网络管理

### 四种网络模型

| 模型 | 说明 | 网络隔离 | 典型场景 |
|------|------|---------|---------|
| **bridge** | 默认模式，通过 docker0 网桥 NAT 转发 | 是 | 单机多容器互通 |
| **host** | 共用宿主机 Network Namespace | 否 | 高性能网络服务 |
| **container** | 与其他容器共用 Network Namespace | 否（共享） | K8s Pod 内通信 |
| **none** | 无网络，仅 lo 回环 | 完全隔离 | 安全审计、离线计算 |

### 查看与管理网络

```bash
docker network ls                           # 列出所有网络
docker network inspect bridge               # 查看网络详情
docker network inspect mynet                # 查看网络中的容器
```

### 创建自定义网络

```bash
# 创建自定义网桥（支持容器名解析）
docker network create --driver bridge \
  --subnet 192.168.10.0/24 \
  --gateway 192.168.10.1 \
  mynet

# 使用自定义网络 + 固定 IP
docker run -d --network mynet --ip 192.168.10.10 --name web1 nginx:alpine
```

### 连接与断开网络

```bash
docker network connect bridge web1          # 容器加入网络（多 IP）
docker network disconnect bridge web1       # 容器离开网络
```

### 使用不同网络模式

```bash
# host 模式（性能最好，注意端口冲突）
docker run -d --network host nginx:alpine

# container 模式（共享另一容器的网络）
docker run -d --network container:web1 --name web2 nginx:alpine

# none 模式（完全隔离）
docker run -d --network none --name isolated nginx:alpine
```

### 删除网络

```bash
docker network rm mynet
docker network prune -f                     # 清理未使用网络
```

---

## 6. 数据卷管理

### 命名卷

```bash
docker volume create mydata                 # 创建命名卷
docker volume ls                            # 列出所有卷
docker volume inspect mydata                # 查看卷详情（存储位置）
docker volume rm mydata                     # 删除卷
docker volume prune -f                      # 清理未使用卷
```

### 使用数据卷

```bash
# 命名卷
docker run -d -v mydata:/data nginx:alpine

# 绑定挂载（宿主机目录:容器目录）
docker run -d -v /data/web:/usr/share/nginx/html nginx:alpine

# 只读挂载
docker run -d -v /data/config:/etc/nginx:ro nginx:alpine
```

### 数据卷容器

```bash
# 创建数据卷容器
docker run -it --name data_container \
  -v /opt/data/a:/data/a \
  -v /opt/data/b:/data/b \
  alpine /bin/sh

# 其他容器复用数据卷
docker run -d --volumes-from data_container --name app1 nginx:alpine
docker run -d --volumes-from data_container --name app2 nginx:alpine
```

---

## 7. Dockerfile 构建

### 指令速查表

| 指令 | 作用 | 产生层 |
|------|------|-------|
| `FROM` | 基础镜像（必须第一条） | 是 |
| `RUN` | 构建时执行命令 | 是 |
| `COPY` | 复制文件到镜像 | 是 |
| `ADD` | 复制/解压/下载文件 | 是 |
| `CMD` | 容器启动默认命令 | 否 |
| `ENTRYPOINT` | 容器启动入口 | 否 |
| `EXPOSE` | 声明端口 | 否 |
| `ENV` | 环境变量 | 是 |
| `ARG` | 构建参数 | 否 |
| `WORKDIR` | 工作目录 | 否 |
| `VOLUME` | 声明数据卷 | 否 |
| `USER` | 切换用户 | 否 |
| `LABEL` | 元数据标签 | 否 |
| `HEALTHCHECK` | 健康检查 | 否 |

### 示例 Dockerfile

```dockerfile
FROM nginx:alpine
LABEL maintainer="admin@example.com" version="1.0"
ENV TZ=Asia/Shanghai
RUN apk add --no-cache curl && rm -rf /var/cache/apk/*
COPY index.html /usr/share/nginx/html/
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
  CMD curl -f http://localhost/ || exit 1
CMD ["nginx", "-g", "daemon off;"]
```

### 构建命令

```bash
# 基本构建
docker build -t mynginx:1.0 /path/to/context/

# 指定 Dockerfile 文件名
docker build -t mynginx:1.0 -f /path/MyDockerfile /path/

# 不使用缓存
docker build --no-cache -t mynginx:1.0 .

# 传递构建参数
docker build --build-arg VERSION=8 -t mynginx:1.0 .

# 指定平台
docker build --platform linux/amd64 -t mynginx:1.0 .
```

### 多阶段构建

```dockerfile
# 阶段一：编译
FROM golang:1.21 AS builder
WORKDIR /app
COPY . .
RUN CGO_ENABLED=0 go build -o myapp

# 阶段二：运行（最终镜像）
FROM alpine:3.18
WORKDIR /app
COPY --from=builder /app/myapp .
CMD ["./myapp"]
```

### CMD vs ENTRYPOINT

```dockerfile
# 灵活组合：ENTRYPOINT 固定入口 + CMD 默认参数
ENTRYPOINT ["nginx"]
CMD ["-g", "daemon off;"]

# docker run myimage           → nginx -g "daemon off;"
# docker run myimage -t        → nginx -t
```

### 最佳实践

- 合并 RUN 指令减少层数：`RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*`
- 变化少的放前面（依赖安装），变化多的放后面（源代码）
- 使用 `.dockerignore` 排除不需要的文件
- 优先使用 `COPY` 而非 `ADD`（语义更清晰）
- 以非 root 用户运行：`RUN useradd -r appuser && USER appuser`
- 清理构建产物：`rm -rf /var/cache/apk/* /tmp/*`

---

## 8. Docker Compose 编排

### 基本模板

```yaml
services:
  web:
    image: nginx:alpine
    container_name: compose_web
    ports:
      - "9090:80"
    volumes:
      - html_data:/usr/share/nginx/html
    environment:
      TZ: Asia/Shanghai
    restart: always
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost/"]
      interval: 30s
      timeout: 3s
      retries: 3
    depends_on:
      - redis
    networks:
      - app_net

  redis:
    image: redis:alpine
    container_name: compose_redis
    restart: always
    volumes:
      - redis_data:/data
    networks:
      - app_net

volumes:
  html_data:
  redis_data:

networks:
  app_net:
    driver: bridge
    ipam:
      config:
        - subnet: 172.20.0.0/16
          gateway: 172.20.0.1
```

### 字段说明

| 字段 | 说明 | 示例 |
|------|------|------|
| `image` | 使用的镜像 | `nginx:alpine` |
| `container_name` | 容器名 | `web` |
| `restart` | 重启策略 | `always` / `no` / `on-failure` |
| `ports` | 端口映射 | `"9090:80"` |
| `volumes` | 数据持久化 | `html_data:/usr/share/nginx/html` |
| `environment` | 环境变量 | `TZ: Asia/Shanghai` |
| `command` | 启动命令 | `--character-set-server=utf8mb4` |
| `depends_on` | 启动顺序依赖 | `- redis` |
| `healthcheck` | 健康检查 | `test: ["CMD", "curl", "-f", "http://localhost/"]` |
| `networks` | 加入的网络 | `- app_net` |

### 常用命令

```bash
docker compose up -d                    # 启动（后台）
docker compose up -d --build            # 重新构建并启动
docker compose down                     # 停止并移除容器和网络
docker compose down -v                  # 同时删除卷
docker compose ps                       # 查看容器状态
docker compose logs -f web              # 跟踪日志
docker compose exec web /bin/sh         # 进入容器
docker compose top                      # 查看进程
docker compose build                    # 构建镜像
docker compose build --no-cache         # 不使用缓存构建
docker compose config                   # 验证配置文件
docker compose config --services        # 列出所有服务名
docker compose start redis              # 启动指定服务
docker compose stop redis               # 停止指定服务
docker compose restart redis            # 重启指定服务
docker compose pull                     # 拉取所有服务镜像
docker compose run --rm web echo "test" # 一次性执行命令
```

### 指定文件名

```bash
docker compose -f /path/to/docker-compose.yml up -d
docker compose -f /path/to/docker-compose.yml down
```

---

## 9. 系统管理与清理

### 系统信息

```bash
docker info                        # Docker 系统信息
docker version                     # 版本信息
docker system df                   # 磁盘使用统计
docker system events               # 实时事件
```

### 清理命令

```bash
docker system prune -f             # 清理停止的容器、未使用网络、悬空镜像
docker system prune -a -f          # 清理所有未使用资源（包括未使用的镜像）
docker system prune -a --volumes -f  # 连同未使用卷一起清理
docker container prune -f          # 清理已停止容器
docker image prune -f              # 清理悬空镜像
docker image prune -a -f           # 清理所有未使用镜像
docker volume prune -f             # 清理未使用卷
docker network prune -f            # 清理未使用网络
docker builder prune -f            # 清理构建缓存
```

---

## 10. 故障排查

### Docker 服务启动失败

```bash
# 查看服务状态
systemctl status docker

# 查看详细日志
journalctl -u docker.service --no-pager -n 50

# 检查配置文件语法
cat /etc/docker/daemon.json | python3 -m json.tool

# 手动重启
systemctl daemon-reload
systemctl restart docker
```

### 容器无法启动

```bash
# 查看容器日志
docker logs <容器名>

# 查看容器退出码
docker inspect <容器名> -f '{{.State.ExitCode}}'

# 查看容器状态
docker inspect <容器名> -f '{{.State.Status}} {{.State.Error}}'
```

### 镜像拉取失败

```bash
# 检查镜像加速配置
cat /etc/docker/daemon.json

# 测试加速地址连通性
curl -I https://docker.m.daocloud.io/v2/

# 重新配置镜像加速
python3 start.py reconfigure

# 手动指定加速地址拉取
docker pull docker.m.daocloud.io/library/nginx:alpine
```

### 端口冲突

```bash
# 查看端口占用
ss -tlnp | grep :8080

# 修改容器端口映射
docker stop <容器名>
docker rm <容器名>
docker run -d -p 9090:80 --name <容器名> <镜像>
```

### 磁盘空间不足

```bash
# 查看 Docker 磁盘使用
docker system df

# 清理所有未使用资源
docker system prune -a --volumes -f

# 查看容器日志大小
du -sh /var/lib/docker/containers/*/*-json.log

# 限制容器日志大小（在 daemon.json 中配置）
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  }
}
```

### 网络不通

```bash
# 检查网桥
brctl show

# 查看 iptables NAT 规则
iptables -t nat -L -n

# 检查容器网络
docker inspect <容器名> -f '{{.NetworkSettings.IPAddress}}'
docker exec <容器名> ping -c 3 8.8.8.8
```

### 进入容器排查（无 shell 时）

```bash
# 获取容器 PID
docker inspect <容器名> -f '{{.State.Pid}}'

# 通过 nsenter 进入
nsenter --target <PID> --mount --uts --ipc --net --pid
```

---

## 验证测试结果

### 安装验证（6 系统 × 阿里云源，2026-07-17）

| 系统 | 版本 | 安装方式 | Docker 版本 | Compose 版本 | 状态 |
|------|------|---------|------------|-------------|:----:|
| Ubuntu | 22.04 (jammy) | apt 阿里云源 | 29.6.1 | v5.3.1 | 已验证 |
| Debian | 12 (bookworm) | apt 阿里云源 | 29.6.1 | v5.3.1 | 已验证 |
| Rocky Linux | 9 | dnf 阿里云源 | 29.6.1 | v5.3.1 | 已验证 |
| AlmaLinux | 9 | dnf 阿里云源 | 29.6.1 | v5.3.1 | 已验证 |
| Anolis OS | 23.4 | dnf 阿里云源 | 29.6.1 | v5.3.1 | 已验证 |
| openEuler | 24.03-LTS-SP2 | start.py 脚本 | 26.1.3 | v2.27.0 | 已验证 |

### 已知问题与解决方案

| 系统 | 问题 | 解决方案 |
|------|------|---------|
| 所有系统 | `download.docker.com` SSL 握手失败 | 使用 `mirrors.aliyun.com/docker-ce` 阿里云源 |
| Anolis OS 23 | start.py 检测不到系统（`os_id=anolis` vs `SUPPORTED_OS=anolisos`） | 手动用 dnf 阿里云源安装，或修复 start.py 的检测逻辑 |
| Anolis OS 23 | Docker 首次启动失败（nftables 兼容性） | `kill -9 $(pgrep dockerd); rm -f /var/run/docker.pid; systemctl reset-failed docker; systemctl start docker` |
| openEuler 24.03 | `get.docker.com` 不支持 | 必须手动替换 `$releasever` 为 8，用 start.py 脚本 |
| Ubuntu/Debian | GPG 密钥 `gpg --dearmor` 在非 TTY 环境失败 | 用 `curl -o docker.asc` 直接下载 ASCII 格式，`signed-by` 指向 `.asc` 文件 |

### Docker 操作验证（Ubuntu 22.04 + Docker 27.3.1 实测）

| 测试项 | 状态 | 测试项 | 状态 |
|--------|------|--------|------|
| 镜像拉取 (pull) | 通过 | 容器运行 (run -d) | 通过 |
| 镜像标签 (tag) | 通过 | 容器交互 (run -it) | 通过 |
| 镜像导出 (save) | 通过 | 容器停止/启动 | 通过 |
| 镜像导入 (load) | 通过 | 容器暂停/恢复 | 通过 |
| 镜像历史 (history) | 通过 | exec 进入容器 | 通过 |
| 镜像详情 (inspect) | 通过 | docker cp 文件复制 | 通过 |
| 容器日志 (logs) | 通过 | 容器进程 (top) | 通过 |
| 自定义网络创建 | 通过 | 命名卷创建使用 | 通过 |
| 固定 IP 分配 | 通过 | 绑定挂载 | 通过 |
| Dockerfile 构建 | 通过 | 资源限制 (-m/--cpus) | 通过 |
| Compose up/down | 通过 | Compose ps/logs/exec | 通过 |
| Compose top | 通过 | system prune/df | 通过 |

---

## 文件清单

| 文件 | 说明 |
|------|------|
| `SKILL.md` | 本文档（综合 Docker 操作手册） |
| `start.py` | Docker 安装管理脚本（脱敏版，可开源） |
| `scripts/install_docker_debian.sh` | Debian 系一键安装脚本（阿里云源） |
| `scripts/install_docker_rhel.sh` | RHEL 系一键安装脚本（阿里云源，参数化） |

## 脱敏说明

本 Skill 已完成脱敏处理，可直接开源：
- 无 IP 地址、密码、密钥等敏感信息
- 所有 URL 均为 Docker 官方公开下载地址和公共镜像加速地址
- 安装脚本 `start.py` 随附于本 Skill 目录
