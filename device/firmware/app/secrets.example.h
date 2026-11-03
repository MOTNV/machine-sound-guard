// 사람마다 다른 값. 복사해서 secrets.h로 쓴다 (secrets.h는 커밋하지 않음). CI는 이 파일을 그대로 복사해 컴파일한다.
#pragma once
#define WIFI_SSID "your-wifi"
#define WIFI_PASSWORD "your-password"
#define SERVER_URL "http://192.168.0.10:8000"  // 로그를 받는 서버 (PC 또는 라즈베리 파이 IP)
#define DEVICE_ID "dev-01"
