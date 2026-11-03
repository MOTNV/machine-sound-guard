"""가상 기계: 모터·날개 소리를 만들고 이상(불균형·베어링 마모·이물질 걸림·속도 저하)을 섞는다.

보드와 실제 기계 없이 정상·이상 소리를 같은 조건으로 원하는 만큼 만든다 (docs/decisions.md).
학습 데이터(dataset), 시연(play·stream), CI 테스트(tests/tools)가 모두 이 소리를 쓴다.

    python tools/virtual_machine.py wav -o normal.wav --seconds 10
    python tools/virtual_machine.py wav -o bearing.wav --anomaly bearing --severity 0.8
    python tools/virtual_machine.py wav -o story.wav --anomaly imbalance --ramp --seconds 120   # 점점 나빠짐
    python tools/virtual_machine.py dataset --out data/generated                                  # 학습용 1초 조각들
    python tools/virtual_machine.py stream --anomaly rubbing --severity 0.6 | <가상 ESP32>          # 16비트 PCM을 stdout으로
    python tools/virtual_machine.py play --anomaly slowdown --severity 0.7                           # 스피커로 듣기 (sounddevice)
"""
from __future__ import annotations

import argparse
import sys
import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np

SR = 16000  # ESP32 마이크(PDM)와 같은 표본화 주파수
ANOMALIES = ("imbalance", "bearing", "rubbing", "slowdown")
KOREAN = {"imbalance": "날개 불균형", "bearing": "베어링 마모", "rubbing": "이물질 걸림", "slowdown": "속도 저하"}


@dataclass
class Machine:
    rpm: float = 1500.0     # 분당 회전수 → 회전 주파수 25Hz
    blades: int = 5         # 날개 수 → 날개 통과 주파수 125Hz
    noise: float = 0.025    # 바람 잡음 크기
    gain: float = 0.2       # 전체 크기 (이상이 가장 심해도 최대값이 1을 넘지 않게)


def _smooth_random(n: int, rng: np.random.Generator, rate_hz: float) -> np.ndarray:
    """천천히 흔들리는 값 (-1~1 근처). rate_hz보다 느린 변화만 남긴다."""
    k = max(2, int(n * rate_hz / SR) + 2)
    points = rng.uniform(-1, 1, k)
    return np.interp(np.linspace(0, k - 1, n), np.arange(k), points)


def _colored_noise(n: int, rng: np.random.Generator) -> np.ndarray:
    """낮은 소리 쪽이 큰 바람 잡음 (흰 잡음을 한 번 거른다)."""
    white = rng.standard_normal(n)
    spectrum = np.fft.rfft(white)
    f = np.fft.rfftfreq(n, 1 / SR)
    spectrum /= np.sqrt(1 + (f / 400.0) ** 2)
    out = np.fft.irfft(spectrum, n)
    return out / (np.std(out) + 1e-9)


def generate(seconds: float = 1.0, anomaly: str | None = None, severity: float = 0.0, seed: int | None = None,
             machine: Machine | None = None, ramp: bool = False) -> np.ndarray:
    """가상 기계 소리 (float32, -1~1). severity는 0(정상)~1(심함). ramp=True면 0에서 severity까지 점점 커진다."""
    if anomaly is not None and anomaly not in ANOMALIES:
        raise ValueError(f"anomaly는 {ANOMALIES} 중 하나: {anomaly!r}")
    m = machine or Machine()
    rng = np.random.default_rng(seed)
    n = int(seconds * SR)
    t = np.arange(n) / SR
    sev = np.full(n, float(np.clip(severity, 0, 1)))
    if ramp:
        sev = np.linspace(0, float(np.clip(severity, 0, 1)), n)
    if anomaly is None:
        sev[:] = 0

    # 회전 속도: 평소에도 ±1% 흔들린다. 속도 저하는 최대 30% 느려지고 불안정하게 흔들린다
    rpm = m.rpm * (1 + 0.01 * _smooth_random(n, rng, 0.5))
    if anomaly == "slowdown":
        wobble = np.sin(2 * np.pi * 0.7 * t + rng.uniform(0, 2 * np.pi))
        rpm = rpm * (1 - 0.30 * sev + 0.06 * sev * wobble)
    f_rot = rpm / 60.0
    phase_rot = 2 * np.pi * np.cumsum(f_rot) / SR

    # 평소 소리: 날개 통과음과 배음, 약한 회전음, 모터 전기음(120Hz), 바람 잡음
    x = np.zeros(n)
    for k, amp in ((1, 1.0), (2, 0.45), (3, 0.22), (4, 0.1)):
        x += amp * np.sin(k * m.blades * phase_rot + rng.uniform(0, 2 * np.pi))
    x += 0.12 * np.sin(phase_rot + rng.uniform(0, 2 * np.pi))
    x += 0.08 * np.sin(2 * np.pi * 120 * t + rng.uniform(0, 2 * np.pi))
    x *= 1 + 0.03 * _smooth_random(n, rng, 2.0)
    x += m.noise / m.gain * _colored_noise(n, rng)

    if anomaly == "imbalance":
        # 한 바퀴에 한 번 웅웅: 회전 주파수 성분이 커지고 날개 소리가 회전마다 출렁인다
        x *= 1 + 0.5 * sev * np.sin(phase_rot)
        x += 1.6 * sev * np.sin(phase_rot + 0.3)
    elif anomaly == "bearing":
        # 바깥 궤도 결함 주파수(회전의 약 3.58배)마다 3.5~5kHz 공진이 짧게 울린다 (사각사각)
        bpfo = 3.58 * f_rot
        hits = np.where(np.diff(np.floor(np.cumsum(bpfo) / SR)) > 0)[0]
        ring_t = np.arange(int(0.006 * SR)) / SR
        for i in hits:
            f_res = rng.uniform(3500, 5000)
            ring = np.exp(-ring_t * 900) * np.sin(2 * np.pi * f_res * ring_t)
            j = min(n, i + len(ring))
            x[i:j] += 1.4 * sev[i] * rng.uniform(0.6, 1.0) * ring[: j - i]
        x += 0.25 * sev * np.sin(2 * np.pi * 4200 * t) * _colored_noise(n, rng) * 0.3
    elif anomaly == "rubbing":
        # 한 바퀴마다 딱: 1~3kHz 짧은 충격음 (위치가 조금씩 어긋난다)
        hits = np.where(np.diff(np.floor(phase_rot / (2 * np.pi))) > 0)[0]
        click_n = int(0.004 * SR)
        for i in hits:
            i = max(0, min(n - click_n, i + int(rng.integers(-40, 40))))
            burst = rng.standard_normal(click_n) * np.exp(-np.arange(click_n) / (click_n / 4))
            burst = np.convolve(burst, np.ones(4) / 4, mode="same") - np.convolve(burst, np.ones(16) / 16, mode="same")
            x[i:i + click_n] += 2.2 * sev[i] * burst / (np.abs(burst).max() + 1e-9)

    return np.clip(m.gain * x, -1, 1).astype(np.float32)


def write_wav(path: Path, audio: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(to_pcm16(audio))


def to_pcm16(audio: np.ndarray) -> bytes:
    return (np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes()


def read_wav(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as w:
        assert w.getframerate() == SR and w.getnchannels() == 1 and w.getsampwidth() == 2, f"{path}: 16kHz 모노 16비트가 아님"
        return np.frombuffer(w.readframes(w.getnframes()), "<i2").astype(np.float32) / 32767


def make_dataset(out: Path, normal: int, per_anomaly: int, seconds: float, seed: int) -> dict[str, int]:
    """학습용 조각. 정상은 회전 속도·잡음 크기를 바꿔 가며 다양하게, 이상은 세기를 0.3~1로 섞는다.
    파일 이름 <라벨>.<번호>.wav (Edge Impulse 업로드 때 라벨을 이름에서 읽는다)."""
    rng = np.random.default_rng(seed)
    counts = {}
    for i in range(normal):
        machine = Machine(rpm=rng.uniform(1380, 1620), noise=rng.uniform(0.015, 0.04), gain=rng.uniform(0.15, 0.22))
        write_wav(out / "normal" / f"normal.{i:04d}.wav", generate(seconds, seed=int(rng.integers(1 << 31)), machine=machine))
    counts["normal"] = normal
    for anomaly in ANOMALIES:
        for i in range(per_anomaly):
            machine = Machine(rpm=rng.uniform(1380, 1620), noise=rng.uniform(0.015, 0.04), gain=rng.uniform(0.15, 0.22))
            audio = generate(seconds, anomaly, rng.uniform(0.3, 1.0), seed=int(rng.integers(1 << 31)), machine=machine)
            write_wav(out / anomaly / f"{anomaly}.{i:04d}.wav", audio)
        counts[anomaly] = per_anomaly
    return counts


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("wav", "stream", "play"):
        s = sub.add_parser(name)
        s.add_argument("--anomaly", choices=ANOMALIES)
        s.add_argument("--severity", type=float, default=0.7)
        s.add_argument("--seconds", type=float, default=10 if name == "wav" else 0, help="0이면 끝없이 (stream·play)")
        s.add_argument("--ramp", action="store_true", help="이상 세기를 0에서 --severity까지 점점 올린다")
        s.add_argument("--seed", type=int)
        if name == "wav":
            s.add_argument("-o", "--out", type=Path, required=True)
    d = sub.add_parser("dataset")
    d.add_argument("--out", type=Path, default=Path("data/generated"))
    d.add_argument("--normal", type=int, default=300)
    d.add_argument("--per-anomaly", type=int, default=40, help="이상 종류마다 (검증용. 이상 감지 학습에는 정상만 쓴다)")
    d.add_argument("--seconds", type=float, default=1.0)
    d.add_argument("--seed", type=int, default=7)
    a = p.parse_args(argv)

    if a.cmd == "dataset":
        counts = make_dataset(a.out, a.normal, a.per_anomaly, a.seconds, a.seed)
        print(f"{a.out}: " + ", ".join(f"{KOREAN.get(k, '정상')} {v}개" for k, v in counts.items()))
        return
    if a.cmd == "wav":
        write_wav(a.out, generate(a.seconds, a.anomaly, a.severity, a.seed, ramp=a.ramp))
        print(f"{a.out}: {a.seconds}초, {KOREAN.get(a.anomaly, '정상')}" + (f" 세기 {a.severity}" if a.anomaly else ""), file=sys.stderr)
        return
    # stream·play: 1초씩 끊김 없이 이어 만든다 (조각마다 seed를 바꿔 같은 소리가 반복되지 않게)
    rng = np.random.default_rng(a.seed)
    total = a.seconds or float("inf")
    player = None
    if a.cmd == "play":
        import sounddevice  # 선택 패키지

        player = sounddevice.OutputStream(samplerate=SR, channels=1, dtype="float32")
        player.start()
    elapsed = 0.0
    try:
        while elapsed < total:
            sev = a.severity * min(1.0, elapsed / 60) if a.ramp else a.severity
            chunk = generate(1.0, a.anomaly, sev, int(rng.integers(1 << 31)))
            if player:
                player.write(chunk.reshape(-1, 1))
            else:
                sys.stdout.buffer.write(to_pcm16(chunk))
                sys.stdout.buffer.flush()
            elapsed += 1.0
    except (BrokenPipeError, KeyboardInterrupt):
        pass


if __name__ == "__main__":
    main()
