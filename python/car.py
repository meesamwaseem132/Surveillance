import queue
import threading
import time

import requests

from config import CTRL_URL

MOVE_CMDS = ("F", "B", "L", "R")
FAIL_LIMIT = 3          # Failed status checks in a row before reporting the car offline


class Car:
    """Sends commands and reads status. Reconnects automatically and stops on link loss."""

    def __init__(self):
        self.cmd = "S"
        self.speed = 2
        self.distance = None
        self.connected = False
        self.attempts = 0       # Reconnect attempts since the link was lost

        self._fails = 0
        self._session = requests.Session()
        self._queue = queue.Queue(maxsize=50)
        self._running = True

        threading.Thread(target=self._worker, daemon=True).start()
        threading.Thread(target=self._heartbeat, daemon=True).start()
        threading.Thread(target=self._poll_status, daemon=True).start()

    # ----- Commands -----
    def _enqueue(self, **params):
        # Don't send movement while the car is unreachable, or old commands
        # would run as soon as the link came back.
        if not self.connected and params.get("c") in MOVE_CMDS:
            return
        try:
            self._queue.put_nowait(params)
        except queue.Full:
            pass

    def drive(self, cmd):
        self.cmd = cmd
        self._enqueue(c=cmd)

    def set_speed(self, level):
        self.speed = level
        self._enqueue(c=str(level))

    def horn(self):
        self._enqueue(c="H")

    # ----- Background threads -----
    def _worker(self):
        while self._running:
            params = self._queue.get()
            try:
                self._session.get(f"{CTRL_URL}/cmd", params=params, timeout=0.5)
            except requests.RequestException:
                pass

    def _heartbeat(self):
        # The ESP32 stops the car after 1.5 s of silence, so repeat movement commands
        while self._running:
            if self.cmd != "S":
                self._enqueue(c=self.cmd)
            time.sleep(0.5)

    def _poll_status(self):
        while self._running:
            try:
                data = self._session.get(f"{CTRL_URL}/status", timeout=0.5).json()
                self._fails = 0
                self.attempts = 0

                if not self.connected:
                    # Link just came back: start stopped for safety
                    self.connected = True
                    self.cmd = "S"
                    self._enqueue(c="S")

                self.distance = data["distance"] if data["distance"] >= 0 else None
                self.speed = data["speed"]

            except (requests.RequestException, ValueError, KeyError):
                self._fails += 1
                if self.connected and self._fails >= FAIL_LIMIT:
                    self.connected = False
                    self.cmd = "S"
                if not self.connected:
                    self.attempts += 1

            time.sleep(0.3 if self.connected else 1.0)

    def close(self):
        self._running = False
        self.cmd = "S"
        try:
            self._session.get(f"{CTRL_URL}/cmd", params={"c": "S"}, timeout=0.5)
        except requests.RequestException:
            pass