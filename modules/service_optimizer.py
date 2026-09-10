"""Module [5]: Service Optimizer.

18-service catalog with plain-English descriptions, safety ratings,
and permanent stop + mask ("Deep Neutralization").
"""
import os
import subprocess
import time

from core.logging_setup import logger
from core.sudo import check_sudo
from ui.colors import RESET, CYAN, GREEN, YELLOW, RED, WHITE, DIM, BOLD, TERMINAL_WIDTH
from ui.terminal import (
    terminal_manager, get_confirmation, wait_for_enter, clear_screen,
    flush_input,
)

# SAFETY BLACKLIST — these can NEVER be masked by the optimizer,
# regardless of what the user selects, to prevent bricking the system.
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

# Detailed service catalog with educational descriptions
SERVICE_CATALOG = {
    "bluetooth": {
        "desc": "Manages wireless connections for headsets, mice, and keyboards. "
                "Disable if you only use wired devices to save power and improve "
                "security.",
        "safety": f"{YELLOW}⚠️  CAUTION.{RESET}"
    },
    "cups": {
        "desc": "The Common Unix Printing System. Responsible for all local and "
                "network printing tasks. Disable only if this machine never "
                "needs to print documents.",
        "safety": f"{YELLOW}⚠️  CAUTION.{RESET}"
    },
    "cups-browsed": {
        "desc": "A sub-service of CUPS that automatically 'discovers' and adds "
                "new printers found on your network. Safe to disable if you "
                "manually add printers.",
        "safety": f"{GREEN}✅ SAFE.{RESET}"
    },
    "avahi-daemon": {
        "desc": "Implements Zeroconf networking (mDNS/DNS-SD), allowing your PC "
                "to find local services like Apple AirPlay or Chromecast "
                "without a DNS server. Disable to reduce network noise.",
        "safety": f"{GREEN}✅ SAFE.{RESET}"
    },
    "whoopsie": {
        "desc": "Ubuntu's crash reporting submission daemon. It uploads 'oops' "
                "data to Canonical when a program fails. Safe to disable; "
                "does not affect system stability.",
        "safety": f"{GREEN}✅ VERY SAFE.{RESET}"
    },
    "geoclue": {
        "desc": "Location-aware service that provides your coordinates to apps "
                "like GNOME Maps or Weather. Disable if you prefer privacy "
                "or don't use location-based apps.",
        "safety": f"{GREEN}✅ VERY SAFE.{RESET}"
    },
    "ModemManager": {
        "desc": "Controls 2G/3G/4G/5G mobile broadband modems (USB dongles or "
                "built-in SIM slots). Safe to disable if you only use "
                "Ethernet or Wi-Fi.",
        "safety": f"{GREEN}✅ SAFE.{RESET}"
    },
    "colord": {
        "desc": "Manages color profiles for monitors, printers, and scanners. "
                "Essential for photographers/designers; safe to disable for "
                "general server or coding use.",
        "safety": f"{GREEN}✅ SAFE.{RESET}"
    },
    "chrony": {
        "desc": "An implementation of the Network Time Protocol (NTP). It keeps "
                "your system clock perfectly synchronized. Only disable if "
                "you have another time sync tool.",
        "safety": f"{GREEN}✅ SAFE.{RESET}"
    },
    "snap.canonical-livepatch.canonical-livepatch": {
        "desc": "Enables applying critical Linux kernel security updates without "
                "rebooting. Safe to disable, but you will need to manually "
                "reboot more often for updates.",
        "safety": f"{GREEN}✅ SAFE.{RESET}"
    },
    "apport": {
        "desc": "The system that generates the 'A problem has occurred' pop-up "
                "windows. It collects debug data for developers. Safe to "
                "disable to stop annoying pop-ups.",
        "safety": f"{GREEN}✅ VERY SAFE.{RESET}"
    },
    "kerneloops": {
        "desc": "Specifically tracks and reports Linux kernel 'oopses' (minor "
                "crashes) to a central database. Safe to disable.",
        "safety": f"{GREEN}✅ VERY SAFE.{RESET}"
    },
    "multipathd": {
        "desc": "Used for managing multiple paths to storage devices (typical in "
                "high-end Enterprise SANs). Completely unnecessary for almost "
                "all home or desktop users.",
        "safety": f"{GREEN}✅ SAFE.{RESET}"
    },
    "power-profiles-daemon": {
        "desc": "Allows you to switch between 'Power Saver', 'Balanced', and "
                "'Performance' modes in your desktop settings. Disable with "
                "caution on laptops.",
        "safety": f"{YELLOW}⚠️  CAUTION.{RESET}"
    },
    "switcheroo-control": {
        "desc": "Used on laptops with two graphics cards (e.g., Intel + NVIDIA) "
                "to switch between them for power saving. Disable only if "
                "you have a single GPU.",
        "safety": f"{GREEN}✅ SAFE.{RESET}"
    },
    "apt-news.service": {
        "desc": "A small service that fetches news and announcements about "
                "Ubuntu updates to show in your terminal. Very safe to "
                "disable to keep terminal clean.",
        "safety": f"{GREEN}✅ VERY SAFE.{RESET}"
    },
    "motd-news.service": {
        "desc": "Shows news and promotional messages in the 'Message of the Day' "
                "when you first log in to a terminal. Very safe to disable.",
        "safety": f"{GREEN}✅ VERY SAFE.{RESET}"
    },
    "gnome-remote-desktop": {
        "desc": "Allows you to remotely control your screen using the RDP or VNC "
                "protocols. Disable to prevent anyone from remotely accessing "
                "your desktop.",
        "safety": f"{GREEN}✅ SAFE.{RESET}"
    }
}


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


def optimize_services():
    clear_screen()
    print(f"{CYAN}{BOLD}❯ SYSTEM SERVICE OPTIMIZER{RESET}\n")
    if not check_sudo():
        print(f"\n{RED}[!] Optimization Aborted.{RESET}")
        time.sleep(1.5)
        return

    active = []
    with terminal_manager(echo=False):
        print(f"{CYAN}[*] Scanning for services...{RESET}\n")
        for s in SERVICE_CATALOG.keys():
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
    print(f"{DIM}{'-' * TERMINAL_WIDTH}{RESET}")
    for i, s in enumerate(active, 1):
        print(f"{i:<3} | {s:<30} | {GREEN}RUNNING{RESET}")
    print(f"\n{CYAN}Options: [Number] for details | [Enter] to return{RESET}")
    flush_input()
    choice = input(f"{GREEN}Choice : {RESET}").strip()
    if choice.isdigit() and 1 <= int(choice) <= len(active):
        t = active[int(choice) - 1]
        info = SERVICE_CATALOG[t]
        clear_screen()
        print(
            f"{YELLOW}--- {t.upper()} ---{RESET}\n\n"
            f"Desc: {info['desc']}\nSafety: {info['safety']}\n")
        print(f"{DIM}{'-' * TERMINAL_WIDTH}{RESET}")
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
        print(f"\n{DIM}{'-' * TERMINAL_WIDTH}{RESET}")
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
