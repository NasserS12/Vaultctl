"""Module [2]: Live Process Manager.

Real-time top-8 view sortable by RAM or CPU, process inspection,
and kill by table index or direct PID (SIGTERM & SIGKILL).
"""
import os
import time
import psutil
from datetime import datetime

from core.logging_setup import logger
from ui.colors import RESET, CYAN, GREEN, YELLOW, RED, WHITE, DIM
from ui.terminal import (
    clear_screen, flush_input, get_confirmation,
    section_header, footer_prompt,
)

KERNEL_PID_THRESHOLD = 100


def manage_processes_live():
    sort_by = 'memory_percent'

    def row_color(mem_pct, cpu_pct):
        """Return color based on highest resource pressure."""
        if mem_pct > 80 or cpu_pct > 80:
            return RED
        if mem_pct > 50 or cpu_pct > 50:
            return YELLOW
        return WHITE

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
                f"\n{GREEN}[ OK ] {sig_sent} sent to "
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
        section_header(f"PROCESS MANAGER — SORT: {mode_text}")
        print()

        # --- Summary bar ---
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
            c = row_color(mem_val, cpu_val)   # color per row
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
            continue

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
                footer_prompt("resume live monitoring")

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
