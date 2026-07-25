#!/usr/bin/env python3
"""
Docker 批量安装工具 - 跨平台 (macOS / Windows)
================================================
零第三方依赖，通过 SSH 向多台 Linux VM 批量安装 Docker CE。

功能:
  - 自动从 OpenStack 获取 VM 列表（或手动指定）
  - 自动检测每台 VM 的 OS 类型
  - 自动选择对应的安装脚本（Debian 系 / RHEL 系 / openEuler）
  - 并行上传 + 安装（默认 3 并发）
  - 安装后自动验证（版本、服务状态、Compose）
  - 支持跳过已安装的 VM
  - 处理 Kylin/Rocky 10 等新版本 OS 的源兼容性

用法示例:
  python3 docker_batch_installer.py                    # 自动获取 VM 并安装
  python3 docker_batch_installer.py --vm 192.168.100.10 # 只装指定 VM
  python3 docker_batch_installer.py --force            # 强制重装
  python3 docker_batch_installer.py --workers 6        # 6 并发
  python3 docker_batch_installer.py --verify-only      # 仅验证不安装

前置条件:
  1. macOS 或 Windows 10+（自带 OpenSSH）
  2. Python 3.8+
  3. 已配好 SSH 密钥登录到所有 VM
  4. docker Skill 目录中有安装脚本

作者: Docker Skill  |  更新: 2026-07-20
"""

import subprocess
import sys
import os
import time
import json
import argparse
import platform
from concurrent.futures import ThreadPoolExecutor, as_completed

# ============================================================
#  配置区
# ============================================================

CONFIG = {
    # OpenStack 节点（用于自动获取 VM 列表）
    "NODE_IP": "10.0.0.200",
    "NODE_USER": "root",
    "ADMIN_OPENRC": "/etc/kolla/admin-openrc.sh",
    "VENV_ACTIVATE": "/path/to/venv/bin/activate",

    # SSH 配置
    "SSH_USER": "root",
    "SSH_KEY": None,  # None=自动检测 ~/.ssh/id_rsa

    # Docker Skill 安装脚本路径
    "SCRIPTS_DIR": None,  # None=自动检测

    # 安装参数
    "MAX_WORKERS": 3,           # 并发数
    "INSTALL_TIMEOUT": 600,     # 单台安装超时（秒）
    "VERIFY_TIMEOUT": 30,       # 验证超时（秒）

    # VM 密码（密钥失败时回退，需 expect）
    "VM_PASSWORD": "Cloud@2026",
}


# ============================================================
#  OS → 安装脚本映射
# ============================================================

# 每种 OS 的安装配置:
#   script:          使用的安装脚本文件名
#   args:            脚本参数（列表）
#   family:          OS 家族 (debian/rhel/openeuler)
#   fallback_mirror: 阿里云源失败时回退的镜像 (ustc/tuna)
#   needs_kernel_fix: 是否需要安装额外内核模块 (Rocky 10 等)
#   direct_install:  是否跳过 shell 脚本直接用 SSH 命令安装（需特殊镜像源时）
OS_INSTALL_CONFIG = {
    # Debian 系
    "ubuntu": {
        "script": "install_docker_debian.sh",
        "args": [],  # 自动检测 codename
        "family": "debian",
    },
    "debian": {
        "script": "install_docker_debian.sh",
        "args": [],  # 自动检测 codename
        "family": "debian",
    },
    # RHEL 系
    "rocky": {
        "script": "install_docker_rhel.sh",
        "args": ["rocky", "9"],  # Rocky 9/10 都用 9（向后兼容）
        "family": "rhel",
        "needs_kernel_fix": True,  # Rocky 10 内核 6.12 缺 br_netfilter/xt_addrtype
    },
    "anolis": {
        "script": "install_docker_rhel.sh",
        "args": ["anolis", "9"],
        "family": "rhel",
    },
    "kylin": {
        "script": "install_docker_rhel.sh",
        "args": ["kylin", "8"],  # Kylin V10 基于 CentOS 8
        "family": "rhel",
        "fallback_mirror": "ustc",  # 阿里云源缺失 el8 部分 RPM，回退到 USTC
    },
    "centos": {
        "script": "install_docker_rhel.sh",
        "args": ["centos", "8"],
        "family": "rhel",
    },
    "almalinux": {
        "script": "install_docker_rhel.sh",
        "args": ["almalinux", "9"],
        "family": "rhel",
    },
    # openEuler 专用
    "openeuler": {
        "script": "install_docker_openeuler.sh",
        "args": [],
        "family": "openeuler",
    },
}

# 镜像源配置（阿里云源缺失部分 el8 包时的回退）
MIRROR_URLS = {
    "aliyun": "https://mirrors.aliyun.com/docker-ce/linux/centos",
    "ustc":   "https://mirrors.ustc.edu.cn/docker-ce/linux/centos",
    "tuna":   "https://mirrors.tuna.tsinghua.edu.cn/docker-ce/linux/centos",
}


# ============================================================
#  工具函数
# ============================================================

def get_ssh_key_path():
    """获取本机 SSH 私钥路径"""
    if CONFIG["SSH_KEY"]:
        return CONFIG["SSH_KEY"]
    return os.path.expanduser(os.path.join("~", ".ssh", "id_rsa"))


def get_scripts_dir():
    """获取 docker Skill 安装脚本目录"""
    if CONFIG["SCRIPTS_DIR"]:
        return CONFIG["SCRIPTS_DIR"]
    # 自动检测
    candidates = [
        os.path.expanduser("~/Desktop/obsidian/.trae/skills/docker/scripts"),
        os.path.expanduser("~/.trae/skills/docker/scripts"),
        r"C:\obsidian\.trae\skills\docker\scripts",
        r"C:\Users\admin\.trae\skills\docker\scripts",
    ]
    for path in candidates:
        if os.path.isdir(path):
            return path
    # 默认返回 macOS 路径
    return os.path.expanduser("~/Desktop/obsidian/.trae/skills/docker/scripts")


def run_local(cmd, timeout=30):
    """执行本地命令"""
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def ssh_exec(host, cmd, timeout=120, ssh_user=None):
    """通过 SSH 在远程主机执行命令"""
    if ssh_user is None:
        ssh_user = CONFIG["SSH_USER"]
    key_path = get_ssh_key_path()

    ssh_args = [
        "ssh",
        "-o", "StrictHostKeyChecking=no",
        "-o", "ConnectTimeout=10",
        "-o", "UserKnownHostsFile=/dev/null",
        "-o", "BatchMode=yes",
    ]
    if os.path.exists(key_path):
        ssh_args += ["-i", key_path]

    ssh_args.append(f"{ssh_user}@{host}")
    ssh_args.append(cmd)

    result = subprocess.run(ssh_args, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        raise RuntimeError(f"SSH failed: {result.stderr.strip()}")
    return result.stdout.strip()


def scp_upload(host, local_path, remote_path, timeout=60, ssh_user=None):
    """通过 SCP 上传文件"""
    if ssh_user is None:
        ssh_user = CONFIG["SSH_USER"]
    key_path = get_ssh_key_path()

    scp_args = [
        "scp", "-o", "StrictHostKeyChecking=no",
        "-o", "ConnectTimeout=10",
        "-o", "UserKnownHostsFile=/dev/null",
        "-o", "BatchMode=yes",
    ]
    if os.path.exists(key_path):
        scp_args += ["-i", key_path]

    scp_args.append(local_path)
    scp_args.append(f"{ssh_user}@{host}:{remote_path}")

    result = subprocess.run(scp_args, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        raise RuntimeError(f"SCP failed: {result.stderr.strip()}")
    return True


def get_vm_list_from_openstack():
    """从 OpenStack 获取 VM 列表，返回 [(name, ip, status), ...]"""
    ssh_args = [
        "ssh", "-o", "StrictHostKeyChecking=no", "-o", "BatchMode=yes",
        "-o", "UserKnownHostsFile=/dev/null",
        "-i", get_ssh_key_path(),
        f"{CONFIG['NODE_USER']}@{CONFIG['NODE_IP']}",
        f"source {CONFIG['ADMIN_OPENRC']} && source {CONFIG['VENV_ACTIVATE']} && "
        f"openstack server list --all-projects -f json -c Name -c Status -c Networks"
    ]
    result = subprocess.run(ssh_args, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise RuntimeError(f"获取 VM 列表失败: {result.stderr.strip()}")

    data = json.loads(result.stdout)
    vms = []
    for vm in data:
        name = vm.get("Name", "")
        status = vm.get("Status", "")
        networks = vm.get("Networks", {})
        # 提取 IP
        ip = ""
        if isinstance(networks, dict):
            for net, ips in networks.items():
                if isinstance(ips, list) and ips:
                    ip = ips[0]
                    break
                elif isinstance(ips, str):
                    ip = ips
                    break
        elif isinstance(networks, str):
            ip = networks.split("=")[-1].strip() if "=" in networks else networks
        if status == "ACTIVE" and ip:
            vms.append((name, ip, status))
    return vms


def detect_os(host):
    """检测远程主机的 OS 类型，返回 os_id (小写)"""
    cmd = ". /etc/os-release && echo \"$ID\""
    out = ssh_exec(host, cmd, timeout=10)
    os_id = out.strip().lower()
    return os_id


def verify_docker(host):
    """验证 Docker 安装状态，返回 dict"""
    try:
        out = ssh_exec(host, "docker --version 2>/dev/null; "
                             "echo '---'; "
                             "systemctl is-active docker 2>/dev/null; "
                             "echo '---'; "
                             "docker compose version 2>/dev/null",
                       timeout=15)
        parts = out.split("---")
        docker_ver = parts[0].strip() if len(parts) > 0 else ""
        service_status = parts[1].strip() if len(parts) > 1 else ""
        compose_ver = parts[2].strip() if len(parts) > 2 else ""

        return {
            "installed": bool(docker_ver),
            "docker_version": docker_ver,
            "service_active": service_status == "active",
            "compose_version": compose_ver,
        }
    except RuntimeError as e:
        return {
            "installed": False,
            "docker_version": "",
            "service_active": False,
            "compose_version": "",
            "error": str(e),
        }


# ============================================================
#  OS 特殊修复函数
# ============================================================

# daemon.json 内容（所有系统通用，2026-07-20 优化版）
DAEMON_JSON = """{
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
}"""


def fix_kernel_modules(host):
    """
    Rocky 10 / RHEL 10 修复: 安装缺失的内核模块。
    
    问题: Rocky 10 内核 6.12 的 kernel-modules-core 不含 br_netfilter、
    xt_addrtype、iptable_nat，导致 Docker 启动时 iptables-nft 报错:
      "Extension addrtype revision 0 not supported, missing kernel module?"
    
    修复: 安装 kernel-modules + kernel-modules-extra（含上述模块），
    modprobe 加载，并写入 modules-load.d 实现开机自动加载。
    """
    print(f"    [内核模块修复] 检查 br_netfilter/xt_addrtype/iptable_nat...")
    try:
        out = ssh_exec(host, "lsmod | grep -E 'br_netfilter|xt_addrtype'", timeout=10)
        if out.strip():
            print(f"    [内核模块修复] 模块已加载，跳过")
            return True
    except RuntimeError:
        pass

    # 检查 modprobe 是否可用
    try:
        out = ssh_exec(host, "modprobe br_netfilter 2>&1", timeout=10)
        if "FATAL" not in out and "not found" not in out:
            print(f"    [内核模块修复] modprobe 成功，加载其余模块...")
            ssh_exec(host, "modprobe xt_addrtype && modprobe iptable_nat", timeout=10)
            ssh_exec(host,
                     "printf 'br_netfilter\\nxt_addrtype\\niptable_nat\\n' "
                     "> /etc/modules-load.d/docker-netfilter.conf", timeout=10)
            return True
    except RuntimeError:
        pass

    # 需要安装 kernel-modules + kernel-modules-extra
    print(f"    [内核模块修复] 安装 kernel-modules + kernel-modules-extra...")
    try:
        kernel_ver = ssh_exec(host, "uname -r", timeout=10).strip()
        ssh_exec(host,
                 f"dnf install -y kernel-modules-{kernel_ver} "
                 f"kernel-modules-extra-{kernel_ver}",
                 timeout=180)
        print(f"    [内核模块修复] 加载模块...")
        ssh_exec(host,
                 "modprobe br_netfilter && modprobe xt_addrtype && modprobe iptable_nat",
                 timeout=10)
        ssh_exec(host,
                 "printf 'br_netfilter\\nxt_addrtype\\niptable_nat\\n' "
                 "> /etc/modules-load.d/docker-netfilter.conf",
                 timeout=10)
        print(f"    [内核模块修复] ✓ 完成")
        return True
    except RuntimeError as e:
        print(f"    [内核模块修复] ✗ 失败: {e}")
        return False


def install_docker_with_mirror(host, releasever, mirror_name):
    """
    使用指定镜像源直接安装 Docker（不依赖 shell 脚本）。
    用于阿里云源缺失包时回退到 USTC 等镜像。
    """
    mirror_base = MIRROR_URLS.get(mirror_name, MIRROR_URLS["ustc"])
    print(f"    [镜像回退] 使用 {mirror_name} 镜像 (releasever={releasever})...")

    # 1. 创建 repo 文件
    repo_content = (
        f"[docker-ce-stable]\n"
        f"name=Docker CE Stable - $basearch\n"
        f"baseurl={mirror_base}/{releasever}/$basearch/stable\n"
        f"enabled=1\n"
        f"gpgcheck=1\n"
        f"gpgkey={mirror_base}/gpg\n"
    )
    # 用 printf 写入避免 shell 转义问题
    import shlex
    ssh_exec(host,
             f"printf '%s\\n' {shlex.quote(repo_content)} > /etc/yum.repos.d/docker-ce.repo",
             timeout=10)

    # 2. 清理缓存 + 卸载冲突包
    ssh_exec(host,
             "dnf clean all && "
             "dnf remove -y podman podman-docker docker docker-engine 2>/dev/null || true",
             timeout=30)

    # 3. 安装 Docker
    print(f"    [镜像回退] dnf install docker-ce...")
    ssh_exec(host,
             "dnf install -y docker-ce docker-ce-cli containerd.io "
             "docker-buildx-plugin docker-compose-plugin",
             timeout=300)

    # 4. 配置 daemon.json
    import shlex
    ssh_exec(host,
             f"mkdir -p /etc/docker && printf '%s\\n' {shlex.quote(DAEMON_JSON)} > /etc/docker/daemon.json",
             timeout=10)

    # 5. 启动
    ssh_exec(host, "systemctl enable --now docker", timeout=30)
    print(f"    [镜像回退] ✓ 安装完成")
    return True


# ============================================================
#  安装逻辑
# ============================================================

def install_docker_on_vm(name, ip, force=False):
    """
    在单个 VM 上安装 Docker。
    返回 (success, message, details)
    """
    print(f"\n[{name}] 开始处理 ({ip})")

    # 1. 检测 OS
    try:
        os_id = detect_os(ip)
        print(f"  OS: {os_id}")
    except RuntimeError as e:
        return False, f"OS 检测失败: {e}", {}

    # 2. 检查是否已安装
    if not force:
        status = verify_docker(ip)
        if status["installed"] and status["service_active"]:
            print(f"  ✓ Docker 已安装且运行中: {status['docker_version']}")
            return True, "已安装（跳过）", status
        elif status["installed"]:
            print(f"  Docker 已安装但服务未运行，尝试重启...")
            try:
                ssh_exec(ip, "systemctl restart docker && sleep 3 && "
                             "systemctl is-active docker", timeout=30)
                status = verify_docker(ip)
                if status["service_active"]:
                    return True, "已安装（重启后恢复）", status
            except RuntimeError:
                pass
            print(f"  重启失败，继续重装...")

    # 3. 获取安装脚本配置
    os_config = OS_INSTALL_CONFIG.get(os_id)
    if not os_config:
        return False, f"不支持的 OS: {os_id}", {}

    script_name = os_config["script"]
    script_args = os_config["args"]
    scripts_dir = get_scripts_dir()
    local_script = os.path.join(scripts_dir, script_name)

    if not os.path.exists(local_script):
        return False, f"安装脚本不存在: {local_script}", {}

    # 4. 上传脚本
    print(f"  上传 {script_name}...")
    remote_script = f"/tmp/install_docker_{os_id}.sh"
    try:
        scp_upload(ip, local_script, remote_script, timeout=30)
    except RuntimeError as e:
        return False, f"上传脚本失败: {e}", {}

    # 5. 执行安装
    args_str = " ".join(script_args)
    install_cmd = f"bash {remote_script} {args_str}"
    print(f"  执行安装 (timeout={CONFIG['INSTALL_TIMEOUT']}s)...")

    install_failed = False
    fail_output_tail = ""

    try:
        output = ssh_exec(ip, install_cmd, timeout=CONFIG["INSTALL_TIMEOUT"])
        success = "DOCKER_INSTALL_OK" in output
        # 提取关键信息
        lines = output.strip().split("\n")
        docker_ver = ""
        compose_ver = ""
        for line in lines:
            if "Docker version" in line or line.startswith("Docker version"):
                docker_ver = line.strip()
            if "Docker Compose version" in line or "compose" in line.lower():
                compose_ver = line.strip()

        if success:
            print(f"  ✓ 安装成功: {docker_ver}")
        else:
            # 安装脚本未返回成功标志
            tail = "\n".join(lines[-10:])
            print(f"  ✗ 安装脚本未返回成功标志")

            # 检查是否是镜像源下载失败（403/No more mirrors）
            if "403" in output or "No more mirrors" in output or "Cannot download" in output:
                fallback_mirror = os_config.get("fallback_mirror")
                if fallback_mirror:
                    print(f"  ⚠ 检测到镜像下载失败，回退到 {fallback_mirror} 镜像...")
                    releasever = script_args[1] if len(script_args) > 1 else "8"
                    try:
                        install_docker_with_mirror(ip, releasever, fallback_mirror)
                        install_failed = False
                    except RuntimeError as e:
                        print(f"  ✗ 镜像回退也失败: {e}")
                        return False, f"镜像回退安装失败: {e}", {"output_tail": tail}
                else:
                    print(f"  最后输出:\n{tail}")
                    return False, "安装脚本未返回成功标志", {"output_tail": tail}
            else:
                print(f"  最后输出:\n{tail}")
                return False, "安装脚本未返回成功标志", {"output_tail": tail}

    except subprocess.TimeoutExpired:
        return False, f"安装超时 ({CONFIG['INSTALL_TIMEOUT']}s)", {}
    except RuntimeError as e:
        return False, f"安装失败: {e}", {}

    # 6. 验证
    print(f"  验证安装...")
    time.sleep(3)  # 等待服务稳定
    status = verify_docker(ip)
    if status["installed"] and status["service_active"]:
        print(f"  ✓ 验证通过: {status['docker_version']}")
        return True, "安装成功", status

    # 7. OS 特殊修复
    # 7a. Rocky 10 / RHEL 10: 内核模块缺失修复
    if os_config.get("needs_kernel_fix"):
        print(f"  ⚠ Docker 未运行，尝试内核模块修复...")
        if fix_kernel_modules(ip):
            try:
                ssh_exec(ip, "systemctl restart docker && sleep 3 && "
                             "systemctl is-active docker", timeout=30)
                status = verify_docker(ip)
                if status["service_active"]:
                    print(f"  ✓ 内核模块修复成功: {status['docker_version']}")
                    return True, "安装成功（内核模块修复）", status
            except RuntimeError:
                pass

    # 7b. 通用 nftables 兜底修复
    print(f"  ⚠ 尝试 nftables 兜底...")
    try:
        ssh_exec(ip,
                 "kill -9 $(pgrep dockerd) 2>/dev/null; "
                 "rm -f /var/run/docker.pid; "
                 "systemctl reset-failed docker 2>/dev/null; "
                 "systemctl start docker; sleep 3; "
                 "systemctl is-active docker",
                 timeout=30)
        status = verify_docker(ip)
        if status["service_active"]:
            print(f"  ✓ 兜底修复成功")
            return True, "安装成功（nftables 兜底）", status
    except RuntimeError:
        pass

    return False, "安装后验证失败", status


# ============================================================
#  主流程
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="Docker 批量安装工具 (跨平台 macOS/Windows)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s                        # 自动获取 VM 并安装 Docker
  %(prog)s --vm 192.168.100.10     # 只装指定 VM
  %(prog)s --vm 192.168.100.10,192.168.100.11  # 多台
  %(prog)s --force                # 强制重装（忽略已安装）
  %(prog)s --workers 6            # 6 并发
  %(prog)s --verify-only          # 仅验证不安装
        """
    )
    parser.add_argument("--vm", default=None,
                        help="指定 VM IP（逗号分隔），不指定则从 OpenStack 获取")
    parser.add_argument("--force", action="store_true",
                        help="强制重装，忽略已安装的 VM")
    parser.add_argument("--workers", type=int, default=CONFIG["MAX_WORKERS"],
                        help=f"并发数 (默认: {CONFIG['MAX_WORKERS']})")
    parser.add_argument("--verify-only", action="store_true",
                        help="仅验证 Docker 状态，不安装")
    parser.add_argument("--ssh-key", default=None,
                        help="SSH 私钥路径 (默认: ~/.ssh/id_rsa)")
    args = parser.parse_args()

    if args.ssh_key:
        CONFIG["SSH_KEY"] = args.ssh_key

    print("=" * 60)
    print("  Docker 批量安装工具")
    print("=" * 60)
    print(f"  平台: {platform.system()}")
    print(f"  SSH 密钥: {get_ssh_key_path()}")
    print(f"  脚本目录: {get_scripts_dir()}")
    print(f"  并发数: {args.workers}")

    # 1. 获取 VM 列表
    if args.vm:
        vm_ips = [ip.strip() for ip in args.vm.split(",")]
        # 获取每台 VM 的名称
        vms = []
        for ip in vm_ips:
            try:
                hostname = ssh_exec(ip, "hostname", timeout=10)
                vms.append((hostname, ip, "ACTIVE"))
            except RuntimeError:
                vms.append((f"vm-{ip}", ip, "ACTIVE"))
    else:
        print("\n从 OpenStack 获取 VM 列表...")
        try:
            vms = get_vm_list_from_openstack()
        except RuntimeError as e:
            print(f"✗ {e}")
            print("  请用 --vm 参数手动指定 IP")
            return 1

    if not vms:
        print("✗ 未找到可用的 VM")
        return 1

    print(f"\n  发现 {len(vms)} 台 VM:")
    for name, ip, status in vms:
        print(f"    {name:20s} {ip:18s} {status}")

    # 2. 仅验证模式
    if args.verify_only:
        print("\n" + "=" * 60)
        print("  仅验证模式")
        print("=" * 60)
        results = []
        for name, ip, _ in vms:
            status = verify_docker(ip)
            results.append((name, ip, status))
            installed = "✓" if status["installed"] else "✗"
            active = "✓" if status["service_active"] else "✗"
            print(f"  {name:20s} {ip:18s} Docker:{installed} Active:{active} "
                  f"{status.get('docker_version', '')}")

        # 汇总
        total = len(results)
        installed_count = sum(1 for _, _, s in results if s["installed"])
        active_count = sum(1 for _, _, s in results if s["service_active"])
        print(f"\n  汇总: {installed_count}/{total} 已安装, {active_count}/{total} 运行中")
        return 0

    # 3. 并行安装
    print(f"\n" + "=" * 60)
    print(f"  开始并行安装 (并发: {args.workers})")
    print("=" * 60)

    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        future_to_vm = {
            executor.submit(install_docker_on_vm, name, ip, args.force): (name, ip)
            for name, ip, _ in vms
        }

        for future in as_completed(future_to_vm):
            name, ip = future_to_vm[future]
            try:
                success, message, details = future.result()
                results.append((name, ip, success, message, details))
            except Exception as e:
                results.append((name, ip, False, f"异常: {e}", {}))

    # 4. 输出汇总报告
    print("\n" + "=" * 60)
    print("  安装汇总报告")
    print("=" * 60)

    print(f"\n  {'名称':<20} {'IP':<18} {'状态':<8} {'Docker 版本':<25} {'说明'}")
    print(f"  {'-'*20} {'-'*18} {'-'*8} {'-'*25} {'-'*30}")

    success_count = 0
    for name, ip, success, message, details in sorted(results, key=lambda x: x[0]):
        status = "✓ 成功" if success else "✗ 失败"
        docker_ver = details.get("docker_version", "")[:24] if details else ""
        print(f"  {name:<20} {ip:<18} {status:<8} {docker_ver:<25} {message}")
        if success:
            success_count += 1

    print(f"\n  总计: {success_count}/{len(results)} 成功")

    if success_count < len(results):
        print("\n  失败的 VM:")
        for name, ip, success, message, details in results:
            if not success:
                print(f"    {name} ({ip}): {message}")
                if details and "output_tail" in details:
                    print(f"      输出末尾:\n{details['output_tail']}")

    return 0 if success_count == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
