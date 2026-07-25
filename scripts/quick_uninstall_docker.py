#!/usr/bin/env python3
"""
一键并行卸载 Docker（paramiko 版）
用法: python quick_uninstall_docker.py
自动: 获取 VM 列表 → 检测 OS → 并行卸载 → 验证清除
"""
import paramiko
import re
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

SSH_KEY = os.path.expanduser('~/.ssh/id_rsa')

# 卸载命令
UNINSTALL_CMDS = {
    'debian': (
        'systemctl stop docker containerd 2>/dev/null; '
        'apt-get purge -y docker-ce docker-ce-cli containerd.io '
        'docker-buildx-plugin docker-compose-plugin docker-ce-rootless-extras 2>/dev/null; '
        'apt-get autoremove -y 2>/dev/null; '
        'rm -rf /var/lib/docker /var/lib/containerd /etc/docker '
        '/etc/apt/sources.list.d/docker.list /etc/apt/keyrings/docker.asc; '
        'echo UNINSTALL_DONE'
    ),
    'rhel': (
        'systemctl stop docker containerd 2>/dev/null; '
        'dnf remove -y docker-ce docker-ce-cli containerd.io '
        'docker-buildx-plugin docker-compose-plugin 2>/dev/null; '
        'rm -rf /var/lib/docker /var/lib/containerd /etc/docker /etc/yum.repos.d/docker-ce.repo; '
        'echo UNINSTALL_DONE'
    ),
    'openeuler': (
        'systemctl stop docker containerd 2>/dev/null; '
        'yum remove -y docker-ce docker-ce-cli containerd.io '
        'docker-buildx-plugin docker-compose-plugin 2>/dev/null; '
        'rm -rf /var/lib/docker /var/lib/containerd /etc/docker /etc/yum.repos.d/docker-ce.repo; '
        'echo UNINSTALL_DONE'
    ),
}

def detect_os_family(ssh):
    stdin, stdout, stderr = ssh.exec_command(
        '. /etc/os-release && echo "$ID"', timeout=10)
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

def uninstall_on_vm(name, ip):
    ssh = None
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(ip, username='root', key_filename=SSH_KEY, timeout=10)
        family = detect_os_family(ssh)
        if not family:
            return name, ip, False, 'Unknown OS'
        cmd = UNINSTALL_CMDS[family]
        stdin, stdout, stderr = ssh.exec_command(cmd, timeout=120)
        out = stdout.read().decode('utf-8', errors='replace')
        ok = 'UNINSTALL_DONE' in out
        return name, ip, ok, out.strip().split('\n')[-1] if out else 'no output'
    except Exception as e:
        return name, ip, False, str(e)
    finally:
        if ssh:
            ssh.close()

def verify_vm(name, ip):
    ssh = None
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(ip, username='root', key_filename=SSH_KEY, timeout=10)
        stdin, stdout, stderr = ssh.exec_command(
            'which docker 2>/dev/null; systemctl is-active docker 2>/dev/null; echo EXIT=$?',
            timeout=10)
        out = stdout.read().decode('utf-8', errors='replace')
        has_docker = '/bin/docker' in out or '/usr/bin/docker' in out
        return name, ip, '已清除' if not has_docker else '仍存在'
    except Exception as e:
        return name, ip, f'ERR:{e}'
    finally:
        if ssh:
            ssh.close()

GREEN = '\033[92m'
RED = '\033[91m'
CYAN = '\033[96m'
RESET = '\033[0m'

def main():
    print(f"\n{CYAN}{'='*60}")
    print(f"  Docker 一键并行卸载（paramiko 版）")
    print(f"{'='*60}{RESET}\n")

    print(f"{CYAN}[1/3] 获取 VM 列表{RESET}")
    vms = get_vm_list()
    if not vms:
        print(f"  {RED}未找到 ACTIVE VM{RESET}")
        return
    for name, ip in sorted(vms.items()):
        print(f"  {name:20s} {ip}")
    print(f"  共 {len(vms)} 台\n")

    print(f"{CYAN}[2/3] 并行卸载 Docker（{len(vms)} 台同时）{RESET}")
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(uninstall_on_vm, name, ip): name for name, ip in vms.items()}
        for f in as_completed(futures):
            name, ip, ok, detail = f.result()
            color = GREEN if ok else RED
            print(f"  {color}{name:20s} {ip:16s} {'已卸载' if ok else '失败'}{RESET}")

    time.sleep(2)
    print(f"\n{CYAN}[3/3] 验证卸载结果{RESET}")
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(verify_vm, name, ip): name for name, ip in vms.items()}
        for f in as_completed(futures):
            name, ip, status = f.result()
            color = GREEN if status == '已清除' else RED
            print(f"  {color}{name:20s} {ip:16s} Docker {status}{RESET}")

    print(f"\n{CYAN}{'='*60}")
    print(f"  卸载完成")
    print(f"{'='*60}{RESET}")

if __name__ == '__main__':
    main()
