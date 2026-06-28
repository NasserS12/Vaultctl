import os
import sys
import subprocess
import psutil
import platform
import time
import shutil
import socket
import urllib.request
import re
import logging
from datetime import datetime
from contextlib import contextmanager

# --- LOGGING SETUP ---
LOG_FILE = os.path.join(
    os.path.dirname(
        os.path.abspath(__file__)),
    "diagnostic_tool.log")
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

# --- ABSOLUTE TOP PRIORITY: LOCK TERMINAL IMMEDIATELY ---
if os.name == 'posix':
    try:
        import termios
        # 1. Disable Echo immediately so nothing appears on screen
        fd = sys.stdin.fileno()
        attr = termios.tcgetattr(fd)
        attr[3] = attr[3] & ~termios.ECHO
        termios.tcsetattr(fd, termios.TCSADRAIN, attr)
        # 2. Flush any early keystrokes typed while Python is starting
        termios.tcflush(sys.stdin, termios.TCIFLUSH)
    except Exception as e:
        logger.debug(f"termios early-lock failed: {e}")

# --- COLOR PALETTE ---
RESET = "\033[0m"
WHITE = "\033[97m"
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BLUE = "\033[94m"
DIM = "\033[2m"
BOLD = "\033[1m"

# Unified status icons
OK = f"{GREEN}✓{RESET}"
WARN = f"{YELLOW}⚠{RESET}"
FAIL = f"{RED}✗{RESET}"
INFO = f"{CYAN}•{RESET}"

TERMINAL_WIDTH = 65

# SAFETY BLACKLIST
CRITICAL_BLACKLIST = [
    'poweroff',
    'reboot',
    'halt',
    'display-manager',
    'gdm',
    'lightdm',
    'sddm',
    'dbus',
    'systemd-',
    'default.target',
    'rescue.target',
    'emergency.target']

# --- UTILS ---


def flush_input():
    """Flushes the stdin buffer to prevent accidental keystrokes
    from skipping prompts."""
    if os.name == 'posix':
        try:
            import termios
            termios.tcflush(sys.stdin, termios.TCIFLUSH)
        except Exception as e:
            logger.debug(f"flush_input failed: {e}")


def set_echo(enable):
    """Enables or disables terminal echo on Linux."""
    if os.name == 'posix' and sys.stdin.isatty():
        try:
            import termios
            fd = sys.stdin.fileno()
            attr = termios.tcgetattr(fd)
            if enable:
                attr[3] = attr[3] | termios.ECHO
            else:
                attr[3] = attr[3] & ~termios.ECHO
            termios.tcsetattr(fd, termios.TCSADRAIN, attr)
        except Exception as e:
            logger.debug(f"set_echo({enable}) failed: {e}")


@contextmanager
def terminal_manager(echo=True):
    """Context manager to safely manage terminal echo."""
    try:
        set_echo(echo)
        yield
    finally:
        set_echo(True)
        flush_input()


def wait_for_enter():
    """Waits for Enter key only. Ignores all other input except Ctrl+C."""
    if os.name == 'posix' and sys.stdin.isatty():
        try:
            import termios
            import tty
            fd = sys.stdin.fileno()
            old = termios.tcgetattr(fd)
            try:
                tty.setraw(fd)
                while True:
                    ch = sys.stdin.read(1)
                    if ch in ('\r', '\n'):
                        break
                    elif ch == '\x03':  # Ctrl+C
                        termios.tcsetattr(fd, termios.TCSADRAIN, old)
                        raise KeyboardInterrupt
                    # Ignore everything else silently
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old)
        except KeyboardInterrupt:
            raise
        except Exception as e:
            logging.debug(f"wait_for_enter raw mode failed: {e}")
            input("")  # fallback
    else:
        input("")  # Windows fallback


def clear_screen():
    """Clears the terminal screen and scrollback buffer
    using fast ANSI escape codes."""
    # ANSI escape sequences to clear screen and scrollback buffer
    print("\033[H\033[2J\033[3J", end="", flush=True)


def get_user_home():
    """Returns the home directory of the real user,
    even if running under sudo."""
    sudo_user = os.environ.get('SUDO_USER')
    if sudo_user:
        try:
            import pwd
            return pwd.getpwnam(sudo_user).pw_dir
        except (ImportError, KeyError):
            return os.path.expanduser(f"~{sudo_user}")
    return os.path.expanduser("~")


def get_confirmation(prompt_text):
    """Strictly captures a yes/no confirmation. Re-asks on invalid input."""
    while True:
        flush_input()
        try:
            ans = input(prompt_text).lower().strip()
            if ans in ['y', 'yes', '1']:
                return True
            if ans in ['n', 'no', '0', '']:
                return False
            print(f"{RED}  [!] Invalid input{RESET}", end="", flush=True)
            time.sleep(1.5)
            # Clear the error and prompt lines for a clean re-ask
            print("\r\033[K\033[A\r\033[K", end="", flush=True)
        except (KeyboardInterrupt, EOFError):
            return False


def check_sudo():
    """Checks for root privileges. Returns True if authenticated."""
    has_sudo_cache = subprocess.run(
        ['sudo', '-n', 'true'], capture_output=True
    ).returncode == 0

    if os.getuid() == 0 or has_sudo_cache:
        return True
    print(
        f"{YELLOW}[!] This action requires root privileges. "
        f"Please authenticate...{RESET}")
    try:
        result = subprocess.run(['sudo', '-v'], check=False)
        success = result.returncode == 0
        if success:
            logger.info("sudo authentication successful.")
        else:
            logger.warning("sudo authentication failed.")
        return success
    except (KeyboardInterrupt, EOFError):
        print(f"\n{RED}[X] Authentication cancelled.{RESET}")
        logger.warning("sudo authentication cancelled by user.")
        return False

# --- CORE METRICS ---


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
            print(f"{DIM}{"-" * TERMINAL_WIDTH}{RESET}")
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
    print(f"{DIM}{"-" * TERMINAL_WIDTH}{RESET}")


def show_snap_status():
    print(f"{CYAN}{BOLD}❯ SNAP PACKAGES STATUS{RESET}")
    try:
        if not shutil.which('snap'):
            print(f"Snap Service  : {YELLOW}Not installed{RESET}")
            print(f"{DIM}{"-" * TERMINAL_WIDTH}{RESET}")
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
            print(f"{DIM}{"-" * TERMINAL_WIDTH}{RESET}")
            return

        pkgs = subprocess.run(
            ['snap', 'list'],
            capture_output=True, text=True
        )
        if pkgs.returncode != 0:
            print(f"Status        : {RED}snap list failed{RESET}")
            print(f"{DIM}{"-" * TERMINAL_WIDTH}{RESET}")
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
            print(f"{DIM}{"-" * TERMINAL_WIDTH}{RESET}")
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
    print(f"{DIM}{"-" * TERMINAL_WIDTH}{RESET}")


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
    print(f"{DIM}{"-" * TERMINAL_WIDTH}{RESET}")


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
    print(f"{DIM}{'-' * TERMINAL_WIDTH}{RESET}")  # noqa: E501


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


def show_network_status():
    print(f"{CYAN}{BOLD}❯ NETWORK & CONNECTIVITY{RESET}")

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        print(f"  {DIM}Local IP {RESET}  {WHITE}{local_ip}{RESET}")

        try:
            public_ip = urllib.request.urlopen(
                'https://ident.me', timeout=2).read().decode('utf8')
            print(f"  {DIM}Public IP{RESET}  {WHITE}{public_ip}{RESET}")
        except Exception as e:
            logger.debug(f"Public IP lookup failed: {e}")
            print(f"  {DIM}Public IP{RESET}  {RED}Offline / Timeout{RESET}")

        print(f"  {DIM}Latency  {RESET}")
        for label, target in [("Google DNS", "8.8.8.8"),
                              ("Cloudflare", "1.1.1.1")]:
            try:
                res = subprocess.run(
                    ['ping', '-c', '1', '-W', '1', target],
                    capture_output=True, text=True)
                if res.returncode == 0:
                    time_match = re.search(r"time=([\d.]+)", res.stdout)
                    if time_match:
                        ms = float(time_match.group(1))
                        color = (
                            GREEN if ms < 50
                            else YELLOW if ms < 150
                            else RED)
                        print(
                            f"    {DIM}→ {
                                label:<12}{RESET} {color}{
                                ms:.1f} ms{RESET}")
                    else:
                        print(
                            f"    {DIM}→ {
                                label:<12}{RESET} {RED}Error{RESET}")
                else:
                    print(
                        f"    {DIM}→ {
                            label:<12}{RESET} {RED}Unreachable{RESET}")
            except Exception as e:
                logger.debug(f"Ping {label} failed: {e}")
                print(f"    {DIM}→ {label:<12}{RESET} {RED}Error{RESET}")

    except Exception as e:
        logger.debug(f"Network connectivity check failed: {e}")
        print(f"  {DIM}Status   {RESET}  {RED}Disconnected{RESET}")

    try:
        net1 = psutil.net_io_counters()
        time.sleep(0.5)
        net2 = psutil.net_io_counters()

        def format_speed(b):
            kb = b / 1024
            if kb > 1024:
                return f"{kb / 1024:.1f} MB/s"
            return f"{kb:.1f} KB/s"

        down = (net2.bytes_recv - net1.bytes_recv) * 2
        up = (net2.bytes_sent - net1.bytes_sent) * 2

        print(f"  {DIM}Download {RESET}  {GREEN}↓ {format_speed(down)}{RESET}")
        print(f"  {DIM}Upload   {RESET}  {CYAN}↑ {format_speed(up)}{RESET}")
    except Exception as e:
        logger.debug(f"Network speed measurement failed: {e}")


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


def manage_processes_live():
    sort_by = 'memory_percent'

    def row_color(mem_pct, cpu_pct):
        """Return color based on highest resource pressure."""
        if mem_pct > 80 or cpu_pct > 80:
            return RED
        if mem_pct > 50 or cpu_pct > 50:
            return YELLOW
        return WHITE

    KERNEL_PID_THRESHOLD = 100

    def do_kill(pid_target, force=False):
        if pid_target <= KERNEL_PID_THRESHOLD:
            print(
                f"\n{RED}[X] Refused: PID {pid_target} is a "
                f"kernel/system process.{RESET}")
            time.sleep(1.5)
            return
        if pid_target not in visible_pids:
            print(
                f"\n{YELLOW}[!] PID {pid_target} not in visible list. "
                f"Use kill <#> to select from table.{RESET}")
            time.sleep(1.5)
            return
        try:
            proc = psutil.Process(pid_target)
            proc_name = proc.name()
        except psutil.NoSuchProcess:
            print(f"\n{RED}[X] Process {pid_target} not found.{RESET}")  # noqa: E501
            time.sleep(1.5)
            return
        except psutil.AccessDenied:
            print(f"\n{RED}[X] Access Denied! Run with sudo.{RESET}")
            time.sleep(2.0)
            return

        # --- Confirmation before killing ---
        sig_label = "FORCE KILL (SIGKILL)" if force else "Kill (SIGTERM)"
        print(
            f"\n{RED}[!] {sig_label} → \"{proc_name}\" "
            f"(PID {pid_target}){RESET}")
        if not get_confirmation(f"{RED}    Are you sure? (y/N): {RESET}"):
            print(f"{YELLOW}[*] Cancelled.{RESET}")
            time.sleep(1.0)
            return

        try:
            if force:
                proc.kill()      # SIGKILL — immediate, no cleanup
            else:
                proc.terminate()  # SIGTERM — graceful
            sig_sent = "SIGKILL" if force else "SIGTERM"
            logger.info(f"Sent {sig_sent} to PID {pid_target} ({proc_name}).")
            print(
                f"\n{GREEN}[✓] {sig_sent} sent to "
                f"\"{proc_name}\" (PID {pid_target}).{RESET}")
        except psutil.NoSuchProcess:
            print(f"\n{YELLOW}[!] Process already exited.{RESET}")
        except psutil.AccessDenied:
            print(f"\n{RED}[X] Access Denied! Run with sudo.{RESET}")
        except Exception as e:
            logger.error(f"Unexpected error killing PID {pid_target}: {e}")
            print(f"\n{RED}[X] Error: {e}{RESET}")
        time.sleep(1.5)

    while True:
        psutil.cpu_percent(interval=0.1)
        clear_screen()

        procs = []
        for proc in psutil.process_iter(
                ['pid', 'name', 'memory_percent', 'cpu_percent', 'username']):
            try:
                procs.append(proc.info)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        total_procs = len(procs)
        running_count = sum(1 for p in procs if p.get('cpu_percent', 0) > 0)

        top_8 = sorted(
            procs,
            key=lambda x: x[sort_by] if x[sort_by] is not None else 0.0,
            reverse=True)[
            :8]
        visible_pids = {p['pid'] for p in top_8}
        total_ram = psutil.virtual_memory().total
        mode_text = "CPU USAGE" if sort_by == 'cpu_percent' else "MEMORY USAGE"

        # --- Header ---
        print(f"{CYAN}{BOLD}❯ PROCESS MANAGER — SORT: {mode_text}{RESET}")
        print()

        # --- Summary bar (improvement #8) ---
        print(
            f"{DIM}  Total: {WHITE}{total_procs}{RESET}{DIM}  |  "
            f"Active (CPU>0): {WHITE}{running_count}{RESET}{DIM}  |  "
            f"Sleeping: {WHITE}{total_procs - running_count}{RESET}\n")

        # --- Table ---
        print(
            f"{DIM}{
                '#':<3} | {
                'PID':<8} | {
                'RAM %':<8} | {
                    'RAM (MB)':<10} | {
                        'CPU %':<8} | {
                            'USER':<10} | {'Process Name'}{RESET}")
        print(f"{DIM}{'-' * 78}{RESET}")
        for i, p in enumerate(top_8, 1):
            user_val = (p['username'] or "N/A")[:10]
            cpu_val = p['cpu_percent'] or 0.0
            mem_val = p['memory_percent'] or 0.0
            ram_mb = (mem_val / 100 * total_ram) / (1024 ** 2)
            c = row_color(mem_val, cpu_val)   # color per row (improvement #3)
            print(f"{DIM}{i:<3}{RESET} | "
                  f"{c}{p['pid']:<8}{RESET} | "
                  f"{c}{mem_val:<8.1f}{RESET} | "
                  f"{c}{ram_mb:<10.1f}{RESET} | "
                  f"{c}{cpu_val:<8.1f}{RESET} | "
                  f"{c}{user_val:<10}{RESET} | "
                  f"{c}{p['name']}{RESET}")
        print(f"{DIM}{'-' * 78}{RESET}")

        # --- Controls ---
        print(f"{CYAN}Sort   : [m] Memory  [c] CPU{RESET}")
        print(
            f"{CYAN}Action : [1-8] Inspect  |  "
            f"[kill <#/PID>] SIGTERM  |  "
            f"[fkill <#/PID>] SIGKILL  |  [Enter] Main Menu{RESET}")

        flush_input()
        action = input(f"{GREEN}Choice : {RESET}").strip().lower()

        # --- Navigation ---
        if not action:
            break
        if action == 'm':
            sort_by = 'memory_percent'
            continue
        if action == 'c':
            sort_by = 'cpu_percent'
            continue

        # --- Kill by index or PID ---
        def resolve_target(raw, cmd):
            target_str = raw.replace(cmd, "").replace(
                "#/", "").replace("#", "").strip()
            if not target_str.isdigit():
                return None, None
            val = int(target_str)
            if 1 <= val <= len(top_8):
                return val, top_8[val - 1]['pid']
            return None, val

        if action.startswith("kill"):
            idx, pid = resolve_target(action, "kill")
            if idx is not None:
                p = top_8[idx - 1]
                clear_screen()
                print(f"\n{GREEN}{'='*60}{RESET}")
                print(f"{YELLOW}[!] About to KILL process #{idx}{RESET}")
                print(f"{GREEN}{'='*60}{RESET}")
                print(f"{YELLOW}Process Name      :{RESET} {p['name']}")
                print(f"{YELLOW}Process ID (PID)  :{RESET} {p['pid']}")
                print(f"{YELLOW}Process Owner     :{RESET} {p['username'] or 'N/A'}")  # noqa: E501
                print(f"{YELLOW}Memory Usage      :{RESET} {p['memory_percent'] or 0:.1f}%")  # noqa: E501
                print(f"{YELLOW}CPU Usage         :{RESET} {p['cpu_percent'] or 0:.1f}%")  # noqa: E501
                print(f"{GREEN}{'='*60}{RESET}")
                do_kill(pid, force=False)
            elif pid is not None:
                do_kill(pid, force=False)
            else:
                print(f"\n{RED}[!] Invalid format! Use: kill <#/PID>{RESET}")  # noqa: E501
                time.sleep(1.5)
            continue  # noqa: E501

        if action.startswith("fkill"):
            idx, pid = resolve_target(action, "fkill")
            if idx is not None:
                p = top_8[idx - 1]
                clear_screen()
                print(f"\n{RED}{'='*60}{RESET}")
                print(f"{RED}[!] About to FORCE KILL process #{idx}{RESET}")
                print(f"{RED}{'='*60}{RESET}")
                print(f"{YELLOW}Process Name      :{RESET} {p['name']}")
                print(f"{YELLOW}Process ID (PID)  :{RESET} {p['pid']}")
                print(f"{YELLOW}Process Owner     :{RESET} {p['username'] or 'N/A'}")  # noqa: E501
                print(f"{YELLOW}Memory Usage      :{RESET} {p['memory_percent'] or 0:.1f}%")  # noqa: E501
                print(f"{YELLOW}CPU Usage         :{RESET} {p['cpu_percent'] or 0:.1f}%")  # noqa: E501
                print(f"{RED}{'='*60}{RESET}")
                do_kill(pid, force=True)
            elif pid is not None:
                do_kill(pid, force=True)
            else:
                print(f"\n{RED}[!] Invalid format! Use: fkill <#/PID>{RESET}")
                time.sleep(1.5)
            continue

        # --- Inspect by index or PID ---
        if action.isdigit():
            idx = int(action)
            if not (1 <= idx <= len(top_8)):
                print(
                    f"{RED}[!] Invalid choice. Enter a number between 1 and {
                        len(top_8)}.{RESET}")
                time.sleep(1.5)
                continue
            pid_target = top_8[idx - 1]['pid']

            try:
                proc = psutil.Process(pid_target)

                try:
                    p_name = proc.name()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    p_name = "N/A"

                try:
                    p_user = proc.username()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    p_user = "Access Denied"

                try:
                    p_status = proc.status().upper()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    p_status = "N/A"

                try:
                    p_threads = proc.num_threads()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    p_threads = "N/A"

                try:
                    p_create_time = datetime.fromtimestamp(
                        proc.create_time()).strftime("%Y-%m-%d %H:%M:%S")
                except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
                    p_create_time = "N/A"

                try:
                    p_exe = proc.exe()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    p_exe = (
                        f"{RED}Access Denied{RESET} "
                        f"(Requires Real Root UID 0)")

                # Full command line (args) used to launch the process
                try:
                    p_cmdline = ' '.join(proc.cmdline()) or p_exe
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    p_cmdline = f"{RED}Access Denied{RESET}"

                # Number of file descriptors the process has open
                try:
                    p_open_files = len(proc.open_files())
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    p_open_files = "N/A"

                # Active network connections owned by this process
                try:
                    p_conns = len(proc.connections())
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    p_conns = "N/A"

                clear_screen()
                print(
                    f"\n{GREEN}{
                        '=' *
                        60}\n{
                        '  PROCESS INSPECTION REPORT ':^60}\n{
                        '=' *
                        60}{RESET}")
                print(f"{YELLOW}Process ID (PID)  :{RESET} {pid_target}")
                print(f"{YELLOW}Process Name      :{RESET} {p_name}")
                print(f"{YELLOW}Process Owner     :{RESET} {p_user}")
                print(f"{YELLOW}Current Status    :{RESET} {p_status}")
                print(f"{YELLOW}Total Threads     :{RESET} {p_threads}")
                print(f"{YELLOW}Started At        :{RESET} {p_create_time}")
                print(f"{YELLOW}Executable Path   :{RESET} {p_exe}")
                p_cmdline_display = (
                    p_cmdline if len(p_cmdline) <= 80
                    else p_cmdline[:80] + f"{DIM}...{RESET}")
                print(f"{YELLOW}Command Line      :{RESET} {p_cmdline_display}")  # noqa: E501
                print(f"{YELLOW}Open Files        :{RESET} {p_open_files}")
                print(f"{YELLOW}Network Conns     :{RESET} {p_conns}")

                if p_user == "root" and os.getuid() != 0:
                    print(
                        f"\n{YELLOW}[!] NOTE: Some details hidden — "
                        f"process belongs to Root.{RESET}")
                    print(
                        f"{YELLOW}    Run as: "
                        f"sudo python3 main.py for full access.{RESET}")

                print(f"\n{GREEN}{'=' * 60}{RESET}")
                print(
                    f"\n{YELLOW}Press Enter to resume "
                    f"live monitoring...{RESET}",
                    end="",
                    flush=True)
                wait_for_enter()

            except psutil.AccessDenied:
                print(
                    f"{RED}Access Denied! Run with real sudo "
                    f"to inspect this process.{RESET}")
                time.sleep(1.5)
            except psutil.NoSuchProcess:
                print(f"{RED}Process not found!{RESET}")
                time.sleep(1.5)
            except Exception as e:
                logger.error(f"Unexpected error inspecting process: {e}")
                print(f"{RED}Invalid choice!{RESET}")
                time.sleep(1.5)
        else:
            print(f"{RED}[!] Invalid choice.{RESET}")
            time.sleep(1.5)

# --- SECURITY AUDIT ---


def secure_stop_service(service_name):
    """Performs a 'Deep Neutralization' of a service."""
    if os.name != 'posix':
        return False
    if any(b in service_name for b in CRITICAL_BLACKLIST):
        logger.warning(
            f"Blocked attempt to neutralize blacklisted "
            f"service: {service_name}")
        return False
    try:
        scan_cmd = [
            'sudo',
            'systemctl',
            'list-unit-files',
            '--all',
            f"{service_name}*",
            '--no-legend']
        scan_res = subprocess.run(scan_cmd, capture_output=True, text=True)
        if scan_res.returncode != 0:
            return False
        units = []
        for line in scan_res.stdout.split('\n'):
            parts = line.split()
            if parts:
                u = parts[0]
                if any(
                    u.endswith(ext) for ext in [
                        '.service',
                        '.socket',
                        '.path',
                        '.timer']):
                    if not any(b in u for b in CRITICAL_BLACKLIST):
                        units.append(u)
        if not units:
            units = [f"{service_name}.service"]
        for unit in units:
            subprocess.run(['sudo', 'systemctl', 'stop', unit],
                           capture_output=True)
            subprocess.run(['sudo', 'systemctl', 'mask',
                           '--now', unit], capture_output=True)
        logger.info(f"Service neutralized: {service_name} (units: {units})")
        return True
    except Exception as e:
        logger.error(f"secure_stop_service({service_name}) failed: {e}")
        return False


def audit_ufw_firewall():
    """Audits UFW Firewall status and rules."""
    print(f"{CYAN}[*] Checking Firewall (UFW) Status...{RESET}")
    try:
        cmd = ['sudo', 'ufw', 'status']
        res = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=5.0)

        output = res.stdout.lower()
        if "inactive" in output:
            print(f"Status: {RED}● INACTIVE (System Unprotected){RESET}")
        elif "active" in output:
            print(f"Status: {GREEN}● ACTIVE (Secured){RESET}")
            rules = [line.strip()
                     for line in res.stdout.split('\n') if line.strip()][1:6]
            if rules:
                print(f"{YELLOW}Active Rules (Preview):{RESET}")
                for r in rules:
                    print(f"  {r}")
        else:
            print(f"Status: {RED}Unknown / Permission Denied{RESET}")
    except Exception as e:
        print(f"{RED}Could not check UFW: {e}{RESET}")


def audit_open_ports():
    print(f"{CYAN}[*] Auditing Network Connections & Sockets...{RESET}")
    try:
        def parse_ss_line(line):
            # Extract process name from ss output (handles variable columns)
            process = "Unknown"
            proc_match = re.search(r'users:\(\("([^"]+)"', line)
            if proc_match:
                process = proc_match.group(1)

            # Strip user info to extract local/remote addresses
            clean_line = re.sub(r'users:.*', '', line).strip()
            parts = re.split(r'\s+', clean_line)
            addrs = [p for p in parts if ":" in p]

            local = addrs[0] if len(addrs) > 0 else "N/A"
            peer = addrs[1] if len(addrs) > 1 else "N/A"

            return {
                "process": process,
                "local": local,
                "peer": peer,
                "parts": parts}

        # SECTION 1: LISTENING SERVICES
        print(f"\n{YELLOW}  [!] LISTENING SERVICES (Incoming Ports){RESET}")
        cmd_l = ['sudo', 'ss', '-ltupn']
        res_l = subprocess.run(
            cmd_l,
            capture_output=True,
            text=True,
            timeout=5.0)

        if res_l.returncode == 0:
            lines = res_l.stdout.strip().split('\n')
            if len(lines) <= 1:
                print(f"    {GREEN}● No listening ports found.{RESET}")
            else:
                print(
                    f"    {
                        'PROTO':<8} | {
                        'LOCAL ADDRESS':<25} | {'SERVICE / PID'}")
                print(f"    {'-' * 61}")
                for line in lines[1:]:
                    data = parse_ss_line(line)
                    proto = data['parts'][0].upper(
                    ) if data['parts'] else "TCP"

                    if (data['local'].startswith('0.0.0.0:')
                            or data['local'].startswith('[::]:')
                            or data['local'].startswith('*:')):
                        print(
                            f"    {
                                proto:<8} | {RED}{
                                data['local']:<25}{RESET} | {YELLOW}{
                                data['process']}{RESET}")
                    else:
                        print(
                            f"    {
                                proto:<8} | {
                                data['local']:<25} | {
                                data['process']}")

        # SECTION 2: ACTIVE CONNECTIONS
        print(
            f"\n{YELLOW}  [>] ACTIVE USER APPLICATIONS "
            f"(Outgoing Traffic){RESET}")
        cmd_a = ['sudo', 'ss', '-atpn']
        res_a = subprocess.run(
            cmd_a,
            capture_output=True,
            text=True,
            timeout=5.0)

        if res_a.returncode == 0:
            lines = res_a.stdout.strip().split('\n')
            established = [line for line in lines if 'ESTAB' in line]

            if not established:
                print(f"    {GREEN}● No active user connections found.{RESET}")
            else:
                print(
                    f"    {
                        'APPLICATION':<15} | {
                        'LOCAL IP':<25} | {'REMOTE ADDRESS'}")
                print(f"    {'-' * 61}")
                for line in established[:15]:
                    data = parse_ss_line(line)
                    app_color = (
                        GREEN if any(
                            b in data['process'].lower()
                            for b in ['brave', 'chrome', 'firefox', 'browser'])
                        else RESET)
                    print(
                        f"    {app_color}{
                            data['process']:<15}{RESET} | {
                            data['local']:<25} | {
                            data['peer']}")
                if len(established) > 15:
                    print(
                        f"    {YELLOW}... and {
                            len(established) -
                            15} more active connections.{RESET}")

    except Exception as e:
        print(f"{RED}Error auditing sockets: {e}{RESET}")


def audit_arp_table():
    """Display ARP table to detect unknown devices on the local network."""
    print(f"{CYAN}{BOLD}❯ ARP TABLE — LOCAL NETWORK DEVICES{RESET}")
    try:
        res = subprocess.run(
            ['arp', '-n'], capture_output=True, text=True, timeout=5.0)
        lines = [
            line for line in res.stdout.strip().split('\n')
            if line and 'Address' not in line and 'incomplete' not in line
        ]

        if not lines:
            print(f"  {WARN} ARP table is empty or could not be read.{RESET}")
        else:
            print(
                f"  {DIM}{
                    'IP ADDRESS':<18} {
                    'MAC ADDRESS':<20} {'INTERFACE'}{RESET}")
            print(f"  {DIM}{'-' * (TERMINAL_WIDTH - 2)}{RESET}")
            for line in lines:
                parts = line.split()
                if len(parts) >= 5:
                    ip = parts[0]
                    mac = parts[2]
                    iface = parts[4]
                    # Flag broadcast/multicast MACs
                    flag = f" {YELLOW}[Broadcast]{RESET}" if mac.startswith(
                        'ff:ff') else ""
                    print(
                        f"  {WHITE}{
                            ip:<18}{RESET} {CYAN}{
                            mac:<20}{RESET} {DIM}{iface}{RESET}{flag}")
            print(f"\n  {DIM}Total devices seen: {WHITE}{len(lines)}{RESET}")
            print(
                f"  {YELLOW}[!] Unrecognized MAC addresses may indicate "
                f"unknown devices on your network.{RESET}")
    except FileNotFoundError:
        print(
            f"  {WARN} 'arp' command not found. "
            f"Install via: sudo apt install net-tools{RESET}")
    except Exception as e:
        logger.debug(f"audit_arp_table failed: {e}")
        print(f"  {RED}Could not read ARP table.{RESET}")
    print(f"{DIM}{'-' * TERMINAL_WIDTH}{RESET}")


def audit_dns_servers():
    """Check configured DNS servers for suspicious or unexpected entries."""
    print(f"{CYAN}{BOLD}❯ DNS SERVER AUDIT{RESET}")
    # Well-known trusted DNS servers
    TRUSTED_DNS = {
        '8.8.8.8': 'Google DNS',
        '8.8.4.4': 'Google DNS',
        '1.1.1.1': 'Cloudflare DNS',
        '1.0.0.1': 'Cloudflare DNS',
        '9.9.9.9': 'Quad9 DNS',
        '149.112.112.112': 'Quad9 DNS',
        '208.67.222.222': 'OpenDNS',
        '208.67.220.220': 'OpenDNS',
        '127.0.0.53': 'systemd-resolved (local)',
        '127.0.0.1': 'Localhost resolver',
    }
    try:
        dns_servers = []

        # Method 1: resolvectl (preferred — shows active DNS per interface)
        try:
            res = subprocess.run(
                ['resolvectl', 'status'],
                capture_output=True, text=True, timeout=5.0
            )
            for line in res.stdout.split('\n'):
                if 'Current DNS Server' in line:
                    m = re.search(r'Current DNS Server:\s+(\S+)', line)
                    if m and m.group(1) not in dns_servers:
                        dns_servers.append(m.group(1))
        except Exception:
            pass

        # Method 2: /etc/resolv.conf as fallback
        if not dns_servers:
            try:
                with open('/etc/resolv.conf', 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith('nameserver'):
                            parts = line.split()
                            if len(parts) >= 2 and parts[1] not in dns_servers:
                                dns_servers.append(parts[1])
            except Exception:
                pass

        if not dns_servers:
            print(f"  {WARN} Could not detect DNS servers.{RESET}")
        else:
            print(
                f"  {DIM}{
                    'DNS SERVER':<20} {
                    'STATUS':<12} {'PROVIDER'}{RESET}")
            print(f"  {DIM}{'-' * (TERMINAL_WIDTH - 2)}{RESET}")
            any_suspicious = False
            for dns in dns_servers:
                # Check private IP ranges (router/local DNS — normal behaviour)
                is_private = (
                    dns.startswith('10.') or
                    dns.startswith('192.168.') or
                    dns.startswith('172.16.') or
                    dns.startswith('172.17.') or
                    dns.startswith('172.18.') or
                    dns.startswith('172.19.') or
                    dns.startswith('172.2') or
                    dns.startswith('172.30.') or
                    dns.startswith('172.31.') or
                    dns in ('127.0.0.1', '127.0.0.53')
                )
                if dns in TRUSTED_DNS:
                    label = TRUSTED_DNS[dns]
                    status = f"{OK} Trusted "
                elif is_private:
                    label = "Local Router / Private DNS (normal)"
                    status = f"{OK} Local   "
                else:
                    label = "Unknown — verify this manually!"
                    status = f"{FAIL} SUSPICIOUS"
                    any_suspicious = True
                print(
                    f"  {WHITE}{dns:<20}{RESET} "
                    f"{status:<12} "
                    f"{YELLOW if (dns not in TRUSTED_DNS and not is_private) else DIM}"  # noqa: E501
                    f"{label}{RESET}")

            if any_suspicious:
                print(f"\n  {RED}[!] Unknown DNS server detected!{RESET}")
                print(
                    f"  {YELLOW}    This could indicate DNS hijacking "
                    f"or misconfiguration.{RESET}")
                print(
                    f"  {YELLOW}    Check /etc/resolv.conf and "
                    f"your router settings.{RESET}")
            else:
                print(
                    f"\n  {OK} All DNS servers are from "
                    f"trusted providers.{RESET}")

    except Exception as e:
        logger.debug(f"audit_dns_servers failed: {e}")
        print(f"  {RED}Could not audit DNS servers.{RESET}")
    print(f"{DIM}{'-' * TERMINAL_WIDTH}{RESET}")


def show_network_audit():
    clear_screen()
    print(f"{CYAN}{BOLD}❯ NETWORK DIAGNOSTICS & SECURITY AUDIT{RESET}\n")
    if not check_sudo():
        print(f"\n{RED}[!] Audit Aborted.{RESET}")
        time.sleep(1.5)
        return
    with terminal_manager(echo=False):
        audit_ufw_firewall()
        print(f"{DIM}{"-" * TERMINAL_WIDTH}{RESET}")
        show_network_status()
        print(f"{DIM}{"-" * TERMINAL_WIDTH}{RESET}")
        audit_open_ports()
        print(f"{DIM}{"-" * TERMINAL_WIDTH}{RESET}")
        audit_arp_table()
        audit_dns_servers()
    print(f"{DIM}{"-" * TERMINAL_WIDTH}{RESET}")
    print(f"\n{YELLOW}Press [Enter] to return...{RESET}", end="", flush=True)
    wait_for_enter()


def audit_ssh_security():
    clear_screen()
    print(f"{CYAN}{BOLD}❯ SSH DEEP SECURITY & HARDENING AUDIT{RESET}\n")
    if not check_sudo():
        print(f"\n{RED}[!] Audit Aborted.{RESET}")
        time.sleep(1.5)
        return

    # 1. Check Service Status
    print(f"{CYAN}[*] Checking SSH Service Status...{RESET}")
    try:
        status_check = subprocess.run(
            ['systemctl', 'is-active', 'ssh'],
            stdout=subprocess.PIPE, text=True)
        if status_check.stdout.strip() != "active":
            print(
                f"Service Status: {RED}● INACTIVE "
                f"(Offline / Secured from Network){RESET}")
            print(
                f"{YELLOW}[!] Notice: Analyzing configuration for "
                f"future risk mitigation...{RESET}")
        else:
            print(
                f"Service Status: {GREEN}● ACTIVE "
                f"(Listening for connections){RESET}")
    except Exception as e:
        logger.debug(f"SSH service status check failed: {e}")
        print(f"Service Status: {RED}Unknown.{RESET}")

    print(f"{DIM}{'-' * TERMINAL_WIDTH}{RESET}")

    # 2. Analyze Configuration
    with terminal_manager(echo=False):
        print(f"{CYAN}[*] Analyzing SSH configuration files...{RESET}")
        try:
            # Precedence: Settings in Include files (like .d/*.conf) usually
            # take effect first
            config_files = []
            config_d = '/etc/ssh/sshd_config.d/'
            if os.name == 'posix':
                if os.path.exists(config_d):
                    try:
                        for f in sorted(os.listdir(config_d)):
                            if f.endswith('.conf'):
                                config_files.append(os.path.join(config_d, f))
                    except OSError as e:
                        logger.debug(f"Could not list sshd_config.d: {e}")
            config_files.append('/etc/ssh/sshd_config')

            content = ""
            scanned = []
            res = subprocess.run(['sudo',
                                  'cat'] + config_files,
                                 stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE,
                                 text=True)
            if res.returncode == 0:
                content = res.stdout
                scanned = [os.path.basename(fp) for fp in config_files]
            else:
                for fp in config_files:
                    res = subprocess.run(
                        ['sudo', 'cat', fp],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE, text=True)
                    if res.returncode == 0:
                        content += f"\n# --- FILE: {fp} ---\n" + res.stdout
                        scanned.append(os.path.basename(fp))

            if scanned:
                print(
                    f"{GREEN}[✓] Scanned {
                        len(scanned)} config file(s).{RESET}")

                def get_smart_val(key):
                    active, comment = None, None
                    pattern = re.compile(
                        rf"^\s*(#?)\s*({key})\s+([^\s#]+)", re.I | re.M)
                    for m in pattern.finditer(content):
                        # Use lower() for safe comparisons
                        val = m.group(3).lower()
                        if m.group(1) == '':
                            active = val
                            break  # SSH uses the FIRST active occurrence
                        elif comment is None:
                            comment = val
                    return active or comment, active is not None

                v_port, a_port = get_smart_val("Port")
                v_root, a_root = get_smart_val("PermitRootLogin")
                v_pwd, a_pwd = get_smart_val("PasswordAuthentication")
                v_empty, a_empty = get_smart_val("PermitEmptyPasswords")
                v_tries, a_tries = get_smart_val("MaxAuthTries")
                v_x11, a_x11 = get_smart_val("X11Forwarding")
                v_idle, a_idle = get_smart_val("ClientAliveInterval")
                v_strict, a_strict = get_smart_val("StrictModes")
                v_grace, a_grace = get_smart_val("LoginGraceTime")
                v_rhosts, a_rhosts = get_smart_val("IgnoreRhosts")
                v_sess, a_sess = get_smart_val("MaxSessions")

                print(f"{'CHECK':<25} | {'VALUE':<20} | {'STATUS'}")
                print(f"{DIM}{'-' * TERMINAL_WIDTH}{RESET}")

                def print_audit_row(label, value, status, recommendation=None):
                    print(f"{label:<25} | {str(value):<20} | {status}")
                    if recommendation and "[ SECURE  ]" not in status:
                        print(
                            f"  {YELLOW}→{RESET} {WHITE}"
                            f"{recommendation}{RESET}")

                p_val = v_port or "22"
                p_status = (
                    f"{GREEN}[ SECURE  ]{RESET}" if p_val != '22'
                    else f"{YELLOW}[ WARNING ]{RESET}")
                print_audit_row(
                    "SSH Port", p_val, p_status,
                    "Use a non-standard port (e.g., 2222) "
                    "to avoid automated brute-force bots.")

                r_val = v_root or 'prohibit-password'
                r_status = (
                    f"{GREEN}[ SECURE  ]{RESET}" if r_val == 'no'
                    else f"{YELLOW}[ WARNING ]{RESET}")
                print_audit_row(
                    "Permit Root Login", r_val, r_status,
                    "Set to 'no' to force login via a standard user and sudo.")

                pw_val = v_pwd or 'yes'
                pw_status = (
                    f"{GREEN}[ SECURE  ]{RESET}" if pw_val == 'no'
                    else f"{YELLOW}[  RISK   ]{RESET}")
                print_audit_row(
                    "Password Auth", pw_val, pw_status,
                    "Disable password auth and use SSH Keys "
                    "(Ed25519) for much higher security.")

                e_val = v_empty or "no"
                e_status = (
                    f"{GREEN}[ SECURE  ]{RESET}" if e_val == 'no'
                    else f"{RED}[  RISK   ]{RESET}")
                print_audit_row(
                    "Empty Passwords", e_val, e_status,
                    "CRITICAL: Set to 'no' immediately "
                    "to prevent passwordless entry.")

                rh_val = v_rhosts or "no"
                rh_status = (
                    f"{GREEN}[ SECURE  ]{RESET}" if rh_val == 'yes'
                    else f"{RED}[  RISK   ]{RESET}")
                print_audit_row(
                    "Ignore Rhosts", rh_val, rh_status,
                    "Set to 'yes' to ignore legacy insecure .rhosts files.")

                s_val = int(v_sess) if (v_sess and v_sess.isdigit()) else 10
                if s_val <= 2:
                    s_status = f"{GREEN}[ SECURE  ]{RESET}"
                elif s_val <= 10:
                    s_status = f"{YELLOW}[ WARNING ]{RESET}"
                else:
                    s_status = f"{RED}[  RISK   ]{RESET}"
                print_audit_row(
                    "Max Sessions", str(s_val), s_status,
                    "Reduce to 2 to prevent "
                    "connection exhaustion attacks.")

                x_val = v_x11 or 'no'
                x_status = (
                    f"{GREEN}[ SECURE  ]{RESET}" if x_val == 'no'
                    else f"{YELLOW}[  RISK   ]{RESET}")
                print_audit_row(
                    "X11 Forwarding", x_val, x_status,
                    "Set to 'no' unless you specifically "
                    "need remote GUI applications.")

                idle_timeout_str = v_idle or "0"
                idle_val = int(
                    idle_timeout_str) if idle_timeout_str.isdigit() else 0
                idle_status = f"{GREEN}[ SECURE  ]{RESET}" if (
                    0 < idle_val <= 300) else f"{YELLOW}[ WARNING ]{RESET}"
                print_audit_row(
                    "Idle Timeout (Sec)", idle_timeout_str, idle_status,
                    "Set ClientAliveInterval to 300 (5 mins) "
                    "to auto-kick idle users.")

                m_val = v_strict or 'yes'
                m_status = (
                    f"{GREEN}[ SECURE  ]{RESET}" if m_val == 'yes'
                    else f"{RED}[  RISK   ]{RESET}")
                print_audit_row(
                    "Strict Modes", m_val, m_status,
                    "Set to 'yes' to ensure SSH checks "
                    "directory permissions before login.")

                g_val = int(v_grace) if v_grace and v_grace.isdigit() else 120
                g_status = (
                    f"{GREEN}[ SECURE  ]{RESET}" if g_val <= 60
                    else f"{YELLOW}[ WARNING ]{RESET}")
                print_audit_row(
                    "Login Grace Time", str(g_val), g_status,
                    "Reduce to 60 seconds to stop "
                    "unauthenticated connection hangs.")

                t_val = int(v_tries) if v_tries and v_tries.isdigit() else 6
                t_status = (
                    f"{GREEN}[ SECURE  ]{RESET}" if t_val <= 4
                    else f"{YELLOW}[ MODERATE ]{RESET}")
                print_audit_row(
                    "Max Auth Tries", str(t_val), t_status,
                    "Set to 3 or 4 to quickly "
                    "lock out brute-force attempts.")

                print(f"{DIM}{'-' * TERMINAL_WIDTH}{RESET}")

                # --- Brute-Force Protection Detection ---
                print(
                    f"{CYAN}[*] Checking for Brute-Force Protection "
                    f"(Fail2Ban/CrowdSec)...{RESET}")

                def check_svc_active(svc_name):
                    try:
                        r = subprocess.run(
                            ['systemctl', 'is-active', svc_name],
                            capture_output=True, text=True, timeout=2)
                        return r.stdout.strip() == 'active'
                    except Exception:
                        return False

                f2b_active = check_svc_active('fail2ban')
                cs_active = check_svc_active('crowdsec')

                if f2b_active:
                    print(
                        f"{'Fail2Ban Service':<25} | "
                        f"{GREEN}● ACTIVE{RESET}             | "
                        f"{GREEN}[ SECURE  ]{RESET}")
                elif cs_active:
                    print(
                        f"{'CrowdSec Service':<25} | "
                        f"{GREEN}● ACTIVE{RESET}             | "
                        f"{GREEN}[ SECURE  ]{RESET}")
                else:
                    print(
                        f"{'Brute-Force Prot.':<25} | "
                        f"{RED}● NOT DETECTED{RESET}       | "
                        f"{RED}[  RISK   ]{RESET}")
                    print(
                        f"  {YELLOW}→{RESET} {WHITE}Install Fail2Ban "
                        f"to auto-block brute-force bots.{RESET}")
                    print(
                        f"     {DIM}Quick: sudo apt install fail2ban{RESET}")

                # --- Two-Factor Authentication Detection ---
                print(
                    f"{CYAN}[*] Checking for "
                    f"Two-Factor Authentication (2FA)...{RESET}")

                two_fa_active = False
                try:
                    pam_res = subprocess.run(
                        ['sudo', 'grep', '-q',
                         'pam_google_authenticator.so', '/etc/pam.d/sshd'],
                        timeout=2)
                    v_kbd, a_kbd = get_smart_val(
                        "KbdInteractiveAuthentication")
                    v_chall, a_chall = get_smart_val(
                        "ChallengeResponseAuthentication")
                    is_pam_ready = pam_res.returncode == 0
                    is_ssh_ready = (
                        (v_kbd or v_chall) == 'yes')
                    two_fa_active = is_pam_ready and is_ssh_ready
                except Exception:
                    pass

                if two_fa_active:
                    print(
                        f"{'Two-Factor Auth':<25} | "
                        f"{GREEN}● CONFIGURED{RESET}         | "
                        f"{GREEN}[ SECURE  ]{RESET}")
                else:
                    print(
                        f"{'Two-Factor Auth':<25} | "
                        f"{RED}● NOT CONFIGURED{RESET}     | "
                        f"{RED}[  RISK   ]{RESET}")
                    print(
                        f"  {YELLOW}→{RESET} {WHITE}Enable 2FA "
                        f"(e.g., Google Authenticator) "
                        f"for a major security boost.{RESET}")

                # --- Summary ---
                print(f"\n{DIM}{'-' * TERMINAL_WIDTH}{RESET}")
                all_secure = all(
                    "[ SECURE  ]" in s
                    for s in [p_status, r_status, pw_status, e_status,
                              rh_status, s_status, x_status, idle_status,
                              m_status, g_status, t_status]
                ) and (f2b_active or cs_active) and two_fa_active
                if all_secure:
                    print(
                        f"{OK} {GREEN}Excellent! SSH configuration "
                        f"meets high security standards.{RESET}")
                else:
                    print(
                        f"{YELLOW}[!] Audit complete. Follow "
                        f"recommendations above to harden "
                        f"your SSH service.{RESET}")

            else:
                print(f"{RED}[!] Error reading config file.{RESET}")
        except Exception as e:
            print(f"{RED}[X] Error: {e}{RESET}")

    print(f"{DIM}{'-' * TERMINAL_WIDTH}{RESET}")
    print(f"\n{YELLOW}Press Enter to return...{RESET}", end="", flush=True)
    wait_for_enter()


def optimize_services():
    clear_screen()
    print(f"{CYAN}{BOLD}❯ SYSTEM SERVICE OPTIMIZER{RESET}\n")
    if not check_sudo():
        print(f"\n{RED}[!] Optimization Aborted.{RESET}")
        time.sleep(1.5)
        return

    # Detailed service catalog with educational descriptions
    services = {
        "bluetooth": {
            "desc": "Manages wireless connections for headsets, mice, and keyboards. "  # noqa: E501
                    "Disable if you only use wired devices to save power and improve "  # noqa: E501
                    "security.",
            "safety": f"{YELLOW}⚠️  CAUTION.{RESET}"
        },
        "cups": {
            "desc": "The Common Unix Printing System. Responsible for all local and "  # noqa: E501
                    "network printing tasks. Disable only if this machine never "  # noqa: E501
                    "needs to print documents.",
            "safety": f"{YELLOW}⚠️  CAUTION.{RESET}"
        },
        "cups-browsed": {
            "desc": "A sub-service of CUPS that automatically 'discovers' and adds "  # noqa: E501
                    "new printers found on your network. Safe to disable if you "  # noqa: E501
                    "manually add printers.",
            "safety": f"{GREEN}✅ SAFE.{RESET}"
        },
        "avahi-daemon": {
            "desc": "Implements Zeroconf networking (mDNS/DNS-SD), allowing your PC "  # noqa: E501
                    "to find local services like Apple AirPlay or Chromecast "
                    "without a DNS server. Disable to reduce network noise.",
            "safety": f"{GREEN}✅ SAFE.{RESET}"
        },
        "whoopsie": {
            "desc": "Ubuntu's crash reporting submission daemon. It uploads 'oops' "  # noqa: E501
                    "data to Canonical when a program fails. Safe to disable; "
                    "does not affect system stability.",
            "safety": f"{GREEN}✅ VERY SAFE.{RESET}"
        },
        "geoclue": {
            "desc": "Location-aware service that provides your coordinates to apps "  # noqa: E501
                    "like GNOME Maps or Weather. Disable if you prefer privacy "  # noqa: E501
                    "or don't use location-based apps.",
            "safety": f"{GREEN}✅ VERY SAFE.{RESET}"
        },
        "ModemManager": {
            "desc": "Controls 2G/3G/4G/5G mobile broadband modems (USB dongles or "  # noqa: E501
                    "built-in SIM slots). Safe to disable if you only use "
                    "Ethernet or Wi-Fi.",
            "safety": f"{GREEN}✅ SAFE.{RESET}"
        },
        "colord": {
            "desc": "Manages color profiles for monitors, printers, and scanners. "  # noqa: E501
                    "Essential for photographers/designers; safe to disable for "  # noqa: E501
                    "general server or coding use.",
            "safety": f"{GREEN}✅ SAFE.{RESET}"
        },
        "chrony": {
            "desc": "An implementation of the Network Time Protocol (NTP). It keeps "  # noqa: E501
                    "your system clock perfectly synchronized. Only disable if "  # noqa: E501
                    "you have another time sync tool.",
            "safety": f"{GREEN}✅ SAFE.{RESET}"
        },
        "snap.canonical-livepatch.canonical-livepatch": {
            "desc": "Enables applying critical Linux kernel security updates without "  # noqa: E501
                    "rebooting. Safe to disable, but you will need to manually "  # noqa: E501
                    "reboot more often for updates.",
            "safety": f"{GREEN}✅ SAFE.{RESET}"
        },
        "apport": {
            "desc": "The system that generates the 'A problem has occurred' pop-up "  # noqa: E501
                    "windows. It collects debug data for developers. Safe to "
                    "disable to stop annoying pop-ups.",
            "safety": f"{GREEN}✅ VERY SAFE.{RESET}"
        },
        "kerneloops": {
            "desc": "Specifically tracks and reports Linux kernel 'oopses' (minor "  # noqa: E501
                    "crashes) to a central database. Safe to disable.",
            "safety": f"{GREEN}✅ VERY SAFE.{RESET}"
        },
        "multipathd": {
            "desc": "Used for managing multiple paths to storage devices (typical in "  # noqa: E501
                    "high-end Enterprise SANs). Completely unnecessary for almost "  # noqa: E501
                    "all home or desktop users.",
            "safety": f"{GREEN}✅ SAFE.{RESET}"
        },
        "power-profiles-daemon": {
            "desc": "Allows you to switch between 'Power Saver', 'Balanced', and "  # noqa: E501
                    "'Performance' modes in your desktop settings. Disable with "  # noqa: E501
                    "caution on laptops.",
            "safety": f"{YELLOW}⚠️  CAUTION.{RESET}"
        },
        "switcheroo-control": {
            "desc": "Used on laptops with two graphics cards (e.g., Intel + NVIDIA) "  # noqa: E501
                    "to switch between them for power saving. Disable only if "
                    "you have a single GPU.",
            "safety": f"{GREEN}✅ SAFE.{RESET}"
        },
        "apt-news.service": {
            "desc": "A small service that fetches news and announcements about "  # noqa: E501
                    "Ubuntu updates to show in your terminal. Very safe to "
                    "disable to keep terminal clean.",
            "safety": f"{GREEN}✅ VERY SAFE.{RESET}"
        },
        "motd-news.service": {
            "desc": "Shows news and promotional messages in the 'Message of the Day' "  # noqa: E501
                    "when you first log in to a terminal. Very safe to disable.",  # noqa: E501
            "safety": f"{GREEN}✅ VERY SAFE.{RESET}"
        },
        "gnome-remote-desktop": {
            "desc": "Allows you to remotely control your screen using the RDP or VNC "  # noqa: E501
                    "protocols. Disable to prevent anyone from remotely accessing "  # noqa: E501
                    "your desktop.",
            "safety": f"{GREEN}✅ SAFE.{RESET}"
        }
    }
    active = []
    with terminal_manager(echo=False):
        print(f"{CYAN}[*] Scanning for services...{RESET}\n")
        for s in services.keys():
            if subprocess.run(
                    ['systemctl', 'is-active', '--quiet', s]).returncode == 0:
                active.append(s)
    if not active:
        print(f"{GREEN}[✓] No target services running.{RESET}")
        print(
            f"\n{YELLOW}Press [Enter] to return...{RESET}",
            end="",
            flush=True)
        wait_for_enter()
        return
    print(f"{'#':<3} | {'SERVICE NAME':<30} | {'STATUS'}")
    print(f"{DIM}{"-" * TERMINAL_WIDTH}{RESET}")
    for i, s in enumerate(active, 1):
        print(f"{i:<3} | {s:<30} | {GREEN}RUNNING{RESET}")
    print(f"\n{CYAN}Options: [Number] for details | [Enter] to return{RESET}")
    flush_input()
    choice = input(f"{GREEN}Choice : {RESET}").strip()
    if choice.isdigit() and 1 <= int(choice) <= len(active):
        t = active[int(choice) - 1]
        info = services[t]
        clear_screen()
        print(
            f"{YELLOW}--- {t.upper()} ---{RESET}\n\n"
            f"Desc: {info['desc']}\nSafety: {info['safety']}\n")
        print(f"{DIM}{"-" * TERMINAL_WIDTH}{RESET}")
        print(f"{RED}{BOLD}  ⚠  WARNING — DEEP NEUTRALIZATION{RESET}")
        print(f"{WHITE}  This will perform TWO permanent actions:{RESET}")
        print(
            f"  {RED}1. STOP{RESET}    — Kills the service "
            f"immediately right now.")
        print(f"  {RED}2. MASK{RESET}    — Blocks it from EVER "
              f"starting again,")
        print("             even after a system reboot.")
        print(f"\n  {YELLOW}To undo this later, you must manually run:{RESET}")
        print(
            f"  {DIM}sudo systemctl unmask {t} && "
            f"sudo systemctl enable {t}{RESET}")
        print(f"\n{DIM}{"-" * TERMINAL_WIDTH}{RESET}")
        if get_confirmation(
                f"{RED}[!] I UNDERSTAND — PROCEED WITH PERMANENT "
                f"NEUTRALIZATION? (y/N): {RESET}"):
            print(f"\n{CYAN}[*] Neutralizing {t}...{RESET}")
            if secure_stop_service(t):
                logger.info(f"User neutralized service: {t}")
                print(f"\n{GREEN}[✓] Neutralized.{RESET}")
            else:
                logger.error(f"Failed to neutralize service: {t}")
                print(f"\n{RED}[X] Error.{RESET}")
            print(
                f"\n{YELLOW}Press [Enter] to return...{RESET}",
                end="",
                flush=True)
            wait_for_enter()
        else:
            print(f"\n{YELLOW}[*] Cancelled.{RESET}")
            time.sleep(1.2)
    else:
        if choice != "":
            print(f"\n{RED}[!] Invalid choice.{RESET}")
            time.sleep(1.2)

# --- STARTUP & MAIN ---


def print_startup_message():
    if os.name == 'posix':
        if os.getuid() != 0:
            set_echo(True)

            cols = shutil.get_terminal_size().columns
            pad = ' ' * max(0, (cols - TERMINAL_WIDTH) // 2)

            print(f"\n{pad}{DIM}{'─' * TERMINAL_WIDTH}{RESET}")
            print(f"\n{pad}  {CYAN}{BOLD}VAULTCTL — Privilege Setup{RESET}")
            print(
                f"{pad}  {DIM}Root access unlocks: "
                f"SSH Audit · Firewall · Service Control{RESET}\n")
            user_agreed = get_confirmation(
                f"{pad}  {CYAN}❯{RESET} Enable root? "
                f"{DIM}(y/N){RESET}: ")

            if user_agreed:
                print(f"\n{pad}  {DIM}Authenticating...{RESET}")
                subprocess.run(['sudo', '-v'], check=False)

            clear_screen()
            has_cache_final = subprocess.run(
                ['sudo', '-n', 'true'], capture_output=True
            ).returncode == 0

            print(f"\n{pad}{DIM}{'─' * TERMINAL_WIDTH}{RESET}\n")
            if has_cache_final:
                if user_agreed:
                    print(
                        f"{pad}  {GREEN}✓{RESET}  {WHITE}"
                        f"Authenticated — Full access enabled{RESET}")
                    logger.info("Session started: authenticated with sudo.")
                else:
                    print(
                        f"{pad}  {GREEN}✓{RESET}  {WHITE}"
                        f"Active sudo session detected — "
                        f"Full access available{RESET}")
                    logger.info(
                        "Session started: pre-existing sudo cache detected.")
            else:
                print(
                    f"{pad}  {YELLOW}⚠{RESET}  {WHITE}"
                    f"Standard user mode{RESET}  {DIM}"
                    f"— Some features restricted{RESET}")
                logger.info(
                    "Session started: standard user mode (no sudo cache).")
            print(
                f"\n{pad}{DIM}{'─' * TERMINAL_WIDTH}{RESET}\n")  # noqa: E501

        else:
            cols = shutil.get_terminal_size().columns
            pad = ' ' * max(0, (cols - TERMINAL_WIDTH) // 2)
            print(
                f"\n{pad}  {GREEN}✓{RESET}  {WHITE}"
                f"Running as Root (UID 0) — Full access{RESET}")
            logger.info("Session started: running as real root (UID 0).")
    else:
        print(f"\n  {YELLOW}⚠{RESET}  {WHITE}Standard user mode{RESET}")
        logger.info("Session started: non-POSIX system, standard user mode.")
    time.sleep(2.0)
    flush_input()
    clear_screen()
    set_echo(True)


def header():
    columns = shutil.get_terminal_size().columns
    LOGO_WIDTH = 65

    logo_lines = [
        '██╗   ██╗ █████╗ ██╗   ██╗██╗  ████████╗ ██████╗████████╗██╗',
        '██║   ██║██╔══██╗██║   ██║██║  ╚══██╔══╝██╔════╝╚══██╔══╝██║',
        '██║   ██║███████║██║   ██║██║     ██║   ██║        ██║   ██║',
        '╚██╗ ██╔╝██╔══██║██║   ██║██║     ██║   ██║        ██║   ██║',
        ' ╚████╔╝ ██║  ██║╚██████╔╝███████╗██║   ╚██████╗   ██║   ███████╗',
        '  ╚═══╝  ╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝    ╚═════╝   ╚═╝   ╚══════╝',
    ]

    tool_name = '[ VAULTCTL — Secure System Control ]\n'
    slogan = 'Know Your System. Own Your Security.\n'
    credits = '(Developed by Nasser)'
    bar = '-' * min(columns, 70)

    def center(text):
        text = text[:columns]
        pad = max(0, (columns - len(text)) // 2)
        return ' ' * pad + text

    print(f"{RED}")

    if columns >= LOGO_WIDTH:
        pad = ' ' * (max(0, (columns - LOGO_WIDTH) // 2) + 2)
        for line in logo_lines:
            print(f"{pad}{line}")
    else:
        print(center('[ VAULTCTL ]'))

    print(f"{RESET}")
    print(f"{CYAN}{center(tool_name)}{RESET}")
    print(f"{YELLOW}{center(slogan)}{RESET}")
    print(f"{WHITE}{center(credits)}{RESET}")
    print(f"{RED}{center(bar)}{RESET}\n")


def main():
    logger.info("=== Diagnostic Tool started ===")
    print_startup_message()
    try:
        while True:
            clear_screen()
            header()

            cols = shutil.get_terminal_size().columns
            pad = ' ' * max(0, (cols - TERMINAL_WIDTH) // 2)

            print(f"{pad}{DIM}{'─' * TERMINAL_WIDTH}{RESET}")
            print(f"{pad}{'MAIN MENU':^{TERMINAL_WIDTH}}")
            print(f"{pad}{DIM}{'─' * TERMINAL_WIDTH}{RESET}")
            print()
            print(
                f"{pad}  {CYAN}[1]{RESET}  {WHITE}"
                f"Full System Scan{RESET}              "
                f"{DIM}CPU · RAM · Disk · Battery · +More{RESET}")
            print()
            print(
                f"{pad}  {CYAN}[2]{RESET}  {WHITE}"
                f"Live Process Manager{RESET}          "
                f"{DIM}Monitor & Kill Processes{RESET}")
            print()
            print(
                f"{pad}  {CYAN}[3]{RESET}  {WHITE}"
                f"Network & Firewall Audit{RESET}      "
                f"{DIM}Ports · UFW · Connections{RESET}")
            print()
            print(
                f"{pad}  {CYAN}[4]{RESET}  {WHITE}"
                f"SSH Security Hardening{RESET}        "
                f"{DIM}Config · Keys · Risk Audit{RESET}")
            print()
            print(
                f"{pad}  {CYAN}[5]{RESET}  {WHITE}"
                f"Service Optimizer{RESET}             "
                f"{DIM}Manage & Neutralize Services{RESET}")
            print()
            print(f"{pad}  {RED}[6]{RESET}  {WHITE}Exit{RESET}")
            print()
            print(f"{pad}{DIM}{'─' * TERMINAL_WIDTH}{RESET}\n")

            flush_input()
            choice = input(f"{pad}  {CYAN}❯{RESET} ").strip()

            if choice == "1":
                logger.info("User selected: Full System Scan")
                with terminal_manager(echo=False):
                    clear_screen()
                    show_sys_info()
                    show_cpu_status()
                    show_mem_status()
                    show_disk_status()
                    show_active_users()
                    show_battery_status()
                    show_pending_updates()
                    show_snap_status()
                    show_ubuntu_pro_status()
                    print(
                        f"\n{YELLOW}Press [Enter] to return "
                        f"to Main Menu...{RESET}",
                        end="",
                        flush=True)
                    wait_for_enter()
            elif choice == "2":
                logger.info("User selected: Live Process Manager")
                with terminal_manager(echo=True):
                    manage_processes_live()
            elif choice == "3":
                logger.info("User selected: Network Diagnostics")
                with terminal_manager(echo=True):
                    show_network_audit()
            elif choice == "4":
                logger.info("User selected: SSH Security Audit")
                with terminal_manager(echo=True):
                    audit_ssh_security()
            elif choice == "5":
                logger.info("User selected: Service Optimizer")
                with terminal_manager(echo=True):
                    optimize_services()
            elif choice == "6":
                logger.info("=== Diagnostic Tool exited by user ===")
                clear_screen()
                print(f"\n{CYAN}{'VAULTCTL':^{cols}}{RESET}")
                print(
                    f"{DIM}{
                        'Session terminated. Stay secure.':^{cols}}{RESET}\n")
                sys.exit(0)
            else:
                print(f"\n{pad}  {FAIL}  Invalid choice — press [1-6]{RESET}")
                time.sleep(1.5)
    except KeyboardInterrupt:
        set_echo(True)
        logger.info("=== Diagnostic Tool terminated via Ctrl+C ===")
        clear_screen()
        cols = shutil.get_terminal_size().columns
        print(f"\n{CYAN}{'VAULTCTL':^{cols}}{RESET}")
        print(f"{DIM}{'Session terminated. Stay secure.':^{cols}}{RESET}\n")
        sys.exit(0)


if __name__ == "__main__":
    main()
