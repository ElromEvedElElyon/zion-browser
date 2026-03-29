# ZionBrowser v2.0.1

**Ultra-Lightweight AI Agent Browser Toolkit — Pure Python, ZERO Dependencies, ~5MB RAM**

ZionBrowser is a CLI browser toolkit built entirely with Python standard library. Designed for AI agents, automation, and developers on resource-constrained systems.

```
$ zion get https://example.com     # Browse any page (~5MB RAM)
$ zion search "AI frameworks"      # Search the web
$ zion cookies import              # Import Firefox sessions
$ zion pipe tasks/register.json    # Run automated pipelines
$ zion serve 8080                  # API server for AI agents
$ pirate scan                      # Security scan your machine
$ lion1 hunt                       # Find auth tokens
```

## Why ZionBrowser?

| Feature | ZionBrowser | Firefox/Chrome | Playwright |
|---------|------------|----------------|------------|
| RAM Usage | **~5MB** | 500MB+ | 300MB+ |
| Dependencies | **0** | Hundreds | 50+ |
| AI Agent API | **Built-in** | No | No |
| MCP Server | **Native** | No | No |
| Security Suite | **8-layer** | Basic | No |
| Learning Engine | **LION AI** | No | No |

## 6 Modules Included

| # | Module | Description | Lines |
|---|--------|-------------|-------|
| 1 | **ZionBrowser Core** | HTTP client, streaming, cookie import, forms, search, caching, pipelines | 1,865 |
| 2 | **ZionAgent** | AI agent API — browse(), search(), login(), pipeline() + MCP server | 669 |
| 3 | **ZionCDP** | Chrome DevTools Protocol for JS-heavy sites, 64MB V8 heap | 827 |
| 4 | **LION** | Learning AI — remembers sites, auth flows, errors, navigation strategies | 836 |
| 5 | **LION-1** | Auth hunter — cookies, API keys, tokens + prompt injection shield | 837 |
| 6 | **PIRATE** | 8-layer security — rootkit detection, malware scan, auto-quarantine | 1,028 |

**Total: 5,982 lines of pure Python. No pip install needed.**

## Quick Start

```bash
# Clone
git clone https://github.com/ElromEvedElElyon/zion-browser.git
cd zion-browser

# Install (creates global commands: zion, lion, lion1, pirate)
python3 setup.py

# Done! Try it:
zion get https://news.ycombinator.com
```

**Requirements:** Python 3.6+ | Any OS (Linux, macOS, Windows) | No packages needed

## For AI Agents (MCP / Python API)

```python
from zion_agent import ZionAgent

agent = ZionAgent()
result = agent.browse("https://example.com")
print(result["text"][:500])

# Search
results = agent.search("lightweight browser Python")

# Login to a site (uses imported Firefox cookies)
agent.login("https://site.com", "user", "pass")

# Run pipeline
agent.pipeline("tasks/my_workflow.json")
```

**MCP Server:**
```bash
zion serve 8080  # JSON API on localhost:8080
```

## Task Pipelines

Automate multi-step workflows with JSON:

```json
{
  "name": "Check HN frontpage",
  "steps": [
    {"action": "get", "url": "https://news.ycombinator.com"},
    {"action": "extract", "selector": ".titleline > a"},
    {"action": "save", "file": "hn_titles.txt"}
  ]
}
```

```bash
zion pipe tasks/check_hn.json
```

## Security Suite (PIRATE)

```bash
pirate scan          # Full 8-layer security scan
pirate monitor       # Real-time file/process monitoring
pirate harden        # Auto-harden your system
pirate status        # Security dashboard
```

Detects: rootkits, malware signatures, suspicious processes, open ports, SUID abuse, SSH misconfig, data exfiltration attempts, and more.

## Mobile (PWA)

Free mobile web app: https://elromevedelelyon.github.io/zion-android/

## Support the Project

ZionBrowser is **free and open source**. If it helps you, consider supporting:

- **PayPal**: [paypal.me/PadraoBitcoin](https://www.paypal.com/paypalme/PadraoBitcoin)
- **Stripe**: [One-time donation](https://buy.stripe.com/dRm9AS0Vu3hegERaLb0x20j)
- **Bitcoin**: `bc1qdj3flkqe7v3qwlfux5d5u3rja7ldm9gwywk9t2`
- **Ethereum**: `0x6b45b26e1d59A832FE8c9E7c685C36Ea54A3F88B`
- **Solana**: `CM42ofAFowySg72GjDuCchEkwwbwnhdSRYgztRCAAEzR`
- **PIX (Brazil)**: `standardbitcoin.io@gmail.com`

## License

MIT License — Free to use, modify, and distribute.

## Author

**Padrao Bitcoin Atividades de Internet LTDA**
CNPJ: 51.148.891/0001-69 | Sao Paulo, Brazil
Contact: standardbitcoin.io@gmail.com

---

*Built with faith. In the name of the Lord Jesus Christ.*
