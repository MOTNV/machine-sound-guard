"""ESP32 판정 코드(C++, device/firmware/app/src/guard)가 파이썬 기준 구현(model/)과 같은 결과를 내는지.

PC용 빌드(가상 ESP32, device/sim)에 같은 소리를 넣어 비교한다. 펌웨어는 같은 소스를 CI가 ESP32-S3용으로 컴파일한다.
"""

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "model"))
sys.path.insert(0, str(ROOT / "tools"))
import data  # noqa: E402
import detector as D  # noqa: E402
import features as F  # noqa: E402
import kmeans  # noqa: E402
import train  # noqa: E402
import virtual_machine as vm  # noqa: E402

SIM = ROOT / "device" / "sim" / "guard_sim"


@pytest.fixture(scope="module", autouse=True)
def build():
    subprocess.run(["make", "-s", "-C", str(SIM.parent)], check=True)


def sim(args, chunks):
    pcm = b"".join(vm.to_pcm16(c) for c in chunks)
    out = subprocess.run([str(SIM), *args], input=pcm, capture_output=True, check=True).stdout.decode()
    return [json.loads(line) for line in out.splitlines()]


def as_heard(chunk):
    """16비트로 바꿨다 되돌린 소리 (C가 받는 것과 같은 값)."""
    return np.frombuffer(vm.to_pcm16(chunk), "<i2").astype(np.float32) / 32767


CASES = [(None, 0.0), ("imbalance", 0.5), ("bearing", 0.5), ("rubbing", 0.5), ("slowdown", 0.5), (None, 0.0)]
CHUNKS = [vm.generate(1.0, a, s, seed=i) for i, (a, s) in enumerate(CASES)]


def test_core_does_not_use_arduino():
    """PC에서도 빌드되도록 판정 코드는 아두이노 기능을 쓰지 않는다."""
    for name in ("guard.h", "guard.cpp"):
        assert "Arduino.h" not in (SIM.parents[1] / "firmware" / "app" / "src" / "guard" / name).read_text(encoding="utf-8")


def test_features_match():
    for line, chunk in zip(sim(["features"], CHUNKS), CHUNKS):
        ref = F.features(as_heard(chunk))
        assert np.abs(np.array(line["features"]) - ref).max() < 1e-4
        assert abs(line["rms"] - F.rms(as_heard(chunk))) < 1e-6


def test_factory_scores_match():
    model = train.train()
    got = [m["score"] for m in sim(["run", "--windows"], CHUNKS) if m["kind"] == "window"]
    ref = [float(model.score(F.features(as_heard(c)))[0]) for c in CHUNKS]
    assert np.allclose(got, ref, rtol=1e-3, atol=1e-3)
    assert [g >= 1 for g in got] == [False, True, True, True, True, False]  # 정상만 기준 아래


def test_calibration_and_decisions_match():
    """현장 보정 → 판단 규칙까지 메시지가 하나하나 같다 (다른 기계, 꺼짐 → 보정 → 정상 → 베어링 마모 → 정상)."""
    rng = np.random.default_rng(5)

    def chunk(anomaly=None, sev=0.0):
        return vm.generate(1.0, anomaly, sev, seed=int(rng.integers(1 << 31)), machine=data.machine(rng, data.OTHER_RPM))

    seq = [np.zeros(vm.SR, np.float32)] * 3 + [chunk() for _ in range(60 + 20)] + [chunk("bearing", 0.6) for _ in range(15)] + [chunk() for _ in range(12)]
    out = sim(["run", "--calibrate", "60"], seq)
    heard = [as_heard(c) for c in seq]
    feats = [F.features(x) for x in heard]
    running = [i for i, x in enumerate(heard) if F.rms(x) >= F.OFF_RMS][:60]
    model = kmeans.calibrate(np.array([feats[i] for i in running]))
    calibrated = next(m for m in out if m["kind"] == "calibrated")
    assert abs(calibrated["threshold"] - model.threshold) < 1e-3 * model.threshold

    det, ref = D.Detector(), []
    for i in range(running[-1] + 1, len(seq)):
        ref += det.update(F.rms(heard[i]), float(model.score(feats[i])[0]))
    got = [m for m in out if m["kind"] in ("anomaly_start", "anomaly_end", "reading")]
    assert [m["kind"] for m in got] == [m["kind"] for m in ref]
    assert [m.get("state") for m in got] == [m.get("state") for m in ref]
    assert [m.get("duration_s") for m in got] == [m.get("duration_s") for m in ref]
    assert np.allclose([m["score" if "score" in m else "score_avg"] for m in got],
                       [m["score" if "score" in m else "score_avg"] for m in ref], atol=0.01)
    assert any(m["kind"] == "anomaly_start" for m in got), "베어링 마모를 잡지 못함"


def test_silence_is_off():
    out = sim(["run"], [np.zeros(vm.SR, np.float32)] * 10)
    reading = next(m for m in out if m["kind"] == "reading")
    assert reading["state"] == "off" and reading["score_max"] == 0
    assert not any(m["kind"] == "anomaly_start" for m in out)
