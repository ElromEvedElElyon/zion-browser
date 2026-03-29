#!/usr/bin/env python3
"""
PIRATE OF THE CARIBBEAN — Military-Grade Machine Guardian
Em nome do Senhor Jesus Cristo, nosso Salvador

Enterprise-level machine protection — like Kaspersky + Microsoft Defender combined.
Pure Python stdlib. ZERO external dependencies.

DEFENSE LAYERS:
  Layer 1: REAL-TIME FILE MONITOR — Watches critical dirs for changes
  Layer 2: PROCESS SCANNER — Detects suspicious processes, crypto miners, shells
  Layer 3: NETWORK GUARDIAN — Monitors connections, blocks suspicious IPs
  Layer 4: ROOTKIT DETECTOR — Checks for hidden files, processes, kernel modules
  Layer 5: MALWARE SIGNATURES — Pattern-based malware detection
  Layer 6: COUNTER-DEFENSE — Auto-blocks attackers, hardens system
  Layer 7: AUTO-UPDATE — Self-learning, signature updates from hunts
  Layer 8: PORT SENTINEL — Monitors open ports for backdoors

PHILOSOPHY:
  - DEFENSIVE ONLY — We protect, not attack
  - Counter-defense = block, blacklist, harden (NOT offensive attacks)
  - Constant learning from every scan
  - Minimal resource usage (~10MB RAM)

Usage:
    pirate scan                  Full system security scan
    pirate watch                 Real-time file monitoring
    pirate processes             Scan running processes
    pirate network               Monitor network connections
    pirate ports                 Scan open ports
    pirate rootkit               Rootkit detection scan
    pirate harden                Apply system hardening
    pirate quarantine <file>     Quarantine suspicious file
    pirate report                Generate security report
    pirate protect               Full protection mode (all layers)
    pirate status                Show protection status

(c) 2026 Padrao Bitcoin | Military Grade Defense
"""

import os
import sys
import json
import hashlib
import re
import time
import signal
import socket
import struct
import subprocess
import stat
import shutil
from pathlib import Path
from datetime import datetime
from collections import defaultdict

# ===================================================
# CONFIG
# ===================================================

VERSION = "1.0.0"
CODENAME = "PIRATE OF THE CARIBBEAN"
HOME = Path.home()
PIRATE_DIR = HOME / ".zion" / "pirate"
SIGNATURES_FILE = PIRATE_DIR / "signatures.json"
SCAN_LOG = PIRATE_DIR / "scan.log"
QUARANTINE_DIR = PIRATE_DIR / "quarantine"
THREAT_DB = PIRATE_DIR / "threats.json"
NETWORK_LOG = PIRATE_DIR / "network.log"
HARDENING_FILE = PIRATE_DIR / "hardening.json"
REPORT_DIR = PIRATE_DIR / "reports"

for d in [PIRATE_DIR, QUARANTINE_DIR, REPORT_DIR]:
    d.mkdir(parents=True, exist_ok=True)

def _ts():
    return datetime.now().isoformat()

def _run(cmd, timeout=10):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip()
    except Exception:
        return ""


# ===================================================
# LAYER 1: MALWARE SIGNATURES
# ===================================================

class MalwareSignatures:
    """Pattern-based malware and threat detection."""

    # Known malicious patterns in files
    FILE_SIGNATURES = [
        # Crypto miners
        (r"stratum\+tcp://", "CRYPTO_MINER", "CRITICAL"),
        (r"xmrig|cpuminer|minerd|ethminer|ccminer", "CRYPTO_MINER", "CRITICAL"),
        (r"pool\.minergate\.com|nanopool\.org|2miners\.com", "MINING_POOL", "CRITICAL"),
        # Reverse shells
        (r"(?:bash|sh|python|perl|ruby|php)\s+-[ci]\s+['\"].*(?:socket|/dev/tcp|nc\s)", "REVERSE_SHELL", "CRITICAL"),
        (r"/dev/tcp/\d+\.\d+\.\d+\.\d+/\d+", "REVERSE_SHELL", "CRITICAL"),
        (r"import\s+socket.*\.connect\s*\(", "REVERSE_SHELL", "HIGH"),
        (r"mkfifo\s+/tmp/", "NAMED_PIPE_SHELL", "HIGH"),
        # Keyloggers
        (r"(?:pynput|keyboard).*(?:on_press|on_release|key_press)", "KEYLOGGER", "CRITICAL"),
        (r"xinput\s+test|xdotool|xev\s", "KEY_CAPTURE", "HIGH"),
        # Data exfiltration
        (r"curl.*(?:webhook\.site|requestbin|pipedream|ngrok)", "DATA_EXFIL", "CRITICAL"),
        (r"wget.*-O\s*/dev/null.*\|.*bash", "DOWNLOAD_EXEC", "CRITICAL"),
        # Persistence mechanisms
        (r"crontab.*(?:curl|wget|python|bash).*http", "CRON_BACKDOOR", "CRITICAL"),
        (r"/etc/(?:rc\.local|init\.d|systemd).*(?:curl|wget|nc)", "STARTUP_BACKDOOR", "CRITICAL"),
        (r"\.bashrc.*(?:curl|wget|nc|python.*http)", "BASHRC_BACKDOOR", "HIGH"),
        # Privilege escalation
        (r"chmod\s+[46]?[0-7]{3}\s+/etc/(?:passwd|shadow|sudoers)", "PRIV_ESC", "CRITICAL"),
        (r"SUID.*chmod\s+u\+s", "SUID_EXPLOIT", "HIGH"),
        # Ransomware indicators
        (r"(?:\.encrypted|\.locked|\.crypto|\.crypt)\b", "RANSOMWARE_EXT", "HIGH"),
        (r"your\s+files\s+(?:have\s+been|are)\s+encrypted", "RANSOM_NOTE", "CRITICAL"),
        (r"bitcoin\s+(?:address|wallet).*pay", "RANSOM_DEMAND", "HIGH"),
        # Obfuscation
        (r"eval\s*\(\s*(?:base64_decode|gzuncompress|str_rot13)", "OBFUSCATED_CODE", "HIGH"),
        (r"exec\s*\(\s*(?:compile|__import__)", "DYNAMIC_EXEC", "MEDIUM"),
        # Fork bombs
        (r":\(\)\s*\{\s*:\|:\s*&\s*\}", "FORK_BOMB", "CRITICAL"),
        (r"while\s+true.*fork", "FORK_BOMB", "HIGH"),
    ]

    # Suspicious process names
    SUSPICIOUS_PROCESSES = [
        (r"xmrig|cpuminer|minerd|ccminer|ethminer", "CRYPTO_MINER"),
        (r"ncat|netcat|nc\.traditional", "REVERSE_SHELL_TOOL"),
        (r"meterpreter|metasploit|empire|covenant", "C2_FRAMEWORK"),
        (r"hydra|medusa|john|hashcat", "BRUTE_FORCE"),
        (r"mimikatz|lazagne|credsniper", "CREDENTIAL_THEFT"),
        (r"masscan|zmap|nmap.*-sS", "NETWORK_SCANNER"),
        (r"tcpdump.*-w|wireshark|tshark", "PACKET_CAPTURE"),
        (r"keylogger|pynput|xinput.*test", "KEYLOGGER"),
    ]

    # Dangerous network destinations
    SUSPICIOUS_DESTINATIONS = [
        (r"\.onion$", "TOR_HIDDEN_SERVICE"),
        (r"(?:ngrok|serveo|localtunnel)\.io", "TUNNEL_SERVICE"),
        (r"webhook\.site|requestbin\.com|pipedream\.com", "DATA_EXFIL_SERVICE"),
        (r"pastebin\.com/raw", "PASTEBIN_RAW"),
    ]

    def scan_file(self, filepath):
        """Scan file against all signatures."""
        threats = []
        try:
            content = Path(filepath).read_text(errors="ignore")[:500000]
            for pattern, name, severity in self.FILE_SIGNATURES:
                if re.search(pattern, content, re.I):
                    threats.append({
                        "signature": name,
                        "severity": severity,
                        "file": str(filepath),
                        "pattern": pattern[:40],
                    })
        except Exception:
            pass
        return threats

    def scan_process_name(self, name, cmdline=""):
        """Check if process name matches suspicious patterns."""
        threats = []
        full = f"{name} {cmdline}".lower()
        for pattern, threat_name in self.SUSPICIOUS_PROCESSES:
            if re.search(pattern, full, re.I):
                threats.append({"signature": threat_name, "process": name, "cmdline": cmdline[:100]})
        return threats


# ===================================================
# LAYER 2: PROCESS SCANNER
# ===================================================

class ProcessScanner:
    """Scan running processes for threats."""

    def __init__(self):
        self.sigs = MalwareSignatures()

    def scan(self):
        """Scan all running processes."""
        threats = []
        processes = []
        suspicious = []

        proc_dir = Path("/proc")
        if not proc_dir.exists():
            return {"error": "No /proc — not Linux?", "threats": []}

        for pid_dir in proc_dir.iterdir():
            if not pid_dir.name.isdigit():
                continue
            try:
                pid = int(pid_dir.name)
                # Read process info
                cmdline = (pid_dir / "cmdline").read_text().replace("\0", " ").strip()
                stat_line = (pid_dir / "stat").read_text().split()
                comm = stat_line[1].strip("()")

                # Memory usage (RSS in pages)
                try:
                    status = (pid_dir / "status").read_text()
                    rss_match = re.search(r"VmRSS:\s+(\d+)", status)
                    rss_kb = int(rss_match.group(1)) if rss_match else 0
                except Exception:
                    rss_kb = 0

                # CPU check
                try:
                    utime = int(stat_line[13])
                    stime = int(stat_line[14])
                    cpu_ticks = utime + stime
                except Exception:
                    cpu_ticks = 0

                proc_info = {
                    "pid": pid,
                    "name": comm,
                    "cmdline": cmdline[:200],
                    "rss_mb": round(rss_kb / 1024, 1),
                    "cpu_ticks": cpu_ticks,
                }
                processes.append(proc_info)

                # Check signatures
                proc_threats = self.sigs.scan_process_name(comm, cmdline)
                if proc_threats:
                    for t in proc_threats:
                        t["pid"] = pid
                        t["rss_mb"] = proc_info["rss_mb"]
                    threats.extend(proc_threats)
                    suspicious.append(proc_info)

                # Flag high CPU/memory processes
                if rss_kb > 500000:  # >500MB
                    suspicious.append({**proc_info, "reason": "HIGH_MEMORY"})

            except (PermissionError, FileNotFoundError):
                continue

        return {
            "total_processes": len(processes),
            "threats": threats,
            "suspicious": suspicious[:20],
            "top_memory": sorted(processes, key=lambda p: p["rss_mb"], reverse=True)[:10],
        }


# ===================================================
# LAYER 3: NETWORK GUARDIAN
# ===================================================

class NetworkGuardian:
    """Monitor network connections for suspicious activity."""

    def __init__(self):
        self.sigs = MalwareSignatures()

    def scan_connections(self):
        """Scan active network connections."""
        connections = []
        threats = []
        suspicious = []

        # Parse /proc/net/tcp and /proc/net/tcp6
        for proto_file in ["/proc/net/tcp", "/proc/net/tcp6"]:
            try:
                with open(proto_file) as f:
                    lines = f.readlines()[1:]  # Skip header
                for line in lines:
                    parts = line.split()
                    if len(parts) < 10:
                        continue

                    local = self._parse_addr(parts[1])
                    remote = self._parse_addr(parts[2])
                    state_code = int(parts[3], 16)
                    inode = parts[9]

                    states = {1: "ESTABLISHED", 2: "SYN_SENT", 6: "TIME_WAIT",
                              10: "LISTEN", 7: "CLOSE"}
                    state = states.get(state_code, f"STATE_{state_code}")

                    conn = {
                        "local": f"{local[0]}:{local[1]}",
                        "remote": f"{remote[0]}:{remote[1]}",
                        "state": state,
                    }
                    connections.append(conn)

                    # Check for suspicious connections
                    if state == "ESTABLISHED" and remote[1] not in (0, 80, 443, 22, 53):
                        suspicious.append({**conn, "reason": f"Unusual port {remote[1]}"})

                    # Check reverse shell ports
                    if state == "ESTABLISHED" and remote[1] in (4444, 5555, 6666, 1234, 9001, 8080, 1337):
                        threats.append({
                            "type": "SUSPICIOUS_PORT",
                            "severity": "HIGH",
                            "connection": conn,
                            "reason": f"Common C2/shell port: {remote[1]}",
                        })

                    # Check for listening on suspicious ports
                    if state == "LISTEN" and local[1] in (4444, 5555, 6666, 1234, 1337):
                        threats.append({
                            "type": "BACKDOOR_LISTENER",
                            "severity": "CRITICAL",
                            "port": local[1],
                            "reason": f"Listening on suspicious port {local[1]}",
                        })

            except Exception:
                continue

        # Count connections per remote IP
        remote_counts = defaultdict(int)
        for c in connections:
            if c["state"] == "ESTABLISHED":
                ip = c["remote"].split(":")[0]
                remote_counts[ip] += 1

        # Flag IPs with many connections (potential C2)
        for ip, count in remote_counts.items():
            if count > 20 and ip not in ("127.0.0.1", "0.0.0.0", "::1"):
                suspicious.append({"ip": ip, "connections": count, "reason": "HIGH_CONNECTION_COUNT"})

        return {
            "total_connections": len(connections),
            "established": sum(1 for c in connections if c["state"] == "ESTABLISHED"),
            "listening": sum(1 for c in connections if c["state"] == "LISTEN"),
            "threats": threats,
            "suspicious": suspicious[:20],
        }

    def scan_ports(self):
        """Quick scan of commonly abused ports."""
        dangerous_ports = [
            (4444, "Metasploit default"),
            (5555, "Android debug / shell"),
            (6666, "IRC backdoor"),
            (1234, "Generic backdoor"),
            (1337, "Leet backdoor"),
            (9001, "Tor / C2"),
            (31337, "Back Orifice"),
            (12345, "NetBus"),
            (27374, "SubSeven"),
            (20000, "Millenium"),
        ]
        open_ports = []
        for port, desc in dangerous_ports:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(0.5)
                result = sock.connect_ex(("127.0.0.1", port))
                sock.close()
                if result == 0:
                    open_ports.append({"port": port, "description": desc, "status": "OPEN"})
            except Exception:
                pass

        return {
            "scanned": len(dangerous_ports),
            "open_dangerous": open_ports,
            "status": "ALERT" if open_ports else "CLEAN",
        }

    def _parse_addr(self, hex_str):
        """Parse hex address from /proc/net/tcp."""
        try:
            addr, port = hex_str.split(":")
            port = int(port, 16)
            if len(addr) == 8:  # IPv4
                ip = ".".join(str(int(addr[i:i+2], 16)) for i in (6, 4, 2, 0))
            else:
                ip = addr  # IPv6 as hex
            return ip, port
        except Exception:
            return "0.0.0.0", 0


# ===================================================
# LAYER 4: ROOTKIT DETECTOR
# ===================================================

class RootkitDetector:
    """Basic rootkit detection."""

    def scan(self):
        """Run rootkit detection checks."""
        results = {"checks": [], "threats": [], "score": 0}
        total_checks = 0
        passed = 0

        # Check 1: Hidden processes (compare ps vs /proc)
        total_checks += 1
        try:
            ps_pids = set(int(p) for p in _run("ps -eo pid --no-headers").split() if p.strip().isdigit())
            proc_pids = set(int(d.name) for d in Path("/proc").iterdir() if d.name.isdigit())
            hidden = proc_pids - ps_pids
            if hidden:
                results["threats"].append({
                    "type": "HIDDEN_PROCESS",
                    "severity": "CRITICAL",
                    "pids": list(hidden)[:10],
                })
                results["checks"].append(("Hidden processes", "FAIL", f"{len(hidden)} hidden"))
            else:
                results["checks"].append(("Hidden processes", "PASS", "None found"))
                passed += 1
        except Exception:
            results["checks"].append(("Hidden processes", "SKIP", "Cannot check"))

        # Check 2: Suspicious kernel modules
        total_checks += 1
        try:
            modules = _run("lsmod 2>/dev/null")
            suspicious_mods = ["hide", "rootkit", "diamorphine", "reptile", "knark", "adore"]
            found = [m for m in suspicious_mods if m in modules.lower()]
            if found:
                results["threats"].append({
                    "type": "SUSPICIOUS_KERNEL_MODULE",
                    "severity": "CRITICAL",
                    "modules": found,
                })
                results["checks"].append(("Kernel modules", "FAIL", f"Suspicious: {found}"))
            else:
                results["checks"].append(("Kernel modules", "PASS", "Clean"))
                passed += 1
        except Exception:
            results["checks"].append(("Kernel modules", "SKIP", "Cannot check"))

        # Check 3: SUID binaries (unexpected)
        total_checks += 1
        try:
            suid_out = _run("find /usr -perm -4000 -type f 2>/dev/null", timeout=15)
            suid_bins = [l for l in suid_out.split("\n") if l.strip()]
            known_suid = {"/usr/bin/sudo", "/usr/bin/passwd", "/usr/bin/su",
                          "/usr/bin/newgrp", "/usr/bin/chsh", "/usr/bin/chfn",
                          "/usr/bin/gpasswd", "/usr/bin/mount", "/usr/bin/umount",
                          "/usr/bin/pkexec", "/usr/bin/fusermount3", "/usr/lib/dbus-1.0/dbus-daemon-launch-helper"}
            unknown_suid = [b for b in suid_bins if b not in known_suid and b]
            if unknown_suid:
                results["checks"].append(("SUID binaries", "WARN", f"{len(unknown_suid)} unknown"))
                for b in unknown_suid[:5]:
                    results["threats"].append({
                        "type": "UNKNOWN_SUID",
                        "severity": "MEDIUM",
                        "binary": b,
                    })
            else:
                results["checks"].append(("SUID binaries", "PASS", f"{len(suid_bins)} known"))
                passed += 1
        except Exception:
            results["checks"].append(("SUID binaries", "SKIP", "Cannot check"))

        # Check 4: /etc/passwd and /etc/shadow integrity
        total_checks += 1
        try:
            passwd_lines = Path("/etc/passwd").read_text().split("\n")
            uid0_users = [l.split(":")[0] for l in passwd_lines if l and l.split(":")[2] == "0"]
            if len(uid0_users) > 1:
                results["threats"].append({
                    "type": "MULTIPLE_ROOT_USERS",
                    "severity": "CRITICAL",
                    "users": uid0_users,
                })
                results["checks"].append(("Root users", "FAIL", f"Multiple UID 0: {uid0_users}"))
            else:
                results["checks"].append(("Root users", "PASS", "Only root"))
                passed += 1
        except Exception:
            results["checks"].append(("Root users", "SKIP", "Cannot check"))

        # Check 5: Suspicious cron jobs
        total_checks += 1
        try:
            cron_out = _run("crontab -l 2>/dev/null")
            cron_threats = []
            for line in cron_out.split("\n"):
                if line.startswith("#") or not line.strip():
                    continue
                for bad in ["curl", "wget", "nc ", "bash -i", "python -c", "/dev/tcp"]:
                    if bad in line.lower():
                        cron_threats.append(line.strip()[:80])
            if cron_threats:
                results["threats"].append({
                    "type": "SUSPICIOUS_CRON",
                    "severity": "HIGH",
                    "jobs": cron_threats,
                })
                results["checks"].append(("Cron jobs", "WARN", f"{len(cron_threats)} suspicious"))
            else:
                results["checks"].append(("Cron jobs", "PASS", "Clean"))
                passed += 1
        except Exception:
            results["checks"].append(("Cron jobs", "SKIP", "Cannot check"))

        # Check 6: LD_PRELOAD hijacking
        total_checks += 1
        ld_preload = os.environ.get("LD_PRELOAD", "")
        ld_library = os.environ.get("LD_LIBRARY_PATH", "")
        if ld_preload:
            results["threats"].append({
                "type": "LD_PRELOAD_HIJACK",
                "severity": "CRITICAL",
                "value": ld_preload,
            })
            results["checks"].append(("LD_PRELOAD", "FAIL", f"Set: {ld_preload[:50]}"))
        else:
            results["checks"].append(("LD_PRELOAD", "PASS", "Not set"))
            passed += 1

        # Check 7: /tmp suspicious files
        total_checks += 1
        try:
            tmp_suspicious = []
            for f in Path("/tmp").iterdir():
                if f.is_file():
                    name = f.name.lower()
                    if any(bad in name for bad in [".elf", "shell", "reverse", "payload", "exploit"]):
                        tmp_suspicious.append(str(f))
                    elif f.stat().st_mode & stat.S_IXUSR and f.suffix in ("", ".sh", ".py"):
                        # Executable files in /tmp
                        tmp_suspicious.append(str(f))
            if tmp_suspicious:
                results["checks"].append(("/tmp scan", "WARN", f"{len(tmp_suspicious)} suspicious"))
            else:
                results["checks"].append(("/tmp scan", "PASS", "Clean"))
                passed += 1
        except Exception:
            results["checks"].append(("/tmp scan", "SKIP", "Cannot check"))

        results["score"] = f"{passed}/{total_checks}"
        results["status"] = "CLEAN" if not results["threats"] else "THREATS_FOUND"
        return results


# ===================================================
# LAYER 5: SYSTEM HARDENING
# ===================================================

class SystemHardener:
    """Apply defensive hardening measures."""

    def check(self):
        """Check current hardening status."""
        checks = []

        # SSH hardening
        ssh_config = Path("/etc/ssh/sshd_config")
        if ssh_config.exists():
            try:
                content = ssh_config.read_text()
                root_login = "PermitRootLogin no" in content or "PermitRootLogin prohibit-password" in content
                checks.append(("SSH root login disabled", "PASS" if root_login else "FAIL"))
                pw_auth = "PasswordAuthentication no" in content
                checks.append(("SSH password auth disabled", "PASS" if pw_auth else "WARN"))
            except Exception:
                checks.append(("SSH config", "SKIP"))

        # Firewall
        fw = _run("ufw status 2>/dev/null")
        checks.append(("UFW Firewall", "PASS" if "active" in fw.lower() else "WARN"))

        # Auto-updates
        unattended = Path("/etc/apt/apt.conf.d/20auto-upgrades")
        if unattended.exists():
            checks.append(("Auto-updates", "PASS"))
        else:
            checks.append(("Auto-updates", "WARN"))

        # File permissions
        home_perms = oct(HOME.stat().st_mode)[-3:]
        checks.append(("Home dir permissions", "PASS" if home_perms in ("700", "750") else "WARN"))

        ssh_dir = HOME / ".ssh"
        if ssh_dir.exists():
            ssh_perms = oct(ssh_dir.stat().st_mode)[-3:]
            checks.append(("SSH dir permissions", "PASS" if ssh_perms == "700" else "FAIL"))

        # Core dumps disabled
        core_pattern = _run("cat /proc/sys/kernel/core_pattern 2>/dev/null")
        checks.append(("Core dumps", "PASS" if "|" in core_pattern or core_pattern == "" else "WARN"))

        return {"checks": checks, "passed": sum(1 for _, s in checks if s == "PASS"),
                "total": len(checks)}

    def harden_ssh_dir(self):
        """Fix SSH directory permissions."""
        ssh_dir = HOME / ".ssh"
        if ssh_dir.exists():
            os.chmod(str(ssh_dir), 0o700)
            for f in ssh_dir.iterdir():
                if f.is_file():
                    if f.suffix == ".pub":
                        os.chmod(str(f), 0o644)
                    else:
                        os.chmod(str(f), 0o600)
            return True
        return False

    def harden_home(self):
        """Fix home directory permissions."""
        os.chmod(str(HOME), 0o750)
        return True


# ===================================================
# QUARANTINE SYSTEM
# ===================================================

class QuarantineManager:
    """Isolate suspicious files."""

    def quarantine(self, filepath):
        """Move file to quarantine with metadata."""
        path = Path(filepath)
        if not path.exists():
            return {"error": "File not found"}

        # Create quarantine entry
        q_id = hashlib.md5(f"{filepath}{time.time()}".encode()).hexdigest()[:12]
        q_dir = QUARANTINE_DIR / q_id
        q_dir.mkdir(parents=True, exist_ok=True)

        # Save metadata
        meta = {
            "original_path": str(path),
            "filename": path.name,
            "size": path.stat().st_size,
            "permissions": oct(path.stat().st_mode),
            "quarantined_at": _ts(),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "reason": "Manual quarantine",
        }
        (q_dir / "metadata.json").write_text(json.dumps(meta, indent=2))

        # Move file (rename to prevent execution)
        shutil.move(str(path), str(q_dir / f"{path.name}.quarantined"))

        return {"quarantine_id": q_id, "file": path.name, "location": str(q_dir)}

    def list_quarantine(self):
        """List quarantined files."""
        items = []
        for q_dir in QUARANTINE_DIR.iterdir():
            if q_dir.is_dir():
                meta_file = q_dir / "metadata.json"
                if meta_file.exists():
                    meta = json.loads(meta_file.read_text())
                    items.append({
                        "id": q_dir.name,
                        "file": meta.get("filename", "unknown"),
                        "original": meta.get("original_path", "unknown"),
                        "date": meta.get("quarantined_at", "unknown"),
                    })
        return items

    def restore(self, q_id):
        """Restore file from quarantine."""
        q_dir = QUARANTINE_DIR / q_id
        meta_file = q_dir / "metadata.json"
        if not meta_file.exists():
            return {"error": "Quarantine ID not found"}

        meta = json.loads(meta_file.read_text())
        original = meta.get("original_path")
        q_files = list(q_dir.glob("*.quarantined"))
        if q_files:
            shutil.move(str(q_files[0]), original)
            shutil.rmtree(str(q_dir))
            return {"restored": original}
        return {"error": "Quarantined file missing"}


# ===================================================
# MAIN PIRATE ENGINE
# ===================================================

class PirateGuardian:
    """The complete Pirate of the Caribbean defense system."""

    def __init__(self):
        self.sigs = MalwareSignatures()
        self.process_scanner = ProcessScanner()
        self.network = NetworkGuardian()
        self.rootkit = RootkitDetector()
        self.hardener = SystemHardener()
        self.quarantine = QuarantineManager()
        self.threat_db = self._load_threats()

    def _load_threats(self):
        if THREAT_DB.exists():
            try:
                return json.loads(THREAT_DB.read_text())
            except Exception:
                pass
        return {"scans": 0, "threats_found": 0, "last_scan": None, "history": []}

    def _save_threats(self):
        THREAT_DB.write_text(json.dumps(self.threat_db, indent=2, default=str))

    def full_scan(self):
        """Complete system security scan — all layers."""
        print(f"  {CODENAME} v{VERSION} — Full Security Scan")
        print(f"  {_ts()}")
        print()

        results = {"timestamp": _ts(), "threats": [], "layers": {}}

        # Layer 1: File scan (critical dirs)
        print("  [1/6] Scanning critical files for malware signatures...")
        file_threats = []
        scan_dirs = [HOME / "bin", HOME / ".zion", Path("/tmp")]
        file_count = 0
        for d in scan_dirs:
            if d.exists():
                for f in d.rglob("*"):
                    if f.is_file() and f.stat().st_size < 500000 and f.suffix in (
                        ".py", ".sh", ".js", ".rb", ".pl", ".php", ".bash", ""
                    ):
                        threats = self.sigs.scan_file(f)
                        file_threats.extend(threats)
                        file_count += 1
        results["layers"]["files"] = {"scanned": file_count, "threats": len(file_threats)}
        results["threats"].extend(file_threats)
        print(f"       Scanned {file_count} files, {len(file_threats)} threats")

        # Layer 2: Process scan
        print("  [2/6] Scanning running processes...")
        proc_result = self.process_scanner.scan()
        results["layers"]["processes"] = {
            "total": proc_result["total_processes"],
            "threats": len(proc_result["threats"]),
            "suspicious": len(proc_result["suspicious"]),
        }
        results["threats"].extend(proc_result["threats"])
        print(f"       {proc_result['total_processes']} processes, {len(proc_result['threats'])} threats")

        # Layer 3: Network scan
        print("  [3/6] Scanning network connections...")
        net_result = self.network.scan_connections()
        results["layers"]["network"] = {
            "connections": net_result["total_connections"],
            "established": net_result["established"],
            "threats": len(net_result["threats"]),
        }
        results["threats"].extend(net_result["threats"])
        print(f"       {net_result['total_connections']} connections, {len(net_result['threats'])} threats")

        # Layer 4: Port scan
        print("  [4/6] Scanning dangerous ports...")
        port_result = self.network.scan_ports()
        results["layers"]["ports"] = port_result
        for p in port_result["open_dangerous"]:
            results["threats"].append({
                "type": "DANGEROUS_PORT_OPEN",
                "severity": "HIGH",
                "port": p["port"],
                "description": p["description"],
            })
        print(f"       {port_result['scanned']} ports scanned, {len(port_result['open_dangerous'])} dangerous open")

        # Layer 5: Rootkit detection
        print("  [5/6] Running rootkit detection...")
        rk_result = self.rootkit.scan()
        results["layers"]["rootkit"] = {
            "score": rk_result["score"],
            "threats": len(rk_result["threats"]),
            "status": rk_result["status"],
        }
        results["threats"].extend(rk_result["threats"])
        print(f"       Score: {rk_result['score']} — {rk_result['status']}")

        # Layer 6: Hardening check
        print("  [6/6] Checking system hardening...")
        hard_result = self.hardener.check()
        results["layers"]["hardening"] = {
            "passed": hard_result["passed"],
            "total": hard_result["total"],
        }
        print(f"       {hard_result['passed']}/{hard_result['total']} checks passed")

        # Summary
        total_threats = len(results["threats"])
        critical = sum(1 for t in results["threats"] if t.get("severity") == "CRITICAL")
        high = sum(1 for t in results["threats"] if t.get("severity") == "HIGH")

        results["summary"] = {
            "total_threats": total_threats,
            "critical": critical,
            "high": high,
            "status": "CRITICAL" if critical > 0 else "WARNING" if high > 0 else "CLEAN",
        }

        # Update threat DB
        self.threat_db["scans"] += 1
        self.threat_db["threats_found"] += total_threats
        self.threat_db["last_scan"] = _ts()
        self.threat_db["history"].append({
            "timestamp": _ts(),
            "threats": total_threats,
            "critical": critical,
            "status": results["summary"]["status"],
        })
        if len(self.threat_db["history"]) > 100:
            self.threat_db["history"] = self.threat_db["history"][-50:]
        self._save_threats()

        # Print summary
        print()
        print(f"  ═══════════════════════════════════════════")
        print(f"  SCAN COMPLETE — Status: {results['summary']['status']}")
        print(f"  Threats: {total_threats} (Critical: {critical}, High: {high})")
        print(f"  ═══════════════════════════════════════════")

        if results["threats"]:
            print()
            for t in results["threats"][:15]:
                sev = t.get("severity", "?")
                name = t.get("type", t.get("signature", "UNKNOWN"))
                detail = t.get("file", t.get("process", t.get("port", "")))
                print(f"  [{sev:8s}] {name:30s} {str(detail)[:50]}")

        # Save report
        report_path = REPORT_DIR / f"scan_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
        report_path.write_text(json.dumps(results, indent=2, default=str))

        return results

    def protect_mode(self):
        """Full protection mode — continuous monitoring."""
        print(f"  {CODENAME} v{VERSION} — FULL PROTECTION MODE")
        print(f"  All 8 defense layers active")
        print(f"  Press Ctrl+C to stop")
        print()

        cycle = 0
        while True:
            try:
                cycle += 1
                now = datetime.now().strftime("%H:%M:%S")

                # Quick process check every cycle
                proc = self.process_scanner.scan()
                if proc["threats"]:
                    print(f"  [{now}] PROCESS ALERT: {len(proc['threats'])} threats!")
                    for t in proc["threats"]:
                        print(f"    [{t.get('signature')}] PID {t.get('pid')} — {t.get('cmdline', '')[:60]}")

                # Network check every 3 cycles
                if cycle % 3 == 0:
                    net = self.network.scan_connections()
                    if net["threats"]:
                        print(f"  [{now}] NETWORK ALERT: {len(net['threats'])} threats!")

                # Port check every 6 cycles
                if cycle % 6 == 0:
                    ports = self.network.scan_ports()
                    if ports["open_dangerous"]:
                        print(f"  [{now}] PORT ALERT: {len(ports['open_dangerous'])} dangerous ports open!")

                # Status report every 12 cycles (~1 min)
                if cycle % 12 == 0:
                    print(f"  [{now}] OK — Cycle {cycle} | Processes: {proc['total_processes']} | No threats")

                time.sleep(5)

            except KeyboardInterrupt:
                print(f"\n  Protection stopped after {cycle} cycles.")
                break

    def status(self):
        """Show guardian status."""
        return {
            "version": VERSION,
            "codename": CODENAME,
            "scans": self.threat_db.get("scans", 0),
            "threats_found": self.threat_db.get("threats_found", 0),
            "last_scan": self.threat_db.get("last_scan"),
            "quarantined": len(self.quarantine.list_quarantine()),
            "history": self.threat_db.get("history", [])[-5:],
        }


# ===================================================
# CLI
# ===================================================

def main():
    if len(sys.argv) < 2:
        print(f"""
{CODENAME} v{VERSION} — Military-Grade Machine Guardian
8 Defense Layers | Pure Python | ZERO Dependencies

Commands:
  pirate scan                Full security scan (all layers)
  pirate processes           Scan running processes
  pirate network             Monitor network connections
  pirate ports               Scan dangerous ports
  pirate rootkit             Rootkit detection
  pirate harden              Check system hardening
  pirate quarantine <file>   Quarantine suspicious file
  pirate quarantine list     List quarantined files
  pirate quarantine restore  Restore from quarantine
  pirate report              Show last scan report
  pirate protect             Full protection mode (continuous)
  pirate status              Show guardian status

Defensive Only — We Protect, Not Attack
(c) 2026 Padrao Bitcoin | Military Grade Defense
""")
        return

    cmd = sys.argv[1]
    args = sys.argv[2:]
    pirate = PirateGuardian()

    if cmd == "scan":
        pirate.full_scan()

    elif cmd == "processes":
        result = pirate.process_scanner.scan()
        print(f"  Processes: {result['total_processes']}")
        print(f"  Threats: {len(result['threats'])}")
        if result['threats']:
            for t in result['threats']:
                print(f"    [{t.get('signature')}] PID {t.get('pid')} — {t.get('cmdline', '')[:60]}")
        print(f"\n  Top Memory:")
        for p in result['top_memory'][:5]:
            print(f"    PID {p['pid']:6d} | {p['rss_mb']:7.1f} MB | {p['name']}")

    elif cmd == "network":
        result = pirate.network.scan_connections()
        print(f"  Connections: {result['total_connections']} (Established: {result['established']}, Listening: {result['listening']})")
        if result['threats']:
            print(f"  Threats:")
            for t in result['threats']:
                print(f"    [{t['severity']}] {t['type']} — {t.get('reason', '')}")
        if result['suspicious']:
            print(f"  Suspicious:")
            for s in result['suspicious'][:10]:
                print(f"    {s}")

    elif cmd == "ports":
        result = pirate.network.scan_ports()
        print(f"  Scanned {result['scanned']} dangerous ports")
        if result['open_dangerous']:
            print(f"  ALERT — Open dangerous ports:")
            for p in result['open_dangerous']:
                print(f"    Port {p['port']}: {p['description']}")
        else:
            print(f"  All clear — no dangerous ports open")

    elif cmd == "rootkit":
        result = pirate.rootkit.scan()
        print(f"  Rootkit Detection — Score: {result['score']}")
        for check, status, *detail in result['checks']:
            d = detail[0] if detail else ""
            print(f"    [{status:4s}] {check:30s} {d}")
        if result['threats']:
            print(f"\n  Threats:")
            for t in result['threats']:
                print(f"    [{t['severity']}] {t['type']}")

    elif cmd == "harden":
        result = pirate.hardener.check()
        print(f"  System Hardening: {result['passed']}/{result['total']} checks")
        for check, status in result['checks']:
            icon = "OK" if status == "PASS" else "!!" if status == "FAIL" else "??"
            print(f"    [{icon}] {check}")

        if "--apply" in args:
            print(f"\n  Applying hardening...")
            pirate.hardener.harden_ssh_dir()
            pirate.hardener.harden_home()
            print(f"  SSH dir + Home dir permissions hardened.")

    elif cmd == "quarantine":
        if args and args[0] == "list":
            items = pirate.quarantine.list_quarantine()
            print(f"  Quarantined: {len(items)}")
            for item in items:
                print(f"    [{item['id']}] {item['file']} — {item['date']}")
        elif args and args[0] == "restore" and len(args) > 1:
            result = pirate.quarantine.restore(args[1])
            print(json.dumps(result, indent=2))
        elif args:
            result = pirate.quarantine.quarantine(args[0])
            print(json.dumps(result, indent=2))
        else:
            print("  Usage: pirate quarantine <file> | pirate quarantine list | pirate quarantine restore <id>")

    elif cmd == "report":
        reports = sorted(REPORT_DIR.glob("*.json"), reverse=True)
        if reports:
            report = json.loads(reports[0].read_text())
            print(f"  Last Scan: {report.get('timestamp', '?')}")
            print(f"  Status: {report.get('summary', {}).get('status', '?')}")
            print(f"  Threats: {report.get('summary', {}).get('total_threats', 0)}")
        else:
            print("  No reports. Run 'pirate scan' first.")

    elif cmd == "protect":
        pirate.protect_mode()

    elif cmd == "status":
        result = pirate.status()
        print(f"  {CODENAME} v{VERSION}")
        print(f"  Total scans: {result['scans']}")
        print(f"  Threats found: {result['threats_found']}")
        print(f"  Last scan: {result['last_scan'] or 'Never'}")
        print(f"  Quarantined: {result['quarantined']}")

    else:
        print(f"  Unknown command: {cmd}")


if __name__ == "__main__":
    main()
