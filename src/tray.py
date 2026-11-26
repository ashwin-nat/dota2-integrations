"""The packaged app's presence: a menu bar icon on macOS (plus its Dock icon), a tray icon on Windows.

The app has no window of its own; the editor runs in the browser. The icon is how people
reopen the editor and quit. It must run on the main thread (macOS requires it), so the
asyncio app runs in a background thread while this runs the platform's event loop.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

from src import osutil

logger = logging.getLogger(__name__)

ICON_PATH = Path(__file__).parent / "config_ui" / "static" / "icon.png"


def _image():
    from PIL import Image

    return Image.open(ICON_PATH).resize((64, 64), Image.LANCZOS)


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
            "soundbo", _image(), "Soundbo",
            menu=pystray.Menu(
                pystray.MenuItem("Open Soundbo", lambda *_: open_editor(), default=True),
                pystray.MenuItem("Quit", lambda *_: quit_app()),
            ),
        )
    except Exception as e:
        logger.warning(f"No tray icon: {e}")
        return None
    if osutil.IS_MACOS:
        try:
            _reopen_from_dock(open_editor)
        except Exception as e:
            logger.warning(f"Dock icon won't reopen the editor: {e}")
    return icon
