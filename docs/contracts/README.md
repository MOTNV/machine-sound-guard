# 파트 사이 데이터 형식

구현 전에 경계마다 형식을 정해 이 폴더에 적는다. 바꾸는 커밋은 메시지에 `[contract]`를 붙인다 (CI가 모든 파트를 검사한다).

| 경계 | 보내는 쪽 → 받는 쪽 | 문서 |
|---|---|---|
| 측정·이상 기록 | device(ESP32) → server | [device-log.md](device-log.md) 초안 |
| 조회 | server(DB) → web | 미정 (DB 정한 뒤) |
