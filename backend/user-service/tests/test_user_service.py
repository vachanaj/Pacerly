import uuid
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base, get_db
from app.main import app
from shared.auth import AuthenticatedUser, get_current_user

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DB_URL)
TestSessionLocal = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)

RUNNER_USER = AuthenticatedUser(
    user_id=uuid.UUID("11111111-1111-4111-8111-111111111111"),
    email="runner@pacerly.se",
    display_name="Alex Runner",
    roles=["runner"],
)

ADMIN_USER = AuthenticatedUser(
    user_id=uuid.UUID("22222222-2222-4222-8222-222222222222"),
    email="admin@pacerly.se",
    display_name="Platform Admin",
    roles=["runner", "admin"],
)


@pytest_asyncio.fixture(autouse=True)
async def setup_database():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def override_get_db():
    async with TestSessionLocal() as session:
        yield session


@pytest_asyncio.fixture
async def client():
    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_health_endpoint(client: AsyncClient):
    res = await client.get("/user/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_auto_provision_and_update_profile(client: AsyncClient):
    app.dependency_overrides[get_current_user] = lambda: RUNNER_USER

    # 1. First GET auto-creates the row in user_profiles
    res = await client.get("/user/me")
    assert res.status_code == 200
    data = res.json()
    assert data["user_id"] == str(RUNNER_USER.user_id)
    assert data["email"] == "runner@pacerly.se"
    assert data["profile_completed"] is False

    # 2. PUT updates physiological fields and marks profile completed
    update_payload = {
        "height_cm": 178.5,
        "weight_kg": 71.0,
        "resting_hr": 48,
        "max_hr": 192,
        "baseline_pace_sec_per_km": 285,
        "weekly_distance_goal_km": 55.0,
    }
    put_res = await client.put("/user/me", json=update_payload)
    assert put_res.status_code == 200
    updated = put_res.json()
    assert updated["profile_completed"] is True
    assert updated["resting_hr"] == 48
    assert updated["baseline_pace_sec_per_km"] == 285


@pytest.mark.asyncio
async def test_admin_can_list_profiles_and_user_can_delete(client: AsyncClient):
    app.dependency_overrides[get_current_user] = lambda: RUNNER_USER
    await client.get("/user/me")

    app.dependency_overrides[get_current_user] = lambda: ADMIN_USER
    admin_res = await client.get("/user/admin/profiles")
    assert admin_res.status_code == 200
    assert len(admin_res.json()) == 1

    app.dependency_overrides[get_current_user] = lambda: RUNNER_USER
    del_res = await client.delete("/user/me")
    assert del_res.status_code == 204


# --- Endpoint Failure Tests (REQ7) ---


@pytest.mark.asyncio
async def test_failure_unauthorized_without_token(client: AsyncClient):
    # Do not override get_current_user -> HTTPBearer must reject missing Authorization header
    res = await client.get("/user/me")
    assert res.status_code in (401, 403)


@pytest.mark.asyncio
async def test_failure_forbidden_for_non_admin_role(client: AsyncClient):
    app.dependency_overrides[get_current_user] = lambda: RUNNER_USER
    res = await client.get("/user/admin/profiles")
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_failure_validation_error_on_invalid_metrics(client: AsyncClient):
    app.dependency_overrides[get_current_user] = lambda: RUNNER_USER
    res = await client.put("/user/me", json={"resting_hr": 5, "height_cm": -10})
    assert res.status_code == 422