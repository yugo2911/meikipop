# src/screenshot/screenmanager.py
import logging
import os
import subprocess
import tempfile
import threading
import time

import mss
from PIL import Image

from src.config.config import config
from src.gui.input import _is_wayland
from src.gui.region_selector import RegionSelector

logger = logging.getLogger(__name__) # Get the logger

# todo doesnt work when monitors change
class ScreenManager(threading.Thread):
    def __init__(self, shared_state, input_loop):
        super().__init__(daemon=True, name="ScreenManager")
        self.shared_state = shared_state
        self.monitor = None
        self.last_ocr_put_time = 0.0
        self.last_screenshot = None
        self.last_mouse_pos = None
        self.input_loop = input_loop
        if config.scan_region == "region":
            self.set_scan_region()
        else:
            try:
                screen_idx = int(config.scan_region)
                self.set_scan_screen(screen_idx)
            except (ValueError, IndexError):
                logger.warning(f"Invalid screen '{config.scan_region}' in config, defaulting to screen 1.")
                self.set_scan_screen(1)

    def run(self):
        logger.debug("Screenshot thread started.")
        while self.shared_state.running:
            try:
                if config.auto_scan_mode and not config.is_enabled:
                    logger.debug(f"paused while auto mode")
                    self._sleep_and_handle_loop_exit(1)
                    continue
                self.shared_state.screenshot_trigger_event.wait()
                self.shared_state.screenshot_trigger_event.clear()
                if not self.shared_state.running: break
                logger.debug("Screenshot: Triggered!")

                # prevent multiple ocr runs during auto_scan_interval_seconds
                seconds_since_last_ocr = time.perf_counter() - self.last_ocr_put_time
                if config.auto_scan_mode and seconds_since_last_ocr < config.auto_scan_interval_seconds:
                    logger.debug(
                        f"...{seconds_since_last_ocr:.2f}s since last ocr, sleeping for another {config.auto_scan_interval_seconds - seconds_since_last_ocr:.2f}s")
                    self._sleep_and_handle_loop_exit(config.auto_scan_interval_seconds - seconds_since_last_ocr)
                    continue

                # prevent ocr runs without mouse movements for auto-on-mouse-move mode
                if config.auto_scan_mode and config.auto_scan_on_mouse_move and self.last_mouse_pos == self.input_loop.get_mouse_pos():
                    continue
                self.last_mouse_pos = self.input_loop.get_mouse_pos()

                logger.debug("screenmanager acquiring lock...")
                with self.shared_state.screen_lock:
                    logger.debug("...successfully acquired lock by screenmanager")
                    start_time = time.perf_counter()
                    screenshot = self.take_screenshot()
                logger.debug("...successfully released lock by screenmanager")
                processing_duration = time.perf_counter() - start_time
                logger.debug(f"Screenshot {screenshot.size} complete in {processing_duration:.2f}s")

                if not isinstance(screenshot, Image.Image):
                    if self.last_screenshot and self.last_screenshot.raw == screenshot.raw:
                        logger.debug(f"Screen content didnt change... skipping ocr")
                        self._sleep_and_handle_loop_exit(0.1)
                        continue

                self.last_screenshot = screenshot
                self.last_mouse_pos = self.input_loop.get_mouse_pos()
                img = screenshot if isinstance(screenshot, Image.Image) else Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
                self.shared_state.ocr_queue.put(img)
                self.last_ocr_put_time = time.perf_counter()
            except:
                logger.exception("An unexpected error occurred in the screenshot loop. Continuing...")
                self._sleep_and_handle_loop_exit(1)
        logger.debug("Screenshot thread stopped.")

    def take_screenshot(self):
        if _is_wayland():
            m = self.monitor
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
                tmp_path = f.name
            try:
                # Hyprland / wlroots: grim
                region = f"{m['left']},{m['top']} {m['width']}x{m['height']}"
                subprocess.run(['grim', '-g', region, tmp_path], check=True, stderr=subprocess.DEVNULL)
            except (FileNotFoundError, subprocess.CalledProcessError):
                try:
                    # KDE 5.25+ / KWin: ScreenShot2 DBus interface (no extra deps)
                    subprocess.run([
                        'dbus-send', '--session', '--print-reply=literal',
                        '--dest=org.kde.KWin.ScreenShot2',
                        '/org/kde/KWin/ScreenShot2',
                        'org.kde.KWin.ScreenShot2.CaptureArea',
                        f'int32:{m["left"]}', f'int32:{m["top"]}',
                        f'int32:{m["width"]}', f'int32:{m["height"]}',
                        'uint32:0',
                        f'string:{tmp_path}'
                    ], check=True, stderr=subprocess.DEVNULL)
                except (FileNotFoundError, subprocess.CalledProcessError):
                    # KDE fallback: spectacle
                    subprocess.run(
                        ['spectacle', '-b', '-n', '-o', tmp_path],
                        check=True, stderr=subprocess.DEVNULL
                    )
            img = Image.open(tmp_path)
            img.load()
            os.unlink(tmp_path)
            return img
        else:
            with mss.mss() as sct:
                sct_img = sct.grab(self.monitor)
                return sct_img

    def set_scan_region(self):
        scan_rect = RegionSelector.get_region()
        if scan_rect:
            logger.info(f"Set scan area to region {scan_rect}")
            self.monitor = {"top": scan_rect.y(), "left": scan_rect.x(), "width": scan_rect.width(),
                            "height": scan_rect.height()}
            return True
        else:
            logger.info("Region selection cancelled.")
            return False

    def set_scan_screen(self, screen_index):
        logger.info(f"Set scan area to screen {screen_index}")
        with mss.mss() as sct:
            if screen_index < len(sct.monitors):
                logger.info(f"Set scan area to screen {screen_index}")
                self.monitor = sct.monitors[screen_index]
            else:
                logger.error(f"Cannot set scan screen: index {screen_index} is out of bounds.")

    def get_scan_geometry(self):
        if not self.monitor:
            return 0, 0, 0, 0
        return self.monitor["left"], self.monitor["top"], self.monitor["width"], self.monitor["height"]

    def force_screenshot_trigger(self):
        self.last_screenshot = None
        self.last_mouse_pos = None

    def _sleep_and_handle_loop_exit(self, interval):
        if config.auto_scan_mode:
            time.sleep(interval)
            self.shared_state.screenshot_trigger_event.set()
        else:
            self.shared_state.hit_scan_queue.put((False, None))

    @staticmethod
    def get_screens():
        with mss.mss() as sct:
            return sct.monitors