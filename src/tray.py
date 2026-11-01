"""The packaged app's presence: a menu bar icon on macOS (plus its Dock icon), a tray icon on Windows.

The app has no window of its own; the editor runs in the browser. The icon is how people
reopen the editor and quit. It must run on the main thread (macOS requires it), so the
asyncio app runs in a background thread while this runs the platform's event loop.
"""
from __future__ import annotations

import logging
import sys
from typing import Callable

logger = logging.getLogger(__name__)


def _image():
    from PIL import Image, ImageDraw

    # A gold diamond like the editor's logo
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.polygon([(32, 4), (60, 32), (32, 60), (4, 32)], fill=(201, 166, 90, 255), outline=(255, 226, 150, 255))
    d.polygon([(32, 20), (44, 32), (32, 44), (20, 32)], fill=(120, 40, 30, 255))
    return img


def _reopen_from_dock(open_editor: Callable[[], None]) -> None:
    """Clicking the app's Dock icon opens the editor, like reopening any Mac app."""
    import AppKit
    import Foundation
    import objc

    class Delegate(Foundation.NSObject):
        def applicationShouldHandleReopen_hasVisibleWindows_(self, app, has_windows):
            open_editor()
            return True

    delegate = Delegate.alloc().init()
    AppKit.NSApplication.sharedApplication().setDelegate_(delegate)
    _reopen_from_dock.delegate = delegate  # type: ignore[attr-defined]  # keep it alive
    objc  # noqa: B018  (imported so PyInstaller bundles it)


def make_icon(open_editor: Callable[[], None], quit_app: Callable[[], None]):
    """The tray icon, ready for icon.run() on the main thread; None if this system can't show one."""
    try:
        import pystray

        icon = pystray.Icon(
            "rule-forge", _image(), "Rule Forge",
            menu=pystray.Menu(
                pystray.MenuItem("Open Rule Forge", lambda *_: open_editor(), default=True),
                pystray.MenuItem("Quit", lambda *_: quit_app()),
            ),
        )
    except Exception as e:
        logger.warning(f"No tray icon: {e}")
        return None
    if sys.platform == "darwin":
        try:
            _reopen_from_dock(open_editor)
        except Exception as e:
            logger.warning(f"Dock icon won't reopen the editor: {e}")
    return icon
