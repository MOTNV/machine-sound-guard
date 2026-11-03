"""모델이 충분히 좋은지 (CI 통과 조건). 1초 창 기준, 가상 기계 소리, 같은 seed라 결과가 흔들리지 않는다.

기준을 낮추려면 docs/decisions.md에 이유를 적는다.
"""

import numpy as np
import pytest

import data

ANOMALIES = data.vm.ANOMALIES


def rate(model, feats):
    return float(np.mean(model.score(feats) >= 1) * 100)


def test_factory_quiet_on_its_machine(factory):
    assert rate(factory, data.clips(400, 100)) <= 1.0


@pytest.mark.parametrize("anomaly", ANOMALIES)
def test_factory_detects_moderate_anomaly(factory, anomaly):
    assert rate(factory, data.clips(60, 110 + ANOMALIES.index(anomaly), anomaly=anomaly, severity=0.3)) >= 95


def test_other_machine_needs_calibration(factory, calibrated):
    """기본 모델은 회전 속도가 다른 기계에서 오경보가 많고, 2분 현장 보정 뒤에는 거의 없다."""
    before = rate(factory, data.clips(400, 200, data.OTHER_RPM))
    after = rate(calibrated, data.clips(400, 300, data.OTHER_RPM))
    assert before >= 10 and after <= 2.0 and after <= before / 5


@pytest.mark.parametrize("anomaly", ANOMALIES)
def test_calibrated_detects(calibrated, anomaly):
    i = ANOMALIES.index(anomaly)
    assert rate(calibrated, data.clips(60, 310 + i, data.OTHER_RPM, anomaly, 0.5)) >= 95
    floor = 60 if anomaly == "slowdown" else 90  # 보정 2분으로는 아주 약한 속도 저하를 정상 흔들림과 가르기 어렵다
    assert rate(calibrated, data.clips(60, 320 + i, data.OTHER_RPM, anomaly, 0.3)) >= floor


def test_committed_model_matches_training():
    """학습 코드·가상 기계를 바꾸고 헤더를 다시 만들지 않으면 실패한다."""
    import train

    assert train.main(["--check"]) == 0
