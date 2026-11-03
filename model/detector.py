"""판단 규칙 (기준 구현, docs/contracts/device-log.md). ESP32와 가상 ESP32가 같은 규칙을 쓴다.

1초마다 (소리 크기, 이상 점수)를 받아
  - 소리가 OFF_RMS보다 작으면 off (점수를 매기지 않음)
  - 점수 ≥ 1 인 창이 3번 연속이면 이상 시작, < 1 인 창이 5번 연속이면 이상 끝
  - 10초마다 요약 (state, score_avg, score_max, anomaly_windows)
"""
from __future__ import annotations

from dataclasses import dataclass, field

from features import OFF_RMS

START_AFTER = 3
END_AFTER = 5
SUMMARY_EVERY = 10


@dataclass
class Detector:
    anomaly: bool = False
    over: int = 0
    under: int = 0
    started_at: int = 0
    tick: int = 0
    peak: float = 0.0
    window: list = field(default_factory=list)  # (state, score) 10초치

    def update(self, level: float, score: float) -> list[dict]:
        """1초 결과 하나 → 보낼 메시지 목록 (이벤트·요약)."""
        out = []
        self.tick += 1
        running = level >= OFF_RMS
        if not running:
            score = 0.0
        if running and score >= 1.0:
            self.over, self.under = self.over + 1, 0
        else:
            self.under, self.over = self.under + 1, 0
        if self.anomaly:
            self.peak = max(self.peak, score)
        if not self.anomaly and self.over >= START_AFTER:
            self.anomaly, self.started_at, self.peak = True, self.tick, score
            out.append({"kind": "anomaly_start", "score": round(score, 3)})
        elif self.anomaly and self.under >= END_AFTER:
            self.anomaly = False
            out.append({"kind": "anomaly_end", "score": round(score, 3), "duration_s": self.tick - self.started_at})
        state = "anomaly" if self.anomaly else ("running" if running else "off")
        self.window.append((state, score, running and score >= 1.0))
        if len(self.window) == SUMMARY_EVERY:
            scores = [s for _, s, _ in self.window]
            states = [st for st, _, _ in self.window]
            summary_state = "anomaly" if "anomaly" in states else ("running" if "running" in states else "off")
            out.append({"kind": "reading", "window_s": SUMMARY_EVERY, "state": summary_state,
                        "score_avg": round(sum(scores) / len(scores), 3), "score_max": round(max(scores), 3),
                        "anomaly_windows": sum(1 for *_, a in self.window if a)})
            self.window = []
        return out
