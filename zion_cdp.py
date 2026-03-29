#!/usr/bin/env python3
"""
ZionBrowser CDP Module — Chrome DevTools Protocol Integration
Em nome do Senhor Jesus Cristo, nosso Salvador

Pure Python stdlib — ZERO external dependencies.
Connects to Chrome via WebSocket CDP for JS-heavy sites.

Strategy: Launch Chrome ONLY when needed, execute, close immediately.
- HTTP client: ~5MB RAM (90% of tasks)
- Chrome CDP: ~200-400MB (only for Cloudflare/SPA sites)
- Auto-kill after task to free RAM

(c) 2026 Padrao Bitcoin
"""

import json
import os
import signal
import socket
import struct
import subprocess
import sys
import time
import hashlib
import ssl
import re
from pathlib import Path
from urllib.parse import urlparse
import urllib.request

ZION_DIR = Path.home() / ".zion"
CDP_PROFILE = ZION_DIR / "chrome-profile"
CDP_PORT = 9222

# Ultra-minimal Chrome flags for low RAM
CHROME_FLAGS = [
    "--headless=new",
    "--disable-gpu",
    "--disable-software-rasterizer",
    "--disable-dev-shm-usage",
    "--no-sandbox",
    "--disable-extensions",
    "--disable-background-networking",
    "--disable-default-apps",
    "--disable-sync",
    "--disable-translate",
    "--disable-features=TranslateUI",
    "--disable-breakpad",
    "--disable-component-update",
    "--disable-domain-reliability",
    "--disable-features=AudioServiceOutOfProcess",
    "--disable-hang-monitor",
    "--disable-ipc-flooding-protection",
    "--disable-popup-blocking",
    "--disable-prompt-on-repost",
    "--disable-renderer-backgrounding",
    "--disable-client-side-phishing-detection",
    "--metrics-recording-only",
    "--no-first-run",
    "--password-store=basic",
    "--use-mock-keychain",
    "--single-process",  # Saves ~100MB RAM
    "--js-flags=--max-old-space-size=128",  # Limit V8 heap
    "--disable-features=site-per-process",  # Reduce process count
    f"--user-data-dir={CDP_PROFILE}",
    f"--remote-debugging-port={CDP_PORT}",
]

# Even more aggressive memory saving for 3.3GB machines
LOW_MEM_FLAGS = [
    "--disable-images",
    "--blink-settings=imagesEnabled=false",
    "--disable-remote-fonts",
]


# ===================================================
# WEBSOCKET CLIENT — Pure Python, minimal
# ===================================================

class SimpleWebSocket:
    """Minimal WebSocket client using only stdlib."""

    def __init__(self, url):
        parsed = urlparse(url)
        self.host = parsed.hostname
        self.port = parsed.port or 80
        self.path = parsed.path or "/"
        self.sock = None

    def connect(self):
        self.sock = socket.create_connection((self.host, self.port), timeout=30)
        # WebSocket handshake
        key = hashlib.sha1(os.urandom(16)).hexdigest()[:24]
        handshake = (
            f"GET {self.path} HTTP/1.1\r\n"
            f"Host: {self.host}:{self.port}\r\n"
            f"Upgrade: websocket\r\n"
            f"Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            f"Sec-WebSocket-Version: 13\r\n"
            f"\r\n"
        )
        self.sock.sendall(handshake.encode())

        # Read response
        resp = b""
        while b"\r\n\r\n" not in resp:
            resp += self.sock.recv(4096)

        if b"101" not in resp.split(b"\r\n")[0]:
            raise ConnectionError(f"WebSocket handshake failed: {resp[:200]}")

    def send(self, data):
        """Send text frame with masking."""
        payload = data.encode("utf-8") if isinstance(data, str) else data
        length = len(payload)
        mask_key = os.urandom(4)

        # Build frame header
        header = bytearray()
        header.append(0x81)  # FIN + Text opcode

        if length < 126:
            header.append(0x80 | length)  # Mask bit + length
        elif length < 65536:
            header.append(0x80 | 126)
            header.extend(struct.pack(">H", length))
        else:
            header.append(0x80 | 127)
            header.extend(struct.pack(">Q", length))

        header.extend(mask_key)

        # Mask payload
        masked = bytearray(length)
        for i in range(length):
            masked[i] = payload[i] ^ mask_key[i % 4]

        self.sock.sendall(bytes(header) + bytes(masked))

    def recv(self, timeout=30):
        """Receive text frame."""
        self.sock.settimeout(timeout)
        try:
            # Read frame header
            header = self._recv_bytes(2)
            opcode = header[0] & 0x0F
            masked = bool(header[1] & 0x80)
            length = header[1] & 0x7F

            if length == 126:
                length = struct.unpack(">H", self._recv_bytes(2))[0]
            elif length == 127:
                length = struct.unpack(">Q", self._recv_bytes(8))[0]

            if masked:
                mask_key = self._recv_bytes(4)

            payload = self._recv_bytes(length)

            if masked:
                payload = bytearray(payload)
                for i in range(len(payload)):
                    payload[i] ^= mask_key[i % 4]
                payload = bytes(payload)

            if opcode == 0x08:  # Close
                return None
            if opcode == 0x09:  # Ping
                self._send_pong(payload)
                return self.recv(timeout)

            return payload.decode("utf-8", errors="replace")

        except socket.timeout:
            return None

    def _recv_bytes(self, n):
        data = b""
        while len(data) < n:
            chunk = self.sock.recv(n - len(data))
            if not chunk:
                raise ConnectionError("Connection closed")
            data += chunk
        return data

    def _send_pong(self, payload):
        frame = bytearray([0x8A, 0x80 | len(payload)])
        mask = os.urandom(4)
        frame.extend(mask)
        masked = bytearray(len(payload))
        for i in range(len(payload)):
            masked[i] = payload[i] ^ mask[i % 4]
        frame.extend(masked)
        self.sock.sendall(bytes(frame))

    def close(self):
        if self.sock:
            try:
                # Send close frame
                frame = bytearray([0x88, 0x80, 0, 0, 0, 0])
                self.sock.sendall(bytes(frame))
                self.sock.close()
            except Exception:
                pass
            self.sock = None


# ===================================================
# CDP CLIENT — Chrome DevTools Protocol
# ===================================================

class CDPClient:
    """Chrome DevTools Protocol client — pure Python."""

    def __init__(self):
        self.ws = None
        self.msg_id = 0
        self.chrome_proc = None

    def launch_chrome(self, url="about:blank", low_mem=True):
        """Launch Chrome with minimal memory footprint."""
        CDP_PROFILE.mkdir(parents=True, exist_ok=True)

        # Kill any existing Chrome on our debug port
        self._kill_existing()

        chrome_bin = self._find_chrome()
        if not chrome_bin:
            raise FileNotFoundError("Chrome/Chromium not found")

        flags = list(CHROME_FLAGS)
        if low_mem:
            flags.extend(LOW_MEM_FLAGS)

        cmd = [chrome_bin] + flags + [url]
        self.chrome_proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            preexec_fn=os.setsid
        )

        # Wait for CDP to be ready
        for _ in range(30):
            time.sleep(0.5)
            if self._check_cdp_ready():
                return True

        raise TimeoutError("Chrome did not start in time")

    def connect(self):
        """Connect to Chrome CDP WebSocket."""
        # Get WebSocket URL from /json endpoint
        try:
            req = urllib.request.Request(f"http://127.0.0.1:{CDP_PORT}/json")
            resp = urllib.request.urlopen(req, timeout=5)
            tabs = json.loads(resp.read())
            if not tabs:
                raise ConnectionError("No tabs found")
            ws_url = tabs[0].get("webSocketDebuggerUrl", "")
            if not ws_url:
                raise ConnectionError("No WebSocket URL")
        except Exception as e:
            raise ConnectionError(f"Cannot connect to Chrome: {e}")

        self.ws = SimpleWebSocket(ws_url)
        self.ws.connect()
        return True

    def send(self, method, params=None, timeout=30):
        """Send CDP command and wait for response."""
        self.msg_id += 1
        msg = {"id": self.msg_id, "method": method}
        if params:
            msg["params"] = params

        self.ws.send(json.dumps(msg))

        # Wait for our response
        deadline = time.time() + timeout
        while time.time() < deadline:
            raw = self.ws.recv(timeout=min(5, deadline - time.time()))
            if raw is None:
                continue
            try:
                data = json.loads(raw)
                if data.get("id") == self.msg_id:
                    return data.get("result", {})
            except Exception:
                continue

        return None

    def navigate(self, url, wait_load=True):
        """Navigate to URL and optionally wait for load."""
        result = self.send("Page.navigate", {"url": url})
        if wait_load:
            self.send("Page.enable")
            # Wait for loadEventFired
            deadline = time.time() + 30
            while time.time() < deadline:
                raw = self.ws.recv(timeout=5)
                if raw and "Page.loadEventFired" in raw:
                    break
            time.sleep(1)  # Extra time for JS execution
        return result

    def get_html(self):
        """Get full page HTML after JS execution."""
        result = self.send("Runtime.evaluate", {
            "expression": "document.documentElement.outerHTML",
            "returnByValue": True
        })
        if result:
            val = result.get("result", {}).get("value", "")
            return val
        return ""

    def get_text(self):
        """Get page text content."""
        result = self.send("Runtime.evaluate", {
            "expression": "document.body.innerText",
            "returnByValue": True
        })
        if result:
            return result.get("result", {}).get("value", "")
        return ""

    def get_title(self):
        """Get page title."""
        result = self.send("Runtime.evaluate", {
            "expression": "document.title",
            "returnByValue": True
        })
        if result:
            return result.get("result", {}).get("value", "")
        return ""

    def get_url(self):
        """Get current URL."""
        result = self.send("Runtime.evaluate", {
            "expression": "window.location.href",
            "returnByValue": True
        })
        if result:
            return result.get("result", {}).get("value", "")
        return ""

    def evaluate(self, expression):
        """Execute JavaScript and return result."""
        result = self.send("Runtime.evaluate", {
            "expression": expression,
            "returnByValue": True,
            "awaitPromise": True
        })
        if result:
            return result.get("result", {}).get("value")
        return None

    def click(self, selector):
        """Click element by CSS selector."""
        return self.evaluate(f"""
            (() => {{
                const el = document.querySelector('{selector}');
                if (el) {{ el.click(); return true; }}
                return false;
            }})()
        """)

    def type_text(self, selector, text):
        """Type text into input field."""
        # Focus the element first
        self.evaluate(f"""
            (() => {{
                const el = document.querySelector('{selector}');
                if (el) {{
                    el.focus();
                    el.value = '';
                }}
            }})()
        """)

        # Type character by character via CDP
        for char in text:
            self.send("Input.dispatchKeyEvent", {
                "type": "keyDown",
                "text": char,
                "key": char,
            })
            self.send("Input.dispatchKeyEvent", {
                "type": "keyUp",
                "key": char,
            })

        # Also set value directly as backup
        escaped = text.replace("'", "\\'").replace("\n", "\\n")
        self.evaluate(f"""
            (() => {{
                const el = document.querySelector('{selector}');
                if (el) {{
                    el.value = '{escaped}';
                    el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                }}
            }})()
        """)

    def screenshot(self, filepath=None):
        """Take screenshot, save to file."""
        result = self.send("Page.captureScreenshot", {"format": "png"})
        if result and "data" in result:
            import base64
            data = base64.b64decode(result["data"])
            if filepath:
                Path(filepath).write_bytes(data)
                return filepath
            else:
                path = ZION_DIR / f"screenshot_{int(time.time())}.png"
                path.write_bytes(data)
                return str(path)
        return None

    def get_cookies(self):
        """Get all cookies from Chrome."""
        result = self.send("Network.getAllCookies")
        if result:
            return result.get("cookies", [])
        return []

    def set_cookie(self, name, value, domain, path="/"):
        """Set a cookie."""
        self.send("Network.setCookie", {
            "name": name,
            "value": value,
            "domain": domain,
            "path": path,
        })

    def get_links(self):
        """Extract all links from page."""
        result = self.evaluate("""
            (() => {
                const links = [];
                document.querySelectorAll('a[href]').forEach(a => {
                    links.push({url: a.href, text: (a.textContent || '').trim().substring(0, 80)});
                });
                return JSON.stringify(links);
            })()
        """)
        if result:
            try:
                return json.loads(result)
            except Exception:
                pass
        return []

    def get_forms(self):
        """Extract all forms from page."""
        result = self.evaluate("""
            (() => {
                const forms = [];
                document.querySelectorAll('form').forEach((f, i) => {
                    const inputs = [];
                    f.querySelectorAll('input,textarea,select').forEach(inp => {
                        inputs.push({
                            tag: inp.tagName.toLowerCase(),
                            type: inp.type || 'text',
                            name: inp.name || '',
                            id: inp.id || '',
                            value: inp.value || '',
                            placeholder: inp.placeholder || ''
                        });
                    });
                    forms.push({
                        index: i,
                        action: f.action || '',
                        method: (f.method || 'GET').toUpperCase(),
                        id: f.id || '',
                        inputs: inputs
                    });
                });
                return JSON.stringify(forms);
            })()
        """)
        if result:
            try:
                return json.loads(result)
            except Exception:
                pass
        return []

    def fill_form(self, form_data, form_index=0):
        """Fill and submit a form."""
        for field, value in form_data.items():
            escaped_val = value.replace("'", "\\'")
            self.evaluate(f"""
                (() => {{
                    const forms = document.querySelectorAll('form');
                    if (forms[{form_index}]) {{
                        const inp = forms[{form_index}].querySelector('[name="{field}"], #{field}');
                        if (inp) {{
                            inp.value = '{escaped_val}';
                            inp.dispatchEvent(new Event('input', {{ bubbles: true }}));
                            inp.dispatchEvent(new Event('change', {{ bubbles: true }}));
                        }}
                    }}
                }})()
            """)

    def submit_form(self, form_index=0):
        """Submit form by index."""
        self.evaluate(f"""
            (() => {{
                const forms = document.querySelectorAll('form');
                if (forms[{form_index}]) {{
                    forms[{form_index}].submit();
                }}
            }})()
        """)
        time.sleep(2)

    def wait_for(self, selector, timeout=10):
        """Wait for element to appear."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            result = self.evaluate(f"!!document.querySelector('{selector}')")
            if result:
                return True
            time.sleep(0.5)
        return False

    def scroll_to_bottom(self):
        """Scroll to bottom of page."""
        self.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(1)

    def close(self):
        """Close WebSocket and kill Chrome."""
        if self.ws:
            self.ws.close()
            self.ws = None
        self._kill_chrome()

    def _kill_chrome(self):
        """Kill Chrome process."""
        if self.chrome_proc:
            try:
                os.killpg(os.getpgid(self.chrome_proc.pid), signal.SIGTERM)
            except Exception:
                pass
            try:
                self.chrome_proc.wait(timeout=5)
            except Exception:
                try:
                    os.killpg(os.getpgid(self.chrome_proc.pid), signal.SIGKILL)
                except Exception:
                    pass
            self.chrome_proc = None

    def _kill_existing(self):
        """Kill any Chrome on our debug port."""
        try:
            subprocess.run(
                ["pkill", "-f", f"--remote-debugging-port={CDP_PORT}"],
                capture_output=True, timeout=5
            )
            time.sleep(0.5)
        except Exception:
            pass

    def _check_cdp_ready(self):
        try:
            req = urllib.request.Request(f"http://127.0.0.1:{CDP_PORT}/json/version")
            resp = urllib.request.urlopen(req, timeout=2)
            return resp.getcode() == 200
        except Exception:
            return False

    def _find_chrome(self):
        for path in ["/usr/bin/google-chrome", "/usr/bin/chromium-browser",
                     "/snap/bin/chromium", "/usr/bin/chromium"]:
            if os.path.exists(path):
                return path
        return None


# ===================================================
# HYBRID BROWSER — Smart routing: HTTP vs Chrome
# ===================================================

class ZionHybrid:
    """Hybrid browser: HTTP for simple sites, Chrome for JS-heavy ones.

    Usage:
        browser = ZionHybrid()
        page = browser.smart_get("https://hackenproof.com")  # Auto-selects mode
        browser.close()  # Always close to free RAM
    """

    # Sites known to need Chrome (Cloudflare, heavy SPA)
    CHROME_DOMAINS = {
        "hackenproof.com", "app.grayswan.ai", "audits.sherlock.xyz",
        "cantina.xyz", "twitter.com", "x.com", "web.whatsapp.com",
        "web.telegram.org", "discord.com", "chat.openai.com",
    }

    def __init__(self):
        # Import from main module
        from zion_browser import ZionBrowser
        self.http_browser = ZionBrowser()
        self.cdp = None
        self._chrome_active = False

    def smart_get(self, url):
        """Automatically choose HTTP or Chrome based on domain."""
        domain = urlparse(url).netloc.replace("www.", "")

        if domain in self.CHROME_DOMAINS:
            return self.chrome_get(url)

        # Try HTTP first
        page = self.http_browser.go(url)

        # If Cloudflare blocked, retry with Chrome
        if page.is_cloudflare or (page.status == 403 and len(page.text) < 100):
            print(f"  [!] Cloudflare detected, switching to Chrome CDP...")
            self.CHROME_DOMAINS.add(domain)  # Remember for next time
            return self.chrome_get(url)

        return {
            "mode": "http",
            "status": page.status,
            "title": page.title,
            "url": page.url,
            "text": page.text,
            "links": page.links,
            "forms": page.forms,
        }

    def chrome_get(self, url):
        """Navigate via Chrome CDP."""
        self._ensure_chrome()
        self.cdp.navigate(url)
        time.sleep(2)

        return {
            "mode": "chrome",
            "title": self.cdp.get_title(),
            "url": self.cdp.get_url(),
            "text": self.cdp.get_text()[:3000],
            "links": self.cdp.get_links()[:50],
            "forms": self.cdp.get_forms(),
        }

    def chrome_action(self, action, **kwargs):
        """Execute Chrome action (click, type, screenshot, etc.)."""
        self._ensure_chrome()

        if action == "click":
            return self.cdp.click(kwargs.get("selector", ""))
        elif action == "type":
            self.cdp.type_text(kwargs.get("selector", ""), kwargs.get("text", ""))
            return True
        elif action == "screenshot":
            return self.cdp.screenshot(kwargs.get("filepath"))
        elif action == "evaluate":
            return self.cdp.evaluate(kwargs.get("expression", ""))
        elif action == "fill_form":
            self.cdp.fill_form(kwargs.get("data", {}), kwargs.get("form_index", 0))
            return True
        elif action == "submit":
            self.cdp.submit_form(kwargs.get("form_index", 0))
            return True
        elif action == "wait":
            return self.cdp.wait_for(kwargs.get("selector", ""), kwargs.get("timeout", 10))
        elif action == "scroll":
            self.cdp.scroll_to_bottom()
            return True
        elif action == "cookies":
            return self.cdp.get_cookies()

        return None

    def _ensure_chrome(self):
        if not self._chrome_active:
            print("  Launching Chrome (low-mem mode)...")
            self.cdp = CDPClient()
            self.cdp.launch_chrome(low_mem=True)
            self.cdp.connect()
            self._chrome_active = True
            print(f"  Chrome ready on port {CDP_PORT}")

    def close_chrome(self):
        """Close Chrome to free RAM."""
        if self.cdp:
            self.cdp.close()
            self.cdp = None
            self._chrome_active = False
            print("  Chrome closed, RAM freed.")

    def close(self):
        self.close_chrome()


# ===================================================
# CLI for CDP module
# ===================================================

def main():
    if len(sys.argv) < 2:
        print(f"""
ZionBrowser CDP Module — Chrome DevTools Protocol
Pure Python, ZERO dependencies

Usage:
  python3 zion_cdp.py get <url>          Navigate (auto-detects if Chrome needed)
  python3 zion_cdp.py chrome <url>       Force Chrome CDP mode
  python3 zion_cdp.py screenshot <url>   Take screenshot
  python3 zion_cdp.py forms <url>        Show JS-rendered forms
  python3 zion_cdp.py links <url>        Show JS-rendered links
  python3 zion_cdp.py eval <js>          Evaluate JavaScript
  python3 zion_cdp.py kill               Kill Chrome process
""")
        return

    cmd = sys.argv[1]
    args = sys.argv[2:]

    if cmd == "kill":
        cdp = CDPClient()
        cdp._kill_existing()
        print("  Chrome processes killed.")
        return

    hybrid = ZionHybrid()

    try:
        if cmd == "get":
            result = hybrid.smart_get(args[0])
            print(f"  Mode: {result['mode']}")
            print(f"  Title: {result['title']}")
            print(f"  URL: {result['url']}")
            print(f"  Links: {len(result['links'])} | Forms: {len(result['forms'])}")
            print()
            text = result['text']
            for line in text.split("\n")[:40]:
                print(f"  {line[:120]}")

        elif cmd == "chrome":
            result = hybrid.chrome_get(args[0])
            print(f"  Title: {result['title']}")
            print(f"  URL: {result['url']}")
            print(f"  Links: {len(result['links'])} | Forms: {len(result['forms'])}")
            print()
            for line in result['text'].split("\n")[:40]:
                print(f"  {line[:120]}")

        elif cmd == "screenshot":
            hybrid.chrome_get(args[0])
            path = hybrid.chrome_action("screenshot")
            print(f"  Screenshot: {path}")

        elif cmd == "forms":
            result = hybrid.chrome_get(args[0])
            for f in result['forms']:
                print(f"\n  Form #{f['index']}: {f['method']} -> {f['action']}")
                for inp in f['inputs']:
                    print(f"    [{inp['type']:10s}] {inp['name']:25s} = {inp['value'][:30]}")

        elif cmd == "links":
            result = hybrid.chrome_get(args[0])
            for i, l in enumerate(result['links'][:50]):
                print(f"  [{i:3d}] {l['text'][:35]:35s} {l['url'][:80]}")

        elif cmd == "eval":
            hybrid._ensure_chrome()
            result = hybrid.cdp.evaluate(" ".join(args))
            print(f"  Result: {result}")

    finally:
        hybrid.close()


if __name__ == "__main__":
    main()
