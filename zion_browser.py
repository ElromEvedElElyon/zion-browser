#!/usr/bin/env python3
"""
ZionBrowser v2.0 — Ultra-Lightweight CLI Browser for AI Agents
Em nome do Senhor Jesus Cristo, nosso Salvador

ZERO external dependencies. Pure Python stdlib.
Uses ~3-5MB RAM vs Firefox ~500MB+.
Designed for machines with 3.3GB RAM or less.

NEW in v2.0:
- Firefox cookie import (transfer sessions without re-login)
- Streaming responses (never loads full page into RAM if not needed)
- Task pipeline engine (multi-step automation)
- Smart form detection with CSRF token extraction
- Memory profiler built-in
- Global `zion` command
- JavaScript redirect detection
- Bookmark manager
- Response caching (avoid re-fetching)
- API-first design (importable Python library)
- Multi-session support (switch between accounts)

Usage:
    zion get <url>                     Fetch & show page text
    zion links <url>                   Extract links
    zion forms <url>                   Show forms
    zion submit <url> key=val&k2=v2    POST form data
    zion login <url> <user> <pass>     Login to site
    zion api <url>                     Fetch JSON API
    zion download <url> <file>         Download file
    zion cookies [import|export|list]  Cookie management
    zion session [list|switch|new]     Session management
    zion pipe <pipeline.json>          Execute task pipeline
    zion search <query>                Quick web search via DuckDuckGo
    zion mem                           Show memory usage
    zion i                             Interactive mode
    zion serve [port]                  HTTP API server for AI agents

Product: $29.99 — AI Agent Browser Toolkit
License: Padrao Bitcoin — standardbitcoin.io@gmail.com

(c) 2026 Padrao Bitcoin Atividades de Internet LTDA
CNPJ: 51.148.891/0001-69
"""

import os
import sys
import json
import ssl
import gzip
import zlib
import time
import re
import hashlib
import sqlite3
import struct
import http.cookiejar
import http.server
import urllib.request
import urllib.parse
import urllib.error
import resource
from html.parser import HTMLParser
from pathlib import Path
from datetime import datetime, timezone
from io import BytesIO
from configparser import ConfigParser

# ===================================================
# CONFIG
# ===================================================

VERSION = "2.0.0"
PRODUCT_NAME = "ZionBrowser"
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0"

ZION_DIR = Path.home() / ".zion"
COOKIE_FILE = ZION_DIR / "cookies.txt"
SESSION_DIR = ZION_DIR / "sessions"
CACHE_DIR = ZION_DIR / "cache"
HISTORY_FILE = ZION_DIR / "history.jsonl"
BOOKMARKS_FILE = ZION_DIR / "bookmarks.json"
CONFIG_FILE = ZION_DIR / "config.json"
PIPES_DIR = ZION_DIR / "pipes"

MAX_REDIRECTS = 10
TIMEOUT = 15
MAX_RESPONSE = 2 * 1024 * 1024  # 2MB max per response (RAM budget)
MAX_CACHE_SIZE = 10 * 1024 * 1024  # 10MB total cache
CACHE_TTL = 300  # 5 min cache

# Ensure dirs exist
for d in [ZION_DIR, SESSION_DIR, CACHE_DIR, PIPES_DIR]:
    d.mkdir(parents=True, exist_ok=True)


def mem_mb():
    """Current RSS memory in MB."""
    try:
        ru = resource.getrusage(resource.RUSAGE_SELF)
        return ru.ru_maxrss / 1024  # Linux returns KB
    except Exception:
        return 0


# ===================================================
# HTML PARSER — Ultra-light, streaming
# ===================================================

class ZionHTMLParser(HTMLParser):
    """Lightweight HTML parser — text, links, forms, meta."""

    def __init__(self):
        super().__init__()
        self.text_parts = []
        self.links = []
        self.forms = []
        self.current_form = None
        self.current_tag = None
        self.skip_tags = {"script", "style", "noscript", "svg", "path"}
        self.in_skip = 0
        self.title = ""
        self.in_title = False
        self.meta = {}
        self.headings = []
        self._link_stack = []
        # JS redirect detection
        self.js_redirects = []
        self.in_script = False
        self.script_buf = ""

    def handle_starttag(self, tag, attrs):
        self.current_tag = tag
        a = dict(attrs)

        if tag == "script":
            self.in_script = True
            self.script_buf = ""
            self.in_skip += 1
            return

        if tag in self.skip_tags:
            self.in_skip += 1
            return

        if tag == "title":
            self.in_title = True

        if tag == "meta":
            name = a.get("name", a.get("property", ""))
            content = a.get("content", "")
            if name and content:
                self.meta[name] = content
            # meta refresh redirect
            equiv = a.get("http-equiv", "").lower()
            if equiv == "refresh" and content:
                m = re.search(r'url\s*=\s*["\']?([^"\';\s]+)', content, re.I)
                if m:
                    self.js_redirects.append(m.group(1))

        if tag == "a":
            href = a.get("href", "")
            if href:
                self._link_stack.append({"href": href, "text": ""})

        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self.headings.append({"level": tag, "text": ""})

        if tag == "form":
            self.current_form = {
                "action": a.get("action", ""),
                "method": a.get("method", "GET").upper(),
                "id": a.get("id", ""),
                "name": a.get("name", ""),
                "enctype": a.get("enctype", ""),
                "inputs": []
            }

        if tag in ("input", "textarea", "select"):
            inp = {
                "tag": tag,
                "type": a.get("type", "text"),
                "name": a.get("name", ""),
                "value": a.get("value", ""),
                "id": a.get("id", ""),
                "placeholder": a.get("placeholder", ""),
                "required": "required" in a or a.get("required") == "true",
            }
            if self.current_form is not None:
                self.current_form["inputs"].append(inp)

        if tag == "option" and self.current_form:
            # Track select options
            pass

    def handle_endtag(self, tag):
        if tag == "script":
            self.in_script = False
            # Scan for JS redirects
            if self.script_buf:
                for pattern in [
                    r'window\.location\s*=\s*["\']([^"\']+)',
                    r'location\.href\s*=\s*["\']([^"\']+)',
                    r'location\.replace\(["\']([^"\']+)',
                    r'window\.location\.assign\(["\']([^"\']+)',
                ]:
                    m = re.search(pattern, self.script_buf)
                    if m:
                        self.js_redirects.append(m.group(1))
            self.in_skip = max(0, self.in_skip - 1)
            return

        if tag in self.skip_tags:
            self.in_skip = max(0, self.in_skip - 1)
            return

        if tag == "title":
            self.in_title = False

        if tag == "a" and self._link_stack:
            link = self._link_stack.pop()
            self.links.append(link)

        if tag == "form" and self.current_form is not None:
            self.forms.append(self.current_form)
            self.current_form = None

    def handle_data(self, data):
        if self.in_script:
            self.script_buf += data
            return

        if self.in_skip > 0:
            return

        text = data.strip()
        if not text:
            return

        if self.in_title:
            self.title += text

        if self.headings and self.current_tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self.headings[-1]["text"] += text

        if self._link_stack:
            self._link_stack[-1]["text"] += text

        self.text_parts.append(text)

    def get_text(self, max_lines=200):
        full = "\n".join(self.text_parts)
        lines = [l.strip() for l in full.split("\n") if l.strip()]
        deduped = []
        prev = ""
        for line in lines[:max_lines]:
            if line != prev:
                deduped.append(line)
                prev = line
        return "\n".join(deduped)

    def get_links(self, base_url=""):
        resolved = []
        seen = set()
        for link in self.links:
            href = link["href"]
            if href.startswith(("javascript:", "#", "mailto:", "tel:")):
                continue
            if not href.startswith("http"):
                href = urllib.parse.urljoin(base_url, href)
            if href not in seen:
                seen.add(href)
                resolved.append({"url": href, "text": link["text"].strip()})
        return resolved

    def get_forms(self):
        return self.forms


# ===================================================
# FIREFOX COOKIE IMPORTER
# ===================================================

class FirefoxCookieImporter:
    """Import cookies from Firefox SQLite database."""

    @staticmethod
    def find_profiles():
        """Find Firefox profile directories."""
        profiles = []
        ff_dirs = [
            Path.home() / ".mozilla" / "firefox",
            Path.home() / "snap" / "firefox" / "common" / ".mozilla" / "firefox",
        ]
        for ff_dir in ff_dirs:
            ini = ff_dir / "profiles.ini"
            if ini.exists():
                cp = ConfigParser()
                cp.read(str(ini))
                for section in cp.sections():
                    if cp.has_option(section, "Path"):
                        path = cp.get(section, "Path")
                        is_rel = cp.getboolean(section, "IsRelative", fallback=True)
                        if is_rel:
                            full = ff_dir / path
                        else:
                            full = Path(path)
                        if full.exists():
                            name = cp.get(section, "Name", fallback=path)
                            profiles.append({"name": name, "path": full})
        # Also check for direct cookie files
        for ff_dir in ff_dirs:
            if ff_dir.exists():
                for p in ff_dir.iterdir():
                    if p.is_dir() and (p / "cookies.sqlite").exists():
                        if not any(pr["path"] == p for pr in profiles):
                            profiles.append({"name": p.name, "path": p})
        return profiles

    @staticmethod
    def import_cookies(profile_path, domain_filter=None):
        """Import cookies from Firefox SQLite database.

        Args:
            profile_path: Path to Firefox profile directory
            domain_filter: Optional domain to filter (e.g. 'hackenproof.com')

        Returns:
            List of cookie dicts
        """
        db_path = Path(profile_path) / "cookies.sqlite"
        if not db_path.exists():
            return []

        # Copy DB to avoid locking issues with running Firefox
        import shutil
        tmp_db = CACHE_DIR / "ff_cookies_tmp.sqlite"
        shutil.copy2(str(db_path), str(tmp_db))

        cookies = []
        try:
            conn = sqlite3.connect(str(tmp_db))
            conn.row_factory = sqlite3.Row
            query = "SELECT host, name, value, path, expiry, isSecure, isHttpOnly FROM moz_cookies"
            if domain_filter:
                query += f" WHERE host LIKE '%{domain_filter}%'"
            for row in conn.execute(query):
                cookies.append({
                    "domain": row["host"],
                    "name": row["name"],
                    "value": row["value"],
                    "path": row["path"],
                    "expires": row["expiry"],
                    "secure": bool(row["isSecure"]),
                    "httponly": bool(row["isHttpOnly"]),
                })
            conn.close()
        except Exception as e:
            print(f"  Cookie import error: {e}")
        finally:
            tmp_db.unlink(missing_ok=True)

        return cookies

    @staticmethod
    def cookies_to_jar(cookies, cookie_jar):
        """Add imported cookies to our cookie jar."""
        count = 0
        for c in cookies:
            cookie = http.cookiejar.Cookie(
                version=0,
                name=c["name"],
                value=c["value"],
                port=None,
                port_specified=False,
                domain=c["domain"],
                domain_specified=True,
                domain_initial_dot=c["domain"].startswith("."),
                path=c["path"],
                path_specified=True,
                secure=c["secure"],
                expires=c["expires"] if c["expires"] else None,
                discard=c["expires"] == 0,
                comment=None,
                comment_url=None,
                rest={"HttpOnly": str(c["httponly"])},
            )
            cookie_jar.set_cookie(cookie)
            count += 1
        return count


# ===================================================
# RESPONSE CACHE — Avoid re-fetching
# ===================================================

class ResponseCache:
    """Simple file-based response cache."""

    def __init__(self):
        self._cleanup_if_needed()

    def _key(self, url):
        return hashlib.md5(url.encode()).hexdigest()

    def get(self, url):
        key = self._key(url)
        cache_file = CACHE_DIR / f"{key}.json"
        if cache_file.exists():
            try:
                data = json.loads(cache_file.read_text())
                age = time.time() - data.get("ts", 0)
                if age < CACHE_TTL:
                    return data.get("status"), data.get("headers", {}), data.get("body", ""), data.get("url", url)
            except Exception:
                pass
        return None

    def put(self, url, status, headers, body):
        key = self._key(url)
        cache_file = CACHE_DIR / f"{key}.json"
        # Only cache successful GET responses under size limit
        if status == 200 and len(body) < 500_000:
            data = {"url": url, "status": status, "headers": dict(headers), "body": body, "ts": time.time()}
            try:
                cache_file.write_text(json.dumps(data))
            except Exception:
                pass

    def _cleanup_if_needed(self):
        """Remove old cache files if total exceeds limit."""
        try:
            total = sum(f.stat().st_size for f in CACHE_DIR.glob("*.json"))
            if total > MAX_CACHE_SIZE:
                files = sorted(CACHE_DIR.glob("*.json"), key=lambda f: f.stat().st_mtime)
                while total > MAX_CACHE_SIZE // 2 and files:
                    f = files.pop(0)
                    total -= f.stat().st_size
                    f.unlink(missing_ok=True)
        except Exception:
            pass

    def clear(self):
        for f in CACHE_DIR.glob("*.json"):
            f.unlink(missing_ok=True)


# ===================================================
# HTTP ENGINE — Cookie-aware, streaming, cached
# ===================================================

class ZionHTTP:
    """Ultra-lightweight HTTP client with cookie persistence and caching."""

    def __init__(self, session_name="default"):
        self.session_name = session_name
        self.cookie_file = SESSION_DIR / f"{session_name}_cookies.txt"
        self.session_file = SESSION_DIR / f"{session_name}_session.json"

        # Also use global cookie file for backwards compat
        if not self.cookie_file.exists() and COOKIE_FILE.exists():
            import shutil
            shutil.copy2(str(COOKIE_FILE), str(self.cookie_file))

        self.cookie_jar = http.cookiejar.MozillaCookieJar(str(self.cookie_file))
        if self.cookie_file.exists():
            try:
                self.cookie_jar.load(ignore_discard=True, ignore_expires=True)
            except Exception:
                pass

        self.ssl_ctx = ssl.create_default_context()
        self.ssl_ctx.minimum_version = ssl.TLSVersion.TLSv1_2

        cookie_proc = urllib.request.HTTPCookieProcessor(self.cookie_jar)
        https_handler = urllib.request.HTTPSHandler(context=self.ssl_ctx)
        self.opener = urllib.request.build_opener(cookie_proc, https_handler)

        self.headers = {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,pt-BR;q=0.8",
            "Accept-Encoding": "identity",
            "Connection": "keep-alive",
            "DNT": "1",
            "Upgrade-Insecure-Requests": "1",
        }

        self.session = self._load_session()
        self.cache = ResponseCache()

    def _load_session(self):
        if self.session_file.exists():
            try:
                return json.loads(self.session_file.read_text())
            except Exception:
                pass
        return {"csrf": {}, "auth": {}, "last_url": "", "referer": ""}

    def _save(self):
        try:
            self.cookie_jar.save(ignore_discard=True, ignore_expires=True)
        except Exception:
            pass
        try:
            self.session_file.write_text(json.dumps(self.session, indent=2, default=str))
        except Exception:
            pass

    def _decompress(self, data, encoding):
        if encoding == "gzip":
            try:
                return gzip.decompress(data)
            except Exception:
                pass
        elif encoding == "deflate":
            try:
                return zlib.decompress(data, -zlib.MAX_WBITS)
            except Exception:
                try:
                    return zlib.decompress(data)
                except Exception:
                    pass
        elif encoding == "br":
            # Brotli: try Python brotli module, fallback to identity re-request
            try:
                import brotli
                return brotli.decompress(data)
            except ImportError:
                pass  # brotli not installed, data returned as-is
            except Exception:
                pass
        # For any unknown encoding, check if data looks like compressed binary
        if encoding and encoding not in ("gzip", "deflate", "br", "identity"):
            pass  # Unknown encoding, return raw
        return data

    # Retry config: status codes that should trigger retry with backoff
    RETRY_CODES = {429, 500, 502, 503, 504}
    MAX_RETRIES = 3
    RETRY_BACKOFF = [1, 2, 4]  # seconds

    def request(self, url, method="GET", data=None, headers=None, json_data=None, use_cache=True):
        """Make HTTP request with retry + backoff. Returns (status, headers, body, final_url)."""
        # Check cache for GET requests
        if method == "GET" and use_cache:
            cached = self.cache.get(url)
            if cached:
                return cached

        h = dict(self.headers)
        if self.session.get("referer"):
            h["Referer"] = self.session["referer"]
        if headers:
            h.update(headers)

        if json_data is not None:
            data = json.dumps(json_data).encode("utf-8")
            h["Content-Type"] = "application/json"
        elif data and isinstance(data, dict):
            data = urllib.parse.urlencode(data).encode("utf-8")
            if method == "POST":
                h["Content-Type"] = "application/x-www-form-urlencoded"

        last_result = None
        for attempt in range(self.MAX_RETRIES):
            result = self._do_request(url, method, data, h)
            status = result[0]

            # Success or non-retryable error
            if status not in self.RETRY_CODES:
                return result

            last_result = result
            # Retry with backoff
            if attempt < self.MAX_RETRIES - 1:
                delay = self.RETRY_BACKOFF[min(attempt, len(self.RETRY_BACKOFF) - 1)]
                # Respect Retry-After header for 429
                if status == 429:
                    retry_after = result[1].get("Retry-After", "")
                    if retry_after.isdigit():
                        delay = min(int(retry_after), 10)
                time.sleep(delay)

        return last_result  # Return last attempt result

    def _do_request(self, url, method, data, h):
        """Single HTTP request attempt. Returns (status, headers, body, final_url)."""
        req = urllib.request.Request(url, data=data, headers=h, method=method)

        try:
            resp = self.opener.open(req, timeout=TIMEOUT)
            status = resp.getcode()
            rh = dict(resp.headers)
            final_url = resp.geturl()

            body_raw = resp.read(MAX_RESPONSE)
            enc = rh.get("Content-Encoding", "").lower()
            if enc:
                body_raw = self._decompress(body_raw, enc)

            charset = "utf-8"
            ct = rh.get("Content-Type", "")
            if "charset=" in ct:
                charset = ct.split("charset=")[-1].split(";")[0].strip()
            body = body_raw.decode(charset, errors="replace")

            self.session["last_url"] = final_url
            self.session["referer"] = final_url
            self._save()

            # Log to history
            self._log(url, method, status, final_url)

            # Cache GET 200
            if method == "GET" and status == 200:
                self.cache.put(url, status, rh, body)

            return status, rh, body, final_url

        except urllib.error.HTTPError as e:
            body = ""
            try:
                raw = e.read(MAX_RESPONSE)
                enc = e.headers.get("Content-Encoding", "").lower()
                if enc:
                    raw = self._decompress(raw, enc)
                body = raw.decode("utf-8", errors="replace")
            except Exception:
                pass
            self._save()
            self._log(url, method, e.code, url)
            return e.code, dict(e.headers), body, url

        except urllib.error.URLError as e:
            return 0, {}, f"Connection error: {e.reason}", url

        except Exception as e:
            return 0, {}, f"Error: {e}", url

    def get(self, url, **kw):
        return self.request(url, "GET", **kw)

    def post(self, url, data=None, **kw):
        return self.request(url, "POST", data=data, **kw)

    def download(self, url, filepath):
        """Stream download to disk — minimal RAM usage."""
        req = urllib.request.Request(url, headers=self.headers)
        try:
            resp = self.opener.open(req, timeout=60)
            total = 0
            with open(filepath, "wb") as f:
                while True:
                    chunk = resp.read(8192)
                    if not chunk:
                        break
                    f.write(chunk)
                    total += len(chunk)
            return True, filepath, total
        except Exception as e:
            return False, str(e), 0

    def _log(self, url, method, status, final_url):
        try:
            with open(HISTORY_FILE, "a") as f:
                entry = {"url": url, "method": method, "status": status,
                         "final": final_url, "ts": datetime.now().isoformat()}
                f.write(json.dumps(entry) + "\n")
        except Exception:
            pass


# ===================================================
# PAGE — Parsed result
# ===================================================

class ZionPage:
    """Parsed web page with lazy evaluation."""

    def __init__(self, status, headers, body, url):
        self.status = status
        self.headers = headers
        self.body = body
        self.url = url
        self._parser = None
        self._parsed = False

    def _ensure_parsed(self):
        if self._parsed:
            return
        self._parser = ZionHTMLParser()
        ct = self.headers.get("Content-Type", "")
        if "html" in ct or "xml" in ct or (not ct and "<html" in self.body[:500].lower()):
            try:
                self._parser.feed(self.body)
            except Exception:
                pass
        self._parsed = True

    @property
    def title(self):
        self._ensure_parsed()
        return self._parser.title or "(no title)"

    @property
    def text(self):
        self._ensure_parsed()
        t = self._parser.get_text()
        # Fallback: for JSON/plain text responses, return body directly
        if not t.strip() and self.body:
            ct = self.headers.get("Content-Type", "")
            if "json" in ct or "text/plain" in ct or "html" not in ct:
                return self.body.strip()
        return t

    @property
    def links(self):
        self._ensure_parsed()
        return self._parser.get_links(self.url)

    @property
    def forms(self):
        self._ensure_parsed()
        return self._parser.get_forms()

    @property
    def meta(self):
        self._ensure_parsed()
        return self._parser.meta

    @property
    def headings(self):
        self._ensure_parsed()
        return self._parser.headings

    @property
    def js_redirects(self):
        self._ensure_parsed()
        return self._parser.js_redirects

    @property
    def is_cloudflare(self):
        return (self.status == 403 and
                ("cloudflare" in self.body[:2000].lower() or
                 "cf-ray" in str(self.headers).lower()))

    @property
    def is_js_only(self):
        """Detect pages that require JavaScript to render content."""
        if not self.body:
            return False
        # Pages with many links or working forms are server-rendered
        if len(self.links) > 10 or len(self.forms) > 2:
            return False
        text = self.text.strip()
        text_lines = [l.strip() for l in text.split("\n") if l.strip()]
        # Page has HTML but very little visible text = JS-rendered
        has_html = "<html" in self.body[:500].lower()
        has_scripts = self.body.lower().count("<script") > 2
        few_text = len(text_lines) < 5
        has_noscript = "<noscript" in self.body.lower()
        has_react_root = ('id="root"' in self.body or 'id="app"' in self.body or
                          'id="__next"' in self.body or 'ng-app' in self.body)
        # Score-based detection — threshold 4 to reduce false positives
        score = 0
        if has_html and few_text:
            score += 2
        if has_scripts:
            score += 1
        if has_noscript:
            score += 1
        if has_react_root:
            score += 2
        if len(self.forms) == 0 and "form" in self.body.lower():
            score += 1
        return score >= 4

    @property
    def is_json(self):
        ct = self.headers.get("Content-Type", "")
        return "json" in ct

    def json(self):
        try:
            return json.loads(self.body)
        except Exception:
            return None

    def find_links(self, pattern):
        c = re.compile(pattern, re.I)
        return [l for l in self.links if c.search(l["url"]) or c.search(l.get("text", ""))]

    def find_form(self, pattern=None, index=0):
        """Find form by action/id pattern or index."""
        if pattern:
            for f in self.forms:
                if (re.search(pattern, f["action"], re.I) or
                        re.search(pattern, f.get("id", ""), re.I) or
                        re.search(pattern, f.get("name", ""), re.I)):
                    return f
        if self.forms and index < len(self.forms):
            return self.forms[index]
        return None

    def csrf_token(self):
        """Extract CSRF token from forms or meta tags."""
        # Check meta tags
        for key in ["csrf-token", "csrf_token", "_token", "csrfmiddlewaretoken"]:
            if key in self.meta:
                return key, self.meta[key]
        # Check hidden form inputs
        for form in self.forms:
            for inp in form["inputs"]:
                if inp["type"] == "hidden" and any(
                    t in inp["name"].lower() for t in ["csrf", "token", "_token", "authenticity"]
                ):
                    return inp["name"], inp["value"]
        return None, None

    def summary(self, max_text=50):
        """Compact page summary."""
        lines = [
            f"  URL: {self.url}",
            f"  Status: {self.status}",
            f"  Title: {self.title}",
            f"  Links: {len(self.links)} | Forms: {len(self.forms)}",
        ]

        if self.is_cloudflare:
            lines.append("  [!] CLOUDFLARE PROTECTED — JS challenge required")

        if self.is_js_only:
            lines.append("  [!] JS-ONLY PAGE — Use 'zion-cdp chrome <url>' for full rendering")

        if self.js_redirects:
            lines.append(f"  [>] JS Redirect: {self.js_redirects[0]}")

        csrf_name, csrf_val = self.csrf_token()
        if csrf_name:
            lines.append(f"  [CSRF] {csrf_name}={csrf_val[:30]}...")

        if self.headings:
            lines.append("")
            for h in self.headings[:8]:
                indent = "  " * (int(h["level"][1]) - 1)
                lines.append(f"  {indent}{h['level']}: {h['text'][:70]}")

        lines.append("")
        text = self.text
        for line in text.split("\n")[:max_text]:
            lines.append(f"  {line[:120]}")

        return "\n".join(lines)


# ===================================================
# BROWSER — Main interface
# ===================================================

class ZionBrowser:
    """Ultra-lightweight CLI browser — ~3-5MB RAM."""

    def __init__(self, session_name="default"):
        self.http = ZionHTTP(session_name)
        self.page = None
        self.session_name = session_name

    def go(self, url):
        """Navigate to URL with smart error recovery."""
        if not url.startswith("http"):
            url = "https://" + url
        status, headers, body, final_url = self.http.get(url, use_cache=False)
        self.page = ZionPage(status, headers, body, final_url)

        # Follow JS redirects if page is a redirect-only page
        if self.page.js_redirects and len(self.page.text) < 100:
            redir = self.page.js_redirects[0]
            if not redir.startswith("http"):
                redir = urllib.parse.urljoin(final_url, redir)
            status, headers, body, final_url = self.http.get(redir, use_cache=False)
            self.page = ZionPage(status, headers, body, final_url)

        # Record navigation intelligence
        self._record_navigation(url, self.page)

        return self.page

    def _record_navigation(self, url, page):
        """Record navigation results for learning — errors, patterns, solutions."""
        domain = urllib.parse.urlparse(url).netloc
        # Track error patterns
        if not hasattr(self, '_error_counts'):
            self._error_counts = {}
        if not hasattr(self, '_domain_notes'):
            self._domain_notes = {}

        if page.status == 403 and page.is_cloudflare:
            count = self._error_counts.get(domain, 0) + 1
            self._error_counts[domain] = count
            self._domain_notes[domain] = "cloudflare_protected"
        elif page.status >= 400:
            self._error_counts[domain] = self._error_counts.get(domain, 0) + 1
        elif page.is_js_only:
            self._domain_notes[domain] = "js_only"

    def get_navigation_hint(self, url):
        """Get hint for how to navigate a URL based on learned patterns."""
        domain = urllib.parse.urlparse(url).netloc
        if not hasattr(self, '_domain_notes'):
            return None
        note = self._domain_notes.get(domain)
        if note == "cloudflare_protected":
            return "CLOUDFLARE: Use 'zion-cdp chrome' or import Firefox cookies"
        elif note == "js_only":
            return "JS-ONLY: Use 'zion-cdp chrome' for full page rendering"
        return None

    def request(self, url, method="GET", data=None, headers=None, json_data=None):
        """Direct HTTP request — returns ZionPage."""
        status, h, body, final = self.http.request(url, method=method, data=data,
                                                    headers=headers, json_data=json_data,
                                                    use_cache=False)
        self.page = ZionPage(status, h, body, final)
        self._record_navigation(url, self.page)
        return self.page

    def post(self, url, data, headers=None):
        """POST form data."""
        status, h, body, final = self.http.post(url, data=data, headers=headers)
        self.page = ZionPage(status, h, body, final)
        return self.page

    def submit_form(self, form_data, form_index=0, action_override=None):
        """Submit a form on the current page."""
        if not self.page:
            return None
        form = self.page.find_form(index=form_index)
        if not form:
            return None

        # Build full data with hidden fields
        data = {}
        for inp in form["inputs"]:
            if inp["name"]:
                if inp["type"] == "hidden":
                    data[inp["name"]] = inp["value"]
                elif inp["value"]:
                    data[inp["name"]] = inp["value"]
        data.update(form_data)

        action = action_override or form["action"]
        if not action:
            action = self.page.url
        elif not action.startswith("http"):
            action = urllib.parse.urljoin(self.page.url, action)

        method = form["method"]
        if method == "POST":
            return self.post(action, data)
        else:
            qs = urllib.parse.urlencode(data)
            return self.go(f"{action}?{qs}")

    def api(self, url, method="GET", json_data=None, headers=None):
        """API call returning JSON."""
        h = {"Accept": "application/json"}
        if headers:
            h.update(headers)
        if method == "POST":
            status, rh, body, _ = self.http.request(url, "POST", json_data=json_data, headers=h)
        else:
            status, rh, body, _ = self.http.get(url, headers=h)
        try:
            return status, json.loads(body)
        except Exception:
            return status, {"raw": body[:2000]}

    def login(self, url, username, password, user_field=None, pass_field=None):
        """Smart login — detects form fields automatically."""
        page = self.go(url)
        form = page.find_form("login|signin|auth|session|log_in")
        if not form:
            form = page.find_form()
        if not form:
            return False, "No form found"

        data = {}
        user_set = False
        pass_set = False

        for inp in form["inputs"]:
            name = inp["name"]
            if not name:
                continue

            nl = name.lower()
            tl = inp["type"].lower()
            pl = inp.get("placeholder", "").lower()

            # Hidden fields (CSRF etc)
            if tl == "hidden":
                data[name] = inp["value"]
                continue

            # Username/email field
            if not user_set and (
                tl == "email" or
                any(k in nl for k in ["user", "email", "login", "handle", "account"]) or
                any(k in pl for k in ["email", "user"])
            ):
                data[name] = username
                user_set = True
                continue

            # Password field
            if not pass_set and (
                tl == "password" or
                any(k in nl for k in ["pass", "pwd", "secret"])
            ):
                data[name] = password
                pass_set = True
                continue

            # Keep default values
            if inp["value"]:
                data[name] = inp["value"]

        # Override with explicit field names
        if user_field:
            data[user_field] = username
        if pass_field:
            data[pass_field] = password

        action = form["action"]
        if not action:
            action = url
        elif not action.startswith("http"):
            action = urllib.parse.urljoin(url, action)

        result = self.post(action, data)
        success = result.status in (200, 301, 302, 303)
        return success, f"Status {result.status} | {result.title}"

    def search(self, query):
        """Search via DuckDuckGo Lite (no JS required)."""
        url = "https://lite.duckduckgo.com/lite/"
        data = {"q": query}
        status, headers, body, final = self.http.post(url, data=data)
        page = ZionPage(status, headers, body, final)
        results = []
        for link in page.links:
            u = link["url"]
            if u.startswith("https://lite.duckduckgo.com") or "duckduckgo.com" in u:
                continue
            if u.startswith("http"):
                results.append({"title": link["text"][:80], "url": u})
        return results[:15]

    def download(self, url, filepath):
        return self.http.download(url, filepath)

    def import_firefox_cookies(self, domain=None, profile_idx=0):
        """Import cookies from Firefox."""
        profiles = FirefoxCookieImporter.find_profiles()
        if not profiles:
            return 0, "No Firefox profiles found"
        if profile_idx >= len(profiles):
            profile_idx = 0
        profile = profiles[profile_idx]
        cookies = FirefoxCookieImporter.import_cookies(profile["path"], domain)
        count = FirefoxCookieImporter.cookies_to_jar(cookies, self.http.cookie_jar)
        self.http._save()
        return count, f"Imported {count} cookies from {profile['name']}"


# ===================================================
# TASK PIPELINE — Multi-step web automation
# ===================================================

class ZionPipeline:
    """Execute multi-step web tasks."""

    def __init__(self, browser=None):
        self.browser = browser or ZionBrowser()
        self.results = []
        self.variables = {}  # Store values between steps

    def run(self, pipeline):
        """Execute pipeline from dict or file path."""
        if isinstance(pipeline, (str, Path)):
            pipeline = json.loads(Path(pipeline).read_text())

        name = pipeline.get("name", "unnamed")
        print(f"  Pipeline: {name}")
        print(f"  Steps: {len(pipeline.get('steps', []))}")
        print()

        for i, step in enumerate(pipeline.get("steps", [])):
            action = step.get("action", "get")
            url = self._interpolate(step.get("url", ""))
            desc = step.get("desc", step.get("description", f"Step {i+1}"))
            data = step.get("data", {})
            wait = step.get("wait", 0)
            save_as = step.get("save_as", "")
            expect = step.get("expect", {})

            print(f"  [{i+1}] {desc}")

            result = {"step": i+1, "action": action, "desc": desc}

            try:
                if action == "get":
                    page = self.browser.go(url)
                    result["status"] = page.status
                    result["title"] = page.title
                    result["url"] = page.url
                    if page.is_cloudflare:
                        result["blocked"] = "cloudflare"
                        print(f"      [!] Cloudflare blocked")

                elif action == "post":
                    data = {k: self._interpolate(str(v)) for k, v in data.items()}
                    page = self.browser.post(url, data)
                    result["status"] = page.status
                    result["title"] = page.title

                elif action == "login":
                    ok, msg = self.browser.login(
                        url,
                        self._interpolate(data.get("username", "")),
                        self._interpolate(data.get("password", "")),
                        data.get("user_field"),
                        data.get("pass_field"),
                    )
                    result["success"] = ok
                    result["message"] = msg

                elif action == "api":
                    method = data.get("method", "GET")
                    status, resp = self.browser.api(url, method, data.get("json"))
                    result["status"] = status
                    result["response"] = resp

                elif action == "search":
                    results = self.browser.search(data.get("query", url))
                    result["results"] = results
                    print(f"      Found {len(results)} results")

                elif action == "download":
                    ok, path, size = self.browser.download(url, data.get("file", "/tmp/zion_dl"))
                    result["success"] = ok
                    result["path"] = path
                    result["size"] = size

                elif action == "extract_links":
                    if self.browser.page:
                        pattern = data.get("pattern", ".*")
                        links = self.browser.page.find_links(pattern)
                        result["links"] = links[:20]
                        self.variables[save_as or "links"] = links

                elif action == "extract_forms":
                    if self.browser.page:
                        result["forms"] = self.browser.page.forms

                elif action == "submit_form":
                    form_data = {k: self._interpolate(str(v)) for k, v in data.items()}
                    idx = step.get("form_index", 0)
                    page = self.browser.submit_form(form_data, idx)
                    if page:
                        result["status"] = page.status
                        result["title"] = page.title
                    else:
                        result["error"] = "No form found"

                elif action == "set_var":
                    for k, v in data.items():
                        self.variables[k] = self._interpolate(str(v))
                    result["variables"] = dict(self.variables)

                elif action == "print":
                    msg = self._interpolate(data.get("message", ""))
                    print(f"      {msg}")
                    result["message"] = msg

                elif action == "cookies_import":
                    count, msg = self.browser.import_firefox_cookies(data.get("domain"))
                    result["imported"] = count
                    result["message"] = msg

                # Save result variable
                if save_as and self.browser.page:
                    if "csrf" in save_as.lower():
                        _, val = self.browser.page.csrf_token()
                        self.variables[save_as] = val or ""
                    elif save_as == "url":
                        self.variables[save_as] = self.browser.page.url
                    elif save_as == "title":
                        self.variables[save_as] = self.browser.page.title

                # Check expectations
                if expect:
                    exp_status = expect.get("status")
                    if exp_status and result.get("status") != exp_status:
                        result["expect_failed"] = True
                        print(f"      [FAIL] Expected status {exp_status}, got {result.get('status')}")

                status_str = result.get("status", result.get("success", "ok"))
                print(f"      -> {status_str}")

            except Exception as e:
                result["error"] = str(e)
                print(f"      [ERROR] {e}")

            self.results.append(result)

            if wait > 0:
                time.sleep(wait)

        return self.results

    def _interpolate(self, text):
        """Replace {{var}} with stored values."""
        for key, val in self.variables.items():
            text = text.replace(f"{{{{{key}}}}}", str(val))
        return text


# ===================================================
# HTTP API SERVER — For AI agent integration
# ===================================================

class ZionAPIHandler(http.server.BaseHTTPRequestHandler):
    """Minimal HTTP API for AI agents to control ZionBrowser."""

    browser = None

    def log_message(self, fmt, *args):
        pass  # Suppress logs

    def _respond(self, status, data):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data, default=str).encode())

    def do_GET(self):
        parts = urllib.parse.urlparse(self.path)
        qs = dict(urllib.parse.parse_qsl(parts.query))

        if parts.path == "/go":
            url = qs.get("url", "")
            if url:
                page = self.browser.go(url)
                self._respond(200, {
                    "status": page.status, "title": page.title,
                    "url": page.url, "links": len(page.links),
                    "forms": len(page.forms), "text": page.text[:1000]
                })
            else:
                self._respond(400, {"error": "url required"})

        elif parts.path == "/links":
            if self.browser.page:
                self._respond(200, {"links": self.browser.page.links[:50]})
            else:
                self._respond(404, {"error": "no page"})

        elif parts.path == "/forms":
            if self.browser.page:
                self._respond(200, {"forms": self.browser.page.forms})
            else:
                self._respond(404, {"error": "no page"})

        elif parts.path == "/text":
            if self.browser.page:
                self._respond(200, {"text": self.browser.page.text[:3000]})
            else:
                self._respond(404, {"error": "no page"})

        elif parts.path == "/search":
            query = qs.get("q", "")
            results = self.browser.search(query)
            self._respond(200, {"results": results})

        elif parts.path == "/mem":
            self._respond(200, {"rss_mb": round(mem_mb(), 1)})

        elif parts.path == "/health":
            self._respond(200, {"status": "ok", "version": VERSION})

        else:
            self._respond(404, {"error": "unknown endpoint"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode() if length else "{}"
        try:
            data = json.loads(body)
        except Exception:
            data = {}

        parts = urllib.parse.urlparse(self.path)

        if parts.path == "/post":
            url = data.get("url", "")
            form_data = data.get("data", {})
            page = self.browser.post(url, form_data)
            self._respond(200, {
                "status": page.status, "title": page.title, "url": page.url
            })

        elif parts.path == "/login":
            ok, msg = self.browser.login(
                data.get("url", ""),
                data.get("username", ""),
                data.get("password", ""),
                data.get("user_field"),
                data.get("pass_field"),
            )
            self._respond(200, {"success": ok, "message": msg})

        elif parts.path == "/pipe":
            pipe = ZionPipeline(self.browser)
            results = pipe.run(data)
            self._respond(200, {"results": results})

        else:
            self._respond(404, {"error": "unknown endpoint"})


# ===================================================
# CLI — Command line interface
# ===================================================

HELP = f"""
{PRODUCT_NAME} v{VERSION} — Ultra-Lightweight CLI Browser
Memory: ~3-5MB (vs Firefox ~500MB+)
Pure Python stdlib — ZERO external dependencies

NAVIGATION:
  zion get <url>                    Fetch & show page
  zion links <url>                  Extract links
  zion forms <url>                  Show forms
  zion submit <url> k=v&k=v        POST form data
  zion login <url> <user> <pass>   Login to site
  zion search <query>              Search via DuckDuckGo

API & DATA:
  zion api <url>                   Fetch JSON API
  zion download <url> [file]       Download file

COOKIES & SESSIONS:
  zion cookies list                List cookies
  zion cookies import [domain]     Import from Firefox
  zion cookies clear               Clear cookies
  zion session list                List sessions
  zion session switch <name>       Switch session
  zion session new <name>          Create new session

AUTOMATION:
  zion pipe <pipeline.json>        Execute task pipeline
  zion pipe create <name>          Create pipeline template

SERVER:
  zion serve [port]                HTTP API for AI agents (default: 7700)

UTILITY:
  zion mem                         Show memory usage
  zion cache clear                 Clear response cache
  zion history [n]                 Show recent history
  zion i                           Interactive mode

Product of Padrao Bitcoin | $29.99
standardbitcoin.io@gmail.com
"""


def cmd_get(browser, args):
    if not args:
        print("Usage: zion get <url>")
        return
    page = browser.go(args[0])
    print(page.summary())


def cmd_links(browser, args):
    if not args:
        print("Usage: zion links <url>")
        return
    page = browser.go(args[0])
    for i, l in enumerate(page.links):
        print(f"  [{i:3d}] {l['text'][:40]:40s} {l['url'][:90]}")


def cmd_forms(browser, args):
    if not args:
        print("Usage: zion forms <url>")
        return
    page = browser.go(args[0])
    if not page.forms:
        print("  No forms found.")
        return
    for i, f in enumerate(page.forms):
        print(f"\n  Form #{i}: action={f['action']} method={f['method']}")
        if f.get("id"):
            print(f"    id={f['id']}")
        for inp in f["inputs"]:
            req = " *REQUIRED" if inp.get("required") else ""
            ph = f" ({inp['placeholder']})" if inp.get("placeholder") else ""
            print(f"    [{inp['type']:10s}] {inp['name']:25s} = {inp['value'][:30]}{ph}{req}")


def cmd_submit(browser, args):
    if len(args) < 2:
        print("Usage: zion submit <url> key=val&key2=val2")
        return
    url = args[0]
    data = dict(p.split("=", 1) for p in args[1].split("&") if "=" in p)
    page = browser.post(url, data)
    print(page.summary(20))


def cmd_login(browser, args):
    if len(args) < 3:
        print("Usage: zion login <url> <user> <pass> [user_field] [pass_field]")
        return
    uf = args[3] if len(args) > 3 else None
    pf = args[4] if len(args) > 4 else None
    ok, msg = browser.login(args[0], args[1], args[2], uf, pf)
    status = "SUCCESS" if ok else "FAILED"
    print(f"  Login: {status} — {msg}")


def cmd_search(browser, args):
    if not args:
        print("Usage: zion search <query>")
        return
    query = " ".join(args)
    results = browser.search(query)
    if not results:
        print("  No results found.")
        return
    for i, r in enumerate(results):
        print(f"  [{i+1}] {r['title']}")
        print(f"      {r['url']}")


def cmd_api(browser, args):
    if not args:
        print("Usage: zion api <url>")
        return
    status, data = browser.api(args[0])
    print(f"  Status: {status}")
    print(json.dumps(data, indent=2)[:5000])


def cmd_download(browser, args):
    if not args:
        print("Usage: zion download <url> [filename]")
        return
    filepath = args[1] if len(args) > 1 else f"/tmp/zion_{int(time.time())}"
    ok, path, size = browser.download(args[0], filepath)
    if ok:
        print(f"  OK: {path} ({size} bytes)")
    else:
        print(f"  FAILED: {path}")


def cmd_cookies(browser, args):
    action = args[0] if args else "list"

    if action == "list":
        cookies = list(browser.http.cookie_jar)
        print(f"  Total: {len(cookies)} cookies")
        for c in cookies[:50]:
            print(f"  {c.domain:30s} {c.name:25s} = {c.value[:40]}")

    elif action == "import":
        domain = args[1] if len(args) > 1 else None
        profiles = FirefoxCookieImporter.find_profiles()
        if not profiles:
            print("  No Firefox profiles found.")
            return
        print(f"  Found {len(profiles)} Firefox profile(s):")
        for i, p in enumerate(profiles):
            print(f"    [{i}] {p['name']} — {p['path']}")
        idx = int(args[2]) if len(args) > 2 else 0
        count, msg = browser.import_firefox_cookies(domain, idx)
        print(f"  {msg}")

    elif action == "clear":
        browser.http.cookie_jar.clear()
        browser.http._save()
        print("  Cookies cleared.")

    elif action == "export":
        filepath = args[1] if len(args) > 1 else str(ZION_DIR / "cookies_export.json")
        cookies = []
        for c in browser.http.cookie_jar:
            cookies.append({"domain": c.domain, "name": c.name, "value": c.value,
                            "path": c.path, "secure": c.secure, "expires": c.expires})
        Path(filepath).write_text(json.dumps(cookies, indent=2))
        print(f"  Exported {len(cookies)} cookies to {filepath}")


def cmd_session(browser, args):
    action = args[0] if args else "list"

    if action == "list":
        sessions = list(SESSION_DIR.glob("*_cookies.txt"))
        print(f"  Sessions: {len(sessions)}")
        for s in sessions:
            name = s.stem.replace("_cookies", "")
            active = " [ACTIVE]" if name == browser.session_name else ""
            cookies = 0
            try:
                jar = http.cookiejar.MozillaCookieJar(str(s))
                jar.load(ignore_discard=True, ignore_expires=True)
                cookies = len(list(jar))
            except Exception:
                pass
            print(f"    {name:20s} {cookies} cookies{active}")

    elif action == "switch" and len(args) > 1:
        print(f"  Switching to session: {args[1]}")
        browser.__init__(args[1])
        print(f"  Active: {browser.session_name} ({len(list(browser.http.cookie_jar))} cookies)")

    elif action == "new" and len(args) > 1:
        name = args[1]
        print(f"  Creating session: {name}")
        browser.__init__(name)
        print(f"  Active: {name}")


def cmd_pipe(browser, args):
    if not args:
        print("Usage: zion pipe <pipeline.json> | zion pipe create <name>")
        return

    if args[0] == "create":
        name = args[1] if len(args) > 1 else "template"
        template = {
            "name": name,
            "description": "Pipeline template",
            "steps": [
                {"action": "get", "url": "https://example.com", "desc": "Load page"},
                {"action": "extract_forms", "desc": "Find forms"},
                {"action": "login", "url": "https://example.com/login",
                 "data": {"username": "user", "password": "pass"},
                 "desc": "Login"},
            ]
        }
        path = PIPES_DIR / f"{name}.json"
        path.write_text(json.dumps(template, indent=2))
        print(f"  Created: {path}")
        return

    if args[0] == "list":
        pipes = list(PIPES_DIR.glob("*.json"))
        print(f"  Pipelines: {len(pipes)}")
        for p in pipes:
            try:
                data = json.loads(p.read_text())
                steps = len(data.get("steps", []))
                print(f"    {p.stem:25s} {steps} steps — {data.get('description', '')[:50]}")
            except Exception:
                print(f"    {p.stem:25s} [invalid]")
        return

    # Execute pipeline
    path = args[0]
    if not Path(path).exists():
        # Check pipes dir
        pipe_path = PIPES_DIR / f"{path}.json"
        if pipe_path.exists():
            path = str(pipe_path)
        else:
            print(f"  Pipeline not found: {path}")
            return

    pipe = ZionPipeline(browser)
    results = pipe.run(path)
    print(f"\n  Pipeline complete: {len(results)} steps")
    for r in results:
        status = r.get("status", r.get("success", r.get("error", "?")))
        print(f"    [{r['step']}] {r['desc'][:50]:50s} -> {status}")


def cmd_serve(browser, args):
    port = int(args[0]) if args else 7700
    ZionAPIHandler.browser = browser
    server = http.server.HTTPServer(("127.0.0.1", port), ZionAPIHandler)
    print(f"  ZionBrowser API server on http://127.0.0.1:{port}")
    print(f"  Endpoints: /go?url=, /links, /forms, /text, /search?q=, /post, /login, /pipe")
    print(f"  Press Ctrl+C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Server stopped.")


def cmd_mem(browser, args):
    mb = mem_mb()
    cookies = len(list(browser.http.cookie_jar))
    cache_files = len(list(CACHE_DIR.glob("*.json")))
    cache_size = sum(f.stat().st_size for f in CACHE_DIR.glob("*.json")) / 1024
    print(f"  ZionBrowser v{VERSION}")
    print(f"  RSS Memory: {mb:.1f} MB")
    print(f"  Cookies: {cookies}")
    print(f"  Cache: {cache_files} files, {cache_size:.0f} KB")
    print(f"  Session: {browser.session_name}")


def cmd_history(browser, args):
    n = int(args[0]) if args else 20
    if not HISTORY_FILE.exists():
        print("  No history.")
        return
    lines = HISTORY_FILE.read_text().strip().split("\n")
    for line in lines[-n:]:
        try:
            h = json.loads(line)
            ts = h.get("ts", "")[:19]
            print(f"  [{h['status']:3d}] {h['method']:4s} {h['url'][:80]} ({ts})")
        except Exception:
            pass


def cmd_interactive(browser, args):
    print(f"  ZionBrowser v{VERSION} — Interactive Mode")
    print(f"  Session: {browser.session_name} | Cookies: {len(list(browser.http.cookie_jar))}")
    print(f"  Commands: go, links, forms, text, source, submit, login, search, api")
    print(f"            download, cookies, history, mem, pipe, help, quit")
    print()

    while True:
        try:
            prompt = f"zion:{browser.session_name}> "
            line = input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            break

        if not line:
            continue

        parts = line.split()
        cmd = parts[0].lower()
        cmd_args = parts[1:]

        try:
            if cmd in ("go", "get", "open", "nav"):
                if cmd_args:
                    page = browser.go(cmd_args[0])
                    print(page.summary(30))
                else:
                    print("  Usage: go <url>")

            elif cmd == "links":
                if cmd_args:
                    page = browser.go(cmd_args[0])
                else:
                    page = browser.page
                if page:
                    for i, l in enumerate(page.links[:50]):
                        print(f"  [{i:3d}] {l['text'][:35]:35s} {l['url'][:80]}")
                else:
                    print("  No page loaded.")

            elif cmd == "follow":
                if browser.page and cmd_args:
                    idx = int(cmd_args[0])
                    links = browser.page.links
                    if 0 <= idx < len(links):
                        page = browser.go(links[idx]["url"])
                        print(page.summary(20))
                    else:
                        print(f"  Invalid link index. Max: {len(links)-1}")

            elif cmd == "forms":
                if cmd_args:
                    page = browser.go(cmd_args[0])
                else:
                    page = browser.page
                if page and page.forms:
                    for i, f in enumerate(page.forms):
                        print(f"\n  Form #{i}: {f['method']} -> {f['action']}")
                        for inp in f["inputs"]:
                            req = " *" if inp.get("required") else ""
                            print(f"    [{inp['type']:10s}] {inp['name']:25s} = {inp['value'][:30]}{req}")
                else:
                    print("  No forms found.")

            elif cmd == "text":
                if browser.page:
                    print(browser.page.text[:3000])
                else:
                    print("  No page loaded.")

            elif cmd == "source":
                if browser.page:
                    print(browser.page.body[:5000])

            elif cmd == "title":
                if browser.page:
                    print(f"  {browser.page.title}")

            elif cmd == "url":
                if browser.page:
                    print(f"  {browser.page.url}")

            elif cmd == "submit":
                if len(cmd_args) >= 2:
                    form_idx = int(cmd_args[0])
                    data = dict(p.split("=", 1) for p in cmd_args[1].split("&") if "=" in p)
                    page = browser.submit_form(data, form_idx)
                    if page:
                        print(page.summary(20))
                    else:
                        print("  No form found.")
                else:
                    print("  Usage: submit <form#> key=val&key2=val2")

            elif cmd == "login":
                if len(cmd_args) >= 3:
                    ok, msg = browser.login(cmd_args[0], cmd_args[1], cmd_args[2])
                    print(f"  {'SUCCESS' if ok else 'FAILED'}: {msg}")
                else:
                    print("  Usage: login <url> <user> <pass>")

            elif cmd == "search":
                query = " ".join(cmd_args)
                results = browser.search(query)
                for i, r in enumerate(results):
                    print(f"  [{i+1}] {r['title']}")
                    print(f"      {r['url']}")

            elif cmd == "api":
                if cmd_args:
                    s, d = browser.api(cmd_args[0])
                    print(f"  Status: {s}")
                    print(json.dumps(d, indent=2)[:3000])

            elif cmd == "download":
                if len(cmd_args) >= 2:
                    ok, p, sz = browser.download(cmd_args[0], cmd_args[1])
                    print(f"  {'OK' if ok else 'FAIL'}: {p} ({sz} bytes)")

            elif cmd == "cookies":
                cmd_cookies(browser, cmd_args)

            elif cmd == "history":
                cmd_history(browser, cmd_args)

            elif cmd == "mem":
                cmd_mem(browser, [])

            elif cmd == "pipe":
                cmd_pipe(browser, cmd_args)

            elif cmd == "back":
                # Navigate to referer
                ref = browser.http.session.get("referer", "")
                if ref:
                    page = browser.go(ref)
                    print(page.summary(20))

            elif cmd in ("quit", "exit", "q"):
                break

            elif cmd == "help":
                print("  go <url>           Navigate to URL")
                print("  links [url]        Show links")
                print("  follow <n>         Follow link by index")
                print("  forms [url]        Show forms")
                print("  text               Show page text")
                print("  source             Show HTML source")
                print("  title              Show page title")
                print("  url                Show current URL")
                print("  submit # k=v&k=v   Submit form")
                print("  login url u p      Login")
                print("  search <query>     DuckDuckGo search")
                print("  api <url>          JSON API call")
                print("  download url file  Download file")
                print("  cookies [cmd]      Cookie management")
                print("  history [n]        Show history")
                print("  mem                Memory usage")
                print("  pipe <file>        Run pipeline")
                print("  back               Go to previous page")
                print("  quit               Exit")

            else:
                # Try as URL
                if "." in cmd:
                    page = browser.go(cmd)
                    print(page.summary(20))
                else:
                    print(f"  Unknown: {cmd}. Type 'help'.")

        except Exception as e:
            print(f"  Error: {e}")

    print("  Session saved.")


def main():
    if len(sys.argv) < 2:
        print(HELP)
        return

    cmd = sys.argv[1].lower()
    args = sys.argv[2:]

    # Session selection via -s flag
    session = "default"
    if "-s" in sys.argv:
        idx = sys.argv.index("-s")
        if idx + 1 < len(sys.argv):
            session = sys.argv[idx + 1]
            args = [a for a in args if a != "-s" and a != session]

    browser = ZionBrowser(session)

    commands = {
        "get": cmd_get,
        "links": cmd_links,
        "forms": cmd_forms,
        "submit": cmd_submit,
        "login": cmd_login,
        "search": cmd_search,
        "api": cmd_api,
        "download": cmd_download,
        "cookies": cmd_cookies,
        "session": cmd_session,
        "pipe": cmd_pipe,
        "serve": cmd_serve,
        "mem": cmd_mem,
        "history": cmd_history,
        "i": cmd_interactive,
        "interactive": cmd_interactive,
    }

    if cmd == "cache" and args and args[0] == "clear":
        browser.http.cache.clear()
        print("  Cache cleared.")
    elif cmd in commands:
        commands[cmd](browser, args)
    elif cmd in ("help", "-h", "--help"):
        print(HELP)
    elif cmd == "version":
        print(f"  {PRODUCT_NAME} v{VERSION}")
    else:
        # Try as URL
        if "." in cmd:
            page = browser.go(cmd)
            print(page.summary())
        else:
            print(f"  Unknown command: {cmd}")
            print(HELP)


if __name__ == "__main__":
    main()
