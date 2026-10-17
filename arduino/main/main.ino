// Arduino Uno: motor control (L298N), ultrasonic obstacle stop, buzzer,
// and command link to ESP32-CAM over SoftwareSerial.

#include <SoftwareSerial.h>

const uint8_t ENA = 5, IN1 = 7, IN2 = 8;     // left motor
const uint8_t ENB = 6, IN3 = 9, IN4 = 10;    // right motor
const uint8_t TRIG = 12, ECHO = 13;
const uint8_t BUZZER = 4;
const uint8_t ESP_RX = 2, ESP_TX = 3;

SoftwareSerial esp(ESP_RX, ESP_TX);          // 9600 baud link to ESP32-CAM

const int OBSTACLE_CM = 20;                  // stop when closer than this
const int SPEEDS[] = {0, 130, 190, 255};     // speed levels 1..3

int speedLevel = 2;
char cmd = 'S';
int distanceCm = -1;
unsigned long lastDistMs = 0, lastSendMs = 0, beepOffMs = 0;

void setMotor(uint8_t en, uint8_t a, uint8_t b, int spd) {
  if (spd > 0)      { digitalWrite(a, HIGH); digitalWrite(b, LOW); }
  else if (spd < 0) { digitalWrite(a, LOW);  digitalWrite(b, HIGH); }
  else              { digitalWrite(a, LOW);  digitalWrite(b, LOW); }
  analogWrite(en, abs(spd));
}

void drive(char c) {
  int v = SPEEDS[speedLevel];
  int l = 0, r = 0;
  switch (c) {
    case 'F': l = v;  r = v;  break;   // forward
    case 'B': l = -v; r = -v; break;   // backward
    case 'L': l = -v; r = v;  break;   // spin left
    case 'R': l = v;  r = -v; break;   // spin right
    default:  break;                   // 'S' = stop
  }
  // Obstacle protection: refuse to drive forward into something close
  if (c == 'F' && distanceCm > 0 && distanceCm < OBSTACLE_CM) {
    l = 0; r = 0;
  }
  setMotor(ENA, IN1, IN2, l);
  setMotor(ENB, IN3, IN4, r);
}

int readDistance() {
  digitalWrite(TRIG, LOW);  delayMicroseconds(2);
  digitalWrite(TRIG, HIGH); delayMicroseconds(10);
  digitalWrite(TRIG, LOW);
  long d = pulseIn(ECHO, HIGH, 25000);     // 25 ms timeout (~4 m)
  if (d == 0) return -1;
  return d / 58;                           // microseconds to cm
}

void handleChar(char c) {
  if (c && strchr("FBLRS", c)) {
    cmd = c;
  } else if (c >= '1' && c <= '3') {
    speedLevel = c - '0';
  } else if (c == 'H') {                   // horn: 300 ms beep
    digitalWrite(BUZZER, HIGH);
    beepOffMs = millis() + 300;
  }
}

void setup() {
  pinMode(ENA, OUTPUT); pinMode(IN1, OUTPUT); pinMode(IN2, OUTPUT);
  pinMode(ENB, OUTPUT); pinMode(IN3, OUTPUT); pinMode(IN4, OUTPUT);
  pinMode(TRIG, OUTPUT); pinMode(ECHO, INPUT);
  pinMode(BUZZER, OUTPUT);
  digitalWrite(BUZZER, LOW);
  drive('S');
  esp.begin(9600);
}

void loop() {
  // 1. Read commands from ESP32-CAM
  while (esp.available()) {
    char c = esp.read();
    if (c != '\n' && c != '\r') handleChar(c);
  }

  // 2. Measure distance about every 60 ms
  if (millis() - lastDistMs > 60) {
    lastDistMs = millis();
    distanceCm = readDistance();
  }

  // 3. Buzzer off when the horn time has passed
  if (beepOffMs && millis() > beepOffMs) {
    digitalWrite(BUZZER, LOW);
    beepOffMs = 0;
  }

  // 4. Apply the current command (with obstacle check)
  drive(cmd);

  // 5. Send telemetry to ESP32-CAM every 200 ms
  if (millis() - lastSendMs > 200) {
    lastSendMs = millis();
    esp.print("D:");
    esp.println(distanceCm);
  }
}