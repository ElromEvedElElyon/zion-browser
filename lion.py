#!/usr/bin/env python3
"""
LION — Learning & Intelligence Operative Navigator
Em nome do Senhor Jesus Cristo, nosso Salvador

The AI brain of ZionBrowser. An autonomous learning agent that:
- Learns from every navigation (success, failure, patterns)
- Remembers site structures, form fields, auth flows
- Auto-applies cookies and auth tokens
- Detects and adapts to anti-bot measures
- Suggests optimal navigation strategies
- Grows smarter with every interaction

Integrated with Israel/Four and ZionBrowser ecosystem.

Architecture:
  LION Agent
    ├── Knowledge Base (JSON) — site patterns, form structures, auth flows
    ├── Error Memory — failures and how to overcome them
    ├── Cookie Intelligence — auto-apply best cookies per domain
    ├── Navigation Strategy — optimal path to reach any page
    └── ZionBrowser — execution engine (HTTP + Chrome CDP)

Usage:
    python3 lion.py navigate <url>         # Smart navigate (uses all knowledge)
    python3 lion.py learn <url>            # Learn site structure
    python3 lion.py recall <domain>        # What do we know about this domain?
    python3 lion.py auth <domain>          # Show auth strategy for domain
    python3 lion.py errors [domain]        # Show errors & solutions learned
    python3 lion.py pipeline <goal>        # Auto-generate pipeline for goal
    python3 lion.py train                  # Train on all history
    python3 lion.py status                 # Knowledge base status
    python3 lion.py mcp                    # Run as MCP server for Claude

(c) 2026 Padrao Bitcoin | Israel/Four Integration
"""

import json
import os
import sys
import time
import re
import hashlib
from pathlib import Path
from datetime import datetime
from collections import defaultdict

# Add parent dir
sys.path.insert(0, str(Path(__file__).parent))

LION_DIR = Path.home() / ".zion" / "lion"
KNOWLEDGE_FILE = LION_DIR / "knowledge.json"
ERRORS_FILE = LION_DIR / "errors.json"
AUTH_FILE = LION_DIR / "auth_strategies.json"
PATTERNS_FILE = LION_DIR / "site_patterns.json"
COOKIES_INTEL_FILE = LION_DIR / "cookies_intel.json"
HISTORY_FILE = Path.home() / ".zion" / "history.jsonl"

# Ensure dirs
LION_DIR.mkdir(parents=True, exist_ok=True)

VERSION = "1.0.0"


class LionKnowledge:
    """Persistent knowledge base that grows with every interaction."""

    def __init__(self):
        self.sites = self._load(KNOWLEDGE_FILE, {})
        self.errors = self._load(ERRORS_FILE, {"errors": [], "solutions": {}})
        self.auth = self._load(AUTH_FILE, {})
        self.patterns = self._load(PATTERNS_FILE, {})
        self.cookies_intel = self._load(COOKIES_INTEL_FILE, {})

    def _load(self, path, default):
        if path.exists():
            try:
                return json.loads(path.read_text())
            except Exception:
                pass
        return default

    def _save(self, path, data):
        path.write_text(json.dumps(data, indent=2, default=str))

    def save_all(self):
        self._save(KNOWLEDGE_FILE, self.sites)
        self._save(ERRORS_FILE, self.errors)
        self._save(AUTH_FILE, self.auth)
        self._save(PATTERNS_FILE, self.patterns)
        self._save(COOKIES_INTEL_FILE, self.cookies_intel)

    # Site Knowledge
    def learn_site(self, domain, data):
        """Store/update knowledge about a site."""
        if domain not in self.sites:
            self.sites[domain] = {
                "first_seen": datetime.now().isoformat(),
                "visits": 0,
                "pages": {},
                "forms": {},
                "api_endpoints": [],
                "auth_type": None,
                "cloudflare": False,
                "requires_js": False,
                "success_rate": 1.0,
                "notes": [],
            }
        site = self.sites[domain]
        site["visits"] += 1
        site["last_visit"] = datetime.now().isoformat()
        site.update(data)
        self._save(KNOWLEDGE_FILE, self.sites)

    def learn_page(self, domain, path, page_data):
        """Store knowledge about a specific page."""
        if domain not in self.sites:
            self.learn_site(domain, {})
        self.sites[domain]["pages"][path] = {
            "title": page_data.get("title", ""),
            "forms_count": page_data.get("forms_count", 0),
            "links_count": page_data.get("links_count", 0),
            "status": page_data.get("status", 0),
            "last_seen": datetime.now().isoformat(),
        }
        self._save(KNOWLEDGE_FILE, self.sites)

    def get_site(self, domain):
        return self.sites.get(domain, {})

    # Error Learning
    def learn_error(self, domain, url, error_type, error_msg, solution=None):
        """Record an error and its solution for future reference."""
        entry = {
            "domain": domain,
            "url": url,
            "type": error_type,
            "message": error_msg,
            "timestamp": datetime.now().isoformat(),
            "solution": solution,
        }
        self.errors["errors"].append(entry)

        # Index solutions by error type
        if solution:
            key = f"{domain}:{error_type}"
            self.errors["solutions"][key] = {
                "solution": solution,
                "success_count": self.errors["solutions"].get(key, {}).get("success_count", 0) + 1,
                "last_used": datetime.now().isoformat(),
            }

        # Keep errors list manageable
        if len(self.errors["errors"]) > 500:
            self.errors["errors"] = self.errors["errors"][-300:]

        self._save(ERRORS_FILE, self.errors)

    def get_solution(self, domain, error_type):
        """Get known solution for an error."""
        key = f"{domain}:{error_type}"
        sol = self.errors["solutions"].get(key)
        if sol:
            return sol["solution"]
        # Try generic solutions
        generic = self.errors["solutions"].get(f"*:{error_type}")
        if generic:
            return generic["solution"]
        return None

    # Auth Strategies
    def learn_auth(self, domain, strategy):
        """Store authentication strategy for a domain.

        strategy: {
            "type": "form|api|oauth|cookies",
            "login_url": "...",
            "user_field": "email",
            "pass_field": "password",
            "csrf_field": "token",
            "success_indicator": "dashboard|profile|my-account",
            "cookies_needed": ["session", "csrf"],
            "headers_needed": {"Authorization": "Bearer ..."},
        }
        """
        self.auth[domain] = strategy
        self.auth[domain]["last_success"] = datetime.now().isoformat()
        self._save(AUTH_FILE, self.auth)

    def get_auth(self, domain):
        return self.auth.get(domain, {})

    # Cookie Intelligence
    def learn_cookies(self, domain, cookie_names, purpose="session"):
        """Learn which cookies are important for a domain."""
        if domain not in self.cookies_intel:
            self.cookies_intel[domain] = {"cookies": {}, "required": []}
        for name in cookie_names:
            self.cookies_intel[domain]["cookies"][name] = {
                "purpose": purpose,
                "first_seen": datetime.now().isoformat(),
            }
        self._save(COOKIES_INTEL_FILE, self.cookies_intel)

    def get_required_cookies(self, domain):
        intel = self.cookies_intel.get(domain, {})
        return list(intel.get("cookies", {}).keys())

    # Pattern Detection
    def learn_pattern(self, pattern_type, domain, data):
        """Learn a navigation/site pattern.

        pattern_types: cloudflare, spa, api_first, form_login, oauth, redirect_chain
        """
        key = f"{pattern_type}:{domain}"
        self.patterns[key] = {
            "type": pattern_type,
            "domain": domain,
            "data": data,
            "learned": datetime.now().isoformat(),
            "use_count": self.patterns.get(key, {}).get("use_count", 0) + 1,
        }
        self._save(PATTERNS_FILE, self.patterns)

    def get_patterns(self, domain):
        result = {}
        for key, val in self.patterns.items():
            if domain in key:
                result[key] = val
        return result


class LionAgent:
    """The intelligent navigation agent."""

    def __init__(self):
        self.kb = LionKnowledge()
        self.browser = None

    def _get_browser(self):
        if not self.browser:
            from zion_browser import ZionBrowser
            self.browser = ZionBrowser("lion")
        return self.browser

    def _domain(self, url):
        from urllib.parse import urlparse
        return urlparse(url).netloc.replace("www.", "")

    def navigate(self, url):
        """Smart navigation using all accumulated knowledge + auto-recovery."""
        domain = self._domain(url)
        site = self.kb.get_site(domain)
        browser = self._get_browser()

        strategy = self._plan_navigation(url, domain, site)
        result = {"url": url, "domain": domain, "strategy": strategy["mode"]}

        try:
            if strategy["mode"] == "http":
                page = browser.go(url)
                result.update(self._process_page(page, domain, url))

                # AUTO-RECOVERY: Detect problems and suggest solutions
                if page.is_cloudflare:
                    result["blocked"] = "cloudflare"
                    result["recovery"] = "cloudflare_detected"
                    self.kb.learn_error(domain, url, "cloudflare",
                                       "Blocked by Cloudflare JS challenge",
                                       "Use Chrome CDP: zion-cdp chrome <url>")
                    self.kb.learn_site(domain, {"cloudflare": True, "requires_js": True})
                    self.kb.learn_pattern("cloudflare", domain, {"confirmed": True})
                    result["suggestion"] = "Use 'zion-cdp chrome <url>' (need ~300MB free RAM)"

                elif page.is_js_only:
                    result["js_only"] = True
                    result["recovery"] = "js_only_detected"
                    self.kb.learn_site(domain, {"requires_js": True})
                    result["suggestion"] = "Page is JS-rendered. Use 'zion-cdp chrome <url>' for forms"

                elif page.status == 403:
                    # Check if we have a learned solution
                    solution = self.kb.get_solution(domain, "403")
                    if solution:
                        result["learned_solution"] = solution
                    else:
                        self.kb.learn_error(domain, url, "403", "Forbidden",
                                           "Try importing cookies: zion cookies import <domain>")
                    result["suggestion"] = "Try: zion cookies import " + domain

                elif page.status == 404:
                    # Session expired pattern (common with Amazon, KDP)
                    if "session" in page.text.lower() or "sign in" in page.text.lower():
                        result["recovery"] = "session_expired"
                        self.kb.learn_error(domain, url, "session_expired",
                                           "Session expired, need re-login",
                                           "Re-import cookies or login again")
                        result["suggestion"] = "Session expired. Re-login or: zion cookies import " + domain

            elif strategy["mode"] == "chrome":
                # Try HTTP first (saves RAM), only suggest Chrome if needed
                page = browser.go(url)
                if page.is_cloudflare:
                    result["blocked"] = "cloudflare"
                    result["suggestion"] = "Use 'zion-cdp chrome <url>' when RAM available (need ~300MB free)"
                    self.kb.learn_error(domain, url, "cloudflare", "Blocked by Cloudflare JS challenge",
                                       "Use Chrome CDP mode with adequate RAM")
                elif page.is_js_only:
                    result.update(self._process_page(page, domain, url))
                    result["js_only"] = True
                    result["suggestion"] = "Forms/content hidden. Use 'zion-cdp chrome <url>'"
                else:
                    result.update(self._process_page(page, domain, url))

            elif strategy["mode"] == "api":
                api_url = strategy.get("api_url", url)
                status, data = browser.api(api_url)
                result["status"] = status
                result["data"] = data
                self.kb.learn_site(domain, {"api_endpoints": [api_url]})

            # Learn from successful navigation
            if result.get("status") == 200 and not result.get("blocked"):
                self.kb.learn_site(domain, {
                    "success_rate": min(1.0, site.get("success_rate", 0.5) + 0.1),
                })
                # Only mark requires_js=False if we got meaningful content
                if result.get("links_count", 0) > 5 and result.get("forms_count", 0) > 0:
                    self.kb.learn_site(domain, {"requires_js": False})

        except Exception as e:
            result["error"] = str(e)
            # Check for learned solution
            error_type = type(e).__name__
            solution = self.kb.get_solution(domain, error_type)
            if solution:
                result["learned_solution"] = solution
            self.kb.learn_error(domain, url, error_type, str(e))

        self.kb.save_all()
        return result

    def learn(self, url):
        """Deep learn a site — crawl structure, forms, auth flows."""
        domain = self._domain(url)
        browser = self._get_browser()
        learned = {"domain": domain, "pages_crawled": 0, "forms_found": 0, "links_found": 0}

        # Main page
        page = browser.go(url)
        if page.status == 200:
            self._process_page(page, domain, url)
            learned["pages_crawled"] = 1
            learned["forms_found"] = len(page.forms)
            learned["links_found"] = len(page.links)

            # Check for auth
            for form in page.forms:
                has_pass = any(i["type"] == "password" for i in form["inputs"])
                has_email = any("email" in i.get("name", "").lower() or "user" in i.get("name", "").lower()
                               for i in form["inputs"])
                if has_pass and has_email:
                    auth_strategy = {
                        "type": "form",
                        "login_url": url,
                        "form_action": form["action"],
                        "method": form["method"],
                        "fields": {},
                    }
                    for inp in form["inputs"]:
                        name = inp["name"]
                        if not name:
                            continue
                        nl = name.lower()
                        if any(k in nl for k in ["email", "user", "login"]):
                            auth_strategy["fields"]["username"] = name
                        elif any(k in nl for k in ["pass", "pwd"]):
                            auth_strategy["fields"]["password"] = name
                        elif inp["type"] == "hidden":
                            auth_strategy["fields"][name] = {"type": "hidden", "value": inp["value"]}

                    self.kb.learn_auth(domain, auth_strategy)
                    learned["auth_detected"] = True

            # Crawl internal links (first 10)
            internal_links = [l for l in page.links if domain in l["url"]][:10]
            for link in internal_links:
                try:
                    p2 = browser.go(link["url"])
                    if p2.status == 200:
                        self._process_page(p2, domain, link["url"])
                        learned["pages_crawled"] += 1
                        learned["forms_found"] += len(p2.forms)
                    time.sleep(0.5)  # Be polite
                except Exception:
                    pass

        elif page.is_cloudflare:
            self.kb.learn_site(domain, {"cloudflare": True, "requires_js": True})
            self.kb.learn_pattern("cloudflare", domain, {"detected": True})
            learned["cloudflare"] = True

        self.kb.save_all()
        return learned

    def recall(self, domain):
        """What do we know about a domain?"""
        site = self.kb.get_site(domain)
        auth = self.kb.get_auth(domain)
        patterns = self.kb.get_patterns(domain)
        cookies = self.kb.get_required_cookies(domain)

        # Get errors for this domain
        errors = [e for e in self.kb.errors["errors"] if e.get("domain") == domain][-5:]

        return {
            "domain": domain,
            "known": bool(site),
            "site": site,
            "auth_strategy": auth,
            "patterns": patterns,
            "required_cookies": cookies,
            "recent_errors": errors,
            "visits": site.get("visits", 0),
            "pages_known": len(site.get("pages", {})),
        }

    def suggest_pipeline(self, goal):
        """Auto-generate a navigation pipeline based on goal description."""
        # Parse goal to extract targets
        steps = []

        # Common goal patterns
        if "hackenproof" in goal.lower():
            auth = self.kb.get_auth("hackenproof.com")
            steps.append({"action": "cookies_import", "desc": "Import Firefox cookies"})
            if auth:
                steps.append({
                    "action": "login",
                    "url": auth.get("login_url", "https://hackenproof.com/signin"),
                    "data": {"user_field": auth.get("fields", {}).get("username", "email"),
                             "pass_field": auth.get("fields", {}).get("password", "password")},
                    "desc": "Login to HackenProof"
                })
            steps.append({"action": "get", "url": "https://hackenproof.com/programs", "desc": "Browse programs"})
            if "submit" in goal.lower() or "near" in goal.lower():
                steps.append({"action": "extract_links", "data": {"pattern": "near|NEAR"},
                              "desc": "Find NEAR program"})

        elif "immunefi" in goal.lower():
            steps.append({"action": "cookies_import", "desc": "Import Firefox cookies"})
            steps.append({"action": "get", "url": "https://bugs.immunefi.com", "desc": "Open Immunefi"})

        elif "bugcrowd" in goal.lower():
            steps.append({"action": "get", "url": "https://bugcrowd.com", "desc": "Open Bugcrowd"})
            if "openai" in goal.lower():
                steps.append({"action": "get", "url": "https://bugcrowd.com/openai", "desc": "OpenAI program"})

        elif "register" in goal.lower() or "signup" in goal.lower():
            steps.append({"action": "cookies_import", "desc": "Import cookies"})
            steps.append({"action": "get", "url": goal, "desc": "Open registration page"})
            steps.append({"action": "extract_forms", "desc": "Find registration form"})

        elif "search" in goal.lower():
            query = goal.replace("search", "").strip()
            steps.append({"action": "search", "data": {"query": query}, "desc": f"Search: {query}"})

        else:
            # Generic: just navigate
            steps.append({"action": "get", "url": goal, "desc": f"Navigate to {goal}"})
            steps.append({"action": "extract_links", "desc": "Map links"})
            steps.append({"action": "extract_forms", "desc": "Map forms"})

        pipeline = {
            "name": f"Auto-generated: {goal[:50]}",
            "description": f"Pipeline for: {goal}",
            "generated_by": "LION Agent",
            "timestamp": datetime.now().isoformat(),
            "steps": steps,
        }

        return pipeline

    def train(self):
        """Train on navigation history to improve knowledge."""
        if not HISTORY_FILE.exists():
            return {"message": "No history to train on"}

        stats = {"total": 0, "success": 0, "errors": 0, "domains_learned": set()}

        for line in HISTORY_FILE.read_text().strip().split("\n"):
            try:
                entry = json.loads(line)
                stats["total"] += 1
                domain = self._domain(entry.get("url", ""))
                stats["domains_learned"].add(domain)

                status = entry.get("status", 0)
                if status == 200:
                    stats["success"] += 1
                    self.kb.learn_site(domain, {"last_success_status": 200})
                elif status == 403:
                    self.kb.learn_error(domain, entry["url"], "403",
                                       "Forbidden - likely Cloudflare or auth required")
                    self.kb.learn_site(domain, {"requires_js": True})
                elif status == 0:
                    stats["errors"] += 1
                    self.kb.learn_error(domain, entry["url"], "connection",
                                       "Connection failed")
            except Exception:
                continue

        self.kb.save_all()
        return {
            "trained_on": stats["total"],
            "successful": stats["success"],
            "errors": stats["errors"],
            "domains": len(stats["domains_learned"]),
            "success_rate": f"{stats['success']/max(1,stats['total'])*100:.1f}%",
        }

    def status(self):
        """Knowledge base status."""
        return {
            "version": VERSION,
            "sites_known": len(self.kb.sites),
            "auth_strategies": len(self.kb.auth),
            "patterns_learned": len(self.kb.patterns),
            "errors_recorded": len(self.kb.errors.get("errors", [])),
            "solutions_known": len(self.kb.errors.get("solutions", {})),
            "cookies_intel": len(self.kb.cookies_intel),
            "top_sites": sorted(
                [(d, s.get("visits", 0)) for d, s in self.kb.sites.items()],
                key=lambda x: x[1], reverse=True
            )[:10],
        }

    # Internal helpers

    def _plan_navigation(self, url, domain, site):
        """Choose optimal navigation strategy based on knowledge."""
        # Check if we know this site needs Chrome
        if site.get("cloudflare") or site.get("requires_js"):
            return {"mode": "chrome"}

        # Check patterns
        patterns = self.kb.get_patterns(domain)
        if any("cloudflare" in k for k in patterns):
            return {"mode": "chrome"}

        # Check if there's a known API
        if site.get("api_endpoints"):
            return {"mode": "api", "api_url": site["api_endpoints"][0]}

        # Default: try HTTP (fast, low memory)
        return {"mode": "http"}

    def _process_page(self, page, domain, url):
        """Process a page result and learn from it."""
        from urllib.parse import urlparse
        path = urlparse(url).path

        result = {
            "status": page.status,
            "title": page.title,
            "url": page.url,
            "text": page.text[:1500],
            "links_count": len(page.links),
            "forms_count": len(page.forms),
        }

        # Learn page structure
        self.kb.learn_page(domain, path, result)

        # Detect Cloudflare
        if page.is_cloudflare:
            self.kb.learn_site(domain, {"cloudflare": True, "requires_js": True})
            self.kb.learn_pattern("cloudflare", domain, {"confirmed": True})
            result["cloudflare"] = True

        # Learn form patterns
        if page.forms:
            for i, form in enumerate(page.forms):
                form_key = form.get("action", f"form_{i}")
                self.kb.learn_site(domain, {"forms": {form_key: {
                    "method": form["method"],
                    "inputs": [{"name": inp["name"], "type": inp["type"]} for inp in form["inputs"]],
                }}})

        # Learn cookies we received
        try:
            cookies = [c.name for c in self._get_browser().http.cookie_jar if domain in c.domain]
            if cookies:
                self.kb.learn_cookies(domain, cookies)
        except Exception:
            pass

        return result


# ===================================================
# Pre-seed knowledge for our target sites
# ===================================================

SEED_KNOWLEDGE = {
    "hackenproof.com": {
        "cloudflare": True,
        "requires_js": True,
        "notes": ["Heavy Cloudflare protection", "Need Chrome CDP or imported cookies"],
    },
    "immunefi.com": {
        "requires_js": True,
        "notes": ["SPA app at bugs.immunefi.com", "API at bugs.immunefi.com/api"],
    },
    "bugcrowd.com": {
        "requires_js": False,
        "notes": ["Works with HTTP client", "CSRF token in meta tags"],
    },
    "github.com": {
        "requires_js": False,
        "notes": ["Works perfectly with HTTP", "API at api.github.com"],
    },
    "opire.dev": {
        "requires_js": False,
        "notes": ["SSR, works with HTTP", "Bounties on home page"],
    },
    "audits.sherlock.xyz": {
        "requires_js": True,
        "notes": ["SPA, needs Chrome"],
    },
    "cantina.xyz": {
        "requires_js": True,
        "notes": ["SPA, needs Chrome"],
    },
    # LEARNED Session 60 — Amazon issues
    "developer.amazon.com": {
        "requires_js": True,
        "brotli": True,
        "notes": [
            "Landing page works with HTTP (Accept-Encoding: identity)",
            "Registration form is JS-rendered (React) — needs Chrome CDP",
            "Sign-in page at amazon.com/ap/signin MUST use Accept-Encoding: identity",
            "Brotli compression even when not requested — FIXED with identity header",
            "Console/apps pages redirect to registration if not completed",
            "Cookies from Firefox can be imported for auth",
        ],
    },
    "kdp.amazon.com": {
        "requires_js": False,
        "brotli": True,
        "notes": [
            "Bookshelf works with HTTP (SSR)",
            "Account page (account.kdp.amazon.com) is JS-only",
            "Session expires FAST — re-login frequently needed",
            "2SV required for royalty payments",
            "Create title at: /action/dualbookshelf.createnew/create",
        ],
    },
    "www.amazon.com": {
        "brotli": True,
        "requires_js": False,
        "notes": [
            "CRITICAL: Uses Brotli compression by default even with gzip request",
            "MUST use Accept-Encoding: identity to get readable content",
            "Sign-in forms detectable with HTTP (after identity encoding fix)",
            "CSRF token: appActionToken in hidden fields",
        ],
    },
    "sell.amazon.com": {
        "brotli": True,
        "requires_js": True,
        "notes": ["Seller Central is JS-heavy SPA", "Digital downloads PROHIBITED for 3rd party"],
    },
    "account.kdp.amazon.com": {
        "requires_js": True,
        "notes": ["Fully JS-rendered account settings", "Needs Chrome CDP"],
    },
    "npmjs.com": {
        "requires_js": True,
        "notes": ["Login/token generation needs browser", "npm CLI uses tokens from ~/.npmrc"],
    },
}

SEED_AUTH = {
    "hackenproof.com": {
        "type": "form",
        "login_url": "https://hackenproof.com/signin",
        "fields": {"username": "email", "password": "password"},
    },
    "bugs.immunefi.com": {
        "type": "form",
        "login_url": "https://bugs.immunefi.com",
        "fields": {"username": "email", "password": "password"},
    },
    "bugcrowd.com": {
        "type": "form",
        "login_url": "https://bugcrowd.com/user/sign_in",
        "fields": {"username": "user[email]", "password": "user[password]"},
    },
    # Amazon — learned Session 60
    "developer.amazon.com": {
        "type": "cookie_import",
        "login_url": "https://www.amazon.com/ap/signin?openid.assoc_handle=mas_dev_portal",
        "notes": "Import cookies from Firefox first: zion cookies import amazon.com",
        "fields": {"username": "email", "password": "password"},
    },
    "kdp.amazon.com": {
        "type": "cookie_import",
        "login_url": "https://kdp.amazon.com/en_US/signin",
        "notes": "Session expires fast. Re-import cookies frequently.",
    },
}


def seed_knowledge():
    """Pre-seed knowledge base if empty."""
    kb = LionKnowledge()
    if not kb.sites:
        for domain, data in SEED_KNOWLEDGE.items():
            kb.learn_site(domain, data)
        for domain, auth in SEED_AUTH.items():
            kb.learn_auth(domain, auth)
        kb.save_all()
        return True
    return False


# ===================================================
# CLI
# ===================================================

def main():
    if len(sys.argv) < 2:
        print(f"""
LION v{VERSION} — Learning & Intelligence Operative Navigator
AI brain of ZionBrowser | Integrated with Israel/Four

Commands:
  lion navigate <url>          Smart navigate (uses all knowledge)
  lion learn <url>             Deep-learn site structure
  lion recall <domain>         What we know about domain
  lion auth <domain>           Auth strategy for domain
  lion errors [domain]         Errors & solutions learned
  lion pipeline <goal>         Auto-generate navigation pipeline
  lion train                   Train on all history
  lion seed                    Pre-seed knowledge base
  lion status                  Knowledge base status

Part of ZionBrowser ecosystem | Padrao Bitcoin
""")
        return

    cmd = sys.argv[1]
    args = sys.argv[2:]

    lion = LionAgent()

    if cmd == "navigate" or cmd == "nav":
        result = lion.navigate(args[0])
        print(json.dumps(result, indent=2, default=str))

    elif cmd == "learn":
        result = lion.learn(args[0])
        print(json.dumps(result, indent=2, default=str))

    elif cmd == "recall":
        result = lion.recall(args[0])
        print(json.dumps(result, indent=2, default=str))

    elif cmd == "auth":
        result = lion.kb.get_auth(args[0])
        print(json.dumps(result, indent=2, default=str))

    elif cmd == "errors":
        domain = args[0] if args else None
        errors = lion.kb.errors["errors"]
        if domain:
            errors = [e for e in errors if e.get("domain") == domain]
        solutions = lion.kb.errors.get("solutions", {})
        print(f"  Errors: {len(errors)}")
        for e in errors[-10:]:
            print(f"  [{e['type']}] {e['domain']} — {e['message'][:60]}")
        print(f"\n  Solutions known: {len(solutions)}")
        for k, v in list(solutions.items())[:10]:
            print(f"  {k}: {v['solution'][:60]}")

    elif cmd == "pipeline":
        goal = " ".join(args)
        result = lion.suggest_pipeline(goal)
        print(json.dumps(result, indent=2))
        # Save pipeline
        name = re.sub(r'[^a-z0-9]+', '-', goal.lower())[:30]
        path = Path.home() / ".zion" / "pipes" / f"lion-{name}.json"
        path.write_text(json.dumps(result, indent=2))
        print(f"\n  Saved: {path}")

    elif cmd == "train":
        result = lion.train()
        print(json.dumps(result, indent=2, default=str))

    elif cmd == "seed":
        done = seed_knowledge()
        if done:
            print("  Knowledge base seeded with target site patterns.")
        else:
            print("  Knowledge base already has data. Skipping seed.")

    elif cmd == "status":
        result = lion.status()
        print(f"  LION v{VERSION} — Knowledge Base Status")
        print(f"  Sites known: {result['sites_known']}")
        print(f"  Auth strategies: {result['auth_strategies']}")
        print(f"  Patterns learned: {result['patterns_learned']}")
        print(f"  Errors recorded: {result['errors_recorded']}")
        print(f"  Solutions known: {result['solutions_known']}")
        if result['top_sites']:
            print(f"\n  Top sites:")
            for domain, visits in result['top_sites']:
                print(f"    {domain:30s} {visits} visits")

    else:
        print(f"Unknown command: {cmd}")


if __name__ == "__main__":
    main()
