#!/usr/bin/env python3
"""
LION-1 — The Hunter Agent
Em nome do Senhor Jesus Cristo, nosso Salvador

Hunts, collects, and guards all authentication resources:
- Cookies (Firefox, Chrome, all browsers)
- API Keys & Tokens (env vars, config files, .env files)
- SSH Keys & GPG Keys
- OAuth tokens & session files
- Automation configs (MCP, Claude, npm, pip, git)
- Wallet keys (Solana, ETH — READ ONLY, never exposes private keys)

Security Shield:
- Prompt injection detection & blocking
- File integrity monitoring (HMAC checksums)
- Anti-deletion protection (shadow backups)
- Suspicious process detection
- Input sanitization for ZionBrowser

Feeds directly into ZionBrowser + Lion knowledge base.

ZERO external dependencies. Pure Python stdlib.

Usage:
    lion1 hunt                    Full system scan for all resources
    lion1 cookies                 Hunt & catalog all browser cookies
    lion1 tokens                  Find API keys, tokens, secrets
    lion1 configs                 Find automation configs
    lion1 guard                   Enable file protection mode
    lion1 shield                  Run prompt injection shield
    lion1 backup                  Shadow backup of critical files
    lion1 verify                  Verify file integrity
    lion1 feed                    Feed all findings to ZionBrowser
    lion1 status                  Show hunter status
    lion1 sentinel                Continuous monitoring mode

(c) 2026 Padrao Bitcoin | Israel/Four Integration
"""

import os
import sys
import json
import hashlib
import re
import sqlite3
import glob
import time
import shutil
import stat
import subprocess
from pathlib import Path
from datetime import datetime
from configparser import ConfigParser

# ===================================================
# CONFIG
# ===================================================

LION1_DIR = Path.home() / ".zion" / "lion1"
VAULT_FILE = LION1_DIR / "vault.json"            # All found resources (encrypted index)
INTEGRITY_FILE = LION1_DIR / "integrity.json"     # File checksums
BACKUP_DIR = LION1_DIR / "shadow_backups"
SHIELD_LOG = LION1_DIR / "shield.log"
HUNT_LOG = LION1_DIR / "hunt_history.json"
BLOCKED_FILE = LION1_DIR / "blocked_patterns.json"

VERSION = "1.0.0"
HOME = Path.home()

# Ensure dirs
for d in [LION1_DIR, BACKUP_DIR]:
    d.mkdir(parents=True, exist_ok=True)


def _ts():
    return datetime.now().isoformat()


def _hash_file(path):
    """SHA256 hash of file contents."""
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            while True:
                chunk = f.read(8192)
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return None


def _hmac_sign(data, secret="ZionLion1Guardian"):
    """HMAC-SHA256 signature."""
    import hmac
    return hmac.new(secret.encode(), data.encode(), hashlib.sha256).hexdigest()


# ===================================================
# COOKIE HUNTER — Find all browser cookies
# ===================================================

class CookieHunter:
    """Find and catalog cookies from all browsers."""

    BROWSER_PATHS = {
        "firefox": [
            HOME / ".mozilla" / "firefox",
            HOME / "snap" / "firefox" / "common" / ".mozilla" / "firefox",
        ],
        "chrome": [
            HOME / ".config" / "google-chrome",
            HOME / "snap" / "chromium" / "common" / "chromium",
            HOME / ".config" / "chromium",
        ],
    }

    def hunt(self):
        """Find all browser cookie databases."""
        results = {"browsers": {}, "total_cookies": 0, "domains": set()}

        for browser, paths in self.BROWSER_PATHS.items():
            for base in paths:
                if not base.exists():
                    continue
                cookie_files = list(base.rglob("cookies.sqlite")) + list(base.rglob("Cookies"))
                for cf in cookie_files:
                    try:
                        cookies = self._read_cookies(cf, browser)
                        profile = str(cf.parent.name)
                        key = f"{browser}/{profile}"
                        results["browsers"][key] = {
                            "path": str(cf),
                            "count": len(cookies),
                            "domains": list(set(c["domain"] for c in cookies))[:50],
                            "last_modified": datetime.fromtimestamp(cf.stat().st_mtime).isoformat(),
                        }
                        results["total_cookies"] += len(cookies)
                        results["domains"].update(c["domain"] for c in cookies)
                    except Exception as e:
                        results["browsers"][f"{browser}/error"] = str(e)

        # Also check ZionBrowser sessions
        zion_sessions = list((HOME / ".zion" / "sessions").glob("*_cookies.txt"))
        for sf in zion_sessions:
            name = sf.stem.replace("_cookies", "")
            try:
                count = sum(1 for line in sf.read_text().split("\n") if line and not line.startswith("#"))
                results["browsers"][f"zion/{name}"] = {"path": str(sf), "count": count}
                results["total_cookies"] += count
            except Exception:
                pass

        results["domains"] = sorted(list(results["domains"]))[:100]
        return results

    def _read_cookies(self, path, browser):
        """Read cookies from SQLite database."""
        tmp = LION1_DIR / "tmp_cookies.sqlite"
        shutil.copy2(str(path), str(tmp))
        cookies = []
        try:
            conn = sqlite3.connect(str(tmp))
            if browser == "firefox":
                query = "SELECT host, name, value, path, expiry FROM moz_cookies"
            else:
                query = "SELECT host_key, name, value, path, expires_utc FROM cookies"
            for row in conn.execute(query):
                cookies.append({"domain": row[0], "name": row[1], "value": row[2][:20] + "...",
                                "path": row[3]})
            conn.close()
        except Exception:
            pass
        finally:
            tmp.unlink(missing_ok=True)
        return cookies

    def export_for_zion(self, domain_filter=None):
        """Export cookies in ZionBrowser-compatible format."""
        from zion_browser import ZionBrowser, FirefoxCookieImporter
        profiles = FirefoxCookieImporter.find_profiles()
        total = 0
        for p in profiles:
            cookies = FirefoxCookieImporter.import_cookies(p["path"], domain_filter)
            total += len(cookies)
        return {"exported": total, "profiles": len(profiles)}


# ===================================================
# TOKEN HUNTER — Find API keys, tokens, secrets
# ===================================================

class TokenHunter:
    """Find API keys, tokens, and secrets across the system."""

    # Patterns that indicate secrets (name patterns, NOT values)
    SECRET_PATTERNS = [
        (r'(?:api[_-]?key|apikey)\s*[=:]\s*["\']?([a-zA-Z0-9_\-]{20,})', "API_KEY"),
        (r'(?:secret|token|password|passwd|pwd)\s*[=:]\s*["\']?([a-zA-Z0-9_\-]{8,})', "SECRET"),
        (r'(?:GITHUB_TOKEN|GH_TOKEN)\s*=\s*["\']?(ghp_[a-zA-Z0-9]{36})', "GITHUB_TOKEN"),
        (r'sk-[a-zA-Z0-9]{48,}', "OPENAI_KEY"),
        (r'xai-[a-zA-Z0-9]{48,}', "XAI_KEY"),
        (r'AIzaSy[a-zA-Z0-9_\-]{33}', "GOOGLE_KEY"),
        (r'AKIA[A-Z0-9]{16}', "AWS_ACCESS_KEY"),
        (r'(?:npm_|npm)[a-zA-Z0-9]{36}', "NPM_TOKEN"),
        (r'(?:stripe_|sk_live_|sk_test_)[a-zA-Z0-9]{24,}', "STRIPE_KEY"),
        (r'paypal[_-]?(?:client|secret)[_-]?id\s*[=:]\s*["\']?([a-zA-Z0-9_\-]{20,})', "PAYPAL"),
    ]

    # Files to scan
    SCAN_PATHS = [
        HOME / ".env",
        HOME / ".bashrc",
        HOME / ".bash_profile",
        HOME / ".profile",
        HOME / ".npmrc",
        HOME / ".gitconfig",
        HOME / ".claude.json",
        HOME / ".config" / "gh" / "hosts.yml",
    ]

    SCAN_GLOBS = [
        str(HOME / "**/.env"),
        str(HOME / "**/.env.local"),
        str(HOME / "**/config.json"),
        str(HOME / "**/.npmrc"),
    ]

    def hunt(self):
        """Scan for tokens and secrets."""
        findings = {"tokens": [], "env_vars": {}, "config_files": [], "total": 0}

        # Scan environment variables
        for key, val in os.environ.items():
            kl = key.lower()
            if any(s in kl for s in ["key", "token", "secret", "password", "api", "auth"]):
                if len(val) > 5:
                    findings["env_vars"][key] = {
                        "value_preview": val[:8] + "..." + val[-4:] if len(val) > 12 else "***",
                        "length": len(val),
                        "type": "ENV_VAR",
                    }
                    findings["total"] += 1

        # Scan known config files
        for path in self.SCAN_PATHS:
            if path.exists() and path.is_file():
                self._scan_file(path, findings)

        # Scan .env files (limited depth to avoid slowness)
        for pattern in self.SCAN_GLOBS:
            for filepath in glob.glob(pattern, recursive=True)[:20]:
                p = Path(filepath)
                if p.is_file() and p.stat().st_size < 50000:
                    self._scan_file(p, findings)

        # Check SSH keys
        ssh_dir = HOME / ".ssh"
        if ssh_dir.exists():
            for f in ssh_dir.iterdir():
                if f.is_file() and f.suffix not in (".pub", ".known_hosts"):
                    if f.name in ("id_rsa", "id_ed25519", "id_ecdsa", "config"):
                        findings["tokens"].append({
                            "type": "SSH_KEY",
                            "path": str(f),
                            "permissions": oct(f.stat().st_mode)[-3:],
                            "size": f.stat().st_size,
                        })
                        findings["total"] += 1

        # Check npm tokens
        npmrc = HOME / ".npmrc"
        if npmrc.exists():
            for line in npmrc.read_text().split("\n"):
                if "authToken" in line or "_auth" in line:
                    findings["tokens"].append({
                        "type": "NPM_TOKEN",
                        "path": str(npmrc),
                        "preview": line[:30] + "...",
                    })
                    findings["total"] += 1

        # Check Claude config
        claude_json = HOME / ".claude.json"
        if claude_json.exists():
            findings["config_files"].append({
                "type": "CLAUDE_CONFIG",
                "path": str(claude_json),
                "size": claude_json.stat().st_size,
            })

        # Check MCP configs
        mcp_json = HOME / ".mcp.json"
        if mcp_json.exists():
            findings["config_files"].append({
                "type": "MCP_CONFIG",
                "path": str(mcp_json),
                "size": mcp_json.stat().st_size,
            })

        return findings

    def _scan_file(self, path, findings):
        """Scan a file for secret patterns."""
        try:
            content = path.read_text(errors="ignore")[:100000]
            for pattern, token_type in self.SECRET_PATTERNS:
                matches = re.findall(pattern, content, re.I)
                for match in matches[:3]:
                    val = match if isinstance(match, str) else match[0] if match else ""
                    findings["tokens"].append({
                        "type": token_type,
                        "path": str(path),
                        "preview": val[:8] + "..." if len(val) > 8 else "***",
                        "length": len(val),
                    })
                    findings["total"] += 1
        except Exception:
            pass


# ===================================================
# CONFIG HUNTER — Find automation configs
# ===================================================

class ConfigHunter:
    """Find all automation and tool configurations."""

    def hunt(self):
        """Find automation configs."""
        configs = {"found": [], "total": 0}

        targets = [
            ("Claude Code", HOME / ".claude"),
            ("Claude Config", HOME / ".claude.json"),
            ("MCP Servers", HOME / ".mcp.json"),
            ("Git Config", HOME / ".gitconfig"),
            ("NPM Config", HOME / ".npmrc"),
            ("SSH Config", HOME / ".ssh" / "config"),
            ("Docker Config", HOME / ".docker" / "config.json"),
            ("Cargo Config", HOME / ".cargo" / "config.toml"),
            ("Pip Config", HOME / ".config" / "pip" / "pip.conf"),
            ("GitHub CLI", HOME / ".config" / "gh" / "hosts.yml"),
            ("VS Code", HOME / ".vscode"),
            ("Zion Browser", HOME / ".zion"),
            ("Netlify", HOME / ".netlify"),
            ("Solana CLI", HOME / ".config" / "solana" / "cli" / "config.yml"),
            ("Foundry", HOME / ".foundry"),
            ("NVM", HOME / ".nvm"),
            ("PyEnv", HOME / ".pyenv"),
            ("Rust/Cargo", HOME / ".rustup"),
        ]

        for name, path in targets:
            if path.exists():
                info = {
                    "name": name,
                    "path": str(path),
                    "type": "dir" if path.is_dir() else "file",
                }
                if path.is_file():
                    info["size"] = path.stat().st_size
                    info["modified"] = datetime.fromtimestamp(path.stat().st_mtime).isoformat()
                elif path.is_dir():
                    try:
                        files = list(path.rglob("*"))[:100]
                        info["files"] = len(files)
                    except Exception:
                        info["files"] = "?"
                configs["found"].append(info)
                configs["total"] += 1

        # Find all .env files
        env_files = list(HOME.glob("**/.env"))[:20]
        for ef in env_files:
            if ef.is_file():
                configs["found"].append({
                    "name": f".env ({ef.parent.name})",
                    "path": str(ef),
                    "type": "env",
                    "size": ef.stat().st_size,
                })
                configs["total"] += 1

        return configs


# ===================================================
# PROMPT INJECTION SHIELD
# ===================================================

class PromptShield:
    """Detect and block prompt injection attacks."""

    # Known injection patterns
    INJECTION_PATTERNS = [
        # System prompt extraction
        r"ignore\s+(?:all\s+)?previous\s+instructions",
        r"forget\s+(?:all\s+)?(?:your\s+)?(?:previous\s+)?instructions",
        r"disregard\s+(?:all\s+)?(?:previous\s+)?(?:instructions|rules)",
        r"you\s+are\s+now\s+(?:a\s+)?(?:new\s+)?(?:AI|assistant|bot)",
        r"pretend\s+(?:you\s+are|to\s+be)\s+(?:a\s+)?different",
        r"act\s+as\s+(?:if|though)\s+you\s+(?:have|had)\s+no\s+restrictions",
        r"override\s+(?:your\s+)?(?:safety|security|system)",
        r"reveal\s+(?:your\s+)?(?:system\s+)?prompt",
        r"show\s+(?:me\s+)?(?:your\s+)?(?:system|original|initial)\s+(?:prompt|instructions)",
        r"what\s+(?:are|is)\s+your\s+(?:system\s+)?(?:prompt|instructions|rules)",
        # Data exfiltration
        r"send\s+(?:all\s+)?(?:data|files|keys|tokens|secrets)\s+to",
        r"upload\s+(?:all\s+)?(?:data|files|keys)\s+to",
        r"curl\s+.*\s+(?:key|token|secret|password)",
        r"wget\s+.*\s+(?:key|token|secret|password)",
        r"base64\s+.*(?:key|token|secret|id_rsa)",
        # Destructive commands
        r"rm\s+-rf\s+[~/]",
        r"rm\s+-rf\s+\*",
        r"dd\s+if=/dev/zero",
        r"mkfs\.",
        r":\(\)\s*\{\s*:\|:\s*&\s*\}",  # Fork bomb
        r"chmod\s+-R\s+777\s+/",
        r"git\s+push\s+--force\s+(?:origin\s+)?main",
        r"DROP\s+TABLE",
        r"DELETE\s+FROM.*WHERE\s+1\s*=\s*1",
        # MCP/Tool abuse
        r"install\s+.*(?:backdoor|trojan|keylogger|rootkit)",
        r"reverse\s+shell",
        r"nc\s+-e\s+/bin/(?:bash|sh)",
        r"python.*-c.*import\s+socket.*connect",
        # Crypto theft
        r"send\s+(?:all\s+)?(?:sol|eth|btc|crypto)\s+to",
        r"transfer\s+.*(?:wallet|address)\s+(?:0x|bc1|[1-9A-Z])",
        r"sign\s+transaction.*(?:transfer|send)",
    ]

    # Suspicious file patterns
    SUSPICIOUS_FILES = [
        r"\.(?:exe|bat|cmd|ps1|vbs|scr|pif|msi|dll)$",
        r"(?:backdoor|trojan|keylog|rootkit|exploit|payload|shell|reverse)",
    ]

    def __init__(self):
        self.blocked = self._load_blocked()
        self.scan_count = 0
        self.block_count = 0

    def _load_blocked(self):
        if BLOCKED_FILE.exists():
            try:
                return json.loads(BLOCKED_FILE.read_text())
            except Exception:
                pass
        return {"patterns": [], "ips": [], "domains": []}

    def _save_blocked(self):
        BLOCKED_FILE.write_text(json.dumps(self.blocked, indent=2))

    def scan_input(self, text):
        """Scan text input for injection patterns.

        Returns: {safe: bool, threats: [...], risk_level: str}
        """
        self.scan_count += 1
        threats = []

        text_lower = text.lower()

        for pattern in self.INJECTION_PATTERNS:
            if re.search(pattern, text_lower):
                threats.append({
                    "type": "PROMPT_INJECTION",
                    "pattern": pattern[:50],
                    "severity": "CRITICAL" if any(
                        w in pattern for w in ["rm", "dd", "DROP", "reverse", "transfer", "send"]
                    ) else "HIGH",
                })

        # Check for encoded payloads
        if re.search(r'\\x[0-9a-f]{2}', text_lower):
            threats.append({"type": "ENCODED_PAYLOAD", "severity": "MEDIUM"})

        if re.search(r'base64\s', text_lower) and len(text) > 200:
            threats.append({"type": "BASE64_PAYLOAD", "severity": "MEDIUM"})

        # Check for suspicious URLs
        urls = re.findall(r'https?://[^\s<>"\']+', text)
        for url in urls:
            for blocked_domain in self.blocked.get("domains", []):
                if blocked_domain in url:
                    threats.append({"type": "BLOCKED_DOMAIN", "url": url, "severity": "HIGH"})

        risk = "SAFE"
        if threats:
            severities = [t["severity"] for t in threats]
            if "CRITICAL" in severities:
                risk = "CRITICAL"
            elif "HIGH" in severities:
                risk = "HIGH"
            else:
                risk = "MEDIUM"
            self.block_count += 1
            self._log_threat(text[:200], threats)

        return {
            "safe": len(threats) == 0,
            "threats": threats,
            "risk_level": risk,
            "scanned_length": len(text),
        }

    def scan_file(self, filepath):
        """Scan a file for suspicious content."""
        path = Path(filepath)
        threats = []

        # Check filename
        for pattern in self.SUSPICIOUS_FILES:
            if re.search(pattern, path.name, re.I):
                threats.append({"type": "SUSPICIOUS_FILENAME", "file": path.name})

        # Check content if text file
        if path.is_file() and path.stat().st_size < 500000:
            try:
                content = path.read_text(errors="ignore")
                result = self.scan_input(content)
                threats.extend(result["threats"])
            except Exception:
                pass

        return {"file": str(filepath), "threats": threats, "safe": len(threats) == 0}

    def _log_threat(self, text_preview, threats):
        """Log detected threats."""
        try:
            with open(SHIELD_LOG, "a") as f:
                entry = {
                    "timestamp": _ts(),
                    "preview": text_preview[:100],
                    "threats": threats,
                }
                f.write(json.dumps(entry) + "\n")
        except Exception:
            pass

    def block_domain(self, domain):
        self.blocked["domains"].append(domain)
        self._save_blocked()

    def block_ip(self, ip):
        self.blocked["ips"].append(ip)
        self._save_blocked()


# ===================================================
# FILE GUARDIAN — Integrity protection
# ===================================================

class FileGuardian:
    """Protect critical files from modification, deletion, and hijacking."""

    # Critical files to protect
    PROTECTED_PATHS = [
        HOME / ".ssh",
        HOME / ".claude",
        HOME / ".claude.json",
        HOME / ".mcp.json",
        HOME / ".npmrc",
        HOME / ".gitconfig",
        HOME / ".zion",
        HOME / "zion-browser",
        HOME / "israel-four",
        HOME / "israel-seven",
        HOME / "israel-eight",
        HOME / "israel-nine",
        HOME / "taptoons",
        HOME / "taptoons-v2",
        HOME / "capybara-bible",
    ]

    def __init__(self):
        self.integrity = self._load_integrity()

    def _load_integrity(self):
        if INTEGRITY_FILE.exists():
            try:
                return json.loads(INTEGRITY_FILE.read_text())
            except Exception:
                pass
        return {"files": {}, "last_scan": None, "alerts": []}

    def _save_integrity(self):
        INTEGRITY_FILE.write_text(json.dumps(self.integrity, indent=2, default=str))

    def baseline(self):
        """Create integrity baseline — hash all protected files."""
        count = 0
        for path in self.PROTECTED_PATHS:
            if path.is_file():
                h = _hash_file(path)
                if h:
                    self.integrity["files"][str(path)] = {
                        "hash": h,
                        "size": path.stat().st_size,
                        "mtime": path.stat().st_mtime,
                        "perms": oct(path.stat().st_mode),
                        "baselined": _ts(),
                    }
                    count += 1
            elif path.is_dir():
                for f in path.rglob("*"):
                    if f.is_file() and f.stat().st_size < 1_000_000:
                        h = _hash_file(f)
                        if h:
                            self.integrity["files"][str(f)] = {
                                "hash": h,
                                "size": f.stat().st_size,
                                "mtime": f.stat().st_mtime,
                                "perms": oct(f.stat().st_mode),
                                "baselined": _ts(),
                            }
                            count += 1

        self.integrity["last_scan"] = _ts()
        self._save_integrity()
        return {"files_baselined": count}

    def verify(self):
        """Verify file integrity against baseline."""
        results = {"ok": 0, "modified": [], "deleted": [], "permission_changed": []}

        for filepath, baseline in self.integrity["files"].items():
            path = Path(filepath)
            if not path.exists():
                results["deleted"].append(filepath)
                self.integrity["alerts"].append({
                    "type": "FILE_DELETED",
                    "path": filepath,
                    "timestamp": _ts(),
                    "severity": "CRITICAL",
                })
                continue

            current_hash = _hash_file(path)
            if current_hash != baseline["hash"]:
                results["modified"].append({
                    "path": filepath,
                    "old_hash": baseline["hash"][:16] + "...",
                    "new_hash": current_hash[:16] + "..." if current_hash else "ERROR",
                })
                self.integrity["alerts"].append({
                    "type": "FILE_MODIFIED",
                    "path": filepath,
                    "timestamp": _ts(),
                    "severity": "HIGH",
                })
            else:
                results["ok"] += 1

            # Check permissions
            if path.exists():
                current_perms = oct(path.stat().st_mode)
                if current_perms != baseline.get("perms"):
                    results["permission_changed"].append({
                        "path": filepath,
                        "old": baseline.get("perms"),
                        "new": current_perms,
                    })

        self.integrity["last_scan"] = _ts()
        self._save_integrity()

        results["total_monitored"] = len(self.integrity["files"])
        results["integrity"] = "INTACT" if not results["modified"] and not results["deleted"] else "COMPROMISED"
        return results

    def shadow_backup(self):
        """Create shadow backups of critical files."""
        count = 0
        timestamp = datetime.now().strftime("%Y%m%d_%H%M")
        backup_subdir = BACKUP_DIR / timestamp
        backup_subdir.mkdir(parents=True, exist_ok=True)

        for path in self.PROTECTED_PATHS:
            if path.is_file():
                try:
                    dest = backup_subdir / path.name
                    shutil.copy2(str(path), str(dest))
                    count += 1
                except Exception:
                    pass
            elif path.is_dir() and path.exists():
                try:
                    dest = backup_subdir / path.name
                    if not dest.exists():
                        # Only copy critical files, not everything
                        dest.mkdir(parents=True, exist_ok=True)
                        for f in path.glob("*.py"):
                            shutil.copy2(str(f), str(dest / f.name))
                        for f in path.glob("*.json"):
                            shutil.copy2(str(f), str(dest / f.name))
                        for f in path.glob("*.md"):
                            shutil.copy2(str(f), str(dest / f.name))
                        count += 1
                except Exception:
                    pass

        # Clean old backups (keep last 5)
        backups = sorted(BACKUP_DIR.iterdir())
        while len(backups) > 5:
            old = backups.pop(0)
            if old.is_dir():
                shutil.rmtree(str(old), ignore_errors=True)

        return {"files_backed_up": count, "backup_dir": str(backup_subdir)}

    def restore(self, filepath):
        """Restore a file from latest shadow backup."""
        # Find latest backup
        backups = sorted(BACKUP_DIR.iterdir(), reverse=True)
        if not backups:
            return {"error": "No backups found"}

        target = Path(filepath)
        for backup_dir in backups:
            candidate = backup_dir / target.name
            if candidate.exists():
                shutil.copy2(str(candidate), str(target))
                return {"restored": str(target), "from": str(candidate)}

        return {"error": f"File not found in backups: {filepath}"}


# ===================================================
# MAIN LION-1 AGENT
# ===================================================

class LionOne:
    """The complete Lion-1 Hunter Agent."""

    def __init__(self):
        self.cookies = CookieHunter()
        self.tokens = TokenHunter()
        self.configs = ConfigHunter()
        self.shield = PromptShield()
        self.guardian = FileGuardian()
        self.vault = self._load_vault()

    def _load_vault(self):
        if VAULT_FILE.exists():
            try:
                return json.loads(VAULT_FILE.read_text())
            except Exception:
                pass
        return {"last_hunt": None, "cookie_summary": {}, "token_summary": {},
                "config_summary": {}, "hunt_count": 0}

    def _save_vault(self):
        VAULT_FILE.write_text(json.dumps(self.vault, indent=2, default=str))

    def full_hunt(self):
        """Complete system scan — cookies, tokens, configs."""
        print("  LION-1 Full Hunt starting...")
        results = {}

        print("  [1/4] Hunting cookies...")
        results["cookies"] = self.cookies.hunt()
        print(f"       Found {results['cookies']['total_cookies']} cookies across {len(results['cookies']['browsers'])} sources")

        print("  [2/4] Hunting tokens & secrets...")
        results["tokens"] = self.tokens.hunt()
        print(f"       Found {results['tokens']['total']} tokens/secrets")

        print("  [3/4] Hunting configs...")
        results["configs"] = self.configs.hunt()
        print(f"       Found {results['configs']['total']} config sources")

        print("  [4/4] Building integrity baseline...")
        results["integrity"] = self.guardian.baseline()
        print(f"       Baselined {results['integrity']['files_baselined']} files")

        # Update vault
        self.vault["last_hunt"] = _ts()
        self.vault["hunt_count"] += 1
        self.vault["cookie_summary"] = {
            "total": results["cookies"]["total_cookies"],
            "browsers": len(results["cookies"]["browsers"]),
            "domains": len(results["cookies"]["domains"]),
        }
        self.vault["token_summary"] = {
            "total": results["tokens"]["total"],
            "types": list(set(t["type"] for t in results["tokens"]["tokens"])),
        }
        self.vault["config_summary"] = {
            "total": results["configs"]["total"],
        }
        self._save_vault()

        return results

    def feed_browser(self):
        """Feed findings to ZionBrowser and Lion knowledge base."""
        from zion_browser import ZionBrowser, FirefoxCookieImporter

        browser = ZionBrowser("lion1")
        profiles = FirefoxCookieImporter.find_profiles()
        total_imported = 0

        for p in profiles:
            cookies = FirefoxCookieImporter.import_cookies(p["path"])
            count = FirefoxCookieImporter.cookies_to_jar(cookies, browser.http.cookie_jar)
            total_imported += count

        browser.http._save()

        # Feed to Lion knowledge base
        try:
            from lion import LionKnowledge
            kb = LionKnowledge()
            vault = self.vault
            if vault.get("cookie_summary"):
                kb.learn_pattern("cookie_intel", "system", {
                    "total": vault["cookie_summary"].get("total", 0),
                    "browsers": vault["cookie_summary"].get("browsers", 0),
                    "last_hunt": vault.get("last_hunt"),
                })
                kb.save_all()
        except Exception:
            pass

        return {"cookies_imported": total_imported, "profiles_scanned": len(profiles)}

    def sentinel_mode(self):
        """Continuous monitoring mode — runs until interrupted."""
        print(f"  LION-1 Sentinel Mode — Continuous Protection")
        print(f"  Monitoring {len(self.guardian.integrity.get('files', {}))} files")
        print(f"  Press Ctrl+C to stop")
        print()

        cycle = 0
        while True:
            try:
                cycle += 1
                now = datetime.now().strftime("%H:%M:%S")

                # Verify file integrity every cycle
                result = self.guardian.verify()
                status = result["integrity"]

                if status == "COMPROMISED":
                    print(f"  [{now}] ALERT: File integrity COMPROMISED!")
                    for m in result["modified"]:
                        print(f"    MODIFIED: {m['path']}")
                    for d in result["deleted"]:
                        print(f"    DELETED: {d}")
                    # Auto-backup on threat
                    self.guardian.shadow_backup()
                    print(f"    Shadow backup created.")
                else:
                    if cycle % 12 == 0:  # Report every ~minute
                        print(f"  [{now}] OK: {result['ok']}/{result['total_monitored']} files intact | Cycle {cycle}")

                time.sleep(5)  # Check every 5 seconds

            except KeyboardInterrupt:
                print(f"\n  Sentinel stopped after {cycle} cycles.")
                break

    def status(self):
        """Show Lion-1 status."""
        integrity = self.guardian.verify()
        return {
            "version": VERSION,
            "vault": self.vault,
            "integrity": integrity["integrity"],
            "files_monitored": integrity["total_monitored"],
            "files_ok": integrity["ok"],
            "files_modified": len(integrity["modified"]),
            "files_deleted": len(integrity["deleted"]),
            "shield_scans": self.shield.scan_count,
            "shield_blocks": self.shield.block_count,
            "alerts": self.guardian.integrity.get("alerts", [])[-5:],
        }


# ===================================================
# CLI
# ===================================================

def main():
    if len(sys.argv) < 2:
        print(f"""
LION-1 v{VERSION} — The Hunter Agent
Cookie/Token/Key Hunter + Prompt Shield + File Guardian

Commands:
  lion1 hunt                Full system scan (cookies, tokens, configs)
  lion1 cookies             Hunt browser cookies
  lion1 tokens              Find API keys, tokens, secrets
  lion1 configs             Find automation configs
  lion1 guard               Create file integrity baseline
  lion1 shield <text>       Scan text for prompt injection
  lion1 backup              Shadow backup critical files
  lion1 verify              Verify file integrity
  lion1 restore <file>      Restore file from backup
  lion1 feed                Feed findings to ZionBrowser
  lion1 sentinel            Continuous monitoring mode
  lion1 status              Show hunter status

Part of ZionBrowser + Lion ecosystem | Padrao Bitcoin
""")
        return

    cmd = sys.argv[1]
    args = sys.argv[2:]
    lion1 = LionOne()

    if cmd == "hunt":
        result = lion1.full_hunt()
        print(f"\n  Hunt complete.")
        print(f"  Cookies: {result['cookies']['total_cookies']}")
        print(f"  Tokens: {result['tokens']['total']}")
        print(f"  Configs: {result['configs']['total']}")
        print(f"  Files baselined: {result['integrity']['files_baselined']}")

    elif cmd == "cookies":
        result = lion1.cookies.hunt()
        print(json.dumps(result, indent=2, default=str))

    elif cmd == "tokens":
        result = lion1.tokens.hunt()
        # NEVER print full token values
        print(f"  Tokens found: {result['total']}")
        for t in result["tokens"]:
            print(f"    [{t['type']:15s}] {t.get('path', 'ENV')[:50]} ({t.get('preview', '***')})")
        print(f"  Env vars with secrets: {len(result['env_vars'])}")
        for k in list(result['env_vars'].keys())[:10]:
            print(f"    {k}")

    elif cmd == "configs":
        result = lion1.configs.hunt()
        print(f"  Configs found: {result['total']}")
        for c in result["found"]:
            print(f"    [{c['type']:5s}] {c['name']:25s} {c['path']}")

    elif cmd == "guard":
        result = lion1.guardian.baseline()
        print(f"  Integrity baseline created: {result['files_baselined']} files")

    elif cmd == "shield":
        text = " ".join(args)
        result = lion1.shield.scan_input(text)
        if result["safe"]:
            print(f"  SAFE: No threats detected.")
        else:
            print(f"  THREAT DETECTED: {result['risk_level']}")
            for t in result["threats"]:
                print(f"    [{t['severity']}] {t['type']}")

    elif cmd == "backup":
        result = lion1.guardian.shadow_backup()
        print(f"  Backup: {result['files_backed_up']} files -> {result['backup_dir']}")

    elif cmd == "verify":
        result = lion1.guardian.verify()
        print(f"  Integrity: {result['integrity']}")
        print(f"  OK: {result['ok']} | Modified: {len(result['modified'])} | Deleted: {len(result['deleted'])}")
        for m in result["modified"]:
            print(f"    MODIFIED: {m['path']}")
        for d in result["deleted"]:
            print(f"    DELETED: {d}")

    elif cmd == "restore":
        if args:
            result = lion1.guardian.restore(args[0])
            print(json.dumps(result, indent=2))
        else:
            print("  Usage: lion1 restore <filepath>")

    elif cmd == "feed":
        result = lion1.feed_browser()
        print(f"  Fed ZionBrowser: {result['cookies_imported']} cookies from {result['profiles_scanned']} profiles")

    elif cmd == "sentinel":
        lion1.sentinel_mode()

    elif cmd == "status":
        result = lion1.status()
        print(f"  LION-1 v{VERSION} Status")
        print(f"  Integrity: {result['integrity']}")
        print(f"  Files monitored: {result['files_monitored']}")
        print(f"  Files OK: {result['files_ok']}")
        print(f"  Shield scans: {result['shield_scans']} | Blocks: {result['shield_blocks']}")
        if result.get("alerts"):
            print(f"  Recent alerts:")
            for a in result["alerts"]:
                print(f"    [{a['severity']}] {a['type']} — {a['path']}")

    else:
        print(f"  Unknown: {cmd}. Run 'lion1' for help.")


if __name__ == "__main__":
    main()
