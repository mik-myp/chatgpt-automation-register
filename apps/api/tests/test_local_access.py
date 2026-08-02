from fastapi.testclient import TestClient


def test_local_api_accepts_loopback_host_and_origin(client: TestClient) -> None:
    response = client.get(
        "/api/health",
        headers={"host": "127.0.0.1:8000", "origin": "http://localhost:5173"},
    )
    assert response.status_code == 200


def test_local_api_rejects_non_local_host(client: TestClient) -> None:
    response = client.get("/api/health", headers={"host": "register.example.com"})
    assert response.status_code == 403
    assert "Host" in response.json()["detail"]


def test_local_api_rejects_non_local_origin(client: TestClient) -> None:
    response = client.post(
        "/api/settings/data/cleanup",
        headers={"origin": "https://attacker.example"},
    )
    assert response.status_code == 403
    assert "Origin" in response.json()["detail"]
