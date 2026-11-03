# machine-sound-guard

ESP32-S3가 기계 소리를 직접 듣고, 평소 소리와 다르면 "이상"으로 판단해 기록하는 이상음 감지기. 쌓인 이상 점수로 고장 전조를 본다 (예지 정비, 산업 안전).

```
[가상 기계]  ──소리──▶  [ESP32-S3]  ──10초 요약·이상 이벤트──▶  [server: API + Postgres]  ──▶  [웹 대시보드]
PC 스피커로 재생       Edge Impulse 이상 감지          HTTP POST (같은 Wi-Fi)              점수 그래프, 이상 목록
```

## 필수 조건

| 조건 | 어떻게 |
|---|---|
| ESP32에 모델을 넣어 사용 | Edge Impulse로 평소 소리만 학습한 이상 감지 모델을 보드에서 돌려 1초마다 이상 점수를 낸다 (`device/`) |
| 로그를 DB에 저장 | 10초 요약과 이상 시작·끝 이벤트를 Postgres에 저장한다 (`server/`, 형식은 `docs/contracts/`) |
| CI 구현 | PR마다 바뀐 부분만 검사: 펌웨어 컴파일(모델 포함), 서버·DB 기동과 테스트 (`.github/workflows/ci.yml`) |

## 폴더

| 폴더 | 하는 일 |
|---|---|
| `device/` | ESP32-S3 펌웨어(`firmware/app`), Edge Impulse 라이브러리 zip(`model/`) |
| `server/` | API 서버와 Postgres (docker compose) |
| `tools/` | 가상 기계(정상·이상 소리 만들기), 가짜 장치(보드 없이 기록 보내기) |
| `tests/` | `tests/<파트>/test_*.py`. 서비스 코드를 import하지 않고 HTTP로 부른다 |
| `docs/` | 데이터 형식(`contracts/`), 결정 기록(`decisions.md`) |

## 개발 환경

| 대상 | 기준 |
|---|---|
| ESP32 | Seeed XIAO ESP32S3 Sense, FQBN `esp32:esp32:XIAO_ESP32S3:PSRAM=opi`, esp32 코어 3.3.12 (ci.yml과 같은 값) |
| 서버 | Docker Compose 2.24 이상, `python:3.12-slim`, `postgres:16.6-alpine` |

## 실행

```bash
cd server && cp ../.env.example .env
docker compose up --build -d     # api(8000) + db
docker compose ps                # healthy 확인
```

펌웨어는 `device/firmware/app/secrets.example.h`를 `secrets.h`로 복사해 Wi-Fi와 서버 주소(PC IP)를 채운 뒤 올린다. 시리얼 첫 줄에 `FW_VERSION`이 나온다.

## 테스트 · CI

```bash
pip install -r tests/requirements.txt
pytest tests/server               # server를 띄운 상태에서
```

PR을 올리면 GitHub Actions가 바뀐 부분만 검사하고, 마지막 `ci-ok`가 초록불이어야 병합된다. 계약(`docs/contracts/`)이나 CI가 바뀌면 전부 검사한다.

## 브랜치

- `main`(최종본)과 `dev`(통합)에는 직접 push하지 않고 PR로만 합친다. 병합은 Create a merge commit.
- 작업 브랜치: `<태그>/<파트>/<기능>` (태그 `feature` `fix` `docs` `refactor` `chore`, 파트 `device` `server` `tools`, 여러 곳이면 `common`). `dev`에서 만들고 `dev`로 PR, 병합 후 삭제.
- 커밋 메시지: `<타입>(<파트>): <요약>`. 계약을 바꾸면 `[contract]`를 붙인다.
- `.env`, `secrets.h`, 녹음 원본(`data/raw/`)은 커밋하지 않는다.
