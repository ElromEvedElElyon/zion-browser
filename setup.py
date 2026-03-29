#!/usr/bin/env python3
"""Setup script for ZionBrowser — pip installable."""
from pathlib import Path

# Simple setup without setuptools dependency
def install():
    """Install ZionBrowser to ~/.local/bin for easy access."""
    src = Path(__file__).parent / "zion_browser.py"
    dest = Path.home() / ".local" / "bin" / "zion"

    dest.parent.mkdir(parents=True, exist_ok=True)

    # Create wrapper script
    wrapper = f"""#!/bin/bash
python3 {src.resolve()} "$@"
"""
    dest.write_text(wrapper)
    dest.chmod(0o755)

    # Also create data directories
    (Path.home() / ".zion").mkdir(exist_ok=True)
    (Path.home() / ".zion" / "cache").mkdir(exist_ok=True)

    print(f"ZionBrowser installed to {dest}")
    print(f"Usage: zion get https://example.com")
    print(f"       zion interactive")
    print(f"       zion login https://hackenproof.com user pass")


if __name__ == "__main__":
    install()
