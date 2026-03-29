#!/usr/bin/env python3
"""
ZionBrowser Agent Extension — AI Agent Interface
Em nome do Senhor Jesus Cristo, nosso Salvador

Designed for Claude Code, OpenClaw, and any AI agent.
This is the PRIMARY interface for AI agents to control the browser.

ZERO external dependencies. Pure Python stdlib.

Architecture:
  AI Agent (Claude/OpenClaw)
       │
       ▼
  ZionAgent API  ← This module
       │
       ├── HTTP Client (~5MB) — 90% of tasks
       └── Chrome CDP (on-demand) — Cloudflare/SPA/Social

Usage as Python library:
    from zion_agent import ZionAgent
    agent = ZionAgent()
    result = agent.browse("https://hackenproof.com")
    agent.close()

Usage as CLI:
    python3 zion_agent.py browse <url>
    python3 zion_agent.py search <query>
    python3 zion_agent.py forms <url>
    python3 zion_agent.py submit <url> field1=val1 field2=val2
    python3 zion_agent.py login <url> <user> <pass>
    python3 zion_agent.py screenshot <url>
    python3 zion_agent.py pipeline <file.json>
    python3 zion_agent.py serve [port]

Usage as MCP Tool (for Claude Code):
    Add to ~/.mcp.json:
    {
      "mcpServers": {
        "zion-browser": {
          "command": "python3",
          "args": ["/home/administrador/zion-browser/zion_agent.py", "mcp"]
        }
      }
    }

(c) 2026 Padrao Bitcoin | $29.99
"""

import json
import sys
import os
import time
from pathlib import Path

# Add parent dir to path
sys.path.insert(0, str(Path(__file__).parent))

from zion_browser import ZionBrowser, ZionPipeline, ZionPage, ResponseCache, FirefoxCookieImporter
from zion_browser import ZION_DIR, VERSION, mem_mb


class ZionAgent:
    """AI Agent interface for ZionBrowser.

    Provides a simplified, high-level API designed for AI agents.
    Every method returns a clean dict — easy for LLMs to parse.
    """

    def __init__(self, session="agent"):
        self.browser = ZionBrowser(session)
        self.cdp = None
        self._chrome = False
        # Import Firefox cookies on first use
        self._cookies_imported = (ZION_DIR / ".cookies_imported").exists()

    def browse(self, url, force_chrome=False):
        """Navigate to URL. Auto-selects HTTP or Chrome mode.

        Returns dict with: status, title, url, text, links_count, forms_count, mode
        """
        if not self._cookies_imported:
            self._import_cookies()

        if not url.startswith("http"):
            url = "https://" + url

        # Try HTTP first (fast, low memory)
        if not force_chrome:
            page = self.browser.go(url)

            if not page.is_cloudflare and page.status != 0:
                return self._page_result(page, "http")

        # Fallback to Chrome CDP
        return self._chrome_browse(url)

    def search(self, query, max_results=10):
        """Search the web via DuckDuckGo.

        Returns list of {title, url}
        """
        results = self.browser.search(query)
        return {"query": query, "results": results[:max_results]}

    def forms(self, url=None):
        """Get forms on current or specified page.

        Returns list of form dicts with inputs.
        """
        if url:
            self.browse(url)
        if not self.browser.page:
            return {"error": "No page loaded"}
        return {"url": self.browser.page.url, "forms": self.browser.page.forms}

    def links(self, url=None, pattern=None):
        """Get links on current or specified page.

        Args:
            url: Navigate to URL first (optional)
            pattern: Regex filter for links (optional)
        """
        if url:
            self.browse(url)
        if not self.browser.page:
            return {"error": "No page loaded"}

        links = self.browser.page.links
        if pattern:
            links = self.browser.page.find_links(pattern)

        return {"url": self.browser.page.url, "links": links[:100], "total": len(links)}

    def submit(self, url, data, method="POST"):
        """Submit form data to URL.

        Args:
            url: Target URL
            data: Dict of form fields
            method: POST or GET
        """
        if method == "GET":
            import urllib.parse
            qs = urllib.parse.urlencode(data)
            page = self.browser.go(f"{url}?{qs}")
        else:
            page = self.browser.post(url, data)

        return self._page_result(page, "http")

    def login(self, url, username, password, **kwargs):
        """Login to a website.

        Returns {success, message, title, url}
        """
        ok, msg = self.browser.login(url, username, password,
                                     kwargs.get("user_field"),
                                     kwargs.get("pass_field"))
        result = {"success": ok, "message": msg}
        if self.browser.page:
            result["title"] = self.browser.page.title
            result["url"] = self.browser.page.url
        return result

    def api(self, url, method="GET", json_data=None, headers=None):
        """Make JSON API call.

        Returns {status, data}
        """
        status, data = self.browser.api(url, method, json_data, headers)
        return {"status": status, "data": data}

    def download(self, url, filepath=None):
        """Download file.

        Returns {success, path, size}
        """
        if not filepath:
            filepath = f"/tmp/zion_{int(time.time())}"
        ok, path, size = self.browser.download(url, filepath)
        return {"success": ok, "path": path, "size": size}

    def screenshot(self, url=None, filepath=None):
        """Take screenshot of current or specified page (requires Chrome).

        Returns {path}
        """
        if url:
            self._chrome_browse(url)
        elif not self._chrome:
            return {"error": "No Chrome session. Provide URL."}

        if self.cdp:
            path = self.cdp.screenshot(filepath)
            return {"path": path}
        return {"error": "Chrome not available"}

    def click(self, selector):
        """Click element by CSS selector (requires Chrome).

        Returns {success}
        """
        if not self._chrome:
            return {"error": "Chrome not active. Use browse(url, force_chrome=True) first."}
        result = self.cdp.click(selector)
        return {"success": bool(result)}

    def type_text(self, selector, text):
        """Type text into element (requires Chrome).

        Returns {success}
        """
        if not self._chrome:
            return {"error": "Chrome not active."}
        self.cdp.type_text(selector, text)
        return {"success": True}

    def evaluate_js(self, expression):
        """Execute JavaScript in Chrome (requires Chrome).

        Returns {result}
        """
        if not self._chrome:
            return {"error": "Chrome not active."}
        result = self.cdp.evaluate(expression)
        return {"result": result}

    def cookies(self, action="list", domain=None):
        """Manage cookies.

        Actions: list, import, clear, export
        """
        if action == "list":
            clist = []
            for c in list(self.browser.http.cookie_jar)[:100]:
                clist.append({"domain": c.domain, "name": c.name, "value": c.value[:50]})
            return {"cookies": clist, "total": len(list(self.browser.http.cookie_jar))}

        elif action == "import":
            count, msg = self.browser.import_firefox_cookies(domain)
            return {"imported": count, "message": msg}

        elif action == "clear":
            self.browser.http.cookie_jar.clear()
            self.browser.http._save()
            return {"message": "Cookies cleared"}

        elif action == "export":
            clist = []
            for c in self.browser.http.cookie_jar:
                clist.append({"domain": c.domain, "name": c.name, "value": c.value})
            return {"cookies": clist}

    def pipeline(self, pipeline_path_or_dict):
        """Execute task pipeline.

        Args:
            pipeline_path_or_dict: Path to JSON file or dict
        """
        pipe = ZionPipeline(self.browser)
        results = pipe.run(pipeline_path_or_dict)
        return {"results": results, "total_steps": len(results)}

    def memory(self):
        """Get memory usage info."""
        return {
            "rss_mb": round(mem_mb(), 1),
            "cookies": len(list(self.browser.http.cookie_jar)),
            "chrome_active": self._chrome,
            "session": self.browser.session_name,
            "version": VERSION,
        }

    def close(self):
        """Clean up — close Chrome if active."""
        if self.cdp:
            self.cdp.close()
            self.cdp = None
            self._chrome = False

    # Internal methods

    def _import_cookies(self):
        """Auto-import Firefox cookies on first use."""
        try:
            profiles = FirefoxCookieImporter.find_profiles()
            if profiles:
                cookies = FirefoxCookieImporter.import_cookies(profiles[0]["path"])
                FirefoxCookieImporter.cookies_to_jar(cookies, self.browser.http.cookie_jar)
                self.browser.http._save()
                (ZION_DIR / ".cookies_imported").touch()
                self._cookies_imported = True
        except Exception:
            pass

    def _chrome_browse(self, url):
        """Navigate using Chrome CDP."""
        try:
            from zion_cdp import CDPClient
            if not self._chrome:
                self.cdp = CDPClient()
                self.cdp.launch_chrome(url, low_mem=True)
                self.cdp.connect()
                self._chrome = True
                time.sleep(2)
            else:
                self.cdp.navigate(url)
                time.sleep(2)

            return {
                "mode": "chrome",
                "status": 200,
                "title": self.cdp.get_title(),
                "url": self.cdp.get_url(),
                "text": self.cdp.get_text()[:3000],
                "links_count": len(self.cdp.get_links()),
                "forms_count": len(self.cdp.get_forms()),
            }
        except Exception as e:
            return {
                "mode": "chrome",
                "status": 0,
                "error": str(e),
                "text": "",
                "title": "",
                "url": url,
            }

    def _page_result(self, page, mode):
        return {
            "mode": mode,
            "status": page.status,
            "title": page.title,
            "url": page.url,
            "text": page.text[:2000],
            "links_count": len(page.links),
            "forms_count": len(page.forms),
            "cloudflare": page.is_cloudflare,
        }


# ===================================================
# MCP SERVER — For Claude Code integration
# ===================================================

def run_mcp_server():
    """Run as MCP server for Claude Code."""
    import sys

    agent = ZionAgent("claude")

    # MCP protocol: read JSON-RPC from stdin, write to stdout
    def respond(id, result):
        response = {"jsonrpc": "2.0", "id": id, "result": result}
        msg = json.dumps(response)
        sys.stdout.write(f"Content-Length: {len(msg)}\r\n\r\n{msg}")
        sys.stdout.flush()

    def respond_error(id, code, message):
        response = {"jsonrpc": "2.0", "id": id, "error": {"code": code, "message": message}}
        msg = json.dumps(response)
        sys.stdout.write(f"Content-Length: {len(msg)}\r\n\r\n{msg}")
        sys.stdout.flush()

    tools = [
        {
            "name": "zion_browse",
            "description": "Navigate to URL and get page content. Auto-selects HTTP or Chrome mode.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to navigate to"},
                    "force_chrome": {"type": "boolean", "default": False}
                },
                "required": ["url"]
            }
        },
        {
            "name": "zion_search",
            "description": "Search the web via DuckDuckGo",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"}
                },
                "required": ["query"]
            }
        },
        {
            "name": "zion_forms",
            "description": "Get forms on a page",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to check forms"}
                },
                "required": ["url"]
            }
        },
        {
            "name": "zion_submit",
            "description": "Submit form data to URL",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "data": {"type": "object"},
                    "method": {"type": "string", "default": "POST"}
                },
                "required": ["url", "data"]
            }
        },
        {
            "name": "zion_login",
            "description": "Login to a website",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "username": {"type": "string"},
                    "password": {"type": "string"}
                },
                "required": ["url", "username", "password"]
            }
        },
        {
            "name": "zion_api",
            "description": "Make JSON API call",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "method": {"type": "string", "default": "GET"},
                    "json_data": {"type": "object"}
                },
                "required": ["url"]
            }
        },
        {
            "name": "zion_screenshot",
            "description": "Take screenshot of webpage (uses Chrome)",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "url": {"type": "string"}
                },
                "required": ["url"]
            }
        },
        {
            "name": "zion_click",
            "description": "Click element by CSS selector (requires Chrome active)",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "selector": {"type": "string"}
                },
                "required": ["selector"]
            }
        },
        {
            "name": "zion_type",
            "description": "Type text into element (requires Chrome active)",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "selector": {"type": "string"},
                    "text": {"type": "string"}
                },
                "required": ["selector", "text"]
            }
        },
        {
            "name": "zion_cookies",
            "description": "Manage cookies (list, import from Firefox, clear)",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["list", "import", "clear"]},
                    "domain": {"type": "string"}
                },
                "required": ["action"]
            }
        },
    ]

    # Main MCP loop
    while True:
        try:
            # Read Content-Length header
            line = sys.stdin.readline()
            if not line:
                break
            if line.startswith("Content-Length:"):
                length = int(line.split(":")[1].strip())
                sys.stdin.readline()  # Empty line
                body = sys.stdin.read(length)
                request = json.loads(body)
            else:
                continue

            method = request.get("method", "")
            id = request.get("id")
            params = request.get("params", {})

            if method == "initialize":
                respond(id, {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "zion-browser", "version": VERSION}
                })

            elif method == "tools/list":
                respond(id, {"tools": tools})

            elif method == "tools/call":
                tool_name = params.get("name", "")
                args = params.get("arguments", {})

                try:
                    if tool_name == "zion_browse":
                        result = agent.browse(args["url"], args.get("force_chrome", False))
                    elif tool_name == "zion_search":
                        result = agent.search(args["query"])
                    elif tool_name == "zion_forms":
                        result = agent.forms(args.get("url"))
                    elif tool_name == "zion_submit":
                        result = agent.submit(args["url"], args["data"], args.get("method", "POST"))
                    elif tool_name == "zion_login":
                        result = agent.login(args["url"], args["username"], args["password"])
                    elif tool_name == "zion_api":
                        result = agent.api(args["url"], args.get("method", "GET"), args.get("json_data"))
                    elif tool_name == "zion_screenshot":
                        result = agent.screenshot(args.get("url"))
                    elif tool_name == "zion_click":
                        result = agent.click(args["selector"])
                    elif tool_name == "zion_type":
                        result = agent.type_text(args["selector"], args["text"])
                    elif tool_name == "zion_cookies":
                        result = agent.cookies(args["action"], args.get("domain"))
                    else:
                        result = {"error": f"Unknown tool: {tool_name}"}

                    respond(id, {
                        "content": [{"type": "text", "text": json.dumps(result, indent=2, default=str)}]
                    })

                except Exception as e:
                    respond(id, {
                        "content": [{"type": "text", "text": json.dumps({"error": str(e)})}],
                        "isError": True
                    })

            elif method == "notifications/initialized":
                pass  # Acknowledgement, no response needed

            else:
                if id:
                    respond_error(id, -32601, f"Method not found: {method}")

        except Exception as e:
            sys.stderr.write(f"MCP Error: {e}\n")
            continue


# ===================================================
# CLI ENTRY
# ===================================================

def main():
    if len(sys.argv) < 2:
        print(f"""
ZionBrowser Agent v{VERSION} — AI Agent Interface
Designed for Claude Code, OpenClaw, and AI agents

CLI:
  python3 zion_agent.py browse <url>
  python3 zion_agent.py search <query>
  python3 zion_agent.py forms <url>
  python3 zion_agent.py links <url> [pattern]
  python3 zion_agent.py submit <url> key=val key2=val2
  python3 zion_agent.py login <url> <user> <pass>
  python3 zion_agent.py api <url>
  python3 zion_agent.py screenshot <url>
  python3 zion_agent.py cookies [list|import|clear]
  python3 zion_agent.py pipeline <file.json>
  python3 zion_agent.py mem
  python3 zion_agent.py mcp              # Run as MCP server

Python:
  from zion_agent import ZionAgent
  agent = ZionAgent()
  result = agent.browse("https://example.com")
""")
        return

    cmd = sys.argv[1]
    args = sys.argv[2:]

    if cmd == "mcp":
        run_mcp_server()
        return

    agent = ZionAgent()

    try:
        if cmd == "browse":
            result = agent.browse(args[0], "--chrome" in args)
            print(json.dumps(result, indent=2, default=str))

        elif cmd == "search":
            result = agent.search(" ".join(args))
            print(json.dumps(result, indent=2))

        elif cmd == "forms":
            result = agent.forms(args[0] if args else None)
            print(json.dumps(result, indent=2))

        elif cmd == "links":
            pattern = args[1] if len(args) > 1 else None
            result = agent.links(args[0] if args else None, pattern)
            print(json.dumps(result, indent=2))

        elif cmd == "submit":
            url = args[0]
            data = {}
            for a in args[1:]:
                if "=" in a:
                    k, v = a.split("=", 1)
                    data[k] = v
            result = agent.submit(url, data)
            print(json.dumps(result, indent=2, default=str))

        elif cmd == "login":
            result = agent.login(args[0], args[1], args[2])
            print(json.dumps(result, indent=2, default=str))

        elif cmd == "api":
            result = agent.api(args[0])
            print(json.dumps(result, indent=2, default=str))

        elif cmd == "screenshot":
            result = agent.screenshot(args[0] if args else None)
            print(json.dumps(result, indent=2))

        elif cmd == "cookies":
            action = args[0] if args else "list"
            domain = args[1] if len(args) > 1 else None
            result = agent.cookies(action, domain)
            print(json.dumps(result, indent=2))

        elif cmd == "pipeline":
            result = agent.pipeline(args[0])
            print(json.dumps(result, indent=2, default=str))

        elif cmd == "mem":
            result = agent.memory()
            print(json.dumps(result, indent=2))

        else:
            print(f"Unknown command: {cmd}")

    finally:
        agent.close()


if __name__ == "__main__":
    main()
