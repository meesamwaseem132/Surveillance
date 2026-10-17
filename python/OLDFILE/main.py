"""
Surveillance car console
- Live video from the ESP32-CAM
- Drive controls (on-screen buttons or keyboard)
- Obstacle distance display

Keys:  W forward | S back | A left | D right | SPACE stop
       H horn    | 1/2/3 speed | Q quit
"""
import threading
import time

import cv2
import numpy as np
import requests

ESP_IP = "192.168.0.101"               # <-- replace with the IP from the Serial Monitor
CTRL_URL = f"http://{ESP_IP}:80"
STREAM_URL = f"http://{ESP_IP}:81/stream"

W, H = 640, 480
PANEL_H = 100
WINDOW = "Surveillance Car"

# ---------- Video ----------
class Camera:
    def __init__(self, url):
        self.url = url
        self.cap = cv2.VideoCapture(url)
        self.frame = None
        self.running = True
        threading.Thread(target=self._reader, daemon=True).start()

    def _reader(self):
        while self.running:
            ok, frame = self.cap.read()
            if ok:
                self.frame = cv2.resize(frame, (W, H))
            else:
                # Stream dropped: reconnect
                time.sleep(0.5)
                self.cap.release()
                self.cap = cv2.VideoCapture(self.url)


# ---------- Car link ----------
class Car:
    def __init__(self):
        self.cmd = "S"
        self.speed = 2
        self.distance = None
        self.session = requests.Session()
        threading.Thread(target=self._heartbeat, daemon=True).start()
        threading.Thread(target=self._poll_status, daemon=True).start()

    def _send(self, **params):
        try:
            self.session.get(f"{CTRL_URL}/cmd", params=params, timeout=0.5)
        except requests.RequestException:
            pass

    def drive(self, c):
        self.cmd = c
        self._send(c=c)

    def set_speed(self, level):
        self.speed = level
        self._send(c=str(level))

    def horn(self):
        self._send(c="H")

    def _heartbeat(self):
        # The ESP32 stops the car if it hears nothing for 1.5 s,
        # so keep re-sending the active movement command.
        while True:
            if self.cmd != "S":
                self._send(c=self.cmd)
            time.sleep(0.5)

    def _poll_status(self):
        while True:
            try:
                data = self.session.get(f"{CTRL_URL}/status", timeout=0.5).json()
                self.distance = data["distance"] if data["distance"] >= 0 else None
                self.speed = data["speed"]
            except (requests.RequestException, ValueError, KeyError):
                pass
            time.sleep(0.3)

    def close(self):
        self.drive("S")


# ---------- UI ----------
KEYS = {
    ord("w"): "F", ord("s"): "B", ord("a"): "L", ord("d"): "R",
    ord(" "): "S", ord("h"): "H",
}

BUTTONS = [("FWD", "F"), ("LEFT", "L"), ("STOP", "S"),
           ("RIGHT", "R"), ("BACK", "B"), ("HORN", "H")]
BTN_W, BTN_H, GAP = 95, 70, 8
button_rects = []
for i, (label, cmd) in enumerate(BUTTONS):
    x1 = 15 + i * (BTN_W + GAP)
    y1 = H + 15
    button_rects.append((label, cmd, x1, y1, x1 + BTN_W, y1 + BTN_H))

car = None


def action(cmd):
    if cmd in ("F", "B", "L", "R", "S"):
        car.drive(cmd)
    elif cmd == "H":
        car.horn()
    elif cmd in ("1", "2", "3"):
        car.set_speed(int(cmd))


def on_mouse(event, x, y, flags, param):
    if event != cv2.EVENT_LBUTTONDOWN:
        return
    for _, cmd, x1, y1, x2, y2 in button_rects:
        if x1 <= x <= x2 and y1 <= y <= y2:
            action(cmd)


def main():
    global car
    car = Car()
    cam = Camera(STREAM_URL)

    cv2.namedWindow(WINDOW)
    cv2.setMouseCallback(WINDOW, on_mouse)
    font = cv2.FONT_HERSHEY_SIMPLEX

    try:
        while True:
            canvas = np.full((H + PANEL_H, W, 3), 30, np.uint8)

            if cam.frame is not None:
                canvas[:H] = cam.frame
            else:
                cv2.putText(canvas, "Connecting to camera...",
                            (160, H // 2), font, 0.9, (0, 200, 255), 2)

            # Status overlay
            dist_txt = (f"Distance: {car.distance} cm"
                        if car.distance is not None else "Distance: --")
            cv2.putText(canvas, dist_txt, (10, 30), font, 0.8, (0, 255, 0), 2)
            cv2.putText(canvas, f"Cmd: {car.cmd}   Speed: {car.speed}",
                        (10, 60), font, 0.8, (255, 255, 255), 2)

            # Control buttons
            for label, cmd, x1, y1, x2, y2 in button_rects:
                color = (0, 160, 0) if cmd == car.cmd else (70, 70, 70)
                cv2.rectangle(canvas, (x1, y1), (x2, y2), color, -1)
                cv2.putText(canvas, label, (x1 + 10, y1 + 45),
                            font, 0.7, (255, 255, 255), 2)

            cv2.imshow(WINDOW, canvas)

            key = cv2.waitKey(30) & 0xFF
            if key == ord("q"):
                break
            if 0 <= key < 128:
                key = ord(chr(key).lower())
            if key in KEYS:
                action(KEYS[key])
            elif key in (ord("1"), ord("2"), ord("3")):
                action(chr(key))
    finally:
        car.close()
        cam.running = False
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()