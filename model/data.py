"""학습·평가에 쓰는 가상 기계 소리 묶음. 같은 seed는 항상 같은 소리다 (CI에서 결과가 흔들리지 않게)."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import virtual_machine as vm  # noqa: E402

from features import features  # noqa: E402

FACTORY_RPM = 1500.0   # 기본 모델을 학습한 기계
OTHER_RPM = 1420.0     # 현장 보정을 보여 줄 "다른 기계"


def machine(rng: np.random.Generator, rpm: float) -> vm.Machine:
    """기계 한 대: 회전 속도는 ±1%만, 마이크 거리(크기)와 주변 잡음은 다양하게."""
    return vm.Machine(rpm=rng.uniform(rpm * 0.99, rpm * 1.01), noise=rng.uniform(0.015, 0.04), gain=rng.uniform(0.15, 0.22))


def clips(n: int, seed: int, rpm: float = FACTORY_RPM, anomaly: str | None = None, severity: float = 0.0) -> np.ndarray:
    """1초 조각 n개의 특징 [n, 67]."""
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(n):
        audio = vm.generate(1.0, anomaly, severity, seed=int(rng.integers(1 << 31)), machine=machine(rng, rpm))
        out.append(features(audio))
    return np.array(out)
