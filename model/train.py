"""기본 모델을 학습해 ESP32용 C 헤더로 내보내고, 평가 결과를 남긴다.

    python model/train.py            # device/firmware/app/src/guard/model_data.h, model/report.md
    python model/train.py --check    # 커밋된 헤더가 지금 학습 결과와 같은지만 확인 (CI)

같은 코드·같은 seed면 항상 같은 모델이 나온다. 특징·학습·가상 기계를 바꾸면 이 명령을 다시 돌려 헤더를 함께 커밋한다.
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import data  # noqa: E402
import kmeans  # noqa: E402
from features import N_FEATURES  # noqa: E402

ROOT = HERE.parent
HEADER = ROOT / "device" / "firmware" / "app" / "src" / "guard" / "model_data.h"
REPORT = HERE / "report.md"
TRAIN_SEED, VALID_SEED = 1, 2
N_TRAIN, N_VALID = 400, 400
SEVERITIES = (0.15, 0.3, 0.5, 0.8)


def train() -> kmeans.Model:
    return kmeans.train(data.clips(N_TRAIN, TRAIN_SEED), data.clips(N_VALID, VALID_SEED))


def floats(values) -> str:
    return ", ".join(f"{float(v):.7g}f" for v in np.ravel(values))


def header_text(model: kmeans.Model) -> str:
    digest = hashlib.sha256(np.concatenate([model.mean, model.std, model.centroids.ravel(), [model.threshold]]).astype("<f4").tobytes()).hexdigest()[:8]
    rows = ",\n".join(f"    {{{floats(c)}}}" for c in model.centroids)
    return f"""// 자동 생성: python model/train.py (직접 고치지 않는다)
// 기본 모델: 가상 기계 {data.FACTORY_RPM:.0f}rpm 정상 소리 {N_TRAIN}초로 K-means {model.centroids.shape[0]}개, 기준 = 검증 정상 {N_VALID}초 거리의 99.5%
// 특징·점수 계산은 model/features.py, model/kmeans.py와 같다
#pragma once

#define GUARD_N_FEATURES {N_FEATURES}
#define GUARD_K {model.centroids.shape[0]}
#define GUARD_MODEL_ID "factory-{digest}"

static const float GUARD_MEAN[GUARD_N_FEATURES] = {{{floats(model.mean)}}};
static const float GUARD_STD[GUARD_N_FEATURES] = {{{floats(model.std)}}};
static const float GUARD_CENTROIDS[GUARD_K][GUARD_N_FEATURES] = {{
{rows}
}};
static const float GUARD_THRESHOLD = {model.threshold:.7g}f;
"""


def parse_header(text: str) -> dict:
    def array(name):
        body = re.search(rf"{name}\[[^\]]*\](?:\[[^\]]*\])? = \{{(.*?)\}};", text, re.S).group(1)
        return np.array([float(v.rstrip("f")) for v in re.findall(r"-?[\d.]+(?:e[-+]?\d+)?f", body)])
    return {"mean": array("GUARD_MEAN"), "std": array("GUARD_STD"), "centroids": array("GUARD_CENTROIDS"),
            "threshold": float(re.search(r"GUARD_THRESHOLD = ([\d.e+-]+)f", text).group(1))}


def evaluate(model: kmeans.Model, rpm: float, seed: int) -> dict:
    """1초 창 기준 오경보율과 이상별·세기별 감지율 (%)."""
    result = {"false_alarm": float(np.mean(model.score(data.clips(400, seed, rpm)) >= 1) * 100), "detect": {}}
    for i, anomaly in enumerate(data.vm.ANOMALIES):
        result["detect"][anomaly] = {s: float(np.mean(model.score(data.clips(60, seed + 10 * (i + 1) + int(s * 10), rpm, anomaly, s)) >= 1) * 100)
                                     for s in SEVERITIES}
    return result


def report_text(rows: list[tuple[str, dict]]) -> str:
    lines = ["# 모델 평가 (python model/train.py가 만든다)", "",
             "1초 창 기준. 오경보 = 정상을 이상으로 본 비율, 감지 = 이상을 이상으로 본 비율. 실제 경보는 3초 연속일 때만 난다.", "",
             "| 경우 | 오경보 | " + " | ".join(f"{data.vm.KOREAN[a]} {s}" for a in data.vm.ANOMALIES for s in SEVERITIES) + " |",
             "|---|---|" + "---|" * (len(data.vm.ANOMALIES) * len(SEVERITIES))]
    for name, r in rows:
        cells = " | ".join(f"{r['detect'][a][s]:.0f}%" for a in data.vm.ANOMALIES for s in SEVERITIES)
        lines.append(f"| {name} | {r['false_alarm']:.1f}% | {cells} |")
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--check", action="store_true")
    a = p.parse_args(argv)
    model = train()
    if a.check:
        saved = parse_header(HEADER.read_text(encoding="utf-8"))
        same = (np.allclose(saved["mean"], model.mean, rtol=1e-4, atol=1e-5) and np.allclose(saved["std"], model.std, rtol=1e-4, atol=1e-5)
                and np.allclose(saved["centroids"], model.centroids.ravel(), rtol=1e-4, atol=1e-4) and abs(saved["threshold"] - model.threshold) < 1e-3 * model.threshold)
        print("커밋된 모델이 학습 결과와 같음" if same else "커밋된 모델이 학습 결과와 다름: python model/train.py 를 돌려 헤더를 다시 커밋한다")
        return 0 if same else 1
    HEADER.parent.mkdir(parents=True, exist_ok=True)
    HEADER.write_text(header_text(model), encoding="utf-8")
    calibrated = kmeans.calibrate(data.clips(120, 30, data.OTHER_RPM))
    rows = [(f"기본 모델 → 같은 기계 ({data.FACTORY_RPM:.0f}rpm)", evaluate(model, data.FACTORY_RPM, 100)),
            (f"기본 모델 → 다른 기계 ({data.OTHER_RPM:.0f}rpm)", evaluate(model, data.OTHER_RPM, 200)),
            ("현장 보정 2분 → 다른 기계", evaluate(calibrated, data.OTHER_RPM, 300))]
    REPORT.write_text(report_text(rows), encoding="utf-8")
    print(f"{HEADER.relative_to(ROOT)}, {REPORT.relative_to(ROOT)}")
    print(report_text(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
