// ESP32-CAM: MJPEG video on port 81, drive commands on port 80,
// relays commands to Arduino over Serial2 and reads distance telemetry.

#include <WiFi.h>
#include "esp_camera.h"
#include "esp_http_server.h"
#include "secrets.h"

// AI Thinker camera pins
#define PWDN_GPIO_NUM   32
#define RESET_GPIO_NUM  -1
#define XCLK_GPIO_NUM    0
#define SIOD_GPIO_NUM   26
#define SIOC_GPIO_NUM   27
#define Y9_GPIO_NUM     35
#define Y8_GPIO_NUM     34
#define Y7_GPIO_NUM     39
#define Y6_GPIO_NUM     36
#define Y5_GPIO_NUM     21
#define Y4_GPIO_NUM     19
#define Y3_GPIO_NUM     18
#define Y2_GPIO_NUM      5
#define VSYNC_GPIO_NUM  25
#define HREF_GPIO_NUM   23
#define PCLK_GPIO_NUM   22

// UART link to Arduino Uno
#define ARDUINO_RX  14   // ESP32 receives from Uno TX (through divider)
#define ARDUINO_TX  15   // ESP32 sends to Uno RX

#define CMD_TIMEOUT_MS 1500   // stop the car if no command arrives for this long

char currentCmd = 'S';
unsigned long lastCmdMs = 0;
int speedLevel = 2;
int lastDistance = -1;
String rxLine;

// ---------- MJPEG stream ----------
#define PART_BOUNDARY "123456789000000000000987654321"
static const char* STREAM_CONTENT_TYPE = "multipart/x-mixed-replace;boundary=" PART_BOUNDARY;
static const char* STREAM_BOUNDARY     = "\r\n--" PART_BOUNDARY "\r\n";
static const char* STREAM_PART         = "Content-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n";

static esp_err_t stream_handler(httpd_req_t* req) {
  camera_fb_t* fb = NULL;
  esp_err_t res = ESP_OK;
  char partBuf[64];

  res = httpd_resp_set_type(req, STREAM_CONTENT_TYPE);
  if (res != ESP_OK) return res;
  httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");

  while (true) {
    fb = esp_camera_fb_get();
    if (!fb) { res = ESP_FAIL; break; }

    res = httpd_resp_send_chunk(req, STREAM_BOUNDARY, strlen(STREAM_BOUNDARY));
    if (res == ESP_OK) {
      size_t hlen = snprintf(partBuf, sizeof(partBuf), STREAM_PART, fb->len);
      res = httpd_resp_send_chunk(req, partBuf, hlen);
    }
    if (res == ESP_OK) res = httpd_resp_send_chunk(req, (const char*)fb->buf, fb->len);

    esp_camera_fb_return(fb);
    if (res != ESP_OK) break;
  }
  return res;
}

// ---------- Commands ----------
static esp_err_t cmd_handler(httpd_req_t* req) {
  char query[32] = {0};
  char val[8] = {0};

  if (httpd_req_get_url_query_str(req, query, sizeof(query)) == ESP_OK &&
      httpd_query_key_value(query, "c", val, sizeof(val)) == ESP_OK) {
    char c = val[0];
    if (c && strchr("FBLRS", c)) {
      currentCmd = c;
      lastCmdMs = millis();
      Serial2.write(c); Serial2.write('\n');
    } else if (c >= '1' && c <= '3') {
      speedLevel = c - '0';
      Serial2.write(c); Serial2.write('\n');
    } else if (c == 'H') {
      Serial2.write('H'); Serial2.write('\n');
    }
  }
  httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");
  return httpd_resp_send(req, "OK", 2);
}

static esp_err_t status_handler(httpd_req_t* req) {
  char buf[96];
  snprintf(buf, sizeof(buf),
           "{\"distance\":%d,\"speed\":%d,\"cmd\":\"%c\"}",
           lastDistance, speedLevel, currentCmd);
  httpd_resp_set_type(req, "application/json");
  httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");
  return httpd_resp_send(req, buf, HTTPD_RESP_USE_STRLEN);
}

void startServers() {
  // Control server on port 80
  httpd_config_t cfg = HTTPD_DEFAULT_CONFIG();
  cfg.server_port = 80;
  cfg.ctrl_port = 32768;
  httpd_handle_t ctrl = NULL;
  httpd_uri_t cmdUri    = {"/cmd",    HTTP_GET, cmd_handler,    NULL};
  httpd_uri_t statusUri = {"/status", HTTP_GET, status_handler, NULL};
  if (httpd_start(&ctrl, &cfg) == ESP_OK) {
    httpd_register_uri_handler(ctrl, &cmdUri);
    httpd_register_uri_handler(ctrl, &statusUri);
  }

  // Stream server on port 81
  cfg.server_port = 81;
  cfg.ctrl_port = 32769;
  httpd_handle_t stream = NULL;
  httpd_uri_t streamUri = {"/stream", HTTP_GET, stream_handler, NULL};
  if (httpd_start(&stream, &cfg) == ESP_OK) {
    httpd_register_uri_handler(stream, &streamUri);
  }
}

void parseTelemetry(const String& line) {
  if (line.startsWith("D:")) {
    lastDistance = line.substring(2).toInt();
  }
}

void setup() {
  Serial.begin(115200);
  Serial2.begin(9600, SERIAL_8N1, ARDUINO_RX, ARDUINO_TX);

  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer   = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk     = XCLK_GPIO_NUM;
  config.pin_pclk     = PCLK_GPIO_NUM;
  config.pin_vsync    = VSYNC_GPIO_NUM;
  config.pin_href     = HREF_GPIO_NUM;
  config.pin_sccb_sda = SIOD_GPIO_NUM;
  config.pin_sccb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn     = PWDN_GPIO_NUM;
  config.pin_reset    = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;

  if (psramFound()) {
    config.frame_size   = FRAMESIZE_VGA;   // 640x480
    config.jpeg_quality = 12;
    config.fb_count     = 2;
  } else {
    config.frame_size   = FRAMESIZE_QVGA;  // 320x240 without PSRAM
    config.jpeg_quality = 15;
    config.fb_count     = 1;
  }

  if (esp_camera_init(&config) != ESP_OK) {
    Serial.println("Camera init failed");
    return;
  }

  WiFi.begin(WIFI_SSID, WIFI_PASS);
  Serial.print("Connecting to WiFi");
  while (WiFi.status() != WL_CONNECTED) { delay(500); Serial.print("."); }
  Serial.println();
  Serial.print("Camera ready. Stream: http://");
  Serial.print(WiFi.localIP());
  Serial.println(":81/stream");
  Serial.print("Controller IP: ");
  Serial.println(WiFi.localIP());

  startServers();
}

void loop() {
  // Read telemetry from Arduino
  while (Serial2.available()) {
    char c = Serial2.read();
    if (c == '\n') {
      parseTelemetry(rxLine);
      rxLine = "";
    } else if (c != '\r') {
      rxLine += c;
    }
  }

  // Safety watchdog: stop the car if the controller goes silent
  if (currentCmd != 'S' && millis() - lastCmdMs > CMD_TIMEOUT_MS) {
    currentCmd = 'S';
    Serial2.write('S'); Serial2.write('\n');
    Serial.println("Watchdog: no command, stopping");
  }

  delay(5);
}