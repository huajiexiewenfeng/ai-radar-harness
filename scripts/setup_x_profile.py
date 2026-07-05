from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".vendor"))
sys.path.insert(0, str(ROOT / "lib"))

from ai_radar.collectors import _launch_chromium_context
from ai_radar.config import load_run_config


def main() -> int:
    parser = argparse.ArgumentParser(description="Open a persistent Chrome profile for X login.")
    parser.add_argument("--profile-dir", default=None, help="Profile directory relative to ai-radar root, or absolute.")
    parser.add_argument("--url", default="https://x.com/home")
    args = parser.parse_args()

    config = load_run_config(ROOT / "harness" / "run-config.yaml")
    x_config = dict(config.get("x", {}))
    profile_dir = Path(args.profile_dir or x_config.get("profile_dir", ".browser-profile"))
    if not profile_dir.is_absolute():
        profile_dir = ROOT / profile_dir
    profile_dir.mkdir(parents=True, exist_ok=True)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright is not installed. Run: python -m pip install --target ai-radar/.vendor playwright")
        return 2

    print(f"Opening Chrome with profile: {profile_dir}")
    print("Log in to X in the opened window, then press Enter here after the X home page is loaded.")
    with sync_playwright() as playwright:
        context = _launch_chromium_context(playwright, profile_dir, x_config, headless=False)
        page = context.new_page()
        page.goto(args.url, wait_until="domcontentloaded", timeout=120000)
        input("Press Enter after login is complete...")
        context.close()
    print(f"Saved X browser profile: {profile_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
