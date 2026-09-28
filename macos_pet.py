"""Native macOS window backend for Tuantuan.

PyObjC renders the PNG frames in a transparent NSWindow, bypassing Tk's
inconsistent macOS transparency implementation.
"""

from __future__ import annotations

import time
import signal
from pathlib import Path

import objc
from AppKit import (
    NSApp,
    NSApplication,
    NSApplicationActivationPolicyAccessory,
    NSBackingStoreBuffered,
    NSColor,
    NSEvent,
    NSFloatingWindowLevel,
    NSImage,
    NSImageScaleNone,
    NSImageView,
    NSMakeRect,
    NSMakePoint,
    NSScreen,
    NSWindow,
    NSWindowCollectionBehaviorCanJoinAllSpaces,
    NSWindowCollectionBehaviorFullScreenAuxiliary,
    NSWindowStyleMaskBorderless,
)
from Foundation import NSObject, NSTimer

WIDTH = 192
HEIGHT = 208
FRAME_COUNTS = {"idle": 6, "failed": 8}


class PetImageView(NSImageView):
    def mouseDown_(self, event: object) -> None:
        self.drag_offset = event.locationInWindow()

    def mouseDragged_(self, _event: object) -> None:
        point = NSEvent.mouseLocation()
        self.window().setFrameOrigin_(
            NSMakePoint(point.x - self.drag_offset.x, point.y - self.drag_offset.y)
        )

    def rightMouseDown_(self, _event: object) -> None:
        NSApp.terminate_(None)


class PetDelegate(NSObject):
    def init(self) -> "PetDelegate":
        self = objc.super(PetDelegate, self).init()
        if self is not None:
            self.started_at = time.monotonic()
            self.frame_index = 0
        return self

    def applicationDidFinishLaunching_(self, _notification: object) -> None:
        self.frames = self._load_frames()
        visible = NSScreen.mainScreen().visibleFrame()
        frame = NSMakeRect(
            visible.origin.x + visible.size.width - WIDTH - 24,
            visible.origin.y + 24,
            WIDTH,
            HEIGHT,
        )
        self.window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            frame, NSWindowStyleMaskBorderless, NSBackingStoreBuffered, False
        )
        self.window.setOpaque_(False)
        self.window.setBackgroundColor_(NSColor.clearColor())
        self.window.setHasShadow_(False)
        self.window.setLevel_(NSFloatingWindowLevel)
        self.window.setCollectionBehavior_(
            NSWindowCollectionBehaviorCanJoinAllSpaces
            | NSWindowCollectionBehaviorFullScreenAuxiliary
        )
        self.view = PetImageView.alloc().initWithFrame_(
            NSMakeRect(0, 0, WIDTH, HEIGHT)
        )
        self.view.setImageScaling_(NSImageScaleNone)
        self.window.setContentView_(self.view)
        self._show_frame()
        self.window.orderFrontRegardless()
        self.timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            5.0, self, "tick:", None, True
        )

    def _load_frames(self) -> dict[str, list[NSImage]]:
        assets = Path(__file__).with_name("assets")
        frames: dict[str, list[NSImage]] = {}
        for state, count in FRAME_COUNTS.items():
            frames[state] = []
            for index in range(count):
                image = NSImage.alloc().initWithContentsOfFile_(
                    str(assets / state / f"{index:02}.png")
                )
                if image is None:
                    raise FileNotFoundError(f"Missing {state} frame {index:02}")
                frames[state].append(image)
        return frames

    def tick_(self, _timer: object) -> None:
        self.frame_index += 1
        self._show_frame()

    def _show_frame(self) -> None:
        state = "failed" if (time.monotonic() - self.started_at) % 360 >= 60 else "idle"
        self.view.setImage_(self.frames[state][self.frame_index % len(self.frames[state])])


def run() -> None:
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
    signal.signal(signal.SIGINT, lambda _signum, _frame: app.terminate_(None))
    delegate = PetDelegate.alloc().init()
    app.setDelegate_(delegate)
    app.run()
