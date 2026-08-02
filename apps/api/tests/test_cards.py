from fastapi.testclient import TestClient


def test_import_cards_accepts_copy_and_export_text(client: TestClient) -> None:
    copied = client.post(
        "/api/kakao/cards/import",
        json={
            "text": (
                "\ufeff=== 使用说明 ===\n"
                "这段说明不能作为卡密导入\n\n"
                "=== 卡密内容 ===\n"
                "FIRST-CARD\n"
                "SECOND-CARD\n"
            )
        },
    )
    exported = client.post(
        "/api/kakao/cards/import",
        json={"text": "\ufeff卡密导出\n\nTHIRD-CARD\n"},
    )

    assert copied.status_code == 200
    assert copied.json() == {"inserted": 2, "duplicates": 0}
    assert exported.status_code == 200
    assert exported.json() == {"inserted": 1, "duplicates": 0}

    cards = client.get("/api/kakao/cards", params={"limit": 20}).json()
    assert {item["code"] for item in cards["items"]} == {
        "FIRST-CARD",
        "SECOND-CARD",
        "THIRD-CARD",
    }


def test_large_card_import_is_batched_below_sqlite_parameter_limit(client: TestClient) -> None:
    response = client.post(
        "/api/kakao/cards/import",
        json={"text": "\n".join(f"CARD-{index}" for index in range(1001))},
    )

    assert response.status_code == 200
    assert response.json() == {"inserted": 1001, "duplicates": 0}
