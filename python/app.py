import time
import tkinter as tk

import customtkinter as ctk
import cv2
from PIL import Image

from car import Car
from camera import VideoStream
from config import STREAM_URL, OBSTACLE_CM, MAX_DISTANCE_CM

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

DRIVE_KEYS = {"w": "F", "s": "B", "a": "L", "d": "R"}
CMD_NAMES = {"F": "Forward", "B": "Backward", "L": "Left", "R": "Right",
             "S": "Stop", "H": "Horn"}


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Surveillance Car Console")
        self.geometry("1150x680")
        self.minsize(950, 600)

        self.car = Car()
        self.video = VideoStream(STREAM_URL)
        self.held_keys = set()
        self._last_frame = None
        self._ctk_img = None
        self._was_online = None

        self._build_ui()
        self._bind_keys()

        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(33, self._update_video)
        self.after(200, self._update_status)
        self._log("Console started")

    # ---------- Layout ----------
    def _build_ui(self):
        self.grid_columnconfigure(0, weight=3)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Video panel
        video_frame = ctk.CTkFrame(self, corner_radius=12)
        video_frame.grid(row=0, column=0, sticky="nsew", padx=(16, 8), pady=16)
        video_frame.grid_rowconfigure(0, weight=1)
        video_frame.grid_columnconfigure(0, weight=1)

        self.video_label = ctk.CTkLabel(video_frame, text="Connecting to camera...",
                                        font=ctk.CTkFont(size=16))
        self.video_label.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)

        # Side panel
        side = ctk.CTkFrame(self, corner_radius=12)
        side.grid(row=0, column=1, sticky="nsew", padx=(8, 16), pady=16)
        side.grid_columnconfigure(0, weight=1)
        side.grid_rowconfigure(6, weight=1)

        title = ctk.CTkLabel(side, text="CAR CONTROL", font=ctk.CTkFont(size=18, weight="bold"))
        title.grid(row=0, column=0, pady=(16, 4))

        self.conn_label = ctk.CTkLabel(side, text="● Car: offline", text_color="red")
        self.conn_label.grid(row=1, column=0, pady=2)
        self.cam_label = ctk.CTkLabel(side, text="● Camera: offline", text_color="red")
        self.cam_label.grid(row=2, column=0, pady=2)

        # Distance gauge
        dist_frame = ctk.CTkFrame(side, fg_color="transparent")
        dist_frame.grid(row=3, column=0, pady=(10, 4), padx=16, sticky="ew")
        dist_frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(dist_frame, text="Obstacle distance").grid(row=0, column=0, sticky="w")
        self.dist_value = ctk.CTkLabel(dist_frame, text="-- cm",
                                       font=ctk.CTkFont(size=22, weight="bold"))
        self.dist_value.grid(row=1, column=0, sticky="w")
        self.dist_bar = ctk.CTkProgressBar(dist_frame)
        self.dist_bar.grid(row=2, column=0, sticky="ew", pady=(4, 0))
        self.dist_bar.set(0)

        # Direction pad
        pad = ctk.CTkFrame(side, fg_color="transparent")
        pad.grid(row=4, column=0, pady=10)
        self._drive_button(pad, "▲", "F", 0, 1)
        self._drive_button(pad, "◀", "L", 1, 0)
        stop = ctk.CTkButton(pad, text="STOP", width=64, height=56,
                             fg_color="#B22222", hover_color="#8B1A1A",
                             command=lambda: self.drive("S"))
        stop.grid(row=1, column=1, padx=4, pady=4)
        self._drive_button(pad, "▶", "R", 1, 2)
        self._drive_button(pad, "▼", "B", 2, 1)

        # Speed and horn
        controls = ctk.CTkFrame(side, fg_color="transparent")
        controls.grid(row=5, column=0, padx=16, pady=6, sticky="ew")
        controls.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(controls, text="Speed").grid(row=0, column=0, sticky="w")
        self.speed_var = ctk.StringVar(value=str(self.car.speed))
        ctk.CTkSegmentedButton(controls, values=["1", "2", "3"], variable=self.speed_var,
                               command=self._on_speed).grid(row=1, column=0, sticky="ew", pady=(2, 8))
        ctk.CTkButton(controls, text="HORN", height=36,
                      fg_color="#B8860B", hover_color="#8B6508",
                      command=self.horn).grid(row=2, column=0, sticky="ew")

        # Log
        self.log_box = ctk.CTkTextbox(side, height=130, state="disabled")
        self.log_box.grid(row=6, column=0, padx=16, pady=(6, 16), sticky="nsew")

    def _drive_button(self, parent, text, cmd, row, col):
        btn = ctk.CTkButton(parent, text=text, width=64, height=56,
                            font=ctk.CTkFont(size=20))
        btn.grid(row=row, column=col, padx=4, pady=4)
        # Hold to drive, release to stop
        btn.bind("<ButtonPress-1>", lambda e: self.drive(cmd))
        btn.bind("<ButtonRelease-1>", lambda e: self.drive("S"))
        return btn

    # ---------- Keyboard ----------
    def _bind_keys(self):
        self.bind("<KeyPress>", self._on_key_press)
        self.bind("<KeyRelease>", self._on_key_release)

    def _on_key_press(self, event):
        key = event.keysym.lower()
        if key in self.held_keys:
            return  # Ignore auto-repeat
        self.held_keys.add(key)

        if key in DRIVE_KEYS:
            self.drive(DRIVE_KEYS[key])
        elif key == "space":
            self.drive("S")
        elif key == "h":
            self.horn()
        elif key in ("1", "2", "3"):
            self.speed_var.set(key)
            self._on_speed(key)

    def _on_key_release(self, event):
        key = event.keysym.lower()
        self.held_keys.discard(key)
        if key in DRIVE_KEYS:
            # If another drive key is still held, keep driving that way
            remaining = [DRIVE_KEYS[k] for k in DRIVE_KEYS if k in self.held_keys]
            self.drive(remaining[-1] if remaining else "S")

    # ---------- Actions ----------
    def drive(self, cmd):
        if cmd != self.car.cmd:
            self._log(CMD_NAMES[cmd])
        self.car.drive(cmd)

    def horn(self):
        self.car.horn()
        self._log("Horn")

    def _on_speed(self, value):
        self.car.set_speed(int(value))
        self._log(f"Speed set to {value}")

    # ---------- Periodic updates ----------
    def _update_video(self):
        frame = self.video.frame
        if frame is not None and frame is not self._last_frame:
            self._last_frame = frame
            w, h = self.video_label.winfo_width(), self.video_label.winfo_height()
            if w > 50 and h > 50:
                img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                img = self._fit(img, w - 16, h - 16)
                self._ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=img.size)
                self.video_label.configure(image=self._ctk_img, text="")
        self.after(33, self._update_video)

    def _update_status(self):
        online = self.car.connected
        if online != self._was_online:
            self._log("Car connected" if online else "Car connection lost")
            self._was_online = online
        self.conn_label.configure(text=f"● Car: {'online' if online else 'offline'}",
                                  text_color="green" if online else "red")
        self.cam_label.configure(text=f"● Camera: {'online' if self.video.online else 'offline'}",
                                 text_color="green" if self.video.online else "red")

        d = self.car.distance
        if d is None:
            self.dist_value.configure(text="-- cm", text_color=("gray10", "gray90"))
            self.dist_bar.set(0)
        else:
            color = "red" if d < OBSTACLE_CM else "green"
            self.dist_value.configure(text=f"{d} cm", text_color=color)
            self.dist_bar.configure(progress_color=color)
            self.dist_bar.set(min(d, MAX_DISTANCE_CM) / MAX_DISTANCE_CM)

        self.after(200, self._update_status)

    # ---------- Helpers ----------
    @staticmethod
    def _fit(img, max_w, max_h):
        ratio = min(max_w / img.width, max_h / img.height)
        return img.resize((max(1, int(img.width * ratio)), max(1, int(img.height * ratio))),
                          Image.LANCZOS)

    def _log(self, msg):
        stamp = time.strftime("%H:%M:%S")
        self.log_box.configure(state="normal")
        self.log_box.insert("end", f"[{stamp}] {msg}\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def on_close(self):
        self.car.close()
        self.video.stop()
        self.destroy()


if __name__ == "__main__":
    App().mainloop()