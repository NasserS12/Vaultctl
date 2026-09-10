"""Module [1]: Full System Scan.

CPU, RAM, Disk, Battery, active users, pending APT/Snap updates,
and Ubuntu Pro / ESM status.
"""
import os
import shutil
import subprocess
import platform
import psutil
from datetime import datetime

from core.logging_setup import logger
from ui.colors import (
    RESET, WHITE, CYAN, GREEN, YELLOW, RED, DIM, BOLD,
    OK, WARN, TERMINAL_WIDTH,
)


def get_uptime():
    boot_time = datetime.fromtimestamp(psutil.boot_time())
    now = datetime.now()
    uptime = now - boot_time
    return str(uptime).split(".")[0]


def show_ubuntu_pro_status():
    print(f"{CYAN}{BOLD}❯ UBUNTU PRO & ESM STATUS{RESET}")
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
    print(f"{CYAN}{BOLD}❯ SNAP PACKAGES STATUS{RESET}")
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
            f"Snap Service  : {status_color}● {
                svc.stdout.strip().upper()}{RESET}")

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
            for line in lines:
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

    except subprocess.TimeoutExpired:
        print(f"Status : {RED}Timed out waiting for snap{RESET}")
    except FileNotFoundError as e:
        print(f"Status : {RED}Required command not found: {e.filename}{RESET}")
    except Exception as e:
        logger.debug(f"show_snap_status failed: {e}")
        print(f"Status : {RED}Could not retrieve snap info{RESET}")
    print(f"{DIM}{'-' * TERMINAL_WIDTH}{RESET}")


def show_pending_updates():
    print(f"{CYAN}{BOLD}❯ PENDING SYSTEM UPDATES{RESET}")
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


def show_sys_info():
    print(f"{CYAN}{BOLD}❯ SYSTEM INFORMATION{RESET}")
    print(f"  {DIM}Hostname{RESET}  {WHITE}{platform.node()}{RESET}")
    print(
        f"  {DIM}OS      {RESET}  {WHITE}{
            platform.system()} {
            platform.release()}{RESET}")
    print(f"  {DIM}Arch    {RESET}  {WHITE}{platform.machine()}{RESET}")
    print(f"  {DIM}Uptime  {RESET}  {WHITE}{get_uptime()}{RESET}")

    try:
        load1, load5, load15 = os.getloadavg()
        cores = psutil.cpu_count() or 1

        def get_load_color(load_val):
            if load_val < cores * 0.7:
                return GREEN
            if load_val < cores:
                return YELLOW
            return RED
        print(
            f"  {DIM}Load Avg{RESET}  " f"{
                get_load_color(load1)}{
                load1:.2f}{RESET}  " f"{
                get_load_color(load5)}{
                    load5:.2f}{RESET}  " f"{
                        get_load_color(load15)}{
                            load15:.2f}{RESET}  {DIM}(1m · 5m · 15m){RESET}")
    except Exception as e:
        logger.debug(f"show_sys_info load avg failed: {e}")
    print(f"{DIM}{'-' * TERMINAL_WIDTH}{RESET}")


def show_cpu_status():
    print(f"{CYAN}{BOLD}❯ CPU STATUS{RESET}")
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
    print(f"{CYAN}{BOLD}❯ MEMORY STATUS{RESET}")
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
    print(f"{CYAN}{BOLD}❯ STORAGE STATUS{RESET}\n")
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
    print(f"{CYAN}{BOLD}❯ ACTIVE LOGGED-IN USERS{RESET}")
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
        print(f"{CYAN}{BOLD}❯ POWER & BATTERY STATUS{RESET}")
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
        print(f"{CYAN}{BOLD}❯ POWER STATUS{RESET}")
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
