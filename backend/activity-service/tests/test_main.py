from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

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


def sample_activity_record(activity_id=None, shoe_id=None):
    return {
        "activity_id": activity_id or uuid4(),
        "user_id": main.DEFAULT_TEST_USER,
        "shoe_id": shoe_id,
        "title": "Morning Easy Run",
        "workout_type": "easy",
        "total_distance_km": 10.0,
        "total_duration_sec": 3300,
        "avg_pace_sec_per_km": 330,
        "perceived_exertion": 5,
        "started_at": datetime.now(UTC),
        "created_at": datetime.now(UTC),
    }


def make_mock_pool(conn):
    pool = MagicMock()
    pool.acquire.return_value = AsyncCM(conn)
    return pool


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "activity-service"}


def test_create_activity_success():
    shoe_id = uuid4()
    conn = AsyncMock()
    conn.transaction = MagicMock(return_value=AsyncCM())
    conn.fetchrow.return_value = sample_activity_record(shoe_id=shoe_id)
    conn.fetchval.return_value = uuid4()

    mock_exchange = AsyncMock()

    with (
        patch.object(main, "db_pool", make_mock_pool(conn)),
        patch.object(main, "rmq_exchange", mock_exchange),
    ):
        response = client.post(
            "/activities",
            json={
                "title": "Morning Easy Run",
                "workout_type": "easy",
                "total_distance_km": 10.0,
                "total_duration_sec": 3300,
                "perceived_exertion": 5,
                "shoe_id": str(shoe_id),
                "splits": [
                    {"split_number": 1, "distance_km": 1.0, "duration_sec": 330}
                ],
            },
        )

    assert response.status_code == 201
    assert response.json()["avg_pace_sec_per_km"] == 330
    assert mock_exchange.publish.await_count == 1


def test_list_and_get_activity_success():
    activity_id = uuid4()
    conn = AsyncMock()
    conn.fetch.side_effect = [
        [sample_activity_record(activity_id=activity_id)],
        [
            {
                "split_id": uuid4(),
                "activity_id": activity_id,
                "split_number": 1,
                "distance_km": 1.0,
                "duration_sec": 330,
                "pace_sec_per_km": 330,
                "elevation_gain_m": 5.0,
            }
        ],
    ]
    conn.fetchrow.return_value = sample_activity_record(activity_id=activity_id)

    with patch.object(main, "db_pool", make_mock_pool(conn)):
        list_resp = client.get("/activities")
        detail_resp = client.get(f"/activities/{activity_id}")

    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1
    assert detail_resp.status_code == 200
    assert len(detail_resp.json()["splits"]) == 1


def test_delete_activity_success():
    activity_id = uuid4()
    conn = AsyncMock()
    conn.fetchval.return_value = activity_id

    with patch.object(main, "db_pool", make_mock_pool(conn)):
        response = client.delete(f"/activities/{activity_id}")

    assert response.status_code == 204


# --- Failure Endpoint Tests ---


def test_get_activity_not_found():
    conn = AsyncMock()
    conn.fetchrow.return_value = None

    with patch.object(main, "db_pool", make_mock_pool(conn)):
        response = client.get(f"/activities/{uuid4()}")

    assert response.status_code == 404
    assert response.json()["detail"] == "Activity not found"


def test_delete_activity_not_found():
    conn = AsyncMock()
    conn.fetchval.return_value = None

    with patch.object(main, "db_pool", make_mock_pool(conn)):
        response = client.delete(f"/activities/{uuid4()}")

    assert response.status_code == 404


def test_create_activity_negative_distance_fails():
    response = client.post(
        "/activities",
        json={
            "title": "Invalid Run",
            "total_distance_km": -5.0,
            "total_duration_sec": 1500,
        },
    )
    assert response.status_code == 422
