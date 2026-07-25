#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Docker 管理工具 - 多系统 Docker 安装、卸载和配置
支持系统：Ubuntu / Debian / CentOS / Rocky Linux / Anolis OS / openEuler
Docker 版本：27.3.1
"""

import os
import sys
import subprocess
import json
import shutil
import time
import platform
from pathlib import Path
from typing import List, Tuple, Optional, Dict
from concurrent.futures import ThreadPoolExecutor, as_completed


class Colors:
    """终端颜色输出"""
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    BOLD = '\033[1m'
    END = '\033[0m'


# ============================================================
# 操作系统检测
# ============================================================

class OSDetector:
    """检测操作系统类型和版本"""

    # 支持的系统配置表
    SUPPORTED_OS = {
        "ubuntu": {
            "family": "debian",
            "repo_distro": "ubuntu",
            "versions": {
                "22.04": "jammy",
                "24.04": "noble",
            },
        },
        "debian": {
            "family": "debian",
            "repo_distro": "debian",
            "versions": {
                "11": "bullseye",
                "12": "bookworm",
            },
        },
        "centos": {
            "family": "rhel",
            "repo_distro": "centos",
            "versions": {
                "7": "7",
                "8": "8",
                "9": "9",
            },
        },
        "rocky": {
            "family": "rhel",
            "repo_distro": "centos",
            "versions": {
                "8": "8",
                "9": "9",
            },
        },
        "anolisos": {
            "family": "rhel",
            "repo_distro": "centos",
            "versions": {
                "8": "8",
                "23": "9",
            },
            "force_releasever": True,
        },
        "openeuler": {
            "family": "rhel",
            "repo_distro": "centos",
            "versions": {
                "22.03": "8",
                "24.03": "8",
            },
            "force_releasever": True,
            "force_releasever_value": "8",
        },
    }

    @staticmethod
    def detect() -> Dict:
        """
        检测当前操作系统

        Returns:
            dict: {
                "id": "ubuntu",
                "name": "Ubuntu",
                "version": "22.04",
                "codename": "jammy",
                "family": "debian",
                "arch": "amd64",
                "supported": True,
            }
        """
        info = {
            "id": "unknown",
            "name": "Unknown",
            "version": "",
            "codename": "",
            "family": "",
            "arch": "amd64",
            "supported": False,
        }

        # 检测架构
        machine = platform.machine().lower()
        if machine in ("x86_64", "amd64"):
            info["arch"] = "amd64"
        elif machine in ("aarch64", "arm64"):
            info["arch"] = "arm64"
        else:
            info["arch"] = machine

        # 读取 /etc/os-release
        os_release = {}
        try:
            with open("/etc/os-release") as f:
                for line in f:
                    line = line.strip()
                    if "=" in line:
                        key, _, value = line.partition("=")
                        os_release[key] = value.strip('"')
        except FileNotFoundError:
            return info

        os_id = os_release.get("ID", "").lower()
        os_name = os_release.get("NAME", "Unknown")
        version_id = os_release.get("VERSION_ID", "")
        version_codename = os_release.get("VERSION_CODENAME", "")

        info["id"] = os_id
        info["name"] = os_name
        info["version"] = version_id

        # 匹配支持的系统
        for supported_id, config in OSDetector.SUPPORTED_OS.items():
            if os_id == supported_id or supported_id in os_id:
                info["family"] = config["family"]
                info["repo_distro"] = config.get("repo_distro", supported_id)

                # 查找版本对应的 codename/releasever
                versions = config["versions"]
                for ver, codename in versions.items():
                    if version_id.startswith(ver) or version_id == ver:
                        info["codename"] = codename
                        info["supported"] = True
                        break

                # 如果没精确匹配到版本，尝试取主版本号
                if not info["supported"] and versions:
                    major_ver = version_id.split(".")[0]
                    for ver, codename in versions.items():
                        if major_ver == ver.split(".")[0]:
                            info["codename"] = codename
                            info["supported"] = True
                            break

                # Debian/Ubuntu 用 codename，RHEL 系用 version_id
                if info["family"] == "debian" and version_codename:
                    info["codename"] = version_codename

                break

        return info


# ============================================================
# 日志工具
# ============================================================

def log(message, level="INFO"):
    """输出日志信息"""
    color_map = {
        "INFO": Colors.BLUE,
        "SUCCESS": Colors.GREEN,
        "WARNING": Colors.YELLOW,
        "ERROR": Colors.RED,
        "STEP": Colors.CYAN
    }
    color = color_map.get(level, Colors.WHITE)
    print(f"{color}[{level}] {message}{Colors.END}")


def run_command(command, check=True, shell=False):
    """执行 shell 命令"""
    try:
        if shell:
            result = subprocess.run(command, shell=True, capture_output=True, text=True, check=False)
        else:
            result = subprocess.run(command, capture_output=True, text=True, check=False)
        if check and result.returncode != 0:
            log(f"命令执行失败: {command if shell else ' '.join(command)}", "ERROR")
            if result.stderr:
                log(f"错误: {result.stderr.strip()}", "ERROR")
        return result.returncode, result.stdout, result.stderr
    except Exception as e:
        log(f"执行命令时发生异常: {e}", "ERROR")
        return -1, "", str(e)


def command_exists(cmd):
    """检查命令是否存在"""
    return shutil.which(cmd) is not None


def check_root():
    """检查 root 权限"""
    if os.geteuid() != 0:
        log("请使用 root 权限运行此脚本！", "ERROR")
        log(f"提示: sudo python3 {sys.argv[0]}", "WARNING")
        sys.exit(1)


# ============================================================
# Debian 系安装器 (Ubuntu / Debian)
# ============================================================

class DebianInstaller:
    """Debian 系安装器（Ubuntu / Debian）"""

    DOCKER_VERSION = "27.3.1"
    CONTAINERD_VERSION = "1.7.22"
    BUILDX_VERSION = "0.17.1"
    COMPOSE_VERSION = "2.27.1"

    # 需要卸载的冲突包
    CONFLICT_PACKAGES = [
        "docker.io", "docker-doc", "docker-compose", "docker-compose-v2",
        "podman-docker", "containerd", "runc",
        "docker-ce", "docker-ce-cli", "containerd.io",
        "docker-compose-plugin", "docker-ce-rootless-extras", "docker-buildx-plugin",
    ]

    PODMAN_PACKAGES = [
        "podman", "podman-plugins", "podman-docker", "podman-build", "podman-compose",
    ]

    def __init__(self, os_info):
        self.os_info = os_info
        self.distro = os_info["repo_distro"]  # ubuntu 或 debian
        self.codename = os_info["codename"]   # jammy, noble, bookworm 等
        self.version_id = os_info["version"]  # 22.04, 24.04, 12 等
        self.arch = os_info["arch"]           # amd64, arm64
        self.packages_dir = Path("/var/cache/apt/archives")

    def _get_package_list(self):
        """生成 deb 包列表和下载 URL"""
        v = self.DOCKER_VERSION
        cv = self.CONTAINERD_VERSION
        bx = self.BUILDX_VERSION
        cp = self.COMPOSE_VERSION
        cn = self.codename
        vid = self.version_id
        arch = self.arch

        if self.distro == "ubuntu":
            suffix = f"{v}-1~ubuntu.{vid}~{cn}"
        else:
            suffix = f"{v}-1~debian.{vid}~{cn}"

        packages = [
            (f"containerd.io_{cv}-1_{arch}.deb",
             f"https://download.docker.com/linux/{self.distro}/dists/{cn}/pool/stable/{arch}/containerd.io_{cv}-1_{arch}.deb"),
            (f"docker-ce-cli_{suffix}_{arch}.deb",
             f"https://download.docker.com/linux/{self.distro}/dists/{cn}/pool/stable/{arch}/docker-ce-cli_{suffix}_{arch}.deb"),
            (f"docker-buildx-plugin_{bx}-1~ubuntu.{vid}~{cn}_{arch}.deb" if self.distro == "ubuntu" else f"docker-buildx-plugin_{bx}-1~debian.{vid}~{cn}_{arch}.deb",
             f"https://download.docker.com/linux/{self.distro}/dists/{cn}/pool/stable/{arch}/docker-buildx-plugin_{bx}-1~{self.distro}.{vid}~{cn}_{arch}.deb"),
            (f"docker-ce-rootless-extras_{suffix}_{arch}.deb",
             f"https://download.docker.com/linux/{self.distro}/dists/{cn}/pool/stable/{arch}/docker-ce-rootless-extras_{suffix}_{arch}.deb"),
            (f"docker-ce_{suffix}_{arch}.deb",
             f"https://download.docker.com/linux/{self.distro}/dists/{cn}/pool/stable/{arch}/docker-ce_{suffix}_{arch}.deb"),
            (f"docker-compose-plugin_{cp}-1~ubuntu.{vid}~{cn}_{arch}.deb" if self.distro == "ubuntu" else f"docker-compose-plugin_{cp}-1~debian.{vid}~{cn}_{arch}.deb",
             f"https://download.docker.com/linux/{self.distro}/dists/{cn}/pool/stable/{arch}/docker-compose-plugin_{cp}-1~{self.distro}.{vid}~{cn}_{arch}.deb"),
        ]
        return packages

    def remove_conflicts(self):
        """卸载冲突包和 Podman"""
        log("=" * 60, "STEP")
        log("卸载冲突软件包", "STEP")
        log("=" * 60, "STEP")

        all_packages = self.CONFLICT_PACKAGES + self.PODMAN_PACKAGES
        for pkg in all_packages:
            run_command(["apt-get", "remove", "--purge", "-y", pkg], check=False)

        run_command(["apt-get", "autoremove", "-y"], check=False)
        log("冲突包清理完成", "SUCCESS")

    def install_dependencies(self):
        """安装依赖"""
        log("安装依赖包...", "INFO")
        run_command(["apt-get", "update"], check=False)
        run_command(["apt-get", "install", "-y", "ca-certificates", "curl", "gnupg"], check=False)

    def download_package(self, filename, url, max_retries=10):
        """下载单个 deb 包"""
        filepath = self.packages_dir / filename

        if filepath.exists() and filepath.stat().st_size > 0:
            log(f"包已存在: {filename}", "SUCCESS")
            return True

        download_cmds = [
            ["curl", "-L", "-C", "-", "-o", str(filepath), url, "-s", "-S",
             "--connect-timeout", "30", "--max-time", "600"],
            ["wget", "-c", "-O", str(filepath), url, "-q", "--timeout=30"],
        ]

        for attempt in range(1, max_retries + 1):
            for cmd in download_cmds:
                if command_exists(cmd[0]):
                    rc, _, stderr = run_command(cmd, check=False)
                    if rc == 0 and filepath.exists() and filepath.stat().st_size > 0:
                        return True
                    filepath.unlink(missing_ok=True)

            if attempt < max_retries:
                time.sleep(min(2 ** attempt, 30))

        log(f"下载失败 ({max_retries}次重试后): {filename}", "ERROR")
        return False

    def install_packages(self):
        """下载并安装 Docker deb 包（并行下载）"""
        log("=" * 60, "STEP")
        log("下载 Docker 安装包（并行）", "STEP")
        log("=" * 60, "STEP")

        packages = self._get_package_list()
        self.packages_dir.mkdir(parents=True, exist_ok=True)

        # 并行下载所有包（6 包并行，约 3-4 倍加速）
        failed = []
        total = len(packages)

        def _download_one(args):
            idx, filename, url = args
            return idx, filename, self.download_package(filename, url)

        with ThreadPoolExecutor(max_workers=min(total, 6)) as pool:
            futures = {pool.submit(_download_one, (i, fn, url)): (i, fn)
                       for i, (fn, url) in enumerate(packages, 1)}
            for future in as_completed(futures):
                idx, filename, success = future.result()
                if success:
                    log(f"[{idx}/{total}] 完成: {filename}", "SUCCESS")
                else:
                    log(f"[{idx}/{total}] 失败: {filename}", "ERROR")
                    failed.append(filename)

        if failed:
            log(f"以下 {len(failed)} 个包下载失败: {failed}", "ERROR")
            return False

        log(f"所有包下载完成 ({total}/{total})", "SUCCESS")

        # 按依赖顺序安装所有包
        print()
        log("=" * 60, "STEP")
        log("安装 Docker 包", "STEP")
        log("=" * 60, "STEP")

        failed_installs = []
        for filename, _ in packages:
            filepath = self.packages_dir / filename
            log(f"正在安装: {filename}", "INFO")
            rc, _, stderr = run_command(["dpkg", "-i", str(filepath)], check=False)

            if rc != 0:
                log(f"{filename} 安装失败，尝试修复依赖...", "WARNING")
                run_command(["apt-get", "install", "-f", "-y"], check=False)
                rc, _, _ = run_command(["dpkg", "-i", str(filepath)], check=False)

            if rc == 0:
                log(f"{filename} 安装成功", "SUCCESS")
            else:
                log(f"{filename} 安装失败", "ERROR")
                failed_installs.append(filename)

        if failed_installs:
            log(f"以下包安装失败: {failed_installs}", "ERROR")
            return False

        log("所有包安装完成", "SUCCESS")
        return True

    def remove_docker(self):
        """卸载 Docker"""
        for pkg in self.CONFLICT_PACKAGES:
            run_command(["apt-get", "remove", "--purge", "-y", pkg], check=False)
        run_command(["apt-get", "autoremove", "-y"], check=False)
        log("Docker 卸载完成", "SUCCESS")
        return True

    def get_remove_packages(self):
        return self.CONFLICT_PACKAGES


# ============================================================
# RHEL 系安装器 (CentOS / Rocky / Anolis / openEuler)
# ============================================================

class RhelInstaller:
    """RHEL 系安装器（CentOS / Rocky Linux / Anolis OS / openEuler）"""

    DOCKER_VERSION = "27.3.1"

    # 需要卸载的旧包
    CONFLICT_PACKAGES = [
        "docker", "docker-client", "docker-client-latest", "docker-common",
        "docker-latest", "docker-latest-logrotate", "docker-logrotate",
        "docker-engine", "podman", "runc", "podman-docker",
        "docker-ce", "docker-ce-cli", "containerd.io",
        "docker-compose-plugin", "docker-ce-rootless-extras", "docker-buildx-plugin",
    ]

    def __init__(self, os_info):
        self.os_info = os_info
        self.os_id = os_info["id"]
        self.version = os_info["version"]
        self.releasever = os_info.get("codename", "")  # RHEL 系用版本号作为 releasever
        self.arch = os_info["arch"]

        # 包管理器选择
        if command_exists("dnf"):
            self.pkg_manager = "dnf"
        elif command_exists("yum"):
            self.pkg_manager = "yum"
        else:
            self.pkg_manager = "yum"

        # openEuler 和 Anolis 需要强制指定 releasever
        config = OSDetector.SUPPORTED_OS.get(os_info["id"], {})
        if config.get("force_releasever"):
            forced = config.get("force_releasever_value")
            if forced:
                self.releasever = forced
            elif self.releasever:
                pass  # 已从 versions 表获取
            else:
                self.releasever = "8"  # 默认用 8

    def remove_conflicts(self):
        """卸载冲突包"""
        log("=" * 60, "STEP")
        log("卸载冲突软件包", "STEP")
        log("=" * 60, "STEP")

        for pkg in self.CONFLICT_PACKAGES:
            run_command([self.pkg_manager, "remove", "-y", pkg], check=False)

        log("冲突包清理完成", "SUCCESS")

    def install_dependencies(self):
        """安装依赖"""
        log("安装依赖包...", "INFO")

        if self.pkg_manager == "dnf":
            run_command(["dnf", "install", "-y", "dnf-plugins-core"], check=False)
        else:
            run_command(["yum", "install", "-y", "yum-utils"], check=False)

    def add_repository(self):
        """添加 Docker 官方源"""
        log("添加 Docker 官方源...", "INFO")

        repo_url = "https://download.docker.com/linux/centos/docker-ce.repo"

        if self.pkg_manager == "dnf":
            run_command(["dnf", "config-manager", "--add-repo", repo_url], check=False)
        else:
            run_command(["yum-config-manager", "--add-repo", repo_url], check=False)

        # openEuler 和 Anolis：替换 $releasever
        repo_file = Path("/etc/yum.repos.d/docker-ce.repo")
        if repo_file.exists():
            if self.os_id == "openeuler" or self.os_id == "anolisos":
                log(f"检测到 {self.os_info['name']}，替换 $releasever → {self.releasever}", "INFO")
                run_command(
                    f"sed -i 's/\\$releasever/{self.releasever}/g' {repo_file}",
                    check=False, shell=True
                )

        # 替换为国内镜像（可选，加速下载）
        if repo_file.exists():
            run_command(
                f"sed -i 's|https://download.docker.com|https://mirrors.aliyun.com/docker-ce|g' {repo_file}",
                check=False, shell=True
            )
            log("已替换为阿里云镜像源加速", "INFO")

        log("Docker 源添加完成", "SUCCESS")

    def install_packages(self):
        """通过 yum/dnf 安装 Docker"""
        log("=" * 60, "STEP")
        log("安装 Docker 包", "STEP")
        log("=" * 60, "STEP")

        packages = [
            "docker-ce", "docker-ce-cli", "containerd.io",
            "docker-buildx-plugin", "docker-compose-plugin",
        ]

        # 清除缓存
        run_command([self.pkg_manager, "clean", "all"], check=False)

        # 安装
        install_cmd = [self.pkg_manager, "install", "-y"] + packages
        rc, stdout, stderr = run_command(install_cmd, check=False)

        if rc != 0:
            log("安装失败，尝试不指定依赖安装...", "WARNING")
            if self.pkg_manager == "dnf":
                install_cmd = ["dnf", "install", "-y", "--nobest"] + packages
            else:
                install_cmd = ["yum", "install", "-y", "--skip-broken"] + packages
            rc, stdout, stderr = run_command(install_cmd, check=False)

        if rc == 0:
            log("Docker 包安装完成", "SUCCESS")
            return True
        else:
            log(f"安装失败: {stderr}", "ERROR")
            return False

    def remove_docker(self):
        """卸载 Docker"""
        for pkg in self.CONFLICT_PACKAGES:
            run_command([self.pkg_manager, "remove", "-y", pkg], check=False)
        log("Docker 卸载完成", "SUCCESS")
        return True

    def get_remove_packages(self):
        return self.CONFLICT_PACKAGES


# ============================================================
# Docker 管理器
# ============================================================

class DockerManager:
    """Docker 管理器 - 统一配置、启动、验证"""

    # Docker 镜像加速地址（精简为 4 个最快的，实测其余不可用或超时）
    REGISTRY_MIRRORS = [
        "https://docker.m.daocloud.io",
        "https://docker.1ms.run",
        "https://hub.rat.dev",
        "https://docker.kejilion.pro",
    ]

    def __init__(self):
        check_root()
        self.os_info = OSDetector.detect()
        self.installer = self._create_installer()

    def _create_installer(self):
        """根据操作系统创建安装器"""
        if not self.os_info["supported"]:
            log(f"不支持的操作系统: {self.os_info['name']} {self.os_info['version']}", "ERROR")
            log(f"支持的系统: Ubuntu, Debian, CentOS, Rocky Linux, Anolis OS, openEuler", "WARNING")
            sys.exit(1)

        family = self.os_info["family"]
        log(f"检测到操作系统: {self.os_info['name']} {self.os_info['version']} ({self.os_info['arch']})", "STEP")

        if family == "debian":
            return DebianInstaller(self.os_info)
        elif family == "rhel":
            return RhelInstaller(self.os_info)
        else:
            log(f"不支持的系统类型: {family}", "ERROR")
            sys.exit(1)

    def configure_docker(self):
        """配置 Docker daemon.json"""
        log("=" * 60, "STEP")
        log("配置 Docker", "STEP")
        log("=" * 60, "STEP")

        config = {
            "registry-mirrors": self.REGISTRY_MIRRORS,
            "log-driver": "json-file",
            "log-opts": {
                "max-size": "10m",
                "max-file": "3"
            },
            "max-concurrent-downloads": 10,
            "max-download-attempts": 5
        }

        config_path = Path("/etc/docker/daemon.json")
        config_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            with open(config_path, 'w') as f:
                json.dump(config, f, indent=2)
            log(f"Docker 配置已写入: {config_path}", "SUCCESS")
            return True
        except Exception as e:
            log(f"写入配置失败: {e}", "ERROR")
            return False

    def start_docker_service(self):
        """启动 Docker 服务"""
        log("=" * 60, "STEP")
        log("启动 Docker 服务", "STEP")
        log("=" * 60, "STEP")

        log("启动 Docker 服务...", "INFO")
        rc, _, _ = run_command(["systemctl", "start", "docker"], check=False)
        if rc != 0:
            log("启动 Docker 服务失败", "ERROR")
            return False

        log("设置 Docker 开机自启...", "INFO")
        run_command(["systemctl", "enable", "docker"], check=False)

        log("重启 Docker 服务以应用配置...", "INFO")
        run_command(["systemctl", "restart", "docker"], check=False)

        rc, stdout, _ = run_command(["systemctl", "is-active", "docker"], check=False)
        if rc == 0 and stdout.strip() == "active":
            log("Docker 服务运行正常", "SUCCESS")
            return True
        else:
            log("Docker 服务未正常运行", "ERROR")
            return False

    def verify_installation(self):
        """验证 Docker 安装"""
        log("=" * 60, "STEP")
        log("验证 Docker 安装", "STEP")
        log("=" * 60, "STEP")

        rc, stdout, _ = run_command(["docker", "--version"], check=False)
        if rc == 0:
            log(f"Docker 版本: {stdout.strip()}", "SUCCESS")
        else:
            log("无法获取 Docker 版本", "ERROR")
            return False

        rc, stdout, _ = run_command(["docker", "compose", "version"], check=False)
        if rc == 0:
            log(f"Compose 版本: {stdout.strip()}", "SUCCESS")

        log("测试运行 hello-world...", "INFO")
        rc, stdout, stderr = run_command(["docker", "run", "--rm", "hello-world"], check=False)
        if rc == 0:
            log("Docker 运行正常", "SUCCESS")
            return True
        else:
            log("Docker 测试运行失败（可能需要等待镜像加速生效）", "WARNING")
            log(f"  错误: {stderr.strip()[:200]}", "WARNING")
            return False

    def install(self, force=False):
        """安装 Docker"""
        log("=" * 60, "STEP")
        log("开始安装 Docker", "STEP")
        log(f"系统: {self.os_info['name']} {self.os_info['version']}", "STEP")
        log("=" * 60, "STEP")

        if command_exists("docker"):
            if force:
                log("强制重新安装模式", "WARNING")
                self.installer.remove_docker()
            else:
                log("Docker 已安装", "WARNING")
                choice = input(f"{Colors.YELLOW}是否重新安装? (y/n): {Colors.END}").strip().lower()
                if choice != 'y':
                    log("取消安装", "WARNING")
                    return False
                self.installer.remove_docker()

        # 1. 卸载冲突包
        self.installer.remove_conflicts()

        # 2. 安装依赖
        self.installer.install_dependencies()

        # 3. RHEL 系需要添加源
        if isinstance(self.installer, RhelInstaller):
            self.installer.add_repository()

        # 4. 安装包
        if not self.installer.install_packages():
            log("包安装失败", "ERROR")
            return False

        # 5. 配置
        if not self.configure_docker():
            log("配置失败", "ERROR")
            return False

        # 6. 启动
        if not self.start_docker_service():
            log("启动服务失败", "ERROR")
            return False

        # 7. 验证
        self.verify_installation()

        log("=" * 60, "STEP")
        log("Docker 安装完成", "SUCCESS")
        log("=" * 60, "STEP")
        return True

    def uninstall(self):
        """卸载 Docker"""
        log("=" * 60, "STEP")
        log("开始卸载 Docker", "STEP")
        log("=" * 60, "STEP")

        if not command_exists("docker"):
            log("Docker 未安装", "WARNING")
            return

        self.installer.remove_docker()

        # 清理残留
        run_command(["rm", "-rf", "/var/lib/docker"], check=False)
        run_command(["rm", "-rf", "/var/lib/containerd"], check=False)
        run_command(["rm", "-f", "/etc/docker/daemon.json"], check=False)

        # RHEL 系清理 repo 文件
        repo_file = Path("/etc/yum.repos.d/docker-ce.repo")
        if repo_file.exists():
            repo_file.unlink()

        log("Docker 卸载完成", "SUCCESS")

    def reconfigure(self):
        """重新配置 Docker"""
        log("=" * 60, "STEP")
        log("重新配置 Docker", "STEP")
        log("=" * 60, "STEP")

        if not command_exists("docker"):
            log("Docker 未安装，无法配置", "ERROR")
            return

        if self.configure_docker():
            self.start_docker_service()
            log("Docker 配置完成", "SUCCESS")
        else:
            log("Docker 配置失败", "ERROR")

    def status(self):
        """查看 Docker 状态"""
        log("=" * 60, "STEP")
        log("Docker 状态", "STEP")
        log("=" * 60, "STEP")

        log(f"操作系统: {self.os_info['name']} {self.os_info['version']} ({self.os_info['arch']})", "INFO")

        if command_exists("docker"):
            log("Docker 已安装", "SUCCESS")
            _, stdout, _ = run_command(["docker", "--version"])
            log(f"  版本: {stdout.strip()}", "INFO")

            rc, stdout, _ = run_command(["systemctl", "is-active", "docker"])
            if stdout.strip() == "active":
                log("  服务状态: 运行中", "SUCCESS")
            else:
                log("  服务状态: 未运行", "ERROR")

            config_path = Path("/etc/docker/daemon.json")
            if config_path.exists():
                try:
                    with open(config_path) as f:
                        config = json.load(f)
                    mirrors = config.get("registry-mirrors", [])
                    log(f"  镜像加速地址: {len(mirrors)} 个", "INFO")
                except:
                    log("  配置文件读取失败", "ERROR")
            else:
                log("  配置文件不存在", "WARNING")
        else:
            log("Docker 未安装", "ERROR")


# ============================================================
# 主程序
# ============================================================

OPTIONS_MAP = {
    '1': ('安装 Docker', 'install'),
    '2': ('重新配置 Docker', 'reconfigure'),
    '3': ('查看 Docker 状态', 'status'),
    '4': ('卸载 Docker', 'uninstall'),
}


def show_menu(os_info):
    """显示交互式菜单"""
    os_label = f"{os_info['name']} {os_info['version']}"
    supported = "已支持" if os_info["supported"] else "不支持"

    print(f"""
{Colors.CYAN}{Colors.BOLD}
╔══════════════════════════════════════════════════════════════╗
║              Docker 管理工具                                  ║
║                                                              ║
║  功能：安装、配置、卸载 Docker                                ║
║  支持：Ubuntu/Debian/CentOS/Rocky/Anolis/openEuler          ║
║  系统：{os_label:<48s}║
║  状态：{supported:<50s}║
╚══════════════════════════════════════════════════════════════╝
{Colors.END}
""")
    print(f"{Colors.YELLOW}请选择操作：{Colors.END}\n")
    for key, (name, _) in OPTIONS_MAP.items():
        print(f"  {Colors.GREEN}[{key}]{Colors.END}  {name}")
    print(f"  {Colors.RED}[Q]{Colors.END}  退出")
    print()


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Docker 管理工具 - 多系统 Docker 安装、卸载和配置",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s                    # 交互式菜单模式
  %(prog)s install            # 安装 Docker
  %(prog)s install -f         # 强制重新安装
  %(prog)s uninstall          # 卸载 Docker
  %(prog)s reconfigure        # 重新配置 Docker
  %(prog)s status             # 查看 Docker 状态

支持系统:
  Ubuntu 22.04/24.04, Debian 11/12,
  CentOS 7/8/9, Rocky Linux 8/9,
  Anolis OS 8/23, openEuler 22.03/24.03
        """
    )

    parser.add_argument(
        "action",
        nargs="?",
        choices=["install", "uninstall", "reconfigure", "status"],
        help="执行的操作 (不提供则进入交互式菜单)"
    )

    parser.add_argument(
        "-f", "--force",
        action="store_true",
        help="强制重新安装（与 install 一起使用）"
    )

    args = parser.parse_args()

    manager = DockerManager()

    if args.action is None:
        while True:
            show_menu(manager.os_info)
            try:
                choice = input(f"{Colors.YELLOW}请输入选项 (1-4, Q/q=退出): {Colors.END}")
                if choice.lower() == 'q':
                    return
                elif choice in OPTIONS_MAP:
                    method = getattr(manager, OPTIONS_MAP[choice][1])
                    method()
                    input(f"\n{Colors.YELLOW}按回车继续...{Colors.END}")
                else:
                    print(f"{Colors.RED}无效选项{Colors.END}")
            except KeyboardInterrupt:
                return
        return

    if args.action == "install":
        manager.install(force=args.force)
    elif args.action == "uninstall":
        manager.uninstall()
    elif args.action == "reconfigure":
        manager.reconfigure()
    elif args.action == "status":
        manager.status()


if __name__ == "__main__":
    main()
