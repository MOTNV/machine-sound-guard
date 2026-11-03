"""특징 계산 (model/features.py). ESP32 C 코드가 같은 값을 내는지는 tests/device에서 비교한다."""

import numpy as np

import features as F
import data


def test_feature_vector_shape_and_finite():
    x = data.vm.generate(1.0, seed=1)
    f = F.features(x)
    assert f.shape == (F.N_FEATURES,) == (67,)
    assert np.all(np.isfinite(f))


def test_same_sound_same_features():
    x = data.vm.generate(1.0, "bearing", 0.5, seed=2)
    assert np.array_equal(F.features(x), F.features(x.copy()))


def test_filterbank_covers_range():
    fb = F.FILTERBANK
    assert fb.shape == (F.N_MELS, F.NFFT // 2 + 1)
    assert np.all(fb.max(1) > 0.5), "비어 있는 멜 대역이 있음"


def test_silence_is_off():
    assert F.rms(np.zeros(F.WINDOW)) < F.OFF_RMS <= F.rms(data.vm.generate(1.0, seed=3))


def test_imbalance_raises_rotation_band():
    """불균형은 회전음(20~32Hz) 비율을 크게 올린다 (멜 대역만으로는 해상도가 모자라 이 특징을 따로 둔다)."""
    normal = F.features(data.vm.generate(1.0, seed=4))
    odd = F.features(data.vm.generate(1.0, "imbalance", 0.8, seed=4))
    assert odd[64] > normal[64] + 2.0


def test_slowdown_moves_blade_tone_out_of_band():
    """속도 저하로 날개음이 100Hz 아래로 내려가면 100~150Hz 비율이 준다."""
    normal = F.features(data.vm.generate(1.0, seed=4))
    odd = F.features(data.vm.generate(1.0, "slowdown", 0.8, seed=4))
    assert odd[66] < normal[66] - 0.2
