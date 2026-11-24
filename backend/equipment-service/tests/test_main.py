import json
from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from app import main
from fastapi.testclient import TestClient

client = TestClient(main.app)


class AsyncCM:
    def __init__(self, return_value=None):
        self.return_value = return_value

    async def __aenter__(self):
        return self.return_value

    async def __aexit__(self, exc_type, exc, tb):
        return False


def sample_shoe_record(shoe_id=None, status="active", mileage=0.0):
    return {
        "shoe_id": shoe_id or uuid4(),
        "user_id": main.DEFAULT_TEST_USER,
        "brand": "Adidas",
        "model": "Supernova Rise 3",
        "nickname": "Daily Trainer",
        "max_lifespan_km": 800.0,
        "current_mileage_km": mileage,
        "wear_percentage": round((mileage / 800.0) * 100, 2),
        "status": status,
        "is_default": False,
        "purchased_at": date(2026, 11, 22),
        "retired_at": datetime.now(UTC) if status == "retired" else None,
        "created_at": datetime.now(UTC),
    }


def make_mock_pool(conn):
    pool = MagicMock()
    pool.acquire.return_value = AsyncCM(conn)
    return pool


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "equipment-service"}


def test_create_shoe_success():
    conn = AsyncMock()
    conn.fetchrow.return_value = sample_shoe_record()

    with patch.object(main, "db_pool", make_mock_pool(conn)):
        response = client.post(
            "/shoes",
            json={
                "brand": "Adidas",
                "model": "Supernova Rise 3",
                "nickname": "Daily Trainer",
                "max_lifespan_km": 800.0,
            },
        )

    assert response.status_code == 201
    body = response.json()
    assert body["brand"] == "Adidas"
    assert body["current_mileage_km"] == 0.0


def test_list_shoes_success():
    conn = AsyncMock()
    conn.fetch.return_value = [sample_shoe_record(mileage=10.0)]

    with patch.object(main, "db_pool", make_mock_pool(conn)):
        response = client.get("/shoes")

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["current_mileage_km"] == 10.0


def test_retire_shoe_success():
    shoe_id = uuid4()
    conn = AsyncMock()
    conn.fetchrow.return_value = sample_shoe_record(shoe_id=shoe_id, status="retired")

    with patch.object(main, "db_pool", make_mock_pool(conn)):
        response = client.patch(f"/shoes/{shoe_id}/retire")

    assert response.status_code == 200
    assert response.json()["status"] == "retired"


# --- Failure Endpoint Tests ---


def test_retire_shoe_not_found():
    conn = AsyncMock()
    conn.fetchrow.return_value = None

    with patch.object(main, "db_pool", make_mock_pool(conn)):
        response = client.patch(f"/shoes/{uuid4()}/retire")

    assert response.status_code == 404
    assert response.json()["detail"] == "Shoe not found"


def test_create_shoe_invalid_lifespan_fails():
    response = client.post(
        "/shoes",
        json={
            "brand": "Adidas",
            "model": "Supernova Rise 3",
            "max_lifespan_km": -50.0,
        },
    )
    assert response.status_code == 422


# --- Consumer Unit Test ---


@pytest.mark.asyncio
async def test_handle_activity_logged_updates_mileage():
    shoe_id = uuid4()
    activity_id = uuid4()
    conn = AsyncMock()
    conn.transaction = MagicMock(return_value=AsyncCM())
    conn.fetchval.side_effect = [1, uuid4()]

    message = MagicMock()
    message.process.return_value = AsyncCM()
    message.body = json.dumps(
        {
            "activity_id": str(activity_id),
            "shoe_id": str(shoe_id),
            "total_distance_km": 12.5,
        }
    ).encode()

    with patch.object(main, "db_pool", make_mock_pool(conn)):
        await main.handle_activity_logged(message)

    assert conn.execute.await_count == 1
