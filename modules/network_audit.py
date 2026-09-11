"""Module [3]: Network & Firewall Audit.

UFW status + rule preview, listening ports, active outgoing
connections, ARP table, and DNS hijack detection.
"""
import re
import socket
import subprocess
import time
import urllib.request

import psutil

from core.logging_setup import logger
from core.sudo import check_sudo
from ui.colors import (
    RESET, CYAN, GREEN, YELLOW, RED, WHITE, DIM,
    OK, WARN, FAIL, TERMINAL_WIDTH,
)
from ui.terminal import (
    terminal_manager, clear_screen, section_header, footer_prompt,
)

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


def parse_ss_line(line):
    """Extract process name / local / peer addresses from an `ss` line."""
    process = "Unknown"
    proc_match = re.search(r'users:\(\("([^"]+)"', line)
    if proc_match:
        process = proc_match.group(1)

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
            print(f"Status: {RED}[INACTIVE] System Unprotected{RESET}")
        elif "active" in output:
            print(f"Status: {GREEN}[ACTIVE] Secured{RESET}")
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
                print(f"    {OK} No listening ports found.")
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
                print(f"    {OK} No active user connections found.")
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
    section_header("ARP TABLE — LOCAL NETWORK DEVICES")
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
    section_header("DNS SERVER AUDIT")
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


def show_network_status():
    section_header("NETWORK & CONNECTIVITY")

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


def show_network_audit():
    clear_screen()
    section_header("NETWORK DIAGNOSTICS & SECURITY AUDIT")
    print()
    if not check_sudo():
        print(f"\n{RED}[!] Audit Aborted.{RESET}")
        time.sleep(1.5)
        return
    with terminal_manager(echo=False):
        audit_ufw_firewall()
        print(f"{DIM}{'-' * TERMINAL_WIDTH}{RESET}")
        show_network_status()
        print(f"{DIM}{'-' * TERMINAL_WIDTH}{RESET}")
        audit_open_ports()
        print(f"{DIM}{'-' * TERMINAL_WIDTH}{RESET}")
        audit_arp_table()
        audit_dns_servers()
    footer_prompt("return to menu")
