#!/usr/bin/env python3
"""
在每台 VM 上缓存 Docker 安装包到 /opt/docker-pkgs/
下次安装时直接从本地安装，无需网络下载
用法: python cache_docker_packages.py
"""
import paramiko
import re
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

SSH_KEY = os.path.expanduser('~/.ssh/id_rsa')

# 各 OS 的包缓存命令
CACHE_CMDS = {
    'debian': (
        'mkdir -p /opt/docker-pkgs && cd /opt/docker-pkgs && '
        'apt-get update -qq 2>/dev/null; '
        'apt-get download docker-ce docker-ce-cli containerd.io '
        'docker-buildx-plugin docker-compose-plugin 2>&1; '
        'echo "=== cached files ==="; ls -lh /opt/docker-pkgs/*.deb 2>/dev/null | wc -l; '
        'du -sh /opt/docker-pkgs/; echo CACHE_DONE'
    ),
    'rhel': (
        'mkdir -p /opt/docker-pkgs && cd /opt/docker-pkgs && '
        'dnf install -y dnf-plugins-core 2>/dev/null; '
        'dnf download --downloaddir=/opt/docker-pkgs '
        'docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin 2>&1; '
        'echo "=== cached files ==="; ls -l /opt/docker-pkgs/*.rpm 2>/dev/null | wc -l; '
        'du -sh /opt/docker-pkgs/; echo CACHE_DONE'
    ),
    'openeuler': (
        'mkdir -p /opt/docker-pkgs && cd /opt/docker-pkgs && '
        'yum install -y yum-utils 2>/dev/null; '
        'yumdownloader --destdir=/opt/docker-pkgs '
        'docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin 2>&1; '
        'echo "=== cached files ==="; ls -l /opt/docker-pkgs/*.rpm 2>/dev/null | wc -l; '
        'du -sh /opt/docker-pkgs/; echo CACHE_DONE'
    ),
}

def detect_os_family(ssh):
    stdin, stdout, stderr = ssh.exec_command('. /etc/os-release && echo "$ID"', timeout=10)
    os_id = stdout.read().decode().strip().lower()
    if os_id in ('ubuntu', 'debian'):
        return 'debian'
    elif os_id in ('rocky', 'almalinux', 'centos', 'rhel', 'anolis', 'kylin'):
        return 'rhel'
    elif os_id == 'openeuler':
        return 'openeuler'
    return None

def get_vm_list():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect('10.0.0.200', username='root', key_filename=SSH_KEY, timeout=10)
    cmd = ('source /etc/kolla/admin-openrc.sh && source /path/to/venv/bin/activate '
           '&& openstack server list -f value -c Name -c Status -c Networks')
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=30)
    output = stdout.read().decode('utf-8', errors='replace')
    ssh.close()
    vms = {}
    for line in output.strip().split('\n'):
        if not line.strip():
            continue
        parts = line.split(None, 2)
        if len(parts) < 3:
            continue
        name, status, networks = parts[0], parts[1], parts[2]
        if status != 'ACTIVE':
            continue
        ip_match = re.search(r'192\.168\.9\.\d+', networks)
        if ip_match:
            vms[name] = ip_match.group()
    return vms

def cache_on_vm(name, ip):
    ssh = None
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(ip, username='root', key_filename=SSH_KEY, timeout=10)
        family = detect_os_family(ssh)
        if not family:
            return name, ip, False, 'Unknown OS'
        cmd = CACHE_CMDS[family]
        stdin, stdout, stderr = ssh.exec_command(cmd, timeout=120)
        out = stdout.read().decode('utf-8', errors='replace')
        ok = 'CACHE_DONE' in out
        # 提取缓存信息
        lines = [l.strip() for l in out.split('\n') if l.strip()]
        detail = ''
        for l in lines:
            if 'cached files' in l or '/opt/docker-pkgs' in l:
                detail = l
                break
        return name, ip, ok, detail
    except Exception as e:
        return name, ip, False, str(e)
    finally:
        if ssh:
            ssh.close()

GREEN = '\033[92m'
RED = '\033[91m'
CYAN = '\033[96m'
RESET = '\033[0m'

def main():
    print(f"\n{CYAN}{'='*60}")
    print(f"  缓存 Docker 安装包到各 VM 本地（/opt/docker-pkgs/）")
    print(f"{'='*60}{RESET}\n")

    print(f"{CYAN}获取 VM 列表{RESET}")
    vms = get_vm_list()
    if not vms:
        print(f"  {RED}未找到 ACTIVE VM{RESET}")
        return
    for name, ip in sorted(vms.items()):
        print(f"  {name:20s} {ip}")
    print(f"  共 {len(vms)} 台\n")

    print(f"{CYAN}并行缓存安装包（{len(vms)} 台同时）{RESET}")
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(cache_on_vm, name, ip): name for name, ip in vms.items()}
        for f in as_completed(futures):
            name, ip, ok, detail = f.result()
            color = GREEN if ok else RED
            print(f"  {color}{name:20s} {ip:16s} {'缓存成功' if ok else '失败'}  {detail}{RESET}")

    print(f"\n{CYAN}{'='*60}")
    print(f"  缓存完成，包路径: /opt/docker-pkgs/")
    print(f"{'='*60}{RESET}")

if __name__ == '__main__':
    main()
