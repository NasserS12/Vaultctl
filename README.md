# VAULTCTL — Linux System Diagnostic & Security Hardening

A single-file Python CLI tool that scans, monitors, and hardens your Linux system.

## Features

| Menu | Tool |
|---|---|
| `[1]` Full System Scan | CPU, RAM, Disk, Battery, Network, Users, Snap packages, APT updates, Ubuntu Pro |
| `[2]` Live Process Manager | Top-8 view, sort by RAM/CPU, inspect details, kill by table index or PID |
| `[3]` Network & Firewall Audit | UFW status, listening ports, active connections, ARP table, DNS audit |
| `[4]` SSH Security Hardening | 11-point config audit, fail2ban/crowdsec detection, 2FA check, recommendations |
| `[5]` Service Optimizer | 17 services catalog with descriptions, safe stop + mask |

## Requirements

- **Python 3.12+** (uses PEP 701 f-strings)
- `psutil` (installed automatically)

## Quick Start

```bash
pip install psutil
python3 test.py
```

Some features (SSH audit, firewall, service control) require sudo — the tool prompts for it at startup.

## Install Dependencies

```bash
pip install -r requirements.txt
```
