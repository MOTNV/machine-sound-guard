// 펌웨어 뼈대 — 지금은 버전 확인만 한다. 주제가 정해지면 Edge Impulse 추론과 서버 전송을 채운다.
// 시리얼 첫 줄에 FW_VERSION을 찍는다 (보드에 올라간 버전도 팀이 맞춰야 하는 값).
#include <Arduino.h>
#include <esp_arduino_version.h>
#include "secrets.h"

#define FW_VERSION "0.0.1"

void setup() {
  Serial.begin(115200);
  delay(1500);
  Serial.printf("FW_VERSION %s, esp32 core %d.%d.%d, PSRAM %u KB, device %s\n", FW_VERSION,
                ESP_ARDUINO_VERSION_MAJOR, ESP_ARDUINO_VERSION_MINOR, ESP_ARDUINO_VERSION_PATCH,
                (unsigned)(ESP.getPsramSize() / 1024), DEVICE_ID);
}

void loop() {
  delay(1000);
}
