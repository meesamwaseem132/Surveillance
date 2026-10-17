import threading
import time

import cv2


class VideoStream:
    """Reads the MJPEG stream in the background and reconnects automatically."""

    def __init__(self, url):
        self.url = url
        self.frame = None
        self.online = False
        self.attempts = 0      # Failed connection attempts since the last success
        self.retry_in = 0      # Seconds until the next attempt (for the UI countdown)
        self._running = True
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        while self._running:
            self.attempts += 1
            cap = cv2.VideoCapture(self.url)

            if not cap.isOpened():
                cap.release()
                self._wait(3)
                continue

            # Connected
            self.attempts = 0
            self.online = True
            while self._running:
                ok, frame = cap.read()
                if not ok:
                    break
                self.frame = frame

            # Stream dropped
            self.online = False
            cap.release()
            self._wait(2)

    def _wait(self, seconds):
        for s in range(seconds, 0, -1):
            if not self._running:
                return
            self.retry_in = s
            time.sleep(1)
        self.retry_in = 0

    def stop(self):
        self._running = False