"""펌웨어 파일 구조 (보드 없이). 컴파일은 CI device 잡이 한다."""

import re
from pathlib import Path

APP = Path(__file__).resolve().parents[2] / "device" / "firmware" / "app"


def test_prints_firmware_version():
    sketch = (APP / "app.ino").read_text(encoding="utf-8")
    assert re.search(r'#define\s+FW_VERSION\s+"[^"]+"', sketch)
    assert "FW_VERSION" in sketch.split("void setup", 1)[1].split("void loop", 1)[0]


def test_secrets_example_has_required_names():
    text = (APP / "secrets.example.h").read_text(encoding="utf-8")
    for name in ("WIFI_SSID", "WIFI_PASSWORD", "SERVER_URL", "DEVICE_ID"):
        assert re.search(rf"#define\s+{name}\b", text), name


def test_model_header_is_generated():
    header = (APP / "src" / "guard" / "model_data.h").read_text(encoding="utf-8")
    assert "자동 생성: python model/train.py" in header and "GUARD_THRESHOLD" in header
