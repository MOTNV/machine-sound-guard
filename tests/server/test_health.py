import requests


def test_health(server_url):
    r = requests.get(f"{server_url}/health", timeout=5)
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
