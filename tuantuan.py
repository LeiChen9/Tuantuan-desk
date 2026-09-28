"""A dependency-light, cross-platform desktop pet for Tuantuan."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import platform
import queue
import threading
import time
import tkinter as tk
from pathlib import Path

CELL_WIDTH = 192
CELL_HEIGHT = 208
MAGENTA = "#ff00ff"
FRAME_COUNTS = {0: 6, 1: 8, 2: 8, 3: 4, 4: 5, 5: 8, 6: 6, 7: 6, 8: 6}


class TuantuanApp:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.window_bg = MAGENTA
        if platform.system() == "Darwin":
            self.window_bg = "systemTransparent"

        self.frames = self._load_frames()
        self.root.configure(bg=self.window_bg)
        self.label = tk.Label(self.root, bg=self.window_bg, bd=0, highlightthickness=0)
        self.label.pack()
        if platform.system() == "Darwin":
            self.root.attributes("-transparent", True)
        else:
            self.root.attributes("-transparentcolor", MAGENTA)
        self.root.bind("<Button-3>", lambda _event: self.root.destroy())
        self.root.bind("<Escape>", lambda _event: self.root.destroy())

        self.events: queue.SimpleQueue[tuple[int, int]] = queue.SimpleQueue()
        self.x = float(self.root.winfo_screenwidth() - CELL_WIDTH - 32)
        self.y = float(self.root.winfo_screenheight() - CELL_HEIGHT - 96)
        self.target: tuple[float, float] | None = None
        self.last_tick = time.monotonic()
        self.last_frame_change = self.last_tick
        self.idle_since = self.last_tick
        self.frame_index = 0
        self.row = 0
        self.root.geometry(f"{CELL_WIDTH}x{CELL_HEIGHT}+{int(self.x)}+{int(self.y)}")
        self._show_frame()
        self.root.after(16, self._tick)

    def _load_frames(self) -> dict[int, list[tk.PhotoImage]]:
        asset = Path(__file__).with_name("assets") / "tuantuan-spritesheet.png"
        if not asset.is_file():
            raise FileNotFoundError(f"Missing sprite sheet: {asset}")
        sheet = tk.PhotoImage(file=asset)
        frames: dict[int, list[tk.PhotoImage]] = {}
        for row, count in FRAME_COUNTS.items():
            frames[row] = []
            for column in range(count):
                frame = tk.PhotoImage(width=CELL_WIDTH, height=CELL_HEIGHT)
                frame.tk.call(
                    str(frame),
                    "copy",
                    str(sheet),
                    "-from",
                    column * CELL_WIDTH,
                    row * CELL_HEIGHT,
                    (column + 1) * CELL_WIDTH,
                    (row + 1) * CELL_HEIGHT,
                )
                frames[row].append(frame)
        self.sheet = sheet  # Keep the backing image alive for Tk.
        return frames

    def _start_global_click_listener(self) -> None:
        if platform.system() == "Windows":
            threading.Thread(target=self._windows_mouse_hook, daemon=True).start()
            return
        try:
            from pynput import mouse
        except ImportError:
            return

        def on_click(x: int, y: int, button: object, pressed: bool) -> None:
            if pressed and button == mouse.Button.left:
                self.events.put((x, y))

        mouse.Listener(on_click=on_click).start()

    def _windows_mouse_hook(self) -> None:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        wh_mouse_ll, wm_lbuttondown = 14, 0x0201

        class Point(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

        class MouseInfo(ctypes.Structure):
            _fields_ = [("point", Point), ("mouse_data", ctypes.c_ulong), ("flags", ctypes.c_ulong), ("time", ctypes.c_ulong), ("extra", ctypes.c_void_p)]

        callback_type = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, ctypes.c_size_t, ctypes.c_ssize_t)

        def callback(code: int, message: int, data: int) -> int:
            if code >= 0 and message == wm_lbuttondown:
                point = ctypes.cast(data, ctypes.POINTER(MouseInfo)).contents.point
                self.events.put((point.x, point.y))
            return user32.CallNextHookEx(None, code, message, data)

        self.windows_hook_callback = callback_type(callback)
        hook = user32.SetWindowsHookExW(wh_mouse_ll, self.windows_hook_callback, kernel32.GetModuleHandleW(None), 0)
        message = wintypes.MSG()
        while hook and user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(message))
            user32.DispatchMessageW(ctypes.byref(message))
        if hook:
            user32.UnhookWindowsHookEx(hook)

    def _move_to_click(self, event: tk.Event) -> None:
        self._set_target(event.x_root, event.y_root)

    def _set_target(self, click_x: int, click_y: int) -> None:
        max_x = self.root.winfo_screenwidth() - CELL_WIDTH
        max_y = self.root.winfo_screenheight() - CELL_HEIGHT
        self.target = (
            max(0, min(max_x, click_x - CELL_WIDTH / 2)),
            max(0, min(max_y, click_y - CELL_HEIGHT / 2)),
        )

    def _tick(self) -> None:
        now = time.monotonic()
        self.last_tick = now
        self.row = 5 if now - self.idle_since >= 5 else 0
        self._animate(now)
        self.root.after(16, self._tick)

    def _move(self, delta: float) -> None:
        if self.target is None:
            self.row = 0
            return
        target_x, target_y = self.target
        dx, dy = target_x - self.x, target_y - self.y
        distance = (dx * dx + dy * dy) ** 0.5
        if distance < 3:
            self.x, self.y, self.target, self.row = target_x, target_y, None, 0
            self.root.geometry(f"+{int(self.x)}+{int(self.y)}")
            return
        speed = min(360.0, 90.0 + distance * 1.7)
        step = min(distance, speed * delta)
        self.x += dx / distance * step
        self.y += dy / distance * step
        self.row = 1 if dx >= 0 else 2
        self.root.geometry(f"+{int(self.x)}+{int(self.y)}")

    def _animate(self, now: float) -> None:
        interval = 0.20 if self.row == 0 else 0.15
        if now - self.last_frame_change < interval:
            return
        self.last_frame_change = now
        self.frame_index = (self.frame_index + 1) % len(self.frames[self.row])
        self._show_frame()

    def _show_frame(self) -> None:
        frame = self.frames[self.row][self.frame_index % len(self.frames[self.row])]
        self.label.configure(image=frame)

    def run(self) -> None:
        self.root.mainloop()


if __name__ == "__main__":
    if platform.system() == "Darwin":
        from macos_pet import run

        run()
    else:
        TuantuanApp().run()
