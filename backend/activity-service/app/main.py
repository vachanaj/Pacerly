import json
import os
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

import aio_pika
import asyncpg
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://pacerly:pacerly_dev@localhost:5433/activities",
)
RABBITMQ_URL = os.getenv(
    "RABBITMQ_URL",
    "amqp://pacerly:pacerly_dev@localhost:5672/",
)
EXCHANGE_NAME = "pacerly.events"
ROUTING_KEY = "activity.logged"

DEFAULT_TEST_USER = UUID("11111111-1111-1111-1111-111111111111")

db_pool: asyncpg.Pool | None = None
rmq_connection: aio_pika.abc.AbstractRobustConnection | None = None
rmq_channel: aio_pika.abc.AbstractChannel | None = None
rmq_exchange: aio_pika.abc.AbstractExchange | None = None


class SplitCreate(BaseModel):
    split_number: int = Field(..., ge=1, json_schema_extra={"example": 1})
    distance_km: float = Field(..., gt=0, json_schema_extra={"example": 1.0})
    duration_sec: int = Field(..., gt=0, json_schema_extra={"example": 325})
    elevation_gain_m: float = Field(
        default=0.0, ge=0, json_schema_extra={"example": 5.0}
    )


class ActivityCreate(BaseModel):
    title: str = Field(..., json_schema_extra={"example": "Morning Easy Run"})
    workout_type: str = Field(default="easy", json_schema_extra={"example": "easy"})
    total_distance_km: float = Field(..., gt=0, json_schema_extra={"example": 10.0})
    total_duration_sec: int = Field(..., gt=0, json_schema_extra={"example": 3300})
    perceived_exertion: int | None = Field(
        None, ge=1, le=10, json_schema_extra={"example": 5}
    )
    shoe_id: UUID | None = None
    started_at: datetime | None = None
    splits: list[SplitCreate] = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    global db_pool, rmq_connection, rmq_channel, rmq_exchange
    db_pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)
    rmq_connection = await aio_pika.connect_robust(RABBITMQ_URL)
    rmq_channel = await rmq_connection.channel()
    rmq_exchange = await rmq_channel.declare_exchange(
        EXCHANGE_NAME, aio_pika.ExchangeType.TOPIC, durable=True
    )
    yield
    await rmq_connection.close()
    await db_pool.close()


app = FastAPI(title="Pacerly Activity Service", lifespan=lifespan)


def format_activity(row: asyncpg.Record) -> dict:
    data = dict(row)
    data["total_distance_km"] = float(data["total_distance_km"])
    return data


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "activity-service"}


@app.post("/activities", status_code=201)
async def create_activity(
    activity: ActivityCreate,
    x_user_id: Annotated[UUID, Header()] = DEFAULT_TEST_USER,
):
    avg_pace = max(1, round(activity.total_duration_sec / activity.total_distance_km))
    started_at = activity.started_at or datetime.now(UTC)

    async with db_pool.acquire() as conn, conn.transaction():
        row = await conn.fetchrow(
            """
            INSERT INTO activities (
                user_id, shoe_id, title, workout_type,
                total_distance_km, total_duration_sec, avg_pace_sec_per_km,
                perceived_exertion, started_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            RETURNING *
            """,
            x_user_id,
            activity.shoe_id,
            activity.title,
            activity.workout_type,
            activity.total_distance_km,
            activity.total_duration_sec,
            avg_pace,
            activity.perceived_exertion,
            started_at,
        )
        activity_id = row["activity_id"]

        for split in activity.splits:
            split_pace = max(1, round(split.duration_sec / split.distance_km))
            await conn.execute(
                """
                INSERT INTO activity_splits (
                    activity_id, split_number, distance_km, duration_sec,
                    pace_sec_per_km, elevation_gain_m
                )
                VALUES ($1, $2, $3, $4, $5, $6)
                """,
                activity_id,
                split.split_number,
                split.distance_km,
                split.duration_sec,
                split_pace,
                split.elevation_gain_m,
            )

        event_payload = {
            "activity_id": str(activity_id),
            "user_id": str(x_user_id),
            "shoe_id": str(activity.shoe_id) if activity.shoe_id else None,
            "workout_type": activity.workout_type,
            "total_distance_km": float(activity.total_distance_km),
            "total_duration_sec": activity.total_duration_sec,
            "avg_pace_sec_per_km": avg_pace,
            "started_at": started_at.isoformat(),
        }

        event_id = await conn.fetchval(
            """
            INSERT INTO outbox_events (aggregate_id, routing_key, payload)
            VALUES ($1, $2, $3::jsonb)
            RETURNING event_id
            """,
            activity_id,
            ROUTING_KEY,
            json.dumps(event_payload),
        )

    await rmq_exchange.publish(
        aio_pika.Message(
            body=json.dumps(event_payload).encode(),
            content_type="application/json",
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        ),
        routing_key=ROUTING_KEY,
    )

    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE outbox_events SET published = TRUE WHERE event_id = $1",
            event_id,
        )

    return format_activity(row)


@app.get("/activities")
async def list_activities(
    x_user_id: Annotated[UUID, Header()] = DEFAULT_TEST_USER,
):
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM activities WHERE user_id = $1 ORDER BY started_at DESC",
            x_user_id,
        )
    return [format_activity(r) for r in rows]


@app.get("/activities/{activity_id}")
async def get_activity(
    activity_id: UUID,
    x_user_id: Annotated[UUID, Header()] = DEFAULT_TEST_USER,
):
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM activities WHERE activity_id = $1 AND user_id = $2",
            activity_id,
            x_user_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Activity not found")

        splits = await conn.fetch(
            "SELECT * FROM activity_splits WHERE activity_id = $1 ORDER BY split_number ASC",
            activity_id,
        )

    result = format_activity(row)
    result["splits"] = [
        {
            **dict(s),
            "distance_km": float(s["distance_km"]),
            "elevation_gain_m": float(s["elevation_gain_m"])
            if s["elevation_gain_m"] is not None
            else 0.0,
        }
        for s in splits
    ]
    return result


@app.delete("/activities/{activity_id}", status_code=204)
async def delete_activity(
    activity_id: UUID,
    x_user_id: Annotated[UUID, Header()] = DEFAULT_TEST_USER,
):
    async with db_pool.acquire() as conn:
        deleted = await conn.fetchval(
            "DELETE FROM activities WHERE activity_id = $1 AND user_id = $2 RETURNING activity_id",
            activity_id,
            x_user_id,
        )
    if not deleted:
        raise HTTPException(status_code=404, detail="Activity not found")
