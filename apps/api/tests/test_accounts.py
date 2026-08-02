from fastapi.testclient import TestClient

OUTLOOK_ACCOUNT = "alpha@example.com----secret----client-id----refresh-token"
LINK_ACCOUNT = "beta@example.com---https://mail.example.com/inbox/beta"


def test_import_list_and_stats(client: TestClient) -> None:
    response = client.post(
        "/api/accounts/import",
        json={"text": f"{OUTLOOK_ACCOUNT}\ninvalid-line\n{LINK_ACCOUNT}"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "inserted": 2,
        "updated": 0,
        "unchanged": 0,
        "invalid": 1,
        "invalid_lines": [2],
    }

    stats = client.get("/api/accounts/stats")
    assert stats.json() == {
        "total": 2,
        "available": 2,
        "in_use": 0,
        "done": 0,
        "failed": 0,
    }

    accounts = client.get("/api/accounts", params={"status": "available", "search": "beta"})
    assert accounts.status_code == 200
    payload = accounts.json()
    assert payload["total"] == 1
    assert payload["items"][0]["email"] == "beta@example.com"
    assert "refresh_token" not in payload["items"][0]


def test_import_accounts_accepts_wrapped_copy_text(client: TestClient) -> None:
    response = client.post(
        "/api/accounts/import",
        json={
            "text": (f"\ufeff=== 使用说明 ===\n看购买说明页\n\n=== 卡密内容 ===\n{LINK_ACCOUNT}\n")
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "inserted": 1,
        "updated": 0,
        "unchanged": 0,
        "invalid": 0,
        "invalid_lines": [],
    }


def test_claim_release_and_state_guards(client: TestClient) -> None:
    client.post("/api/accounts/import", json={"text": OUTLOOK_ACCOUNT})

    claimed = client.post("/api/accounts/claim", json={})
    assert claimed.status_code == 200
    assert claimed.json()["status"] == "in_use"
    assert claimed.json()["refresh_token"] == "refresh-token"

    unavailable = client.post("/api/accounts/claim", json={"email": "alpha@example.com"})
    assert unavailable.status_code == 409

    cannot_delete = client.delete("/api/accounts/alpha@example.com")
    assert cannot_delete.status_code == 409

    released = client.post("/api/accounts/alpha@example.com/release")
    assert released.status_code == 200
    assert released.json()["status"] == "available"

    deleted = client.delete("/api/accounts/alpha@example.com")
    assert deleted.status_code == 204
    assert client.get("/api/accounts/alpha@example.com").status_code == 404


def test_reimport_updates_source_without_resetting_state(client: TestClient) -> None:
    client.post("/api/accounts/import", json={"text": OUTLOOK_ACCOUNT})
    client.post("/api/accounts/claim", json={})

    updated_source = "alpha@example.com----new-secret----new-client----new-refresh"
    response = client.post("/api/accounts/import", json={"text": updated_source})

    assert response.json()["updated"] == 1
    detail = client.get("/api/accounts/alpha@example.com").json()
    assert detail["status"] == "in_use"
    assert detail["password"] == "new-secret"


def test_large_account_import_is_batched_below_sqlite_parameter_limit(
    client: TestClient,
) -> None:
    lines = [
        f"user-{index}@example.com----password----client----refresh-{index}"
        for index in range(1001)
    ]

    response = client.post("/api/accounts/import", json={"text": "\n".join(lines)})

    assert response.status_code == 200
    assert response.json()["inserted"] == 1001
