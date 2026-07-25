#!/usr/bin/env python3
"""
一键并行安装 Docker 到 OpenStack VM（paramiko 版）
用法: python quick_install_docker.py
自动: 获取 VM 列表 → 检测 OS → SFTP 上传脚本 → 并行安装 → 验证
单连接复用：一个 SSH 连接完成全部操作，无 shell 转义问题
"""
import paramiko
import re
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SSH_KEY = os.path.expanduser('~/.ssh/id_rsa')

# ============================================================
# SSH 连接管理
# ============================================================

class VMConnection:
    """单台 VM 的 SSH 连接，复用连接完成全部操作"""

    def __init__(self, name, ip):
        self.name = name
        self.ip = ip
        self.ssh = None
        self.sftp = None

    def connect(self):
        self.ssh = paramiko.SSHClient()
        self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.ssh.connect(self.ip, username='root', key_filename=SSH_KEY, timeout=10)
        self.sftp = self.ssh.open_sftp()
        return self

    def exec_cmd(self, cmd, timeout=300):
        """执行命令，返回 (returncode, stdout+stderr)"""
        stdin, stdout, stderr = self.ssh.exec_command(cmd, timeout=timeout)
        out = stdout.read().decode('utf-8', errors='replace')
        err = stderr.read().decode('utf-8', errors='replace')
        return stdout.channel.recv_exit_status(), out + err

    def upload_and_run(self, local_script, args='', timeout=300):
        """SFTP 上传脚本并执行"""
        remote_path = '/tmp/install_docker.sh'
        self.sftp.put(local_script, remote_path)
        cmd = f'bash {remote_path} {args}' if args else f'bash {remote_path}'
        rc, out = self.exec_cmd(cmd, timeout=timeout)
        return rc, out

    def close(self):
        if self.sftp:
            self.sftp.close()
        if self.ssh:
            self.ssh.close()


# ============================================================
# OS 检测
# ============================================================

def detect_os(conn):
    """检测 OS，返回 (family, distro, releasever, script_file, args)"""
    rc, out = conn.exec_cmd('. /etc/os-release && echo "$ID $VERSION_ID"', timeout=10)
    parts = out.strip().split()
    if len(parts) < 2:
        return None, None, None, None, None

    os_id = parts[0].lower()
    version_id = parts[1]

    if os_id in ('ubuntu', 'debian'):
        return 'debian', os_id, None, \
               os.path.join(SCRIPT_DIR, 'install_docker_debian.sh'), ''
    elif os_id in ('rocky', 'almalinux', 'centos', 'rhel'):
        major = int(version_id.split('.')[0])
        releasever = '9' if major >= 9 else '8'
        return 'rhel', os_id, releasever, \
               os.path.join(SCRIPT_DIR, 'install_docker_rhel.sh'), \
               f'{os_id} {releasever}'
    elif os_id == 'anolis':
        releasever = '9' if version_id.startswith('23') else version_id.split('.')[0]
        return 'rhel', os_id, releasever, \
               os.path.join(SCRIPT_DIR, 'install_docker_rhel.sh'), \
               f'{os_id} {releasever}'
    elif os_id == 'kylin':
        return 'rhel', os_id, '8', \
               os.path.join(SCRIPT_DIR, 'install_docker_rhel.sh'), \
               f'{os_id} 8'
    elif os_id == 'openeuler':
        return 'openeuler', os_id, None, \
               os.path.join(SCRIPT_DIR, 'install_docker_openeuler.sh'), ''
    return None, None, None, None, None


# ============================================================
# 获取 VM 列表
# ============================================================

def get_vm_list():
    """从 OpenStack 获取 ACTIVE VM 列表"""
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


# ============================================================
# 单台 VM 安装流程
# ============================================================

def install_on_vm(name, ip):
    """完整流程：连接 → 检测OS → 上传脚本 → 安装 → 返回结果"""
    conn = None
    try:
        conn = VMConnection(name, ip).connect()

        # 检测 OS
        family, distro, releasever, script_file, args = detect_os(conn)
        if not family:
            return name, ip, False, 'Unknown OS'

        # 上传并执行
        rc, out = conn.upload_and_run(script_file, args, timeout=300)
        ok = 'DOCKER_INSTALL_OK' in out
        detail = out.strip().split('\n')[-1] if out else 'no output'
        return name, ip, ok, detail

    except Exception as e:
        return name, ip, False, str(e)
    finally:
        if conn:
            conn.close()


def verify_vm(name, ip):
    """验证 Docker 安装"""
    conn = None
    try:
        conn = VMConnection(name, ip).connect()
        rc, out = conn.exec_cmd(
            'docker --version 2>/dev/null; '
            'systemctl is-active docker 2>/dev/null; '
            'docker run --rm hello-world 2>&1 | grep "Hello from Docker"',
            timeout=60
        )
        lines = [l.strip() for l in out.split('\n') if l.strip() and 'Warning:' not in l]
        ver = lines[0] if len(lines) >= 1 else 'N/A'
        active = lines[1] if len(lines) >= 2 else 'N/A'
        hello = lines[2] if len(lines) >= 3 else 'N/A'
        ok = active == 'active' and 'Hello' in hello
        return name, ip, ver, active, 'OK' if ok else 'FAIL'
    except Exception as e:
        return name, ip, 'N/A', 'N/A', f'ERR:{e}'
    finally:
        if conn:
            conn.close()


# ============================================================
# 主流程
# ============================================================

GREEN = '\033[92m'
RED = '\033[91m'
CYAN = '\033[96m'
RESET = '\033[0m'

def main():
    print(f"\n{CYAN}{'='*60}")
    print(f"  Docker 一键并行安装（paramiko 版）")
    print(f"{'='*60}{RESET}\n")

    # Step 1: 获取 VM 列表
    print(f"{CYAN}[1/3] 获取 VM 列表{RESET}")
    vms = get_vm_list()
    if not vms:
        print(f"  {RED}未找到 ACTIVE VM{RESET}")
        return
    for name, ip in sorted(vms.items()):
        print(f"  {name:20s} {ip}")
    print(f"  共 {len(vms)} 台\n")

    # Step 2: 并行安装
    print(f"{CYAN}[2/3] 并行安装 Docker（{len(vms)} 台同时）{RESET}")
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(install_on_vm, name, ip): name for name, ip in vms.items()}
        results = []
        for f in as_completed(futures):
            name, ip, ok, detail = f.result()
            results.append((name, ip, ok))
            color = GREEN if ok else RED
            print(f"  {color}{name:20s} {ip:16s} {'PASS' if ok else 'FAIL'}{RESET}  {detail}")
    print()

    # 等待 Docker 服务完全启动
    time.sleep(3)

    # Step 3: 验证
    print(f"{CYAN}[3/3] 验证 Docker（hello-world）{RESET}")
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(verify_vm, name, ip): name for name, ip in vms.items()}
        for f in as_completed(futures):
            name, ip, ver, active, hello = f.result()
            color = GREEN if hello == 'OK' else RED
            print(f"  {color}{name:20s} {ip:16s} {ver:35s} {active:8s} hello: {hello}{RESET}")

    # 总结
    ok_count = sum(1 for _, _, ok in results if ok)
    verify_ok = 0
    print(f"\n{CYAN}{'='*60}")
    print(f"  安装: {ok_count}/{len(vms)} 成功")
    print(f"{'='*60}{RESET}")

if __name__ == '__main__':
    main()
