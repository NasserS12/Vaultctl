"""Module [1]: Full System Scan.

CPU, RAM, Disk, Battery, active users, pending APT/Snap updates,
and Ubuntu Pro / ESM status.
"""
import os
import platform
import shutil
import subprocess
from datetime import datetime

import psutil

from core.logging_setup import logger
from ui.colors import (
    CYAN,
    DIM,
    GREEN,
    OK,
    RED,
    RESET,
    TERMINAL_WIDTH,
    WARN,
    WHITE,
    YELLOW,
)
from ui.terminal import section_header


def get_uptime():
    boot_time = datetime.fromtimestamp(psutil.boot_time())
    now = datetime.now()
    uptime = now - boot_time
    return str(uptime).split(".")[0]


def show_ubuntu_pro_status():
    section_header("UBUNTU PRO & ESM STATUS")
    try:
        if not shutil.which('pro') and not shutil.which('ubuntu-advantage'):
            print(f"Ubuntu Pro    : {YELLOW}Tool not installed{RESET}")
            print("Install via   : sudo apt install ubuntu-advantage-tools")
            print(f"{DIM}{'-' * TERMINAL_WIDTH}{RESET}")
            return

        cmd = shutil.which('pro') or 'ubuntu-advantage'

        result = subprocess.run(
            [cmd, 'status', '--format', 'tabular'],
            capture_output=True, text=True,
            timeout=10
        )

        output = result.stdout + result.stderr

        if any(
            x in output.lower() for x in [
                'not attached',
                'unattached',
                'no contract']):
            print(f"Subscription  : {WARN} Not subscribed (Free tier){RESET}")
            print("Activate via  : sudo pro attach <token>")
        elif any(x in output.lower() for x in [
                'attached', 'subscription', 'contract', 'pro']):
            print(f"Subscription  : {OK} Ubuntu Pro Active{RESET}")
        else:
            first_line = output.strip().split(
                '\n')[0] if output.strip() else 'No output'
            print(f"Subscription  : {YELLOW}{first_line}{RESET}")

        # ESM Security Updates
        if 'esm-infra' in output:
            if 'enabled' in output[output.find(
                    'esm-infra'):output.find('esm-infra') + 60].lower():
                print(
                    f"ESM Infra     : {OK} Enabled "
                    f"(Extended security patches){RESET}")
            else:
                print(f"ESM Infra     : {WARN} Disabled{RESET}")

        if 'esm-apps' in output:
            if 'enabled' in output[output.find(
                    'esm-apps'):output.find('esm-apps') + 60].lower():
                print(f"ESM Apps      : {OK} Enabled{RESET}")
            else:
                print(f"ESM Apps      : {WARN} Disabled{RESET}")

        if 'livepatch' in output:
            if 'enabled' in output[output.find(
                    'livepatch'):output.find('livepatch') + 60].lower():
                print(
                    f"Livepatch     : {OK} Enabled "
                    f"(Kernel updates without reboot){RESET}")
            else:
                print(f"Livepatch     : {WARN} Disabled{RESET}")

        # Support expiry
        for line in output.split('\n'):
            if 'expires' in line.lower() or 'valid until' in line.lower():
                print(f"Expiry        : {CYAN}{line.strip()}{RESET}")
                break

    except subprocess.TimeoutExpired:
        logger.debug("show_ubuntu_pro_status timed out")
        print(
            f"Status        : {RED}Timeout - could not reach "
            f"Ubuntu Pro servers{RESET}")
    except Exception as e:
        logger.debug(f"show_ubuntu_pro_status failed: {e}")
        print(
            f"Status        : {RED}Could not retrieve Ubuntu Pro info{RESET}")
    print(f"{DIM}{'-' * TERMINAL_WIDTH}{RESET}")


def show_snap_status():
    section_header("SNAP PACKAGES STATUS")
    try:
        if not shutil.which('snap'):
            print(f"Snap Service  : {YELLOW}Not installed{RESET}")
            print(f"{DIM}{'-' * TERMINAL_WIDTH}{RESET}")
            return

        svc = subprocess.run(
            ['systemctl', 'is-active', 'snapd'],
            capture_output=True, text=True
        )
        snapd_active = svc.stdout.strip() == 'active'
        status_color = GREEN if snapd_active else RED
        print(
            f"Snap Service  : {status_color}"
            f"[{svc.stdout.strip().upper()}]{RESET}")

        if not snapd_active:
            print(f"Status        : {RED}snapd is not running{RESET}")
            print(f"{DIM}{'-' * TERMINAL_WIDTH}{RESET}")
            return

        pkgs = subprocess.run(
            ['snap', 'list'],
            capture_output=True, text=True
        )
        if pkgs.returncode != 0:
            print(f"Status        : {RED}snap list failed{RESET}")
            print(f"{DIM}{'-' * TERMINAL_WIDTH}{RESET}")
            return

        lines = pkgs.stdout.strip().split('\n')[1:]
        print(f"Installed     : {len(lines)} package(s)")

        print(f"{CYAN}[*] Checking for updates...{RESET}", end='\r')
        update_names = []
        try:
            updates = subprocess.run(
                ['snap', 'refresh', '--list'],
                capture_output=True, text=True,
                timeout=5
            )
            if updates.returncode == 0:
                out = updates.stdout.strip()
                if not out.startswith('All snaps up to date'):
                    update_names = [
                        line.split()[0]
                        for line in out.split('\n')[1:]
                        if line.strip()
                    ]
        except subprocess.TimeoutExpired:
            logger.debug("snap refresh --list timed out")
        except subprocess.CalledProcessError as e:
            logger.debug(f"snap refresh --list failed: {e}")

        count = len(update_names)
        if count == 0:
            print(f"Updates       : {OK} All up to date   {RESET}")
        else:
            print(f"Updates       : {RED}! {count} update(s) available{RESET}")

        if lines:
            print(f"\n{'NAME':<25} {'VERSION':<15} {'STATUS'}")
            print(f"{DIM}{'-' * TERMINAL_WIDTH}{RESET}")
            MAX_DISPLAY = 15
            for line in lines[:MAX_DISPLAY]:
                parts = line.split()
                if len(parts) < 2:
                    continue
                name = parts[0]
                version = parts[1]
                if name in update_names:
                    status = f"{WARN} Update available{RESET}"
                else:
                    status = f"{OK} Latest{RESET}"
                print(f"{name:<25} {version:<15} {status}")
            if len(lines) > MAX_DISPLAY:
                remaining = len(lines) - MAX_DISPLAY
                print(f"{DIM}... and {remaining} more package(s).{RESET}")

    except subprocess.TimeoutExpired:
        print(f"Status : {RED}Timed out waiting for snap{RESET}")
    except FileNotFoundError as e:
        print(f"Status : {RED}Required command not found: {e.filename}{RESET}")
    except Exception as e:
        logger.debug(f"show_snap_status failed: {e}")
        print(f"Status : {RED}Could not retrieve snap info{RESET}")
    print(f"{DIM}{'-' * TERMINAL_WIDTH}{RESET}")


def show_pending_updates():
    section_header("PENDING SYSTEM UPDATES")
    try:
        result = subprocess.run(
            ['apt', 'list', '--upgradable'],
            capture_output=True, text=True
        )
        lines = [line for line in result.stdout.strip().split('\n')
                 if '/' in line]
        count = len(lines)

        if count == 0:
            print(f"Status : {OK} System is up to date{RESET}")
        elif count <= 5:
            print(f"Status : {WARN} {count} update(s) available{RESET}")
            for line in lines:
                pkg = line.split('/')[0]
                print(f"  → {pkg}")
        else:
            print(f"Status : {RED}! {count} updates pending{RESET}")
            for line in lines[:5]:
                pkg = line.split('/')[0]
                print(f"  → {pkg}")
            print(f"  {YELLOW}... and {count - 5} more{RESET}")

        # Security updates specifically
        sec = subprocess.run(
            ['apt', 'list', '--upgradable'],
            capture_output=True, text=True
        )
        sec_count = sum(1 for line in sec.stdout.split('\n')
                        if 'security' in line)
        if sec_count > 0:
            print(
                f"Security: {RED}! {sec_count} security "
                f"update(s) critical{RESET}")
        else:
            print(f"Security: {OK} No security updates pending{RESET}")

    except Exception as e:
        logger.debug(f"show_pending_updates failed: {e}")
        print(f"Status : {RED}Could not check updates{RESET}")
    print(f"{DIM}{'-' * TERMINAL_WIDTH}{RESET}")


def get_os_pretty_name(path = '/etc/os-release'):
    """Read the distro's friendly name from /etc/os-release."""
    with open(path, 'r') as f:
        content = f.read()
    for line in content.splitlines():
        if line.startswith('PRETTY_NAME='):
            return line.split('=', 1)[1].strip('"')
    return "Unknown Linux"


def get_package_counts():
    """Return a formatted string like '1744 (dpkg), 20 (snap)'."""
    dpkg_count = 0
    try:
        result = subprocess.run(
        ['dpkg-query', '-f', '${db:Status-Status}\n', '-W'],
        capture_output=True, text=True, timeout=5
    )
        dpkg_count = sum(
            1 for line in result.stdout.strip().splitlines()
            if line.strip() == 'installed'
        )
    except Exception as e:
        logger.debug(f"dpkg package count failed: {e}")

    snap_count = 0
    try:
        result = subprocess.run(
            ['snap', 'list'],
            capture_output=True, text=True, timeout=5
        )
        lines = result.stdout.strip().splitlines()
        snap_count = max(0, len(lines) - 1)
    except Exception as e:
        logger.debug(f"snap pakage count failed: {e}")

    return f"{dpkg_count} (dpkg), {snap_count} (snap)"


KNOWN_TERMINALS = {
    'ptyxis', 'gnome-terminal-server', 'konsole', 'xterm',
    'alacritty', 'kitty', 'tilix', 'terminator', 'xfce4-terminal',
    }


TERMINAL_PACKAGE_NAMES = {
    'ptyxis': 'ptyxis',
    'gnome-terminal-server': 'gnome-terminal',
    'konsole': 'konsole',
    'xterm': 'xterm',
    'alacritty': 'alacritty',
    'kitty': 'kitty',
    'tilix': 'tilix',
    'terminator': 'terminator',
    'xfce4-terminal': 'xfce4-terminal',
}

def get_terminal_version(process_name):
    """Look up the installed package version for a terminal
    emulator's process name, via dpkg."""
    pkg_name = TERMINAL_PACKAGE_NAMES.get(process_name, process_name)
    try:
        result = subprocess.run(
            ['dpkg-query', '-W', '-f=${Version}', pkg_name],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            full_version = result.stdout.strip()
            return full_version.split('-')[0]

    except Exception as e:
        logger.debug(f"get_terminal_version failed: {e}")
    return None

def get_terminal_process_name():
    """Walk up the process tree from this script until we find a
    known terminal emulator process."""
    try:
        proc = psutil.Process(os.getpid())
        while proc is not None:
            name = proc.name()
            if name in KNOWN_TERMINALS:
                return name
            proc = proc.parent()
    except Exception as e:
        logger.debug(f"get_terminal_process_name failed: {e}")
    return None

def get_terminal_info():
    """Return a formatted string like 'Ptyxis 50.1', or 'Unknown'
    if detection fails."""
    process_name = get_terminal_process_name()
    if process_name is None:
        return "Unknown"

    version = get_terminal_version(process_name)
    display_name = process_name.replace('-', ' ').title()

    if version:
        return f"{display_name} {version}"
    return display_name

def get_host_info():
    """Read the physical machine's vendor + model from DMI sysfs
    entries (e.g. 'LENOVO ThinkPad E14 Gen 7')."""
    def read_dmi(field):
        try:
            with open(f'/sys/class/dmi/id/{field}', 'r') as f:
                return f.read().strip()
        except Exception:
            return ""

    vendor = read_dmi('sys_vendor')
    model = read_dmi('product_family') or read_dmi('product_name')

    parts = [p for p in [vendor, model] if p]
    return " ".join(parts) if parts else "Unknown"

def show_sys_info():
    section_header("SYSTEM INFORMATION")
    print(f"  {DIM}Hostname{RESET}  {WHITE}{platform.node()}{RESET}")
    print(f"  {DIM}Host    {RESET}  {WHITE}{get_host_info()}{RESET}")
    print(f"  {DIM}OS      {RESET}  {WHITE}{get_os_pretty_name()}{RESET}")
    print(f"  {DIM}Kernel  {RESET}  {WHITE}{platform.release()}{RESET}")
    print(f"  {DIM}Package{RESET}   {WHITE}{get_package_counts()}{RESET}")
    print(f"  {DIM}Terminal{RESET}  {WHITE}{get_terminal_info()}{RESET}")
    print(f"  {DIM}Arch    {RESET}  {WHITE}{platform.machine()}{RESET}")
    print(f"  {DIM}Uptime  {RESET}  {WHITE}{get_uptime()}{RESET}")  
    print(f"{DIM}{'-' * TERMINAL_WIDTH}{RESET}")


def show_cpu_status():
    section_header("CPU STATUS")
    freq = psutil.cpu_freq()
    cpu_usage = psutil.cpu_percent(interval=None)
    color = GREEN if cpu_usage < 50 else YELLOW if cpu_usage < 80 else RED
    print(f"  {DIM}Usage    {RESET}  {color}{cpu_usage}%{RESET}")

    try:
        temps = psutil.sensors_temperatures()
        if 'coretemp' in temps:
            t = temps['coretemp'][0].current
            t_color = GREEN if t < 60 else YELLOW if t < 80 else RED
            print(f"  {DIM}Temp     {RESET}  {t_color}{t}°C{RESET}")
        elif 'cpu_thermal' in temps:
            t = temps['cpu_thermal'][0].current
            print(f"  {DIM}Temp     {RESET}  {t}°C")
    except Exception as e:
        logger.debug(f"CPU temperature read failed: {e}")

    if freq:
        print(
            f"  {DIM}Freq     {RESET}  {WHITE}{
                freq.current:.0f} MHz{RESET}  {DIM}/ {
                freq.max:.0f} MHz max{RESET}")
    print(
        f"  {DIM}Cores    {RESET}  {WHITE}{
            psutil.cpu_count(
                logical=False)} Physical{RESET}  {DIM}/ {
            psutil.cpu_count(
                logical=True)} Logical{RESET}")

    per_cpu = psutil.cpu_percent(percpu=True)
    bars = []
    for p in per_cpu[:8]:
        c = GREEN if p < 50 else YELLOW if p < 80 else RED
        bars.append(f"{c}{p:>4.1f}%{RESET}")
    print(f"  {DIM}Per Core {RESET}  "
          f"{('  ').join(bars)}")
    print(f"{DIM}{'-' * TERMINAL_WIDTH}{RESET}")


def show_mem_status():
    section_header("MEMORY STATUS")
    mem = psutil.virtual_memory()
    swap = psutil.swap_memory()
    def to_gb(b): return b / (1024**3)

    ram_color = (
        GREEN if mem.percent < 60
        else YELLOW if mem.percent < 85
        else RED)
    swap_color = (
        GREEN if swap.percent < 40
        else YELLOW if swap.percent < 70
        else RED)

    print(f"  {DIM}RAM      {RESET}  {ram_color}{mem.percent}%{RESET}  "
          f"{DIM}({to_gb(mem.used):.2f} / {to_gb(mem.total):.2f} GB){RESET}")
    print(
        f"  {DIM}Free     {RESET}  {WHITE}{
            to_gb(
                mem.available):.2f} GB{RESET}")
    print(f"  {DIM}Swap     {RESET}  {swap_color}{swap.percent}%{RESET}")
    print(f"{DIM}{'-' * TERMINAL_WIDTH}{RESET}")


def show_disk_status():
    section_header("STORAGE STATUS")
    print()
    total_used = 0
    total_free = 0
    drives = []

    for part in psutil.disk_partitions():
        try:
            if (os.name == 'nt'
                and ('cdrom' in part.opts or part.fstype == '')) or \
               '/snap' in part.mountpoint or \
               part.mountpoint in ['/boot/efi', '/proc', '/sys']:
                continue

            usage = psutil.disk_usage(part.mountpoint)
            drives.append({
                'mount': part.mountpoint,
                'used': usage.percent,
                'free_gb': usage.free / (1024**3),
                'total_gb': usage.total / (1024**3),
                'fstype': part.fstype
            })
            total_used += usage.used
            total_free += usage.free

        except PermissionError:
            continue

    print(
        f"  {DIM}{
            'Mount':<16} {
            'Used':>6}   {
                'Free':>8}   {
                    'Total':>8}   {'Type'}{RESET}")
    print(f"{DIM}{'-' * TERMINAL_WIDTH}{RESET}")

    for d in drives:
        u_color = (
            GREEN if d['used'] < 70
            else YELLOW if d['used'] < 90
            else RED)
        print(f"  {WHITE}{d['mount']:<16}{RESET} "
              f"{u_color}{d['used']:>5.1f}%{RESET}   "
              f"{d['free_gb']:>7.1f}GB   "
              f"{d['total_gb']:>7.1f}GB   "
              f"{DIM}{d['fstype']}{RESET}")
    print(f"{DIM}{'-' * TERMINAL_WIDTH}{RESET}")
    total_used_gb = total_used / (1024**3)
    total_free_gb = total_free / (1024**3)
    print(
        f"  {DIM}Total{RESET}  Used: {WHITE}{
            total_used_gb:.1f} GB{RESET}  Free: {GREEN}{
            total_free_gb:.1f} GB{RESET}\n")


def show_active_users():
    section_header("ACTIVE LOGGED-IN USERS")
    users = psutil.users()
    if not users:
        print(f"  {DIM}No other users logged in.{RESET}")
    else:
        print(
            f"  {DIM}{
                'User':<15}  {
                'Terminal':<10}  {
                'Host':<15}  {'Started'}{RESET}")
        print(f"{DIM}{'-' * TERMINAL_WIDTH}{RESET}")
        for u in users:
            start_time = datetime.fromtimestamp(
                u.started).strftime("%Y-%m-%d %H:%M")
            print(
                f"  {WHITE}{
                    u.name:<15}{RESET}  {
                    u.terminal:<10}  {
                    u.host:<15}  {DIM}{start_time}{RESET}")
    print(f"{DIM}{'-' * TERMINAL_WIDTH}{RESET}")


def show_battery_status():
    battery = psutil.sensors_battery()
    if battery:
        section_header("POWER & BATTERY STATUS")
        plugged = (
            f"{GREEN}Charging ⚡{RESET}" if battery.power_plugged
            else f"{YELLOW}On Battery{RESET}")
        color = (
            GREEN if battery.percent > 50
            else YELLOW if battery.percent > 20
            else RED)
        print(
            f"  {DIM}Charge   {RESET}  {color}{int(battery.percent)}%{RESET}  "
            f"{DIM}({plugged}{DIM}){RESET}")
        if not battery.power_plugged and battery.secsleft != psutil.POWER_TIME_UNKNOWN:  # noqa: E501
            m, s = divmod(battery.secsleft, 60)
            h, m = divmod(m, 60)
            t_color = GREEN if h >= 2 else YELLOW if h >= 1 else RED
            print(f"  {DIM}Remaining{RESET}  {t_color}{h}h {m}m{RESET}")
    else:
        section_header("POWER STATUS")
        print(
            f"  {DIM}Source   {RESET}  {GREEN}AC Wall Power{RESET}  "
            f"{DIM}(No Battery){RESET}")
    print(f"{DIM}{'-' * TERMINAL_WIDTH}{RESET}")


def run_full_scan():
    """Orchestrator for Main Menu option [1] — runs every scan section
    in the same order as the original monolithic script."""
    show_sys_info()
    show_cpu_status()
    show_mem_status()
    show_disk_status()
    show_active_users()
    show_battery_status()
    show_pending_updates()
    show_snap_status()
    show_ubuntu_pro_status()
