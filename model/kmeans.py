"""K-means 이상 감지 (기준 구현). 현장 보정 때 ESP32가 같은 순서로 같은 계산을 한다 (무작위 없음).

학습: 특징을 표준화(평균 0, 표준편차 1) → 군집 중심 초기값을 "가장 먼 점" 방식으로 고름 → Lloyd 반복 30번.
점수: 표준화한 특징에서 가장 가까운 중심까지의 거리 ÷ 기준 거리. 1 이상이면 이상.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

K = 8
ITERATIONS = 30
SD_FLOOR = 1e-3  # 거의 변하지 않는 특징이 점수를 지배하지 않게


@dataclass
class Model:
    mean: np.ndarray        # [F]
    std: np.ndarray         # [F]
    centroids: np.ndarray   # [K, F] 표준화된 공간
    threshold: float        # 이 거리 = 점수 1

    def distance(self, feats: np.ndarray) -> np.ndarray:
        z = (np.atleast_2d(feats) - self.mean) / self.std
        return np.sqrt(((z[:, None, :] - self.centroids[None]) ** 2).sum(-1)).min(1)

    def score(self, feats: np.ndarray) -> np.ndarray:
        return self.distance(feats) / self.threshold


def farthest_point_init(z: np.ndarray, k: int) -> np.ndarray:
    """첫 중심 = 평균에 가장 가까운 점, 다음부터 = 지금 중심들에서 가장 먼 점."""
    first = int(np.argmin(((z - z.mean(0)) ** 2).sum(1)))
    chosen = [first]
    nearest = ((z - z[first]) ** 2).sum(1)
    for _ in range(1, k):
        nxt = int(np.argmax(nearest))
        chosen.append(nxt)
        nearest = np.minimum(nearest, ((z - z[nxt]) ** 2).sum(1))
    return z[chosen].copy()


def fit(feats: np.ndarray, k: int = K, iterations: int = ITERATIONS) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """정상 특징 → (평균, 표준편차, 군집 중심). 군집이 비면 이전 중심을 그대로 둔다."""
    feats = np.asarray(feats, np.float64)
    mean = feats.mean(0)
    std = np.maximum(feats.std(0), SD_FLOOR)
    z = (feats - mean) / std
    centroids = farthest_point_init(z, k)
    for _ in range(iterations):
        labels = ((z[:, None, :] - centroids[None]) ** 2).sum(-1).argmin(1)
        for j in range(k):
            members = z[labels == j]
            if len(members):
                centroids[j] = members.mean(0)
    return mean, std, centroids


def train(normal: np.ndarray, validation: np.ndarray, quantile: float = 0.995) -> Model:
    """기본 모델: 학습용 정상으로 군집, 따로 둔 검증용 정상의 거리 분위수를 기준으로."""
    mean, std, centroids = fit(normal)
    model = Model(mean, std, centroids, 1.0)
    model.threshold = float(np.quantile(model.distance(validation), quantile))
    return model


def calibrate(normal: np.ndarray, margin: float = 1.1) -> Model:
    """현장 보정: 설치한 기계의 평소 소리만으로. 검증용을 따로 둘 수 없어 학습 거리의 최대값에 여유를 둔다."""
    mean, std, centroids = fit(normal)
    model = Model(mean, std, centroids, 1.0)
    model.threshold = float(model.distance(normal).max() * margin)
    return model
