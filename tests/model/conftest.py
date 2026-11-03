import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "model"))


@pytest.fixture(scope="session")
def factory():
    import train

    return train.train()


@pytest.fixture(scope="session")
def calibrated():
    import data
    import kmeans

    return kmeans.calibrate(data.clips(120, 30, data.OTHER_RPM))
