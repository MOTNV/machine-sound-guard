"""소리 특징 (기준 구현). ESP32 C 코드(device/firmware/app/src/guard/)가 이 수식을 그대로 따른다.

1초(16000표본) → 67개 값:
  [0:32]  멜 대역 32개 로그 에너지의 평균 (음색)          1024점 FFT, 512 간격 30프레임, Hann 창
  [32:64] 같은 값의 표준편차 (충격음·출렁임)
  [64:67] 1초 전체에서 저음 대역의 비율 로그: 20~32Hz(회전음), 45~55Hz(회전 2배), 100~150Hz(날개음)
"""
from __future__ import annotations

import numpy as np

SR = 16000
WINDOW = 16000          # 1초
NFFT = 1024
HOP = 512
N_MELS = 32
FMIN, FMAX = 20.0, 7600.0
LOW_BANDS = ((20, 32), (45, 55), (100, 150))  # Hz. 1초 창이라 DFT 한 칸 = 1Hz
N_FEATURES = 2 * N_MELS + len(LOW_BANDS)
OFF_RMS = 0.01          # 이보다 작으면 기계가 꺼진 것으로 본다 (점수를 매기지 않음)
EPS_MEL = 1e-6
EPS_LOW = 1e-9


def hann(n: int) -> np.ndarray:
    """대칭 Hann 창 (numpy.hanning과 같다): 0.5 - 0.5·cos(2πi/(n-1))"""
    return 0.5 - 0.5 * np.cos(2 * np.pi * np.arange(n) / (n - 1))


def hz_to_mel(f):
    return 2595.0 * np.log10(1.0 + np.asarray(f) / 700.0)


def mel_to_hz(m):
    return 700.0 * (10.0 ** (np.asarray(m) / 2595.0) - 1.0)


def mel_filterbank() -> np.ndarray:
    """[N_MELS, NFFT/2+1] 삼각 필터 (HTK 멜, 높이 1)."""
    points = mel_to_hz(np.linspace(hz_to_mel(FMIN), hz_to_mel(FMAX), N_MELS + 2))
    bins = np.arange(NFFT // 2 + 1) * SR / NFFT
    fb = np.zeros((N_MELS, len(bins)))
    for i in range(N_MELS):
        lo, center, hi = points[i], points[i + 1], points[i + 2]
        fb[i] = np.clip(np.minimum((bins - lo) / (center - lo), (hi - bins) / (hi - center)), 0, None)
    return fb


FILTERBANK = mel_filterbank()
FRAME_WINDOW = hann(NFFT)
FULL_WINDOW = hann(WINDOW)


def rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.asarray(x, np.float64) ** 2)))


def features(x: np.ndarray) -> np.ndarray:
    """1초 소리 → 67개 특징 (float64)."""
    x = np.asarray(x, np.float64)
    assert len(x) == WINDOW, f"1초({WINDOW}표본)가 아님: {len(x)}"
    starts = range(0, WINDOW - NFFT + 1, HOP)
    frames = np.stack([x[s:s + NFFT] * FRAME_WINDOW for s in starts])
    power = np.abs(np.fft.rfft(frames, axis=1)) ** 2
    logmel = np.log(power @ FILTERBANK.T + EPS_MEL)
    xw = x * FULL_WINDOW
    spectrum = np.fft.rfft(xw)
    total = WINDOW * np.sum(xw ** 2)  # 파스발: 양쪽 스펙트럼 전체 에너지
    low = [np.log(np.sum(np.abs(spectrum[lo:hi]) ** 2) / (total + 1e-12) + EPS_LOW) for lo, hi in LOW_BANDS]
    return np.concatenate([logmel.mean(0), logmel.std(0), low])
