"""가상 기계(tools/virtual_machine.py)가 정상·이상 소리를 의도대로 만드는지. 소리의 물리적 특징으로 확인한다."""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
import virtual_machine as vm  # noqa: E402

SEEDS = range(3)


def band(x, lo, hi):
    """lo~hi Hz 대역이 전체 에너지에서 차지하는 비율."""
    s = np.abs(np.fft.rfft(x)) ** 2
    f = np.fft.rfftfreq(len(x), 1 / vm.SR)
    return s[(f >= lo) & (f < hi)].sum() / s.sum()


def peak_hz(x, lo, hi):
    s = np.abs(np.fft.rfft(x))
    f = np.fft.rfftfreq(len(x), 1 / vm.SR)
    m = (f >= lo) & (f < hi)
    return f[m][np.argmax(s[m])]


def kurtosis(x):
    return ((x - x.mean()) ** 4).mean() / x.var() ** 2


def high_pass(x, f0=800):
    """f0 Hz 아래(모터·날개 소리)를 지운다. 충격음은 고음 쪽에 뾰족하게 남는다."""
    s = np.fft.rfft(x)
    s[np.fft.rfftfreq(len(x), 1 / vm.SR) < f0] = 0
    return np.fft.irfft(s, len(x))


def test_shape_and_range():
    x = vm.generate(2.0, seed=0)
    assert x.dtype == np.float32 and len(x) == 2 * vm.SR
    assert 0.05 < np.sqrt((x ** 2).mean()) < 0.5


def test_same_seed_same_sound():
    assert np.array_equal(vm.generate(1, "bearing", 0.5, seed=3), vm.generate(1, "bearing", 0.5, seed=3))
    assert not np.array_equal(vm.generate(1, seed=3), vm.generate(1, seed=4))


@pytest.mark.parametrize("anomaly", [None, *vm.ANOMALIES])
@pytest.mark.parametrize("seed", SEEDS)
def test_never_clips(anomaly, seed):
    assert np.abs(vm.generate(2, anomaly, 1.0, seed=seed)).max() < 0.99, "소리가 잘림 (최대값 1)"


@pytest.mark.parametrize("seed", SEEDS)
def test_normal_blade_pass_tone(seed):
    """날개 5개 × 25Hz = 125Hz 부근이 가장 큰 소리."""
    assert abs(peak_hz(vm.generate(4, seed=seed), 60, 400) - 125) < 5


@pytest.mark.parametrize("seed", SEEDS)
def test_imbalance_raises_rotation_tone(seed):
    n, x = vm.generate(4, seed=seed), vm.generate(4, "imbalance", 0.8, seed=seed)
    assert band(x, 20, 30) > 10 * band(n, 20, 30)


@pytest.mark.parametrize("seed", SEEDS)
def test_bearing_raises_high_band(seed):
    n, x = vm.generate(4, seed=seed), vm.generate(4, "bearing", 0.8, seed=seed)
    assert band(x, 3000, 6000) > 10 * band(n, 3000, 6000)


@pytest.mark.parametrize("seed", SEEDS)
def test_rubbing_adds_impacts(seed):
    """한 바퀴마다 딱: 고음 쪽 파형이 뾰족해진다 (첨도가 커진다)."""
    n, x = vm.generate(4, seed=seed), vm.generate(4, "rubbing", 0.8, seed=seed)
    assert kurtosis(high_pass(x)) > kurtosis(high_pass(n)) + 10


@pytest.mark.parametrize("seed", SEEDS)
def test_slowdown_lowers_pitch(seed):
    x = vm.generate(4, "slowdown", 0.8, seed=seed)
    assert peak_hz(x, 60, 200) < 125 * 0.85


def test_severity_zero_is_normal():
    assert np.allclose(vm.generate(1, "bearing", 0.0, seed=1), vm.generate(1, seed=1))


def test_ramp_gets_worse_over_time():
    x = vm.generate(8, "bearing", 1.0, seed=2, ramp=True)
    first, last = x[: 2 * vm.SR], x[-2 * vm.SR:]
    assert band(last, 3000, 6000) > 5 * band(first, 3000, 6000)


def test_wav_round_trip(tmp_path):
    x = vm.generate(1, "imbalance", 0.5, seed=5)
    vm.write_wav(tmp_path / "a.wav", x)
    y = vm.read_wav(tmp_path / "a.wav")
    assert len(y) == len(x) and np.abs(y - x).max() < 1e-3


def test_dataset_layout(tmp_path):
    counts = vm.make_dataset(tmp_path, normal=4, per_anomaly=2, seconds=1.0, seed=1)
    assert counts == {"normal": 4, **{a: 2 for a in vm.ANOMALIES}}
    for label, n in counts.items():
        files = sorted((tmp_path / label).glob(f"{label}.*.wav"))
        assert len(files) == n and len(vm.read_wav(files[0])) == vm.SR
