# device → server: 측정·이상 기록

- 상태: **초안**

ESP32는 1초 창마다 이상 점수를 계산한다. 매 창을 보내지 않고, 10초마다 요약 하나와 이상이 시작·끝날 때 이벤트 하나를 보낸다 (Wi-Fi 부하와 DB 크기를 줄이려고).

**이상 점수**: 1초 소리의 특징 67개(`model/features.py`)에서 가장 가까운 K-means 군집 중심까지의 거리 ÷ 기준 거리(`model/kmeans.py`). **1 이상이면 그 1초는 이상**이다. 소리가 `OFF_RMS`(0.01)보다 작으면 기계가 꺼진 것으로 보고 점수를 0으로 둔다.

## 요약: 10초마다

```
POST /api/readings
{"device_id": "fan-01", "fw": "0.1.0", "window_s": 10, "state": "running", "score_avg": 0.21, "score_max": 0.48, "anomaly_windows": 0}
```

| 필드 | 뜻 |
|---|---|
| `state` | `off` (기계가 꺼짐, 소리가 작음) · `running` (정상 동작) · `anomaly` (이상) |
| `score_avg`, `score_max` | 10초 동안의 이상 점수 평균·최대. 0에 가까울수록 평소 소리, 1 이상이면 이상 |
| `anomaly_windows` | 10초 중 이상 점수가 1 이상인 1초 창 수 |

## 이벤트: 이상이 시작·끝날 때

```
POST /api/events
{"device_id": "fan-01", "fw": "0.1.0", "kind": "anomaly_start", "score": 0.83}
{"device_id": "fan-01", "fw": "0.1.0", "kind": "anomaly_end", "score": 0.12, "duration_s": 14}
```

- 이상 시작: 점수 1 이상인 창이 **3번 연속**일 때 (한 번 튄 소리로 울리지 않게)
- 이상 끝: 1 미만인 창이 5번 연속일 때
- 규칙의 기준 구현은 `model/detector.py` (ESP32와 가상 ESP32가 같은 규칙)

시각은 서버가 받은 시각으로 기록한다 (ESP32에는 정확한 시계가 없다).
