# VAULTCTL — Linux System Diagnostic & Security Hardening

> **Know Your System. Own Your Security.**

A single-file Python CLI tool that scans, monitors, and hardens your Ubuntu/Linux system — no installation required beyond `psutil`.

---

## Features

| # | Module | Description |
|---|--------|-------------|
| `[1]` | **Full System Scan** | CPU · RAM · Disk · Battery · Network · Logged-in Users · Snap packages · APT updates · Ubuntu Pro / ESM status |
| `[2]` | **Live Process Manager** | Real-time top-8 view sortable by RAM or CPU · Inspect full process details · Kill by table index or direct PID (SIGTERM & SIGKILL) |
| `[3]` | **Network & Firewall Audit** | UFW status + rule preview · Listening ports · Active outgoing connections · ARP table · DNS hijack detection |
| `[4]` | **SSH Security Hardening** | 11-point `sshd_config` audit · Fail2Ban / CrowdSec detection · Google Authenticator 2FA check · Actionable fix recommendations |
| `[5]` | **Service Optimizer** | 18-service catalog with plain-English descriptions · Safety ratings · Permanent stop + mask (Deep Neutralization) |

---

## Requirements

- **Python 3.12+** — uses PEP 701 f-string syntax
- **psutil ≥ 6.0.0** — cross-platform process and system metrics

---

## Quick Start

```bash
# Install dependency
pip install psutil

# Run (standard user — some features restricted)
python3 main.py

# Run with full access (SSH audit, firewall, service control)
sudo python3 main.py
```

> **Tip:** The tool will ask you to authenticate sudo at startup so it never interrupts you mid-workflow.

---

## Install from source

```bash
git clone https://github.com/NasserS12/Vaultctl.git
cd Vaultctl
pip install -r requirements.txt
python3 main.py
```

---

## Feature Details

### Full System Scan `[1]`
One-shot snapshot of the entire machine: CPU usage and temperature per core, RAM + swap consumption, disk partitions with color-coded fill levels, active user sessions, battery state, pending APT and Snap updates, and Ubuntu Pro / ESM subscription status.

### Live Process Manager `[2]`
Auto-refreshing table of the 8 highest-resource processes. Press `m`/`c` to toggle sort mode. Select a row number to open a detailed inspection report (exe path, threads, open files, network connections). Use `kill <#>` for graceful SIGTERM or `fkill <#>` for immediate SIGKILL — with confirmation prompt before every action.

### Network & Firewall Audit `[3]`
Checks UFW firewall rules, maps all listening sockets to their owning process, lists established outgoing connections, reads the ARP table to reveal unknown devices on your LAN, and audits your active DNS servers against a curated whitelist of trusted resolvers.

### SSH Security Hardening `[4]`
Reads `/etc/ssh/sshd_config.d/*.conf` and `/etc/ssh/sshd_config` in correct precedence order and grades 11 directives as `[ SECURE ]`, `[ WARNING ]`, or `[ RISK ]`. For every finding that isn't secure, a one-line remediation command is printed inline. Also checks whether Fail2Ban/CrowdSec is running and whether Google Authenticator 2FA is configured.

### Service Optimizer `[5]`
Scans for 18 common non-essential services and lists only the ones currently running. Select one to read a plain-English explanation of what it does and a safety rating. Choosing to neutralize a service runs `systemctl stop` + `systemctl mask --now` — permanently blocking it from ever auto-starting again.

To reverse neutralization:
```bash
sudo systemctl unmask <service> && sudo systemctl enable <service>
```

---

## Safety Guarantees

- **Critical blacklist** — `poweroff`, `reboot`, `dbus`, `systemd-*`, and display managers can never be masked by the optimizer.
- **Kernel PID protection** — processes with PID ≤ 100 are refused as kill targets.
- **Confirmation prompts** — every destructive action (kill, neutralize) requires explicit `y` confirmation.
- **Echo restoration** — terminal echo is always restored on exit, even after a crash or Ctrl+C.

---

## Logging

All significant events are written to `diagnostic_tool.log` in the same directory:

```
2025-01-15 14:32:01 [INFO] Session started: authenticated with sudo.
2025-01-15 14:33:47 [INFO] User selected: SSH Security Audit
2025-01-15 14:35:12 [INFO] Service neutralized: whoopsie
```

---

## Project Structure

```
vaultctl/
├── main.py          # Single-file application (all modules)
├── requirements.txt # Python dependencies
└── README.md        # This file
```

---

## Author

Developed by **Nasser**

---

## License

MIT License — free to use, modify, and distribute.
