"""판단 규칙 (model/detector.py, docs/contracts/device-log.md)."""

import detector as D
from features import OFF_RMS

ON = OFF_RMS * 10


def run(scores, level=ON):
    d = D.Detector()
    out = []
    for s in scores:
        out += d.update(level, s)
    return [m for m in out if m["kind"] != "reading"], [m for m in out if m["kind"] == "reading"]


def test_short_spike_is_ignored():
    events, _ = run([0.2, 1.5, 1.6, 0.3, 0.2, 2.0, 0.1])
    assert events == []


def test_three_in_a_row_starts_and_five_quiet_ends():
    events, _ = run([0.2, 1.2, 1.4, 1.3, 1.8, 0.5, 0.4, 0.3, 0.2, 0.1])
    assert [e["kind"] for e in events] == ["anomaly_start", "anomaly_end"]
    assert events[0]["score"] == 1.3 and events[1]["duration_s"] == 6


def test_summary_every_ten_seconds():
    _, readings = run([0.1] * 9 + [1.2] + [0.2] * 10)
    assert len(readings) == 2
    r = readings[0]
    assert r == {"kind": "reading", "window_s": 10, "state": "running", "score_avg": 0.21, "score_max": 1.2, "anomaly_windows": 1}


def test_quiet_machine_is_off_and_not_scored():
    events, readings = run([5.0] * 10, level=OFF_RMS / 2)
    assert events == [] and readings[0]["state"] == "off" and readings[0]["score_max"] == 0.0
