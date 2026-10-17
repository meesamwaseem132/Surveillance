import threading
import time

import cv2


class VideoStream:
    """Reads the MJPEG stream in the background and keeps the latest frame."""

    def __init__(self, url):
        self.url = url
        self.frame = None
        self.online = False
        self._running = True
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        cap = cv2.VideoCapture(self.url)
        while self._running:
            ok, frame = cap.read()
            if ok:
                self.frame = frame
                self.online = True
            else:
                self.online = False
                cap.release()
                time.sleep(1)
                cap = cv2.VideoCapture(self.url)
        cap.release()

    def stop(self):
        self._running = False