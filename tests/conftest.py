"""모든 테스트가 같이 쓰는 fixture. 서버 주소는 환경변수로 바꿀 수 있다 (기본: docker compose로 띄운 내 PC)."""

import os

import pytest


@pytest.fixture(scope="session")
def server_url() -> str:
    return os.environ.get("SERVER_URL", "http://localhost:8000")
