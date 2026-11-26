"""Check every icon in src/config_ui/static/permanent_buffs.json loads from Valve's CDN.

Builds each URL the way app.js does (CDN + abilities/ | items/ | heroes/ + name + .png) and
fails on anything that is not a 200 image. The CDN answers a missing image with a 404 HTML
page, which the editor shows as a broken icon (Firefox logs it as OpaqueResponseBlocking);
the editor has no fallback, and dotaconstants lists abilities the CDN has no image for
(Silencer's innate silencer_brain_drain), so the catalog cache alone does not prove an icon.

    uv run python tools/check_buff_icons.py
"""
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUFFS = ROOT / "src/config_ui/static/permanent_buffs.json"
APP_JS = ROOT / "src/config_ui/static/app.js"
FOLDERS = {"ability": "abilities", "item": "items", "hero": "heroes"}


def cdn() -> str:
    """The CDN base from app.js, so this check can't drift from what the editor loads."""
    m = re.search(r'^const CDN = "([^"]+)";', APP_JS.read_text(encoding="utf-8"), re.M)
    if not m:
        sys.exit(f"could not find `const CDN = \"...\"` in {APP_JS}")
    return m.group(1)


def url_for(base: str, icon: str) -> str:
    src, name = icon.split(":", 1) if ":" in icon else ("ability", icon)  # as buffIcon in app.js
    if src not in FOLDERS:
        raise ValueError(f"unknown icon source {src!r} (use ability:, item: or hero:)")
    return f"{base}{FOLDERS[src]}/{name}.png"


def check(url: str) -> str | None:
    """None if the URL serves an image, else what went wrong."""
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "soundbo-icon-check"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            ctype = resp.headers.get("Content-Type", "")
            return None if ctype.startswith("image/") else f"200 but {ctype or 'no content type'}"
    except urllib.error.HTTPError as e:
        return f"HTTP {e.code}"
    except OSError as e:
        return f"request failed: {e}"


def main() -> int:
    base = cdn()
    bad = 0
    for buff in json.loads(BUFFS.read_text(encoding="utf-8")):
        try:
            url = url_for(base, buff["icon"])
        except ValueError as e:
            problem, url = str(e), ""
        else:
            problem = check(url)
        print(f"{'FAIL' if problem else 'ok  '}  {buff['key']}  {buff['icon']}" + (f"  -> {problem}  {url}" if problem else ""))
        bad += bool(problem)
    print(f"\n{bad} broken icon(s)" if bad else "\nall icons load")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
