ESP_IP = "192.168.0.101"
CTRL_URL = f"http://{ESP_IP}:80"
STREAM_URL = f"http://{ESP_IP}:81/stream"

OBSTACLE_CM = 20          # Matches the Arduino threshold
MAX_DISTANCE_CM = 100     # Full scale for the distance bar